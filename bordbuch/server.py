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
import binascii
import contextlib
import datetime
import decimal
import hmac
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB_LOCK = threading.Lock()
# Belege und automatische Sicherungen liegen neben der Datenbank, nicht im
# Programmverzeichnis: im Container ist das Programmverzeichnis Teil des Abbilds
# und waere nach jedem Neubau leer. Ein Volume auf das Datenverzeichnis deckt
# damit Datenbank, Belege und Sicherungen zugleich ab.
RECEIPT_DIR = os.path.join(HERE, "receipts")


# Was der Server ueberhaupt herausgeben darf - der Rest des Verzeichnisses
# (Datenbank, Quelltext, Sicherungen) bleibt unerreichbar.
PUBLIC_FILES = {"index.html", "favicon.ico"}
# Wege, die die Oberflaeche selbst beantwortet (B-10). Der Server liefert
# dafuer index.html aus; welcher Reiter gezeigt wird, entscheidet die Seite.
# Eine feste Liste und kein Platzhalter: so bleibt ein Tippfehler in der
# Adresse ein 404 und wird nicht stillschweigend zur Uebersicht.
UI_ROUTEN = {
    "", "fahrzeug", "ladungen", "tanken", "auffaelligkeiten", "wartung",
    "preise", "verlauf", "bericht", "einstellungen",
}
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


# Aeltere Fahrzeugdaten als 1990 gibt es in diesem Tool nicht - was davor
# liegt, ist ein Tippfehler im Jahr.
FRUEHESTES_JAHR = 1990


def valid_dat(v):
    """Nur ein Tagesdatum wie 2027-03 oder 2027-03-15 durchlassen.

    Prueft ausschliesslich die FORM, nicht den Bereich. Fuer den Bereich gibt
    es valid_dat_vergangen() und valid_dat_zukunft() - siehe dort, warum es
    zwei getrennte Funktionen sind und kein Schalter.

    Die HU wird oft nur mit Monat angegeben - dann wird der Erste ergaenzt,
    damit spaeter gerechnet werden kann.
    """
    s = str(v or "").strip()[:10]
    if re.match(r"^\d{4}-\d{2}$", s):
        s = s + "-01"
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return ""
    # Auch die Form kann unmoeglich sein: 2026-02-31 passt auf das Muster.
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return ""
    return s


def valid_dat_vergangen(v, zukunft_tage=1):
    """Datum eines EREIGNISSES - darf nicht in der Zukunft liegen (B-05).

    Ein Tag Zukunft ist erlaubt: Zeitzonen und eine falsch gestellte Uhr
    sollen keine Eingabe verhindern. Eine Tankung im Jahr 2099 dagegen ist
    ein Tippfehler.
    """
    s = valid_dat(v)
    if not s:
        return ""
    d = datetime.date.fromisoformat(s)
    if d > datetime.date.today() + datetime.timedelta(days=zukunft_tage):
        return ""
    if d.year < FRUEHESTES_JAHR:
        return ""
    return s


def valid_dat_zukunft(v, jahre=50):
    """Datum einer FAELLIGKEIT - darf in der Zukunft liegen (B-05).

    Die HU im Maerz 2027 ist voellig richtig, ein Termin im Jahr 2400 nicht.
    Bewusst eine eigene Funktion und kein Schalter an valid_dat_vergangen():
    bei einem Schalter wird irgendwann die falsche Vorgabe benutzt, und dann
    lehnt das Tool eine voellig richtige HU-Faelligkeit ab.
    """
    s = valid_dat(v)
    if not s:
        return ""
    d = datetime.date.fromisoformat(s)
    if d.year < FRUEHESTES_JAHR or d.year > datetime.date.today().year + jahre:
        return ""
    return s


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


def valid_ts(v, zukunft_tage=1):
    """Zeitstempel pruefen - Form UND Bereich (B-05).

    Vorher wurde nur die Form geprueft, nie der Bereich: eine Tankung am
    31.12.2099 wurde angenommen und als Erfolg gemeldet. Ein Tag Zukunft ist
    erlaubt (Zeitzonen, falsch gestellte Uhr), mehr nicht.
    """
    v = str(v or "").strip()[:40]
    if not TS_RE.match(v):
        return ""
    try:
        d = datetime.date.fromisoformat(v[:10])
    except ValueError:
        return ""
    if d > datetime.date.today() + datetime.timedelta(days=zukunft_tage):
        return ""
    if d.year < FRUEHESTES_JAHR:
        return ""
    return v


RECEIPT_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|jpeg|png|webp|heic|pdf)$", re.I)
# Schriftdateien (B-19). Enge Liste statt Platzhalter: der Ordner soll kein
# allgemeiner Dateispeicher werden.
SCHRIFT_NAME = re.compile(r"^[a-z]+-latin(-ext)?\.woff2$")
# Groesste zulaessige Anfrage: ein Beleg (8 MB) plus Luft fuer Base64 und Text
MAX_BODY = 14 * 1024 * 1024
RECEIPT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "heic": "image/heic", "pdf": "application/pdf"}
MAX_RECEIPT = 8 * 1024 * 1024

# Typerkennung aus dem INHALT, nicht aus dem Namen (B-21).
#
# Geprueft wurde vorher allein die Dateiendung im Namen, den der Client
# mitschickt - der Inhalt wurde nie angesehen. Eine HTML-Datei als "x.jpg"
# hochgeladen landete als .jpg im Ablageort und wurde mit Content-Type
# image/jpeg ausgeliefert. Dass nosniff die Ausfuehrung verhinderte, war
# Glueck und kein Entwurf; der Ablageort wurde damit zum Dateispeicher fuer
# beliebige Inhalte, und der Nutzer merkte erst beim Ansehen, dass sein
# Beleg kein Bild ist.
MAGISCHE_BYTES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"%PDF-", "pdf"),
)


def beleg_name_pruefen(v):
    """Einen Belegnamen aus einer Sicherung annehmen oder verwerfen (B-21).

    Beim Einspielen wurde das Feld ungeprueft uebernommen. Die Oberflaeche
    verzweigte darauf und baute bei einem Wert, der mit "data:" beginnt,
    einen data:-Verweis in die Seite - ein manipulierter Sicherungsstand
    konnte damit beliebige Inhalte in die Oberflaeche bringen. Moderne
    Browser verhindern die oberste Navigation zu data:, aber der Zweig
    gehoert weg, und hier ist die Stelle, an der er nicht entsteht.

    Was nicht auf einen von uns selbst erzeugten Dateinamen passt, wird
    verworfen - die Zeile bleibt, nur ohne Beleg.
    """
    name = str(v or "")[:80]
    return name if RECEIPT_NAME.match(name) else ""


def typ_aus_inhalt(blob):
    """Dateityp am Inhalt erkennen. None, wenn es keiner der erlaubten ist."""
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    # HEIC und Verwandte: der Typ steht im ftyp-Kasten ab Byte 4.
    if blob[4:8] == b"ftyp" and blob[8:12] in (
            b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"):
        return "heic"
    for kennung, typ in MAGISCHE_BYTES:
        if blob.startswith(kennung):
            return typ
    return None


# Erlaubte Einstellungsschluessel (B-22). Vollstaendig aus den DEFAULTS in
# index.html uebernommen, plus homePrices - das ist der Preisverlauf, der
# dort benutzt aber nicht vorbelegt wird. Wer eine Einstellung hinzufuegt,
# ergaenzt sie HIER mit, sonst weist der Server sie ab. Das ist Absicht: so
# faellt ein Tippfehler sofort auf, statt still in der Datenbank zu landen.
ERLAUBTE_EINSTELLUNGEN = {
    "thema",            # Darstellung: system / hell / dunkel (B-11)
    "vatRate",          # Mehrwertsteuersatz in Prozent
    "kwhPer100", "fuelPer100",      # Verbrauchsvorgaben
    "fuelPrice", "homePrice", "homePrices", "useHomePrice",
    "kwhSatz", "satzJahr", "satzQuelle",
    "stationKind",      # Ladepunkt -> home/public
    "invoiceExpect",    # je Anbieter: Abrechnung erwartet?
    "ack",              # weggeklickte Auffaelligkeiten
    "ppkMax", "pplMax", "minKw", "longHours",   # Plausibilitaetsschwellen
    "onboarded",
}
# 64 KB reichen fuer sehr viele Ladepunkte und einen langen Preisverlauf.
MAX_EINSTELLUNGEN_B = 64 * 1024
# Hoechstzahl Zeilen je Import-Aufruf (B-20). Die Oberflaeche stapelt in
# Bloecken dieser Groesse, damit ein grosser Import die Sperre nicht
# minutenlang haelt.
MAX_IMPORT_ZEILEN = 5000


# Hoechstzahl Platzhalter je Abfrage (B-39). Eine IN-Liste mit beliebig
# vielen Platzhaltern laeuft irgendwann gegen SQLITE_MAX_VARIABLE_NUMBER -
# je nach Uebersetzung 999, 32766 oder mehr. Statt sich auf die jeweilige
# Umgebung zu verlassen, wird in Bloecken gearbeitet: 500 ist klein genug
# fuer jede Uebersetzung und gross genug, dass es nicht auffaellt.
BLOCK = 500


def in_bloecken(werte, groesse=BLOCK):
    """Eine Liste in Bloecke zerlegen."""
    for i in range(0, len(werte), groesse):
        yield werte[i:i + groesse]


class RumpfZuGross(Exception):
    """Der Rumpf ueberschreitet MAX_BODY (B-37) - fuehrt zu 413."""

    def __init__(self, groesse=0):
        Exception.__init__(self, "Rumpf zu gross")
        self.groesse = groesse


class LaengeFehlt(Exception):
    """Die Anfrage hat keine brauchbare Content-Length (B-38) - fuehrt zu 411."""

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  name     TEXT NOT NULL UNIQUE,
  settings TEXT NOT NULL DEFAULT '{}',
  created  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cars(
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  nutzer_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  kwh_per_100 REAL NOT NULL DEFAULT 18,
  active      INTEGER NOT NULL DEFAULT 1,
  note        TEXT NOT NULL DEFAULT '',
  created     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions(
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  nutzer_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
  UNIQUE(nutzer_id, tx)
);
CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(nutzer_id, start);
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
    # Geldbetraege als Cent-Ganzzahl (B-04). CLAUDE.md §13 und CLAUDE.md §20
    # verlangen beides: keine Fliesskommazahl fuer Geld, und die Einheit im
    # Namen. Die alten REAL-Spalten bleiben vorerst stehen und werden nur noch
    # mitgeschrieben, nicht gelesen - sie sind der Rueckweg, solange noch
    # jemand auf eine aeltere Fassung zurueckrollen koennte.
    ("sessions", "cost_ct", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "net_ct", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "vat_ct", "INTEGER NOT NULL DEFAULT 0"),
    ("sessions", "invoice_gross_ct", "INTEGER NOT NULL DEFAULT 0"),
    ("fuelings", "cost_ct", "INTEGER NOT NULL DEFAULT 0"),
    ("werkstatt", "cost_ct", "INTEGER NOT NULL DEFAULT 0"),
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
  nutzer_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_wartung_user ON wartung(nutzer_id, car_id);
""", """
CREATE TABLE IF NOT EXISTS werkstatt(
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  nutzer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  car_id  INTEGER REFERENCES cars(id) ON DELETE SET NULL,
  ts      TEXT NOT NULL,
  art     TEXT NOT NULL DEFAULT '',
  cost    REAL NOT NULL DEFAULT 0,
  odo     REAL NOT NULL DEFAULT 0,
  betrieb TEXT NOT NULL DEFAULT '',
  note    TEXT NOT NULL DEFAULT '',
  receipt TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_werkstatt_user ON werkstatt(nutzer_id, car_id);
""", """
CREATE TABLE IF NOT EXISTS fuelings(
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  nutzer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
    "CREATE INDEX IF NOT EXISTS idx_fuel_user ON fuelings(nutzer_id, ts);",
    "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"]

# Indizes, die eine erst durch ADD_COLUMNS entstandene Spalte brauchen - sie
# muessen daher nach den Spalten laufen, nicht mit den Tabellen.
ADD_INDEXES = [
    # Ein Anmeldename gehoert zu genau einem Profil. Leere Namen sind ausgenommen,
    # damit alte Profile ohne Verknuepfung nebeneinander bestehen koennen.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_authentik"
    " ON users(authentik_user) WHERE authentik_user<>''",
]
SCHEMA_VERSION = "6"
# Fassungsnummer der Anwendung, getrennt vom Datenstand oben. Wird von
# --version und /api/version gelesen.
VERSION = "2.6.1"

# --------------------------------------------------- Die Vertrauensgrenze
#
# Die Identitaet kommt als Kopfzeile von Traefik (CLAUDE.md §17), und oben
# steht schon der richtige Satz dazu: der Kopf ist nur so viel wert wie die
# Gewissheit, dass ausschliesslich der Proxy den Server erreicht. Diese
# Gewissheit gab es nicht - im Docker-Netz erreicht jeder Container Port
# 8080 eines anderen direkt (N-44). Am Wiki gemessen: eine Anfrage mit
# "X-Authentik-Groups: wiki-admin" bekam die Verwaltungsdaten.
#
# Traefik setzt am Eingang eine Marke, die nur er und die Werkzeuge kennen.
# Ohne sie wird gar nicht erst nach der Identitaet gefragt.
EINLASS_KOPF = "X-Prolo-Einlass"
EINLASS = os.environ.get("PROLO_EINLASS", "")
EINLASS_B = EINLASS.encode("utf-8")
# Frei bleibt nur die Fassungsabfrage: die Gesundheitspruefung von Docker
# laeuft im Container gegen 127.0.0.1, und aktualisieren.sh fragt sie ueber
# das interne Netz ab - beides am Zugang vorbei, beides ohne
# Schuetzenswertes (§19).
EINLASS_FREI = ("/api/version",)

SESSION_FIELDS = ["tx", "start", "finish", "sec", "kwh", "cost", "net", "vat", "station", "city", "zip",
                  "street", "rate", "partner", "entity", "invoice_no", "invoice_date", "invoice_gross",
                  "src", "manual", "note", "odo",
                  # Cent-Ganzzahlen (B-04) - die eigentlichen Werte.
                  "cost_ct", "net_ct", "vat_ct", "invoice_gross_ct"]
JSON_TO_COL = {"id": "tx", "start": "start", "end": "finish", "sec": "sec", "kwh": "kwh", "cost": "cost",
               "net": "net", "vat": "vat", "station": "station", "city": "city", "zip": "zip",
               "street": "street", "rate": "rate", "partner": "partner", "entity": "entity",
               "invoiceNo": "invoice_no", "invoiceDate": "invoice_date", "invoiceGross": "invoice_gross", "odo": "odo",
               "src": "src", "manual": "manual", "note": "note",
               "costCt": "cost_ct", "netCt": "net_ct", "vatCt": "vat_ct",
               "invoiceGrossCt": "invoice_gross_ct"}
COL_TO_JSON = {v: k for k, v in JSON_TO_COL.items()}
INT_COLS = {"sec", "manual", "cost_ct", "net_ct", "vat_ct", "invoice_gross_ct"}
REAL_COLS = {"kwh", "cost", "net", "vat", "invoice_gross", "odo"}
# Welche Cent-Spalte zu welcher Altspalte gehoert (B-04). Gelesen wird nur die
# Cent-Spalte; die Altspalte wird zum Rueckrollen mitgeschrieben.
GELD_SPALTEN = {
    "sessions": (("cost", "cost_ct"), ("net", "net_ct"), ("vat", "vat_ct"),
                 ("invoice_gross", "invoice_gross_ct")),
    "fuelings": (("cost", "cost_ct"),),
    "werkstatt": (("cost", "cost_ct"),),
}


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


# Tabellen, in denen der Besitzer ab Stand 5 nutzer_id heisst.
BESITZER_TABELLEN = ("cars", "sessions", "fuelings", "wartung", "werkstatt")


def spalten_von(con, tabelle):
    """Spaltennamen einer Tabelle - leere Menge, wenn es sie nicht gibt."""
    try:
        return {r["name"] for r in con.execute("PRAGMA table_info(%s)" % tabelle)}
    except sqlite3.OperationalError:
        return set()


def migration_hinweis(aenderungen):
    """Vor jeder Aenderung, die Daten anfasst, auf die Sicherung hinweisen.

    CLAUDE.md §15: "Vor Migrationen, die Daten veraendern, weist das Tool auf
    die Sicherung hin." Der Hinweis steht bewusst VOR der ersten Aenderung -
    danach waere er wertlos.
    """
    print("=" * 68)
    print("Die Datenbank wird auf Stand %s gebracht." % SCHEMA_VERSION)
    print("Aenderungen: %s" % ", ".join(aenderungen))
    print("Das ist nicht umkehrbar. Ohne aktuelle Sicherung jetzt abbrechen")
    print("(Strg+C) und zuerst /opt/stack/backup.sh laufen lassen.")
    print("=" * 68)


def migration_kopie():
    """Eine Kopie des bisherigen Stands anlegen - der Rueckweg (CLAUDE.md §15).

    Die Kopie bleibt liegen. Sie kostet einmalig den Platz der Datenbank und
    ist das Einzige, was nach einer schiefgegangenen Migration noch hilft.
    """
    kopie = CFG.db + ".vor-stand-%s" % SCHEMA_VERSION
    if os.path.exists(kopie):
        print("Kopie des bisherigen Stands liegt bereits vor: %s" % kopie)
        return kopie
    shutil.copy2(CFG.db, kopie)
    print("Kopie des bisherigen Stands: %s" % kopie)
    return kopie


def init_db():
    """Datenbank anlegen oder auf den aktuellen Stand bringen.

    Ablauf in drei Schritten, die seit B-13 fuer jede Migration gelten und in
    CLAUDE.md §24a festgeschrieben sind:

      1. Hinweis auf die Sicherung - bevor etwas passiert.
      2. Kopie der bisherigen Datei anlegen - der Rueckweg.
      3. Alle Aenderungen in einer Transaktion - alles oder nichts.

    Vorher liefen fuenf ALTER TABLE hintereinander, jedes sofort wirksam.
    Brach der Vorgang nach der dritten Tabelle ab - Stromausfall, voller
    Datentraeger, SIGKILL durch den Container-Neustart -, stand die Datenbank
    in einem Mischzustand: die Haelfte der Tabellen mit nutzer_id, die andere
    noch mit user_id. Der Container startete dann in einer Schleife neu.
    """
    folder = os.path.dirname(os.path.abspath(CFG.db))
    if folder:
        os.makedirs(folder, exist_ok=True)
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    fresh = not os.path.exists(CFG.db) or os.path.getsize(CFG.db) == 0
    with db() as con:
        # ---- Schritt 0: Bestandsaufnahme, ausschliesslich lesend -----------
        # Erst wissen, was zu tun ist - dann darf gewarnt und kopiert werden.
        umbenennen = [t for t in BESITZER_TABELLEN
                      if "user_id" in spalten_von(con, t)
                      and "nutzer_id" not in spalten_von(con, t)]
        fehlend = [(t, sp) for t, sp, _ in ADD_COLUMNS
                   if spalten_von(con, t) and sp not in spalten_von(con, t)]
        alt = con.execute(
            "SELECT v FROM meta WHERE k='schema'").fetchone() if not fresh else None
        # B-04: steht die Geldumstellung noch aus? Der Merker liegt in meta,
        # die Tabelle gibt es bei einer alten Datenbank aber vielleicht noch
        # nicht - darum vorsichtig fragen.
        geld_offen = False
        if not fresh and spalten_von(con, "meta"):
            geld_offen = not con.execute(
                "SELECT v FROM meta WHERE k='geld_in_ct'").fetchone()
        aenderungen = []
        if umbenennen:
            aenderungen.append("user_id wird zu nutzer_id in %s" % ", ".join(umbenennen))
        if fehlend:
            aenderungen.append("neue Spalten: %s"
                               % ", ".join("%s.%s" % ts for ts in fehlend))
        if geld_offen:
            aenderungen.append("Geldbetraege werden auf Cent-Ganzzahlen umgestellt "
                               "(nicht umkehrbar)")

        # ---- Schritt 1 und 2: Hinweis und Kopie, vor der ersten Aenderung --
        # Bei einer neuen Datenbank ist das kein Update, sondern der Normalfall.
        if aenderungen and not fresh:
            migration_hinweis(aenderungen)
            migration_kopie()

        # ---- Schritt 3: Aenderungen, jede Gruppe atomar --------------------
        # Die Umbenennungen muessen VOR BASE_SCHEMA laufen: die Indizes dort
        # stehen auf nutzer_id und wuerden sonst an der alten Spalte scheitern.
        # Sie sind zugleich der Fall, den B-13 beschreibt - darum in einer
        # Transaktion: entweder heissen danach alle fuenf Tabellen nutzer_id
        # oder keine.
        if umbenennen:
            with bulk(con):
                for tab in umbenennen:
                    con.execute("ALTER TABLE %s RENAME COLUMN user_id TO nutzer_id" % tab)
            for tab in umbenennen:
                print("Datenbank ergaenzt: %s.user_id heisst jetzt nutzer_id" % tab)

        # executescript beendet eine offene Transaktion, muss also ausserhalb
        # von bulk() stehen. Unkritisch: CREATE TABLE/INDEX IF NOT EXISTS ist
        # idempotent - ein abgebrochener Lauf wird beim naechsten Start
        # vollendet und kann keinen Mischzustand hinterlassen.
        con.executescript(BASE_SCHEMA)
        for sql in ADD_TABLES:
            con.executescript(sql)

        with bulk(con):
            for table, column, decl in ADD_COLUMNS:
                if column not in spalten_von(con, table):
                    con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, decl))
                    if not fresh:
                        print("Datenbank ergaenzt: %s.%s" % (table, column))
            for sql in ADD_INDEXES:
                con.execute(sql)
            # Erst nachdem die Cent-Spalten da sind (B-04). In derselben
            # Transaktion wie die Spalten: entweder beides oder nichts.
            if geld_umstellen(con) and not fresh:
                print("Datenbank: Geldbetraege sind jetzt Cent-Ganzzahlen.")
            con.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('schema',?)",
                        (SCHEMA_VERSION,))
        if alt and alt["v"] != SCHEMA_VERSION:
            print("Datenbank von Stand %s auf %s gebracht." % (alt["v"], SCHEMA_VERSION))


def num(v, d=0.0):
    """Eine Zahl mit Vorgabewert lesen.

    Bleibt fuer die Stellen, an denen eine Null fachlich richtig ist (etwa ein
    nicht angegebener Kilometerstand). Wo ein fehlender Wert ein Fehler ist,
    gehoert pflicht_zahl() hin - siehe FEHLT und B-05.
    """
    try:
        f = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
        return f if f == f and abs(f) != float("inf") else d
    except (TypeError, ValueError):
        return d


# ----------------------------------------------------------------------
# Eingaben pruefen statt still ersetzen (B-05)
#
# CLAUDE.md §11, woertlich: "Keine stillen Vorgabewerte. Fehlt ein Wert, wird
# das gemeldet - nicht durch eine Null ersetzt. Eine Null in der
# Verbrauchsrechnung ist schlimmer als eine Fehlermeldung, weil sie falsche
# Ergebnisse erzeugt, die niemandem auffallen."
#
# Belegt war: 40 Liter fuer "abc" Euro bei Kilometerstand 9 000 000 wurden
# angenommen, gespeichert und als Erfolg gemeldet - in der Datenbank stand
# cost 0.0. Neun Millionen Kilometer ist das Beispiel aus CLAUDE.md selbst.
# ----------------------------------------------------------------------

FEHLT = object()          # Kennzeichen: der Wert war nicht lesbar


def zahl(v, d=FEHLT):
    """Eine Zahl lesen. Ohne d kommt FEHLT zurueck, nicht 0 (CLAUDE.md §11)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return d
    try:
        f = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return d
    return f if f == f and abs(f) != float("inf") else d


# Plausibilitaetsgrenzen. Bewusst weit gefasst: sie sollen Tippfehler fangen,
# nicht Sonderfaelle verbieten. Wer eine Grenze aendert, aendert sie hier.
GRENZEN = {
    "odo_km":     (0, 2_000_000),     # 2 Mio km faehrt kein PKW
    "liters_l":   (0, 300),           # groesster PKW-Tank unter 200 l
    "kwh":        (0, 400),           # groesster PKW-Akku unter 250 kWh
    "betrag_ct":  (0, 5_000_00),      # 5000 EUR je Einzelvorgang
    "sec":        (0, 7 * 24 * 3600),  # eine Woche am Stueck laden
    "km_frei":    (0, 2_000_000),     # Intervalle und Faelligkeiten
    "monate":     (0, 600),           # 50 Jahre
    "verbrauch_kwh100": (1, 100),
    "verbrauch_l100":   (0.5, 60),
    "akku_kwh":   (0, 250),
    "tank_l":     (0, 200),
}
# Welche Antriebsart welche Verbrauchsgroesse ueberhaupt hat. Steht hier
# neben den Grenzen, weil beides zusammen gelesen werden muss: eine Groesse,
# die es bei dieser Art nicht gibt, wird auch nicht auf Plausibilitaet
# geprueft (N-08). Dieselbe Aufteilung wie KINDS.charge / KINDS.fuel in
# index.html.
LAEDT = {"bev", "phev"}       # hat einen Verbrauch in kWh/100 km
TANKT = {"phev", "petrol", "diesel"}   # hat einen Verbrauch in l/100 km

# Klartextnamen fuer die Fehlermeldung - "odo" sagt einem Nutzer nichts.
FELD_NAMEN = {
    "odo": "Der Kilometerstand", "liters": "Die Litermenge", "kwh": "Die Energiemenge",
    "cost": "Der Betrag", "sec": "Die Ladedauer", "intervallKm": "Das Kilometer-Intervall",
    "intervallMon": "Das Monats-Intervall", "letzteKm": "Der letzte Kilometerstand",
    "faelligKm": "Die Faelligkeit in Kilometern", "km": "Der Kilometerstand",
    "kwhPer100": "Der Verbrauch in kWh/100 km", "lPer100": "Der Verbrauch in l/100 km",
    "battery": "Die Akkugroesse", "tank": "Die Tankgroesse",
}


def _zahl_text(w):
    """Eine Zahl so schreiben, wie sie in der Meldung lesbar ist."""
    return ("%d" % w) if float(w).is_integer() else ("%s" % w)


def pflicht_zahl(data, feld, grenze, pflicht=True):
    """Einen Zahlenwert lesen und pruefen.

    Rueckgabe (wert, fehlertext). fehlertext ist None, wenn alles passt.
    Die Meldung sagt, was zu tun ist (CLAUDE.md §7) - nicht nur, was kaputt ist.
    """
    name = FELD_NAMEN.get(feld, "Der Wert '%s'" % feld)
    roh = data.get(feld)
    # Fehlend und unlesbar sind zwei verschiedene Dinge. pflicht=False heisst
    # "darf fehlen" - nicht "darf Unsinn sein". Wer etwas eintippt, bekommt
    # immer eine Antwort darauf; sonst waere genau die stille Null zurueck,
    # die dieser Befund abschafft.
    if roh is None or (isinstance(roh, str) and not roh.strip()):
        if not pflicht:
            return None, None
        return None, "%s fehlt. Bitte eintragen." % name
    w = zahl(roh)
    if w is FEHLT:
        return None, ("%s ist keine Zahl (%r). Bitte nur Ziffern eingeben, "
                      "Komma oder Punkt als Dezimaltrennzeichen."
                      % (name, str(roh)[:30]))
    lo, hi = GRENZEN[grenze]
    if not (lo <= w <= hi):
        return None, ("%s %s wirkt wie ein Tippfehler - plausibel ist %s bis %s. "
                      "Bitte pruefen." % (name, _zahl_text(w), _zahl_text(lo), _zahl_text(hi)))
    return w, None


def pflicht_cent(data, feld, pflicht=True):
    """Einen Geldbetrag als Cent lesen und pruefen (B-04 und B-05 zusammen)."""
    name = FELD_NAMEN.get(feld, "Der Betrag '%s'" % feld)
    roh = data.get(feld)
    if roh is None or (isinstance(roh, str) and not roh.strip()):
        if not pflicht:
            return None, None
        return None, "%s fehlt. Bitte eintragen." % name
    ct = cent(roh)
    if ct is None:
        return None, ("%s ist keine Zahl (%r). Bitte nur Ziffern eingeben, "
                      "zum Beispiel 12,34." % (name, str(roh)[:30]))
    lo, hi = GRENZEN["betrag_ct"]
    if not (lo <= ct <= hi):
        return None, ("%s %s EUR wirkt wie ein Tippfehler - plausibel ist %s bis "
                      "%s EUR je Vorgang. Bitte pruefen."
                      % (name, _zahl_text(ct / 100.0), _zahl_text(lo / 100),
                         _zahl_text(hi // 100)))
    return ct, None


def verbrauchswerte(kind, data):
    """Verbrauchsangaben einlesen, passend zur Antriebsart (N-08).

    Rueckgabe: (kwh_pro_100, liter_pro_100, fehler). Geprueft wird nur die
    Groesse, die es bei dieser Art ueberhaupt gibt - fuer die andere steht 0,
    und das ist die Aussage "gibt es hier nicht".

    Der Befund dahinter: die Oberflaeche schickt fuer die nicht passende
    Groesse eine 0. pflicht_zahl(..., pflicht=False) laesst ein Feld fehlen,
    prueft eine eingetragene 0 aber gegen die Plausibilitaetsgrenze - und die
    liegt bei 0,5 (l/100 km) bzw. 1 (kWh/100 km). Damit liessen sich bev,
    petrol und diesel gar nicht anlegen, mit einer Meldung ueber ein Feld,
    das der Assistent fuer diese Art nicht anzeigt.
    """
    kwh = lit = None
    if kind in LAEDT:
        kwh, fehler = pflicht_zahl(data, "kwhPer100", "verbrauch_kwh100",
                                   pflicht=False)
        if fehler:
            return None, None, fehler
    if kind in TANKT:
        lit, fehler = pflicht_zahl(data, "lPer100", "verbrauch_l100",
                                   pflicht=False)
        if fehler:
            return None, None, fehler
    return (kwh if kwh is not None else (18.0 if kind in LAEDT else 0.0),
            lit if lit is not None else (7.0 if kind in TANKT else 0.0),
            None)


def pflicht_text(data, feld, grenze, meldung):
    """Ein Pflicht-Textfeld lesen (N-02).

    Das Gegenstueck zu pflicht_zahl/pflicht_cent fuer Text. Vorher stand an
    den Aufrufstellen ein 'or "Vorgabe"' - ein POST ganz ohne Inhalt legte
    damit einen Datensatz mit erfundenem Namen an und meldete 200. CLAUDE.md §11 verbietet stille Vorgabewerte; B-05 hat das fuer Zahlen umgesetzt,
    Text war uebersehen worden.

    Gibt (wert, fehler) zurueck - nie beides. Leerzeichen zaehlen als leer.
    """
    roh = data.get(feld)
    # Bewusst kein 'or ""': die Zahl 0 ist falsch, aber nicht leer. Mit
    # 'or ""' waere ein Auto namens 0 als fehlender Name durchgefallen,
    # eines namens 911 dagegen nicht.
    wert = "" if roh is None else roh if isinstance(roh, str) else str(roh)
    wert = wert.strip()[:grenze]
    if not wert:
        return None, meldung
    return wert, None


# ----------------------------------------------------------------------
# Geld (B-04)
#
# CLAUDE.md §13 und CLAUDE.md §20, beide wortgleich: Geldbetraege niemals
# als Fliesskommazahl. Der Grund ist nicht Kosmetik - drei Tankungen zu 0,10
# EUR und eine zu 8,72 EUR ergaben als REAL summiert 9.020000000000001 statt
# 9,02. Der Fehler ist systematisch, waechst mit der Datenmenge und faellt
# niemandem auf, weil die Anzeige auf zwei Stellen rundet. Das Bordbuch ist
# fuer Nachweise gegenueber Arbeitgeber und Finanzamt gedacht.
#
# Innerhalb des Servers ist ein Betrag darum immer eine Ganzzahl in Cent.
# Euro gibt es nur an zwei Stellen: beim Einlesen einer Eingabe und beim
# Anzeigen.
# ----------------------------------------------------------------------

def cent(v, d=None):
    """Einen Betrag als Cent-Ganzzahl lesen.

    Kein stiller Vorgabewert (CLAUDE.md §11, siehe B-05): ist der Wert nicht
    lesbar, kommt None zurueck - nicht 0. Eine Null in der Kostenrechnung ist
    schlimmer als eine Fehlermeldung, weil sie falsche Ergebnisse erzeugt, die
    niemandem auffallen.

    Gerundet wird kaufmaennisch (ROUND_HALF_UP), nicht wie in Python ueblich
    zur geraden Zahl: 8,995 EUR sind 900 Cent, nicht 899.
    """
    if v is None or (isinstance(v, str) and not v.strip()):
        return d
    try:
        d_ = decimal.Decimal(str(v).replace(",", ".").strip())
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None
    if not d_.is_finite():
        return None
    try:
        return int((d_ * 100).quantize(decimal.Decimal("1"),
                                       rounding=decimal.ROUND_HALF_UP))
    except (decimal.InvalidOperation, decimal.Overflow):
        return None


def ct_lesen(v, d=None):
    """Eine Angabe, die SCHON in Cent ist, als Cent lesen (N-10).

    Der Unterschied zu cent(): cent() bekommt Euro und multipliziert mit 100.
    Wer damit eine Cent-Angabe liest, bekommt den hundertfachen Betrag - und
    genau das ist an zwei Stellen passiert, beim Import von Ladelisten und
    beim Einspielen einer Sicherung. 14,21 EUR wurden zu 1421,00 EUR, eine
    Tankung fuer 74,12 EUR zu 7412,00 EUR.

    Kein stiller Vorgabewert (CLAUDE.md §11): ist der Wert nicht lesbar, kommt
    None zurueck, damit der Aufrufer auf die Euro-Spalte ausweichen kann.
    """
    if v is None or (isinstance(v, str) and not v.strip()):
        return d
    try:
        d_ = decimal.Decimal(str(v).replace(",", ".").strip())
    except (decimal.InvalidOperation, ValueError, TypeError):
        return None
    if not d_.is_finite():
        return None
    try:
        # Bruchteile eines Cents gibt es nicht - kaufmaennisch runden, wie in
        # cent(), damit 1420,5 zu 1421 wird und nicht zu 1420.
        return int(d_.quantize(decimal.Decimal("1"),
                               rounding=decimal.ROUND_HALF_UP))
    except (decimal.InvalidOperation, decimal.Overflow):
        return None


def netto_ct(brutto_ct, satz):
    """Netto aus Brutto ableiten, ohne Fliesskomma.

    satz ist der Mehrwertsteuersatz in Prozent (z. B. 19). Rueckgabe in Cent.
    """
    satz = decimal.Decimal(str(satz))
    return int((decimal.Decimal(int(brutto_ct)) / (1 + satz / 100))
               .quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def mwst_ct(brutto_ct, satz):
    """Mehrwertsteuer als Differenz, nicht als eigene Rechnung.

    So ist netto + mwst == brutto per Konstruktion garantiert und nicht per
    Zufall. Vorher wurde net auf vier Stellen gerundet und vat als cost - net
    gar nicht - dabei entstand eine Mehrwertsteuer mit 16 Nachkommastellen.
    """
    return int(brutto_ct) - netto_ct(brutto_ct, satz)


def satz_aus_settings(user):
    """Mehrwertsteuersatz aus dem Profil, mit 19 % als Rueckfall."""
    try:
        satz = float(json.loads(user["settings"] or "{}").get("vatRate"))
    except (ValueError, TypeError):
        return decimal.Decimal("19")
    if not (0 <= satz < 50):
        return decimal.Decimal("19")
    return decimal.Decimal(str(satz))


def cent_aus_sicherung(satz, ct_schluessel, euro_schluessel):
    """Betrag aus einer Sicherung lesen (B-04).

    Bevorzugt wird die Cent-Angabe. Eine Sicherung aus einer aelteren Fassung
    kennt nur den Euro-Wert - dann wird von dort umgerechnet, sonst liefe ein
    alter Stand auf Nullen ein. CLAUDE.md §15: Datenverlust ist die einzige
    echte Katastrophe.
    """
    w = satz.get(ct_schluessel)
    if w is not None:
        # ct_lesen, nicht cent (N-10): der Wert steht schon in Cent. Mit
        # cent() wurde er ein zweites Mal mit 100 multipliziert - eine
        # Tankung fuer 74,12 EUR kam als 7412,00 EUR zurueck.
        ct = ct_lesen(w)
        if ct is not None:
            return ct
    return cent(satz.get(euro_schluessel), 0) or 0


def import_zeile_werte(s):
    """Eine Importzeile in die Werte fuer SESSION_FIELDS uebersetzen (N-10).

    Eigene Funktion, damit genau dieser Weg pruefbar ist: hier ist der
    hundertfache Betrag entstanden, und eine Mutation an dieser Stelle muss
    einen Test rot machen.

    Geld: bevorzugt wird die Cent-Angabe der Oberflaeche (costCt) - SIE IST
    SCHON CENT und wird mit ct_lesen gelesen, nicht mit cent(). Aeltere
    Dateien kennen nur die Euro-Spalte; von dort wird umgerechnet, damit ein
    alter Export nicht auf Nullen einlaeuft.
    """
    werte = []
    for col in SESSION_FIELDS:
        v = s.get(COL_TO_JSON[col])
        if col in ("cost_ct", "net_ct", "vat_ct", "invoice_gross_ct"):
            w = ct_lesen(v) if v is not None else None
            if w is None:
                w = cent(s.get(COL_TO_JSON[col[:-3]]), 0) or 0
            v = w
        elif col in INT_COLS:
            v = int(num(v))
        elif col in REAL_COLS:
            v = round(num(v), 4)
        else:
            v = "" if v is None else str(v)[:200]
        werte.append(v)
    return werte


def hundertfache_betraege(con):
    """Zeilen finden, in denen die Cent-Spalte hundertfach zu hoch steht (N-10).

    Erkennungsmerkmal ist der Widerspruch zwischen den zwei Spalten: die
    Cent-Spalte ist EXAKT das Hundertfache dessen, was die Euro-Altspalte
    sagt. So eine Zeile kann nicht richtig sein - die beiden sollen dasselbe
    bedeuten. Ein ehrlicher Betrag von 1421,00 EUR hat cost=1421.0 und
    cost_ct=142100, und 142100 ist nicht das Hundertfache von 142100.

    Rueckgabe: Liste (tabelle, spalte_euro, spalte_ct, anzahl, beispiele).
    Es wird nichts geaendert.
    """
    aus = []
    for tab, paare in GELD_SPALTEN.items():
        for euro, ct in paare:
            zeilen = con.execute(
                "SELECT id, %s AS euro, %s AS ct FROM %s "
                "WHERE %s > 0 AND %s = CAST(ROUND(%s * 100) AS INTEGER) * 100"
                % (euro, ct, tab, euro, ct, euro)).fetchall()
            if zeilen:
                aus.append((tab, euro, ct, len(zeilen),
                            [(z["id"], z["euro"], z["ct"]) for z in zeilen[:3]]))
    return aus


# Ab welchem Stueckpreis ein Betrag nicht mehr von dieser Welt ist. Zum
# Vergleich: die Oberflaeche warnt ab 0,85 EUR/kWh und 2,10 EUR/l. Zehn Euro
# je Einheit ist also weit jenseits jedes echten Preises - und wenn derselbe
# Betrag durch hundert geteilt wieder im plausiblen Bereich landet, ist der
# Fall klar.
UNPLAUSIBEL_CT = 1000        # 10,00 EUR je kWh oder Liter
WIEDER_PLAUSIBEL_CT = 400    #  4,00 EUR je kWh oder Liter


def unplausible_betraege(con):
    """Zeilen finden, bei denen der Stueckpreis nur mit Faktor 100 erklaerbar ist.

    Das ist die zweite Spur zu N-10. Beim Einspielen einer Sicherung wurden
    BEIDE Spalten verdorben - die Cent-Spalte und die Euro-Altspalte -, weil
    die Altspalte aus der falschen Cent-Zahl abgeleitet wurde. Der
    Widerspruch zwischen den Spalten fehlt dort also, und es bleibt nur der
    Stueckpreis: 7412,00 EUR fuer 42,8 Liter sind 173 EUR je Liter.

    Das ist ein Indiz, kein Beweis - darum wird es getrennt gemeldet und nur
    auf ausdruecklichen Wunsch berichtigt. Bei Werkstattrechnungen gibt es
    keine Menge zum Vergleich; die bleiben hier aussen vor und stehen im
    Bericht als solche.
    """
    aus = []
    for tab, menge, einheit in (("sessions", "kwh", "kWh"),
                                ("fuelings", "liters", "l")):
        zeilen = con.execute(
            "SELECT id, %s AS menge, cost_ct AS ct FROM %s "
            "WHERE %s > 0 AND cost_ct > 0 "
            "  AND cost_ct * 1.0 / %s > ? "
            "  AND (cost_ct / 100.0) / %s <= ?"
            % (menge, tab, menge, menge, menge),
            (UNPLAUSIBEL_CT, WIEDER_PLAUSIBEL_CT)).fetchall()
        if zeilen:
            aus.append((tab, einheit, len(zeilen),
                        [(z["id"], z["menge"], z["ct"]) for z in zeilen[:3]]))
    return aus


def betraege_richten(con, auch_unplausible=False):
    """Die in hundertfache_betraege() gefundenen Zeilen berichtigen (N-10).

    Gesetzt wird die Cent-Spalte auf den Wert, den die Euro-Altspalte sagt -
    das ist der Betrag, der in der Datei stand. Laeuft in der Transaktion des
    Aufrufers. Rueckgabe: Liste (tabelle, spalte, anzahl).
    """
    aus = []
    for tab, euro, ct, anzahl, _ in hundertfache_betraege(con):
        cur = con.execute(
            "UPDATE %s SET %s = CAST(ROUND(%s * 100) AS INTEGER) "
            "WHERE %s > 0 AND %s = CAST(ROUND(%s * 100) AS INTEGER) * 100"
            % (tab, ct, euro, euro, ct, euro))
        aus.append((tab, ct, cur.rowcount))
    if not auch_unplausible:
        return aus
    for tab, einheit, anzahl, _ in unplausible_betraege(con):
        menge = "kwh" if tab == "sessions" else "liters"
        # Beide Spalten zurechtruecken - hier war auch die Altspalte falsch.
        cur = con.execute(
            "UPDATE %s SET cost_ct = CAST(ROUND(cost_ct / 100.0) AS INTEGER), "
            "              cost = ROUND(cost / 100.0, 2) "
            "WHERE %s > 0 AND cost_ct > 0 "
            "  AND cost_ct * 1.0 / %s > ? "
            "  AND (cost_ct / 100.0) / %s <= ?"
            % (tab, menge, menge, menge),
            (UNPLAUSIBEL_CT, WIEDER_PLAUSIBEL_CT))
        aus.append((tab, "cost_ct (Stueckpreis)", cur.rowcount))
    return aus


def geld_umstellen(con):
    """Einmalige Umrechnung der REAL-Betraege auf Cent-Ganzzahlen (B-04).

    Idempotent ueber einen Merker in meta: ein zweiter Lauf tut nichts. Laeuft
    innerhalb der Transaktion des Aufrufers (B-13).

    ROUND vor CAST ist wesentlich - CAST allein schneidet ab, und 8,99 EUR
    wuerden zu 898 Cent.
    """
    if con.execute("SELECT v FROM meta WHERE k='geld_in_ct'").fetchone():
        return False
    for tab, paare in GELD_SPALTEN.items():
        for alt_sp, ct_sp in paare:
            con.execute("UPDATE %s SET %s = CAST(ROUND(%s * 100) AS INTEGER)"
                        % (tab, ct_sp, alt_sp))
    con.execute("INSERT INTO meta(k,v) VALUES('geld_in_ct','1')")
    return True


def gruppen_aus_kopf(roh):
    """Gruppen aus X-Authentik-Groups lesen (B-30).

    Authentik trennt die Gruppen mit einem Pipe ("foo|bar|baz"), nicht mit
    Komma - das steht so im Wiki-Server dokumentiert, und das Bordbuch trennte
    trotzdem nur an Komma. Damit war "a|bordbuch-admin|c" EINE Gruppe namens
    "a|bordbuch-admin|c", ist_admin() schlug fehl und die Gesamtsicherung waere
    fuer niemanden erreichbar gewesen.

    Komma und Semikolon werden zusaetzlich angenommen, damit ein Wechsel der
    Identitaetsinstanz nicht alles lahmlegt. Modulweite Funktion, damit sie
    ohne HTTP pruefbar ist.
    """
    return {g.strip() for g in re.split(r"[|,;]", roh or "") if g.strip()}


def mail_kurz(m):
    """a****e@beispiel.de - genug zum Unterscheiden, zu wenig zum Sammeln (B-06).

    Bei aehnlichen Anzeigenamen muss man die richtige Person treffen koennen.
    Dafuer genuegt ein Umriss der Adresse; die vollstaendige Adresse ist ein
    Personendatum und hat in einer Trefferliste nichts zu suchen.
    """
    m = str(m or "")
    if "@" not in m:
        return ""
    lokal, _, wo = m.partition("@")
    if len(lokal) <= 2:
        return "*" * len(lokal) + "@" + wo
    return lokal[0] + "*" * (len(lokal) - 2) + lokal[-1] + "@" + wo


def row_session(r):
    out = {"dbid": r["id"], "carId": r["car_id"]}
    for col in SESSION_FIELDS:
        out[COL_TO_JSON[col]] = r[col]
    out["manual"] = bool(r["manual"])
    # Die Euro-Felder werden aus den Cent-Feldern abgeleitet, nicht aus der
    # Altspalte gelesen (B-04 Schritt 5). So koennen die beiden Darstellungen
    # nicht auseinanderlaufen, auch wenn eine alte Zeile noch einen
    # abweichenden REAL-Wert traegt. Sie dienen nur der Anzeige - gerechnet
    # wird in der Oberflaeche mit den Cent-Feldern.
    for euro, ct in (("cost", "cost_ct"), ("net", "net_ct"), ("vat", "vat_ct"),
                     ("invoiceGross", "invoice_gross_ct")):
        out[euro] = r[ct] / 100.0
    return out


def row_fuel(r):
    return {"dbid": r["id"], "carId": r["car_id"], "ts": r["ts"], "liters": r["liters"],
            # Cent ist der Wert, Euro nur die Anzeige (B-04).
            "costCt": r["cost_ct"], "cost": r["cost_ct"] / 100.0,
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


def belege_loeschen(con, nutzer_id, behalten=()):
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
        for r in con.execute("SELECT receipt FROM %s WHERE nutzer_id=? AND receipt<>''" % tabelle,
                             (nutzer_id,)):
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
    # Wird waehrend eines schreibenden Aufrufs auf True gesetzt (B-20): dann
    # merkt sich send_json() die Antwort, statt sie zu senden. Gesendet wird
    # erst, nachdem die Sperre freigegeben ist.
    _sammeln = False
    _antwort = None

    def send_json(self, obj, code=200):
        if self._sammeln:
            # Nur die ERSTE Antwort zaehlt - die Handler benutzen durchgaengig
            # "return self.send_json(...)", eine zweite kann es also nicht
            # geben. Falls doch, waere die erste die richtige.
            if self._antwort is None:
                self._antwort = (obj, code)
            return
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        """Den Rumpf als JSON lesen.

        Wirft eigene Ausnahmen, damit do_POST() die Faelle unterscheiden kann
        (B-37, B-38). Vorher flog fuer alles ein ValueError, und do_POST fing
        pauschal alles ab und meldete "Die Anfrage war keine gueltige
        JSON-Nachricht." - bei einem zu grossen Rumpf war das schlicht falsch
        und schickte den Nutzer auf die Suche nach einem Tippfehler, den es
        nicht gab.
        """
        roh = self.headers.get("Content-Length")
        if roh is None:
            # Ohne Content-Length landete n bei 0 und damit bei einem LEEREN
            # Objekt - der Aufruf lief durch, als haette jemand {} geschickt
            # (B-38). Bei einer Anfrage mit chunked transfer-encoding ist das
            # der Normalfall und fuehrte zu voellig unverstaendlichem
            # Verhalten: gespeichert wurde nichts, gemeldet auch nichts.
            raise LaengeFehlt()
        try:
            n = int(roh)
        except (TypeError, ValueError):
            raise LaengeFehlt()
        if n < 0:
            raise LaengeFehlt()
        if n == 0:
            return {}
        if n > MAX_BODY:
            raise RumpfZuGross(n)
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def ich(self, con, anlegen=False):
        """Wer fragt? Kommt ausschliesslich aus dem Kopf, den der Proxy setzt.

        Bordbuch legt niemanden an und prueft kein Passwort - das macht die
        vorgeschaltete Identitaetsinstanz.

        anlegen=False (Vorgabe): ist der Name unbekannt, kommt None zurueck.
        anlegen=True: dann entsteht das Profil.

        Vorher legte JEDER Aufruf das Profil an, auch ein GET (B-42). Eine
        GET-Anfrage sollte nichts schreiben - /api/state tat es, und schon
        ein versehentlicher Aufruf mit einem fremden Anmeldenamen hinterliess
        eine Profilzeile. Angelegt wird jetzt beim ersten SCHREIBENDEN
        Zugriff; die Oberflaeche stoesst ihn beim ersten Start ausdruecklich
        ueber /api/anmelden an.
        """
        # Kopfnamen sind laut HTTP unabhaengig von Gross- und Kleinschreibung;
        # Traefik schickt sie als X-Authentik-Username.
        name = (self.headers.get("X-Authentik-Username") or "").strip()[:60]
        if not name:
            return None
        mail = (self.headers.get("X-Authentik-Email") or "").strip()[:120]
        # Der volle Anzeigename kommt eigens mit; ohne ihn bleibt der Anmeldename.
        voll = (self.headers.get("X-Authentik-Name") or "").strip()[:60]
        row = con.execute("SELECT * FROM users WHERE authentik_user=?", (name,)).fetchone()
        if not row and not anlegen:
            return None
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
        return gruppen_aus_kopf(self.headers.get("X-Authentik-Groups"))

    def ist_admin(self):
        return CFG.admin_gruppe in self.gruppen()

    def profil(self, con, anlegen=False):
        """(ich, arbeitsprofil, darf_schreiben). Ohne Kopf gibt es nichts.
        Das Arbeitsprofil ist das eigene - oder ein fremdes, fuer das eine
        Freigabe vorliegt. anlegen siehe ich() (B-42)."""
        ich = self.ich(con, anlegen)
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
        """True, wenn die Anfrage nicht von dieser Seite selbst stammt.

        Ohne diese Pruefung koennte eine beliebige Webseite im Browser eines
        Mitbewohners Profile anlegen oder loeschen - die Endpunkte dafuer
        brauchen naemlich keinen eigenen Kopf, der einen Preflight erzwingt.

        "same-site" wird bewusst NICHT akzeptiert (B-03): alle Tools liegen
        unter prolo.me, und eine Nachbar-Subdomain (Wiki, n8n) ist fuer
        Bordbuch genauso fremd wie eine beliebige Seite im Netz. Das Wiki
        liefert per Konstruktion fremdes HTML im eigenen Origin aus - eine
        eingespielte Wiki-Seite ist also ausfuehrbarer Code auf
        wiki.prolo.me und duerfte sonst hier hereinschreiben.
        """
        ziel = self.headers.get("Sec-Fetch-Site")
        if ziel is not None:
            return ziel != "same-origin"        # alles andere ist fremd
        # Aeltere Browser ohne Sec-Fetch-Site: ueber Origin/Referer entscheiden.
        herkunft = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not herkunft:
            # Bisher galt hier "kein Origin = erlaubt", mit der Begruendung,
            # curl schicke nichts. Genau diesen Zustand kann ein Angreifer
            # aber erzeugen - darum jetzt umgekehrt: kein Nachweis = abweisen.
            # Werkzeuge auf der Kommandozeile setzen kuenftig
            #   -H "Origin: https://bordbuch.prolo.me"
            # oder gleich -H "Sec-Fetch-Site: same-origin".
            return True
        return urlparse(herkunft).netloc != (self.headers.get("Host") or "")

    # ---------------- GET ----------------
    def einlass_pruefen(self, path):
        """Kam die Anfrage ueber den Zugang dieses Servers? (N-44)

        Laeuft vor allem anderen, auch vor der Identitaet. Begruendung
        oben bei EINLASS_KOPF.
        """
        if path in EINLASS_FREI:
            return True
        # Auf Bytes vergleichen: ein Umlaut in der Kopfzeile wuerde sonst
        # einen TypeError werfen statt eine 401.
        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")
        if hmac.compare_digest(mit, EINLASS_B):
            return True
        self.send_json({"error": "Diese Anfrage kam nicht ueber den Zugang "
                                 "dieses Servers. Das Bordbuch ist unter "
                                 "https://bordbuch.prolo.me erreichbar."}, 401)
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if not self.einlass_pruefen(path):
            return
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
        if path == "/api/freigabe/suche":
            return self.freigabe_suche(urlparse(self.path).query)
        if path.startswith("/api/"):
            return self.send_json({"error": "unbekannter Endpunkt"}, 404)
        return self.static(path)

    # Wie viele Treffer eine Suche hoechstens zurueckgibt. Klein genug, dass
    # sich daraus kein Verzeichnis abschoepfen laesst, gross genug fuer den
    # Alltag.
    SUCHE_MAX = 10
    SUCHE_MIN_ZEICHEN = 3

    def freigabe_suche(self, query):
        """Profile fuer den Freigabe-Dialog suchen (B-06).

        Verlangt mindestens drei Zeichen, gibt hoechstens zehn Treffer und die
        E-Mail nur verkuerzt. Damit bleibt der Dialog benutzbar, ohne dass sich
        das Personenverzeichnis abgreifen laesst.
        """
        from urllib.parse import parse_qs
        q = (parse_qs(query or "").get("q") or [""])[0].strip()[:60]
        with db() as con:
            ich = self.ich(con)
            if not ich:
                return self.send_json(
                    {"error": "Nicht angemeldet. Bordbuch erwartet die Anmeldung "
                              "ueber die vorgeschaltete Identitaetsinstanz."}, 401)
            if len(q) < self.SUCHE_MIN_ZEICHEN:
                return self.send_json(
                    {"error": "Bitte mindestens %d Zeichen eingeben - Name oder "
                              "E-Mail-Adresse der Person, die du freigeben willst."
                              % self.SUCHE_MIN_ZEICHEN}, 400)
            # LIKE mit ESCAPE, damit % und _ in der Eingabe keine Platzhalter
            # sind - sonst waere "%" eine Suche nach allen.
            muster = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            treffer = [{"id": r["id"], "name": r["name"], "email": mail_kurz(r["email"])}
                       for r in con.execute(
                           "SELECT id,name,email FROM users"
                           " WHERE id<>? AND (name LIKE ? ESCAPE '\\'"
                           "               OR email LIKE ? ESCAPE '\\')"
                           " ORDER BY name LIMIT ?",
                           (ich["id"], muster, muster, self.SUCHE_MAX))]
            return self.send_json({"treffer": treffer, "grenze": self.SUCHE_MAX})

    def backup(self):
        """Vollstaendige Sicherung eines Profils als JSON."""
        with db() as con:
            ich, user, _ = self.profil(con)
            if not ich:
                return self.send_json({"error": "Nicht angemeldet."}, 401)
            # Gesichert wird immer das eigene Profil, nie ein freigegebenes.
            user = ich
            cars = [dict(r) for r in con.execute("SELECT * FROM cars WHERE nutzer_id=?", (user["id"],))]
            sess = [dict(r) for r in con.execute("SELECT * FROM sessions WHERE nutzer_id=?", (user["id"],))]
            fuel = [dict(r) for r in con.execute("SELECT * FROM fuelings WHERE nutzer_id=?", (user["id"],))]
            wart = [dict(r) for r in con.execute("SELECT * FROM wartung WHERE nutzer_id=?", (user["id"],))]
            werk = [dict(r) for r in con.execute("SELECT * FROM werkstatt WHERE nutzer_id=?", (user["id"],))]
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
            con.execute("DELETE FROM sessions WHERE nutzer_id=?", (user["id"],))
            con.execute("DELETE FROM fuelings WHERE nutzer_id=?", (user["id"],))
            # Wartungsplan und Werkstattrechnungen gehoeren dazu - sonst blieben
            # sie stehen, waehrend alles andere ersetzt wird, und die neuen
            # Eintraege liefen in die Dublettenpruefung.
            con.execute("DELETE FROM wartung WHERE nutzer_id=?", (user["id"],))
            con.execute("DELETE FROM werkstatt WHERE nutzer_id=?", (user["id"],))
            con.execute("DELETE FROM cars WHERE nutzer_id=?", (user["id"],))

        # Autos werden ueber den Namen zusammengefuehrt. Sonst entstehen beim
        # zweiten Einspielen Doppel wie "Golf" und "Golf".
        have = {r["name"]: r["id"] for r in
                con.execute("SELECT id,name FROM cars WHERE nutzer_id=?", (user["id"],))}
        carmap, cars_new = {}, 0
        for c in payload.get("cars") or []:
            # Hier bleibt der Vorgabewert - anders als in car_save (N-02).
            # Das ist eine Wiederherstellung: die Daten gibt es bereits, sie
            # werden nur zurueckgeholt. Eine alte Sicherung mit einem
            # namenlosen Auto darf nicht dazu fuehren, dass die gesamte
            # Wiederherstellung abbricht - ein Auto namens "Auto" ist
            # deutlich besser als verlorene Tankungen daran.
            name = str(c.get("name") or "Auto")[:60]
            if name in have:
                carmap[c.get("id")] = have[name]
                continue
            kind = c.get("kind") if c.get("kind") in ("bev", "phev", "petrol", "diesel") else "bev"
            new = con.execute("""INSERT INTO cars(nutzer_id,name,kind,kwh_per_100,l_per_100,active,note,plate,
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
        cols = ",".join(["nutzer_id", "car_id"] + SESSION_FIELDS)
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
            f_ct = cent_aus_sicherung(f, "cost_ct", "cost")
            key = (user["id"], f.get("ts"), f_ct, round(num(f.get("liters")), 3))
            if con.execute("""SELECT 1 FROM fuelings WHERE nutzer_id=? AND ts=? AND
                              cost_ct=? AND ROUND(liters,3)=?""", key).fetchone():
                fuel_dup += 1
                continue
            con.execute("""INSERT INTO fuelings(nutzer_id,car_id,ts,liters,cost,cost_ct,odo,full,station,note,receipt)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], carmap.get(f.get("car_id")), f.get("ts"), num(f.get("liters")),
                         f_ct / 100.0, f_ct, num(f.get("odo")), 1 if f.get("full", 1) else 0,
                         str(f.get("station") or "")[:120], str(f.get("note") or "")[:200],
                         beleg_name_pruefen(f.get("receipt"))))
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
            if con.execute("""SELECT 1 FROM wartung WHERE nutzer_id=? AND art=?
                              AND IFNULL(car_id,0)=IFNULL(?,0)""",
                           (user["id"], art[:80], carmap.get(w.get("car_id")))).fetchone():
                wart_dup += 1
                continue
            con.execute("""INSERT INTO wartung(nutzer_id,car_id,art,intervall_km,intervall_mon,
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
            w_ct = cent_aus_sicherung(w, "cost_ct", "cost")
            if con.execute("""SELECT 1 FROM werkstatt WHERE nutzer_id=? AND ts=? AND cost_ct=?
                              AND art=?""",
                           (user["id"], ts, w_ct,
                            str(w.get("art") or "")[:80])).fetchone():
                werk_dup += 1
                continue
            con.execute("""INSERT INTO werkstatt(nutzer_id,car_id,ts,art,cost,cost_ct,odo,betrieb,note,receipt)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], carmap.get(w.get("car_id")), ts, str(w.get("art") or "")[:80],
                         w_ct / 100.0, w_ct, num(w.get("odo")), str(w.get("betrieb") or "")[:120],
                         str(w.get("note") or "")[:200], beleg_name_pruefen(w.get("receipt"))))
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
        # Geprueft statt still ersetzt (B-05). Alle vier Zahlen sind freiwillig
        # (0 = spielt keine Rolle), duerfen aber nicht unlesbar sein.
        for feld, grenze in (("intervallKm", "km_frei"), ("intervallMon", "monate"),
                             ("letzteKm", "odo_km"), ("faelligKm", "km_frei")):
            _, fehler = pflicht_zahl(data, feld, grenze, pflicht=False)
            if fehler:
                return self.send_json({"error": fehler}, 400)
        # letztesDat ist ein Ereignis (die letzte Wartung), faelligDat eine
        # Faelligkeit (die HU im Maerz 2027) - darum zwei verschiedene
        # Pruefungen. Mit einem Schalter wuerde hier irgendwann die falsche
        # Vorgabe benutzt und eine richtige HU-Faelligkeit abgelehnt.
        letztes = valid_dat_vergangen(data.get("letztesDat"))
        if data.get("letztesDat") and not letztes:
            return self.send_json(
                {"error": "Das Datum der letzten Wartung liegt ausserhalb des "
                          "plausiblen Bereichs (ab %d, nicht in der Zukunft). "
                          "Bitte pruefen." % FRUEHESTES_JAHR}, 400)
        faellig = valid_dat_zukunft(data.get("faelligDat"))
        if data.get("faelligDat") and not faellig:
            return self.send_json(
                {"error": "Die Faelligkeit liegt ausserhalb des plausiblen "
                          "Bereichs (hoechstens 50 Jahre voraus). Bitte pruefen."}, 400)
        werte = (car_id, art,
                 max(0.0, num(data.get("intervallKm"))),
                 max(0.0, num(data.get("intervallMon"))),
                 max(0.0, num(data.get("letzteKm"))),
                 letztes,
                 max(0.0, num(data.get("faelligKm"))),
                 faellig,
                 str(data.get("notiz") or "")[:200],
                 1 if data.get("aktiv", True) else 0)
        dbid = data.get("dbid")
        if dbid:
            cur = con.execute("""UPDATE wartung SET car_id=?,art=?,intervall_km=?,intervall_mon=?,
                                 letzte_km=?,letztes_dat=?,faellig_km=?,faellig_dat=?,notiz=?,aktiv=?
                                 WHERE id=? AND nutzer_id=?""", werte + (dbid, user["id"]))
            if not cur.rowcount:
                return self.send_json({"error": "Wartungseintrag nicht gefunden"}, 404)
            return self.send_json({"ok": True, "id": dbid})
        neu = con.execute("""INSERT INTO wartung(nutzer_id,car_id,art,intervall_km,intervall_mon,
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
        row = con.execute("SELECT * FROM wartung WHERE id=? AND nutzer_id=?",
                          (data.get("dbid"), user["id"])).fetchone()
        if not row:
            return self.send_json({"error": "Wartungseintrag nicht gefunden"}, 404)
        km_w, fehler = pflicht_zahl(data, "km", "odo_km", pflicht=False)   # B-05
        if fehler:
            return self.send_json({"error": fehler}, 400)
        km = km_w or 0.0
        # "Erledigt" ist ein Ereignis - also nicht in der Zukunft.
        dat = valid_dat_vergangen(data.get("dat"))
        if data.get("dat") and not dat:
            return self.send_json(
                {"error": "Das Datum der Erledigung liegt ausserhalb des plausiblen "
                          "Bereichs (ab %d, nicht in der Zukunft). Bitte pruefen."
                          % FRUEHESTES_JAHR}, 400)
        dat = dat or datetime.date.today().isoformat()
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
                       WHERE id=? AND nutzer_id=?""",
                    (km or row["letzte_km"], dat, f_km, f_dat, row["id"], user["id"]))
        # Logbucheintrag samt Kosten. Auch ohne Betrag wird er angelegt: dass
        # der TUEV im Maerz 2024 gemacht wurde, ist die Information wert.
        beleg = ""
        try:
            beleg = self.save_receipt(data) or ""
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        kosten_ct, fehler = pflicht_cent(data, "cost", pflicht=False)   # B-04, B-05
        if fehler:
            return self.send_json({"error": fehler}, 400)
        kosten_ct = kosten_ct or 0
        log_id = con.execute("""INSERT INTO werkstatt(nutzer_id,car_id,ts,art,cost,cost_ct,odo,
                                betrieb,note,receipt,wart_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                             (user["id"], row["car_id"], dat + "T12:00:00", row["art"],
                              kosten_ct / 100.0, kosten_ct, km,
                              str(data.get("betrieb") or "")[:120],
                              str(data.get("note") or "")[:200], beleg, row["id"])).lastrowid
        return self.send_json({"ok": True, "log": log_id})

    def service_delete(self, con, user, data):
        cur = con.execute("DELETE FROM wartung WHERE id=? AND nutzer_id=?",
                          (data.get("dbid"), user["id"]))
        if not cur.rowcount:
            return self.send_json(
                {"error": "Diesen Wartungseintrag gibt es nicht mehr. "
                          "Lade die Seite neu."}, 404)
        return self.send_json({"ok": True, "geloescht": cur.rowcount})

    # ------------------------------------------------------------------
    # Werkstattkosten - mit Rechnung als Bild oder PDF, wie bei Tankbelegen
    # ------------------------------------------------------------------
    def shop_save(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        # Eine Werkstattrechnung ist ein Ereignis - also nicht in der Zukunft.
        ts = valid_ts(data.get("ts")) or (valid_dat_vergangen(data.get("ts")) + "T12:00:00"
                                          if valid_dat_vergangen(data.get("ts")) else "")
        if not ts:
            return self.send_json(
                {"error": "Das Datum fehlt oder liegt ausserhalb des plausiblen "
                          "Bereichs (ab %d, hoechstens einen Tag in der Zukunft). "
                          "Bitte pruefen." % FRUEHESTES_JAHR}, 400)
        cost_ct, fehler = pflicht_cent(data, "cost", pflicht=False)   # B-05
        if fehler:
            return self.send_json({"error": fehler}, 400)
        odo_w, fehler = pflicht_zahl(data, "odo", "odo_km", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        cost_ct = cost_ct or 0
        cost = cost_ct / 100.0                       # nur noch mitgeschrieben
        art = str(data.get("art") or "").strip()[:80]
        if cost_ct <= 0 and not art:
            return self.send_json(
                {"error": "Bitte den Betrag oder die Art der Arbeit angeben - sonst "
                          "steht in der Liste nur ein Datum."}, 400)
        try:
            beleg = self.save_receipt(data)
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        dbid = data.get("dbid")
        werte = (car_id, ts, art, cost, cost_ct, odo_w or 0.0,
                 str(data.get("betrieb") or "")[:120], str(data.get("note") or "")[:200],
                 int(num(data.get("wartId"))))
        if dbid:
            alt = con.execute("SELECT receipt FROM werkstatt WHERE id=? AND nutzer_id=?",
                              (dbid, user["id"])).fetchone()
            if not alt:
                return self.send_json({"error": "Rechnung nicht gefunden"}, 404)
            if beleg and alt["receipt"]:
                beleg_datei_weg(alt["receipt"])
            con.execute("""UPDATE werkstatt SET car_id=?,ts=?,art=?,cost=?,cost_ct=?,odo=?,betrieb=?,
                           note=?,wart_id=?,receipt=? WHERE id=? AND nutzer_id=?""",
                        werte + (beleg or alt["receipt"] or "", dbid, user["id"]))
            return self.send_json({"ok": True, "id": dbid})
        # save_receipt() gibt None zurueck, wenn keine Datei mitkam - die Spalte
        # ist aber NOT NULL, darum der leere Text.
        neu = con.execute("""INSERT INTO werkstatt(nutzer_id,car_id,ts,art,cost,cost_ct,odo,betrieb,
                             note,wart_id,receipt) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (user["id"],) + werte + (beleg or "",)).lastrowid
        return self.send_json({"ok": True, "id": neu})

    def shop_delete(self, con, user, data):
        row = con.execute("SELECT receipt FROM werkstatt WHERE id=? AND nutzer_id=?",
                          (data.get("dbid"), user["id"])).fetchone()
        cur = con.execute("DELETE FROM werkstatt WHERE id=? AND nutzer_id=?",
                          (data.get("dbid"), user["id"]))
        if not cur.rowcount:
            return self.send_json(
                {"error": "Diese Rechnung gibt es nicht mehr. Lade die Seite neu."}, 404)
        # Erst nach dem Loeschen der Zeile - sonst waere die Datei weg,
        # obwohl der Eintrag noch stuende.
        if row and row["receipt"]:
            beleg_datei_weg(row["receipt"])
        return self.send_json({"ok": True, "geloescht": cur.rowcount})

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
                             con.execute("SELECT * FROM cars WHERE nutzer_id=?", (u["id"],))],
                    "sessions": [dict(r) for r in
                                 con.execute("SELECT * FROM sessions WHERE nutzer_id=?", (u["id"],))],
                    "fuelings": [dict(r) for r in
                                 con.execute("SELECT * FROM fuelings WHERE nutzer_id=?", (u["id"],))],
                    "wartung": [dict(r) for r in
                                con.execute("SELECT * FROM wartung WHERE nutzer_id=?", (u["id"],))],
                    "werkstatt": [dict(r) for r in
                                  con.execute("SELECT * FROM werkstatt WHERE nutzer_id=?", (u["id"],))],
                    "settings": einst,
                })
            return self.send_json({"ladelog": SCHEMA_VERSION, "typ": "gesamt",
                                   "erstellt": __import__("datetime").datetime.now()
                                   .isoformat(timespec="seconds"),
                                   "profile": profile})

    def admin_import(self, con, user, data):
        """Eine Gesamtsicherung einspielen.

        mode="replace" loescht ALLE Profile und baut die Datenbank neu auf,
        mode="merge" ergaenzt: bekannte Profile werden ueber den Namen
        gefunden, unbekannte neu angelegt. Alles in einer Transaktion - bricht
        etwas ab, bleibt die Datenbank wie vorher.
        """
        # Die Berechtigungspruefung stand bis B-35 VOR diesem Text. Damit war
        # die Zeichenkette kein Docstring mehr, sondern eine wirkungslose
        # Anweisung mitten in der Funktion: help(), __doc__ und jedes
        # Werkzeug, das Docstrings liest, sahen nichts.
        if not self.ist_admin():
            return self.send_json({"error": "Dafuer fehlt die Gruppe '%s'." % CFG.admin_gruppe}, 403)
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

    def state(self):
        with db() as con:
            ich, user, darf_schreiben = self.profil(con)      # kein Anlegen (B-42)
            if not ich:
                # Zwei verschiedene Faelle sauber trennen: gar kein Kopf
                # (nicht angemeldet) oder ein Kopf ohne Profil (erster
                # Besuch). Im zweiten Fall ist das kein Fehler - die
                # Oberflaeche legt das Profil dann ueber POST /api/anmelden
                # an, statt dass ein GET es stillschweigend tut.
                if (self.headers.get("X-Authentik-Username") or "").strip():
                    return self.send_json({"neu": True, "schema": SCHEMA_VERSION})
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
            # Hier stand bis B-06 eine vollstaendige Liste aller Profile samt
            # E-Mail-Adresse - bei JEDEM Seitenaufbau, fuer JEDEN angemeldeten
            # Nutzer, ohne jede Freigabe. Das ist eine Personendatenliste, die
            # jeder abgreifen konnte, auch wer nur Zugriff auf das Bordbuch
            # bekommen sollte und nicht auf das Personenverzeichnis.
            # Gebraucht wird sie nur im Freigabe-Dialog - dafuer gibt es jetzt
            # GET /api/freigabe/suche?q=..., das gezielt sucht und die Adresse
            # verkuerzt ausgibt.
            cars = [{"id": r["id"], "name": r["name"], "kind": r["kind"], "kwhPer100": r["kwh_per_100"],
                     "lPer100": r["l_per_100"], "battery": r["battery"], "tank": r["tank"], "plate": r["plate"],
                     "active": bool(r["active"]), "note": r["note"]}
                    for r in con.execute("SELECT * FROM cars WHERE nutzer_id=? ORDER BY active DESC, id",
                                         (user["id"],))]
            sess = [row_session(r) for r in con.execute(
                "SELECT * FROM sessions WHERE nutzer_id=? ORDER BY start", (user["id"],))]
            fuel = [row_fuel(r) for r in con.execute(
                "SELECT * FROM fuelings WHERE nutzer_id=? ORDER BY ts", (user["id"],))]
            try:
                settings = json.loads(user["settings"] or "{}")
            except ValueError:
                settings = {}
            return self.send_json({"ich": {"id": ich["id"], "name": ich["name"],
                                           "anmeldung": ich["authentik_user"],
                                           "email": ich["email"],
                                           "abmelden": CFG.abmelde_pfad,
                                           # Gruppen kommen aus dem Kopf, nicht aus der
                                           # Datenbank - sie gehoeren der Anmeldung.
                                           "gruppen": sorted(self.gruppen()),
                                           "adminGruppe": CFG.admin_gruppe,
                                           "admin": self.ist_admin()},
                                   "user": {"id": user["id"], "name": user["name"]},
                                   "profile": profile, "schreiben": darf_schreiben,
                                   "freigabenMeine": meine, "freigabenFuerMich": fuerMich,
                                   "cars": cars, "sessions": sess, "fuelings": fuel,
                                   "service": [dict(r) for r in con.execute(
                                       """SELECT id AS dbid,car_id AS carId,art,intervall_km AS intervallKm,
                                          intervall_mon AS intervallMon,letzte_km AS letzteKm,
                                          letztes_dat AS letztesDat,faellig_km AS faelligKm,
                                          faellig_dat AS faelligDat,notiz,aktiv
                                          FROM wartung WHERE nutzer_id=? ORDER BY id""",
                                       (user["id"],))],
                                   # cost_ct ist der Wert, cost nur die Anzeige (B-04).
                                   "shop": [dict(r, cost=r["costCt"] / 100.0) for r in con.execute(
                                       """SELECT id AS dbid,car_id AS carId,ts,art,cost,
                                          cost_ct AS costCt,odo,betrieb,
                                          note,receipt,wart_id AS wartId
                                          FROM werkstatt WHERE nutzer_id=? ORDER BY ts""",
                                       (user["id"],))],
                                   "settings": settings, "schema": SCHEMA_VERSION})

    # ---------------- POST ----------------
    def do_POST(self):
        path = urlparse(self.path).path
        if not self.einlass_pruefen(path):
            return
        # Der eigentliche Riegel gegen Formularangriffe (B-03): application/json
        # ist KEINE CORS-simple-request. Der Browser erzwingt dafuer einen
        # Preflight, und der scheitert, weil Bordbuch keine CORS-Kopfzeilen
        # sendet. Ohne diese Pruefung genuegt ein gewoehnliches Formular mit
        # enctype="text/plain" - dafuer braucht ein Angreifer nicht einmal
        # JavaScript.
        typ = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if typ != "application/json":
            return self.send_json(
                {"error": "Diese Schnittstelle nimmt nur application/json entgegen. "
                          "Bitte den Kopf Content-Type: application/json setzen."}, 415)
        try:
            data = self.body_json()
        except RumpfZuGross as e:
            # 413, nicht 400 (B-37): die Meldung kam bisher nie an, weil der
            # ValueError im Sammelfang landete.
            return self.send_json(
                {"error": "Die Anfrage ist zu gross (%d MB, Grenze %d MB). Bei "
                          "einem Beleg hilft ein kleineres Foto; bei einem "
                          "Import teilt die Oberflaeche die Datei selbst auf."
                          % (e.groesse // 1024 // 1024, MAX_BODY // 1024 // 1024)}, 413)
        except LaengeFehlt:
            # 411, nicht ein leeres Objekt (B-38).
            return self.send_json(
                {"error": "Der Anfrage fehlt die Angabe Content-Length. "
                          "Bordbuch nimmt keine Anfragen mit unbekannter "
                          "Laenge entgegen (kein chunked transfer-encoding)."}, 411)
        except Exception:
            return self.send_json({"error": "Die Anfrage war keine gueltige JSON-Nachricht."}, 400)
        if not isinstance(data, dict):
            # Alle Handler arbeiten mit data.get(...) - ein Array oder String
            # wuerde dort einen AttributeError werfen und die Antwort abschneiden.
            return self.send_json({"error": "Die Anfrage muss ein JSON-Objekt sein."}, 400)
        if self.fremde_herkunft():
            return self.send_json({"error": "Anfrage von fremder Seite abgelehnt"}, 403)
        # Antwort erst NACH der Sperre senden (B-20).
        #
        # send_json() schreibt in den Socket. Das geschah bisher INNERHALB des
        # with-Blocks, also unter der globalen Sperre. Bei einem langsamen oder
        # haengenden Client - Handy im Funkloch, eingeschlafene Verbindung -
        # blockiert dieses Schreiben, bis der Zeitablauf von 30 Sekunden
        # greift. In dieser Zeit stand JEDER schreibende Zugriff ALLER Nutzer:
        # ein einzelnes Geraet mit schlechter Verbindung legte die
        # Schreibfunktion des ganzen Tools lahm.
        #
        # Der Bericht schlaegt vor, alle Handler auf Rueckgabewerte
        # umzustellen. Das waeren 107 Aufrufstellen, und jede einzelne koennte
        # dabei kaputtgehen. Derselbe Gewinn entsteht, wenn send_json() die
        # Antwort waehrend der Sperre nur EINSAMMELT und der Versand danach
        # passiert - ohne eine einzige Handler-Aenderung. Die Eigenschaft, auf
        # die es ankommt, ist identisch: kein Socket-Schreiben unter der Sperre.
        self._sammeln = True
        self._antwort = None
        try:
            # Der gesperrte Teil steckt in einer eigenen Methode. Die Handler
            # benutzen durchgaengig "return self.send_json(...)" - stuende der
            # Block hier, verliesse ein solches return do_POST vollstaendig
            # und uebersprang den Versand unten. In einer eigenen Methode
            # beendet es nur diese.
            self._post_unter_sperre(path, data)
        except sqlite3.Error as e:
            sys.stderr.write("Datenbankfehler bei %s: %s\n" % (path, e))
            self.send_json({"error": "Datenbankfehler. Bitte im Log nachsehen."}, 500)
        except Exception as e:
            # Nichts darf den Verbindungs-Thread ungebremst verlassen, sonst
            # bekommt der Browser eine abgeschnittene Antwort statt einer Meldung.
            sys.stderr.write("Unerwarteter Fehler bei %s: %r\n" % (path, e))
            self.send_json({"error": "Unerwarteter Fehler. Bitte im Log nachsehen."}, 500)
        finally:
            # Ab hier ist die Sperre in jedem Fall frei - auch wenn oben eine
            # Ausnahme geflogen ist.
            self._sammeln = False
        if self._antwort is None:
            sys.stderr.write("Kein Ergebnis bei %s\n" % path)
            return self.send_json({"error": "Unerwarteter Fehler. Bitte im Log nachsehen."}, 500)
        obj, code = self._antwort
        self._antwort = None
        return self.send_json(obj, code)

    def _post_unter_sperre(self, path, data):
        """Der Teil, der die Datenbank anfasst. Laeuft unter DB_LOCK.

        Antworten werden hier nur eingesammelt (siehe send_json und B-20);
        gesendet wird sie von do_POST, nachdem die Sperre frei ist.
        """
        if True:
            with DB_LOCK, db() as con:
                # anlegen=True: ein POST IST der erste schreibende Zugriff,
                # hier darf das Profil entstehen (B-42).
                ich, user, darf_schreiben = self.profil(con, anlegen=True)
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
                    # Ausdruecklicher Anmeldeweg (B-42): legt das Profil an,
                    # falls es noch keines gibt, und gibt sonst nur zurueck,
                    # dass alles steht. Die Anlage selbst hat schon
                    # profil(anlegen=True) oben erledigt.
                    "/api/anmelden": self.anmelden,
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

    # ---------------- Profile ----------------
    def anmelden(self, con, user, data):
        """Das eigene Profil bereitstellen (B-42).

        Angelegt wurde es bereits von profil(anlegen=True); hier wird nur
        bestaetigt. Bewusst ein POST: das Anlegen ist ein Schreibvorgang und
        gehoert nicht in ein GET.
        """
        return self.send_json({"ok": True, "id": user["id"], "name": user["name"]})

    def user_reset(self, con, user, data):
        """Das eigene Profil leeren. Geloescht wird das Profil NICHT - es gehoert
        zur Identitaetsinstanz und wuerde beim naechsten Aufruf ohnehin neu
        entstehen. Die Bestaetigung mit Mengenangabe macht die Oberflaeche."""
        if (data.get("bestaetigt") or "") != "ja":
            return self.send_json({"error": "Nicht bestaetigt"}, 400)
        belege_loeschen(con, user["id"])
        for tabelle in ("werkstatt", "wartung", "fuelings", "sessions", "cars"):
            con.execute("DELETE FROM %s WHERE nutzer_id=?" % tabelle, (user["id"],))
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
        cur = con.execute("DELETE FROM freigaben WHERE id=? AND eigentuemer_id=?",
                          (int(fid), user["id"]))
        if not cur.rowcount:
            return self.send_json(
                {"error": "Diese Freigabe gibt es nicht mehr. Lade die Seite neu."}, 404)
        return self.send_json({"ok": True, "geloescht": cur.rowcount})

    def settings_save(self, con, user, data):
        """Einstellungen speichern - mit Erlaubnisliste und Groessengrenze (B-22).

        Vorher wurde ungeprueft entgegengenommen, was kam: keine Pruefung auf
        Groesse, Struktur oder Schluesselnamen. Ein Feld mit zwei Millionen
        Zeichen ging anstandslos durch, und je Aufruf waren bis zu 14 MB
        moeglich (MAX_BODY). Da /api/state die Einstellungen bei JEDEM
        Seitenaufbau vollstaendig mitliefert, machte das die Anwendung
        unbenutzbar - fuer den Nutzer selbst und ueber die Datenbankgroesse
        auch fuer andere. Ein Nutzer konnte das Volume vollschreiben.

        Die feste Liste erlaubter Schluessel ist hier besser als eine reine
        Groessenpruefung: sie faengt auch Tippfehler in der Oberflaeche, die
        sonst still in der Datenbank landen und nie wieder gelesen werden.
        """
        roh = data.get("settings")
        if not isinstance(roh, dict):
            return self.send_json(
                {"error": "Die Einstellungen muessen ein Objekt sein."}, 400)
        unbekannt = set(roh) - ERLAUBTE_EINSTELLUNGEN
        if unbekannt:
            return self.send_json(
                {"error": "Unbekannte Einstellung: %s. Bekannt sind: %s."
                          % (", ".join(sorted(unbekannt)[:5]),
                             ", ".join(sorted(ERLAUBTE_EINSTELLUNGEN)))}, 400)
        text = json.dumps(roh, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_EINSTELLUNGEN_B:
            return self.send_json(
                {"error": "Die Einstellungen sind zu umfangreich (%d KB, Grenze "
                          "%d KB). Meist steckt dahinter eine sehr lange Liste "
                          "von Ladepunkten oder Preisen."
                          % (len(text.encode("utf-8")) // 1024,
                             MAX_EINSTELLUNGEN_B // 1024)}, 400)
        con.execute("UPDATE users SET settings=? WHERE id=?", (text, user["id"]))
        return self.send_json({"ok": True})

    # ---------------- Autos ----------------
    def car_save(self, con, user, data):
        kind = data.get("kind") if data.get("kind") in ("bev", "phev", "petrol", "diesel") else "bev"
        # Der Name ist Pflicht (N-02). Vorher stand hier ein 'or "Auto"': ein
        # POST ganz ohne Inhalt legte ein Auto namens "Auto" an und meldete
        # 200. Das ist eine stille Vorgabe im Sinne von CLAUDE.md §11, nur an
        # einer Stelle, die B-05 nicht erfasst hat - dort ging es um Zahlen.
        # Die Oberflaeche verlangt den Namen ohnehin schon selbst
        # ("Bitte gib dem Auto einen Namen."), erreichbar war der Vorgabewert
        # also nur ueber einen direkten API-Aufruf.
        name, fehler = pflicht_text(
            data, "name", 60,
            "Bitte gib dem Auto einen Namen - ohne ihn laesst es sich in den "
            "Listen nicht auseinanderhalten.")
        if fehler:
            return self.send_json({"error": fehler}, 400)
        # Geprueft statt stillschweigend in die Grenze gezwungen (B-05):
        # wer 999 kWh/100 km eintippt, hat sich verschrieben und soll das
        # erfahren, statt lautlos 100 gespeichert zu bekommen.
        #
        # ABER: geprueft wird nur, was zur Antriebsart gehoert (N-08). Ein
        # Elektroauto hat keinen Verbrauch in l/100 km, ein Benziner keinen
        # in kWh/100 km - die Oberflaeche schickt fuer die nicht passende
        # Groesse eine 0, und die lag unter der Plausibilitaetsgrenze (0,5
        # bzw. 1). Ergebnis: bev, petrol und diesel liessen sich ueberhaupt
        # nicht anlegen, mit einer Meldung ueber ein Feld, das der
        # Assistent fuer diese Art gar nicht anzeigt. Weil der Assistent
        # erst weiterlaesst, wenn ein Auto steht, sass ein neuer Benutzer
        # damit fest.
        kwh, lit, fehler = verbrauchswerte(kind, data)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        akku_w, fehler = pflicht_zahl(data, "battery", "akku_kwh", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        tank_w, fehler = pflicht_zahl(data, "tank", "tank_l", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        akku = akku_w or 0.0
        tank = tank_w or 0.0
        active = 1 if data.get("active", True) else 0
        note = (data.get("note") or "")[:120]
        plate = (data.get("plate") or "")[:20]
        cid = data.get("id")
        if cid:
            if not con.execute("SELECT 1 FROM cars WHERE id=? AND nutzer_id=?", (cid, user["id"])).fetchone():
                return self.send_json({"error": "Auto nicht gefunden"}, 404)
            con.execute("""UPDATE cars SET name=?,kind=?,kwh_per_100=?,l_per_100=?,active=?,note=?,
                           plate=?,battery=?,tank=? WHERE id=? AND nutzer_id=?""",
                        (name, kind, kwh, lit, active, note, plate, akku, tank, cid, user["id"]))
        else:
            cid = con.execute("""INSERT INTO cars(nutzer_id,name,kind,kwh_per_100,l_per_100,active,note,
                                 plate,battery,tank) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (user["id"], name, kind, kwh, lit, active, note, plate, akku,
                               tank)).lastrowid
        return self.send_json({"ok": True, "id": cid})

    def car_delete(self, con, user, data):
        # rowcount ansehen (B-09): sonst meldet das Tool "Geloescht", obwohl
        # nichts geloescht wurde - und nach dem Neuladen ist die Zeile wieder
        # da. Beim Loeschen ist genau das der Fall, in dem man dem Tool nicht
        # mehr traut.
        cur = con.execute("DELETE FROM cars WHERE id=? AND nutzer_id=?",
                          (data.get("id"), user["id"]))
        if not cur.rowcount:
            return self.send_json(
                {"error": "Dieses Auto gibt es nicht mehr. Lade die Seite neu."}, 404)
        return self.send_json({"ok": True, "geloescht": cur.rowcount})

    def own_car(self, con, user, car_id):
        """(car_id, ok). Ohne Fahrzeugangabe ist der Vorgang erlaubt (B-43).

        Das bleibt bewusst so: einen Beleg abzulehnen, nur weil das Auto
        fehlt, waere Datenverlust - und es gibt Faelle, in denen er wirklich
        zu keinem Fahrzeug gehoert. Bis B-43 verschwanden diese Vorgaenge
        aber lautlos aus jeder Auswertung, weil die Oberflaeche ueberall nach
        dem gewaehlten Auto filtert. Sie stehen jetzt unter
        "Auffaelligkeiten" und lassen sich von dort einem Auto zuordnen.
        """
        if car_id in (None, ""):
            return None, True
        ok = con.execute("SELECT 1 FROM cars WHERE id=? AND nutzer_id=?", (car_id, user["id"])).fetchone()
        return (int(car_id), True) if ok else (None, False)

    # ---------------- Ladevorgaenge ----------------
    def sessions_import(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        rows = data.get("rows") or []
        # Obergrenze je Aufruf (B-20). Ein grosser Import hielt die Sperre fuer
        # die gesamte Dauer - begrenzt war er nur durch MAX_BODY mit 14 MB, also
        # durch Zehntausende Zeilen. Die Oberflaeche stapelt jetzt: sie schickt
        # in Bloecken, und zwischen den Bloecken kommen andere Nutzer dran.
        if len(rows) > MAX_IMPORT_ZEILEN:
            return self.send_json(
                {"error": "Es lassen sich hoechstens %d Zeilen auf einmal "
                          "einlesen (angekommen sind %d). Die Oberflaeche "
                          "teilt groessere Dateien selbst auf - kommt diese "
                          "Meldung trotzdem, bitte die Datei teilen."
                          % (MAX_IMPORT_ZEILEN, len(rows)),
                 "grenze": MAX_IMPORT_ZEILEN}, 413)
        cols = ",".join(["nutzer_id", "car_id"] + SESSION_FIELDS)
        ph = ",".join(["?"] * (len(SESSION_FIELDS) + 2))
        added = dup = 0
        # Ganz oder gar nicht (B-05 Schritt 6, CLAUDE.md §12): "Import von 200
        # Zeilen, Zeile 137 ist kaputt: Die Datei wird entweder ganz uebernommen
        # oder gar nicht - und es steht im Klartext da, welche Zeile das Problem
        # war." Vorher wurden kaputte Zeilen mit continue stillschweigend
        # uebersprungen; der Nutzer sah "erfolgreich" und merkte nie, dass ein
        # Teil seiner Abrechnung fehlt.
        #
        # Zuerst alle Zeilen pruefen, ohne etwas zu schreiben. Erst wenn keine
        # Zeile Fehler hat, wird geschrieben.
        gepruefte, kaputte = [], []
        for nr, s in enumerate(rows, start=1):
            if not s.get("id"):
                kaputte.append((nr, "ohne Kennung - die Spalte mit der "
                                    "Vorgangsnummer fehlt oder ist leer"))
                continue
            if not valid_ts(s.get("start")):
                kaputte.append((nr, "Startzeitpunkt %r ist kein plausibles Datum"
                                % str(s.get(COL_TO_JSON["start"]) or "")[:30]))
                continue
            gepruefte.append(s)
        if kaputte:
            teil = "; ".join("Zeile %d: %s" % (nr, was) for nr, was in kaputte[:5])
            mehr = ("  … und %d weitere" % (len(kaputte) - 5)) if len(kaputte) > 5 else ""
            return self.send_json(
                {"error": "Die Datei wurde NICHT uebernommen - %d von %d Zeilen "
                          "haben Fehler. %s%s. Bitte die genannten Zeilen in der "
                          "Datei berichtigen und erneut einlesen."
                          % (len(kaputte), len(rows), teil, mehr),
                 "zeilen": [nr for nr, _ in kaputte],
                 "geprueft": len(rows), "uebernommen": 0}, 400)
        with bulk(con):
          for s in gepruefte:
            # Die Umrechnung steckt in import_zeile_werte() - dort ist sie
            # einzeln pruefbar (N-10).
            vals = [user["id"], car_id] + import_zeile_werte(s)
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
            return self.send_json(
                {"error": "Die Startzeit fehlt oder liegt ausserhalb des plausiblen "
                          "Bereichs (ab %d, hoechstens einen Tag in der Zukunft). "
                          "Bitte pruefen." % FRUEHESTES_JAHR}, 400)
        # Geprueft statt still ersetzt (B-05).
        kwh, fehler = pflicht_zahl(data, "kwh", "kwh", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        cost_ct, fehler = pflicht_cent(data, "cost", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        sec_w, fehler = pflicht_zahl(data, "sec", "sec", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        odo, fehler = pflicht_zahl(data, "odo", "odo_km", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        kwh = round(kwh or 0.0, 4)
        cost_ct = cost_ct or 0
        sec = int(sec_w or 0)
        station = (data.get("station") or "Zuhause")[:200]
        note = (data.get("note") or "")[:200]
        odo = round(odo or 0.0, 1)
        # Netto mit dem im Profil eingestellten Satz ableiten, nicht fest mit
        # 19 % (B3). Fehlt der Satz oder ist er unsinnig, gilt 19 %.
        satz = satz_aus_settings(user)
        net_ct = netto_ct(cost_ct, satz)
        vat_ct = cost_ct - net_ct          # Summe stimmt per Konstruktion
        # Altspalten werden nur noch mitgeschrieben, nicht gelesen (B-04
        # Schritt 5) - sie sind der Rueckweg auf eine aeltere Fassung.
        cost, net, vat = cost_ct / 100.0, net_ct / 100.0, vat_ct / 100.0
        dbid = data.get("dbid")
        if dbid:
            # Auch importierte Ladungen duerfen korrigiert werden - eine falsch
            # abgerechnete Ladung soll man geradebiegen koennen.
            row = con.execute("SELECT start,finish FROM sessions WHERE id=? AND nutzer_id=?",
                              (dbid, user["id"])).fetchone()
            if not row:
                return self.send_json({"error": "Ladung nicht gefunden"}, 404)
            # Ein vorhandenes Ende BEHALTEN (B-40). Vorher wurde finish hart
            # auf start gesetzt: bei einer importierten Ladung mit echter
            # Endzeit ging diese Angabe verloren, sobald jemand einen
            # Tippfehler im Betrag korrigierte. CLAUDE.md §15 - stille
            # Datenverluste sind das Schlimmste, was ein Tool tun kann.
            mitgeschickt = valid_ts(data.get("finish") or data.get("end"))
            finish = mitgeschickt or row["finish"] or start
            cur = con.execute("""UPDATE sessions SET car_id=?,start=?,finish=?,sec=?,kwh=?,cost=?,net=?,
                                 vat=?,cost_ct=?,net_ct=?,vat_ct=?,station=?,note=?,odo=?
                                 WHERE id=? AND nutzer_id=?""",
                              (car_id, start, finish, sec, kwh, cost, net, vat,
                               cost_ct, net_ct, vat_ct, station, note,
                               odo, dbid, user["id"]))
            if not cur.rowcount:
                return self.send_json({"error": "Ladung nicht gefunden"}, 404)
            return self.send_json({"ok": True, "id": dbid})
        # Kam die Ladung aus einer Datei, schickt die Oberflaeche deren
        # Kennung mit. Dann erkennt die Dublettenpruefung (UNIQUE nutzer_id,tx)
        # sie auch wieder, wenn dieselbe Datei spaeter im Stapel eingelesen
        # wird - sonst stuende die Ladung zweimal in der Liste.
        tx = str(data.get("tx") or "").strip()[:200] or ("manual-" + uuid.uuid4().hex[:16])
        try:
            con.execute("""INSERT INTO sessions(nutzer_id,car_id,tx,start,finish,sec,kwh,cost,net,vat,
                           cost_ct,net_ct,vat_ct,station,manual,note,odo,src)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,'manuell')""",
                        (user["id"], car_id, tx, start, start, sec, kwh, cost, net, vat,
                         cost_ct, net_ct, vat_ct, station, note, odo))
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
        # In Bloecken (B-39) - siehe in_bloecken().
        geaendert = 0
        for teil in in_bloecken(ids):
            q = ("UPDATE sessions SET car_id=? WHERE nutzer_id=? AND id IN (%s)"
                 % ",".join("?" * len(teil)))
            geaendert += con.execute(q, [car_id, user["id"]] + teil).rowcount
        return self.send_json({"ok": True, "changed": geaendert})

    def sessions_delete(self, con, user, data):
        if data.get("all"):
            n = con.execute("DELETE FROM sessions WHERE nutzer_id=?", (user["id"],)).rowcount
            return self.send_json({"ok": True, "deleted": n})
        ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
        if not ids:
            return self.send_json({"ok": True, "deleted": 0})
        # In Bloecken (B-39). Die Loeschungen laufen in EINER Transaktion,
        # damit nicht die Haelfte verschwindet, wenn es dazwischen klemmt.
        weg = 0
        with bulk(con):
            for teil in in_bloecken(ids):
                q = ("DELETE FROM sessions WHERE nutzer_id=? AND id IN (%s)"
                     % ",".join("?" * len(teil)))
                weg += con.execute(q, [user["id"]] + teil).rowcount
        return self.send_json({"ok": True, "deleted": weg})

    # ---------------- Tankungen ----------------
    def save_receipt(self, data):
        """Einen Beleg ablegen. Der INHALT entscheidet ueber den Typ (B-21)."""
        raw = data.get("receiptData")
        if not raw:
            return None
        roh = raw.split(",", 1)[-1]
        # Groesse VOR dem Dekodieren pruefen. Vorher wurde erst dekodiert und
        # dann gemessen - bei 14 MB Rumpf also erst einmal alles in den
        # Speicher geholt. Base64 ist rund ein Drittel groesser als die
        # Nutzlast.
        if len(roh) > MAX_RECEIPT * 4 // 3 + 64:
            raise ValueError("Der Beleg ist groesser als %d MB. Bitte kleiner "
                             "fotografieren oder als PDF speichern."
                             % (MAX_RECEIPT // 1024 // 1024))
        try:
            blob = base64.b64decode(roh, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Die Belegdatei kam beschaedigt an. Bitte noch "
                             "einmal hochladen.")
        if len(blob) > MAX_RECEIPT:
            raise ValueError("Der Beleg ist groesser als %d MB."
                             % (MAX_RECEIPT // 1024 // 1024))
        if not blob:
            raise ValueError("Die Belegdatei ist leer.")
        # Die vom Client genannte Endung wird VERWORFEN und die erkannte
        # benutzt. Ein echtes PNG als "foto.jpg" wird damit angenommen und
        # richtig als .png abgelegt.
        erkannt = typ_aus_inhalt(blob)
        if erkannt is None:
            raise ValueError("Diese Datei ist kein Bild und kein PDF. "
                             "Erlaubt sind JPG, PNG, WEBP, HEIC und PDF.")
        name = uuid.uuid4().hex + "." + erkannt
        with open(os.path.join(RECEIPT_DIR, name), "wb") as fh:
            fh.write(blob)
        return name

    def fuel_save(self, con, user, data):
        car_id, ok = self.own_car(con, user, data.get("carId"))
        if not ok:
            return self.send_json({"error": "Auto nicht gefunden"}, 400)
        ts = valid_ts(data.get("ts"))
        if not ts:
            return self.send_json(
                {"error": "Das Datum fehlt oder liegt ausserhalb des plausiblen "
                          "Bereichs (ab %d, hoechstens einen Tag in der Zukunft). "
                          "Bitte pruefen." % FRUEHESTES_JAHR}, 400)
        # Geprueft statt still ersetzt (B-05). Menge und Kilometerstand sind
        # freiwillig - unlesbar duerfen sie aber nicht sein.
        cost_ct, fehler = pflicht_cent(data, "cost", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        liters, fehler = pflicht_zahl(data, "liters", "liters_l", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        odo, fehler = pflicht_zahl(data, "odo", "odo_km", pflicht=False)
        if fehler:
            return self.send_json({"error": fehler}, 400)
        cost_ct = cost_ct or 0
        cost = cost_ct / 100.0                       # nur noch mitgeschrieben
        liters = round(liters or 0.0, 3)
        odo = round(odo or 0.0, 1)
        full = 1 if data.get("full", True) else 0
        station = (data.get("station") or "")[:120]
        note = (data.get("note") or "")[:200]
        if cost_ct <= 0 and liters <= 0:
            return self.send_json(
                {"error": "Bitte den Betrag oder die Litermenge angeben - ohne "
                          "eines von beiden laesst sich nichts auswerten."}, 400)
        try:
            receipt = self.save_receipt(data)
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        dbid = data.get("dbid")
        if dbid:
            row = con.execute("SELECT receipt FROM fuelings WHERE id=? AND nutzer_id=?",
                              (dbid, user["id"])).fetchone()
            if not row:
                return self.send_json({"error": "Tankung nicht gefunden"}, 404)
            keep = receipt or ("" if data.get("dropReceipt") else row["receipt"])
            con.execute("""UPDATE fuelings SET car_id=?,ts=?,liters=?,cost=?,cost_ct=?,odo=?,full=?,
                           station=?,note=?,receipt=? WHERE id=? AND nutzer_id=?""",
                        (car_id, ts, liters, cost, cost_ct, odo, full, station, note, keep,
                         dbid, user["id"]))
            return self.send_json({"ok": True, "id": dbid})
        new = con.execute("""INSERT INTO fuelings(nutzer_id,car_id,ts,liters,cost,cost_ct,odo,full,
                             station,note,receipt) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                          (user["id"], car_id, ts, liters, cost, cost_ct, odo, full, station, note,
                           receipt or "")).lastrowid
        return self.send_json({"ok": True, "id": new})

    def fuel_delete(self, con, user, data):
        row = con.execute("SELECT receipt FROM fuelings WHERE id=? AND nutzer_id=?",
                          (data.get("id"), user["id"])).fetchone()
        cur = con.execute("DELETE FROM fuelings WHERE id=? AND nutzer_id=?",
                          (data.get("id"), user["id"]))
        if not cur.rowcount:
            return self.send_json(
                {"error": "Diese Tankung gibt es nicht mehr. Lade die Seite neu."}, 404)
        # Die Belegdatei erst entfernen, wenn die Zeile wirklich weg ist.
        if row and row["receipt"]:
            beleg_datei_weg(row["receipt"])
        return self.send_json({"ok": True, "geloescht": cur.rowcount})

    # ---------------- statische Dateien ----------------
    def static(self, path):
        """Nur die Oberflaeche und Belege ausliefern.

        Vorher wurde alles aus dem Programmverzeichnis herausgegeben - also
        auch server.py und vor allem ladelog.db mit allen Daten. Jetzt gibt es
        eine feste Liste erlaubter Dateien, alles andere ist nicht zu holen.
        """
        rel = "index.html" if path in ("/", "") else unquote(path).lstrip("/")
        # Oberflaechen-Routen (B-10): alles ohne Punkt im letzten Teil ist eine
        # Route der Anwendung, nicht eine Datei - /einstellungen, /wartung,
        # /preise. Sie werden von der einen Seite beantwortet. Nur so
        # funktioniert ein Neuladen auf einer solchen Adresse, und nur so
        # laesst sich ein Verweis darauf teilen.
        if (rel not in PUBLIC_FILES
                and not rel.startswith(("api/", "receipts/", "schriften/"))
                and "." not in os.path.basename(rel)):
            if rel.split("/")[0] in UI_ROUTEN:
                rel = "index.html"      # damit die CSP-Kopfzeile unten greift
            else:
                return self.send_error(404, "Nicht gefunden")
        if rel in PUBLIC_FILES:
            full = os.path.join(HERE, rel)
        elif rel.startswith("schriften/"):
            # Schriften selbst ausliefern (B-19), nicht von einer fremden Seite
            # laden - das deckt sich mit der CSP und haelt die Oberflaeche
            # lesbar, auch wenn ein Anbieter verschwindet. Unauthentifiziert
            # erreichbar: es sind oeffentliche Schriften unter der OFL, und
            # sie muessen laden, bevor irgendetwas anderes zu sehen ist.
            name = os.path.basename(rel)
            if not SCHRIFT_NAME.match(name):
                return self.send_error(404, "Nicht gefunden")
            full = os.path.join(HERE, "schriften", name)
        elif rel.startswith("receipts/"):
            name = os.path.basename(rel)   # schneidet jeden Pfadanteil ab
            if not RECEIPT_NAME.match(name):
                return self.send_error(404, "Nicht gefunden")
            # Ein Beleg gehoert zu einem Profil. Der zufaellige Dateiname allein
            # waere nur Verschleierung - wer ihn kennt, saehe sonst fremde
            # Rechnungen. Darum: angemeldet sein UND der Beleg muss zum eigenen
            # oder einem freigegebenen Profil gehoeren.
            with db() as con:
                ich, _ziel, _darf = self.profil(con)
                if not ich:
                    return self.send_error(401, "Nicht angemeldet")
                erlaubt = [ich["id"]]
                for r in con.execute("SELECT eigentuemer_id FROM freigaben"
                                     " WHERE empfaenger_id=? AND ziel_typ='profil'", (ich["id"],)):
                    erlaubt.append(r["eigentuemer_id"])
                platz = ",".join("?" * len(erlaubt))
                treffer = con.execute(
                    "SELECT 1 FROM fuelings WHERE receipt=? AND nutzer_id IN (%s)"
                    " UNION ALL"
                    " SELECT 1 FROM werkstatt WHERE receipt=? AND nutzer_id IN (%s) LIMIT 1"
                    % (platz, platz),
                    tuple([name] + erlaubt + [name] + erlaubt)).fetchone()
            if not treffer:
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
        if rel.startswith("schriften/"):
            # Ein Jahr und unveraenderlich: die Dateien tragen ihren Inhalt im
            # Namen und werden nie an derselben Adresse ausgetauscht.
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if rel.startswith("receipts/"):
            # Belege sind fremde Dateien und bekommen darum eine eigene,
            # sehr enge CSP (B-21). Vorher wurde eine CSP nur fuer
            # index.html gesetzt; nosniff allein verhinderte zwar die
            # Ausfuehrung, aber der Entwurf verliess sich darauf.
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; sandbox; base-uri 'none'")
            endung = os.path.splitext(rel)[1].lstrip(".").lower()
            # PDF als Anhang, nicht inline: eine PDF-Datei wuerde sonst im
            # PDF-Betrachter des Browsers geoeffnet, und PDFs koennen
            # Skripte und Weiterleitungen enthalten. Bilder bleiben inline -
            # sie sollen ja angesehen werden.
            art = "attachment" if endung == "pdf" else "inline"
            self.send_header("Content-Disposition",
                             '%s; filename="beleg.%s"' % (art, endung or "dat"))
        if rel == "index.html":
            # Alles liegt in der einen Datei - externe Quellen braucht es nicht.
            # 'unsafe-inline' ist noetig, weil CSS und JS bewusst eingebettet sind.
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data: blob:; "
                             "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                             # font-src ausdruecklich nennen (B-19), auch wenn
                             # default-src es schon deckt: so steht schwarz auf
                             # weiss, dass Schriften nur von hier kommen.
                             "font-src 'self'; "
                             "base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(data)


def main():
    p = argparse.ArgumentParser(description="Bordbuch Server")
    p.add_argument("--port", type=int, default=int(os.environ.get("LADELOG_PORT", 8080)))
    # Die Identitaet kommt aus einem HTTP-Kopf. Der ist nur so viel wert wie die
    # Gewissheit, dass ausschliesslich der Reverse-Proxy den Server erreicht -
    # darum standardmaessig nur auf dem eigenen Rechner lauschen.
    p.add_argument("--host", default=os.environ.get("LADELOG_HOST", "127.0.0.1"))
    # Auch als Umgebungsvariable, damit das Compose-File es ausdruecklich setzen
    # kann - besser als eine Container-Erkennung, an der der Start haengt.
    p.add_argument("--header-vertrauen", action="store_true",
                   default=str(os.environ.get("BORDBUCH_HEADER_VERTRAUEN", "")).lower()
                   not in ("", "0", "nein", "false", "aus"),
                   help="Auch auf anderen Netzwerkkarten lauschen. Nur sinnvoll, wenn sicher "
                        "ist, dass niemand ausser dem Proxy den Server erreicht "
                        "(im Container: keine ports-Zeile im Compose-File).")
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
    p.add_argument("--version", action="store_true",
                   help="Fassungsnummer ausgeben und beenden")
    # --version bleibt bewusst ohne Nebenwirkung: es wird von der
    # Gesundheitspruefung und von Skripten aufgerufen, und ein Aufruf, der
    # nur nach der Fassung fragt, darf keine Datenbank migrieren. Wer eine
    # Migration gezielt anstossen oder auf einer Kopie ausprobieren will,
    # nimmt --migrieren.
    p.add_argument("--migrieren", action="store_true",
                   help="Datenbank auf den aktuellen Stand bringen und beenden")
    # N-10: Zwei Wege haben Betraege hundertfach gespeichert (Import von
    # Ladelisten und Einspielen einer Sicherung). Der Fehler ist behoben,
    # aber bereits gespeicherte Zeilen bleiben falsch. Gemeldet wird von
    # --betraege-pruefen, geaendert nur von --betraege-richten - und das
    # sagt vorher, dass eine Sicherung dazugehoert (CLAUDE.md §15).
    p.add_argument("--betraege-pruefen", action="store_true",
                   help="Nach hundertfach gespeicherten Betraegen suchen und "
                        "beenden. Aendert nichts.")
    p.add_argument("--betraege-richten", action="store_true",
                   help="Hundertfach gespeicherte Betraege berichtigen und "
                        "beenden. Vorher sichern.")
    p.add_argument("--auch-unplausible", action="store_true",
                   help="Zusammen mit --betraege-richten auch die Zeilen "
                        "berichtigen, bei denen nur der Stueckpreis den "
                        "Faktor 100 verraet (Indiz, kein Beweis).")
    global CFG, RECEIPT_DIR
    CFG = p.parse_args()
    # Belege dorthin, wo auch die Datenbank liegt (siehe oben). Ein eigener Ort
    # geht ueber BORDBUCH_BELEGE, falls jemand sie getrennt halten will.
    RECEIPT_DIR = os.environ.get("BORDBUCH_BELEGE") or os.path.join(
        os.path.dirname(os.path.abspath(CFG.db)) or HERE, "receipts")
    if CFG.version:
        print(VERSION)
        return
    init_db()
    if CFG.migrieren:
        print("Datenbank ist auf Stand %s." % SCHEMA_VERSION)
        return
    if CFG.betraege_pruefen or CFG.betraege_richten:
        with db() as con:
            sicher = hundertfache_betraege(con)
            indiz = unplausible_betraege(con)
            if not sicher and not indiz:
                print("Keine hundertfach gespeicherten Betraege gefunden.")
                return
            if sicher:
                print("SICHER hundertfach (die zwei Geldspalten widersprechen "
                      "sich um genau Faktor 100): %d Zeile(n)\n"
                      % sum(f[3] for f in sicher))
                for tab, euro, ct, anzahl, bsp in sicher:
                    print("  %-10s %-18s %4d Zeile(n)" % (tab, ct, anzahl))
                    for zid, e, c in bsp:
                        print("      id %-5s steht als %10.2f EUR, richtig waere %8.2f EUR"
                              % (zid, c / 100.0, e))
            if indiz:
                print("\nVERDAECHTIG (nur der Stueckpreis verraet es - beim "
                      "Einspielen einer Sicherung\nwurden beide Geldspalten "
                      "verdorben): %d Zeile(n)\n" % sum(f[2] for f in indiz))
                for tab, einheit, anzahl, bsp in indiz:
                    print("  %-10s %4d Zeile(n)" % (tab, anzahl))
                    for zid, menge, c in bsp:
                        je = (c / 100.0) / menge if menge else 0
                        print("      id %-5s %10.2f EUR fuer %.3f %s = %.2f EUR/%s"
                              % (zid, c / 100.0, menge, einheit, je, einheit))
                print("  Werkstattrechnungen stehen hier nicht: dort gibt es "
                      "keine Menge zum Vergleich.")
            if not CFG.betraege_richten:
                print("\nGeaendert wurde nichts. Zum Berichtigen:")
                print("  1. Sicherung ziehen - Einstellungen > Daten > Sicherung,")
                print("     oder auf dem Server: sudo prolo sichern")
                print("  2. python3 server.py --db %s --betraege-richten" % CFG.db)
                if indiz:
                    print("     Die verdaechtigen Zeilen kommen nur mit "
                          "--auch-unplausible mit.")
                return
            geaendert = betraege_richten(con, CFG.auch_unplausible)
            print("\nBerichtigt:")
            for tab, spalte, anzahl in geaendert:
                print("  %-10s %-24s %4d Zeile(n)" % (tab, spalte, anzahl))
            rest_s = hundertfache_betraege(con)
            rest_i = unplausible_betraege(con)
            print("\nNachgesehen: %d sicher, %d verdaechtig noch offen."
                  % (sum(r[3] for r in rest_s), sum(r[2] for r in rest_i)))
            if rest_i and not CFG.auch_unplausible:
                print("Die verdaechtigen bleiben absichtlich stehen - mit "
                      "--auch-unplausible werden sie mitgenommen.")
        return
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
    # Fehlt die Marke, startet das Bordbuch NICHT (N-44). Ein stilles
    # Weiterlaufen waere der schlechtere Fall: die Sicherung waere dann aus,
    # ohne dass es jemandem auffaellt (CLAUDE.md §11). So schlaegt die
    # Gesundheitspruefung fehl und aktualisieren.sh rollt zurueck.
    if not EINLASS:
        print("FEHLER: PROLO_EINLASS ist nicht gesetzt.\n\n"
              "Ohne diesen Wert kann das Bordbuch nicht unterscheiden, ob eine\n"
              "Anfrage vom Zugang dieses Servers kommt oder von einem anderen\n"
              "Container im selben Netz. Es startet darum nicht.\n\n"
              "So geht es weiter:\n"
              "  1. Den Wert aus /opt/stack/traefik/dynamic/einlass.yml nehmen.\n"
              "  2. In /opt/stack/bordbuch/.env eintragen:  PROLO_EINLASS=<Wert>\n"
              "  3. sudo prolo start bordbuch\n\n"
              "Der Wert ist ein Geheimnis wie ein Passwort: nicht in Git und\n"
              "nicht in einen Chat (CLAUDE.md §21, §22).", file=sys.stderr)
        sys.exit(2)
    print("Bordbuch (Stand %s) laeuft auf http://%s:%d\nAnmeldung: Kopf X-Authentik-Username"
          " · Verwaltungsgruppe: %s\nAbmelden: %s\nDatenbank: %s"
          % (SCHEMA_VERSION, CFG.host, CFG.port, CFG.admin_gruppe,
             CFG.abmelde_pfad or "(kein Knopf)", CFG.db))
    print("Belege: %s" % RECEIPT_DIR)
    try:
        Server((CFG.host, CFG.port), App).serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
