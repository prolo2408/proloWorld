"""Was die Admin-Seite in Auftrag geben darf - und in welcher Form.

Diese Datei hat KEINE Nebenwirkung und importiert nichts aus prolo. Sie
liegt zweimal im Einsatz:

  - in der Admin-Seite (Container), damit ein Fehler sofort gemeldet wird
  - im Agenten auf dem Server, der ENTSCHEIDET: was hier nicht durchgeht,
    wird nicht ausgefuehrt

So koennen die beiden Listen nicht auseinanderlaufen.

Ein Auftrag ist eine JSON-Datei {"art": ..., "felder": {...}, "wer": ...}.
Was aus dem Container kommt, ist fremde Eingabe: der Container koennte
uebernommen sein. Darum ist hier jedes Feld gegen ein Muster geprueft, und
nichts davon geht je durch eine Shell.
"""
import re

NAME = re.compile(r"[a-z][a-z0-9-]{0,28}[a-z0-9]|[a-z]")
# Namen, die der Unterbau selbst braucht (Subdomains und Projektnamen).
RESERVIERT = ("admin", "auth", "prolo", "traefik", "authentik", "socket-proxy")
KENNUNG = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}")
ABBILD = re.compile(r"[a-z0-9][a-z0-9._/-]{0,200}(:[A-Za-z0-9._-]{1,128})?(@sha256:[0-9a-f]{64})?")
GIT_URL = re.compile(r"https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/[A-Za-z0-9._~/-]{1,300}")
PORT = re.compile(r"[1-9][0-9]{0,4}")
DIENST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
STAND = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}")
# Git-Zugang (N-134): Anbieter ist ein Hostname, Benutzer und Token ohne
# Zeichen, die im Protokoll von git (Zeilen mit =) Aerger machen.
HOST = re.compile(r"(?=.{4,200}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
BENUTZER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
TOKEN = re.compile(r"[A-Za-z0-9_.~+/=-]{8,500}")
ZUGANG_WARNEN_TAGE = 14     # so lange vor dem Ablauf warnen Stand und Seite
ANMELDUNG = ("authentik", "keine")
MAX_COMPOSE = 256 * 1024
MAX_ENV = 8 * 1024
MAX_AUFTRAG = 600 * 1024

# art: (Pflichtfelder, freiwillige Felder, Beschriftung, Zeitgrenze in Minuten)
ARTEN = {
    "sichern": ((), (), "Jetzt sichern", 120),
    "update": ((), (), "Unterbau aktualisieren", 120),
    "tool_add": (("name", "quelle"), ("abbild", "git", "compose", "port", "dienst",
                                      "anmeldung", "env"), "Tool installieren", 60),
    "tool_start": (("name",), (), "Starten", 15),
    "tool_stop": (("name",), (), "Anhalten", 15),
    "tool_restart": (("name",), (), "Neu starten", 15),
    "tool_update": (("name",), (), "Aktualisieren", 60),
    "tool_logs": (("name",), (), "Protokoll", 5),
    "tool_set": (("name",), ("port", "anmeldung"), "Einstellungen ändern", 15),
    "tool_edit": (("name",), ("compose", "env"), "Bearbeiten", 120),
    "tool_rm": (("name",), (), "Entfernen", 60),
    "tool_restore": (("name", "stand"), (), "Aus Sicherung zurückholen", 120),
    "zugang_setzen": (("host", "benutzer", "token"), (), "Git-Zugang speichern", 5),
    "zugang_rm": (("host",), (), "Git-Zugang entfernen", 5),
    "zugang_test": (("git",), (), "Git-Zugang testen", 5),
}
# Felder, deren Wert nie in die Lage eines Auftrags (also auf die Seite) kommt.
GEHEIM = ("compose", "env", "token")


class Ungueltig(Exception):
    """Ein Auftrag, der so nicht ausgefuehrt wird - der Text sagt, warum."""


def name_pruefen(name):
    if not NAME.fullmatch(name or ""):
        raise Ungueltig("Name: Kleinbuchstaben, Ziffern und Bindestrich, höchstens "
                        "30 Zeichen, beginnt mit einem Buchstaben (z. B. 'uptime').")
    if name in RESERVIERT or name.startswith("prolo"):
        raise Ungueltig("Den Namen '%s' braucht der Unterbau selbst." % name)
    return name


def env_zeilen(text):
    """NAME=wert je Zeile -> dict. Leere Zeilen und # werden uebergangen."""
    werte = {}
    for nr, zeile in enumerate((text or "").splitlines(), 1):
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        k, gleich, v = zeile.partition("=")
        k = k.strip()
        if not gleich or not VARIABLE.fullmatch(k):
            raise Ungueltig("Variablen, Zeile %d: erwartet NAME=wert." % nr)
        if "\x00" in v:
            raise Ungueltig("Variablen, Zeile %d: unzulässiges Zeichen." % nr)
        werte[k] = v.strip()
    return werte


def pruefen(daten):
    """Gibt (art, felder) zurück oder wirft Ungültig."""
    if not isinstance(daten, dict):
        raise Ungueltig("Kein Auftrag.")
    art = daten.get("art")
    if art not in ARTEN:
        raise Ungueltig("Unbekannte Art: %r" % str(art)[:40])
    pflicht, frei, _, _ = ARTEN[art]
    felder = daten.get("felder") or {}
    if not isinstance(felder, dict):
        raise Ungueltig("Felder fehlen.")
    fremd = set(felder) - set(pflicht) - set(frei)
    if fremd:
        raise Ungueltig("Unbekannte Felder: %s" % ", ".join(sorted(fremd))[:80])
    for k, v in felder.items():
        if not isinstance(v, str):
            raise Ungueltig("Feld %s ist kein Text." % k)
    for k in pflicht:
        if not felder.get(k):
            raise Ungueltig("Es fehlt: %s" % k)
    f = {k: (felder.get(k) or "").strip() for k in pflicht + frei}
    if "compose" in f:
        f["compose"] = felder.get("compose") or ""      # Einrueckung erhalten

    if "name" in f:
        name_pruefen(f["name"])
    if f.get("port") and (not PORT.fullmatch(f["port"]) or int(f["port"]) > 65535):
        raise Ungueltig("Port: eine Zahl von 1 bis 65535.")
    if f.get("dienst") and not DIENST.fullmatch(f["dienst"]):
        raise Ungueltig("Dienst: so heißt kein Dienst in einer Compose-Datei.")
    if f.get("anmeldung") and f["anmeldung"] not in ANMELDUNG:
        raise Ungueltig("Anmeldung: authentik oder keine.")
    if "host" in f and not HOST.fullmatch(f["host"]):
        raise Ungueltig("Anbieter: ein Hostname wie github.com - ohne https:// und ohne Pfad.")
    if "benutzer" in f and not BENUTZER.fullmatch(f["benutzer"]):
        raise Ungueltig("Benutzer: dein Name beim Anbieter, z. B. prolo2408.")
    if "token" in f and not TOKEN.fullmatch(f["token"]):
        raise Ungueltig("Token: so sieht kein Token aus (Buchstaben, Ziffern, _ - . ohne "
                        "Leerzeichen). Neu kopieren und einfügen.")
    if art == "zugang_test" and not GIT_URL.fullmatch(f["git"]):
        raise Ungueltig("Repository: eine https://-Adresse, z. B. https://github.com/name/repo.")
    if art == "tool_restore" and not STAND.fullmatch(f["stand"]):
        raise Ungueltig("Stand: so heißt keine Sicherung.")
    if art == "tool_set" and not (f.get("port") or f.get("anmeldung")):
        raise Ungueltig("Nichts zu ändern.")
    if len((f.get("compose") or "").encode("utf-8")) > MAX_COMPOSE:
        raise Ungueltig("Die Compose-Datei ist größer als %d KiB." % (MAX_COMPOSE // 1024))
    if len((f.get("env") or "").encode("utf-8")) > MAX_ENV:
        raise Ungueltig("Zu viele Variablen.")
    env_zeilen(f.get("env"))
    if art == "tool_edit":
        if not f["compose"].strip():
            f["compose"] = ""
        if not (f["compose"] or f["env"]):
            raise Ungueltig("Nichts zu ändern: die Compose-Datei ist wie vorher, und keine "
                            "Variable ist gesetzt.")

    if art == "tool_add":
        q = f["quelle"]
        if q == "abbild":
            if not ABBILD.fullmatch(f.get("abbild") or ""):
                raise Ungueltig("Abbild: z. B. louislam/uptime-kuma:1 - ohne Leerzeichen.")
        elif q == "git":
            if not GIT_URL.fullmatch(f.get("git") or ""):
                raise Ungueltig("Git: eine https://-Adresse eines Repositorys.")
        elif q == "compose":
            if not f["compose"].strip():
                raise Ungueltig("Die Compose-Datei ist leer.")
        else:
            raise Ungueltig("Quelle: abbild, compose oder git.")
    return art, f


def argumente(art, f, datei=None):
    """Die Argumente fuer prolo - eine Liste, nie eine Zeichenkette fuer eine
    Shell. 'datei' ist der Ort, an dem der Agent eine Compose-Datei oder die
    Variablen abgelegt hat."""
    if art == "sichern":
        return ["backup"]
    if art == "update":
        return ["update"]
    if art == "zugang_setzen":     # der Token nur als Datei, nie als Argument
        return ["git-zugang", "setzen", f["host"], "--benutzer", f["benutzer"],
                "--token-datei", datei["token"]]
    if art == "zugang_rm":
        return ["git-zugang", "entfernen", f["host"]]
    if art == "zugang_test":
        return ["git-zugang", "testen", f["git"]]
    n = f["name"]
    if art == "tool_add":
        a = ["tool", "add", n, "--ja", "--von-web"]
        if f["quelle"] == "abbild":
            a += ["--image", f["abbild"]]
        elif f["quelle"] == "git":
            a += ["--git", f["git"]]
        else:
            a += ["--compose", datei["compose"]]
        if f.get("port"):
            a += ["--port", f["port"]]
        if f.get("dienst"):
            a += ["--dienst", f["dienst"]]
        a += ["--anmeldung", f.get("anmeldung") or "authentik"]
        if datei and datei.get("env"):
            a += ["--env-datei", datei["env"]]
        return a
    if art == "tool_set":
        a = ["tool", "set", n]
        if f.get("port"):
            a += ["--port", f["port"]]
        if f.get("anmeldung"):
            a += ["--anmeldung", f["anmeldung"]]
        return a
    if art == "tool_edit":
        a = ["tool", "edit", n, "--ja", "--von-web"]
        if datei and datei.get("compose"):
            a += ["--compose", datei["compose"]]
        if datei and datei.get("env"):
            a += ["--env-datei", datei["env"]]
        return a
    if art == "tool_rm":
        return ["tool", "rm", n, "--ja"]
    if art == "tool_restore":
        return ["restore", f["stand"], "--tool", n, "--ja"]
    if art == "tool_logs":
        return ["tool", "logs", n, "--zeilen", "300"]
    return ["tool", art[len("tool_"):], n]
