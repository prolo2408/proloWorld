#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prolo Wiki - Server

Eine Wissenssammlung aus eigenstaendigen HTML-Seiten. Der Server haelt den
Themenbaum, den Suchindex und die Einspielung neuer Seiten. Die Seiten selbst
laufen im iframe und bringen ihr eigenes Verhalten mit.

Anmeldung kommt ausschliesslich als Kopfzeile von Traefik/Authentik.
Keine eigene Nutzerverwaltung, kein Gastzugang.
"""

import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

# ---------------------------------------------------------------- Konfiguration

# Fassungsnummer der Anwendung (B-23). Ohne sie liess sich am laufenden
# System nicht feststellen, welche Fassung des Wikis arbeitet - das Bordbuch
# hatte VERSION, --version und /api/version, das Wiki gar nichts. Gelesen von
# --version, /api/version und der image:-Zeile im docker-compose.yml; die
# drei muessen zusammenpassen.
VERSION = "1.0.0"

DATEN = os.environ.get("WIKI_DATEN", "/daten")
SEITEN = os.environ.get("WIKI_SEITEN", "/seiten")
PORT = int(os.environ.get("WIKI_PORT", "8080"))
ADMIN_GRUPPE = os.environ.get("WIKI_ADMIN_GRUPPE", "wiki-admin")
# Notnagel fuer den allerersten Start, solange die Gruppe in Authentik fehlt.
ADMIN_NUTZER = {n.strip() for n in os.environ.get("WIKI_ADMIN_NUTZER", "").split(",") if n.strip()}
# Ab dieser Groesse wird ein eingebetteter Base64-Block zum Anhang.
ANHANG_SCHWELLE_B = int(os.environ.get("WIKI_ANHANG_SCHWELLE_B", "200000"))
MAX_UPLOAD_B = int(os.environ.get("WIKI_MAX_UPLOAD_B", str(80 * 1024 * 1024)))

DB_DATEI = os.path.join(DATEN, "wiki.db")
VORSCHAU_ORDNER = os.path.join(SEITEN, ".vorschau")
EIGENER_ORDNER = os.path.dirname(os.path.abspath(__file__))

SLUG_MUSTER = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")
ANKER_MUSTER = re.compile(r"^[A-Za-z][A-Za-z0-9_:.-]{0,63}$")
DATEINAME_MUSTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")

_lokal = threading.local()


def jetzt():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def heute():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- Datenbank

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS seite(
  id            INTEGER PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,
  titel         TEXT NOT NULL,
  kurz          TEXT NOT NULL DEFAULT '',
  pfad_json     TEXT NOT NULL DEFAULT '[]',
  gruppen_json  TEXT NOT NULL DEFAULT '[]',
  stand         TEXT NOT NULL DEFAULT '',
  fassung       INTEGER NOT NULL DEFAULT 1,
  groesse_b     INTEGER NOT NULL DEFAULT 0,
  regelkonform  INTEGER NOT NULL DEFAULT 1,
  hinweise_json TEXT NOT NULL DEFAULT '[]',
  nutzer_id     TEXT NOT NULL DEFAULT '',
  geaendert     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS abschnitt(
  id           INTEGER PRIMARY KEY,
  seite_id     INTEGER NOT NULL REFERENCES seite(id) ON DELETE CASCADE,
  anker        TEXT NOT NULL DEFAULT '',
  titel        TEXT NOT NULL DEFAULT '',
  ebene        INTEGER NOT NULL DEFAULT 1,
  stichworte   TEXT NOT NULL DEFAULT '',
  text         TEXT NOT NULL DEFAULT '',
  reihenfolge  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_abschnitt_seite ON abschnitt(seite_id);

CREATE TABLE IF NOT EXISTS anhang(
  id         INTEGER PRIMARY KEY,
  seite_id   INTEGER NOT NULL REFERENCES seite(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  typ        TEXT NOT NULL DEFAULT '',
  groesse_b  INTEGER NOT NULL DEFAULT 0,
  marke      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_anhang_seite ON anhang(seite_id);

CREATE TABLE IF NOT EXISTS fassung(
  id         INTEGER PRIMARY KEY,
  seite_id   INTEGER NOT NULL REFERENCES seite(id) ON DELETE CASCADE,
  nummer     INTEGER NOT NULL,
  datum      TEXT NOT NULL,
  nutzer_id  TEXT NOT NULL DEFAULT '',
  datei      TEXT NOT NULL,
  groesse_b  INTEGER NOT NULL DEFAULT 0,
  kommentar  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fassung_seite ON fassung(seite_id);

-- Freigabe fuer einen ganzen Themenzweig. Wird nach unten vererbt.
CREATE TABLE IF NOT EXISTS zweig(
  pfad         TEXT PRIMARY KEY,
  gruppen_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS einstellung(
  nutzer_id  TEXT NOT NULL,
  schluessel TEXT NOT NULL,
  wert       TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(nutzer_id, schluessel)
);

CREATE TABLE IF NOT EXISTS lesezeichen(
  nutzer_id TEXT NOT NULL,
  slug      TEXT NOT NULL,
  anker     TEXT NOT NULL DEFAULT '',
  titel     TEXT NOT NULL DEFAULT '',
  angelegt  TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(nutzer_id, slug, anker)
);

CREATE TABLE IF NOT EXISTS zuletzt(
  nutzer_id TEXT NOT NULL,
  slug      TEXT NOT NULL,
  gesehen   TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(nutzer_id, slug)
);

-- Ein Treffer ist ein Abschnitt einer Seite oder eine Seite eines Anhangs.
CREATE TABLE IF NOT EXISTS treffer(
  id              INTEGER PRIMARY KEY,
  seite_id        INTEGER NOT NULL REFERENCES seite(id) ON DELETE CASCADE,
  art             TEXT NOT NULL DEFAULT 'abschnitt',
  anker           TEXT NOT NULL DEFAULT '',
  anhang_name     TEXT NOT NULL DEFAULT '',
  seitennr        INTEGER NOT NULL DEFAULT 0,
  abschnittstitel TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_treffer_seite ON treffer(seite_id);
"""

SCHEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS suche USING fts5(
  titel, stichworte, text,
  tokenize="unicode61 remove_diacritics 2",
  prefix='2 3 4'
);
"""

# Der Trigramm-Index faengt Teilwoerter. Bei deutschen Komposita ist das
# der Unterschied zwischen "maske findet nichts" und "maske findet
# Subnetzmaske".
SCHEMA_TRI = """
CREATE VIRTUAL TABLE IF NOT EXISTS suche_tri USING fts5(
  inhalt, tokenize="trigram remove_diacritics 1"
);
"""
SCHEMA_TRI_EINFACH = """
CREATE VIRTUAL TABLE IF NOT EXISTS suche_tri USING fts5(
  inhalt, tokenize="trigram"
);
"""


def db():
    """
    Eine Verbindung je Anfrage. Frueher war sie an den Thread gebunden und
    wurde nie geschlossen - brach ein Schreibvorgang mittendrin ab, blieb
    dessen Transaktion offen und sperrte die Datenbank fuer alles Weitere.
    """
    v = getattr(_lokal, "db", None)
    if v is None:
        v = sqlite3.connect(DB_DATEI, timeout=20)
        v.row_factory = sqlite3.Row
        v.execute("PRAGMA foreign_keys=ON")
        v.execute("PRAGMA busy_timeout=8000")
        _lokal.db = v
    return v


def db_freigeben(fehlgeschlagen=False):
    """Am Ende jeder Anfrage: Angefangenes zuruecknehmen und schliessen."""
    v = getattr(_lokal, "db", None)
    if v is None:
        return
    try:
        if fehlgeschlagen or v.in_transaction:
            v.rollback()
    except Exception:
        pass
    try:
        v.close()
    except Exception:
        pass
    _lokal.db = None


def datenbank_anlegen():
    os.makedirs(DATEN, exist_ok=True)
    os.makedirs(SEITEN, exist_ok=True)
    v = db()
    v.executescript(SCHEMA)
    v.executescript(SCHEMA_FTS)
    try:
        v.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vokabular "
                  "USING fts5vocab(suche, 'row')")
    except sqlite3.OperationalError:
        sys.stderr.write("HINWEIS: fts5vocab nicht verfuegbar, "
                         "keine Wortvorschlaege bei Tippfehlern.\n")
    try:
        v.executescript(SCHEMA_TRI)
    except sqlite3.OperationalError:
        try:
            v.executescript(SCHEMA_TRI_EINFACH)
        except sqlite3.OperationalError:
            sys.stderr.write("HINWEIS: Trigramm-Index nicht verfuegbar, "
                             "Teilwortsuche eingeschraenkt.\n")
    v.commit()


# ---------------------------------------------------------------- Einstellungen

EINSTELLUNGEN = {
    # schluessel: (Vorgabe, erlaubte Werte oder None fuer ja/nein)
    "thema": ("system", {"system", "hell", "dunkel"}),
    "start": ("uebersicht", {"uebersicht", "zuletzt"}),
    "pdf_treffer": ("1", {"0", "1"}),
    "baum_zu": ("0", {"0", "1"}),
}


def einstellungen_lesen(kennung):
    werte = {k: v[0] for k, v in EINSTELLUNGEN.items()}
    for z in db().execute("SELECT schluessel, wert FROM einstellung WHERE nutzer_id=?",
                          (kennung,)).fetchall():
        if z["schluessel"] in EINSTELLUNGEN:
            werte[z["schluessel"]] = z["wert"]
    return werte


def einstellung_setzen(kennung, schluessel, wert):
    if schluessel not in EINSTELLUNGEN:
        raise Antwort(400, f"Die Einstellung '{schluessel}' gibt es nicht.")
    erlaubt = EINSTELLUNGEN[schluessel][1]
    wert = str(wert)
    if erlaubt and wert not in erlaubt:
        raise Antwort(400, f"Fuer '{schluessel}' ist '{wert}' kein erlaubter Wert.")
    db().execute("INSERT INTO einstellung(nutzer_id,schluessel,wert) VALUES(?,?,?) "
                 "ON CONFLICT(nutzer_id,schluessel) DO UPDATE SET wert=excluded.wert",
                 (kennung, schluessel, wert))


# ---------------------------------------------------------------- Anmeldung

class Nutzer:
    def __init__(self, kennung, name, email, gruppen):
        self.kennung = kennung
        self.name = name or kennung
        self.email = email or ""
        self.gruppen = set(gruppen)
        self.gruppen_roh = ""
        self.ist_admin = (ADMIN_GRUPPE in self.gruppen) or (kennung in ADMIN_NUTZER)


def nutzer_aus_kopf(kopf):
    """Identitaet ausschliesslich aus den Authentik-Kopfzeilen."""
    kennung = (kopf.get("X-Authentik-Username") or "").strip()
    if not kennung:
        return None
    # Authentik trennt die Gruppen mit einem Pipe ("foo|bar|baz"), nicht mit
    # Komma. Beides und Semikolon werden akzeptiert, damit ein anderer
    # Anbieter davor nicht alles lahmlegt.
    roh = kopf.get("X-Authentik-Groups") or ""
    gruppen = [g.strip() for g in re.split(r"[|,;]", roh) if g.strip()]
    n = Nutzer(kennung, (kopf.get("X-Authentik-Name") or "").strip(),
               (kopf.get("X-Authentik-Email") or "").strip(), gruppen)
    n.gruppen_roh = roh
    return n


def zweig_gruppen(pfad_liste):
    """Geerbte Gruppen aller Ebenen oberhalb der Seite."""
    noetig = set()
    v = db()
    for i in range(1, len(pfad_liste) + 1):
        p = "/".join(pfad_liste[:i])
        z = v.execute("SELECT gruppen_json FROM zweig WHERE pfad=?", (p,)).fetchone()
        if z:
            noetig |= set(json.loads(z["gruppen_json"]))
    return noetig


def darf_sehen(nutzer, seite_zeile):
    if nutzer.ist_admin:
        return True
    noetig = set(json.loads(seite_zeile["gruppen_json"] or "[]"))
    noetig |= zweig_gruppen(json.loads(seite_zeile["pfad_json"] or "[]"))
    if not noetig:
        return True
    return bool(noetig & nutzer.gruppen)


def sichtbare_seiten(nutzer):
    v = db()
    zeilen = v.execute("SELECT * FROM seite ORDER BY titel").fetchall()
    return [z for z in zeilen if darf_sehen(nutzer, z)]


# ---------------------------------------------------------------- HTML-Werkzeug

def text_aus_html(bruchstueck):
    """Sichtbaren Text herausloesen. Script und Style fliegen raus."""
    s = re.sub(r"(?is)<script\b.*?</script>", " ", bruchstueck)
    s = re.sub(r"(?is)<style\b.*?</style>", " ", s)
    s = re.sub(r"(?s)<!--.*?-->", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
          .replace("&rarr;", "->").replace("&mdash;", "-").replace("&ndash;", "-"))
    s = re.sub(r"&[a-zA-Z#0-9]{2,8};", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def meta_block_lesen(html):
    m = re.search(
        r'<script[^>]+id=["\']wiki-meta["\'][^>]*>(.*?)</script>', html, re.S | re.I)
    if not m:
        return None, None
    try:
        return json.loads(m.group(1)), m.span()
    except json.JSONDecodeError as e:
        raise ValueError(f"Der Block wiki-meta ist kein gueltiges JSON: {e}")


MAGIE = [
    ("JVBERi0", "application/pdf", "pdf"),
    ("iVBORw0", "image/png", "png"),
    ("/9j/", "image/jpeg", "jpg"),
    ("R0lGOD", "image/gif", "gif"),
    ("UklGR", "image/webp", "webp"),
    ("AAABAA", "image/x-icon", "ico"),
    ("d09GMg", "font/woff2", "woff2"),
]


def typ_erkennen(b64_anfang):
    for marke, typ, endung in MAGIE:
        if b64_anfang.startswith(marke):
            return typ, endung
    return "application/octet-stream", "bin"


def anhaenge_ausgliedern(html, slug, schwelle=ANHANG_SCHWELLE_B):
    """
    Grosse Base64-Bloecke aus dem HTML holen und als Datei ablegen.

    Ohne diesen Schritt schleppt jede Seite ihre Anhaenge bei jedem Aufruf mit,
    und die Suche kommt an den Inhalt nie heran.
    """
    gefunden = []
    zaehler = {}

    def naechster_name(endung, marke):
        basis = re.sub(r"[^a-z0-9-]", "", (marke or "anhang").lower()) or "anhang"
        zaehler[basis] = zaehler.get(basis, 0) + 1
        n = zaehler[basis]
        return f"{basis}.{endung}" if n == 1 else f"{basis}-{n}.{endung}"

    def script_ersetzen(m):
        auf, inhalt = m.group(1), m.group(2)
        roh = inhalt.strip()
        if len(roh) < schwelle or not re.fullmatch(r"[A-Za-z0-9+/=\s]+", roh):
            return m.group(0)
        typ, endung = typ_erkennen(roh[:10])
        marke_m = re.search(r'id=["\']([^"\']+)["\']', auf)
        marke = marke_m.group(1) if marke_m else ""
        name = naechster_name(endung, marke)
        try:
            daten = base64.b64decode(re.sub(r"\s", "", roh), validate=False)
        except Exception:
            return m.group(0)
        gefunden.append({"name": name, "typ": typ, "daten": daten, "marke": marke})
        auf_neu = re.sub(r'\s*data-wiki-anhang=["\'][^"\']*["\']', "", auf)
        auf_neu = auf_neu.rstrip(">") + f' data-wiki-anhang="{name}">'
        return auf_neu + "</script>"

    neu = re.sub(r"(?is)(<script\b[^>]*>)(.*?)</script>", script_ersetzen, html)

    def uri_ersetzen(m):
        praefix, roh = m.group(1), m.group(2)
        if len(roh) < schwelle:
            return m.group(0)
        typ, endung = typ_erkennen(roh[:10])
        name = naechster_name(endung, "eingebettet")
        try:
            daten = base64.b64decode(re.sub(r"\s", "", roh), validate=False)
        except Exception:
            return m.group(0)
        gefunden.append({"name": name, "typ": typ, "daten": daten, "marke": ""})
        return f'{praefix}anhaenge/{name}'

    neu = re.sub(r"(data:[a-zA-Z0-9/.+-]+;base64,)([A-Za-z0-9+/=]{1000,})",
                 lambda m: uri_ersetzen(m) if len(m.group(2)) >= schwelle else m.group(0), neu)
    return neu, gefunden


def pdf_seitentext(pfad):
    """Seitenweiser Text eines PDFs. Leere Liste, wenn es nicht klappt."""
    try:
        e = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", pfad, "-"],
                           capture_output=True, timeout=180)
        if e.returncode != 0:
            return []
        roh = e.stdout.decode("utf-8", "replace")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    seiten = roh.split("\x0c")
    return [re.sub(r"\s+", " ", s).strip() for s in seiten]


# ---------------------------------------------------------------- Pruefung

FARB_MUSTER = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
ERLAUBT_FARBE_IM_TOKENBLOCK = re.compile(r"(?s):root\s*\{.*?\}|\[data-theme[^\]]*\]\s*\{.*?\}"
                                         r"|body\[data-theme[^\]]*\]\s*\{.*?\}")


def regeln_pruefen(html, meta):
    """Gibt (fehler, warnungen) zurueck. Fehler verhindern die Uebernahme."""
    fehler, warnungen = [], []

    slug = (meta.get("slug") or "").strip()
    if not slug:
        fehler.append("Im Block wiki-meta fehlt das Feld 'slug'.")
    elif not SLUG_MUSTER.match(slug):
        fehler.append(f"Der slug '{slug}' ist nicht erlaubt. Nur Kleinbuchstaben, "
                      "Ziffern und Bindestriche, Anfang und Ende ohne Bindestrich.")
    if not (meta.get("titel") or "").strip():
        fehler.append("Im Block wiki-meta fehlt das Feld 'titel'.")

    pfad = meta.get("pfad")
    if not isinstance(pfad, list) or not pfad or not all(isinstance(p, str) and p.strip() for p in pfad):
        fehler.append("Das Feld 'pfad' muss eine nicht leere Liste sein, "
                      'zum Beispiel ["Technik", "Netzwerke"].')
    elif len(pfad) > 4:
        warnungen.append("Der Pfad ist tiefer als vier Ebenen. Das wird in der "
                         "Navigation unuebersichtlich.")

    gruppen = meta.get("gruppen", [])
    if not isinstance(gruppen, list) or not all(isinstance(g, str) for g in gruppen):
        fehler.append("Das Feld 'gruppen' muss eine Liste von Gruppennamen sein "
                      "(leere Liste = alle Angemeldeten).")

    abschnitte = meta.get("abschnitte", [])
    if not isinstance(abschnitte, list):
        fehler.append("Das Feld 'abschnitte' muss eine Liste sein.")
        abschnitte = []
    if not abschnitte:
        warnungen.append("Keine Abschnitte deklariert. Die Suche faellt auf den "
                         "sichtbaren HTML-Text zurueck und kann nicht gezielt springen.")

    gesehen = set()
    for i, a in enumerate(abschnitte, 1):
        if not isinstance(a, dict):
            fehler.append(f"Abschnitt {i} ist kein Objekt.")
            continue
        anker = (a.get("anker") or "").strip()
        if not anker:
            fehler.append(f"Abschnitt {i} ({a.get('titel', '?')}) hat keinen Anker.")
            continue
        if not ANKER_MUSTER.match(anker):
            fehler.append(f"Anker '{anker}' ist nicht erlaubt.")
        if anker in gesehen:
            fehler.append(f"Der Anker '{anker}' kommt mehrfach vor. Anker muessen "
                          "eindeutig sein, sonst springt die Suche ins Leere.")
        gesehen.add(anker)
        if not (a.get("titel") or "").strip():
            fehler.append(f"Abschnitt mit Anker '{anker}' hat keinen Titel.")
        if not re.search(r'\bid=["\']' + re.escape(anker) + r'["\']', html):
            warnungen.append(f"Zum Anker '{anker}' gibt es im HTML kein Element mit "
                             f'id="{anker}". Der Sprung aus der Suche landet dann oben '
                             "auf der Seite.")
        if not (a.get("text") or "").strip() and not (a.get("stichworte") or []):
            warnungen.append(f"Abschnitt '{anker}' hat weder Text noch Stichworte. "
                             "Er ist dann kaum auffindbar.")

    if not re.search(r"(?i)<html[^>]*\slang=", html):
        warnungen.append('Dem <html>-Tag fehlt lang="de".')
    if not re.search(r"(?i)<meta[^>]+viewport", html):
        warnungen.append("Es fehlt die viewport-Angabe. Am Handy wird die Seite "
                         "dann winzig dargestellt.")

    # Schemalose Verweise (//fremd.tld/x.js) und javascript:-Ziele wurden
    # bisher nicht erkannt (B-07 Nebenbefund, B-48). Die CSP faengt sie zwar
    # ab, aber der Einspielende erfuhr nicht, warum seine Seite halb kaputt
    # ist - und genau das soll die Pruefung leisten.
    extern = set(re.findall(
        r'(?i)(?:src|href)=["\'](\s*(?:https?:)?//[^"\']+|javascript:[^"\']*)["\']',
        html))
    extern = {u.strip() for u in extern}
    extern = {u for u in extern if not u.startswith(("https://wiki.prolo.me",))}
    js_ziele = {u for u in extern if u.lower().startswith("javascript:")}
    extern -= js_ziele
    if extern:
        bsp = ", ".join(sorted(extern)[:3])
        fehler.append("Externe Verweise sind nicht erlaubt (kein CDN, keine "
                      f"fremden Schriften). Gefunden: {bsp}")
    if js_ziele:
        fehler.append("javascript:-Verweise sind nicht erlaubt - die CSP "
                      "blockiert sie ohnehin, die Seite waere also halb kaputt. "
                      f"Gefunden: {', '.join(sorted(js_ziele)[:3])}")

    ohne_token = ERLAUBT_FARBE_IM_TOKENBLOCK.sub(" ", html)
    ohne_token = re.sub(r"(?is)<script\b.*?</script>", " ", ohne_token)
    treffer = FARB_MUSTER.findall(ohne_token)
    if treffer:
        warnungen.append(f"{len(treffer)} Farbwerte ausserhalb des Tokenblocks "
                         "gefunden. Das Regelblatt verlangt Tokens aus Abschnitt 2.")

    if not re.search(r"focus-visible", html):
        warnungen.append("Der Pflichtblock aus Regelblatt 8.1 fehlt "
                         "(focus-visible, prefers-reduced-motion).")

    return fehler, warnungen


def sicherheit_pruefen(html):
    """Was eine eingespielte Seite an Verhalten mitbringt (B-07).

    Getrennt von regeln_pruefen(), weil das eine Designpruefung ist und diese
    hier keine ist. Das Ergebnis sind ausdruecklich HINWEISE, keine Fehler:
    die Architektur sieht eigenstaendige Seiten mit eigenem Verhalten vor, und
    eine Seite darf Skripte mitbringen. Aber der Einspielende muss sehen, WAS
    er sich holt - bevor er "Uebernehmen" drueckt.

    Seit B-03 Teil 4 laufen die Seiten in einem opaken Origin, koennen also
    weder an die Wiki-API noch an Cookies oder die Huelle. Diese Hinweise sind
    die zweite Schicht: sie machen sichtbar, was der Code tut, statt sich
    allein darauf zu verlassen, dass die Sandbox haelt.
    """
    hinweise = []

    # Der Meta-Block ist type="application/json" und kein ausfuehrbarer Code -
    # er darf die Zaehlung nicht aufblaehen, sonst meldet die Pruefung bei
    # jeder voellig harmlosen Seite einen Skriptblock und wird nicht gelesen.
    skripte = [(attr, inhalt) for attr, inhalt in
               re.findall(r"(?is)<script\b([^>]*)>(.*?)</script>", html)]
    code = [inhalt for attr, inhalt in skripte
            if inhalt.strip()
            and not re.search(r'(?i)type\s*=\s*["\']?application/(?:ld\+)?json', attr)]
    if code:
        zeichen = sum(len(k) for k in code)
        hinweise.append(f"{len(code)} Skriptblock(e) mit zusammen {zeichen} "
                        "Zeichen. Die Seite bringt eigenen Code mit.")

    ganz = "\n".join(code)
    for muster, was in (
            (r"\bfetch\s*\(", "fetch( - die Seite ruft Adressen ab"),
            (r"\bXMLHttpRequest\b", "XMLHttpRequest - die Seite ruft Adressen ab"),
            (r"\bnavigator\.sendBeacon\b", "navigator.sendBeacon - die Seite sendet Daten"),
            (r"\bparent\s*\.", "parent. - die Seite greift nach der Huelle"),
            (r"\btop\s*\.", "top. - die Seite greift nach dem obersten Fenster"),
            (r"\bdocument\s*\.\s*cookie\b", "document.cookie - die Seite liest Cookies"),
            (r"\blocalStorage\b", "localStorage - die Seite speichert im Browser"),
            (r"\bsessionStorage\b", "sessionStorage - die Seite speichert im Browser"),
            (r"\bindexedDB\b", "indexedDB - die Seite speichert im Browser"),
            (r"\beval\s*\(", "eval( - die Seite fuehrt zusammengesetzten Code aus"),
            (r"new\s+Function\s*\(", "new Function( - die Seite baut Code zur Laufzeit"),
            (r"\bWebSocket\b", "WebSocket - die Seite haelt eine Verbindung offen"),
    ):
        if re.search(muster, ganz):
            hinweise.append(was)

    for tag in ("iframe", "object", "embed", "form"):
        n = len(re.findall(r"(?i)<%s\b" % tag, html))
        if n:
            hinweise.append(f"{n} <{tag}>-Element(e) in der Seite.")

    schemalos = re.findall(r'(?i)(?:src|href)=["\']\s*//[^"\']+', html)
    if schemalos:
        hinweise.append(f"{len(schemalos)} schemalose Verweise (//...). Die CSP "
                        "blockiert sie - die Seite bleibt an diesen Stellen leer.")

    return hinweise


# ---------------------------------------------------------------- Import

def abschnitte_ableiten(html):
    """Notnagel, wenn die Seite keine Abschnitte deklariert."""
    ergebnis = []
    for m in re.finditer(r'(?is)<(h2|h3|section)\b([^>]*)>', html):
        attr = m.group(2)
        am = re.search(r'id=["\']([^"\']+)["\']', attr)
        if not am:
            continue
        anker = am.group(1)
        rest = html[m.end():m.end() + 4000]
        titel = text_aus_html(rest)[:80] or anker
        ergebnis.append({"anker": anker, "titel": titel, "stichworte": [],
                         "text": text_aus_html(rest)[:4000]})
    return ergebnis


def meta_block_ersetzen(html, meta):
    """Den Meta-Block im HTML auf den tatsaechlich uebernommenen Stand bringen."""
    neu = ('<script type="application/json" id="wiki-meta">\n'
           + json.dumps(meta, ensure_ascii=False, indent=1) + "\n</script>")
    return re.sub(r'<script[^>]+id=["\']wiki-meta["\'][^>]*>.*?</script>',
                  lambda m: neu, html, count=1, flags=re.S | re.I)


def ueberschreiben(meta, frage):
    """
    Pfad, Titel, Kennung und Freigabe aus der Oberflaeche haben Vorrang vor
    dem, was in der Datei steht. Sonst muesste die Datei geaendert werden,
    nur um eine Seite umzuhaengen.
    """
    geaendert = []
    pfad = (frage.get("pfad") or [""])[0].strip().strip("/")
    if pfad:
        neu = [t.strip() for t in re.split(r"[/›>]", pfad) if t.strip()]
        if neu and neu != meta.get("pfad"):
            meta["pfad"] = neu
            geaendert.append("Pfad")
    titel = (frage.get("titel") or [""])[0].strip()
    if titel and titel != meta.get("titel"):
        meta["titel"] = titel[:120]
        geaendert.append("Titel")
    slug = (frage.get("slug") or [""])[0].strip().lower()
    if slug and slug != meta.get("slug"):
        if not SLUG_MUSTER.match(slug):
            raise Antwort(400, f"Die Kennung '{slug}' ist nicht erlaubt. Nur "
                               "Kleinbuchstaben, Ziffern und Bindestriche.")
        meta["slug"] = slug
        geaendert.append("Kennung")
    if "gruppen" in frage:
        g = [x.strip() for x in (frage.get("gruppen") or [""])[0].split(",") if x.strip()]
        if g != meta.get("gruppen", []):
            meta["gruppen"] = g
            geaendert.append("Freigabe")
    return geaendert


def seitenordner(slug):
    return os.path.join(SEITEN, slug)


def pruefen(rohbytes, nutzer):
    """Vollstaendiger Probelauf ohne zu speichern. Liefert den Bericht."""
    bericht = {"fehler": [], "warnungen": [], "anhaenge": [], "abschnitte": 0,
               # Eigener Schluessel, getrennt von den Designwarnungen (B-07):
               # die Oberflaeche zeigt ihn als eigenen Abschnitt vor dem
               # Uebernehmen-Knopf.
               "sicherheit": [],
               "meta": None, "groesse_vorher_b": len(rohbytes), "groesse_nachher_b": 0,
               "neu": True, "fassung": 1}
    try:
        html = rohbytes.decode("utf-8")
    except UnicodeDecodeError:
        bericht["fehler"].append("Die Datei ist nicht UTF-8 kodiert. "
                                 "Bitte als UTF-8 speichern.")
        return bericht, None, None

    try:
        meta, _ = meta_block_lesen(html)
    except ValueError as e:
        bericht["fehler"].append(str(e))
        return bericht, None, None

    if meta is None:
        bericht["fehler"].append(
            'Der Block <script type="application/json" id="wiki-meta"> fehlt. '
            "Ohne ihn weiss das Wiki nicht, wohin die Seite gehoert und was "
            "durchsuchbar ist.")
        return bericht, None, None

    bericht["meta"] = meta
    fehler, warnungen = regeln_pruefen(html, meta)
    bericht["fehler"] += fehler
    bericht["warnungen"] += warnungen
    # Sicherheitshinweise auch dann sammeln, wenn die Designpruefung Fehler
    # gefunden hat (B-07): wer eine Seite aus fremder Quelle einspielt, will
    # gerade dann wissen, was darin steckt.
    bericht["sicherheit"] = sicherheit_pruefen(html)
    if fehler:
        return bericht, None, None

    slug = meta["slug"].strip()
    html_neu, anhaenge = anhaenge_ausgliedern(html, slug)
    bericht["groesse_nachher_b"] = len(html_neu.encode("utf-8"))
    bericht["anhaenge"] = [{"name": a["name"], "typ": a["typ"],
                            "groesse_b": len(a["daten"]), "marke": a["marke"]}
                           for a in anhaenge]
    versteht_anhaenge = "data-wiki-anhang" in html
    for a in anhaenge:
        if a["marke"] and not versteht_anhaenge:
            bericht["warnungen"].append(
                f"Der Block '{a['marke']}' wurde als Anhang {a['name']} ausgelagert, "
                "aber die Seite liest ihn noch aus dem eingebetteten Text. Der "
                "Ladecode muss das Attribut data-wiki-anhang auswerten, sonst "
                "bleibt der Anhang leer.")

    abschnitte = meta.get("abschnitte") or []
    if not abschnitte:
        abschnitte = abschnitte_ableiten(html_neu)
        if abschnitte:
            bericht["warnungen"].append(
                f"{len(abschnitte)} Abschnitte automatisch aus Ueberschriften "
                "abgeleitet. Besser ist es, sie im Meta-Block zu deklarieren.")
    bericht["abschnitte"] = len(abschnitte)

    alt = db().execute("SELECT fassung FROM seite WHERE slug=?", (slug,)).fetchone()
    if alt:
        bericht["neu"] = False
        bericht["fassung"] = alt["fassung"] + 1

    return bericht, html_neu, {"meta": meta, "abschnitte": abschnitte, "anhaenge": anhaenge}


def vorschau_ablegen(nutzer, html, anhaenge, slug):
    ordner = os.path.join(VORSCHAU_ORDNER, sichere_kennung(nutzer.kennung))
    shutil.rmtree(ordner, ignore_errors=True)
    os.makedirs(os.path.join(ordner, "anhaenge"), exist_ok=True)
    with open(os.path.join(ordner, "seite.html"), "w", encoding="utf-8") as f:
        f.write(html)
    for a in anhaenge:
        with open(os.path.join(ordner, "anhaenge", a["name"]), "wb") as f:
            f.write(a["daten"])
    with open(os.path.join(ordner, "slug.txt"), "w", encoding="utf-8") as f:
        f.write(slug)


def sichere_kennung(k):
    return re.sub(r"[^A-Za-z0-9._-]", "_", k)[:64] or "unbekannt"


def uebernehmen(html, teile, nutzer, kommentar=""):
    """Seite speichern, alte Fassung wegsichern, Index neu bauen."""
    meta = teile["meta"]
    slug = meta["slug"].strip()
    ordner = seitenordner(slug)
    os.makedirs(os.path.join(ordner, "anhaenge"), exist_ok=True)
    os.makedirs(os.path.join(ordner, "fassungen"), exist_ok=True)

    v = db()
    alt = v.execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
    nummer = 1
    if alt:
        nummer = alt["fassung"]
        quelle = os.path.join(ordner, "seite.html")
        if os.path.exists(quelle):
            ziel = os.path.join(ordner, "fassungen", f"{nummer:04d}-seite.html")
            shutil.copy2(quelle, ziel)
            v.execute("INSERT INTO fassung(seite_id,nummer,datum,nutzer_id,datei,"
                      "groesse_b,kommentar) VALUES(?,?,?,?,?,?,?)",
                      (alt["id"], nummer, jetzt(), alt["nutzer_id"],
                       f"{nummer:04d}-seite.html", os.path.getsize(ziel), kommentar))
        nummer = alt["fassung"] + 1

    with open(os.path.join(ordner, "seite.html"), "w", encoding="utf-8") as f:
        f.write(html)
    groesse = os.path.getsize(os.path.join(ordner, "seite.html"))

    # Anhaenge nur ersetzen, was neu kommt. Bestehende bleiben liegen.
    for a in teile["anhaenge"]:
        with open(os.path.join(ordner, "anhaenge", a["name"]), "wb") as f:
            f.write(a["daten"])

    fehler, warnungen = regeln_pruefen(html, meta)
    daten = (meta.get("titel", "").strip(), meta.get("kurz", "").strip(),
             json.dumps(meta.get("pfad", []), ensure_ascii=False),
             json.dumps(meta.get("gruppen", []), ensure_ascii=False),
             meta.get("stand", "") or heute(), nummer, groesse,
             0 if warnungen else 1,
             json.dumps(warnungen, ensure_ascii=False), nutzer.kennung, jetzt())

    if alt:
        v.execute("UPDATE seite SET titel=?,kurz=?,pfad_json=?,gruppen_json=?,stand=?,"
                  "fassung=?,groesse_b=?,regelkonform=?,hinweise_json=?,nutzer_id=?,"
                  "geaendert=? WHERE slug=?", daten + (slug,))
        seite_id = alt["id"]
    else:
        v.execute("INSERT INTO seite(titel,kurz,pfad_json,gruppen_json,stand,fassung,"
                  "groesse_b,regelkonform,hinweise_json,nutzer_id,geaendert,slug) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", daten + (slug,))
        seite_id = v.execute("SELECT id FROM seite WHERE slug=?", (slug,)).fetchone()["id"]

    v.execute("DELETE FROM abschnitt WHERE seite_id=?", (seite_id,))
    for i, a in enumerate(teile["abschnitte"]):
        v.execute("INSERT INTO abschnitt(seite_id,anker,titel,ebene,stichworte,text,"
                  "reihenfolge) VALUES(?,?,?,?,?,?,?)",
                  (seite_id, a.get("anker", ""), a.get("titel", ""), a.get("ebene", 1),
                   " ".join(a.get("stichworte", []) or []), a.get("text", "") or "", i))

    v.execute("DELETE FROM anhang WHERE seite_id=?", (seite_id,))
    for a in teile["anhaenge"]:
        v.execute("INSERT INTO anhang(seite_id,name,typ,groesse_b,marke) VALUES(?,?,?,?,?)",
                  (seite_id, a["name"], a["typ"], len(a["daten"]), a["marke"]))
    v.commit()

    index_neu_bauen(seite_id, html)
    return seite_id, nummer


def index_neu_bauen(seite_id, html=None):
    """Suchindex einer Seite verwerfen und frisch aufbauen."""
    v = db()
    seite = v.execute("SELECT * FROM seite WHERE id=?", (seite_id,)).fetchone()
    if not seite:
        return
    alte = [r["id"] for r in v.execute("SELECT id FROM treffer WHERE seite_id=?",
                                       (seite_id,)).fetchall()]
    for tid in alte:
        v.execute("DELETE FROM suche WHERE rowid=?", (tid,))
        try:
            v.execute("DELETE FROM suche_tri WHERE rowid=?", (tid,))
        except sqlite3.OperationalError:
            pass
    v.execute("DELETE FROM treffer WHERE seite_id=?", (seite_id,))

    def eintragen(art, anker, anhang_name, seitennr, titel, stichworte, text):
        if not (text or "").strip() and not (stichworte or "").strip():
            return
        cur = v.execute("INSERT INTO treffer(seite_id,art,anker,anhang_name,seitennr,"
                        "abschnittstitel) VALUES(?,?,?,?,?,?)",
                        (seite_id, art, anker, anhang_name, seitennr, titel))
        tid = cur.lastrowid
        v.execute("INSERT INTO suche(rowid,titel,stichworte,text) VALUES(?,?,?,?)",
                  (tid, titel, stichworte, text))
        try:
            v.execute("INSERT INTO suche_tri(rowid,inhalt) VALUES(?,?)",
                      (tid, f"{titel} {stichworte} {text}"))
        except sqlite3.OperationalError:
            pass

    for a in v.execute("SELECT * FROM abschnitt WHERE seite_id=? ORDER BY reihenfolge",
                       (seite_id,)).fetchall():
        eintragen("abschnitt", a["anker"], "", 0, a["titel"], a["stichworte"], a["text"])

    # Sichtbarer Seitentext als zusaetzliches Netz.
    if html is None:
        p = os.path.join(seitenordner(seite["slug"]), "seite.html")
        html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    roh = text_aus_html(html)
    if roh:
        for i in range(0, min(len(roh), 200000), 4000):
            eintragen("seite", "", "", 0, seite["titel"], "", roh[i:i + 4000])

    ordner = seitenordner(seite["slug"])
    for an in v.execute("SELECT * FROM anhang WHERE seite_id=?", (seite_id,)).fetchall():
        if an["typ"] != "application/pdf":
            continue
        pfad = os.path.join(ordner, "anhaenge", an["name"])
        if not os.path.exists(pfad):
            continue
        for nr, txt in enumerate(pdf_seitentext(pfad), 1):
            if len(txt) < 40:
                continue
            eintragen("anhang", "", an["name"], nr, f"{an['name']} Seite {nr}", "", txt)
    v.commit()


# ---------------------------------------------------------------- Suche

def fts_ausdruck(begriff, praefix=True):
    worte = re.findall(r"[\wÄÖÜäöüß]{2,}", begriff, re.UNICODE)
    if not worte:
        return None
    teile = [f'"{w}"*' if praefix else f'"{w}"' for w in worte]
    return " AND ".join(teile)


def schnipsel(text, begriffe, laenge=170):
    """Textausschnitt um den ersten Treffer, mit Markierung."""
    if not text:
        return ""
    flach = entwerten(text)
    pos = -1
    for b in begriffe:
        p = flach.find(entwerten(b))
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        pos = 0
    start = max(0, pos - laenge // 3)
    ende = min(len(text), start + laenge)
    aus = text[start:ende]
    if start > 0:
        aus = "…" + aus
    if ende < len(text):
        aus = aus + "…"
    return aus


def entwerten(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def abstand(a, b, grenze=2):
    """Levenshtein mit Abbruch. Nur fuer kurze Woerter gedacht."""
    if abs(len(a) - len(b)) > grenze:
        return grenze + 1
    vorher = list(range(len(b) + 1))
    for i, za in enumerate(a, 1):
        jetzt_ = [i]
        for j, zb in enumerate(b, 1):
            jetzt_.append(min(vorher[j] + 1, jetzt_[j - 1] + 1,
                              vorher[j - 1] + (za != zb)))
        if min(jetzt_) > grenze:
            return grenze + 1
        vorher = jetzt_
    return vorher[-1]


def wortvorschlag(begriff):
    """
    Naechstliegendes Wort aus dem Index. Faengt Buchstabendreher, die
    weder Praefix- noch Teilwortsuche finden koennen.
    """
    worte = re.findall(r"[\wÄÖÜäöüß]{4,}", begriff, re.UNICODE)
    if not worte:
        return None
    v = db()
    ersetzt, geaendert = [], False
    for w in re.findall(r"[\wÄÖÜäöüß]+", begriff, re.UNICODE):
        flach = entwerten(w)
        if len(flach) < 4:
            ersetzt.append(w)
            continue
        try:
            da = v.execute("SELECT 1 FROM vokabular WHERE term=? LIMIT 1", (flach,)).fetchone()
            if da:
                ersetzt.append(w)
                continue
            kandidaten = v.execute(
                "SELECT term, cnt FROM vokabular WHERE term LIKE ? "
                "AND length(term) BETWEEN ? AND ? ORDER BY cnt DESC LIMIT 400",
                (flach[0] + "%", len(flach) - 2, len(flach) + 2)).fetchall()
        except sqlite3.OperationalError:
            return None
        grenze = 1 if len(flach) < 6 else 2
        bestes, bester = None, grenze + 1
        for k in kandidaten:
            d = abstand(flach, k["term"], grenze)
            if d < bester:
                bestes, bester = k["term"], d
                if d == 1:
                    break
        if bestes:
            ersetzt.append(bestes)
            geaendert = True
        else:
            ersetzt.append(w)
    return " ".join(ersetzt) if geaendert else None


def suchen(nutzer, begriff, grenze=40, mit_anhaengen=True):
    begriff = (begriff or "").strip()
    if len(begriff) < 2:
        return []
    erlaubt = {z["id"]: z for z in sichtbare_seiten(nutzer)}
    if not erlaubt:
        return []
    v = db()
    platz = ",".join("?" * len(erlaubt))
    ids = list(erlaubt.keys())
    gefunden = {}

    def aufnehmen(tid, punkte, quelle):
        vorher = gefunden.get(tid)
        if vorher is None or punkte > vorher[0]:
            gefunden[tid] = (punkte, quelle)

    aus = fts_ausdruck(begriff, praefix=True)
    if aus:
        for modus in ("und", "oder"):
            frage = aus if modus == "und" else aus.replace(" AND ", " OR ")
            try:
                zeilen = v.execute(
                    f"SELECT t.id AS tid, bm25(suche, 12.0, 8.0, 1.0) AS rang "
                    f"FROM suche JOIN treffer t ON t.id = suche.rowid "
                    f"WHERE suche MATCH ? AND t.seite_id IN ({platz}) "
                    f"ORDER BY rang LIMIT ?", [frage] + ids + [grenze * 3]).fetchall()
            except sqlite3.OperationalError:
                zeilen = []
            for z in zeilen:
                aufnehmen(z["tid"], (-z["rang"]) + (6 if modus == "und" else 0), "wort")
            if modus == "und" and len(gefunden) >= grenze:
                break

    # Teilwortsuche als zweites Netz: greift bei Komposita und Tippfehlern.
    if len(gefunden) < grenze:
        kern = max(re.findall(r"[\wÄÖÜäöüß]{3,}", begriff, re.UNICODE) or [""], key=len)
        if len(kern) >= 3:
            try:
                zeilen = v.execute(
                    f"SELECT t.id AS tid, bm25(suche_tri) AS rang "
                    f"FROM suche_tri JOIN treffer t ON t.id = suche_tri.rowid "
                    f"WHERE suche_tri MATCH ? AND t.seite_id IN ({platz}) "
                    f"ORDER BY rang LIMIT ?",
                    [f'"{kern}"'] + ids + [grenze * 2]).fetchall()
            except sqlite3.OperationalError:
                zeilen = []
            for z in zeilen:
                aufnehmen(z["tid"], (-z["rang"]) * 0.35, "teil")

    if not gefunden:
        return []

    tids = list(gefunden.keys())
    platz2 = ",".join("?" * len(tids))
    zeilen = v.execute(
        f"SELECT t.*, s.titel AS s_titel, s.stichworte AS s_stich, s.text AS s_text "
        f"FROM treffer t JOIN suche s ON s.rowid = t.id WHERE t.id IN ({platz2})",
        tids).fetchall()

    worte = re.findall(r"[\wÄÖÜäöüß]{2,}", begriff, re.UNICODE)
    ergebnis = []
    for z in zeilen:
        if z["art"] == "anhang" and not mit_anhaengen:
            continue
        seite = erlaubt[z["seite_id"]]
        punkte, quelle = gefunden[z["id"]]
        titel = z["abschnittstitel"] or seite["titel"]
        if entwerten(begriff) in entwerten(titel):
            punkte += 25
        ergebnis.append({
            "slug": seite["slug"], "seitentitel": seite["titel"],
            "pfad": json.loads(seite["pfad_json"] or "[]"),
            "art": z["art"], "anker": z["anker"], "anhang": z["anhang_name"],
            "seitennr": z["seitennr"], "titel": titel,
            "schnipsel": schnipsel(z["s_text"] or z["s_stich"] or "", worte),
            "punkte": round(punkte, 3), "quelle": quelle,
        })

    ergebnis.sort(key=lambda e: -e["punkte"])
    # Pro Seite hoechstens vier Treffer, damit eine grosse Seite die Liste
    # nicht auffrisst.
    proseite, gefiltert = {}, []
    for e in ergebnis:
        n = proseite.get(e["slug"], 0)
        if n >= 4:
            continue
        proseite[e["slug"]] = n + 1
        gefiltert.append(e)
        if len(gefiltert) >= grenze:
            break
    return gefiltert


# ---------------------------------------------------------------- Baum

def baum_bauen(nutzer):
    wurzel = {"name": "", "kinder": {}, "seiten": []}
    for z in sichtbare_seiten(nutzer):
        pfad = json.loads(z["pfad_json"] or "[]") or ["Ohne Thema"]
        knoten = wurzel
        for teil in pfad:
            knoten = knoten["kinder"].setdefault(teil, {"name": teil, "kinder": {}, "seiten": []})
        knoten["seiten"].append({
            "slug": z["slug"], "titel": z["titel"], "kurz": z["kurz"],
            "stand": z["stand"], "geschuetzt": bool(json.loads(z["gruppen_json"] or "[]")),
        })

    def falten(k):
        return {"name": k["name"],
                "kinder": [falten(x) for x in sorted(k["kinder"].values(), key=lambda y: y["name"])],
                "seiten": sorted(k["seiten"], key=lambda s: s["titel"])}

    return falten(wurzel)["kinder"]


# ---------------------------------------------------------------- HTTP

class Antwort(Exception):
    def __init__(self, code, text):
        self.code = code
        self.text = text


def pfadteile(pfad):
    return [unquote(p) for p in pfad.strip("/").split("/") if p]


class Handler(BaseHTTPRequestHandler):
    server_version = "ProloWiki"
    protocol_version = "HTTP/1.1"
    # Ohne Zeitgrenze wartet ein Thread endlos auf Daten, die nach einem
    # abgebrochenen Upload nie mehr kommen.
    timeout = 60

    def log_message(self, format, *args):
        # Keine Kopfzeilen ins Protokoll, siehe Betriebsregeln Abschnitt 12.
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))

    # -------------------------------------------------- Hilfen

    def senden(self, code, koerper, typ="application/json; charset=utf-8", extra=None):
        if isinstance(koerper, str):
            koerper = koerper.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def json_senden(self, obj, code=200):
        self.senden(code, json.dumps(obj, ensure_ascii=False))

    def fehler(self, code, text):
        self.json_senden({"fehler": text}, code)

    def koerper_lesen(self):
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > MAX_UPLOAD_B:
            raise Antwort(413, f"Die Datei ist groesser als "
                               f"{MAX_UPLOAD_B // (1024 * 1024)} MB.")
        rest, teile = laenge, []
        while rest > 0:
            try:
                block = self.rfile.read(min(rest, 1 << 20))
            except (TimeoutError, OSError):
                block = b""
            if not block:
                self.close_connection = True
                raise Antwort(400, "Die Datei kam nur unvollstaendig an. "
                                   "Bitte noch einmal hochladen.")
            teile.append(block)
            rest -= len(block)
        return b"".join(teile)

    def nutzer(self):
        n = nutzer_aus_kopf(self.headers)
        if n is None:
            raise Antwort(401, "Nicht angemeldet. Diese Anwendung wird ueber "
                               "Authentik aufgerufen.")
        return n

    def admin(self):
        n = self.nutzer()
        if not n.ist_admin:
            raise Antwort(403, f"Dafuer braucht es die Gruppe '{ADMIN_GRUPPE}'.")
        return n

    # -------------------------------------------------- Verteilung

    def fremde_herkunft(self):
        """True, wenn die Anfrage nicht von dieser Seite selbst stammt (B-03).

        Das Wiki hatte bisher gar keine Herkunftspruefung: kein
        Sec-Fetch-Site, kein Origin, kein Referer. Damit standen die
        schreibenden Endpunkte jeder fremden Webseite offen, solange das
        Opfer eine gueltige Authentik-Sitzung hatte.

        "same-site" wird bewusst NICHT akzeptiert: alle Tools liegen unter
        prolo.me, und eine Nachbar-Subdomain ist fuer das Wiki genauso fremd
        wie eine beliebige Seite im Netz.
        """
        ziel = self.headers.get("Sec-Fetch-Site")
        if ziel is not None:
            return ziel != "same-origin"        # alles andere ist fremd
        # Aeltere Browser ohne Sec-Fetch-Site: ueber Origin/Referer entscheiden.
        herkunft = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not herkunft:
            return True                         # kein Nachweis = abweisen
        return urlparse(herkunft).netloc != (self.headers.get("Host") or "")

    # Welcher Content-Type je Endpunkt zulaessig ist (B-03).
    #
    # Der Sinn der Pruefung ist, CORS-"simple requests" auszuschliessen: nur
    # text/plain, application/x-www-form-urlencoded und multipart/form-data
    # darf ein gewoehnliches HTML-Formular ohne Preflight quer ueber Origins
    # senden. Alles andere erzwingt einen Preflight, und der scheitert, weil
    # das Wiki keine CORS-Kopfzeilen sendet.
    #
    # Darum wird hier nicht ueberall application/json verlangt: /api/pruefen
    # und /api/import nehmen die Seite als Datei entgegen und schicken
    # text/html. Das ist ebenfalls kein simple type und damit genauso dicht -
    # eine Pflicht auf application/json haette diese beiden Wege nur
    # zerstoert. Endpunkte, die hier nicht stehen, muessen JSON schicken.
    POST_TYPEN = {
        "pruefen": ("text/html",),
        "import": ("text/html",),
    }

    def typ_pruefen(self, rest):
        """Content-Type gegen POST_TYPEN pruefen. Wirft 415, wenn er nicht passt."""
        erlaubt = self.POST_TYPEN.get(rest[0] if rest else "", ("application/json",))
        typ = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if typ not in erlaubt:
            raise Antwort(415, "Diese Schnittstelle nimmt nur %s entgegen. "
                               "Bitte den Kopf Content-Type entsprechend setzen."
                               % " oder ".join(erlaubt))

    def do_GET(self):
        schiefgegangen = False
        try:
            self.verteilen_get()
        except Antwort as a:
            self.fehler(a.code, a.text)
        except BrokenPipeError:
            pass
        except Exception as e:
            schiefgegangen = True
            self.close_connection = True
            kennung = f"{int(time.time()) % 100000:05d}"
            sys.stderr.write(f"FEHLER GET {self.path} [{kennung}]: "
                             f"{type(e).__name__}: {e}\n")
            traceback.print_exc(file=sys.stderr)
            # Kein interner Pfad, kein Datenbankfehler im Original
            # (Betriebsregeln 12) - die Kennung fuehrt zur Protokollzeile.
            self.fehler(500, f"Auf dem Server ist etwas schiefgegangen "
                             f"({type(e).__name__}, Kennung {kennung}). Die "
                             f"Einzelheiten stehen im Protokoll des Containers.")
        finally:
            db_freigeben(schiefgegangen)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        schiefgegangen = False
        try:
            self.verteilen_post()
        except Antwort as a:
            self.fehler(a.code, a.text)
        except BrokenPipeError:
            pass
        except Exception as e:
            schiefgegangen = True
            self.close_connection = True
            kennung = f"{int(time.time()) % 100000:05d}"
            sys.stderr.write(f"FEHLER POST {self.path} [{kennung}]: "
                             f"{type(e).__name__}: {e}\n")
            traceback.print_exc(file=sys.stderr)
            # Kein interner Pfad, kein Datenbankfehler im Original
            # (Betriebsregeln 12) - die Kennung fuehrt zur Protokollzeile.
            self.fehler(500, f"Auf dem Server ist etwas schiefgegangen "
                             f"({type(e).__name__}, Kennung {kennung}). Die "
                             f"Einzelheiten stehen im Protokoll des Containers.")
        finally:
            db_freigeben(schiefgegangen)

    def verteilen_get(self):
        u = urlparse(self.path)
        teile = pfadteile(u.path)
        frage = parse_qs(u.query)

        # Ohne Anmeldung erreichbar: nur die Lebendpruefung fuer
        # aktualisieren.sh, die intern am Traefik vorbei aufgerufen wird.
        # Fassung abfragen - ohne Anmeldung, wie die Lebendpruefung, damit
        # aktualisieren.sh und die Gesundheitspruefung herankommen (B-23).
        if teile == ["api", "version"]:
            return self.json_senden({"version": VERSION})

        if teile == ["gesundheit"]:
            return self.senden(200, "ok\n", "text/plain; charset=utf-8")

        if not teile:
            return self.datei_senden(os.path.join(EIGENER_ORDNER, "index.html"),
                                     "text/html; charset=utf-8", huelle=True)

        if teile[0] == "api":
            return self.api_get(teile[1:], frage)

        if teile[0] == "seite" and len(teile) >= 2:
            return self.seite_senden(teile[1:])

        if teile[0] == "vorschau":
            return self.vorschau_senden(teile[1:])

        if teile[0] == "schriften" and len(teile) == 2:
            if not DATEINAME_MUSTER.match(teile[1]):
                raise Antwort(400, "Ungueltiger Dateiname.")
            self.nutzer()
            p = os.path.join(EIGENER_ORDNER, "schriften", teile[1])
            if not os.path.exists(p):
                raise Antwort(404, "Schriftdatei nicht hinterlegt.")
            return self.datei_senden(p, "font/woff2", zwischenspeicher=True)

        raise Antwort(404, "Diese Adresse gibt es nicht.")

    def api_get(self, teile, frage):
        n = self.nutzer()
        if teile == ["ich"]:
            return self.json_senden({
                "kennung": n.kennung, "name": n.name, "email": n.email,
                "gruppen": sorted(n.gruppen), "ist_admin": n.ist_admin,
                "gruppen_roh": n.gruppen_roh,
                "admin_gruppe": ADMIN_GRUPPE,
                "einstellungen": einstellungen_lesen(n.kennung),
                "abmelden": "/outpost.goauthentik.io/sign_out"})

        if teile == ["baum"]:
            v = db()
            zuletzt = [dict(r) for r in v.execute(
                "SELECT z.slug, s.titel, z.gesehen FROM zuletzt z "
                "JOIN seite s ON s.slug=z.slug WHERE z.nutzer_id=? "
                "ORDER BY z.gesehen DESC LIMIT 8", (n.kennung,)).fetchall()]
            marken = [dict(r) for r in v.execute(
                "SELECT slug, anker, titel FROM lesezeichen WHERE nutzer_id=? "
                "ORDER BY angelegt DESC LIMIT 40", (n.kennung,)).fetchall()]
            return self.json_senden({"baum": baum_bauen(n), "zuletzt": zuletzt,
                                     "lesezeichen": marken,
                                     "anzahl": len(sichtbare_seiten(n))})

        if teile == ["suche"]:
            q = (frage.get("q") or [""])[0]
            t0 = time.time()
            mit_a = einstellungen_lesen(n.kennung)["pdf_treffer"] == "1"
            treffer = suchen(n, q, mit_anhaengen=mit_a)
            statt = None
            if not treffer:
                statt = wortvorschlag(q)
                if statt:
                    treffer = suchen(n, statt, mit_anhaengen=mit_a)
                    if not treffer:
                        statt = None
            return self.json_senden({"q": q, "statt": statt, "treffer": treffer,
                                     "dauer_ms": round((time.time() - t0) * 1000, 1)})

        if len(teile) == 2 and teile[0] == "seite":
            slug = teile[1]
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            if not darf_sehen(n, z):
                raise Antwort(403, "Fuer diese Seite fehlt dir die Freigabe.")
            db().execute("INSERT INTO zuletzt(nutzer_id,slug,gesehen) VALUES(?,?,?) "
                         "ON CONFLICT(nutzer_id,slug) DO UPDATE SET gesehen=excluded.gesehen",
                         (n.kennung, slug, jetzt()))
            db().commit()
            absch = [dict(r) for r in db().execute(
                "SELECT anker,titel,ebene FROM abschnitt WHERE seite_id=? "
                "ORDER BY reihenfolge", (z["id"],)).fetchall()]
            anh = [dict(r) for r in db().execute(
                "SELECT name,typ,groesse_b,marke FROM anhang WHERE seite_id=?",
                (z["id"],)).fetchall()]
            d = dict(z)
            d["pfad"] = json.loads(d.pop("pfad_json") or "[]")
            d["gruppen"] = json.loads(d.pop("gruppen_json") or "[]")
            d["hinweise"] = json.loads(d.pop("hinweise_json") or "[]")
            d["abschnitte"] = absch
            d["anhaenge"] = anh
            return self.json_senden(d)

        if len(teile) == 2 and teile[0] == "fassungen":
            self.admin()
            z = db().execute("SELECT * FROM seite WHERE slug=?", (teile[1],)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            f = [dict(r) for r in db().execute(
                "SELECT nummer,datum,nutzer_id,groesse_b,kommentar FROM fassung "
                "WHERE seite_id=? ORDER BY nummer DESC", (z["id"],)).fetchall()]
            return self.json_senden({"slug": z["slug"], "aktuell": z["fassung"],
                                     "fassungen": f})

        if teile == ["verwaltung"]:
            self.admin()
            zeilen = [dict(r) for r in db().execute(
                "SELECT slug,titel,pfad_json,gruppen_json,stand,fassung,groesse_b,"
                "regelkonform,hinweise_json,nutzer_id,geaendert FROM seite "
                "ORDER BY geaendert DESC").fetchall()]
            for z in zeilen:
                z["pfad"] = json.loads(z.pop("pfad_json") or "[]")
                z["gruppen"] = json.loads(z.pop("gruppen_json") or "[]")
                z["hinweise"] = json.loads(z.pop("hinweise_json") or "[]")
            pfade = sorted({" / ".join(json.loads(z["pfad_json"] or "[]"))
                            for z in db().execute("SELECT pfad_json FROM seite").fetchall()
                            if z["pfad_json"]})
            zweige = [dict(r) for r in db().execute("SELECT * FROM zweig").fetchall()]
            for z in zweige:
                z["gruppen"] = json.loads(z.pop("gruppen_json") or "[]")
            return self.json_senden({"seiten": zeilen, "zweige": zweige, "pfade": pfade})

        raise Antwort(404, "Unbekannter Aufruf.")

    def seite_senden(self, teile):
        n = self.nutzer()
        slug = teile[0]
        if not SLUG_MUSTER.match(slug):
            raise Antwort(400, "Ungueltige Seitenkennung.")
        z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
        if not z:
            raise Antwort(404, "Diese Seite gibt es nicht.")
        if not darf_sehen(n, z):
            raise Antwort(403, "Fuer diese Seite fehlt dir die Freigabe.")
        ordner = seitenordner(slug)
        if len(teile) >= 3 and teile[1] == "anhaenge":
            name = teile[2]
            if not DATEINAME_MUSTER.match(name):
                raise Antwort(400, "Ungueltiger Dateiname.")
            p = os.path.join(ordner, "anhaenge", name)
            if not os.path.exists(p):
                raise Antwort(404, "Anhang nicht gefunden.")
            an = db().execute("SELECT typ FROM anhang WHERE seite_id=? AND name=?",
                              (z["id"], name)).fetchone()
            return self.datei_senden(p, (an["typ"] if an else "application/octet-stream"))
        # Eingespielter Inhalt, kein eigener Code: fremd=True (B-03 Teil 4).
        return self.datei_senden(os.path.join(ordner, "seite.html"),
                                 "text/html; charset=utf-8", fremd=True)

    def vorschau_senden(self, teile):
        n = self.nutzer()
        ordner = os.path.join(VORSCHAU_ORDNER, sichere_kennung(n.kennung))
        if len(teile) >= 2 and teile[0] == "anhaenge":
            if not DATEINAME_MUSTER.match(teile[1]):
                raise Antwort(400, "Ungueltiger Dateiname.")
            p = os.path.join(ordner, "anhaenge", teile[1])
        else:
            p = os.path.join(ordner, "seite.html")
        if not os.path.exists(p):
            raise Antwort(404, "Keine Vorschau vorhanden.")
        typ = "text/html; charset=utf-8" if p.endswith(".html") else "application/octet-stream"
        # Die Vorschau zeigt genau den Inhalt, der eingespielt werden soll -
        # also ebenfalls fremder Code (B-03 Teil 4).
        return self.datei_senden(p, typ, fremd=p.endswith(".html"))

    def datei_senden(self, pfad, typ, huelle=False, zwischenspeicher=False,
                     fremd=False):
        """Eine Datei ausliefern.

        huelle=True  - die Anwendungshuelle (eigenes index.html). Vertrauter
                       Code, darf die Wiki-API im eigenen Origin benutzen.
        fremd=True   - eingespielter Seiteninhalt. Das ist Code aus fremder
                       Quelle und bekommt darum eine ganz andere CSP (B-03
                       Teil 4, B-07). Bisher bekamen beide dieselbe - das war
                       die Ursache des Problems.
        """
        if not os.path.exists(pfad):
            raise Antwort(404, "Datei nicht gefunden.")
        with open(pfad, "rb") as f:
            daten = f.read()
        extra = {}
        if fremd:
            # Eine eingespielte Seite ist ausfuehrbarer Code aus fremder
            # Quelle. Ohne Isolierung koennte sie die gesamte Wiki-API im
            # Namen des Betrachters aufrufen (einschliesslich /api/import und
            # Loeschvorgaengen, sobald ein Admin sie ansieht) und ueber
            # parent.document die Huelle manipulieren.
            #
            # "sandbox" OHNE allow-same-origin setzt den Origin des Dokuments
            # auf "opaque": document.cookie, localStorage und parent.document
            # sind damit unerreichbar, und jeder fetch() auf /api/... ist eine
            # Anfrage ueber Origin-Grenzen, die ohne CORS-Kopfzeilen scheitert.
            #
            # allow-scripts bleibt drin, weil jede Wiki-Seite einen
            # Pflichtteil hat, der auf die Huelle hoert (Ankersprung,
            # Suchbegriff hervorheben, Thema uebernehmen). Wichtig: zusammen
            # mit allow-same-origin waere die Sandbox aufgehoben - genau diese
            # Kombination stand bisher im sandbox-Attribut des iframes und ist
            # dort ebenfalls entfernt worden.
            extra["Content-Security-Policy"] = (
                "sandbox allow-scripts allow-popups allow-downloads; "
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "font-src 'self'; object-src 'none'; frame-src 'none'; "
                "connect-src 'none'; frame-ancestors 'self'; base-uri 'none'; "
                "form-action 'none'")
        elif huelle:
            # Inline-Stil und Inline-Skript sind noetig, weil die Seiten
            # eigenstaendig sind. Externe Quellen bleiben gesperrt.
            extra["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "font-src 'self'; object-src 'self' blob:; frame-src 'self' blob:; "
                "connect-src 'self'; frame-ancestors 'self'; base-uri 'none'")
        if zwischenspeicher:
            extra["Cache-Control"] = "public, max-age=604800"
        else:
            extra["Cache-Control"] = "no-store"
        return self.senden(200, daten, typ, extra)

    # -------------------------------------------------- Schreibende Aufrufe

    def verteilen_post(self):
        u = urlparse(self.path)
        teile = pfadteile(u.path)
        frage = parse_qs(u.query)
        if teile[:1] != ["api"]:
            raise Antwort(404, "Unbekannter Aufruf.")
        rest = teile[1:]
        # Herkunft und Content-Type vor allem anderen (B-03). Ausnahme: keine -
        # auch /api/einstellungen braucht beides.
        if self.fremde_herkunft():
            raise Antwort(403, "Anfrage von fremder Seite abgelehnt.")
        self.typ_pruefen(rest)

        if rest == ["pruefen"] or rest == ["import"]:
            n = self.admin()
            roh = self.koerper_lesen()
            if not roh:
                raise Antwort(400, "Es wurde keine Datei uebertragen.")
            bericht, html, teile_d = pruefen(roh, n)
            if rest == ["pruefen"]:
                if html is not None:
                    vorschau_ablegen(n, html, teile_d["anhaenge"],
                                     teile_d["meta"].get("slug", ""))
                    bericht["vorschau"] = "/vorschau/"
                return self.json_senden(bericht)
            if bericht["fehler"]:
                return self.json_senden(
                    {"ok": False, "bericht": bericht,
                     "fehler": "Die Datei hat Fehler und wurde nicht uebernommen."}, 400)
            kommentar = (frage.get("kommentar") or [""])[0][:200]
            geaendert = ueberschreiben(teile_d["meta"], frage)
            if geaendert:
                html = meta_block_ersetzen(html, teile_d["meta"])
            seite_id, nummer = uebernehmen(html, teile_d, n, kommentar)
            return self.json_senden({"ok": True, "slug": teile_d["meta"]["slug"],
                                     "fassung": nummer, "geaendert": geaendert,
                                     "bericht": bericht})

        if rest == ["loeschen"]:
            n = self.admin()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug = (daten.get("slug") or "").strip()
            if daten.get("bestaetigt") is not True:
                raise Antwort(400, "Ohne Bestaetigung wird nichts geloescht.")
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            db().execute("DELETE FROM seite WHERE id=?", (z["id"],))
            db().commit()
            # Dateien bleiben liegen - Datenverlust ist die einzige echte
            # Katastrophe. Aufgeraeumt wird von Hand.
            shutil.move(seitenordner(slug),
                        os.path.join(SEITEN, f".geloescht-{slug}-{int(time.time())}"))
            return self.json_senden({"ok": True})

        if rest == ["zuruecksetzen"]:
            n = self.admin()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug, nummer = (daten.get("slug") or "").strip(), int(daten.get("nummer") or 0)
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            p = os.path.join(seitenordner(slug), "fassungen", f"{nummer:04d}-seite.html")
            if not os.path.exists(p):
                raise Antwort(404, "Diese Fassung liegt nicht vor.")
            roh = open(p, "rb").read()
            bericht, html, teile_d = pruefen(roh, n)
            if bericht["fehler"]:
                raise Antwort(400, "Die alte Fassung ist nicht mehr gueltig: "
                                   + "; ".join(bericht["fehler"][:2]))
            _, neu = uebernehmen(html, teile_d, n, f"zurueck auf Fassung {nummer}")
            return self.json_senden({"ok": True, "fassung": neu})

        if rest == ["zweig"]:
            self.admin()
            daten = json.loads(self.koerper_lesen() or b"{}")
            pfad = (daten.get("pfad") or "").strip("/")
            gruppen = daten.get("gruppen") or []
            if not pfad:
                raise Antwort(400, "Es fehlt der Pfad des Themenzweigs.")
            if gruppen:
                db().execute("INSERT INTO zweig(pfad,gruppen_json) VALUES(?,?) "
                             "ON CONFLICT(pfad) DO UPDATE SET gruppen_json=excluded.gruppen_json",
                             (pfad, json.dumps(gruppen, ensure_ascii=False)))
            else:
                db().execute("DELETE FROM zweig WHERE pfad=?", (pfad,))
            db().commit()
            return self.json_senden({"ok": True})

        if rest == ["einstellungen"]:
            n = self.nutzer()
            daten = json.loads(self.koerper_lesen() or b"{}")
            for schluessel, wert in daten.items():
                einstellung_setzen(n.kennung, schluessel, wert)
            db().commit()
            return self.json_senden({"ok": True,
                                     "einstellungen": einstellungen_lesen(n.kennung)})

        if rest == ["lesezeichen"]:
            n = self.nutzer()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug = (daten.get("slug") or "").strip()
            anker = (daten.get("anker") or "").strip()
            if daten.get("entfernen"):
                db().execute("DELETE FROM lesezeichen WHERE nutzer_id=? AND slug=? AND anker=?",
                             (n.kennung, slug, anker))
            else:
                db().execute("INSERT OR REPLACE INTO lesezeichen(nutzer_id,slug,anker,"
                             "titel,angelegt) VALUES(?,?,?,?,?)",
                             (n.kennung, slug, anker, (daten.get("titel") or "")[:120], jetzt()))
            db().commit()
            return self.json_senden({"ok": True})

        if rest == ["neuindex"]:
            self.admin()
            for z in db().execute("SELECT id FROM seite").fetchall():
                index_neu_bauen(z["id"])
            return self.json_senden({"ok": True})

        raise Antwort(404, "Unbekannter Aufruf.")


def main():
    # --version gibt nur die Fassung aus und aendert nichts (wie im Bordbuch,
    # B-13): der Aufruf kommt von Skripten und darf keine Nebenwirkung haben.
    if "--version" in sys.argv:
        print(VERSION)
        return
    datenbank_anlegen()
    os.makedirs(VORSCHAU_ORDNER, exist_ok=True)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write(f"Prolo Wiki laeuft auf Port {PORT}. "
                     f"Daten: {DATEN}, Seiten: {SEITEN}\n")
    srv.serve_forever()


if __name__ == "__main__":
    main()
