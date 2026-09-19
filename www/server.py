#!/usr/bin/env python3
"""Prolo Freigabe - HTML-Seiten hosten und gezielt freigeben.

Das Werkzeug auf prolo.me. Es tut genau drei Dinge:

  1. Es nimmt eine fertige HTML-Datei entgegen und legt sie ab. Sie bleibt
     liegen, bis jemand sie loescht - ein zurueckgezogener Zugang loescht
     nichts.
  2. Es gibt zu einer Seite so viele Zugangslinks aus, wie man will. Ein
     Link je Bewerbung: mit Etikett, Zaehler, Ablaufdatum, jederzeit
     sperrbar UND wieder freischaltbar.
  3. Es zeigt eine oeffentliche Startseite, die nichts verraet.

Warum Links statt eines Passworts fuer alle: ein Link laesst sich einzeln
zurueckziehen, und man sieht an seinem Zaehler, ob er weitergereicht wurde.
Ein gemeinsames Passwort kann beides nicht.

Was ein Link NICHT ist: eine Anmeldung. Wer ihn hat, kommt hinein. Das ist
der Preis dafuer, dass eine Personalerin ohne Konto draufkommt - und der
Grund fuer Ablaufdatum, Zaehler und Widerruf.

Python-Standardbibliothek, SQLite, kein Fremdpaket (CLAUDE.md).
"""
import base64
import hashlib
import hmac
import html as htmlmod
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = "1.0.0"

EIGENER_ORDNER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.environ.get("WWW_DATEN", os.path.join(EIGENER_ORDNER, "daten"))
SEITEN = os.environ.get("WWW_SEITEN", os.path.join(EIGENER_ORDNER, "seiten"))
PORT = int(os.environ.get("WWW_PORT", "8080"))
DB_PFAD = os.path.join(DATEN, "www.db")

# Wer die Verwaltung oeffnen darf. Die Gruppe kommt von Authentik; das
# Werkzeug wertet nur seine eigenen aus (§17).
ADMIN_GRUPPE = os.environ.get("WWW_ADMIN_GRUPPE", "stack-admin")

GRENZE_UPLOAD_B = int(os.environ.get("WWW_MAX_UPLOAD_B", str(20 * 1024 * 1024)))
GRENZE_ETIKETT = 120
GRENZE_TITEL = 120
# Nach so vielen Fehlversuchen von derselben Quelle ist eine Stunde Ruhe.
# Die Ratenbremse in Traefik bremst die Geschwindigkeit, diese Sperre die
# Anzahl - gegen Raten hilft nur beides zusammen.
GRENZE_VERSUCHE = 10
SPERRE_S = 3600
# Wie lange ein Einlass gilt, nachdem der Link einmal gestimmt hat.
KEKS_DAUER_S = 12 * 3600

# --------------------------------------------------- Die Vertrauensgrenze
#
# Wie in Wiki und Bordbuch (N-44): die Identitaet kommt als Kopfzeile von
# Traefik, und ein Werkzeug sieht nicht, WOHER eine Anfrage kam. Ohne die
# Marke, die nur der Zugang kennt, antwortet dieses Werkzeug gar nicht -
# auch nicht auf die oeffentlichen Pfade.
EINLASS_KOPF = "X-Prolo-Einlass"
EINLASS = os.environ.get("PROLO_EINLASS", "")
EINLASS_B = EINLASS.encode("utf-8")
EINLASS_FREI = ("/gesundheit", "/api/version")


def keks_schluessel():
    """Der Schluessel fuer die Sitzungsplaetzchen.

    Abgeleitet aus der Einlassmarke mit einem eigenen Namensraum, statt
    ein zweites Geheimnis zu verwalten. Der Namensraum ist wichtig: ohne
    ihn waere ein Plaetzchen und die Marke derselbe Wert, und wer eines
    haette, haette beides. Wird die Marke gewechselt, laufen alle
    Sitzungen ab - das ist gewollt.
    """
    return hmac.new(EINLASS_B, b"prolo-www-keks-v1", hashlib.sha256).digest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS seite (
  id           INTEGER PRIMARY KEY,
  kennung      TEXT NOT NULL UNIQUE,
  titel        TEXT NOT NULL,
  datei        TEXT NOT NULL,
  groesse_b    INTEGER NOT NULL,
  hochgeladen  TEXT NOT NULL,
  nutzer_id    TEXT NOT NULL,
  geloescht    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS freigabe (
  id            INTEGER PRIMARY KEY,
  seite_id      INTEGER NOT NULL REFERENCES seite(id),
  marke_abdruck TEXT NOT NULL UNIQUE,
  etikett       TEXT NOT NULL,
  angelegt      TEXT NOT NULL,
  laeuft_ab     TEXT,
  zustand       TEXT NOT NULL DEFAULT 'aktiv',
  passwort_hash TEXT,
  passwort_salz TEXT,
  aufrufe       INTEGER NOT NULL DEFAULT 0,
  zuletzt       TEXT,
  nutzer_id     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS freigabe_seite ON freigabe(seite_id);
CREATE TABLE IF NOT EXISTS fehlversuch (
  id     INTEGER PRIMARY KEY,
  quelle TEXT NOT NULL,
  wann   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS fehlversuch_quelle ON fehlversuch(quelle, wann);
"""

_lokal = threading.local()


def db():
    if getattr(_lokal, "con", None) is None:
        _lokal.con = sqlite3.connect(DB_PFAD, timeout=10)
        _lokal.con.row_factory = sqlite3.Row
        _lokal.con.execute("PRAGMA journal_mode=WAL")
        _lokal.con.execute("PRAGMA foreign_keys=ON")
    return _lokal.con


def datenbank_anlegen():
    os.makedirs(DATEN, exist_ok=True)
    os.makedirs(SEITEN, exist_ok=True)
    con = sqlite3.connect(DB_PFAD)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def jetzt():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Antwort(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code, self.text = code, text


# ---------------------------------------------------------------- Pruefen

KENNUNG_MUSTER = re.compile(r"^[a-z0-9][a-z0-9-]{0,58}[a-z0-9]$")


def kennung_bauen(titel, vorhanden):
    """Aus dem Titel eine Adresse machen - ohne Umlaute, ohne Kollision."""
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
              "Ä": "ae", "Ö": "oe", "Ü": "ue"}
    s = "".join(ersatz.get(z, z) for z in (titel or "")).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:50] or "seite"
    if not KENNUNG_MUSTER.match(s):
        s = "seite"
    kandidat, n = s, 2
    while kandidat in vorhanden:
        kandidat = "%s-%d" % (s, n)
        n += 1
    return kandidat


def html_pruefen(roh):
    """Was hochgeladen wird, ist Code aus fremder Quelle (CLAUDE.md §11).

    Geprueft wird hier nur, ob es ueberhaupt eine HTML-Seite ist und ob sie
    in die Grenzen passt. Was sie TUT, wird nicht geprueft - sie laeuft in
    einem abgeschotteten Rahmen mit eigenem, opakem Origin, genau wie eine
    Wiki-Seite. Darum steht auf der Verwaltungsseite auch, dass man nur
    einspielen soll, was man kennt.
    """
    if len(roh) > GRENZE_UPLOAD_B:
        raise Antwort(400, "Die Datei ist %s gross, erlaubt sind %s."
                      % (bytes_lesbar(len(roh)), bytes_lesbar(GRENZE_UPLOAD_B)))
    if not roh.strip():
        raise Antwort(400, "Die Datei ist leer.")
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        raise Antwort(400, "Die Datei ist nicht UTF-8 kodiert. "
                           "Bitte als UTF-8 speichern und noch einmal hochladen.")
    if not re.search(r"(?i)<html|<body|<!doctype", text):
        raise Antwort(400, "Das sieht nicht nach einer HTML-Seite aus - weder "
                           "<!doctype noch <html noch <body kommen darin vor.")
    return text


def titel_aus(text, ersatz):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    t = re.sub(r"\s+", " ", htmlmod.unescape(m.group(1))).strip() if m else ""
    return (t or ersatz)[:GRENZE_TITEL]


def bytes_lesbar(n):
    if n < 1024:
        return "%d Byte" % n
    if n < 1024 * 1024:
        return ("%.1f kB" % (n / 1024)).replace(".", ",")
    return ("%.1f MB" % (n / 1024 / 1024)).replace(".", ",")


# ------------------------------------------------------------- Freigaben

def marke_neu():
    """Ein Zugangslink. 24 Byte = 192 Bit aus secrets, nicht aus random.

    Nicht zu erraten: selbst mit einer Milliarde Versuchen je Sekunde und
    dem Alter des Universums bleibt die Trefferwahrscheinlichkeit
    verschwindend. Die Sperre nach Fehlversuchen weiter unten macht das
    Raten zusaetzlich sinnlos.
    """
    return secrets.token_urlsafe(24)


def abdruck(marke):
    """Gespeichert wird NUR der Abdruck, nie die Marke selbst.

    Eine gestohlene Datenbank ergibt damit keine funktionierenden Links.
    Der Preis: eine einmal ausgegebene Marke laesst sich nicht noch einmal
    anzeigen - genau darum steht sie beim Anlegen einmal gross da.
    """
    return hashlib.sha256(marke.encode("utf-8")).hexdigest()


def passwort_ablegen(passwort):
    salz = secrets.token_bytes(16)
    h = hashlib.scrypt(passwort.encode("utf-8"), salt=salz,
                       n=2 ** 14, r=8, p=1, dklen=32)
    return h.hex(), salz.hex()


def passwort_stimmt(passwort, hash_hex, salz_hex):
    if not hash_hex or not salz_hex:
        return False
    h = hashlib.scrypt(passwort.encode("utf-8"), salt=bytes.fromhex(salz_hex),
                       n=2 ** 14, r=8, p=1, dklen=32)
    return hmac.compare_digest(h.hex(), hash_hex)


def gesperrt(quelle):
    """Zu viele Fehlversuche von derselben Quelle?

    Das commit() nach dem Aufraeumen ist Pflicht und kein Schoenheitsfehler:
    ohne es bleibt die Schreibsperre auf der Datenbank offen, und der
    naechste schreibende Aufruf aus einem anderen Faden laeuft in
    "database is locked" - nach zehn Sekunden Wartezeit, als 500. Genau so
    ist es beim ersten Testlauf passiert; das Signal war, dass ein Test
    ploetzlich zehn Sekunden brauchte.
    """
    grenze = time.time() - SPERRE_S
    db().execute("DELETE FROM fehlversuch WHERE wann < ?", (grenze,))
    db().commit()
    n = db().execute("SELECT COUNT(*) AS n FROM fehlversuch WHERE quelle=? AND wann>=?",
                     (quelle, grenze)).fetchone()["n"]
    return n >= GRENZE_VERSUCHE


def fehlversuch_merken(quelle):
    db().execute("INSERT INTO fehlversuch(quelle, wann) VALUES(?,?)",
                 (quelle, time.time()))
    db().commit()


def freigabe_lage(z):
    """'aktiv', 'gesperrt' oder 'abgelaufen' - in dieser Reihenfolge.

    Gesperrt schlaegt abgelaufen: was zurueckgezogen wurde, bleibt
    zurueckgezogen, auch wenn man das Ablaufdatum verschiebt.
    """
    if z["zustand"] != "aktiv":
        return "gesperrt"
    if z["laeuft_ab"] and z["laeuft_ab"] < jetzt():
        return "abgelaufen"
    return "aktiv"


# ----------------------------------------------------------- Plaetzchen

def keks_backen(freigabe_id):
    bis = int(time.time()) + KEKS_DAUER_S
    nutz = "%d.%d" % (freigabe_id, bis)
    sig = hmac.new(keks_schluessel(), nutz.encode(), hashlib.sha256).digest()
    return nutz + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def keks_lesen(wert):
    """Die Freigabe-Nummer aus einem Plaetzchen - oder None.

    Geprueft wird die Signatur, nicht der Inhalt: ein Plaetzchen kommt vom
    Browser und ist damit eine Eingabe von aussen (§11).
    """
    if not wert or wert.count(".") != 2:
        return None
    nutz, _, sig = wert.rpartition(".")
    erwartet = hmac.new(keks_schluessel(), nutz.encode(), hashlib.sha256).digest()
    erwartet_b64 = base64.urlsafe_b64encode(erwartet).decode().rstrip("=")
    if not hmac.compare_digest(sig, erwartet_b64):
        return None
    try:
        nummer, bis = nutz.split(".")
        if int(bis) < time.time():
            return None
        return int(nummer)
    except ValueError:
        return None


# ----------------------------------------------------------- Der Dienst

class Handler(BaseHTTPRequestHandler):
    server_version = "prolo-www"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -------------------------------------------------- Werkzeug
    def log_message(self, format, *args):
        # Kein vollstaendiger Kopf ins Protokoll (§22).
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(),
                                        format % args))

    def senden(self, code, koerper, typ="text/html; charset=utf-8", extra=None):
        if isinstance(koerper, str):
            koerper = koerper.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        # Nichts von hier gehoert in eine Suchmaschine.
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def json_senden(self, daten, code=200):
        self.senden(code, json.dumps(daten, ensure_ascii=False),
                    "application/json; charset=utf-8")

    def fehler(self, code, text):
        if self.path.startswith("/api/"):
            return self.json_senden({"fehler": text}, code)
        self.senden(code, seite_meldung(code, text))

    def koerper_lesen(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > GRENZE_UPLOAD_B:
            raise Antwort(413, "Die Datei ist zu gross.")
        teile, rest = [], n
        while rest > 0:
            block = self.rfile.read(min(rest, 65536))
            if not block:
                self.close_connection = True
                raise Antwort(400, "Die Datei kam nur unvollstaendig an. "
                                   "Bitte noch einmal hochladen.")
            teile.append(block)
            rest -= len(block)
        return b"".join(teile)

    def quelle(self):
        """Die Adresse des Aufrufers - fuer die Sperre nach Fehlversuchen.

        Genommen wird der LETZTE Eintrag aus X-Forwarded-For, nicht der
        erste. Das ist der entscheidende Unterschied: ein Proxy HAENGT
        seinen Eintrag hinten an. Was davor steht, hat der Aufrufer
        mitgeschickt und ist frei erfunden.

        Erst stand hier der erste Eintrag. Damit haette ein Angreifer die
        Sperre unterlaufen, indem er bei jedem Versuch eine andere Adresse
        vorne anstellt - die Sperre haette nur noch Tippfehler gebremst.
        Aufgefallen ist es, weil zwei Tests derselben Klasse sich die
        Sperre teilten und ich sie ueber diese Kopfzeile trennen wollte.

        Der TCP-Absender allein taugt nicht: das waere immer Traefik, und
        dann teilten sich alle Aufrufer eine einzige Sperre.
        """
        ff = [t.strip() for t in
              (self.headers.get("X-Forwarded-For") or "").split(",") if t.strip()]
        return (ff[-1] if ff else self.client_address[0])[:64]

    def keks(self, name):
        roh = self.headers.get("Cookie") or ""
        for teil in roh.split(";"):
            k, _, v = teil.strip().partition("=")
            if k == name:
                return v
        return None

    # -------------------------------------------------- Die zwei Grenzen
    def einlass_pruefen(self):
        """Kam die Anfrage ueber den Zugang dieses Servers? (N-44)"""
        if urlparse(self.path).path in EINLASS_FREI:
            return
        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")
        if hmac.compare_digest(mit, EINLASS_B):
            return
        raise Antwort(401, "Diese Anfrage kam nicht ueber den Zugang dieses "
                           "Servers.")

    def verwalter(self):
        """Der angemeldete Nutzer, wenn er die Verwaltung oeffnen darf.

        Zwei Tueren (§17): Authentik laesst aufs Grundstueck, diese Pruefung
        ins Haus. Beide unabhaengig - der oeffentliche Router dieses
        Werkzeugs hat KEIN authentik@file, also waere eine Kopfzeile allein
        hier kein Nachweis.
        """
        kennung = (self.headers.get("X-Authentik-Username") or "").strip()
        if not kennung:
            raise Antwort(401, "Nicht angemeldet. Die Verwaltung liegt hinter "
                               "der Anmeldung.")
        roh = self.headers.get("X-Authentik-Groups") or ""
        gruppen = {g.strip() for g in re.split(r"[,|;]", roh) if g.strip()}
        if ADMIN_GRUPPE not in gruppen:
            raise Antwort(403, "Dafuer braucht es die Gruppe '%s'." % ADMIN_GRUPPE)
        return kennung

    # -------------------------------------------------- Verteilung
    def do_GET(self):
        self._lauf(self.verteilen_get, "GET")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._lauf(self.verteilen_post, "POST")

    def _lauf(self, was, name):
        try:
            self.einlass_pruefen()
            was()
        except Antwort as a:
            self.fehler(a.code, a.text)
        except BrokenPipeError:
            pass
        except Exception as e:
            self.close_connection = True
            kennung = "%05d" % (int(time.time()) % 100000)
            sys.stderr.write("FEHLER %s %s [%s]: %s: %s\n"
                             % (name, self.path, kennung, type(e).__name__, e))
            traceback.print_exc(file=sys.stderr)
            # Kein interner Pfad, kein Datenbankfehler im Original (§22).
            self.fehler(500, "Auf dem Server ist etwas schiefgegangen "
                             "(Kennung %s). Die Einzelheiten stehen im "
                             "Protokoll des Containers." % kennung)

    # -------------------------------------------------- GET
    def verteilen_get(self):
        u = urlparse(self.path)
        pfad = u.path
        teile = [t for t in pfad.split("/") if t]

        if pfad == "/gesundheit":
            return self.senden(200, "ok\n", "text/plain; charset=utf-8")
        if pfad == "/api/version":
            return self.json_senden({"version": VERSION})

        if pfad == "/":
            return self.senden(200, seite_start())
        if pfad == "/favicon.ico":
            # Ohne diese Zeile holt sich JEDER Seitenaufruf ein 404 - im
            # Tab steht das Standardsymbol, und im Protokoll steht eine
            # Zeile, die nichts bedeutet. Genau das ist im Wiki offen
            # (N-42); hier faengt es gar nicht erst an.
            return self.senden(200, SYMBOL, "image/svg+xml",
                               {"Cache-Control": "public, max-age=86400"})
        if pfad == "/robots.txt":
            # Was hier liegt, gehoert in keine Suchmaschine - auch die
            # Startseite nicht, solange sie nur ein Schild ist.
            return self.senden(200, "User-agent: *\nDisallow: /\n",
                               "text/plain; charset=utf-8")

        if len(teile) == 2 and teile[0] == "schriften":
            return self.schrift_senden(teile[1])

        # Der Zugangslink. Die Marke steht genau einmal in der Adresse;
        # danach wird auf einen sauberen Pfad umgeleitet (siehe einlass()).
        if len(teile) == 2 and teile[0] == "z":
            return self.einlass(teile[1])

        if len(teile) == 2 and teile[0] == "s":
            return self.freigegebene_seite(teile[1])

        if pfad == "/verwaltung":
            self.verwalter()
            return self.senden(200, seite_verwaltung())
        if pfad == "/api/verwaltung":
            return self.json_senden(verwaltung_daten(self.verwalter()))

        raise Antwort(404, "Diese Adresse gibt es hier nicht.")

    def schrift_senden(self, name):
        if not re.match(r"^[a-z0-9-]+\.(woff2|txt|md)$", name):
            raise Antwort(404, "Diese Datei gibt es nicht.")
        p = os.path.join(EIGENER_ORDNER, "schriften", name)
        if not os.path.exists(p):
            raise Antwort(404, "Diese Datei gibt es nicht.")
        typ = ("font/woff2" if name.endswith(".woff2")
               else "text/plain; charset=utf-8")
        with open(p, "rb") as f:
            self.senden(200, f.read(), typ,
                        {"Cache-Control": "public, max-age=31536000, immutable"})

    # -------------------------------------------------- Der Einlass
    def einlass(self, marke):
        """Ein Zugangslink wird eingeloest.

        Danach steht die Marke NICHT mehr in der Adresszeile: der Server
        setzt ein signiertes Plaetzchen und leitet auf /s/<kennung> um. So
        landet sie nicht im Verlauf, nicht in einem Lesezeichen und nicht
        auf einem Bildschirmfoto.

        Im Traefik-Zugriffsprotokoll steht sie einmal - das laesst sich von
        hier aus nicht verhindern. Die Datei gehoert root, und ein Link
        laeuft ab und ist widerrufbar; der Rest steht im HINWEIS der
        sicherung.conf.
        """
        q = self.quelle()
        if gesperrt(q):
            raise Antwort(429, "Zu viele Fehlversuche. Bitte in einer Stunde "
                               "noch einmal versuchen.")
        z = db().execute(
            "SELECT f.*, s.kennung AS s_kennung, s.geloescht AS s_geloescht "
            "FROM freigabe f JOIN seite s ON s.id = f.seite_id "
            "WHERE f.marke_abdruck = ?", (abdruck(marke),)).fetchone()
        if z is None or z["s_geloescht"]:
            fehlversuch_merken(q)
            raise Antwort(404, "Diesen Zugang gibt es nicht. Vielleicht wurde "
                               "der Link zurueckgezogen.")
        lage = freigabe_lage(z)
        if lage == "gesperrt":
            raise Antwort(403, "Dieser Zugang wurde zurueckgezogen.")
        if lage == "abgelaufen":
            raise Antwort(403, "Dieser Zugang ist abgelaufen.")

        if z["passwort_hash"]:
            # Mit Passwort geht es erst nach dem Formular weiter. Die Marke
            # wandert dafuer in ein kurzlebiges Feld im Formular, nicht in
            # die Adresse.
            return self.senden(200, seite_passwort(marke, ""))
        return self.einlass_gewaehren(z)

    def einlass_gewaehren(self, z):
        db().execute("UPDATE freigabe SET aufrufe = aufrufe + 1, zuletzt = ? "
                     "WHERE id = ?", (jetzt(), z["id"]))
        db().commit()
        keks = keks_backen(z["id"])
        self.send_response(302)
        self.send_header("Location", "/s/" + z["s_kennung"])
        self.send_header("Set-Cookie",
                         "prolo_einlass=%s; Path=/; Max-Age=%d; HttpOnly; "
                         "Secure; SameSite=Lax" % (keks, KEKS_DAUER_S))
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def freigegebene_seite(self, kennung):
        """Die Seite selbst - nur mit gueltigem Plaetzchen."""
        nummer = keks_lesen(self.keks("prolo_einlass"))
        if nummer is None:
            raise Antwort(403, "Dieser Seite fehlt dein Zugang. Ruf den Link "
                               "auf, den du bekommen hast.")
        z = db().execute(
            "SELECT f.*, s.kennung AS s_kennung, s.datei AS s_datei, "
            "       s.geloescht AS s_geloescht "
            "FROM freigabe f JOIN seite s ON s.id = f.seite_id "
            "WHERE f.id = ?", (nummer,)).fetchone()
        if z is None or z["s_geloescht"] or z["s_kennung"] != kennung:
            raise Antwort(403, "Dieser Zugang gilt nicht fuer diese Seite.")
        if freigabe_lage(z) != "aktiv":
            raise Antwort(403, "Dieser Zugang gilt nicht mehr.")
        p = os.path.join(SEITEN, z["s_datei"])
        if not os.path.exists(p):
            raise Antwort(404, "Die Seite ist nicht mehr da.")
        with open(p, "rb") as f:
            self.senden(200, f.read(), "text/html; charset=utf-8", {
                # Eine hochgeladene Seite ist fremder Code. Sie laeuft ohne
                # Verbindung nach draussen und darf nichts nachladen.
                "Content-Security-Policy":
                    "default-src 'none'; img-src 'self' data:; "
                    "style-src 'self' 'unsafe-inline'; font-src 'self'; "
                    "script-src 'unsafe-inline'; form-action 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'",
                "Cache-Control": "private, no-store",
            })

    # -------------------------------------------------- POST
    def verteilen_post(self):
        pfad = urlparse(self.path).path
        teile = [t for t in pfad.split("/") if t]

        # Das Passwortformular eines Zugangslinks. Oeffentlich, ohne
        # Anmeldung - es aendert nichts ausser dem eigenen Plaetzchen.
        if len(teile) == 2 and teile[0] == "z":
            return self.passwort_pruefen(teile[1])

        if not pfad.startswith("/api/"):
            raise Antwort(404, "Diese Adresse gibt es hier nicht.")

        # Der Riegel gegen Formularangriffe von fremden Seiten: ein
        # gewoehnliches HTML-Formular kann Sec-Fetch-Site nicht faelschen,
        # und "cross-site" wird hier abgewiesen.
        herkunft = self.headers.get("Sec-Fetch-Site")
        if herkunft and herkunft not in ("same-origin", "none"):
            raise Antwort(403, "Diese Anfrage kam von einer fremden Seite.")

        nutzer = self.verwalter()
        if pfad == "/api/hochladen":
            return self.hochladen(nutzer)

        daten = json.loads(self.koerper_lesen() or b"{}")
        if pfad == "/api/freigabe":
            return self.freigabe_anlegen(nutzer, daten)
        if pfad == "/api/zustand":
            return self.zustand_setzen(nutzer, daten)
        if pfad == "/api/passwort":
            return self.passwort_setzen(nutzer, daten)
        if pfad == "/api/loeschen":
            return self.seite_loeschen(nutzer, daten)
        raise Antwort(404, "Unbekannter Aufruf.")

    def passwort_pruefen(self, marke):
        q = self.quelle()
        if gesperrt(q):
            raise Antwort(429, "Zu viele Fehlversuche. Bitte in einer Stunde "
                               "noch einmal versuchen.")
        roh = self.koerper_lesen().decode("utf-8", "replace")
        passwort = parse_qs(roh).get("passwort", [""])[0]
        z = db().execute(
            "SELECT f.*, s.kennung AS s_kennung, s.geloescht AS s_geloescht "
            "FROM freigabe f JOIN seite s ON s.id = f.seite_id "
            "WHERE f.marke_abdruck = ?", (abdruck(marke),)).fetchone()
        if z is None or z["s_geloescht"] or freigabe_lage(z) != "aktiv":
            fehlversuch_merken(q)
            raise Antwort(404, "Diesen Zugang gibt es nicht.")
        if not passwort_stimmt(passwort, z["passwort_hash"], z["passwort_salz"]):
            fehlversuch_merken(q)
            return self.senden(200, seite_passwort(
                marke, "Das Passwort stimmt nicht. Es steht in der Nachricht, "
                       "mit der du den Link bekommen hast."))
        return self.einlass_gewaehren(z)

    def hochladen(self, nutzer):
        roh = self.koerper_lesen()
        text = html_pruefen(roh)
        wunsch = parse_qs(urlparse(self.path).query).get("titel", [""])[0].strip()
        titel = (wunsch or titel_aus(text, "Ohne Titel"))[:GRENZE_TITEL]
        vorhanden = {z["kennung"] for z in
                     db().execute("SELECT kennung FROM seite").fetchall()}
        kennung = kennung_bauen(titel, vorhanden)
        datei = kennung + ".html"
        # Erst die Datei, dann die Zeile: eine Zeile ohne Datei waere ein
        # Eintrag, der ins Leere zeigt (§12).
        with open(os.path.join(SEITEN, datei), "wb") as f:
            f.write(roh)
        db().execute(
            "INSERT INTO seite(kennung,titel,datei,groesse_b,hochgeladen,nutzer_id)"
            " VALUES(?,?,?,?,?,?)",
            (kennung, titel, datei, len(roh), jetzt(), nutzer))
        db().commit()
        return self.json_senden({"ok": True, "kennung": kennung, "titel": titel,
                                 "groesse_b": len(roh)})

    def freigabe_anlegen(self, nutzer, daten):
        kennung = (daten.get("kennung") or "").strip()
        etikett = (daten.get("etikett") or "").strip()[:GRENZE_ETIKETT]
        tage = daten.get("tage")
        if not etikett:
            raise Antwort(400, "Der Freigabe fehlt ein Etikett. Schreib hin, "
                               "wofuer der Link ist - spaeter weisst du sonst "
                               "nicht, welchen du zurueckziehen sollst.")
        s = db().execute("SELECT * FROM seite WHERE kennung=? AND geloescht=0",
                         (kennung,)).fetchone()
        if s is None:
            raise Antwort(404, "Diese Seite gibt es nicht.")
        laeuft_ab = None
        if tage not in (None, "", 0):
            try:
                n = int(tage)
            except (TypeError, ValueError):
                raise Antwort(400, "Die Laufzeit muss eine Zahl von Tagen sein.")
            if not 1 <= n <= 3650:
                raise Antwort(400, "Die Laufzeit muss zwischen 1 und 3650 Tagen "
                                   "liegen.")
            laeuft_ab = (datetime.now(timezone.utc)
                         + timedelta(days=n)).isoformat(timespec="seconds")
        marke = marke_neu()
        db().execute(
            "INSERT INTO freigabe(seite_id,marke_abdruck,etikett,angelegt,"
            "laeuft_ab,nutzer_id) VALUES(?,?,?,?,?,?)",
            (s["id"], abdruck(marke), etikett, jetzt(), laeuft_ab, nutzer))
        db().commit()
        # Die Marke steht hier EINMAL. Gespeichert ist nur ihr Abdruck -
        # noch einmal anzeigen kann sie niemand, auch ich nicht.
        return self.json_senden({"ok": True, "marke": marke,
                                 "laeuft_ab": laeuft_ab})

    def zustand_setzen(self, nutzer, daten):
        nummer = daten.get("id")
        zustand = (daten.get("zustand") or "").strip()
        if zustand not in ("aktiv", "gesperrt"):
            raise Antwort(400, "Der Zustand ist entweder 'aktiv' oder "
                               "'gesperrt'.")
        z = db().execute("SELECT * FROM freigabe WHERE id=?", (nummer,)).fetchone()
        if z is None:
            raise Antwort(404, "Diese Freigabe gibt es nicht.")
        db().execute("UPDATE freigabe SET zustand=? WHERE id=?", (zustand, nummer))
        db().commit()
        # Zurueckziehen loescht nichts: derselbe Link laesst sich wieder
        # freischalten. Das war ausdruecklich gewuenscht.
        return self.json_senden({"ok": True, "zustand": zustand})

    def passwort_setzen(self, nutzer, daten):
        nummer = daten.get("id")
        passwort = daten.get("passwort")
        z = db().execute("SELECT * FROM freigabe WHERE id=?", (nummer,)).fetchone()
        if z is None:
            raise Antwort(404, "Diese Freigabe gibt es nicht.")
        if passwort in (None, ""):
            db().execute("UPDATE freigabe SET passwort_hash=NULL, "
                         "passwort_salz=NULL WHERE id=?", (nummer,))
            db().commit()
            return self.json_senden({"ok": True, "passwort": False})
        if len(passwort) < 8:
            raise Antwort(400, "Das Passwort ist zu kurz - mindestens acht "
                               "Zeichen.")
        h, salz = passwort_ablegen(passwort)
        db().execute("UPDATE freigabe SET passwort_hash=?, passwort_salz=? "
                     "WHERE id=?", (h, salz, nummer))
        db().commit()
        return self.json_senden({"ok": True, "passwort": True})

    def seite_loeschen(self, nutzer, daten):
        kennung = (daten.get("kennung") or "").strip()
        if not daten.get("bestaetigt"):
            raise Antwort(400, "Zum Loeschen fehlt die Bestaetigung.")
        s = db().execute("SELECT * FROM seite WHERE kennung=?",
                         (kennung,)).fetchone()
        if s is None:
            raise Antwort(404, "Diese Seite gibt es nicht.")
        # Erst als geloescht markieren, die Datei bleibt liegen (§15). Wer
        # sie wirklich los sein will, loescht sie auf dem Server - dann ist
        # sie weg und nicht vorher aus Versehen.
        db().execute("UPDATE seite SET geloescht=1 WHERE id=?", (s["id"],))
        db().execute("UPDATE freigabe SET zustand='gesperrt' WHERE seite_id=?",
                     (s["id"],))
        db().commit()
        return self.json_senden({"ok": True})


# ------------------------------------------------------------ Oberflaeche

def schuetzen(s):
    return htmlmod.escape(str(s if s is not None else ""), quote=True)


# Die Farbtoken aus CLAUDE.md §2. Einmal je Seite, Umschaltung ueber
# data-theme am Koerper. Kein Farbwert steht ausserhalb dieses Blocks.
TOKEN = """
:root{
  --bg:oklch(0.96 0.004 250); --app:oklch(0.985 0.002 250); --surface:#fff;
  --chrome:oklch(0.995 0.001 250); --line:oklch(0.92 0.004 250);
  --line-soft:oklch(0.96 0.002 250); --hover:oklch(0.96 0.003 250);
  --ink:oklch(0.2 0.01 250); --ink-2:oklch(0.3 0.01 250); --ink-3:oklch(0.52 0.01 250);
  --accent:oklch(0.52 0.17 262); --accent-hover:oklch(0.45 0.17 262);
  --accent-soft:oklch(0.94 0.02 262); --accent-ink:oklch(0.38 0.13 262);
  --on-accent:oklch(0.99 0.002 250); --bar:oklch(0.86 0.03 262);
  --good:oklch(0.45 0.14 158); --good-soft:oklch(0.97 0.01 158);
  --warm-soft:oklch(0.94 0.01 60); --warm-ink:oklch(0.45 0.08 60);
  --danger:oklch(0.52 0.18 25); --overlay:oklch(0.28 0.02 258);
  --feature:oklch(0.34 0.12 262); --feature-ink:oklch(0.99 0.002 250);
  --feature-ink-2:oklch(0.86 0.03 262); --feature-line:oklch(0.46 0.11 262);
  --track:oklch(0.94 0.004 250);
  --shadow:0 24px 60px -20px oklch(0.4 0.03 250 / 0.22);
}
body[data-theme="dark"]{
  --bg:oklch(0.16 0.012 258); --app:oklch(0.2 0.012 258);
  --surface:oklch(0.235 0.013 258); --chrome:oklch(0.205 0.012 258);
  --line:oklch(0.31 0.014 258); --line-soft:oklch(0.27 0.012 258);
  --hover:oklch(0.27 0.013 258);
  --ink:oklch(0.96 0.004 250); --ink-2:oklch(0.87 0.006 250); --ink-3:oklch(0.69 0.01 250);
  --accent:oklch(0.62 0.16 262); --accent-hover:oklch(0.69 0.16 262);
  --accent-soft:oklch(0.33 0.06 262); --accent-ink:oklch(0.85 0.09 262);
  --bar:oklch(0.38 0.06 262); --on-accent:oklch(0.16 0.012 258);
  --good:oklch(0.8 0.14 158); --good-soft:oklch(0.29 0.05 158);
  --warm-soft:oklch(0.33 0.05 60); --warm-ink:oklch(0.86 0.08 60);
  --danger:oklch(0.7 0.16 25); --overlay:oklch(0.2 0.012 258);
  --feature:oklch(0.31 0.07 262); --feature-ink:oklch(0.97 0.004 250);
  --feature-ink-2:oklch(0.8 0.02 250); --feature-line:oklch(0.42 0.05 262);
  --track:oklch(0.3 0.014 258);
  --shadow:0 24px 60px -20px oklch(0.05 0 0 / 0.6);
}
"""

SCHRIFT = """
@font-face{font-family:Sora;src:url(/schriften/sora-latin.woff2) format('woff2');
  font-weight:600;font-display:swap;unicode-range:U+0000-00FF,U+2000-206F}
@font-face{font-family:'Instrument Sans';src:url(/schriften/instrument-latin.woff2) format('woff2');
  font-weight:400 600;font-display:swap;unicode-range:U+0000-00FF,U+2000-206F}
@font-face{font-family:'JetBrains Mono';src:url(/schriften/jetbrains-latin.woff2) format('woff2');
  font-weight:400 500;font-display:swap;unicode-range:U+0000-00FF,U+2000-206F}
"""

# Der Pflichtblock aus §8.1. [hidden] steht VOR allen display-Regeln,
# sonst bleibt ein verstecktes Element sichtbar.
PFLICHT_CSS = """
[hidden]{display:none!important}
button:focus-visible, a:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible, label:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }
"""

GRUND_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink-2);
  font-family:'Instrument Sans',system-ui,sans-serif;font-size:14px;line-height:1.55}
h1,h2,h3,.zahl{font-family:Sora,'Instrument Sans',sans-serif;font-weight:600;
  color:var(--ink);letter-spacing:-0.02em;margin:0}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
.mitte{max-width:1280px;margin:0 auto;padding:32px 20px}
.marke{display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit}
.marke b{width:30px;height:30px;border-radius:8px;background:var(--accent);
  color:var(--on-accent);display:grid;place-items:center;font-family:Sora;font-size:16px}
.marke span{font-family:Sora;font-size:14px;color:var(--ink)}
.marke small{display:block;font-family:'JetBrains Mono',monospace;font-size:10px;
  letter-spacing:0.06em;text-transform:uppercase;color:var(--ink-3)}
.karte{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px;min-width:0}
.knopf{display:inline-flex;align-items:center;justify-content:center;gap:7px;
  min-height:44px;padding:0 16px;border:0;border-radius:10px;background:var(--accent);
  color:var(--on-accent);font:600 14px 'Instrument Sans',sans-serif;cursor:pointer}
.knopf:hover{background:var(--accent-hover)}
.knopf[disabled]{opacity:.5;cursor:not-allowed}
.knopf.rahmen{background:transparent;color:var(--ink-2);border:1px solid var(--line)}
.knopf.rahmen:hover{background:var(--hover);color:var(--ink)}
.knopf.gefahr{background:transparent;color:var(--ink-2);border:1px solid var(--line)}
.knopf.gefahr:hover{border-color:var(--danger);color:var(--danger)}
input[type=text],input[type=password],input[type=number]{width:100%;min-height:44px;
  padding:0 12px;border:1px solid var(--line);border-radius:10px;background:var(--surface);
  color:var(--ink);font:400 14px 'Instrument Sans',sans-serif}
.label{display:block;font-size:12px;color:var(--ink-3);margin-bottom:4px}
.kontext{font-size:12px;color:var(--ink-3)}
.meldung{border:1px solid var(--line);border-left-width:4px;border-radius:10px;
  padding:12px 14px;background:var(--surface);margin:14px 0}
.meldung.warn{border-left-color:var(--warm-ink);background:var(--warm-soft);color:var(--warm-ink)}
.meldung.fehler{border-left-color:var(--danger);color:var(--danger)}
.meldung.gut{border-left-color:var(--good);background:var(--good-soft);color:var(--good)}
table{width:100%;border-collapse:collapse}
th{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.06em;
  text-transform:uppercase;color:var(--ink-3);text-align:left;font-weight:500;
  padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:10px;border-bottom:1px solid var(--line-soft);font-size:13px;vertical-align:top}
tr:hover td{background:var(--hover)}
.badge{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;font-weight:600}
.badge.aktiv{background:var(--good-soft);color:var(--good)}
.badge.gesperrt{background:var(--warm-soft);color:var(--warm-ink)}
.zahlen{text-align:right;font-family:'JetBrains Mono',monospace}
@media (max-width:640px){ .mitte{padding:20px 16px} th,td{padding:8px 6px} }
"""


def huelle(titel, inhalt, kopf=""):
    return ("<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"robots\" content=\"noindex, nofollow\">\n"
            "<link rel=\"icon\" href=\"/favicon.ico\" type=\"image/svg+xml\">\n"
            "<title>%s</title>\n<style>%s%s%s%s</style>\n%s</head>\n"
            "<body data-theme=\"dark\">\n%s\n</body>\n</html>\n"
            % (schuetzen(titel), TOKEN, SCHRIFT, PFLICHT_CSS, GRUND_CSS,
               kopf, inhalt))


# Die Werkzeug-Marke als Symbol fuer den Tab: ein Grossbuchstabe auf
# --accent, wie die Kachel oben links (§5). Die Farbe steht hier als Wert
# und nicht als Token, weil ein SVG als eigene Datei die Tokens der Seite
# nicht sieht - derselbe Wert wie --accent im hellen Thema.
SYMBOL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="oklch(0.52 0.17 262)"/>'
    '<text x="16" y="22" text-anchor="middle" font-family="system-ui,sans-serif"'
    ' font-size="18" font-weight="600" fill="oklch(0.99 0.002 250)">P</text>'
    "</svg>")

MARKE = ('<a class="marke" href="/"><b>P</b><span>Prolo'
         '<small>Freigabe</small></span></a>')


def seite_start():
    """Die oeffentliche Startseite. Sie verraet nichts.

    Kein Name, keine Anschrift, keine Liste der abgelegten Seiten - wer
    hierherkommt, ohne einen Link zu haben, soll gar nicht erst erfahren,
    dass es etwas zu finden gibt.
    """
    return huelle("Prolo", """
<div class="mitte" style="max-width:640px">
  %s
  <div class="karte" style="margin-top:28px">
    <h1 style="font-size:22px">Hier liegt nichts offen herum.</h1>
    <p style="margin:10px 0 0">Diese Adresse gibt Seiten nur an den weiter,
    der einen Zugangslink hat. Hast du einen bekommen, ruf ihn direkt auf —
    er führt dich ohne Umweg zur Seite.</p>
    <p class="kontext" style="margin-top:14px">Stimmt etwas mit deinem Link
    nicht, frag bei der Person nach, von der du ihn hast. Ein Link kann
    ablaufen oder zurückgezogen worden sein.</p>
  </div>
</div>""" % MARKE)


def seite_meldung(code, text):
    art = "fehler" if code >= 500 or code in (403, 404, 429) else "warn"
    return huelle("Prolo — %d" % code, """
<div class="mitte" style="max-width:640px">
  %s
  <div class="karte" style="margin-top:28px">
    <h1 style="font-size:20px">%s</h1>
    <div class="meldung %s" style="margin-top:12px">%s</div>
    <a class="knopf rahmen" href="/" style="margin-top:6px">Zur Startseite</a>
  </div>
</div>""" % (MARKE, KOPFZEILEN.get(code, "Das hat nicht geklappt"),
             art, schuetzen(text)))


KOPFZEILEN = {
    403: "Kein Zugang",
    404: "Nicht gefunden",
    429: "Zu viele Versuche",
    401: "Nicht angemeldet",
    500: "Etwas ist schiefgegangen",
}


def seite_passwort(marke, fehler):
    return huelle("Prolo — Passwort", """
<div class="mitte" style="max-width:480px">
  %s
  <form class="karte" method="post" action="/z/%s" style="margin-top:28px">
    <h1 style="font-size:20px">Noch ein Passwort</h1>
    <p class="kontext" style="margin:6px 0 16px">Zu diesem Link gehört ein
    Passwort. Es steht in der Nachricht, mit der du ihn bekommen hast.</p>
    %s
    <label class="label" for="pw">Passwort</label>
    <input type="password" id="pw" name="passwort" autocomplete="off"
           autofocus required>
    <button class="knopf" type="submit" style="margin-top:14px;width:100%%">
      Weiter</button>
  </form>
</div>""" % (MARKE, schuetzen(marke),
             ('<div class="meldung fehler">%s</div>' % schuetzen(fehler))
             if fehler else ""))


def verwaltung_daten(nutzer):
    seiten = []
    for s in db().execute("SELECT * FROM seite WHERE geloescht=0 "
                          "ORDER BY hochgeladen DESC").fetchall():
        frei = []
        for f in db().execute("SELECT * FROM freigabe WHERE seite_id=? "
                              "ORDER BY angelegt DESC", (s["id"],)).fetchall():
            frei.append({"id": f["id"], "etikett": f["etikett"],
                         "angelegt": f["angelegt"], "laeuft_ab": f["laeuft_ab"],
                         "lage": freigabe_lage(f), "zustand": f["zustand"],
                         "passwort": bool(f["passwort_hash"]),
                         "aufrufe": f["aufrufe"], "zuletzt": f["zuletzt"]})
        seiten.append({"kennung": s["kennung"], "titel": s["titel"],
                       "groesse_b": s["groesse_b"],
                       "hochgeladen": s["hochgeladen"], "freigaben": frei})
    return {"nutzer": nutzer, "seiten": seiten, "version": VERSION}


def seite_verwaltung():
    return huelle("Prolo Freigabe — Verwaltung", """
<div class="mitte">
  <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    %s
    <div style="margin-left:auto" class="kontext" id="wer"></div>
  </div>

  <div class="karte" style="margin-top:20px">
    <h2 style="font-size:15px">Eine Seite ablegen</h2>
    <div class="kontext" style="margin:4px 0 14px">Eine fertige HTML-Datei.
    Sie bleibt liegen, bis du sie löschst — einen Zugang zurückzuziehen
    löscht sie nicht.</div>
    <div class="meldung warn">Eine hochgeladene Seite ist Code aus fremder
    Quelle. Sie läuft ohne Verbindung nach draußen und kommt an nichts
    heran — lege trotzdem nur ab, was du kennst.</div>
    <label class="label" for="titel">Titel (leer lassen: aus der Datei)</label>
    <input type="text" id="titel" maxlength="120" placeholder="Lebenslauf lang">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px">
      <!-- Rahmenknopf, nicht Primaer (§5): eine Datei legt man selten ab,
           einen Link gibt man oft aus. Der blaue Knopf gehoert also dorthin.
           Bleibt der Punkt, dass jede Seitenkarte ihr eigenes "Link
           ausgeben" hat - das ist dieselbe offene Frage wie N-43. -->
      <label class="knopf rahmen" for="datei">Datei auswählen</label>
      <input type="file" id="datei" accept=".html,text/html"
             style="position:absolute;left:-9999px" aria-label="HTML-Datei auswählen">
    </div>
  </div>

  <div id="bericht"></div>
  <div id="liste" style="margin-top:20px"></div>
</div>
<script>
const $ = (x) => document.getElementById(x);
const schuetzen = (s) => String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;');
const datum = (s) => s ? new Date(s).toLocaleDateString('de-DE',
  {day:'2-digit', month:'2-digit', year:'numeric'}) : '—';
const bytes = (n) => n < 1024 ? n + ' Byte'
  : n < 1048576 ? (n/1024).toFixed(1).replace('.',',') + ' kB'
  : (n/1048576).toFixed(1).replace('.',',') + ' MB';

function melden(text, art){
  $('bericht').innerHTML = '<div class="meldung ' + (art||'') + '">' +
    schuetzen(text) + '</div>';
}
async function ruf(weg, daten){
  const a = await fetch(weg, {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(daten)});
  const j = await a.json().catch(() => ({}));
  if(!a.ok) throw new Error(j.fehler || ('Der Server hat mit ' + a.status +
    ' geantwortet.'));
  return j;
}
async function laden(){
  const a = await fetch('/api/verwaltung');
  if(!a.ok){ melden('Die Liste kam nicht — bist du noch angemeldet?', 'fehler');
             return; }
  const d = await a.json();
  $('wer').textContent = d.nutzer + ' · Fassung ' + d.version;
  if(!d.seiten.length){
    $('liste').innerHTML = '<div class="karte"><h2 style="font-size:15px">' +
      'Noch nichts abgelegt</h2><div class="kontext" style="margin-top:4px">' +
      'Lege oben eine HTML-Datei ab. Danach kannst du je Bewerbung einen ' +
      'eigenen Link dafür ausgeben.</div></div>';
    return;
  }
  $('liste').innerHTML = d.seiten.map(bauen).join('');
}
function bauen(s){
  const zeilen = s.freigaben.map(f => `
    <tr>
      <td>${schuetzen(f.etikett)}${f.passwort
        ? ' <span class="badge gesperrt">Passwort</span>' : ''}</td>
      <td><span class="badge ${f.lage === 'aktiv' ? 'aktiv' : 'gesperrt'}"
        >${f.lage}</span></td>
      <td class="zahlen">${f.aufrufe}</td>
      <td class="mono">${datum(f.zuletzt)}</td>
      <td class="mono">${datum(f.laeuft_ab)}</td>
      <td style="white-space:nowrap">
        <button class="knopf rahmen" data-tun="zustand" data-id="${f.id}"
          data-ziel="${f.zustand === 'aktiv' ? 'gesperrt' : 'aktiv'}"
          style="min-height:36px;padding:0 10px">${
            f.zustand === 'aktiv' ? 'Zurückziehen' : 'Wieder freischalten'}</button>
        <button class="knopf rahmen" data-tun="passwort" data-id="${f.id}"
          data-an="${f.passwort ? '0' : '1'}"
          style="min-height:36px;padding:0 10px">${
            f.passwort ? 'Passwort weg' : 'Passwort setzen'}</button>
      </td>
    </tr>`).join('');
  return `<div class="karte" style="margin-top:14px">
    <div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap">
      <h2 style="font-size:15px">${schuetzen(s.titel)}</h2>
      <span class="kontext mono">${schuetzen(s.kennung)} · ${bytes(s.groesse_b)}
        · ${datum(s.hochgeladen)}</span>
      <button class="knopf gefahr" data-tun="loeschen" data-kennung="${schuetzen(s.kennung)}"
        style="margin-left:auto;min-height:36px;padding:0 12px">Seite löschen</button>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;align-items:end">
      <div style="flex:1 1 220px;min-width:0">
        <label class="label" for="et-${s.kennung}">Wofür ist der neue Link?</label>
        <input type="text" id="et-${s.kennung}" maxlength="120"
               placeholder="Bewerbung Stadtwerke">
      </div>
      <div style="flex:0 1 130px;min-width:0">
        <label class="label" for="tg-${s.kennung}">Läuft ab nach (Tage)</label>
        <input type="number" id="tg-${s.kennung}" min="1" max="3650" value="90"
               inputmode="numeric">
      </div>
      <button class="knopf" data-tun="freigabe" data-kennung="${schuetzen(s.kennung)}"
        >Link ausgeben</button>
    </div>
    ${s.freigaben.length ? `<div style="overflow:auto;margin-top:14px"><table>
      <thead><tr><th>Etikett</th><th>Lage</th><th class="zahlen">Aufrufe</th>
      <th>Zuletzt</th><th>Läuft ab</th><th></th></tr></thead>
      <tbody>${zeilen}</tbody></table></div>`
      : '<div class="kontext" style="margin-top:12px">Für diese Seite gibt es ' +
        'noch keinen Link. Ohne Link kommt niemand an sie heran.</div>'}
  </div>`;
}
document.addEventListener('click', async (e) => {
  const k = e.target.closest('[data-tun]');
  if(!k) return;
  k.disabled = true;
  try {
    const tun = k.dataset.tun;
    if(tun === 'freigabe'){
      const et = $('et-' + k.dataset.kennung).value.trim();
      const tg = $('tg-' + k.dataset.kennung).value;
      const a = await ruf('/api/freigabe',
        {kennung: k.dataset.kennung, etikett: et, tage: tg});
      const url = location.origin + '/z/' + a.marke;
      $('bericht').innerHTML = '<div class="meldung gut"><strong>Der Link — ' +
        'jetzt kopieren</strong><div class="kontext" style="margin:4px 0 8px">' +
        'Gespeichert ist nur sein Abdruck. Noch einmal anzeigen kann ihn ' +
        'niemand, auch der Server nicht.</div>' +
        '<input type="text" class="mono" readonly value="' + schuetzen(url) + '">' +
        '</div>';
      $('bericht').querySelector('input').select();
    } else if(tun === 'zustand'){
      await ruf('/api/zustand', {id: +k.dataset.id, zustand: k.dataset.ziel});
      melden(k.dataset.ziel === 'aktiv' ? 'Der Link gilt wieder.'
                                        : 'Der Link gilt nicht mehr.', 'gut');
    } else if(tun === 'passwort'){
      let pw = null;
      if(k.dataset.an === '1'){
        pw = prompt('Passwort für diesen Link (mindestens acht Zeichen):');
        if(pw === null){ k.disabled = false; return; }
      }
      await ruf('/api/passwort', {id: +k.dataset.id, passwort: pw});
      melden(pw ? 'Der Link fragt jetzt nach dem Passwort.'
                : 'Der Link fragt nicht mehr nach einem Passwort.', 'gut');
    } else if(tun === 'loeschen'){
      if(!confirm('Die Seite "' + k.dataset.kennung + '" löschen? Alle Links ' +
                  'darauf gelten danach nicht mehr.')){ k.disabled = false; return; }
      await ruf('/api/loeschen', {kennung: k.dataset.kennung, bestaetigt: true});
      melden('Die Seite ist aus der Liste. Die Datei liegt noch auf dem ' +
             'Server, bis jemand sie dort entfernt.', 'gut');
    }
    await laden();
  } catch(err){
    melden(err.message, 'fehler');
  } finally {
    k.disabled = false;
  }
});
$('datei').addEventListener('change', async (e) => {
  const d = e.target.files[0];
  if(!d) return;
  melden('Wird abgelegt …');
  try {
    const titel = encodeURIComponent($('titel').value.trim());
    const a = await fetch('/api/hochladen?titel=' + titel,
      {method:'POST', headers:{'Content-Type':'text/html'}, body: d});
    const j = await a.json().catch(() => ({}));
    if(!a.ok) throw new Error(j.fehler || ('Der Server hat mit ' + a.status +
      ' geantwortet.'));
    melden('"' + j.titel + '" liegt jetzt hier (' + bytes(j.groesse_b) +
           '). Gib unten einen Link dafür aus.', 'gut');
    $('titel').value = '';
    await laden();
  } catch(err){ melden(err.message, 'fehler'); }
  finally { e.target.value = ''; }
});
laden();
</script>""" % MARKE)


def main():
    # --version bleibt ohne Nebenwirkung: der Aufruf kommt von Skripten (§24a).
    if "--version" in sys.argv:
        print(VERSION)
        return
    if not EINLASS:
        sys.stderr.write(
            "FEHLER: PROLO_EINLASS ist nicht gesetzt.\n\n"
            "Ohne diesen Wert kann das Werkzeug nicht unterscheiden, ob eine\n"
            "Anfrage vom Zugang dieses Servers kommt oder von einem anderen\n"
            "Container im selben Netz. Es startet darum nicht.\n\n"
            "So geht es weiter:\n"
            "  1. Den Wert aus /opt/stack/traefik/dynamic/einlass.yml nehmen.\n"
            "  2. In /opt/stack/www/.env eintragen:  PROLO_EINLASS=<Wert>\n"
            "  3. sudo prolo compose www up -d\n\n"
            "Der Wert ist ein Geheimnis wie ein Passwort: nicht in Git und\n"
            "nicht in einen Chat (CLAUDE.md §21, §22).\n")
        sys.exit(2)
    datenbank_anlegen()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write("Prolo Freigabe %s laeuft auf Port %d. Daten: %s, "
                     "Seiten: %s\n" % (VERSION, PORT, DATEN, SEITEN))
    srv.serve_forever()


if __name__ == "__main__":
    main()
