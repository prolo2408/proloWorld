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
import hashlib
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
VERSION = "1.3.3"

DATEN = os.environ.get("WIKI_DATEN", "/daten")
SEITEN = os.environ.get("WIKI_SEITEN", "/seiten")
PORT = int(os.environ.get("WIKI_PORT", "8080"))
ADMIN_GRUPPE = os.environ.get("WIKI_ADMIN_GRUPPE", "wiki-admin")
# Wer schreiben darf: Seiten anlegen und die eigenen aendern. Lesen darf jeder
# Angemeldete (im Rahmen der Freigaben), verwalten nur ADMIN_GRUPPE.
EDITOR_GRUPPE = os.environ.get("WIKI_EDITOR_GRUPPE", "wiki-editor")
# Das Wiki sieht nur Gruppen an, die so anfangen. In Authentik haengen an einem
# Nutzer die Gruppen aller Tools; "vertrieb" oder "bordbuch-admin" haben hier
# nichts zu entscheiden, und eine Freigabe auf so eine Gruppe waere ein stiller
# Fehler - sie wuerde niemandem etwas geben.
GRUPPEN_PRAEFIX = os.environ.get("WIKI_GRUPPEN_PRAEFIX", "wiki")
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
  -- nutzer_id ist, wer ZULETZT gespeichert hat; urheber, wer die Seite
  -- ANGELEGT hat. Der Unterschied entscheidet ueber das Schreibrecht (N-15).
  nutzer_id     TEXT NOT NULL DEFAULT '',
  urheber       TEXT NOT NULL DEFAULT '',
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
  -- Ueberschrift im Inhaltsverzeichnis: mehrere Abschnitte teilen eine
  -- Gruppe ("Grundlagen", "Adressierung"). Leer heisst: keine Gruppe.
  gruppe       TEXT NOT NULL DEFAULT '',
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

-- Was eine Seite im Browser wirklich anzeigt (N-11). Der Server kann kein
-- JavaScript; eine Seite, die ihre Inhalte erst dort aufbaut, meldet ihren
-- sichtbaren Text selbst, und der wird hier aufbewahrt, damit der Index nach
-- einem Neuaufbau nicht darauf warten muss, dass jemand die Seite oeffnet.
CREATE TABLE IF NOT EXISTS ansichtstext(
  seite_id  INTEGER PRIMARY KEY REFERENCES seite(id) ON DELETE CASCADE,
  text      TEXT NOT NULL DEFAULT '',
  stand     TEXT NOT NULL DEFAULT ''
);
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
    # Der Zweig-Zwischenspeicher gehoert zur Anfrage und geht mit ihr (B-47).
    _lokal.zweige = None


def datenbank_anlegen():
    os.makedirs(DATEN, exist_ok=True)
    os.makedirs(SEITEN, exist_ok=True)
    v = db()
    v.executescript(SCHEMA)
    if spalte_nachtragen(v, "abschnitt", "gruppe", "TEXT NOT NULL DEFAULT ''"):
        sys.stderr.write(
            "HINWEIS: Die Tabelle abschnitt hat die Spalte gruppe bekommen. "
            "Sie fuellt sich beim naechsten Speichern einer Seite; bis dahin "
            "steht das Inhaltsverzeichnis ohne Ueberschriften da.\n")
    if spalte_urheber_nachtragen(v):
        sys.stderr.write(
            "HINWEIS: Die Tabelle seite hat die Spalte urheber bekommen "
            "(N-15) und wurde aus der Fassungsgeschichte gefuellt. Es wurde "
            "nichts ueberschrieben; wer sichergehen will, legt vorher eine "
            "Kopie von wiki.db an.\n")
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
    # Reste aus geloeschten Seiten wegraeumen (N-16). Ohne das scheitert in
    # einer Datenbank, in der schon einmal eine Seite geloescht wurde, JEDER
    # weitere Indexaufbau - auch "Index neu".
    weg = verwaiste_indexzeilen_loeschen(v)
    if weg:
        sys.stderr.write("HINWEIS: %d verwaiste Zeilen aus den Suchtabellen "
                         "entfernt (N-16). Der Suchindex baut sich wieder auf; "
                         "wer sofort alles finden will, laesst in der "
                         "Verwaltung 'Index neu' laufen.\n" % weg)
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

def wiki_gruppen(gruppen):
    """Nur die Gruppen, die dieses Wiki angehen."""
    return {g for g in gruppen if g.startswith(GRUPPEN_PRAEFIX)}


class Nutzer:
    def __init__(self, kennung, name, email, gruppen):
        self.kennung = kennung
        self.name = name or kennung
        self.email = email or ""
        alle = {g for g in gruppen if g}
        self.gruppen = wiki_gruppen(alle)
        # Was aussortiert wurde, bleibt zaehlbar: die Einstellungsseite sagt
        # "3 Gruppen anderer Tools ignoriert", damit niemand raetselt, warum
        # seine Gruppe hier nicht auftaucht.
        self.gruppen_andere = sorted(alle - self.gruppen)
        self.gruppen_roh = ""
        self.ist_admin = (ADMIN_GRUPPE in self.gruppen) or (kennung in ADMIN_NUTZER)
        # Verwalter duerfen alles, was ein Editor darf - sonst muesste man sich
        # zwei Gruppen geben, um eine Seite anzulegen.
        self.ist_editor = self.ist_admin or (EDITOR_GRUPPE in self.gruppen)


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


def zweig_tabelle():
    """Alle Zweig-Freigaben, EINMAL je Anfrage gelesen (B-47).

    Vorher fragte zweig_gruppen() je Aufruf und je Pfadebene die Datenbank.
    sichtbare_seiten() ruft das fuer JEDE Seite auf - bei 500 Seiten mit drei
    Ebenen waren das 1500 Abfragen fuer eine einzige Antwort. Der
    Zwischenspeicher haengt an der Verbindung und wird mit ihr freigegeben,
    ist also nie aelter als die laufende Anfrage.
    """
    t = getattr(_lokal, "zweige", None)
    if t is None:
        t = {z["pfad"]: set(json.loads(z["gruppen_json"] or "[]"))
             for z in db().execute("SELECT pfad,gruppen_json FROM zweig")}
        _lokal.zweige = t
    return t


def zweig_gruppen(pfad_liste):
    """Geerbte Gruppen aller Ebenen oberhalb der Seite."""
    t = zweig_tabelle()
    noetig = set()
    for i in range(1, len(pfad_liste) + 1):
        noetig |= t.get("/".join(pfad_liste[:i]), set())
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


# Woerter, die in Skripten fast nur als Technik vorkommen und im Suchindex
# nichts nuetzen. Kurz gehalten: ein paar Treffer zu viel kosten wenig, ein
# aufgeblaehter Index dagegen macht die Schnipsel unbrauchbar.
SKRIPT_MUELL = {
    "none", "block", "flex", "grid", "auto", "hidden", "visible", "inline",
    "absolute", "relative", "fixed", "sticky", "center", "left", "right",
    "click", "change", "input", "submit", "load", "message", "keydown",
    "div", "span", "button", "true", "false", "null", "undefined", "px",
    "class", "style", "data", "text", "html", "json", "get", "post",
}
# CLAUDE.md §11: Text auf sinnvolle Laenge begrenzt. Die Zahlen kommen aus der
# Messung (N-20): ein Titel von 376 Zeichen machte den Kopf der Anwendung am
# Handy 523 Pixel hoch. 120 Zeichen sind zwei Zeilen und passen ueberall hin,
# wo ein Titel auftaucht - Kopf, Themenbaum, Inhaltsverzeichnis, Suchtreffer.
GRENZE_TITEL = 120
GRENZE_KURZ = 300
GRENZE_PFADTEIL = 60
GRENZE_STICHWORT = 60
# Wie viel sichtbarer Text im Koerper mindestens stehen muss, damit eine Seite
# als Seite gilt (N-23). Vierzig Zeichen sind eine halbe Zeile - darunter
# bekommt der Leser nichts, egal wie voll der Meta-Block ist.
GRENZE_SICHTBAR = 40

# Der Pflichtteil ist der Skriptblock, den die Huelle in JEDE Seite legt:
# Inhaltsverzeichnis, Suche in der Seite, PDF-Bausteine. Er ist NICHT das, was
# der Einspielende sich holt - er ist das, was das Wiki dazugibt (N-40).
#
# Die Marke steht in der ersten Zeile des Blocks und ist eindeutig; "Shell"
# steht noch in den zwei aeltesten Seiten, beide Schreibweisen muessen
# treffen. Dasselbe Muster benutzt pflichtteil-nachziehen.mjs.
PFLICHTTEIL_MARKE = re.compile(
    r"/\* Pflichtteil jeder Wiki-Seite: auf die (?:Huelle|Shell) hoeren\. \*/")
# Der Fingerabdruck steht in index.html, direkt neben dem Code, der den
# Pflichtteil baut. Gehalten wird er von pflichtteil-nachziehen.mjs und
# tests/test_editor.mjs.
PFLICHTTEIL_KENNUNG_MUSTER = re.compile(
    r"const ED_PFLICHTTEIL_KENNUNG = 'sha256:([0-9a-f]{64})';")
_pflichtteil_kennung = []


def pflichtteil_kennung():
    """Der Fingerabdruck des Pflichtteils, den diese Huelle baut - oder None.

    None heisst: nicht feststellbar. Dann wird der Pflichtteil NICHT erkannt
    und alles gemeldet wie vor N-40. Lieber ein Hinweis zu viel als eine
    stille Ausnahme - und vor allem keine falsche Entwarnung, denn "erkannt"
    heisst hier "Zeichen fuer Zeichen der Block dieser Huelle".
    """
    if not _pflichtteil_kennung:
        try:
            with open(os.path.join(EIGENER_ORDNER, "index.html"),
                      encoding="utf-8") as f:
                m = PFLICHTTEIL_KENNUNG_MUSTER.search(f.read())
            _pflichtteil_kennung.append(m.group(1) if m else None)
        except OSError:
            _pflichtteil_kennung.append(None)
    return _pflichtteil_kennung[0]

SKRIPT_TEXT_GRENZE = 60000
# Wie viel Text eine Seite von sich selbst melden darf. 200 000 Zeichen sind
# rund 30 000 Woerter - mehr hat keine Wiki-Seite, und die Grenze verhindert,
# dass eine Seite die Datenbank vollschreibt.
ANSICHT_GRENZE = 200000


def text_aus_skripten(html):
    """Zeichenketten aus den Skriptbloecken einer Seite (N-11).

    Eine Seite, die ihren Inhalt erst im Browser aufbaut - Tabellen,
    Glossare, Schrittfolgen -, hat diesen Inhalt nirgends im HTML. Die Suche
    fand ihn darum nicht: "tcp" ergab null Treffer, obwohl TCP auf der Seite
    steht und in der Liste der Transportprotokolle sichtbar ist.

    Gelesen werden nur Zeichenketten, keine Anweisungen: was in
    Anfuehrungszeichen steht, ist Inhalt oder Beschriftung. Alles, was nach
    Code aussieht (Klammern, Semikolon, Selektoren, Adressen), fliegt raus.
    Der Meta-Block bleibt aussen vor, der ist schon im Index.
    """
    # Der Pflichtteil steht in JEDER Seite und ist Technik, kein Inhalt.
    # Ohne diesen Schritt fand die Suche nach "dark", "light", "prefers",
    # "section", "details" oder "warn" jeweils ALLE fuenf Seiten - sechs
    # Woerter, die auf alles passen, sind das Gegenteil einer Suche (N-28).
    # Erkannt wird der Block an seiner ersten Zeile; beide Schreibweisen,
    # weil die zwei aeltesten Seiten noch "Shell" sagen.
    html = re.sub(r"(?is)<script>\s*/\*\s*Pflichtteil jeder Wiki-Seite:"
                  r"\s*auf die (?:Huelle|Shell) hoeren\.\s*\*/.*?</script>",
                  " ", html)
    bloecke = re.findall(r"(?is)<script([^>]*)>(.*?)</script>", html)
    stuecke = []
    for attr, inhalt in bloecke:
        if "application/json" in attr.lower() or "wiki-meta" in attr.lower():
            continue
        # Ein Block, der ausdruecklich Technik ist und kein Inhalt. Damit
        # kann eine von Hand gebaute Seite sagen: hier steht nichts zum
        # Suchen. Der Pflichtteil braucht das nicht - der wird oben schon
        # an seiner ersten Zeile erkannt.
        if "data-wiki-technik" in attr.lower():
            continue
        for muster in (r"'((?:[^'\\\n]|\\.)*)'",
                       r'"((?:[^"\\\n]|\\.)*)"',
                       r"`((?:[^`\\]|\\.)*)`"):
            for roh in re.findall(muster, inhalt):
                t = roh.replace("\\n", " ").replace("\\t", " ").strip()
                if len(t) < 2 or len(t) > 400:
                    continue
                if not re.search(r"[A-Za-zÄÖÜäöüß]", t):
                    continue
                if re.search(r"[<>{};=]|://", t):
                    continue
                if " " not in t:
                    if t.startswith((".", "#", "/", "-", "&")):
                        continue
                    # Ein Wort mit Bindestrich oder Punkt und ohne Leerzeichen
                    # ist eine Kennung, kein Inhalt: wiki-springen,
                    # mark.wiki-fund, prefers-color-scheme.
                    if "-" in t or "." in t:
                        continue
                    if t.lower() in SKRIPT_MUELL:
                        continue
                stuecke.append(t)
    if not stuecke:
        return ""
    # Reihenfolge behalten, Doppelte weg (ein Wort steht oft in mehreren
    # Zeilen und wuerde die Schnipsel zumuellen).
    gesehen, sauber = set(), []
    for t in stuecke:
        k = t.lower()
        if k in gesehen:
            continue
        gesehen.add(k)
        sauber.append(t)
    return re.sub(r"\s+", " ", " · ".join(sauber))[:SKRIPT_TEXT_GRENZE]


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


def genannte_anhaenge(html):
    """Die Anhangsnamen, die in dieser Seite vorkommen (N-18).

    Zwei Schreibweisen: die Marke data-wiki-anhang="name", die das
    Ausgliedern hinterlaesst, und ein Verweis auf anhaenge/name im Text
    (Bild, Verweis, iframe). Mehr braucht es nicht - es geht nur darum, ob
    die Seite den Anhang noch benutzt.
    """
    namen = set(re.findall(r'data-wiki-anhang=["\']([^"\']+)["\']', html))
    namen |= set(re.findall(r'anhaenge/([A-Za-z0-9][A-Za-z0-9._-]*)', html))
    return {n for n in namen if n and DATEINAME_MUSTER.match(n)}


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
        # Die Schwelle gilt fuer Bloecke, die ZUFAELLIG gross sind. Traegt der
        # Block die Marke data-wiki-anhang, ist er ausdruecklich als Anhang
        # gemeint - dann wird er ausgegliedert, egal wie gross er ist. Genau
        # das braucht der PDF-Baustein des Editors: ein PDF mit 30 KB ist
        # trotzdem ein Anhang, und nur als Anhang laesst es sich anzeigen und
        # seitenweise durchsuchen.
        gewollt = "data-wiki-anhang" in auf.lower()
        if not re.fullmatch(r"[A-Za-z0-9+/=\s]+", roh):
            return m.group(0)
        if len(roh) < schwelle and not gewollt:
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
        roh = m.group(2)
        if len(roh) < schwelle:
            return m.group(0)
        typ, endung = typ_erkennen(roh[:10])
        name = naechster_name(endung, "eingebettet")
        try:
            daten = base64.b64decode(re.sub(r"\s", "", roh), validate=False)
        except Exception:
            return m.group(0)
        gefunden.append({"name": name, "typ": typ, "daten": daten, "marke": ""})
        # Der GANZE Ausdruck wird ersetzt, nicht nur der Datenteil. Vorher
        # blieb das "data:image/png;base64," davor stehen, und heraus kam
        #     src="data:image/png;base64,anhaenge/eingebettet.png"
        # Der Browser liest das als Base64, bekommt Unsinn und zeigt nichts
        # (N-31). Die Pruefung meldete dabei "eingespielt" und legte den
        # Anhang sauber ab - kaputt war nur das, was der Leser sieht.
        return f"anhaenge/{name}"

    # Die Schwelle steht EINMAL, in uri_ersetzen. Vorher stand sie auch hier
    # noch als Bedingung - zwei Riegel fuer dieselbe Sache, von denen keiner
    # fuer sich pruefbar ist: nimmt man einen weg, faellt es nicht auf.
    neu = re.sub(r"(data:[a-zA-Z0-9/.+-]+;base64,)([A-Za-z0-9+/=]{1000,})",
                 uri_ersetzen, neu)
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
    titel = (meta.get("titel") or "").strip()
    if not titel:
        fehler.append("Im Block wiki-meta fehlt das Feld 'titel'.")
    elif len(titel) > GRENZE_TITEL:
        # CLAUDE.md §11: "Text auf sinnvolle Laenge begrenzt?" Ein Titel von
        # 376 Zeichen liess am Handy den Kopf der Anwendung auf 523 Pixel
        # wachsen - zwei Drittel des Schirms fuer eine Zeile (N-20).
        fehler.append(f"Der Titel ist {len(titel)} Zeichen lang, erlaubt sind "
                      f"{GRENZE_TITEL}. Er steht im Kopf, im Themenbaum und in "
                      "jedem Suchtreffer.")
    kurz = (meta.get("kurz") or "").strip()
    if len(kurz) > GRENZE_KURZ:
        fehler.append(f"Der Satz unter dem Titel ist {len(kurz)} Zeichen lang, "
                      f"erlaubt sind {GRENZE_KURZ}. Er ist eine Zusammenfassung, "
                      "kein Abschnitt.")

    pfad = meta.get("pfad")
    if not isinstance(pfad, list) or not pfad or not all(isinstance(p, str) and p.strip() for p in pfad):
        fehler.append("Das Feld 'pfad' muss eine nicht leere Liste sein, "
                      'zum Beispiel ["Technik", "Netzwerke"].')
    elif len(pfad) > 4:
        warnungen.append("Der Pfad ist tiefer als vier Ebenen. Das wird in der "
                         "Navigation unuebersichtlich.")
    if isinstance(pfad, list):
        for teil in pfad:
            if isinstance(teil, str) and len(teil.strip()) > GRENZE_PFADTEIL:
                fehler.append(f"Die Pfadebene '{teil.strip()[:30]}…' ist "
                              f"{len(teil.strip())} Zeichen lang, erlaubt sind "
                              f"{GRENZE_PFADTEIL}.")

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
        atitel = str(a.get("titel") or "").strip()
        if len(atitel) > GRENZE_TITEL:
            fehler.append(f"Der Titel von Abschnitt {i} ist {len(atitel)} Zeichen "
                          f"lang, erlaubt sind {GRENZE_TITEL}. Er steht im "
                          "Inhaltsverzeichnis.")
        for wort in (a.get("stichworte") or []):
            if isinstance(wort, str) and len(wort.strip()) > GRENZE_STICHWORT:
                fehler.append(f"Das Stichwort '{wort.strip()[:30]}…' in Abschnitt "
                              f"{i} ist zu lang (erlaubt: {GRENZE_STICHWORT}).")
                break
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
                         "gefunden. Die Regeln verlangen Tokens aus CLAUDE.md \u00a72.")

    if not re.search(r"focus-visible", html):
        warnungen.append("Der Pflichtblock aus CLAUDE.md §8.1 fehlt "
                         "(focus-visible, prefers-reduced-motion).")

    # Steht im Koerper ueberhaupt etwas? Ein voller Meta-Block mit leerem
    # <body> ging vorher fehlerfrei durch (N-23): die Seite landete im
    # Themenbaum, die Suche fand ihre Abschnitte - und der Leser bekam eine
    # weisse Flaeche. Gemessen: 3703 Byte Datei, 0 Zeichen sichtbarer Text.
    #
    # Eine Ausnahme braucht es: Seiten, die ihren Inhalt erst im Browser
    # bauen, sind ausdruecklich erlaubt (siehe N-11). Traegt die Seite also
    # einen ausfuehrbaren Skriptblock, wird nichts beanstandet - lieber keine
    # Beanstandung als eine falsche.
    sichtbar = re.sub(r"(?is)<(script|style|template)\b[^>]*>.*?</\1\s*>", " ", koerper_von(html))
    sichtbar = re.sub(r"(?s)<!--.*?-->", " ", sichtbar)
    sichtbar = re.sub(r"(?s)<[^>]*>", " ", sichtbar)
    sichtbar = re.sub(r"\s+", " ", sichtbar).strip()
    baut_selbst = any(
        inhalt.strip() and not re.search(
            r'(?i)type\s*=\s*["\']?(?:application/(?:ld\+)?json|text/plain)', attr)
        for attr, inhalt in re.findall(r"(?is)<script\b([^>]*)>(.*?)</script\s*>", html))
    if len(sichtbar) < GRENZE_SICHTBAR and not baut_selbst:
        fehler.append(
            f"Im <body> steht fast kein sichtbarer Text ({len(sichtbar)} Zeichen). "
            "Der Meta-Block allein ist keine Seite: Themenbaum und Suche haetten "
            "Eintraege, der Leser eine leere Flaeche. Wenn die Datei nur als "
            "Entwurf gedacht war, lade sie in den Editor - er baut die Seite "
            "aus dem Meta-Block.")

    return fehler, warnungen


def koerper_von(html):
    """Der Inhalt zwischen <body> und </body>, oder alles, wenn es kein body gibt.

    Ohne <body> ist die Datei kein vollstaendiges HTML - dann wird sie ganz
    betrachtet, statt sie durchzuwinken.
    """
    m = re.search(r"(?is)<body[^>]*>(.*)</body\s*>", html)
    if m:
        return m.group(1)
    m = re.search(r"(?is)<body[^>]*>(.*)$", html)
    return m.group(1) if m else html


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

    # Zwei Bloecke zaehlen NICHT als Code, den die Seite mitbringt:
    #
    # 1. Der Meta-Block ist type="application/json" und gar nicht ausfuehrbar.
    # 2. Der Pflichtteil kommt aus der Huelle selbst (N-40).
    #
    # Beide Male aus demselben Grund: eine Warnung, die bei JEDER harmlosen
    # Seite angeht, wird nicht gelesen. Gemessen vor N-40 an allen sechs
    # mitgelieferten Seiten: jede meldete "1 Skriptblock mit 12534 Zeichen"
    # und "parent. - die Seite greift nach der Huelle", Zeichen fuer Zeichen
    # dieselbe Zahl. Danach rutscht die eine Seite durch, die wirklich etwas
    # Fremdes mitbringt.
    #
    # Erkannt wird der Pflichtteil nur bei EXAKTER Uebereinstimmung mit dem
    # Fingerabdruck dieser Huelle. Alles andere - eine aeltere Fassung, ein
    # Zeichen mehr, etwas Hineingeschriebenes - bleibt Code der Seite und
    # bekommt zusaetzlich seinen eigenen Hinweis.
    erwartet = pflichtteil_kennung()
    code, pflicht_gleich, pflicht_anders = [], False, False
    for m in re.finditer(r"(?is)<script\b([^>]*)>(.*?)</script>", html):
        attr, inhalt = m.group(1), m.group(2)
        if not inhalt.strip():
            continue
        if re.search(r'(?i)type\s*=\s*["\']?application/(?:ld\+)?json', attr):
            continue
        if erwartet and PFLICHTTEIL_MARKE.search(inhalt):
            block = m.group(0).replace("\r\n", "\n")
            if hashlib.sha256(block.encode("utf-8")).hexdigest() == erwartet:
                pflicht_gleich = True
                continue
            pflicht_anders = True
        code.append(inhalt)
    if pflicht_anders:
        hinweise.append(
            "Der Pflichtteil dieser Seite ist nicht der dieser Huelle. Das kann "
            "eine aeltere Fassung sein - oder etwas, das jemand hineingeschrieben "
            "hat. Sieh ihn dir an; oder speichere die Seite einmal durch den "
            "Editor, der legt ihn neu an.")
    if code:
        zeichen = sum(len(k) for k in code)
        hinweise.append(f"{len(code)} Skriptblock(e) mit zusammen {zeichen} "
                        "Zeichen. Die Seite bringt eigenen Code mit."
                        + (" (Der Pflichtteil des Wikis ist dabei nicht "
                           "mitgezaehlt.)" if pflicht_gleich else ""))

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


def urheber_von(z):
    """Wer die Seite angelegt hat (N-15).

    seite.nutzer_id wird bei jeder Uebernahme neu geschrieben und bedeutet
    darum "wer zuletzt gespeichert hat". Als Schreibrecht war das falsch:
    sobald ein Verwalter eine Zeile richtete, stand er selbst drin - und der
    Urheber kam an seine eigene Seite nicht mehr heran. Darum die eigene
    Spalte, mit Rueckfall auf nutzer_id fuer Zeilen, die aus einer Datenbank
    vor 1.2.0 stammen.
    """
    try:
        u = z["urheber"]
    except (KeyError, IndexError):
        u = ""
    return (u or "") or (z["nutzer_id"] or "")


def darf_aendern(z, nutzer):
    """Darf dieser Nutzer diese bestehende Seite aendern? (N-13, N-15, N-21)

    Drei Stufen:
      lesen     jeder Angemeldete, im Rahmen der Freigaben
      schreiben wer in EDITOR_GRUPPE ist - anlegen und die EIGENEN Seiten
                aendern. Sonst koennte jeder die Arbeit aller anderen
                ueberschreiben.
      verwalten ADMIN_GRUPPE: alle Seiten, alle Freigaben, loeschen.
    """
    if not getattr(nutzer, "ist_editor", False):
        return False
    if nutzer.ist_admin:
        return True
    return bool(nutzer.kennung) and urheber_von(z) == nutzer.kennung


def spalte_nachtragen(v, tabelle, spalte, bauart):
    """Eine Spalte in einer bestehenden Datenbank nachtragen.

    CREATE TABLE IF NOT EXISTS legt keine Spalte in einer Tabelle nach, die
    es schon gibt. Darum dieser Weg: nur hinzufuegen, nie etwas
    ueberschreiben. Gibt True zurueck, wenn die Spalte angelegt wurde.
    """
    spalten = {z["name"] for z in
               v.execute("PRAGMA table_info(%s)" % tabelle).fetchall()}
    if spalte in spalten:
        return False
    v.execute("ALTER TABLE %s ADD COLUMN %s %s" % (tabelle, spalte, bauart))
    return True


def spalte_urheber_nachtragen(v):
    """Aeltere Datenbank auf die Spalte urheber bringen (N-15).

    Nur Hinzufuegen und Fuellen, nichts wird ueberschrieben. Gefuellt wird
    aus der Fassungsgeschichte: die erste archivierte Fassung traegt die
    Kennung dessen, der sie geschrieben hat - das ist der Urheber. Gibt es
    keine, bleibt nutzer_id die beste vorhandene Auskunft.

    Gibt True zurueck, wenn die Spalte angelegt wurde.
    """
    if not spalte_nachtragen(v, "seite", "urheber", "TEXT NOT NULL DEFAULT ''"):
        return False
    v.execute("UPDATE seite SET urheber = COALESCE("
              "(SELECT f.nutzer_id FROM fassung f WHERE f.seite_id = seite.id "
              "AND f.nutzer_id <> '' ORDER BY f.nummer LIMIT 1), nutzer_id)")
    return True


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
        # nutzer_id wird neu geschrieben, urheber NICHT (N-15): wer die Seite
        # angelegt hat, bleibt ihr Urheber, auch wenn ein Verwalter sie
        # anfasst. Leer ist er nur bei Zeilen aus einer alten Datenbank ohne
        # Fassungsgeschichte - dann wird er hier nachgetragen.
        v.execute("UPDATE seite SET titel=?,kurz=?,pfad_json=?,gruppen_json=?,stand=?,"
                  "fassung=?,groesse_b=?,regelkonform=?,hinweise_json=?,nutzer_id=?,"
                  "geaendert=? WHERE slug=?", daten + (slug,))
        v.execute("UPDATE seite SET urheber=? WHERE slug=? AND urheber=''",
                  (urheber_von(alt), slug))
        seite_id = alt["id"]
    else:
        v.execute("INSERT INTO seite(titel,kurz,pfad_json,gruppen_json,stand,fassung,"
                  "groesse_b,regelkonform,hinweise_json,nutzer_id,geaendert,slug,"
                  "urheber) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  daten + (slug, nutzer.kennung))
        seite_id = v.execute("SELECT id FROM seite WHERE slug=?", (slug,)).fetchone()["id"]

    v.execute("DELETE FROM abschnitt WHERE seite_id=?", (seite_id,))
    for i, a in enumerate(teile["abschnitte"]):
        v.execute("INSERT INTO abschnitt(seite_id,anker,titel,ebene,stichworte,text,"
                  "gruppe,reihenfolge) VALUES(?,?,?,?,?,?,?,?)",
                  (seite_id, a.get("anker", ""), a.get("titel", ""), a.get("ebene", 1),
                   " ".join(a.get("stichworte", []) or []), a.get("text", "") or "",
                   str(a.get("gruppe", "") or "").strip()[:80], i))

    # Anhaenge (N-18): Die Zeilen der Anhaenge, die diese Seite weiter nennt,
    # bleiben - sonst verliert eine Seite beim Bearbeiten ihre Anhaenge. Genau
    # das passierte, sobald der Editor eine Seite neu speichert: die Datei
    # liegt schon auf dem Server, die neue Fassung nennt sie nur noch (die
    # Marke data-wiki-anhang), also kam nichts Neues an - und die Zeile war
    # weg. Folge: Der Abruf lieferte application/octet-stream statt
    # application/pdf (der Browser laedt herunter statt zu zeigen), die Seite
    # meldete keine Anhaenge mehr, und der Text des PDFs fiel aus der Suche.
    neue = {a["name"] for a in teile["anhaenge"]}
    genannt = genannte_anhaenge(html)
    behalten = []
    for z in v.execute("SELECT name,typ,groesse_b,marke FROM anhang WHERE seite_id=?",
                       (seite_id,)).fetchall():
        if z["name"] in neue or z["name"] not in genannt:
            continue
        if not os.path.exists(os.path.join(ordner, "anhaenge", z["name"])):
            continue
        behalten.append(tuple(z))
    v.execute("DELETE FROM anhang WHERE seite_id=?", (seite_id,))
    for name, typ, groesse, marke in behalten:
        v.execute("INSERT INTO anhang(seite_id,name,typ,groesse_b,marke) VALUES(?,?,?,?,?)",
                  (seite_id, name, typ, groesse, marke))
    for a in teile["anhaenge"]:
        v.execute("INSERT INTO anhang(seite_id,name,typ,groesse_b,marke) VALUES(?,?,?,?,?)",
                  (seite_id, a["name"], a["typ"], len(a["daten"]), a["marke"]))
    v.commit()

    # Der Index wird NACH dem Festschreiben gebaut, und er darf die Uebernahme
    # nicht mehr umwerfen (N-12). Vorher lief index_neu_bauen() ungeschuetzt:
    # ging dort etwas schief - ein PDF-Anhang, den pdftotext nicht mochte, eine
    # FTS-Eigenheit -, dann war die Seite gespeichert und die Antwort trotzdem
    # ein Serverfehler. Der Nutzer sah "Server Fehler", lud neu, und die Seite
    # war da. Genau dieser Widerspruch.
    #
    # Der Index ist abgeleitet und jederzeit neu baubar (Verwaltung > Index
    # neu). Die Seite ist es nicht. Darum: Fehler einsammeln, weitergeben,
    # protokollieren - aber die Uebernahme gilt.
    indexfehler = ""
    try:
        index_neu_bauen(seite_id, html)
    except Exception as e:                                    # noqa: BLE001
        indexfehler = f"{type(e).__name__}: {e}"
        sys.stderr.write("FEHLER beim Indexaufbau fuer Seite %s: %s\n"
                         % (slug, indexfehler))
        traceback.print_exc(file=sys.stderr)
    return seite_id, nummer, indexfehler


def index_leeren(v, seite_id):
    """Alle Indexzeilen einer Seite entfernen - erst die Suchtabellen, dann treffer.

    Die Reihenfolge ist der ganze Punkt (N-16). treffer.id ist ein
    rowid-Alias und dient gleichzeitig als rowid in den FTS-Tabellen. Wird
    eine treffer-Zeile entfernt, ohne ihre FTS-Zeile mitzunehmen, bleibt
    dort eine verwaiste rowid liegen - und weil SQLite freigewordene
    rowids wiederverwendet, kollidiert der naechste Indexaufbau mit ihr:
    "IntegrityError: constraint failed". Danach baut sich der Index NIE
    wieder auf, auch nicht ueber "Index neu".
    """
    for z in v.execute("SELECT id FROM treffer WHERE seite_id=?", (seite_id,)).fetchall():
        v.execute("DELETE FROM suche WHERE rowid=?", (z["id"],))
        try:
            v.execute("DELETE FROM suche_tri WHERE rowid=?", (z["id"],))
        except sqlite3.OperationalError:
            pass
    v.execute("DELETE FROM treffer WHERE seite_id=?", (seite_id,))


def verwaiste_indexzeilen_loeschen(v):
    """Zeilen in den Suchtabellen ohne treffer-Zeile wegraeumen (N-16).

    Das ist die Reparatur fuer Datenbanken, in denen schon eine Seite
    geloescht wurde: dort liegen die FTS-Zeilen noch, und jeder Indexaufbau
    scheitert an ihnen. Der Index ist abgeleitet - hier geht nichts verloren,
    was sich nicht neu bauen laesst.

    Gibt die Anzahl entfernter Zeilen zurueck.
    """
    weg = 0
    for tabelle, spalte in (("suche", "rowid"), ("suche_tri", "rowid")):
        try:
            cur = v.execute("DELETE FROM %s WHERE %s NOT IN "
                            "(SELECT id FROM treffer)" % (tabelle, spalte))
            weg += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        except sqlite3.OperationalError:
            pass                    # Tabelle gibt es nicht (Trigramm fehlt)
    return weg


def index_neu_bauen(seite_id, html=None):
    """Suchindex einer Seite verwerfen und frisch aufbauen."""
    v = db()
    seite = v.execute("SELECT * FROM seite WHERE id=?", (seite_id,)).fetchone()
    if not seite:
        return
    index_leeren(v, seite_id)

    def eintragen(art, anker, anhang_name, seitennr, titel, stichworte, text):
        if not (text or "").strip() and not (stichworte or "").strip():
            return
        cur = v.execute("INSERT INTO treffer(seite_id,art,anker,anhang_name,seitennr,"
                        "abschnittstitel) VALUES(?,?,?,?,?,?)",
                        (seite_id, art, anker, anhang_name, seitennr, titel))
        tid = cur.lastrowid
        # Guertel und Hosentraeger (N-16): liegt unter dieser rowid noch eine
        # verwaiste Zeile, wird sie hier weggeraeumt statt den ganzen Aufbau
        # umzuwerfen. Ein Indexaufbau darf an Resten nicht scheitern.
        v.execute("DELETE FROM suche WHERE rowid=?", (tid,))
        try:
            v.execute("DELETE FROM suche_tri WHERE rowid=?", (tid,))
        except sqlite3.OperationalError:
            pass
        v.execute("INSERT INTO suche(rowid,titel,stichworte,text) VALUES(?,?,?,?)",
                  (tid, titel, stichworte, text))
        try:
            v.execute("INSERT INTO suche_tri(rowid,inhalt) VALUES(?,?)",
                      (tid, f"{titel} {stichworte} {text}"))
        except sqlite3.OperationalError:
            pass

    abschnitte = v.execute(
        "SELECT * FROM abschnitt WHERE seite_id=? ORDER BY reihenfolge",
        (seite_id,)).fetchall()
    for a in abschnitte:
        # Die Gruppe gehoert zu den Stichworten des Abschnitts: wer nach
        # "Adressierung" sucht, will den Abschnitt, nicht nur die Seite.
        stich = " ".join(x for x in (a["stichworte"], a["gruppe"]) if x)
        eintragen("abschnitt", a["anker"], "", 0, a["titel"], stich, a["text"])

    # Der Seitenkopf als eigener Treffer: Titel, der Satz darunter, der Pfad im
    # Themenbaum, die Gruppen des Verzeichnisses und die Abschnittstitel.
    #
    # Ohne das ist eine Seite nur ueber ihren INHALT zu finden, nicht ueber das,
    # was sie beschreibt. In der Messung fehlten damit sechs von 22 Begriffen:
    # "Haushalt" und "Energie" (nur im Pfad), "hingeht" (nur im Satz der Seite),
    # "Grundlagen" und "Adressierung" (nur als Gruppe). Genau die Woerter, mit
    # denen ein Mensch anfaengt, wenn er den Titel nicht mehr weiss.
    pfad = " ".join(json.loads(seite["pfad_json"] or "[]"))
    gruppen = []
    for a in abschnitte:
        g = (a["gruppe"] or "").strip()
        if g and g not in gruppen:
            gruppen.append(g)
    eintragen("kopf", "", "", 0, seite["titel"],
              " ".join(x for x in [pfad, " ".join(gruppen), seite["slug"]] if x),
              " ".join(x for x in [seite["kurz"]] +
                       [a["titel"] for a in abschnitte] if x))

    # Sichtbarer Seitentext als zusaetzliches Netz.
    if html is None:
        p = os.path.join(seitenordner(seite["slug"]), "seite.html")
        html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    roh = text_aus_html(html)
    if roh:
        for i in range(0, min(len(roh), 200000), 4000):
            eintragen("seite", "", "", 0, seite["titel"], "", roh[i:i + 4000])

    # Drittes Netz: was die Seite erst im Browser aufbaut (N-11). Zwei
    # Quellen, und die erste ist die genauere.
    #
    # 1. Der Text, den die Seite selbst gemeldet hat - genau das, was ein
    #    Leser sieht. Gibt es nur, wenn die Seite den aktuellen Pflichtteil
    #    traegt und schon einmal geoeffnet wurde.
    # 2. Die Zeichenketten aus den Skripten. Ungenauer, aber ohne Mitwirkung
    #    der Seite zu haben - und damit auch fuer aeltere Seiten.
    gemeldet = v.execute("SELECT text FROM ansichtstext WHERE seite_id=?",
                         (seite_id,)).fetchone()
    gemeldet = (gemeldet["text"] if gemeldet else "") or ""
    if gemeldet:
        for i in range(0, len(gemeldet), 4000):
            eintragen("ansicht", "", "", 0, seite["titel"], "", gemeldet[i:i + 4000])
    # Die Zeichenketten aus den Skripten nur, wenn die Seite ihren Text NICHT
    # gemeldet hat. Sonst stuende derselbe Inhalt zweimal im Index, und die
    # Trefferliste zeigte jede Seite doppelt - einmal mit gutem Schnipsel,
    # einmal mit einer Aufzaehlung von Zeichenketten.
    if not gemeldet:
        skript = text_aus_skripten(html)
        if skript:
            for i in range(0, len(skript), 4000):
                eintragen("skript", "", "", 0, seite["titel"], "", skript[i:i + 4000])

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

# Die Felder, die im Suchbegriff als "feld:wert" stehen duerfen. Bewusst
# wenige: jedes weitere ist ein Wort, das nicht mehr als Wort gesucht wird.
SUCH_FELDER = ("bereich", "gruppe", "seite")


def suchbegriff_lesen(roh):
    """Einen Suchbegriff in seine Teile zerlegen.

    Erkannt werden:

        wort              muss vorkommen, Wortanfang genuegt
        "mehrere worte"   genau diese Folge
        -wort             darf nicht vorkommen
        bereich:Technik   nur Seiten unter diesem Pfad
        gruppe:wiki-x     nur Seiten mit dieser Freigabe
        seite:kennung     nur diese eine Seite

    Alles andere bleibt ein gewoehnliches Wort - auch ein "feld:wert" mit
    einem Feld, das es hier nicht gibt. Sonst verschwindet ein Doppelpunkt
    im Text stillschweigend aus der Suche.
    """
    teile = {"worte": [], "phrasen": [], "ohne": [],
             "bereich": "", "gruppe": "", "seite": ""}
    s = roh or ""
    i, n = 0, len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        minus = False
        if s[i] == "-" and i + 1 < n and not s[i + 1].isspace():
            minus = True
            i += 1
        feld = ""
        m = re.match(r"([a-zA-ZäöüÄÖÜ]+):", s[i:])
        if m and m.group(1).lower() in SUCH_FELDER:
            feld = m.group(1).lower()
            i += m.end()
        if i < n and s[i] == '"':
            ende = s.find('"', i + 1)
            if ende < 0:
                ende = n
            wert, i, phrase = s[i + 1:ende], ende + 1, True
        else:
            ende = i
            while ende < n and not s[ende].isspace():
                ende += 1
            wert, i, phrase = s[i:ende], ende, False
        wert = wert.strip()
        if not wert:
            continue
        if feld:
            # Ein Minus vor einem Feld waere ein Ausschluss von Seiten - das
            # gibt es hier nicht, und stillschweigend etwas anderes tun ist
            # schlimmer als es zu ignorieren.
            teile[feld] = wert
        elif minus:
            teile["ohne"].append(wert)
        elif phrase:
            teile["phrasen"].append(wert)
        else:
            teile["worte"].append(wert)
    return teile


def fts_wort(text, praefix):
    """Ein Stueck Suchbegriff in ein FTS5-Wort verwandeln.

    Alles, was FTS5 als Operator lesen koennte, fliegt heraus - uebrig
    bleiben Woerter in Anfuehrungszeichen. Ohne das wirft ein Suchbegriff
    mit Klammer oder Stern einen Fehler, und die Suche liefert nichts.
    """
    kern = " ".join(re.findall(r"[\wÄÖÜäöüß]+", text, re.UNICODE))
    if not kern:
        return None
    # Ein Stern hinter einer Wortfolge gilt in FTS5 nur fuer das letzte Wort.
    # Das ist genau richtig: "netz karte" soll "netzwerkkarte" nicht finden,
    # aber "netzwerk kar" darf auf "karte" hinauslaufen.
    return '"%s"%s' % (kern, "*" if praefix else "")


def fts_ausdruck_aus_teilen(teile, praefix=True, wortverbund="AND"):
    """Aus den Teilen eines Suchbegriffs einen FTS5-Ausdruck bauen.

    wortverbund entscheidet, wie die einzelnen WOERTER verbunden werden:
    "AND" verlangt alle, "OR" genuegt eines. Phrasen bleiben in beiden
    Faellen Pflicht - wer Anfuehrungszeichen setzt, meint sie. Vorher wurde
    fuer den weiten Durchgang " AND " in " OR " getauscht; das traf auch die
    Phrase, und "kabel \"rotes kabel\"" fand wieder beide Seiten.
    """
    phrasen = [a for a in (fts_wort(p, False) for p in teile["phrasen"]) if a]
    worte = [a for a in (fts_wort(w, praefix) for w in teile["worte"]) if a]
    if not phrasen and not worte:
        return None
    stuecke = list(phrasen)
    if worte:
        verbund = (" %s " % wortverbund).join(worte)
        # Klammern nur, wenn sie etwas aendern: neben einer Pflicht-Phrase
        # muss ein OR zusammenbleiben, sonst waere die Phrase mit oder-bar.
        stuecke.append("(%s)" % verbund if phrasen and len(worte) > 1 else verbund)
    aus = " AND ".join(stuecke)
    nein = [a for a in (fts_wort(w, praefix) for w in teile["ohne"]) if a]
    if nein:
        # NOT ist in FTS5 ein zweistelliger Operator: links das Gesuchte,
        # rechts das Unerwuenschte.
        aus = "(%s) NOT (%s)" % (aus, " OR ".join(nein))
    return aus




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
    teile = suchbegriff_lesen(begriff)
    erlaubt = {z["id"]: z for z in sichtbare_seiten(nutzer)}

    # Die Einschraenkungen greifen VOR der Suche, auf der Menge der Seiten:
    # damit bleibt die Abfrage selbst unveraendert, und "bereich:Technik"
    # ohne weiteres Wort kann trotzdem etwas liefern.
    if teile["seite"]:
        gesucht = teile["seite"].strip().lower()
        erlaubt = {i: z for i, z in erlaubt.items()
                   if z["slug"].lower() == gesucht}
    if teile["bereich"]:
        stufen = [x.strip().lower() for x in teile["bereich"].split("/") if x.strip()]

        def im_bereich(z):
            pfad = [str(x).strip().lower()
                    for x in json.loads(z["pfad_json"] or "[]")]
            return pfad[:len(stufen)] == stufen

        erlaubt = {i: z for i, z in erlaubt.items() if im_bereich(z)}
    if teile["gruppe"]:
        gesucht = teile["gruppe"].strip().lower()
        erlaubt = {i: z for i, z in erlaubt.items()
                   if gesucht in [str(x).strip().lower()
                                  for x in json.loads(z["gruppen_json"] or "[]")]}
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

    aus = fts_ausdruck_aus_teilen(teile, praefix=True)
    # Nur eine Einschraenkung, kein Wort: dann ist die Frage "was steht
    # ueberhaupt da" - und die Antwort sind die Seiten selbst, nicht nichts.
    if not aus and (teile["bereich"] or teile["gruppe"] or teile["seite"]):
        arten = ("kopf", "abschnitt") if teile["seite"] else ("kopf",)
        platz3 = ",".join("?" * len(arten))
        for z in v.execute(
                f"SELECT id AS tid FROM treffer WHERE art IN ({platz3}) "
                f"AND seite_id IN ({platz}) LIMIT ?",
                list(arten) + ids + [grenze * 3]).fetchall():
            aufnehmen(z["tid"], 1.0, "eingrenzung")
    if aus:
        for modus in ("und", "oder"):
            # Der zweite Durchgang laesst EIN Wort genuegen. Gebaut wird er
            # neu, nicht durch Ersetzen im fertigen Ausdruck: ein " AND ",
            # das zu einer Phrase oder zu einem Ausschluss gehoert, darf
            # dabei nicht mitwandern.
            frage = (aus if modus == "und"
                     else fts_ausdruck_aus_teilen(teile, True, "OR"))
            if not frage:
                continue
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
    # Das zweite Netz greift bei Komposita und Tippfehlern - und es sucht
    # dafuer nur mit dem LAENGSTEN Wort. Bei einer Phrase in
    # Anfuehrungszeichen ist das genau falsch: gemessen wurde aus
    # "TCP und UDP" (3 Stellen auf 1 Seite) ueber dieses Netz 5 Stellen auf
    # 2 Seiten - das Gegenteil dessen, was die Anfuehrungszeichen sagen.
    #
    # Ausschluesse braucht es hier NICHT abzufangen: die haelt der Nachfilter
    # weiter unten, und zwar fuer jede Quelle. Zwei Riegel fuer dieselbe
    # Sache waeren zwei, von denen keiner geprueft werden kann.
    if len(gefunden) < grenze and aus and not teile["phrasen"]:
        # Nur die gesuchten Woerter, nicht die Werte der Felder.
        positiv = " ".join(teile["worte"])
        kern = max(re.findall(r"[\wÄÖÜäöüß]{3,}", positiv, re.UNICODE) or [""], key=len)
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

    # Hervorgehoben wird, was gesucht war - nicht, was ausgeschlossen wurde,
    # und nicht "Technik" aus bereich:Technik.
    worte = re.findall(r"[\wÄÖÜäöüß]{2,}",
                       " ".join(teile["worte"] + teile["phrasen"]), re.UNICODE)
    # Ausschluesse gelten fuer das, was in der Zeile WIRKLICH steht. Das
    # FTS-NOT allein hat sie nur aus dem einen Netz genommen - ein zweiter
    # Weg (oder eine kuenftige dritte Quelle) haette sie wieder hereingeholt.
    # Hier steht die Regel einmal, am Ende, fuer jede Quelle.
    ohne = [w for w in (entwerten(x) for x in teile["ohne"]) if w]
    ergebnis = []
    for z in zeilen:
        if z["art"] == "anhang" and not mit_anhaengen:
            continue
        seite = erlaubt[z["seite_id"]]
        punkte, quelle = gefunden[z["id"]]
        titel = z["abschnittstitel"] or seite["titel"]
        # Der Bonus gilt fuer die gesuchten Woerter, nicht fuer den Rohtext:
        # "tcp bereich:Technik" steht in keinem Titel.
        gesuchter_text = " ".join(teile["worte"] + teile["phrasen"]).strip()
        if gesuchter_text and entwerten(gesuchter_text) in entwerten(titel):
            punkte += 25
        # Der Kopftreffer zeigt den Satz der Seite, nicht seinen Suchstoff.
        # Im Index stehen dort auch Pfad, Gruppen und alle Abschnittstitel -
        # das ist zum FINDEN da. Als Schnipsel gelesen ergaebe es eine
        # aneinandergehaengte Titelkette, und die sagt nichts.
        stoff = z["s_text"] or z["s_stich"] or ""
        if z["art"] == "kopf":
            stoff = seite["kurz"] or stoff
        if ohne:
            heuhaufen = entwerten(" ".join([
                titel or "", z["s_titel"] or "", z["s_stich"] or "",
                z["s_text"] or ""]))
            if any(w in heuhaufen for w in ohne):
                continue
        ergebnis.append({
            "slug": seite["slug"], "seitentitel": seite["titel"],
            "pfad": json.loads(seite["pfad_json"] or "[]"),
            "art": z["art"], "anker": z["anker"], "anhang": z["anhang_name"],
            "seitennr": z["seitennr"], "titel": titel,
            "schnipsel": schnipsel(stoff, worte),
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
        # Keine Kopfzeilen ins Protokoll, siehe CLAUDE.md §22.
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

    def darf_schreiben(self, z, n):
        """Siehe darf_aendern - hier nur der Weg vom Nutzer zur Auskunft."""
        return darf_aendern(z, n)

    def editor(self):
        """Der Nutzer, wenn er schreiben darf - sonst 403 mit dem Gruppennamen."""
        n = self.nutzer()
        if not n.ist_editor:
            raise Antwort(403,
                          "Zum Schreiben im Wiki brauchst du die Gruppe '%s'. "
                          "Lesen darfst du alles, was fuer dich freigegeben "
                          "ist. Die Gruppe vergibt ein Verwalter in Authentik."
                          % EDITOR_GRUPPE)
        return n

    def gruppen_pruefen(self, meta, n):
        """Eine Freigabe darf nur auf eigene Gruppen zeigen (N-13).

        Wer eine Seite fuer 'wiki-technik' freigibt, muss selbst in
        'wiki-technik' sein - sonst koennte man eine Seite in eine Gruppe
        legen, die man nicht kennt, und sie sich damit selbst wegnehmen.
        Verwalter duerfen jede Gruppe setzen.
        """
        gewuenscht = [g for g in (meta.get("gruppen") or []) if g]
        # Erst die Form, dann die Berechtigung: eine Freigabe auf eine Gruppe
        # ohne das Praefix ist ein stiller Fehler - sie nimmt die Seite allen
        # weg und gibt sie niemandem (N-21).
        falsch = [g for g in gewuenscht if not g.startswith(GRUPPEN_PRAEFIX)]
        if falsch:
            raise Antwort(400,
                          "Diese Gruppen gehoeren nicht zum Wiki: %s. Das Wiki "
                          "beachtet nur Gruppen, die mit '%s' anfangen - alles "
                          "andere gehoert anderen Werkzeugen und wuerde die "
                          "Seite fuer alle unsichtbar machen."
                          % (", ".join(sorted(falsch)), GRUPPEN_PRAEFIX))
        if n.ist_admin:
            return
        fremd = [g for g in gewuenscht if g not in n.gruppen]
        if fremd:
            raise Antwort(403,
                          "Diese Gruppen hast du selbst nicht: %s. Freigeben "
                          "kannst du nur fuer Gruppen, in denen du bist - "
                          "deine sind: %s."
                          % (", ".join(sorted(fremd)),
                             ", ".join(sorted(n.gruppen)) or "keine"))

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
            # (CLAUDE.md §22) - die Kennung fuehrt zur Protokollzeile.
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
            # (CLAUDE.md §22) - die Kennung fuehrt zur Protokollzeile.
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
                "ist_editor": n.ist_editor,
                "gruppen_andere": n.gruppen_andere,
                "gruppen_praefix": GRUPPEN_PRAEFIX,
                "gruppen_roh": n.gruppen_roh,
                "admin_gruppe": ADMIN_GRUPPE,
                "editor_gruppe": EDITOR_GRUPPE,
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
            zerlegt = suchbegriff_lesen(q)
            statt = None
            if not treffer:
                # Der Rechtschreibvorschlag gilt fuer die gesuchten Woerter.
                # Mit "bereich:Technik" im Begriff waere sonst "Technik" das
                # falsch geschriebene Wort.
                positiv = " ".join(zerlegt["worte"] + zerlegt["phrasen"])
                vorschlag = wortvorschlag(positiv) if positiv else None
                if vorschlag and vorschlag != positiv:
                    # Die Einschraenkungen bleiben stehen - nur die Woerter
                    # werden ersetzt.
                    rest = " ".join(
                        ["%s:%s" % (f, zerlegt[f]) for f in SUCH_FELDER if zerlegt[f]]
                        + ["-" + w for w in zerlegt["ohne"]])
                    treffer = suchen(n, (vorschlag + " " + rest).strip(),
                                     mit_anhaengen=mit_a)
                    if treffer:
                        # statt = das Wort, mit dem die Treffer gefunden
                        # wurden. Die Oberflaeche sagt damit "Nichts zu
                        # <q> - Treffer fuer <statt>" (N-27).
                        statt = vorschlag
            return self.json_senden({
                "q": q, "statt": statt, "treffer": treffer,
                # Was von dem Begriff als Einschraenkung gelesen wurde. Die
                # Oberflaeche zeigt es an - sonst sucht jemand nach
                # "bereich:Tehcnik" und sieht nur, dass nichts kommt.
                "eingrenzung": {f: zerlegt[f] for f in SUCH_FELDER if zerlegt[f]},
                "ohne": zerlegt["ohne"],
                "phrasen": zerlegt["phrasen"],
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
                "SELECT anker,titel,ebene,gruppe FROM abschnitt WHERE seite_id=? "
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
            # Wer die Seite aendern darf, darf auch ihre Fassungen sehen
            # (N-13) - sonst kann ein Urheber seine eigene Arbeit nicht
            # zurueckholen.
            nf = self.nutzer()
            z = db().execute("SELECT * FROM seite WHERE slug=?", (teile[1],)).fetchone()
            if z and not self.darf_schreiben(z, nf):
                raise Antwort(403, "Die Fassungen dieser Seite sieht ihr "
                                   "Urheber oder ein Verwalter.")
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
                "regelkonform,hinweise_json,nutzer_id,urheber,geaendert FROM seite "
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
            # Alle Gruppen, die im Wiki schon vorkommen - als Vorschlagsliste
            # fuer die Freigabe. Dazu die eigenen des Verwalters.
            bekannt = set()
            for z in zeilen:
                bekannt |= set(z["gruppen"])
            for z in zweige:
                bekannt |= set(z["gruppen"])
            bekannt |= self.nutzer().gruppen
            # Kennzahlen fuer die Wartung. Eine Verwaltung, die auf
            # hunderte Seiten ausgelegt ist, muss sagen koennen, wie gross
            # der Bestand ist - sonst ist "es geht langsam" nicht greifbar.
            def eine(frage, *werte):
                z = db().execute(frage, werte).fetchone()
                return (z[0] if z and z[0] is not None else 0)

            kennzahlen = {
                "seiten": len(zeilen),
                "abschnitte": eine("SELECT COUNT(*) FROM abschnitt"),
                "anhaenge": eine("SELECT COUNT(*) FROM anhang"),
                "anhaenge_b": eine("SELECT SUM(groesse_b) FROM anhang"),
                "seiten_b": eine("SELECT SUM(groesse_b) FROM seite"),
                "indexzeilen": eine("SELECT COUNT(*) FROM treffer"),
                # Reste, die einen Indexlauf zum Scheitern bringen (N-16).
                # Hier nur GEZAEHLT - aufgeraeumt wird beim Neuaufbau, damit
                # ein Blick in die Verwaltung nichts veraendert.
                "verwaiste": eine(
                    "SELECT COUNT(*) FROM suche WHERE rowid NOT IN "
                    "(SELECT id FROM treffer)"),
                "fassungen": eine("SELECT COUNT(*) FROM fassung"),
                "lesezeichen": eine("SELECT COUNT(*) FROM lesezeichen"),
            }
            return self.json_senden({"seiten": zeilen, "zweige": zweige,
                                     "pfade": pfade,
                                     "kennzahlen": kennzahlen,
                                     "gruppen": sorted(g for g in bekannt if g)})

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
            # Schreiben darf, wer in EDITOR_GRUPPE ist (N-21). Wer eine
            # BESTEHENDE Seite ersetzt, muss sie angelegt haben oder Verwalter
            # sein - das wird unten geprueft, wenn die Kennung feststeht.
            n = self.editor()
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
            # Ab hier steht die endgueltige Kennung fest: Rechte pruefen.
            self.gruppen_pruefen(teile_d["meta"], n)
            vorhanden = db().execute("SELECT * FROM seite WHERE slug=?",
                                     (teile_d["meta"]["slug"],)).fetchone()
            if vorhanden and not self.darf_schreiben(vorhanden, n):
                raise Antwort(403,
                              "Die Seite '%s' hat %s angelegt. Aendern kann "
                              "sie ihr Urheber oder ein Verwalter. Waehle eine "
                              "andere Kennung, wenn du eine eigene Seite "
                              "willst." % (teile_d["meta"]["slug"],
                                           vorhanden["nutzer_id"] or "jemand anderes"))
            seite_id, nummer, indexfehler = uebernehmen(html, teile_d, n, kommentar)
            antwort = {"ok": True, "slug": teile_d["meta"]["slug"],
                       "fassung": nummer, "geaendert": geaendert,
                       "bericht": bericht}
            if indexfehler:
                # Die Seite steht, nur die Suche kennt sie noch nicht (N-12).
                # Das gehoert gesagt - und zwar als Hinweis, nicht als Fehler.
                antwort["indexfehler"] = (
                    "Die Seite ist gespeichert, aber der Suchindex wurde nicht "
                    "gebaut (%s). Sie ist erreichbar und wird gefunden, sobald "
                    "in der Verwaltung 'Index neu' gelaufen ist." % indexfehler)
            return self.json_senden(antwort)

        if rest == ["loeschen"]:
            n = self.editor()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug = (daten.get("slug") or "").strip()
            if daten.get("bestaetigt") is not True:
                raise Antwort(400, "Ohne Bestaetigung wird nichts geloescht.")
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            if not self.darf_schreiben(z, n):
                raise Antwort(403, "Loeschen kann diese Seite ihr Urheber "
                                   "oder ein Verwalter.")
            # Erst den Index, dann die Seite (N-16): danach ist die Seite weg
            # und laesst nichts liegen, was den naechsten Indexaufbau umwirft.
            index_leeren(db(), z["id"])
            db().execute("DELETE FROM seite WHERE id=?", (z["id"],))
            db().commit()
            # Dateien bleiben liegen - Datenverlust ist die einzige echte
            # Katastrophe. Aufgeraeumt wird von Hand.
            #
            # Die Datenbank ist an dieser Stelle schon geschrieben UND
            # festgeschrieben. Scheitert das Verschieben, ist die Seite also
            # trotzdem weg - eine 500 waere dann eine Luege (N-30). Gemessen:
            # fehlender Ordner -> "Auf dem Server ist etwas schiefgegangen",
            # HTTP 500, und die Seite war aus Baum und Suche verschwunden.
            hinweis = ""
            try:
                shutil.move(seitenordner(slug),
                            os.path.join(SEITEN,
                                         f".geloescht-{slug}-{int(time.time())}"))
            except FileNotFoundError:
                hinweis = ("Die Seite ist entfernt. Einen Ordner auf der "
                           "Platte hatte sie nicht mehr - es war nichts "
                           "beiseitezulegen.")
            except OSError as fehler:
                # Der zweite Zweig ist ein Fangnetz: er greift bei allem
                # anderen, was ein Verschieben verhindern kann (Rechte, volle
                # Platte). In den Tests laesst sich das nicht ausloesen, ohne
                # das Dateisystem zu manipulieren - darum steht hier, was er
                # tut, statt so zu tun, als waere er geprueft.
                sys.stderr.write("FEHLER: Ordner von '%s' nicht verschoben: "
                                 "%s\n" % (slug, fehler))
                hinweis = ("Die Seite ist aus Themenbaum und Suche entfernt. "
                           "Ihr Ordner liess sich nicht beiseitelegen "
                           f"({fehler.__class__.__name__}) und liegt noch da, "
                           "wo er war.")
            return self.json_senden({"ok": True, "hinweis": hinweis})

        if rest == ["zuruecksetzen"]:
            n = self.editor()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug, nummer = (daten.get("slug") or "").strip(), int(daten.get("nummer") or 0)
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            if not self.darf_schreiben(z, n):
                raise Antwort(403, "Zuruecksetzen kann diese Seite ihr "
                                   "Urheber oder ein Verwalter.")
            p = os.path.join(seitenordner(slug), "fassungen", f"{nummer:04d}-seite.html")
            if not os.path.exists(p):
                raise Antwort(404, "Diese Fassung liegt nicht vor.")
            roh = open(p, "rb").read()
            bericht, html, teile_d = pruefen(roh, n)
            if bericht["fehler"]:
                raise Antwort(400, "Die alte Fassung ist nicht mehr gueltig: "
                                   + "; ".join(bericht["fehler"][:2]))
            _, neu, _ = uebernehmen(html, teile_d, n, f"zurueck auf Fassung {nummer}")
            return self.json_senden({"ok": True, "fassung": neu})

        if rest == ["rechte"]:
            # Der Verwalter steuert die Freigabe einer Seite, ohne sie neu
            # einzuspielen (N-13). Geaendert wird BEIDES: die Datenbank, die
            # ueber die Sichtbarkeit entscheidet, und der Meta-Block in der
            # Datei - sonst dreht das naechste Bearbeiten durch den Urheber
            # die Freigabe wieder zurueck.
            self.admin()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug = (daten.get("slug") or "").strip()
            gruppen = [str(g).strip() for g in (daten.get("gruppen") or []) if str(g).strip()]
            falsch = [g for g in gruppen if not g.startswith(GRUPPEN_PRAEFIX)]
            if falsch:
                raise Antwort(400,
                              "Diese Gruppen gehoeren nicht zum Wiki: %s. Nur "
                              "Gruppen, die mit '%s' anfangen, entscheiden hier "
                              "ueber Sichtbarkeit." % (", ".join(sorted(falsch)),
                                                       GRUPPEN_PRAEFIX))
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            pfad = os.path.join(seitenordner(slug), "seite.html")
            if os.path.exists(pfad):
                with open(pfad, encoding="utf-8") as f:
                    html = f.read()
                try:
                    meta, _ = meta_block_lesen(html)
                except ValueError:
                    meta = None
                if meta is not None:
                    meta["gruppen"] = gruppen
                    with open(pfad, "w", encoding="utf-8") as f:
                        f.write(meta_block_ersetzen(html, meta))
            db().execute("UPDATE seite SET gruppen_json=?, geaendert=? WHERE id=?",
                         (json.dumps(gruppen, ensure_ascii=False), jetzt(), z["id"]))
            db().commit()
            return self.json_senden({"ok": True, "gruppen": gruppen})

        if rest == ["zweig"]:
            # Nach dem Schreiben ist der Zwischenspeicher ueberholt (B-47).
            _lokal.zweige = None
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

        if rest == ["ansichtstext"]:
            # Die Seite meldet, was sie tatsaechlich anzeigt (N-11). Der
            # Server kann kein JavaScript ausfuehren; eine Seite, die ihre
            # Tabellen im Browser aufbaut, hat ihren Inhalt nirgends im HTML.
            # Darum schickt die Seite selbst ihren sichtbaren Text, sobald sie
            # geladen ist - das ist die genaue Fassung dessen, was ein Leser
            # sieht. Kein Verwalterrecht: es ist der Text einer Seite, die
            # dieser Nutzer ohnehin sehen darf, und er ersetzt nichts anderes
            # als seine eigene Indexquelle.
            n = self.nutzer()
            daten = json.loads(self.koerper_lesen() or b"{}")
            slug = (daten.get("slug") or "").strip()
            text = re.sub(r"\s+", " ", str(daten.get("text") or "")).strip()
            z = db().execute("SELECT * FROM seite WHERE slug=?", (slug,)).fetchone()
            if not z:
                raise Antwort(404, "Diese Seite gibt es nicht.")
            if not darf_sehen(n, z):
                raise Antwort(403, "Fuer diese Seite fehlt dir die Freigabe.")
            if len(text) > ANSICHT_GRENZE:
                text = text[:ANSICHT_GRENZE]
            alt_txt = db().execute(
                "SELECT text FROM ansichtstext WHERE seite_id=?", (z["id"],)).fetchone()
            if alt_txt and alt_txt["text"] == text:
                # Nichts Neues - dann auch kein Indexlauf. Sonst wuerde jeder
                # Seitenaufruf den Index neu bauen.
                return self.json_senden({"ok": True, "geaendert": False})
            db().execute("INSERT INTO ansichtstext(seite_id,text,stand) VALUES(?,?,?) "
                         "ON CONFLICT(seite_id) DO UPDATE SET text=excluded.text, "
                         "stand=excluded.stand", (z["id"], text, jetzt()))
            db().commit()
            index_neu_bauen(z["id"])
            return self.json_senden({"ok": True, "geaendert": True,
                                     "zeichen": len(text)})

        if rest == ["neuindex"]:
            self.admin()
            # Zuerst die Reste (N-16), sonst scheitert der Aufbau an ihnen -
            # und genau dieser Knopf ist der Weg, mit dem man es reparieren
            # will. Er muss also selbst reparieren koennen.
            weg = verwaiste_indexzeilen_loeschen(db())
            for z in db().execute("SELECT id FROM seite").fetchall():
                index_neu_bauen(z["id"])
            db().commit()
            return self.json_senden({"ok": True, "verwaiste": weg})

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
