"""Wo was liegt, die Einstellungen, die Sperre und die Ausgabe.

Vier Orte, jeder mit genau einer Bedeutung:

    REPO     /opt/prolo       der Unterbau (git clone) - "prolo update" erneuert ihn
    ETC      /etc/prolo       Einstellungen und Geheimnisse dieses Servers
    VAR      /var/lib/prolo   was der Unterbau zur Laufzeit ablegt
    TOOLS    /opt/tools       je installiertem Tool ein Ordner
    BACKUP   /opt/backup      die Sicherungen

Die Umgebungsvariablen PROLO_ETC, PROLO_VAR, PROLO_TOOLS und PROLO_BACKUP
verlegen die Orte - gedacht fuer die Tests, nicht fuer den Betrieb.
"""
import contextlib
import fcntl
import os
import re
import secrets
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ETC = os.environ.get("PROLO_ETC", "/etc/prolo")
VAR = os.environ.get("PROLO_VAR", "/var/lib/prolo")
TOOLS = os.environ.get("PROLO_TOOLS", "/opt/tools")
BACKUP = os.environ.get("PROLO_BACKUP", "/opt/backup")

KONF = os.path.join(ETC, "prolo.conf")
GEHEIM = os.path.join(ETC, "geheim.env")
SCHLUESSEL = os.path.join(ETC, "backup.key")
SCHLUESSEL_PUB = os.path.join(ETC, "backup.pub")

AGENT = os.path.join(VAR, "agent")
EINGANG = os.path.join(AGENT, "ein")
AUSGANG = os.path.join(AGENT, "aus")
STATUS_JSON = os.path.join(AUSGANG, "status.json")
NETZE_YML = os.path.join(VAR, "unterbau-netze.yml")
SICHERUNG_JSON = os.path.join(VAR, "sicherung.json")
UPDATE_JSON = os.path.join(VAR, "update.json")
SPERRE = os.path.join(VAR, ".sperre")

# Der Nutzer, unter dem die Admin-Seite im Container laeuft (admin/Dockerfile).
ADMIN_UID = 10004

# Das Hilfsabbild fuer tar in Volumes. Feste Fassung - es packt die Daten.
HILFSABBILD = "alpine:3.22"

# Was in prolo.conf stehen darf, mit Vorgabe. None heisst: Pflicht.
KONF_FELDER = {
    "PROLO_DOMAIN": None,
    "PROLO_EMAIL": None,
    "BACKUP_TAGE": "14",
    "AUTO_UPDATE": "ja",
    "ADMIN_GRUPPE": "authentik Admins",
}
GEHEIM_FELDER = ("AUTHENTIK_SECRET_KEY", "PG_PASS", "AUTHENTIK_BOOTSTRAP_PASSWORD")

DOMAIN = re.compile(r"(?=.{4,200}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,63}")


def version():
    with open(os.path.join(REPO, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


# ------------------------------------------------------------- Ausgabe
FARBE = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _f(kode, text):
    return "\033[%sm%s\033[0m" % (kode, text) if FARBE else text


def ok(text):
    print("  %s      %s" % (_f("32", "ok"), text), flush=True)


def getan(text):
    print("  %s   %s" % (_f("34", "getan"), text), flush=True)


def warnung(text):
    print("  %s  %s" % (_f("33", "ACHTUNG"), text), flush=True)


def fehler(text):
    print("  %s  %s" % (_f("31", "FEHLER"), text), flush=True)


def abschnitt(text):
    print("\n" + _f("1", text), flush=True)


class Abbruch(Exception):
    """Ein Fehler, den der Mensch beheben kann - der Text sagt, wie."""


# ------------------------------------------------------- Einstellungen
def env_lesen(pfad):
    """KEY=VALUE je Zeile, # ist ein Kommentar. Fehlt die Datei: {}."""
    werte = {}
    try:
        with open(pfad, encoding="utf-8") as f:
            zeilen = f.read().splitlines()
    except FileNotFoundError:
        return werte
    for nr, zeile in enumerate(zeilen, 1):
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        if "=" not in zeile:
            raise Abbruch("%s, Zeile %d: erwartet NAME=wert, steht da: %s"
                          % (pfad, nr, zeile[:60]))
        k, v = zeile.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        werte[k] = v
    return werte


def env_schreiben(pfad, werte, kopf="", modus=0o600):
    """Schreibt erst daneben, dann umbenennen - nie eine halbe Datei."""
    zeilen = [kopf.rstrip("\n")] if kopf else []
    for k, v in werte.items():
        if "\n" in str(v):
            raise Abbruch("Wert für %s enthält einen Zeilenumbruch." % k)
        zeilen.append("%s=%s" % (k, v))
    datei_schreiben(pfad, "\n".join(zeilen) + "\n", modus)


def datei_schreiben(pfad, text, modus=0o644):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    neu = pfad + ".neu"
    with open(os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modus), "w",
              encoding="utf-8") as f:
        f.write(text)
    os.chmod(neu, modus)
    os.replace(neu, pfad)


def konf():
    """prolo.conf mit Vorgaben. Fehlt ein Pflichtwert, sagt es das."""
    roh = env_lesen(KONF)
    werte = {}
    for k, vorgabe in KONF_FELDER.items():
        v = roh.get(k, vorgabe)
        if v is None or v == "":
            raise Abbruch("%s fehlt in %s. Einrichten mit:  sudo prolo einrichten"
                          % (k, KONF))
        werte[k] = v
    if not DOMAIN.fullmatch(werte["PROLO_DOMAIN"]):
        raise Abbruch("PROLO_DOMAIN=%s in %s ist keine Domain (z. B. prolo.me)."
                      % (werte["PROLO_DOMAIN"], KONF))
    if not re.fullmatch(r"[0-9]{1,4}", werte["BACKUP_TAGE"]) or int(werte["BACKUP_TAGE"]) < 1:
        raise Abbruch("BACKUP_TAGE in %s muss eine Zahl ab 1 sein." % KONF)
    if werte["AUTO_UPDATE"] not in ("ja", "nein"):
        raise Abbruch("AUTO_UPDATE in %s ist ja oder nein." % KONF)
    return werte


def geheimnisse():
    werte = env_lesen(GEHEIM)
    fehlt = [k for k in GEHEIM_FELDER if not werte.get(k)]
    if fehlt:
        raise Abbruch("In %s fehlt: %s. Ergänzt wird das von:  sudo prolo einrichten"
                      % (GEHEIM, ", ".join(fehlt)))
    return werte


def zufall(laenge=40):
    """Ein Geheimnis aus Buchstaben und Ziffern - ohne Zeichen, die in einer
    .env, einer URL oder einer Shell Aerger machen."""
    zeichen = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(zeichen) for _ in range(laenge))


def ist_root():
    return os.geteuid() == 0


def root_noetig(befehl):
    if not ist_root():
        raise Abbruch("Das braucht root:  sudo prolo %s" % befehl)


# ---------------------------------------------------------------- Sperre
_GEHALTEN = [0]


@contextlib.contextmanager
def sperre(was, warten_s=1800):
    """Nur ein veraendernder Vorgang zur Zeit: Sicherung, Update, Tool
    anlegen ... Wer kommt, waehrend ein anderer laeuft, wartet. Innerhalb
    desselben Vorgangs darf man sie mehrfach nehmen (Wiederherstellen ruft
    Sichern)."""
    if _GEHALTEN[0]:
        _GEHALTEN[0] += 1
        try:
            yield
        finally:
            _GEHALTEN[0] -= 1
        return
    os.makedirs(VAR, exist_ok=True)
    fd = os.open(SPERRE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            wer = os.pread(fd, 200, 0).decode("utf-8", "replace").strip()
            print("  Warte, bis der laufende Vorgang fertig ist (%s) ..." % (wer or "?"),
                  flush=True)
            ende = time.time() + warten_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() > ende:
                        raise Abbruch("Ein anderer Vorgang (%s) läuft seit über %d Minuten. "
                                      "Nachsehen:  sudo prolo status" % (wer, warten_s // 60))
                    time.sleep(2)
        os.ftruncate(fd, 0)
        os.pwrite(fd, ("%s seit %s" % (was, time.strftime("%H:%M:%S"))).encode(), 0)
        _GEHALTEN[0] = 1
        yield
    finally:
        _GEHALTEN[0] = 0
        os.close(fd)
