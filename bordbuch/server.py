#!/usr/bin/env python3
"""
Bordbuch - lokaler Server fuer Fahrzeugkosten und Wartung.

Start:    python3 server.py
Optionen: --port 8080 --db ladelog.db --host 0.0.0.0 --verbose

Nur Python-Standardbibliothek. Die Datenbank wird beim Start automatisch
auf den aktuellen Stand gebracht - ein Update besteht also daraus,
server.py und index.html zu ersetzen und den Dienst neu zu starten.
"""
import argparse
import base64
import contextlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB_LOCK = threading.Lock()
RECEIPT_DIR = os.path.join(HERE, "receipts")
# Was der Server ueberhaupt herausgeben darf - der Rest des Verzeichnisses
# (Datenbank, Quelltext, Sicherungen) bleibt unerreichbar.
PUBLIC_FILES = {"index.html", "favicon.ico"}
# Wege, die auch mit Schreibrecht NICHT in einem fremden Profil erlaubt sind.
# Eine Freigabe heisst "mitschreiben duerfen", nicht "das Profil uebernehmen":
# Fahrzeuge, Einstellungen, Sicherungen und Freigaben bleiben beim Eigentuemer.
NUR_EIGENTUEMER = {
    "/api/settings", "/api/restore", "/api/users/reset",
    "/api/freigabe/save", "/api/freigabe/delete",
    "/api/cars/save", "/api/cars/delete", "/api/admin/import",
}
# Zeitstempel muessen als Datum lesbar sein, sonst zeigt die Oberflaeche
# spaeter "Invalid Date" an. Lieber gleich beim Eingang ablehnen.
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def valid_dat(v):
    """Nur ein Tagesdatum wie 2027-03 oder 2027-03-15 durchlassen.

    Die HU wird oft nur mit Monat angegeben - dann wird der Erste ergaenzt,
    damit spaeter gerechnet werden kann.
    """
    s = str(v or "").strip()[:10]
    if re.match(r"^\d{4}-\d{2}$", s):
        return s + "-01"
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else ""


def plus_monate(datum, monate):
    """Datum um n Monate weiterschieben, ohne Fremdbibliothek."""
    import datetime
    try:
        d = datetime.date.fromisoformat(str(datum)[:10])
    except ValueError:
        return ""
    m = d.month - 1 + int(round(float(monate)))
    jahr = d.year + m // 12
    monat = m % 12 + 1
    tag = min(d.day, [31, 29 if (jahr % 4 == 0 and (jahr % 100 or jahr % 400 == 0)) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][monat - 1])
    return datetime.date(jahr, monat, tag).isoformat()


def beleg_datei_weg(name):
    """Eine Belegdatei vom Datentraeger entfernen - Fehler sind hier belanglos."""
    try:
        os.remove(os.path.join(RECEIPT_DIR, name))
    except OSError:
        pass


def valid_ts(v):
    v = str(v or "").strip()[:40]
    return v if TS_RE.match(v) else ""


RECEIPT_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|heic|pdf)$", re.I)
# Groesste zulaessige Anfrage: ein Beleg (8 MB) plus Luft fuer Base64 und Text
MAX_BODY = 14 * 1024 * 1024
RECEIPT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "heic": "image/heic", "pdf": "application/pdf"}
MAX_RECEIPT = 8 * 1024 * 1024

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  name     TEXT NOT NULL UNIQUE,
  settings TEXT NOT NULL DEFAULT '{}',
  created  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cars(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  kwh_per_100 REAL NOT NULL DEFAULT 18,
  active      INTEGER NOT NULL DEFAULT 1,
  note        TEXT NOT NULL DEFAULT '',
  created     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  car_id        INTEGER REFERENCES cars(id) ON DELETE SET NULL,
  tx            TEXT NOT NULL,
  start         TEXT NOT NULL,
  finish        TEXT,
  sec           INTEGER NOT NULL DEFAULT 0,
  kwh           REAL NOT NULL DEFAULT 0,
  cost          REAL NOT NULL DEFAULT 0,
  net           REAL NOT NULL DEFAULT 0,
  vat           REAL NOT NULL DEFAULT 0,
  station       TEXT NOT NULL DEFAULT '',
  city          TEXT NOT NULL DEFAULT '',
  zip           TEXT NOT NULL DEFAULT '',
  street        TEXT NOT NULL DEFAULT '',
  rate          TEXT NOT NULL DEFAULT '',
  partner       TEXT NOT NULL DEFAULT '',
  entity        TEXT NOT NULL DEFAULT '',
  invoice_no    TEXT NOT NULL DEFAULT '',
  invoice_date  TEXT NOT NULL DEFAULT '',
  invoice_gross REAL NOT NULL DEFAULT 0,
  src           TEXT NOT NULL DEFAULT '',
  UNIQUE(user_id, tx)
);
CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(user_id, start);
"""

# Nachtraegliche Aenderungen. Beides ist idempotent: fehlende Spalten werden
# ergaenzt, vorhandene bleiben unberuehrt. So laeuft jedes Update ohne Datenverlust.
ADD_COLUMNS = [
    ("cars", "kind", "TEXT NOT NULL DEFAULT 'bev'"),
    ("cars", "l_per_100", "REAL NOT NULL DEFAULT 7"),
    ("cars", "plate", "TEXT NOT NULL DEFAULT ''"),
    ("sessions", "manual", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "note", "TEXT NOT NULL DEFAULT ''"),
    # Kilometerstand auch bei Ladungen: damit kennt Bordbuch die echte Strecke
    # eines Elektroautos und muss sie nicht aus dem Verbrauch schaetzen.
    ("sessions", "odo", "REAL NOT NULL DEFAULT 0"),
    # Nutzbare Akkugroesse: damit laesst sich aus dem Verbrauch die Reichweite sagen
    ("cars", "battery", "REAL NOT NULL DEFAULT 0"),
    ("cars", "tank", "REAL NOT NULL DEFAULT 0"),
    # Verknuepft eine Werkstattrechnung mit dem Wartungseintrag, zu dem sie
    # gehoert. 0 = freie Rechnung ohne Wartungsbezug. Damit entsteht aus den
    # "Erledigt"-Vermerken von selbst ein Logbuch je Wartungsart.
    ("werkstatt", "wart_id", "INTEGER NOT NULL DEFAULT 0"),
    # Forward-Auth: Wer ein Profil benutzen darf, sagt die Identitaetsinstanz.
    # Der Anmeldename von dort ist der Schluessel zum Profil.
    ("users", "authentik_user", "TEXT NOT NULL DEFAULT ''"),
    ("users", "email", "TEXT NOT NULL DEFAULT ''"),
]
ADD_TABLES = ["""
/* Wer gibt wem Einblick in sein Profil. Bordbuch verwaltet keine Nutzer -
   es verwaltet nur, wer in fremde Daten sehen (oder eintragen) darf. */
CREATE TABLE IF NOT EXISTS freigaben(
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  eigentuemer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  empfaenger_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ziel_typ       TEXT NOT NULL DEFAULT 'profil',
  ziel_id        INTEGER NOT NULL DEFAULT 0,
  rechte         TEXT NOT NULL DEFAULT 'lesen',
  created        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(eigentuemer_id, empfaenger_id, ziel_typ, ziel_id)
);
CREATE INDEX IF NOT EXISTS idx_frei_empf ON freigaben(empfaenger_id);
""", """
CREATE TABLE IF NOT EXISTS wartung(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  car_id        INTEGER REFERENCES cars(id) ON DELETE CASCADE,
  art           TEXT NOT NULL DEFAULT '',    -- "Oelwechsel", "HU/TUEV", "Reifen"
  intervall_km  REAL NOT NULL DEFAULT 0,     -- 0 = spielt keine Rolle
  intervall_mon REAL NOT NULL DEFAULT 0,     -- 0 = spielt keine Rolle
  letzte_km     REAL NOT NULL DEFAULT 0,
  letztes_dat   TEXT NOT NULL DEFAULT '',
  faellig_km    REAL NOT NULL DEFAULT 0,     -- feste Faelligkeit statt Intervall
  faellig_dat   TEXT NOT NULL DEFAULT '',
  notiz         TEXT NOT NULL DEFAULT '',
  aktiv         INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_wartung_user ON wartung(user_id, car_id);
""", """
CREATE TABLE IF NOT EXISTS werkstatt(
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  car_id  INTEGER REFERENCES cars(id) ON DELETE SET NULL,
  ts      TEXT NOT NULL,
  art     TEXT NOT NULL DEFAULT '',
  cost    REAL NOT NULL DEFAULT 0,
  odo     REAL NOT NULL DEFAULT 0,
  betrieb TEXT NOT NULL DEFAULT '',
  note    TEXT NOT NULL DEFAULT '',
  receipt TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_werkstatt_user ON werkstatt(user_id, car_id);
""", """
CREATE TABLE IF NOT EXISTS fuelings(
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  car_id  INTEGER REFERENCES cars(id) ON DELETE SET NULL,
  ts      TEXT NOT NULL,
  liters  REAL NOT NULL DEFAULT 0,
  cost    REAL NOT NULL DEFAULT 0,
  odo     REAL NOT NULL DEFAULT 0,
  full    INTEGER NOT NULL DEFAULT 1,
  station TEXT NOT NULL DEFAULT '',
  note    TEXT NOT NULL DEFAULT '',
  receipt TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT (datetime('now'))
);""",
    "CREATE INDEX IF NOT EXISTS idx_fuel_user ON fuelings(user_id, ts);",
    "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"]

# Indizes, die eine erst durch ADD_COLUMNS entstandene Spalte brauchen - sie
# muessen daher nach den Spalten laufen, nicht mit den Tabellen.
ADD_INDEXES = [
    # Ein Anmeldename gehoert zu genau einem Profil. Leere Namen sind ausgenommen,
    # damit alte Profile ohne Verknuepfung nebeneinander bestehen koennen.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_authentik"
    " ON users(authentik_user) WHERE authentik_user<>''",
]
SCHEMA_VERSION = "5"
# Fassungsnummer der Anwendung, getrennt vom Datenstand oben. Wird von
# --version, /api/version, install.sh und update.sh gelesen.
VERSION = "2.1.0"

SESSION_FIELDS = ["tx", "start", "finish", "sec", "kwh", "cost", "net", "vat", "station", "city", "zip",
                  "street", "rate", "partner", "entity", "invoice_no", "invoice_date", "invoice_gross",
                  "src", "manual", "note", "odo"]
JSON_TO_COL = {"id": "tx", "start": "start", "end": "finish", "sec": "sec", "kwh": "kwh", "cost": "cost",
               "net": "net", "vat": "vat", "station": "station", "city": "city", "zip": "zip",
               "street": "street", "rate": "rate", "partner": "partner", "entity": "entity",
               "invoiceNo": "invoice_no", "invoiceDate": "invoice_date", "invoiceGross": "invoice_gross", "odo": "odo",
               "src": "src", "manual": "manual", "note": "note"}
COL_TO_JSON = {v: k for k, v in JSON_TO_COL.items()}
INT_COLS = {"sec", "manual"}
REAL_COLS = {"kwh", "cost", "net", "vat", "invoice_gross", "odo"}


@contextlib.contextmanager
def db():
    """Verbindung im Autocommit-Betrieb.

    Wichtig: die Antwort an den Browser wird innerhalb des with-Blocks
    geschickt. Wuerde erst beim Verlassen des Blocks committet, koennte der
    Browser den naechsten Zustand abfragen, bevor die Aenderung in der
    Datenbank steht - dann sieht er den alten Stand. Mit isolation_level=None
    ist jede Anweisung sofort geschrieben.
    """
    con = sqlite3.connect(CFG.db, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        con.close()


@contextlib.contextmanager
def bulk(con):
    """Mehrere Schreibvorgaenge als eine Einheit - alles oder nichts."""
    con.execute("BEGIN")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def init_db():
    folder = os.path.dirname(os.path.abspath(CFG.db))
    if folder:
        os.makedirs(folder, exist_ok=True)
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    fresh = not os.path.exists(CFG.db) or os.path.getsize(CFG.db) == 0
    with db() as con:
        con.executescript(BASE_SCHEMA)
        for sql in ADD_TABLES:
            con.executescript(sql)
        for table, column, decl in ADD_COLUMNS:
            have = {r["name"] for r in con.execute("PRAGMA table_info(%s)" % table)}
            if column not in have:
                con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, decl))
                if not fresh:   # bei einer neuen Datenbank ist das kein Update, sondern der Normalfall
                    print("Datenbank ergaenzt: %s.%s" % (table, column))
        for sql in ADD_INDEXES:
            con.execute(sql)
        old = con.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('schema',?)", (SCHEMA_VERSION,))
        if old and old["v"] != SCHEMA_VERSION:
            print("Datenbank von Stand %s auf %s gebracht." % (old["v"], SCHEMA_VERSION))


def num(v, d=0.0):
    try:
        f = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
        return f if f == f and abs(f) != float("inf") else d
    except (TypeError, ValueError):
        return d


def row_session(r):
    out = {"dbid": r["id"], "carId": r["car_id"]}
    for col in SESSION_FIELDS:
        out[COL_TO_JSON[col]] = r[col]
    out["manual"] = bool(r["manual"])
    return out


def row_fuel(r):
    return {"dbid": r["id"], "carId": r["car_id"], "ts": r["ts"], "liters": r["liters"], "cost": r["cost"],
            "odo": r["odo"], "full": bool(r["full"]), "station": r["station"], "note": r["note"],
            "receipt": r["receipt"]}


class Server(ThreadingHTTPServer):
    """HTTP-Server mit groesserer Annahme-Warteschlange und ruhigem Log.

    request_queue_size: beim gleichzeitigen Aufruf durch mehrere Geraete
    liefen sonst Verbindungen in einen Timeout, weil die Warteschlange des
    Betriebssystems (Standard 5) uebergelaufen ist.
    """
    request_queue_size = 64
    daemon_threads = True

    def handle_error(self, request, client_address):
        fehler = sys.exc_info()[1]
        if isinstance(fehler, App.ABBRUCH):
            return          # Client ist weg - kein Grund fuer einen Traceback
        ThreadingHTTPServer.handle_error(self, request, client_address)


def belege_loeschen(con, user_id, behalten=()):
    """Bilddateien der Tankungen eines Profils vom Datentraeger entfernen.

    Die Datenbankzeilen verschwinden per ON DELETE CASCADE von selbst - die
    Dateien in receipts/ nicht. Ohne diesen Aufruf blieben sie fuer immer liegen.

    behalten: Dateinamen, die gleich wieder gebraucht werden. Beim Einspielen
    mit "Alles ersetzen" stehen in der Sicherung dieselben Belegnamen wie in
    der Datenbank - wuerde man sie loeschen, zeigten die neuen Zeilen auf
    Dateien, die es nicht mehr gibt. Deshalb bleibt alles verschont, was in
    der Sicherung noch vorkommt.
    """
    schutz = set(behalten or ())
    weg = 0
    for tabelle in ("fuelings", "werkstatt"):
        for r in con.execute("SELECT receipt FROM %s WHERE user_id=? AND receipt<>''" % tabelle,
                             (user_id,)):
            if r["receipt"] in schutz:
                continue
            beleg_datei_weg(r["receipt"])
            weg += 1
    return weg


def belege_der_sicherung(payload):
    """Alle Belegnamen aus einer Sicherung sammeln - egal auf welcher Ebene."""
    namen = set()
    teile = payload.get("profile") if isinstance(payload.get("profile"), list) else [payload]
    for t in teile or []:
        for schluessel in ("fuelings", "werkstatt"):
            for f in (t or {}).get(schluessel) or []:
                if f.get("receipt"):
                    namen.add(str(f["receipt"]))
    return namen


class App(BaseHTTPRequestHandler):
    server_version = "Bordbuch"
    # HTTP/1.1 haelt die Verbindung offen - sonst braucht jede Anfrage eine
    # neue, und bei mehreren Geraeten gleichzeitig laeuft die Warteschlange
    # des Betriebssystems ueber (abgewiesene Verbindungen).
    protocol_version = "HTTP/1.1"
    # Eine Verbindung, die nichts mehr sendet, gibt ihren Thread nach 30 s frei.
    timeout = 30

    # ---------------- Helfer ----------------
    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > MAX_BODY:
            raise ValueError("Anfrage zu gross (Grenze: %d MB)" % (MAX_BODY // 1024 // 1024))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def ich(self, con):
        """Wer fragt? Kommt ausschliesslich aus dem Kopf, den der Proxy setzt.
        Bordbuch legt niemanden an und prueft kein Passwort - das macht die
        vorgeschaltete Identitaetsinstanz. Ist der Name unbekannt, entsteht
        beim ersten Aufruf ein Profil dafuer (Just-in-Time)."""
        # Kopfnamen sind laut HTTP unabhaengig von Gross- und Kleinschreibung;
        # Traefik schickt sie als X-Authentik-Username.
        name = (self.headers.get("X-Authentik-Username") or "").strip()[:60]
        if not name:
            return None
        mail = (self.headers.get("X-Authentik-Email") or "").strip()[:120]
        # Der volle Anzeigename kommt eigens mit; ohne ihn bleibt der Anmeldename.
        voll = (self.headers.get("X-Authentik-Name") or "").strip()[:60]
        row = con.execute("SELECT * FROM users WHERE authentik_user=?", (name,)).fetchone()
        if row:
            # Anzeigedaten nachziehen, falls sie sich in der Identitaetsinstanz
            # geaendert haben. Ist der Anzeigename dort schon vergeben, bleibt
            # der bisherige - lieber ein alter Name als gar kein Profil.
            if mail and mail != row["email"]:
                con.execute("UPDATE users SET email=? WHERE id=?", (mail, row["id"]))
            if voll and voll != row["name"]:
                try:
                    con.execute("UPDATE users SET name=? WHERE id=?", (voll, row["id"]))
                except sqlite3.IntegrityError:
                    pass
            return con.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
        anzeige = voll or name
        # users.name ist eindeutig; bei Namensgleichheit einen freien finden,
        # statt ein fremdes Profil zu kapern.
        for versuch in range(20):
            try:
                uid = con.execute("INSERT INTO users(name,authentik_user,email) VALUES(?,?,?)",
                                  (anzeige, name, mail)).lastrowid
                break
            except sqlite3.IntegrityError:
                anzeige = "%s (%d)" % (name, versuch + 2)
        else:
            return None
        return con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    def gruppen(self):
        roh = self.headers.get("X-Authentik-Groups") or ""
        return {g.strip() for g in roh.split(",") if g.strip()}

    def ist_admin(self):
        return CFG.admin_gruppe in self.gruppen()

    def profil(self, con):
        """(ich, arbeitsprofil, darf_schreiben). Ohne Kopf gibt es nichts.
        Das Arbeitsprofil ist das eigene - oder ein fremdes, fuer das eine
        Freigabe vorliegt."""
        ich = self.ich(con)
        if not ich:
            return None, None, False
        pid = self.headers.get("X-Bordbuch-Profil")
        if not pid or not str(pid).isdigit() or int(pid) == ich["id"]:
            return ich, ich, True
        ziel = con.execute("SELECT * FROM users WHERE id=?", (int(pid),)).fetchone()
        if not ziel:
            return ich, None, False
        fr = con.execute("SELECT rechte FROM freigaben WHERE eigentuemer_id=? AND empfaenger_id=?"
                         " AND ziel_typ='profil'", (ziel["id"], ich["id"])).fetchone()
        if not fr:
            return ich, None, False
        return ich, ziel, (fr["rechte"] == "schreiben")

    def who(self, con):
        """Alt-Name, wird noch von den GET-Wegen benutzt."""
        return self.profil(con)[1]

    # Abgebrochene Verbindungen sind im Heimnetz Alltag: das Handy sperrt den
    # Bildschirm, der Browser schliesst die offene Keep-Alive-Leitung, eine
    # angekuendigte Nachricht kommt nie an. Fuer solche Faelle darf kein
    # Traceback im Log stehen - sonst uebersieht man darin die echten Fehler.
    ABBRUCH = (TimeoutError, ConnectionError, BrokenPipeError, ConnectionResetError)

    def handle_one_request(self):
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except self.ABBRUCH as e:
            self.close_connection = True
            if CFG.verbose:
                sys.stderr.write("Verbindung abgebrochen (%s)\n" % type(e).__name__)

    def log_message(self, fmt, *args):
        if CFG.verbose:
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def fremde_herkunft(self):
        """True, wenn die Anfrage von einer fremden Seite ausgeloest wurde.

        Ohne diese Pruefung koennte eine beliebige Webseite im Browser eines
        Mitbewohners Profile anlegen oder loeschen - die Endpunkte dafuer
        brauchen naemlich keinen eigenen Kopf, der einen Preflight erzwingt.
        """
        if (self.headers.get("Sec-Fetch-Site") or "") in ("same-origin", "same-site", "none"):
            return False
        herkunft = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not herkunft:
            return False          # Werkzeuge wie curl senden nichts - erlaubt
        return ("//" + (self.headers.get("Host") or "")) not in herkunft

    # ---------------- GET ----------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/version":
            return self.send_json({"version": VERSION, "schema": SCHEMA_VERSION})
        if path == "/api/state":
            return self.state()
        if path == "/api/backup":
            return self.backup()
        if path == "/api/admin/export":
            # Frueher ohne jede Pruefung erreichbar - das war das groesste Loch.
            if not self.ist_admin():
                return self.send_json(
                    {"error": "Dafuer fehlt die Gruppe '%s'." % CFG.admin_gruppe}, 403)
            return self.admin_export()
        if path.startswith("/api/"):
            return self.send_json({"error": "unbekannter Endpunkt"}, 404)
        return self.static(path)

    def backup(self):
        """Vollstaendige Sicherung eines Profils als JSON."""
        with db() as con:
            ich, user, _ = self.profil(con)
            if not ich:
                return self.send_json({"error": "Nicht angemeldet."}, 401)
            # Gesichert wird immer das eigene Profil, nie ein freigegebenes.
            user = ich
            cars = [dict(r) for r in con.execute("SELECT * FROM cars WHERE user_id=?", (user["id"],))]
            sess = [dict(r) for r in con.execute("SELECT * FROM sessions WHERE user_id=?", (user["id"],))]
            fuel = [dict(r) for r in con.execute("SELECT * FROM fuelings WHERE user_id=?", (user["id"],))]
            wart = [dict(r) for r in con.execute("SELECT * FROM wartung WHERE user_id=?", (user["id"],))]
            werk = [dict(r) for r in con.execute("SELECT * FROM werkstatt WHERE user_id=?", (user["id"],))]
            try:
                settings = json.loads(user["settings"] or "{}")
            except ValueError:
                settings = {}
            return self.send_json({"ladelog": SCHEMA_VERSION, "profil": user["name"],
                                   "erstellt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                                   "cars": cars, "sessions": sess, "fuelings": fuel,
                                   "wartung": wart, "werkstatt": werk, "settings": settings})

    # ------------------------------------------------------------------
    # Einspielen einer Sicherung
    #
    # Zwei Wege fuehren hierher: der einzelne Nutzer ueber /api/restore und
    # die Verwaltung ueber /api/admin/import. Die eigentliche Arbeit macht
    # darum einspielen() - beide Endpunkte rufen nur noch auf.
    # ------------------------------------------------------------------
    def einspielen(self, con, user, payload, mode):
        """Autos, Ladungen, Tankungen und Einstellungen in EIN Profil schreiben.

        mode="replace" leert das Profil vorher, "merge" ergaenzt nur.
        Rueckgabe: Zaehler, damit der Aufrufer sagen kann, was passiert ist.
        Laeuft immer innerhalb einer Transaktion des Aufrufers.
        """
        if mode == "replace":
            # Belege, die in der Sicherung wieder auftauchen, bleiben liegen.
            belege_loeschen(con, user["id"], belege_der_sicherung(payload))
            con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            con.execute("DELETE FROM fuelings WHERE user_id=?", (user["id"],))
            # Wartungsplan und Werkstattrechnungen gehoeren dazu - sonst blieben
            # sie stehen, waehrend alles andere ersetzt wird, und die neuen
            # Eintraege liefen in die Dublettenpruefung.
            con.execute("DELETE FROM wartung WHERE user_id=?", (user["id"],))
            con.execute("DELETE FROM werkstatt WHERE user_id=?", (user["id"],))
            con.execute("DELETE FROM cars WHERE user_id=?", (user["id"],))

        # Autos werden ueber den Namen zusammengefuehrt. Sonst entstehen beim
        # zweiten Einspielen Doppel wie "Golf" und "Golf".
        have = {r["name"]: r["id"] for r in
                con.execute("SELECT id,name FROM cars WHERE user_id=?", (user["id"],))}
        carmap, cars_new = {}, 0
        for c in payload.get("cars") or []:
            name = str(c.get("name") or "Auto")[:60]
            if name in have:
                carmap[c.get("id")] = have[name]
                continue
            kind = c.get("kind") if c.get("kind") in ("bev", "phev", "petrol", "diesel") else "bev"
            new = con.execute("""INSERT INTO cars(user_id,name,kind,kwh_per_100,l_per_100,active,note,plate,
                                 battery,tank) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (user["id"], name, kind,
                               num(c.get("kwh_per_100", c.get("kwhPer100")), 18),
                               num(c.get("l_per_100", c.get("lPer100")), 7),
                               1 if c.get("active", 1) else 0,
                               str(c.get("note") or "")[:120], str(c.get("plate") or "")[:20],
                               num(c.get("battery")), num(c.get("tank")))).lastrowid
            carmap[c.get("id")] = new
            have[name] = new
            cars_new += 1

        # Ladungen: die Vorgangsnummer (tx) ist eindeutig, doppelte fallen
        # ueber den UNIQUE-Index von selbst heraus.
        sess_new = sess_dup = 0
        cols = ",".join(["user_id", "car_id"] + SESSION_FIELDS)
        ph = ",".join(["?"] * (len(SESSION_FIELDS) + 2))
        for s in payload.get("sessions") or []:
            if not s.get("tx") or not valid_ts(s.get("start")):
                continue
            vals = [user["id"], carmap.get(s.get("car_id"))]
            for col_ in SESSION_FIELDS:
                v = s.get(col_)
                if col_ in INT_COLS:
                    v = int(num(v))
                elif col_ in REAL_COLS:
                    v = round(num(v), 4)
                else:
                    v = "" if v is None else str(v)[:200]
                vals.append(v)
            try:
                con.execute("INSERT INTO sessions(%s) VALUES(%s)" % (cols, ph), vals)
                sess_new += 1
            except sqlite3.IntegrityError:
                sess_dup += 1

        # Tankungen haben keine Nummer - hier entscheidet die Kombination aus
        # Zeitpunkt, Betrag und Menge, ob es dieselbe Tankung ist.
        fuel_new = fuel_dup = 0
        for f in payload.get("fuelings") or []:
            if not valid_ts(f.get("ts")):
                continue
            key = (user["id"], f.get("ts"), round(num(f.get("cost")), 2), round(num(f.get("liters")), 3))
            if con.execute("""SELECT 1 FROM fuelings WHERE user_id=? AND ts=? AND
                              ROUND(cost,2)=? AND ROUND(liters,3)=?""", key).fetchone():
                fuel_dup += 1
                continue
            con.execute("""INSERT INTO fuelings(user_id,car_id,ts,liters,cost,odo,full,station,note,receipt)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], carmap.get(f.get("car_id")), f.get("ts"), num(f.get("liters")),
                         num(f.get("cost")), num(f.get("odo")), 1 if f.get("full", 1) else 0,
                         str(f.get("station") or "")[:120], str(f.get("note") or "")[:200],
                         str(f.get("receipt") or "")[:80]))
            fuel_new += 1

        # Wartungsplan und Werkstattrechnungen. Beide haengen am Auto, darum
        # wird die Autozuordnung ueber dieselbe Tabelle uebersetzt.
        wart_new = wart_dup = 0
        for w in payload.get("wartung") or []:
            art = str(w.get("art") or "").strip()
            if not art:
                continue
            # Ein Wartungseintrag ist durch Auto und Bezeichnung eindeutig -
            # zweimal "Oelwechsel" am selben Auto ist nie gewollt.
            if con.execute("""SELECT 1 FROM wartung WHERE user_id=? AND art=?
                              AND IFNULL(car_id,0)=IFNULL(?,0)""",
                           (user["id"], art[:80], carmap.get(w.get("car_id")))).fetchone():
                wart_dup += 1
                continue
            con.execute("""INSERT INTO wartung(user_id,car_id,art,intervall_km,intervall_mon,
                           letzte_km,letztes_dat,faellig_km,faellig_dat,notiz,aktiv)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], carmap.get(w.get("car_id")), art[:80],
                         num(w.get("intervall_km")), num(w.get("intervall_mon")),
                         num(w.get("letzte_km")), valid_dat(w.get("letztes_dat")),
                         num(w.get("faellig_km")), valid_dat(w.get("faellig_dat")),
                         str(w.get("notiz") or "")[:200], 1 if w.get("aktiv", 1) else 0))
            wart_new += 1
        werk_new = werk_dup = 0
        for w in payload.get("werkstatt") or []:
            ts = valid_ts(w.get("ts"))
            if not ts:
                continue
            if con.execute("""SELECT 1 FROM werkstatt WHERE user_id=? AND ts=? AND ROUND(cost,2)=?
                              AND art=?""",
                           (user["id"], ts, round(num(w.get("cost")), 2),
                            str(w.get("art") or "")[:80])).fetchone():
                werk_dup += 1
                continue
            con.execute("""INSERT INTO werkstatt(user_id,car_id,ts,art,cost,odo,betrieb,note,receipt)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (user["id"], carmap.get(w.get("car_id")), ts, str(w.get("art") or "")[:80],
                         num(w.get("cost")), num(w.get("odo")), str(w.get("betrieb") or "")[:120],
                         str(w.get("note") or "")[:200], str(w.get("receipt") or "")[:80]))
            werk_new += 1
        if payload.get("settings"):
            if mode == "replace":
                neu_settings = payload["settings"]
            else:
                # Ergaenzen darf die vorhandenen Einstellungen nicht ueberschreiben -
                # sonst ginge z. B. der Preisverlauf (homePrices) des Zielprofils
                # verloren. Vorhandene Schluessel gewinnen, Fehlendes wird ergaenzt (A4).
                try:
                    vorhanden = json.loads(user["settings"] or "{}")
                except (ValueError, TypeError):
                    vorhanden = {}
                neu_settings = {**payload["settings"], **vorhanden}
            con.execute("UPDATE users SET settings=? WHERE id=?",
                        (json.dumps(neu_settings), user["id"]))
        return {"cars": cars_new, "sessions": sess_new, "sessionsDup": sess_dup,
                "fuelings": fuel_new, "fuelingsDup": fuel_dup,
                "wartung": wart_new, "wartungDup": wart_dup,
                "werkstatt": werk_new, "werkstattDup": werk_dup}

    # ------------------------------------------------------------------
    # Wartungsplan
    #
    # Ein Eintrag kann auf zwei Weisen faellig werden: nach Kilometern
    # (Oelwechsel alle 30 000 km) oder nach Zeit (HU im Maerz 2027). Beides
    # darf gleichzeitig gesetzt sein - dann gilt, was zuerst eintritt. Die
    # Faelligkeit selbst rechnet die Oberflaeche aus; hier wird nur
    # gespeichert, damit der Server keine Regeln kennt, die sich aendern.
    # ------------------------------------------------------------------
    def service_save(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        art = str(data.get("art") or "").strip()[:80]
        if not art:
            return self.send_json({"error": "Bitte angeben, um welche Wartung es geht"}, 400)
        werte = (car_id, art,
                 max(0.0, num(data.get("intervallKm"))),
                 max(0.0, num(data.get("intervallMon"))),
                 max(0.0, num(data.get("letzteKm"))),
                 valid_dat(data.get("letztesDat")),
                 max(0.0, num(data.get("faelligKm"))),
                 valid_dat(data.get("faelligDat")),
                 str(data.get("notiz") or "")[:200],
                 1 if data.get("aktiv", True) else 0)
        dbid = data.get("dbid")
        if dbid:
            cur = con.execute("""UPDATE wartung SET car_id=?,art=?,intervall_km=?,intervall_mon=?,
                                 letzte_km=?,letztes_dat=?,faellig_km=?,faellig_dat=?,notiz=?,aktiv=?
                                 WHERE id=? AND user_id=?""", werte + (dbid, user["id"]))
            if not cur.rowcount:
                return self.send_json({"error": "Wartungseintrag nicht gefunden"}, 404)
            return self.send_json({"ok": True, "id": dbid})
        neu = con.execute("""INSERT INTO wartung(user_id,car_id,art,intervall_km,intervall_mon,
                             letzte_km,letztes_dat,faellig_km,faellig_dat,notiz,aktiv)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (user["id"],) + werte).lastrowid
        return self.send_json({"ok": True, "id": neu})

    def service_done(self, con, user, data):
        """Wartung als erledigt eintragen - und daraus einen Logbucheintrag machen.

        Der Wartungseintrag bleibt bestehen und wird nur weitergestellt: aus dem
        Intervall ergibt sich die naechste Faelligkeit von selbst, eine feste
        Faelligkeit (HU im Maerz) rueckt um das Intervall weiter. So muss
        niemand TUEV oder Oelwechsel jedes Mal neu anlegen.

        Gleichzeitig entsteht eine Werkstattrechnung mit Verweis auf diesen
        Eintrag (wart_id). Damit steht spaeter in der Kostenauswertung, was der
        TUEV 2023 gekostet hat - und im Logbuch, bei welchem Kilometerstand.
        Der Kilometerstand ist freiwillig: bei der HU sagt er nichts aus.
        """
        row = con.execute("SELECT * FROM wartung WHERE id=? AND user_id=?",
                          (data.get("dbid"), user["id"])).fetchone()
        if not row:
            return self.send_json({"error": "Wartungseintrag nicht gefunden"}, 404)
        km = max(0.0, num(data.get("km")))
        dat = valid_dat(data.get("dat")) or __import__("datetime").date.today().isoformat()
        f_dat = row["faellig_dat"]
        if f_dat and row["intervall_mon"] > 0:
            f_dat = plus_monate(dat, row["intervall_mon"])
        elif f_dat:
            f_dat = ""          # feste Faelligkeit ohne Intervall: erledigt ist erledigt
        f_km = row["faellig_km"]
        if f_km and row["intervall_km"] > 0 and km > 0:
            f_km = km + row["intervall_km"]
        elif f_km and km > 0:
            f_km = 0.0
        con.execute("""UPDATE wartung SET letzte_km=?,letztes_dat=?,faellig_km=?,faellig_dat=?
                       WHERE id=? AND user_id=?""",
                    (km or row["letzte_km"], dat, f_km, f_dat, row["id"], user["id"]))
        # Logbucheintrag samt Kosten. Auch ohne Betrag wird er angelegt: dass
        # der TUEV im Maerz 2024 gemacht wurde, ist die Information wert.
        beleg = ""
        try:
            beleg = self.save_receipt(data) or ""
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        log_id = con.execute("""INSERT INTO werkstatt(user_id,car_id,ts,art,cost,odo,betrieb,note,
                                receipt,wart_id) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                             (user["id"], row["car_id"], dat + "T12:00:00", row["art"],
                              round(num(data.get("cost")), 2), km,
                              str(data.get("betrieb") or "")[:120],
                              str(data.get("note") or "")[:200], beleg, row["id"])).lastrowid
        return self.send_json({"ok": True, "log": log_id})

    def service_delete(self, con, user, data):
        con.execute("DELETE FROM wartung WHERE id=? AND user_id=?", (data.get("dbid"), user["id"]))
        return self.send_json({"ok": True})

    # ------------------------------------------------------------------
    # Werkstattkosten - mit Rechnung als Bild oder PDF, wie bei Tankbelegen
    # ------------------------------------------------------------------
    def shop_save(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        ts = valid_ts(data.get("ts")) or (valid_dat(data.get("ts")) + "T12:00:00"
                                          if valid_dat(data.get("ts")) else "")
        if not ts:
            return self.send_json({"error": "Datum fehlt oder ist kein Datum"}, 400)
        cost = round(num(data.get("cost")), 2)
        art = str(data.get("art") or "").strip()[:80]
        if cost <= 0 and not art:
            return self.send_json({"error": "Bitte Betrag oder Art der Arbeit angeben"}, 400)
        try:
            beleg = self.save_receipt(data)
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        dbid = data.get("dbid")
        werte = (car_id, ts, art, cost, max(0.0, num(data.get("odo"))),
                 str(data.get("betrieb") or "")[:120], str(data.get("note") or "")[:200],
                 int(num(data.get("wartId"))))
        if dbid:
            alt = con.execute("SELECT receipt FROM werkstatt WHERE id=? AND user_id=?",
                              (dbid, user["id"])).fetchone()
            if not alt:
                return self.send_json({"error": "Rechnung nicht gefunden"}, 404)
            if beleg and alt["receipt"]:
                beleg_datei_weg(alt["receipt"])
            con.execute("""UPDATE werkstatt SET car_id=?,ts=?,art=?,cost=?,odo=?,betrieb=?,note=?,
                           wart_id=?,receipt=? WHERE id=? AND user_id=?""",
                        werte + (beleg or alt["receipt"] or "", dbid, user["id"]))
            return self.send_json({"ok": True, "id": dbid})
        # save_receipt() gibt None zurueck, wenn keine Datei mitkam - die Spalte
        # ist aber NOT NULL, darum der leere Text.
        neu = con.execute("""INSERT INTO werkstatt(user_id,car_id,ts,art,cost,odo,betrieb,note,
                             wart_id,receipt) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (user["id"],) + werte + (beleg or "",)).lastrowid
        return self.send_json({"ok": True, "id": neu})

    def shop_delete(self, con, user, data):
        row = con.execute("SELECT receipt FROM werkstatt WHERE id=? AND user_id=?",
                          (data.get("dbid"), user["id"])).fetchone()
        if row and row["receipt"]:
            beleg_datei_weg(row["receipt"])
        con.execute("DELETE FROM werkstatt WHERE id=? AND user_id=?", (data.get("dbid"), user["id"]))
        return self.send_json({"ok": True})

    def restore(self, con, user, data):
        """Sicherung eines einzelnen Profils einspielen."""
        payload = data.get("data") or {}
        if not isinstance(payload, dict) or "cars" not in payload:
            return self.send_json({"error": "Das sieht nicht wie eine Bordbuch-Sicherung aus"}, 400)
        with bulk(con):
            z = self.einspielen(con, user, payload, data.get("mode"))
        return self.send_json({"ok": True, **z})

    # ------------------------------------------------------------------
    # Verwaltung: alles ueber alle Profile hinweg
    # ------------------------------------------------------------------
    def admin_export(self):
        """Die komplette Datenbank als JSON - jedes Profil mit allem, was dazu gehoert.

        Absichtlich dasselbe Format wie eine Einzelsicherung, nur eine Ebene
        hoeher: {"profile": [ {name, cars, sessions, fuelings, settings}, ... ]}.
        So kann eine Gesamtsicherung auch profilweise wieder eingespielt werden.
        """
        with db() as con:
            profile = []
            for u in con.execute("SELECT * FROM users ORDER BY id"):
                try:
                    einst = json.loads(u["settings"] or "{}")
                except ValueError:
                    einst = {}
                profile.append({
                    "name": u["name"],
                    "cars": [dict(r) for r in
                             con.execute("SELECT * FROM cars WHERE user_id=?", (u["id"],))],
                    "sessions": [dict(r) for r in
                                 con.execute("SELECT * FROM sessions WHERE user_id=?", (u["id"],))],
                    "fuelings": [dict(r) for r in
                                 con.execute("SELECT * FROM fuelings WHERE user_id=?", (u["id"],))],
                    "wartung": [dict(r) for r in
                                con.execute("SELECT * FROM wartung WHERE user_id=?", (u["id"],))],
                    "werkstatt": [dict(r) for r in
                                  con.execute("SELECT * FROM werkstatt WHERE user_id=?", (u["id"],))],
                    "settings": einst,
                })
            return self.send_json({"ladelog": SCHEMA_VERSION, "typ": "gesamt",
                                   "erstellt": __import__("datetime").datetime.now()
                                   .isoformat(timespec="seconds"),
                                   "profile": profile})

    def admin_import(self, con, user, data):
        if not self.ist_admin():
            return self.send_json({"error": "Dafuer fehlt die Gruppe '%s'." % CFG.admin_gruppe}, 403)
        """Eine Gesamtsicherung einspielen.

        mode="replace" loescht ALLE Profile und baut die Datenbank neu auf,
        mode="merge" ergaenzt: bekannte Profile werden ueber den Namen
        gefunden, unbekannte neu angelegt. Alles in einer Transaktion - bricht
        etwas ab, bleibt die Datenbank wie vorher.
        """
        payload = data.get("data") or {}
        profile = payload.get("profile")
        if not isinstance(profile, list) or not profile:
            return self.send_json({"error": "Das sieht nicht wie eine Bordbuch-Gesamtsicherung aus"}, 400)
        mode = data.get("mode")
        bericht = []
        with bulk(con):
            if mode == "replace":
                # foreign_keys=ON sorgt dafuer, dass Autos, Ladungen und
                # Tankungen mit dem Profil verschwinden. Die Belegbilder
                # muessen von Hand weg - sonst bleibt der ganze Ordner liegen.
                # Der Aufruf betrifft ALLE Profile, darum fragt die
                # Oberflaeche vorher ausdruecklich nach.
                schutz = belege_der_sicherung(payload)
                for r in con.execute("SELECT receipt FROM fuelings WHERE receipt<>''"):
                    if r["receipt"] in schutz:
                        continue
                    try:
                        os.remove(os.path.join(RECEIPT_DIR, r["receipt"]))
                    except OSError:
                        pass
                con.execute("DELETE FROM users")
            for p in profile:
                name = str(p.get("name") or "").strip()[:60]
                if not name:
                    continue
                row = con.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
                if row:
                    ziel, neu = row, False
                else:
                    uid = con.execute("INSERT INTO users(name) VALUES(?)", (name,)).lastrowid
                    ziel = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                    neu = True
                z = self.einspielen(con, ziel, p, "merge")
                z.update({"profil": name, "neu": neu})
                bericht.append(z)
        return self.send_json({"ok": True, "profile": bericht})

    def backup_status(self, con):
        """Letzte automatische Sicherung aus meta lesen - oder None, wenn nie gelaufen."""
        zeit = con.execute("SELECT v FROM meta WHERE k='backup_zeit'").fetchone()
        if not zeit:
            return None
        def hol(k):
            r = con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return r["v"] if r else None
        g = hol("backup_groesse"); a = hol("backup_anzahl")
        return {"zeit": zeit["v"], "datei": hol("backup_datei"),
                "groesse": int(g) if (g and g.isdigit()) else None,
                "anzahl": int(a) if (a and a.isdigit()) else None}

    def state(self):
        with db() as con:
            ich, user, darf_schreiben = self.profil(con)
            if not ich:
                return self.send_json(
                    {"error": "Nicht angemeldet. Bordbuch erwartet die Anmeldung "
                              "ueber die vorgeschaltete Identitaetsinstanz."}, 401)
            if not user:
                return self.send_json({"error": "Fuer dieses Profil liegt keine Freigabe vor."}, 403)
            # Profile, die dieser Nutzer oeffnen darf: das eigene und alles,
            # was ihm freigegeben wurde. Eine globale Nutzerliste gibt es nicht.
            profile = [{"id": ich["id"], "name": ich["name"], "rechte": "eigen"}]
            for r in con.execute(
                    "SELECT u.id,u.name,f.rechte FROM freigaben f JOIN users u ON u.id=f.eigentuemer_id"
                    " WHERE f.empfaenger_id=? AND f.ziel_typ='profil' ORDER BY u.name", (ich["id"],)):
                profile.append({"id": r["id"], "name": r["name"], "rechte": r["rechte"]})
            meine = [{"id": r["id"], "profil": r["pid"], "name": r["pname"], "rechte": r["rechte"]}
                     for r in con.execute(
                         "SELECT f.id,f.rechte,u.id AS pid,u.name AS pname FROM freigaben f"
                         " JOIN users u ON u.id=f.empfaenger_id"
                         " WHERE f.eigentuemer_id=? AND f.ziel_typ='profil' ORDER BY u.name",
                         (ich["id"],))]
            fuerMich = [{"id": r["id"], "profil": r["pid"], "name": r["pname"], "rechte": r["rechte"]}
                        for r in con.execute(
                            "SELECT f.id,f.rechte,u.id AS pid,u.name AS pname FROM freigaben f"
                            " JOIN users u ON u.id=f.eigentuemer_id"
                            " WHERE f.empfaenger_id=? AND f.ziel_typ='profil' ORDER BY u.name",
                            (ich["id"],))]
            # Wem man ueberhaupt etwas freigeben kann: nur bereits angemeldete
            # Profile, Bordbuch legt niemanden an.
            andere = [{"id": r["id"], "name": r["name"]}
                      for r in con.execute("SELECT id,name FROM users WHERE id<>? ORDER BY name",
                                           (ich["id"],))]
            cars = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "kwhPer100": r["kwh_per_100"],
                     "lPer100": r["l_per_100"], "battery": r["battery"], "tank": r["tank"], "plate": r["plate"],
                     "active": bool(r["active"]), "note": r["note"]}
                    for r in con.execute("SELECT * FROM cars WHERE user_id=? ORDER BY active DESC, id",
                                         (user["id"],))]
            sess = [row_session(r) for r in con.execute(
                "SELECT * FROM sessions WHERE user_id=? ORDER BY start", (user["id"],))]
            fuel = [row_fuel(r) for r in con.execute(
                "SELECT * FROM fuelings WHERE user_id=? ORDER BY ts", (user["id"],))]
            try:
                settings = json.loads(user["settings"] or "{}")
            except ValueError:
                settings = {}
            return self.send_json({"ich": {"id": ich["id"], "name": ich["name"],
                                           "anmeldung": ich["authentik_user"],
                                           "email": ich["email"],
                                           "abmelden": CFG.abmelde_pfad,
                                           "admin": self.ist_admin()},
                                   "user": {"id": user["id"], "name": user["name"]},
                                   "profile": profile, "schreiben": darf_schreiben,
                                   "freigabenMeine": meine, "freigabenFuerMich": fuerMich,
                                   "andere": andere,
                                   "backup": self.backup_status(con),
                                   "cars": cars, "sessions": sess, "fuelings": fuel,
                                   "service": [dict(r) for r in con.execute(
                                       """SELECT id AS dbid,car_id AS carId,art,intervall_km AS intervallKm,
                                          intervall_mon AS intervallMon,letzte_km AS letzteKm,
                                          letztes_dat AS letztesDat,faellig_km AS faelligKm,
                                          faellig_dat AS faelligDat,notiz,aktiv
                                          FROM wartung WHERE user_id=? ORDER BY id""",
                                       (user["id"],))],
                                   "shop": [dict(r) for r in con.execute(
                                       """SELECT id AS dbid,car_id AS carId,ts,art,cost,odo,betrieb,
                                          note,receipt,wart_id AS wartId
                                          FROM werkstatt WHERE user_id=? ORDER BY ts""",
                                       (user["id"],))],
                                   "settings": settings, "schema": SCHEMA_VERSION})

    # ---------------- POST ----------------
    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body_json()
        except Exception:
            return self.send_json({"error": "Die Anfrage war keine gueltige JSON-Nachricht."}, 400)
        if not isinstance(data, dict):
            # Alle Handler arbeiten mit data.get(...) - ein Array oder String
            # wuerde dort einen AttributeError werfen und die Antwort abschneiden.
            return self.send_json({"error": "Die Anfrage muss ein JSON-Objekt sein."}, 400)
        if self.fremde_herkunft():
            return self.send_json({"error": "Anfrage von fremder Seite abgelehnt"}, 403)
        try:
            with DB_LOCK, db() as con:
                ich, user, darf_schreiben = self.profil(con)
                if not ich:
                    return self.send_json(
                        {"error": "Nicht angemeldet. Bordbuch erwartet die Anmeldung "
                                  "ueber die vorgeschaltete Identitaetsinstanz."}, 401)
                if not user:
                    return self.send_json(
                        {"error": "Fuer dieses Profil liegt keine Freigabe vor."}, 403)
                if path in NUR_EIGENTUEMER and user["id"] != ich["id"]:
                    return self.send_json(
                        {"error": "Das darf nur der Eigentuemer des Profils."}, 403)
                if not darf_schreiben:
                    return self.send_json(
                        {"error": "Du darfst in diesem Profil nur lesen."}, 403)
                routes = {
                    "/api/users/reset": self.user_reset,
                    "/api/freigabe/save": self.freigabe_save,
                    "/api/freigabe/delete": self.freigabe_delete,
                    "/api/settings": self.settings_save,
                    "/api/cars/save": self.car_save,
                    "/api/cars/delete": self.car_delete,
                    "/api/sessions/import": self.sessions_import,
                    "/api/sessions/save": self.session_save,
                    "/api/sessions/assign": self.sessions_assign,
                    "/api/sessions/delete": self.sessions_delete,
                    "/api/fuel/save": self.fuel_save,
                    "/api/fuel/delete": self.fuel_delete,
                    "/api/restore": self.restore,
                    # Wartungsplan und Werkstattkosten
                    "/api/service/save": self.service_save,
                    "/api/service/done": self.service_done,
                    "/api/service/delete": self.service_delete,
                    "/api/shop/save": self.shop_save,
                    "/api/shop/delete": self.shop_delete,
                    # Verwaltung: greift ueber alle Profile hinweg
                    "/api/admin/import": self.admin_import,
                }
                fn = routes.get(path)
                if not fn:
                    return self.send_json({"error": "unbekannter Endpunkt"}, 404)
                return fn(con, user, data)
        except sqlite3.Error as e:
            sys.stderr.write("Datenbankfehler bei %s: %s\n" % (path, e))
            return self.send_json({"error": "Datenbankfehler. Bitte im Log nachsehen."}, 500)
        except Exception as e:
            # Nichts darf den Verbindungs-Thread ungebremst verlassen, sonst
            # bekommt der Browser eine abgeschnittene Antwort statt einer Meldung.
            sys.stderr.write("Unerwarteter Fehler bei %s: %r\n" % (path, e))
            return self.send_json({"error": "Unerwarteter Fehler. Bitte im Log nachsehen."}, 500)

    # ---------------- Profile ----------------
    def user_reset(self, con, user, data):
        """Das eigene Profil leeren. Geloescht wird das Profil NICHT - es gehoert
        zur Identitaetsinstanz und wuerde beim naechsten Aufruf ohnehin neu
        entstehen. Die Bestaetigung mit Mengenangabe macht die Oberflaeche."""
        if (data.get("bestaetigt") or "") != "ja":
            return self.send_json({"error": "Nicht bestaetigt"}, 400)
        belege_loeschen(con, user["id"])
        for tabelle in ("werkstatt", "wartung", "fuelings", "sessions", "cars"):
            con.execute("DELETE FROM %s WHERE user_id=?" % tabelle, (user["id"],))
        con.execute("DELETE FROM freigaben WHERE eigentuemer_id=?", (user["id"],))
        con.execute("UPDATE users SET settings='{}' WHERE id=?", (user["id"],))
        return self.send_json({"ok": True})

    def freigabe_save(self, con, user, data):
        """Einem anderen Profil Einblick in das eigene geben."""
        ziel = data.get("empfaenger")
        rechte = data.get("rechte") if data.get("rechte") in ("lesen", "schreiben") else "lesen"
        if not str(ziel).isdigit() or int(ziel) == user["id"]:
            return self.send_json({"error": "Bitte ein anderes Profil waehlen."}, 400)
        wer = con.execute("SELECT id FROM users WHERE id=?", (int(ziel),)).fetchone()
        if not wer:
            return self.send_json({"error": "Dieses Profil gibt es nicht."}, 404)
        con.execute("INSERT INTO freigaben(eigentuemer_id,empfaenger_id,ziel_typ,ziel_id,rechte)"
                    " VALUES(?,?,'profil',0,?)"
                    " ON CONFLICT(eigentuemer_id,empfaenger_id,ziel_typ,ziel_id)"
                    " DO UPDATE SET rechte=excluded.rechte",
                    (user["id"], int(ziel), rechte))
        return self.send_json({"ok": True})

    def freigabe_delete(self, con, user, data):
        """Eine Freigabe zuruecknehmen - nur eigene."""
        fid = data.get("id")
        if not str(fid).isdigit():
            return self.send_json({"error": "Welche Freigabe?"}, 400)
        con.execute("DELETE FROM freigaben WHERE id=? AND eigentuemer_id=?",
                    (int(fid), user["id"]))
        return self.send_json({"ok": True})

    def settings_save(self, con, user, data):
        con.execute("UPDATE users SET settings=? WHERE id=?",
                    (json.dumps(data.get("settings") or {}), user["id"]))
        return self.send_json({"ok": True})

    # ---------------- Autos ----------------
    def car_save(self, con, user, data):
        kind = data.get("kind") if data.get("kind") in ("bev", "phev", "petrol", "diesel") else "bev"
        name = (data.get("name") or "").strip()[:60] or "Auto"
        kwh = max(1.0, min(100.0, num(data.get("kwhPer100"), 18)))
        lit = max(0.5, min(60.0, num(data.get("lPer100"), 7)))
        active = 1 if data.get("active", True) else 0
        note = (data.get("note") or "")[:120]
        plate = (data.get("plate") or "")[:20]
        akku = max(0.0, min(250.0, num(data.get("battery"))))
        tank = max(0.0, min(200.0, num(data.get("tank"))))
        cid = data.get("id")
        if cid:
            if not con.execute("SELECT 1 FROM cars WHERE id=? AND user_id=?", (cid, user["id"])).fetchone():
                return self.send_json({"error": "Auto nicht gefunden"}, 404)
            con.execute("""UPDATE cars SET name=?,kind=?,kwh_per_100=?,l_per_100=?,active=?,note=?,
                           plate=?,battery=?,tank=? WHERE id=? AND user_id=?""",
                        (name, kind, kwh, lit, active, note, plate, akku, tank, cid, user["id"]))
        else:
            cid = con.execute("""INSERT INTO cars(user_id,name,kind,kwh_per_100,l_per_100,active,note,
                                 plate,battery,tank) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (user["id"], name, kind, kwh, lit, active, note, plate, akku,
                               tank)).lastrowid
        return self.send_json({"ok": True, "id": cid})

    def car_delete(self, con, user, data):
        con.execute("DELETE FROM cars WHERE id=? AND user_id=?", (data.get("id"), user["id"]))
        return self.send_json({"ok": True})

    def own_car(self, con, user, car_id):
        if car_id in (None, ""):
            return None, True
        ok = con.execute("SELECT 1 FROM cars WHERE id=? AND user_id=?", (car_id, user["id"])).fetchone()
        return (int(car_id), True) if ok else (None, False)

    # ---------------- Ladevorgaenge ----------------
    def sessions_import(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        rows = data.get("rows") or []
        cols = ",".join(["user_id", "car_id"] + SESSION_FIELDS)
        ph = ",".join(["?"] * (len(SESSION_FIELDS) + 2))
        added = dup = 0
        with bulk(con):
          for s in rows:
            if not s.get("id") or not valid_ts(s.get("start")):
                continue
            vals = [user["id"], car_id]
            for col in SESSION_FIELDS:
                v = s.get(COL_TO_JSON[col])
                if col in INT_COLS:
                    v = int(num(v))
                elif col in REAL_COLS:
                    v = round(num(v), 4)
                else:
                    v = "" if v is None else str(v)[:200]
                vals.append(v)
            try:
                con.execute("INSERT INTO sessions(%s) VALUES(%s)" % (cols, ph), vals)
                added += 1
            except sqlite3.IntegrityError:
                dup += 1
        return self.send_json({"ok": True, "added": added, "dup": dup})

    def session_save(self, con, user, data):
        """Von Hand erfasste Ladung (z. B. Wallbox ohne Datenexport)."""
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        start = valid_ts(data.get("start"))
        if not start:
            return self.send_json({"error": "Startzeit fehlt oder ist kein Datum"}, 400)
        kwh, cost = round(num(data.get("kwh")), 4), round(num(data.get("cost")), 4)
        sec = int(num(data.get("sec")))
        station = (data.get("station") or "Zuhause")[:200]
        note = (data.get("note") or "")[:200]
        odo = round(num(data.get("odo")), 1)
        # Netto mit dem im Profil eingestellten Satz ableiten, nicht fest mit
        # 19 % (B3). Fehlt der Satz oder ist er unsinnig, gilt 19 %.
        try:
            satz = float(json.loads(user["settings"] or "{}").get("vatRate"))
        except (ValueError, TypeError):
            satz = 19.0
        if not (0 <= satz < 50):
            satz = 19.0
        net = round(cost / (1 + satz / 100.0), 4)
        dbid = data.get("dbid")
        if dbid:
            # Auch importierte Ladungen duerfen korrigiert werden - eine falsch
            # abgerechnete Ladung soll man geradebiegen koennen.
            finish = start
            row = con.execute("SELECT start FROM sessions WHERE id=? AND user_id=?",
                              (dbid, user["id"])).fetchone()
            if not row:
                return self.send_json({"error": "Ladung nicht gefunden"}, 404)
            cur = con.execute("""UPDATE sessions SET car_id=?,start=?,finish=?,sec=?,kwh=?,cost=?,net=?,
                                 vat=?,station=?,note=?,odo=? WHERE id=? AND user_id=?""",
                              (car_id, start, finish, sec, kwh, cost, net, cost - net, station, note,
                               odo, dbid, user["id"]))
            if not cur.rowcount:
                return self.send_json({"error": "Ladung nicht gefunden"}, 404)
            return self.send_json({"ok": True, "id": dbid})
        # Kam die Ladung aus einer Datei, schickt die Oberflaeche deren
        # Kennung mit. Dann erkennt die Dublettenpruefung (UNIQUE user_id,tx)
        # sie auch wieder, wenn dieselbe Datei spaeter im Stapel eingelesen
        # wird - sonst stuende die Ladung zweimal in der Liste.
        tx = str(data.get("tx") or "").strip()[:200] or ("manual-" + uuid.uuid4().hex[:16])
        try:
            con.execute("""INSERT INTO sessions(user_id,car_id,tx,start,finish,sec,kwh,cost,net,vat,
                           station,manual,note,odo,src) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?,'manuell')""",
                        (user["id"], car_id, tx, start, start, sec, kwh, cost, net, cost - net, station,
                         note, odo))
        except sqlite3.IntegrityError:
            return self.send_json({"error": "Diese Ladung ist schon erfasst"}, 409)
        return self.send_json({"ok": True, "tx": tx})

    def sessions_assign(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
        if not ids:
            return self.send_json({"ok": True, "changed": 0})
        q = "UPDATE sessions SET car_id=? WHERE user_id=? AND id IN (%s)" % ",".join("?" * len(ids))
        return self.send_json({"ok": True, "changed": con.execute(q, [car_id, user["id"]] + ids).rowcount})

    def sessions_delete(self, con, user, data):
        if data.get("all"):
            n = con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],)).rowcount
            return self.send_json({"ok": True, "deleted": n})
        ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
        if not ids:
            return self.send_json({"ok": True, "deleted": 0})
        q = "DELETE FROM sessions WHERE user_id=? AND id IN (%s)" % ",".join("?" * len(ids))
        return self.send_json({"ok": True, "deleted": con.execute(q, [user["id"]] + ids).rowcount})

    # ---------------- Tankungen ----------------
    def save_receipt(self, data):
        raw = data.get("receiptData")
        if not raw:
            return None
        ext = re.sub(r"[^a-z0-9]", "", (data.get("receiptName") or "").rsplit(".", 1)[-1].lower())[:5]
        if ext not in RECEIPT_TYPES:
            raise ValueError("Belegformat nicht erlaubt (JPG, PNG, WEBP, HEIC oder PDF)")
        blob = base64.b64decode(raw.split(",", 1)[-1], validate=False)
        if len(blob) > MAX_RECEIPT:
            raise ValueError("Beleg ist groesser als 8 MB")
        name = uuid.uuid4().hex + "." + ext
        with open(os.path.join(RECEIPT_DIR, name), "wb") as fh:
            fh.write(blob)
        return name

    def fuel_save(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        ts = valid_ts(data.get("ts"))
        if not ts:
            return self.send_json({"error": "Datum fehlt oder ist kein Datum"}, 400)
        cost = round(num(data.get("cost")), 2)
        liters = round(num(data.get("liters")), 3)
        odo = round(num(data.get("odo")), 1)
        full = 1 if data.get("full", True) else 0
        station = (data.get("station") or "")[:120]
        note = (data.get("note") or "")[:200]
        if cost <= 0 and liters <= 0:
            return self.send_json({"error": "Bitte Betrag oder Liter angeben"}, 400)
        try:
            receipt = self.save_receipt(data)
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        dbid = data.get("dbid")
        if dbid:
            row = con.execute("SELECT receipt FROM fuelings WHERE id=? AND user_id=?",
                              (dbid, user["id"])).fetchone()
            if not row:
                return self.send_json({"error": "Tankung nicht gefunden"}, 404)
            keep = receipt or ("" if data.get("dropReceipt") else row["receipt"])
            con.execute("""UPDATE fuelings SET car_id=?,ts=?,liters=?,cost=?,odo=?,full=?,station=?,
                           note=?,receipt=? WHERE id=? AND user_id=?""",
                        (car_id, ts, liters, cost, odo, full, station, note, keep, dbid, user["id"]))
            return self.send_json({"ok": True, "id": dbid})
        new = con.execute("""INSERT INTO fuelings(user_id,car_id,ts,liters,cost,odo,full,station,note,receipt)
                             VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (user["id"], car_id, ts, liters, cost, odo, full, station, note,
                           receipt or "")).lastrowid
        return self.send_json({"ok": True, "id": new})

    def fuel_delete(self, con, user, data):
        row = con.execute("SELECT receipt FROM fuelings WHERE id=? AND user_id=?",
                          (data.get("id"), user["id"])).fetchone()
        con.execute("DELETE FROM fuelings WHERE id=? AND user_id=?", (data.get("id"), user["id"]))
        if row and row["receipt"]:
            try:
                os.remove(os.path.join(RECEIPT_DIR, row["receipt"]))
            except OSError:
                pass
        return self.send_json({"ok": True})

    # ---------------- statische Dateien ----------------
    def static(self, path):
        """Nur die Oberflaeche und Belege ausliefern.

        Vorher wurde alles aus dem Programmverzeichnis herausgegeben - also
        auch server.py und vor allem ladelog.db mit allen Daten. Jetzt gibt es
        eine feste Liste erlaubter Dateien, alles andere ist nicht zu holen.
        """
        rel = "index.html" if path in ("/", "") else unquote(path).lstrip("/")
        if rel in PUBLIC_FILES:
            full = os.path.join(HERE, rel)
        elif rel.startswith("receipts/"):
            name = os.path.basename(rel)
            if not RECEIPT_NAME.match(name):
                return self.send_error(404, "Nicht gefunden")
            full = os.path.join(RECEIPT_DIR, name)
        else:
            return self.send_error(404, "Nicht gefunden")
        if not os.path.isfile(full):
            return self.send_error(404, "Nicht gefunden")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if rel == "index.html":
            # Alles liegt in der einen Datei - externe Quellen braucht es nicht.
            # 'unsafe-inline' ist noetig, weil CSS und JS bewusst eingebettet sind.
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob:; "
                             "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                             "base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(data)


def sicherung_anlegen(behalten=14):
    """Konsistente Sicherung der Datenbank nach HERE/backups/ - fuer den Timer.

    Nutzt die SQLite-.backup()-API, die auch bei laufendem Server einen
    sauberen Snapshot zieht (kein blosses Dateikopieren mitten im Schreiben).
    Aeltere Sicherungen werden bis auf die letzten 'behalten' geloescht. Das
    Ergebnis wird in meta vermerkt, damit die Oberflaeche zeigen kann, wann
    zuletzt gesichert wurde.
    """
    import datetime, glob
    ziel_dir = os.path.join(HERE, "backups")
    os.makedirs(ziel_dir, exist_ok=True)
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = os.path.join(ziel_dir, "bordbuch-%s.db" % stempel)

    # Snapshot ziehen - die Quelle darf dabei in Benutzung sein.
    quelle = sqlite3.connect(CFG.db, timeout=30)
    try:
        ziel_con = sqlite3.connect(ziel)
        try:
            quelle.backup(ziel_con)
        finally:
            ziel_con.close()
    finally:
        quelle.close()

    # Rotation: nur die neuesten 'behalten' Dateien behalten.
    entfernt = 0
    if behalten > 0:
        for weg in sorted(glob.glob(os.path.join(ziel_dir, "bordbuch-*.db")))[:-behalten]:
            try:
                os.remove(weg); entfernt += 1
            except OSError:
                pass
    rest = glob.glob(os.path.join(ziel_dir, "bordbuch-*.db"))
    groesse = os.path.getsize(ziel)

    # Ergebnis in meta festhalten (Autocommit, damit der laufende Server es sofort sieht).
    con = sqlite3.connect(CFG.db, timeout=30, isolation_level=None)
    try:
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('backup_zeit',?)",
                    (datetime.datetime.now().isoformat(timespec="seconds"),))
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('backup_datei',?)",
                    (os.path.basename(ziel),))
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('backup_groesse',?)", (str(groesse),))
        con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('backup_anzahl',?)", (str(len(rest)),))
    finally:
        con.close()
    return ziel, groesse, len(rest), entfernt


def main():
    p = argparse.ArgumentParser(description="Bordbuch Server")
    p.add_argument("--port", type=int, default=int(os.environ.get("LADELOG_PORT", 8080)))
    # Die Identitaet kommt aus einem HTTP-Kopf. Der ist nur so viel wert wie die
    # Gewissheit, dass ausschliesslich der Reverse-Proxy den Server erreicht -
    # darum standardmaessig nur auf dem eigenen Rechner lauschen.
    p.add_argument("--host", default=os.environ.get("LADELOG_HOST", "127.0.0.1"))
    p.add_argument("--header-vertrauen", action="store_true",
                   help="Auch auf anderen Netzwerkkarten lauschen. Nur sinnvoll, wenn sicher "
                        "ist, dass niemand ausser dem Proxy den Server erreicht.")
    p.add_argument("--abmelde-pfad", default=os.environ.get("BORDBUCH_ABMELDEN",
                                                            "/outpost.goauthentik.io/sign_out"),
                   help="Wohin der Abmelden-Knopf fuehrt. Leer laesst den Knopf verschwinden.")
    p.add_argument("--admin-gruppe", default=os.environ.get("BORDBUCH_ADMIN_GRUPPE", "bordbuch-admin"),
                   help="Gruppe aus X-Authentik-Groups, die die Gesamtsicherung nutzen darf")
    p.add_argument("--verknuepfe", metavar="ANMELDENAME=PROFIL",
                   help="Ein bestehendes Profil einem Anmeldenamen zuordnen und beenden")
    # Neuer Standardname bordbuch.db. Wer schon eine ladelog.db hat, soll nach
    # dem Update NICHT ploetzlich vor einer leeren Datenbank stehen - darum
    # wird die alte Datei weiter benutzt, solange sie existiert.
    alt = os.path.join(HERE, "ladelog.db")
    neu = os.path.join(HERE, "bordbuch.db")
    standard = alt if (os.path.exists(alt) and not os.path.exists(neu)) else neu
    p.add_argument("--db", default=os.environ.get("BORDBUCH_DB",
                                                 os.environ.get("LADELOG_DB", standard)))
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--backup", action="store_true",
                   help="Einmalige Sicherung anlegen und beenden (fuer den systemd-Timer)")
    p.add_argument("--backup-keep", type=int, default=14,
                   help="Wie viele Sicherungen behalten werden (Standard 14, 0 = alle)")
    p.add_argument("--version", action="store_true",
                   help="Fassungsnummer ausgeben und beenden")
    global CFG
    CFG = p.parse_args()
    if CFG.version:
        print(VERSION)
        return
    if CFG.backup:
        init_db()   # stellt sicher, dass Datenbank und meta-Tabelle existieren
        ziel, groesse, anzahl, entfernt = sicherung_anlegen(CFG.backup_keep)
        print("Sicherung: %s (%d Bytes), %d vorhanden, %d alte entfernt"
              % (os.path.basename(ziel), groesse, anzahl, entfernt))
        return
    init_db()
    if CFG.verknuepfe:
        if "=" not in CFG.verknuepfe:
            print("Bitte in der Form --verknuepfe anmeldename=Profilname angeben.")
            return
        anmeldung, profilname = CFG.verknuepfe.split("=", 1)
        with db() as con:
            row = con.execute("SELECT id,name FROM users WHERE name=?", (profilname.strip(),)).fetchone()
            if not row:
                print("Kein Profil mit dem Namen %r gefunden." % profilname.strip())
                return
            try:
                con.execute("UPDATE users SET authentik_user=? WHERE id=?",
                            (anmeldung.strip(), row["id"]))
            except sqlite3.IntegrityError:
                print("Der Anmeldename %r gehoert schon zu einem anderen Profil." % anmeldung.strip())
                return
        print("Profil %r gehoert jetzt zu %r." % (profilname.strip(), anmeldung.strip()))
        return
    # Ohne Proxy davor waeren die Identitaets-Koepfe frei erfindbar: jeder im
    # Netz koennte sich als beliebiger Nutzer ausgeben. Lieber gar nicht starten
    # als Sicherheit vortaeuschen.
    # Im Container ist 0.0.0.0 der Normalfall: erreichbar ist der Dienst dann nur
    # ueber das Docker-Netz, solange im Compose-File KEINE ports-Zeile steht.
    im_container = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    if im_container and CFG.host not in ("127.0.0.1", "localhost", "::1") and not CFG.header_vertrauen:
        print("Hinweis: Bordbuch laeuft in einem Container und lauscht auf %s.\n"
              "         Das ist richtig, solange der Dienst NUR ueber den Reverse Proxy\n"
              "         erreichbar ist - im Compose-File darf keine ports-Zeile stehen,\n"
              "         sonst sind die Anmeldekoepfe von aussen faelschbar." % CFG.host)
        CFG.header_vertrauen = True
    if CFG.host not in ("127.0.0.1", "localhost", "::1") and not CFG.header_vertrauen:
        print("Bordbuch nimmt die Anmeldung aus den Koepfen der vorgeschalteten\n"
              "Identitaetsinstanz entgegen. Auf %s waeren diese Koepfe faelschbar -\n"
              "jeder im Netz koennte sich als beliebiger Nutzer ausgeben.\n\n"
              "Lass den Server auf 127.0.0.1 lauschen und stelle den Reverse-Proxy davor.\n"
              "Ist der Zugang anders abgesichert, starte mit --header-vertrauen." % CFG.host)
        return
    print("Bordbuch (Stand %s) laeuft auf http://%s:%d\nAnmeldung: Kopf X-Authentik-Username"
          " · Verwaltungsgruppe: %s\nAbmelden: %s\nDatenbank: %s"
          % (SCHEMA_VERSION, CFG.host, CFG.port, CFG.admin_gruppe,
             CFG.abmelde_pfad or "(kein Knopf)", CFG.db))
    try:
        Server((CFG.host, CFG.port), App).serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
