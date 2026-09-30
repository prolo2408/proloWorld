#!/usr/bin/env python3
"""Prolo Admin - die Lage des Stacks auf einer Seite, und die Griffe dazu.

Was dieses Werkzeug zeigt: welche Werkzeuge es gibt, ob sie laufen, in
welchem Netz sie haengen, unter welchem Namen sie erreichbar sind - und vor
allem: was davon NICHT geschuetzt ist.

Was es tut (A-02): Werkzeuge starten, neu starten, anhalten, pruefen,
aktualisieren, sichern, Netze anlegen. Aber NICHT selbst. Die Seite hat
keinen schreibenden Zugriff auf Docker - wer den hat, hat root, und eine
Webseite ist genau die Stelle, an der man am ehesten hereinkommt. Sie legt
einen AUFTRAG ins Auftragsbuch (/auftraege/eingang), und auf dem Server
fuehrt werkzeuge/auftrag.py ihn aus - ueber prolo, mit Startsperre,
Sicherung und Rueckweg (A-01). Was dort nicht erlaubt ist, geht auch von
hier nicht.

Woher die Daten kommen: aus lesenden Aufrufen an den Vermittler
(socket-proxy): /containers/json, /networks und die Protokolle einzelner
Container. Und aus dem Auftragsbuch: erledigt/ (nur lesend eingehaengt)
mit den Ergebnissen und dem Bestand der Werkzeugordner. Dieses Werkzeug
hat KEINEN Zugriff auf /opt/stack - keine Compose-Datei, keine .env, kein
Zertifikat. Es kann also auch nichts davon preisgeben.

Wer darf was: die Gruppe "admin" sieht, die Gruppe "admin-betrieb" handelt
und liest Protokolle. Beide stehen im Label prolo.gruppen (N-95).

Kein Fremdpaket: Standardbibliothek und SQLite (CLAUDE.md).
"""
import datetime
import hashlib
import hmac
import html
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = "0.4.1"

PORT = int(os.environ.get("ADMIN_PORT", "8080"))
DATEN = os.environ.get("ADMIN_DATEN", "/daten")
DB = os.path.join(DATEN, "admin.db")
SCHRIFTEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schriften")

# Der Vermittler vor dem Docker-Socket. Feste Adresse, kein Nutzereingang -
# nichts aus einer Anfrage wird je an diese URL angehaengt. Eine Uebersicht,
# die eine Adresse aus der Anfrage zusammenbaut, ist ein offener Tuersteher
# fuer das interne Netz.
DOCKER_API = os.environ.get("ADMIN_DOCKER_API", "http://socket-proxy:2375")
DOCKER_PFADE = ("/containers/json?all=1", "/networks")
DOCKER_ZEIT_S = 5
# Das Protokoll eines Containers. Die Kennung kommt NIE aus der Anfrage,
# sondern aus der Containerliste von Docker selbst - und sie wird trotzdem
# gegen das Muster geprueft, bevor sie in eine Adresse wandert.
CONTAINER_ID = re.compile(r"[0-9a-f]{64}")
PROTOKOLL_ZEILEN = 200
PROTOKOLL_MAX_BYTE = 512 * 1024

# ---------------------------------------------------- Das Auftragsbuch (A-01)
#
# eingang/ darf die Seite beschreiben, erledigt/ nur lesen (so eingehaengt).
# Die Regeln unten sind dieselben wie in werkzeuge/auftrag.py - die Seite
# prueft vorher, damit die Meldung sofort kommt und nicht erst im
# Auftrag. ENTSCHIEDEN wird dort: was hier durchrutscht, lehnt der
# Ausfuehrer ab. werkzeuge/auftrag-pruefen.sh haelt die Listen zusammen.
AUFTRAEGE = os.environ.get("ADMIN_AUFTRAEGE", "/auftraege")
EINGANG = os.path.join(AUFTRAEGE, "eingang")
ERLEDIGT = os.path.join(AUFTRAEGE, "erledigt")
ARTEN = {
    # art: (Felder, Beschriftung)
    "start": (("werkzeug",), "Starten"),
    "neustart": (("werkzeug",), "Neu starten"),
    "stop": (("werkzeug",), "Anhalten"),
    "pruefen": (("werkzeug",), "Pruefen"),
    "aktualisieren": (("werkzeug",), "Aktualisieren"),
    "sichern": ((), "Sichern"),
    "netz_anlegen": (("netz",), "Netz anlegen"),
    # A-03: eine Compose-Datei einwerfen - erst ansehen, dann anlegen.
    "compose_pruefen": (("name", "compose"), "Compose-Datei pruefen"),
    "neu": (("name", "compose", "dienst", "port", "netz", "geteilt", "anmeldung", "grund",
             "werte"), "Anlegen"),
    # F-02: die Firewall. Die Regeln, WAS gesperrt werden darf, stehen in
    # prolo firewall; hier die Form - und dass niemand sich selbst aussperrt.
    "firewall_sperren": (("adresse", "dauer", "grund"), "Sperren"),
    "firewall_aufheben": (("adresse",), "Sperre aufheben"),
    "firewall_erlauben": (("adresse", "grund"), "Freigeben"),
    "firewall_nicht_erlauben": (("adresse",), "Freigabe entfernen"),
    "firewall_lesen": ((), "Firewall nachsehen"),
}
ADRESSE_MAX = 49
DAUER = re.compile(r"[1-9][0-9]{0,3}[mhd]")
DAUERN = (("1h", "1 Stunde"), ("4h", "4 Stunden"), ("24h", "24 Stunden"),
          ("7d", "7 Tage"), ("30d", "30 Tage"))
# Der Zeitgeber schreibt alle fuenf Minuten. Aelter als das Dreifache heisst:
# er laeuft nicht mehr, und was hier steht, ist Geschichte.
FIREWALL_ALT_S = 15 * 60
BOUNCER_STILL_S = 120
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
GEHEIM = re.compile(r"PASS|SECRET|KEY|TOKEN|SALT|CREDENTIAL", re.I)
DIENST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MAX_COMPOSE = 256 * 1024
FREITEXT_MAX = 200
KERN = ("traefik", "authentik", "socket-proxy", "admin")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
KENNUNG = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}")
OFFEN_STATUS = ("wartet", "laeuft")

# --------------------------------------------------- Die Vertrauensgrenze
#
# Wie in Wiki, Bordbuch und www (N-44): die Identitaet kommt als Kopfzeile
# von Traefik, und ein Werkzeug sieht nicht, WOHER eine Anfrage kam. Im
# Docker-Netz erreicht jeder Container Port 8080 eines anderen direkt, ohne
# Traefik und ohne Anmeldung. Ohne die Marke, die nur der Zugang kennt,
# antwortet dieses Werkzeug gar nicht.
#
# Hier wiegt das schwerer als anderswo: diese Seite sagt, wo die Luecken
# sind. Eine Lueckenliste ist fuer den Betreiber eine Hilfe und fuer jeden
# anderen eine Einkaufsliste.
EINLASS_KOPF = "X-Prolo-Einlass"
EINLASS = os.environ.get("PROLO_EINLASS", "")
EINLASS_B = EINLASS.encode("utf-8")
EINLASS_FREI = ("/gesundheit", "/api/version")

# Eigene Gruppen, und nur die eigenen (§17): alles, was mit "admin"
# anfaengt, wird ausgewertet, der Rest an EINER Stelle verworfen.
GRUPPE_PRAEFIX = os.environ.get("ADMIN_GRUPPE_PRAEFIX", "admin")
GRUPPE_LESEN = os.environ.get("ADMIN_GRUPPE", "admin")
# Handeln ist mehr als Sehen: wer nur die Uebersicht braucht, bekommt nicht
# gleich den Knopf, der ein Werkzeug anhaelt.
GRUPPE_BETRIEB = os.environ.get("ADMIN_GRUPPE_BETRIEB", "admin-betrieb")

MARKE = "A"
TITEL = "Prolo Admin"
UNTERZEILE = "STACK-VERWALTUNG"


class Antwort(Exception):
    def __init__(self, kode, text):
        super().__init__(text)
        self.kode = kode
        self.text = text


# ------------------------------------------------------------ Datenbank
SCHEMA = """
CREATE TABLE IF NOT EXISTS nutzer (
  nutzer_id    TEXT PRIMARY KEY,
  anzeigename  TEXT NOT NULL DEFAULT '',
  email        TEXT NOT NULL DEFAULT '',
  thema        TEXT NOT NULL DEFAULT 'system',
  angelegt     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
THEMEN = ("system", "hell", "dunkel")


def verbindung():
    k = sqlite3.connect(DB, timeout=10)
    k.row_factory = sqlite3.Row
    k.execute("PRAGMA journal_mode=WAL")
    k.execute("PRAGMA foreign_keys=ON")
    return k


def datenbank_anlegen():
    os.makedirs(DATEN, exist_ok=True)
    with verbindung() as k:
        k.executescript(SCHEMA)


def nutzer_holen(kennung, anzeigename, email):
    """Den Nutzer wiedererkennen - ueber den ANMELDENAMEN, nicht die E-Mail.

    Die E-Mail aendert sich, der Anmeldename ist der Schluessel (§17).
    """
    with verbindung() as k:
        z = k.execute("SELECT * FROM nutzer WHERE nutzer_id=?", (kennung,)).fetchone()
        if z is None:
            k.execute("INSERT INTO nutzer (nutzer_id, anzeigename, email) "
                      "VALUES (?,?,?)", (kennung, anzeigename, email))
            z = k.execute("SELECT * FROM nutzer WHERE nutzer_id=?",
                          (kennung,)).fetchone()
        elif (z["anzeigename"], z["email"]) != (anzeigename, email):
            k.execute("UPDATE nutzer SET anzeigename=?, email=? WHERE nutzer_id=?",
                      (anzeigename, email, kennung))
            z = k.execute("SELECT * FROM nutzer WHERE nutzer_id=?",
                          (kennung,)).fetchone()
        return dict(z)


def thema_setzen(kennung, thema):
    if thema not in THEMEN:
        raise Antwort(400, "Unbekannte Darstellung. Moeglich: %s."
                           % ", ".join(THEMEN))
    with verbindung() as k:
        k.execute("UPDATE nutzer SET thema=? WHERE nutzer_id=?", (thema, kennung))


# --------------------------------------------------------- Docker lesen
def docker_roh(pfad, grenze=4 * 1024 * 1024):
    """Ein lesender Aufruf an den Vermittler - nur Pfade, die hier gebaut
    werden (DOCKER_PFADE oder das Protokoll einer bekannten Kennung)."""
    erlaubt = pfad in DOCKER_PFADE or re.fullmatch(
        r"/containers/[0-9a-f]{64}/logs\?stdout=1&stderr=1&tail=%d"
        % PROTOKOLL_ZEILEN, pfad)
    if not erlaubt:
        raise Antwort(500, "Unerlaubter Pfad zum Docker-Vermittler.")
    url = DOCKER_API.rstrip("/") + pfad
    try:
        with urllib.request.urlopen(url, timeout=DOCKER_ZEIT_S) as r:
            return r.read(grenze)
    except urllib.error.HTTPError as e:
        raise Antwort(503, "Der Docker-Vermittler hat abgelehnt (%s %s). Auf "
                           "dem Server nachsehen: sudo prolo protokoll "
                           "socket-proxy" % (e.code, e.reason))
    except urllib.error.URLError as e:
        raise Antwort(503,
                      "Der Docker-Vermittler antwortet nicht (%s). Die "
                      "Uebersicht kann nichts anzeigen, solange er still "
                      "ist. Auf dem Server nachsehen: "
                      "sudo prolo protokoll socket-proxy" % e.reason)
    except OSError as e:
        raise Antwort(503, "Der Docker-Vermittler hat nicht zu Ende geantwortet "
                           "(%s)." % e)


def docker_lesen(pfad):
    """Ein lesender Aufruf mit JSON-Antwort. Welcher Pfad erlaubt ist,
    entscheidet EINE Stelle: docker_roh. Eine zweite Pruefung hier waere
    eine, deren Ausfall niemand bemerkt - die Mutationsprobe hat genau das
    gezeigt."""
    try:
        return json.loads(docker_roh(pfad).decode("utf-8"))
    except ValueError as e:
        raise Antwort(503, "Der Docker-Vermittler hat geantwortet, aber nicht "
                           "verstaendlich (%s)." % e)


ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[()][A-Za-z0-9]|\r")


def entmischen(roh):
    """Das Protokoll eines Containers ohne TTY kommt in Rahmen: 8 Byte Kopf
    (Strom, 0, 0, 0, Laenge als 4 Byte gross-endian), dann die Daten. Mit
    TTY kommt es roh. Welche Form, sagt nur der erste Kopf - also wird er
    geprueft, nicht angenommen."""
    teile, i = [], 0
    if len(roh) >= 8 and roh[0] in (0, 1, 2) and roh[1:4] == b"\0\0\0":
        while i + 8 <= len(roh):
            laenge = int.from_bytes(roh[i + 4:i + 8], "big")
            teile.append(roh[i + 8:i + 8 + laenge])
            i += 8 + laenge
        roh = b"".join(teile)
    return ANSI.sub("", roh.decode("utf-8", "replace"))


def protokoll_lesen(cid):
    if not CONTAINER_ID.fullmatch(cid or ""):
        raise Antwort(404, "Diesen Container kennt Docker nicht.")
    return entmischen(docker_roh(
        "/containers/%s/logs?stdout=1&stderr=1&tail=%d" % (cid, PROTOKOLL_ZEILEN),
        PROTOKOLL_MAX_BYTE))


# ------------------------------------------------------- Das Auftragsbuch
def jetzt():
    return datetime.datetime.now().astimezone()


def json_datei(pfad, grenze=2 * 1024 * 1024):
    """Eine JSON-Datei aus dem Auftragsbuch - oder None. Was dort liegt,
    hat der Ausfuehrer geschrieben; kaputt oder zu gross heisst: nicht
    anzeigen, nicht abstuerzen."""
    try:
        with open(pfad, "rb") as f:
            roh = f.read(grenze + 1)
        if len(roh) > grenze:
            return None
        d = json.loads(roh.decode("utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def bestand_lesen():
    """Die Werkzeugordner auf dem Server, geschrieben vom Ausfuehrer. Auch
    die, die gerade nicht laufen - die kennt Docker nicht."""
    d = json_datei(os.path.join(ERLEDIGT, "bestand.json"))
    if not d or not isinstance(d.get("werkzeuge"), list):
        return None
    d["werkzeuge"] = [w for w in d["werkzeuge"]
                      if isinstance(w, dict) and NAME.fullmatch(str(w.get("name", "")))]
    return d


def ziel_von(felder):
    return (felder.get("werkzeug") or felder.get("name") or felder.get("netz")
            or felder.get("adresse") or "")


def auftrag_pruefen(art, felder, quelle=""):
    """Dieselben Regeln wie werkzeuge/auftrag.py - die Meldung soll sofort
    kommen, nicht erst im Ergebnis. quelle: die Adresse, von der aus gerade
    jemand hier ist - die sperrt er sich nicht selbst weg."""
    if art not in ARTEN:
        raise Antwort(400, "Diesen Auftrag gibt es nicht. Moeglich: %s."
                           % ", ".join(sorted(ARTEN)))
    noetig, _ = ARTEN[art]
    aus = {}
    for f in noetig:
        if f == "werte":
            werte = felder.get("werte") or {}
            if not isinstance(werte, dict) or len(werte) > 30:
                raise Antwort(400, "Zu viele Werte (hoechstens 30).")
            for k, v in werte.items():
                if not VARIABLE.fullmatch(k) or GEHEIM.search(k):
                    raise Antwort(400, "%s: kein Wert, der hierher gehoert - Geheimnisse "
                                       "wuerfelt der Server selbst." % k[:40])
                if len(v) > 500 or not v.isprintable() or "'" in v:
                    raise Antwort(400, "Der Wert fuer %s ist zu lang (500 Zeichen), hat "
                                       "mehrere Zeilen oder ein '." % k)
            aus[f] = werte
            continue
        wert = felder.get(f) or ""
        wert = wert if f == "compose" else wert.strip()
        leer_erlaubt = art == "neu" and f in ("dienst", "port", "netz", "geteilt", "grund")
        if f in ("werkzeug", "name", "netz"):
            if not (leer_erlaubt and not wert) and not NAME.fullmatch(wert):
                raise Antwort(400, "%s: nur Kleinbuchstaben, Ziffern und Bindestrich, "
                                   "hoechstens 40 Zeichen." % {"werkzeug": "Werkzeug", "name": "Name",
                                                              "netz": "Netz"}[f])
        elif f == "compose":
            if not wert.strip():
                raise Antwort(400, "Die Compose-Datei ist leer. Die des Herstellers "
                                   "steht meist in seiner Doku unter 'Docker Compose'.")
            if len(wert.encode("utf-8")) > MAX_COMPOSE:
                raise Antwort(400, "Die Compose-Datei ist groesser als %d KiB."
                                   % (MAX_COMPOSE // 1024))
        elif f == "dienst":
            if wert and not DIENST.fullmatch(wert):
                raise Antwort(400, "Dienst: so heisst kein Dienst in einer Compose-Datei.")
        elif f == "port":
            if wert and not (wert.isdigit() and 0 < int(wert) < 65536):
                raise Antwort(400, "Port: eine Zahl von 1 bis 65535.")
        elif f in ("geteilt", "grund"):
            if len(wert) > FREITEXT_MAX or not wert.isprintable():
                raise Antwort(400, "Der Grund ist zu lang (hoechstens %d Zeichen, eine "
                                   "Zeile)." % FREITEXT_MAX)
        elif f == "adresse":
            try:
                if len(wert) > ADRESSE_MAX:
                    raise ValueError
                ipaddress.ip_network(wert, strict=False)
            except ValueError:
                raise Antwort(400, "Adresse: eine wie 203.0.113.7 oder ein Netz wie "
                                   "203.0.113.0/24.")
        elif f == "dauer":
            if not DAUER.fullmatch(wert):
                raise Antwort(400, "Dauer: zum Beispiel 30m, 12h oder 7d.")
        elif f == "anmeldung":
            if wert not in ("authentik", "eigene"):
                raise Antwort(400, "Anmeldung: Authentik davor oder die eigene des "
                                   "Werkzeugs - das ist eine Entscheidung, darum ohne "
                                   "Vorgabe (§17a).")
        aus[f] = wert
    if art == "neu":
        if aus["anmeldung"] == "eigene" and not aus["grund"]:
            raise Antwort(400, "Eigene Anmeldung nur mit Grund - sonst sieht ein "
                               "fehlendes Authentik aus wie ein vergessenes (N-59).")
        if aus["netz"] and aus["netz"] != "netz-" + aus["name"] and not aus["geteilt"]:
            raise Antwort(400, "Ein vorhandenes Netz teilen nur mit Grund - es hebt die "
                               "Abschottung zwischen zwei Werkzeugen auf (N-62).")
    if art in ("firewall_sperren", "firewall_erlauben") and not aus["grund"]:
        raise Antwort(400, "Ohne Grund wird nichts gesperrt oder freigegeben - spaeter "
                           "weiss sonst niemand, warum.")
    if art == "firewall_sperren" and eigene_betroffen(aus["adresse"], quelle):
        raise Antwort(400, "Das ist deine eigene Adresse (%s) - damit sperrst du dich "
                           "selbst aus, und mit dir diese Seite. Aufheben ginge dann nur "
                           "noch auf dem Server: sudo prolo firewall aufheben %s"
                           % (quelle, aus["adresse"]))
    if art == "stop" and aus.get("werkzeug") in KERN:
        raise Antwort(400, "%s haelt den Zugang offen - ohne ihn gibt es keine "
                           "Seite mehr, von der aus man ihn wieder startet. Neu "
                           "starten geht; anhalten nur auf dem Server: sudo "
                           "prolo stop %s" % (aus["werkzeug"], aus["werkzeug"]))
    return aus


def auftraege_lesen(grenze=60):
    """Die Auftraege, neueste zuerst: was noch im Eingang wartet und was der
    Ausfuehrer schon angefasst hat."""
    aus = {}
    try:
        namen = os.listdir(ERLEDIGT)
    except OSError:
        namen = []
    for n in sorted((n for n in namen if n.endswith(".json")
                     and KENNUNG.fullmatch(n[:-5])), reverse=True)[:grenze]:
        d = json_datei(os.path.join(ERLEDIGT, n))
        if d:
            d["kennung"] = n[:-5]
            aus[n[:-5]] = d
    try:
        wartend = os.listdir(EINGANG)
    except OSError:
        wartend = []
    for n in wartend:
        k = n[:-5]
        if n.endswith(".json") and KENNUNG.fullmatch(k) and k not in aus:
            d = json_datei(os.path.join(EINGANG, n)) or {}
            d.update(kennung=k, status="wartet")
            aus[k] = d
    return [aus[k] for k in sorted(aus, reverse=True)][:grenze]


def auftrag_lesen(kennung):
    """Lage und Ausgabe eines Auftrags - oder 404."""
    if not KENNUNG.fullmatch(kennung or ""):
        raise Antwort(404, "Diesen Auftrag gibt es nicht. Alle Auftraege: /auftraege")
    lage = json_datei(os.path.join(ERLEDIGT, kennung + ".json"))
    if lage is None:
        wartet = json_datei(os.path.join(EINGANG, kennung + ".json"))
        if wartet is None:
            raise Antwort(404, "Diesen Auftrag gibt es nicht. Alle Auftraege: /auftraege")
        wartet.update(kennung=kennung, status="wartet")
        return wartet, ""
    lage["kennung"] = kennung
    try:
        with open(os.path.join(ERLEDIGT, kennung + ".log"), "rb") as f:
            ausgabe = f.read(2 * 1024 * 1024)
    except OSError:
        ausgabe = b""
    return lage, ANSI.sub("", ausgabe.decode("utf-8", "replace"))


def eigene_betroffen(adresse, quelle):
    try:
        return ipaddress.ip_address(quelle) in ipaddress.ip_network(adresse, strict=False)
    except ValueError:
        return False


def quelle_von(xff):
    """Die Adresse des Besuchers: der LETZTE Eintrag in X-Forwarded-For - den
    haengt Traefik an; was davor steht, hat der Aufrufer erfunden (§11, N-48)."""
    teile = [x.strip() for x in (xff or "").split(",") if x.strip()]
    try:
        return str(ipaddress.ip_address(teile[-1])) if teile else ""
    except ValueError:
        return ""


def firewall_lesen():
    """Die Lage der Firewall, wie prolo firewall --json sie abgelegt hat -
    oder None. Was fehlt oder die falsche Form hat, faellt weg."""
    d = json_datei(os.path.join(ERLEDIGT, "firewall.json"))
    if not d:
        return None
    for k in ("sperren", "meldungen", "freigaben", "regeln", "bouncer"):
        d[k] = [x for x in (d.get(k) if isinstance(d.get(k), list) else []) if isinstance(x, dict)]
    d["fehler"] = [str(x) for x in (d.get("fehler") if isinstance(d.get("fehler"), list) else [])]
    d["gelesen"] = {str(k): v for k, v in (d.get("gelesen") or {}).items()
                    if isinstance(v, dict)} if isinstance(d.get("gelesen"), dict) else {}
    d["crowdsec"] = d.get("crowdsec") if isinstance(d.get("crowdsec"), dict) else {}
    try:
        d["gemeinschaft"] = int(d.get("gemeinschaft") or 0)
    except (TypeError, ValueError):
        d["gemeinschaft"] = 0
    return d


def auftrag_ablegen(art, felder, wer, quelle=""):
    """Einen Auftrag in den Eingang legen. Erst daneben (.neu), dann
    umbenennen: der Ausfuehrer sieht nie eine halbe Datei, und systemd
    stoesst erst beim fertigen *.json an.

    Liegt derselbe Auftrag schon offen da (Doppelklick, zweiter Reiter),
    gibt es keinen zweiten - die Kennung des offenen kommt zurueck (§10).
    """
    aus = auftrag_pruefen(art, felder, quelle)
    for a in auftraege_lesen(grenze=30):
        if a.get("status") in OFFEN_STATUS and a.get("art") == art \
                and ziel_von(a) == ziel_von(aus):
            return a["kennung"], False
    if not os.access(EINGANG, os.W_OK):
        raise Antwort(503,
                      "Das Auftragsbuch ist nicht beschreibbar - auf dem Server "
                      "ist es noch nicht eingerichtet. Einmal: sudo prolo "
                      "einrichten (gefahrlos zu wiederholen, es tut nur, was "
                      "fehlt).")
    kennung = "%s-%s" % (jetzt().strftime("%Y%m%d-%H%M%S"), secrets.token_hex(4))
    daten = dict(aus, art=art, wer=wer[:100],
                 angelegt=jetzt().isoformat(timespec="seconds"))
    neu = os.path.join(EINGANG, kennung + ".neu")
    try:
        with open(neu, "x", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False)
        os.replace(neu, os.path.join(EINGANG, kennung + ".json"))
    except OSError as e:
        try:
            os.unlink(neu)
        except OSError:
            pass
        raise Antwort(503, "Der Auftrag liess sich nicht ablegen (%s). Auf dem "
                           "Server: sudo prolo einrichten" % e.strerror)
    return kennung, True


ROUTER_REGEL = re.compile(r"^traefik\.http\.routers\.([^.]+)\.rule$")
ROUTER_MW = re.compile(r"^traefik\.http\.routers\.([^.]+)\.middlewares$")
HOST_REGEL = re.compile(r"Host\(`([^`]+)`\)")


def schutz_lesen(labels):
    """Womit ist dieser Dienst geschuetzt? Gelesen, nicht geraten.

    Die Middleware-Kette steht in den Labels, und zwar JE ROUTER (N-84).
    Vorher reichte ein authentik@file an irgendeinem Router, und der ganze
    Dienst galt als geschuetzt - ein zweiter Router ohne Anmeldung daneben,
    genau der Fall aus §17a, fiel nicht auf. Kein authentik@file und keine
    Erklaerung heisst OFFEN, und dann steht dabei, welcher Router es ist.
    Ein fehlendes middlewares= sieht sonst aus wie ein vergessenes (N-59).

    Dieselbe Regel steht in werkzeuge/netze.sh (fuer "prolo start" und
    "prolo netze") und in werkzeuge/grenze-pruefen.sh (fuer das Repository).
    """
    if labels.get("traefik.enable") != "true":
        return ("", "")
    router = sorted({k[len("traefik.http.routers."):-len(".rule")]
                     for k in labels if ROUTER_REGEL.match(k)})
    oeffentlich = {x for x in labels.get("prolo.oeffentlich", "").split(",") if x}
    ungeschuetzt = [
        r for r in router
        if r not in oeffentlich
        and "authentik@file" not in labels.get("traefik.http.routers.%s.middlewares" % r, "")]
    # traefik.enable ohne eigenen Router: Traefik legt dann selbst einen an,
    # mit einer Vorgaberegel und ohne Middleware.
    if not router:
        ungeschuetzt = ["(Vorgabe)"]
    if ungeschuetzt and labels.get("prolo.anmeldung"):
        return (labels["prolo.anmeldung"], labels.get("prolo.anmeldung.grund", ""))
    if ungeschuetzt:
        return ("OFFEN", ", ".join(ungeschuetzt))
    if oeffentlich:
        return ("oeffentlich", ", ".join(sorted(oeffentlich)))
    return ("authentik", "")


def lage():
    """Die ganze Lage aus zwei lesenden Aufrufen."""
    roh_c = docker_lesen("/containers/json?all=1")
    roh_n = docker_lesen("/networks")

    netze = {}
    for n in roh_n:
        name = n.get("Name") or ""
        if not name:
            continue
        netze[name] = {
            "name": name,
            "treiber": n.get("Driver") or "",
            "intern": bool(n.get("Internal")),
            "container": [],
        }

    werkzeuge = {}
    for c in roh_c:
        labels = {k: str(v) for k, v in (c.get("Labels") or {}).items()}
        projekt = labels.get("com.docker.compose.project") or "(ohne Projekt)"
        dienst = labels.get("com.docker.compose.service") or ""
        cname = (c.get("Names") or ["/?"])[0].lstrip("/")
        cnetze = sorted((c.get("NetworkSettings") or {}).get("Networks") or {})
        offen = sorted({str(p.get("PublicPort")) for p in (c.get("Ports") or [])
                        if p.get("PublicPort")})
        schutz, grund = schutz_lesen(labels)
        hosts = []
        for k, v in labels.items():
            if ROUTER_REGEL.match(k):
                hosts += HOST_REGEL.findall(v)

        for n in cnetze:
            netze.setdefault(n, {"name": n, "treiber": "?", "intern": False,
                                 "container": []})
            netze[n]["container"].append(cname)

        werkzeuge.setdefault(projekt, {"name": projekt, "dienste": []})
        werkzeuge[projekt]["dienste"].append({
            "dienst": dienst or cname,
            "container": cname,
            "id": str(c.get("Id") or ""),
            "abbild": c.get("Image") or "",
            "zustand": c.get("State") or "",
            "lage": c.get("Status") or "",
            "netze": cnetze,
            "netz_label": labels.get("traefik.docker.network", ""),
            "hosts": sorted(set(hosts)),
            "schutz": schutz,
            "schutz_grund": grund,
            "ports": offen,
            "ports_grund": labels.get("prolo.ports", ""),
        })

    for w in werkzeuge.values():
        w["dienste"].sort(key=lambda d: d["dienst"])
    for n in netze.values():
        n["container"].sort()

    return {
        "werkzeuge": [werkzeuge[k] for k in sorted(werkzeuge)],
        "netze": [netze[k] for k in sorted(netze)],
    }


def beanstandungen(l):
    """Was jemand sehen muss, ohne danach zu suchen."""
    aus = []
    for w in l["werkzeuge"]:
        for d in w["dienste"]:
            if d["schutz"] == "OFFEN":
                aus.append((
                    "ungeschuetzt", "%s/%s" % (w["name"], d["dienst"]),
                    "Router ohne Anmeldung und ohne Erklaerung: %s. Entweder "
                    "an genau diesem Router middlewares=authentik@file "
                    "ergaenzen, oder - wenn das Werkzeug eine eigene "
                    "Anmeldung mitbringt - mit prolo.anmeldung=eigene "
                    "erklaeren (CLAUDE.md §17a). Soll er mit Absicht "
                    "oeffentlich sein: prolo.oeffentlich=<router>."
                    % (d["schutz_grund"] or "?")))
            if d["ports"] and not d["ports_grund"]:
                aus.append((
                    "offener Port", "%s/%s" % (w["name"], d["dienst"]),
                    "Veroeffentlicht Port %s auf dem Server. Damit ist der "
                    "Dienst an Traefik, an der Anmeldung und an der Firewall "
                    "vorbei erreichbar (CLAUDE.md §19)."
                    % ", ".join(d["ports"])))
            if d["netz_label"] and d["netz_label"] not in d["netze"]:
                aus.append((
                    "falsches Netz", "%s/%s" % (w["name"], d["dienst"]),
                    "Das Label sagt %s, der Container haengt in %s. Ein neues "
                    "Netz erreicht einen laufenden Container nicht nachtraeglich "
                    "(N-58) - auf dem Server hilft: sudo prolo start %s"
                    % (d["netz_label"], ", ".join(d["netze"]) or "keinem",
                       w["name"])))
            if d["zustand"] not in ("running", ""):
                aus.append((
                    "haelt nicht", "%s/%s" % (w["name"], d["dienst"]),
                    "Der Container ist %s (%s)." % (d["zustand"], d["lage"])))
    return aus


def werkzeuge_sicht(l, bestand):
    """Jedes Werkzeug genau einmal: Docker kennt, was einen Container hat;
    der Bestand kennt jeden Ordner - auch den eines angehaltenen Werkzeugs,
    das Docker nicht mehr nennt."""
    sicht = {}
    for w in l["werkzeuge"]:
        d = w["dienste"]
        sicht[w["name"]] = {
            "name": w["name"], "dienste": d, "gesamt": len(d),
            "laufen": sum(1 for x in d if x["zustand"] == "running"),
            "hosts": sorted({h for x in d for h in x["hosts"]}),
            "art": "", "ordner": False, "fehler": "", "bestand": None}
    for b in (bestand or {}).get("werkzeuge", []):
        s = sicht.setdefault(b["name"], {
            "name": b["name"], "dienste": [], "gesamt": 0, "laufen": 0,
            "hosts": [], "art": "", "ordner": False, "fehler": "", "bestand": None})
        s.update(art=str(b.get("art") or ""), ordner=True,
                 fehler=str(b.get("fehler") or ""), bestand=b)
        if not s["hosts"]:
            s["hosts"] = sorted(str(h) for h in b.get("hosts") or [])
    for s in sicht.values():
        # Bedienen geht, wenn der Ordner bekannt ist - oder wenn es noch gar
        # keinen Bestand gibt: dann entscheidet der Ausfuehrer, nicht die
        # Seite, ob es das Werkzeug gibt.
        s["bedienbar"] = bool(NAME.fullmatch(s["name"])) and (s["ordner"] or bestand is None)
        s["zustand"] = ("laeuft" if s["gesamt"] and s["laufen"] == s["gesamt"]
                        else "teilweise" if s["laufen"]
                        else "angehalten")
    return [sicht[k] for k in sorted(sicht)]


def teilbare_netze(l):
    """Netze, in die sich ein neues Werkzeug haengen koennte: die Netze
    der Werkzeuge - nicht Dockers eigene, nicht die internen, nicht die
    Projektnetze (<projekt>_default)."""
    return sorted(n["name"] for n in l["netze"]
                  if n["name"].startswith("netz-") and not n["intern"])


def anlegen_felder(feld):
    """Aus dem Anlegen-Formular die Felder eines neu-Auftrags - mit GENAU
    der Compose-Datei, die im Pruef-Auftrag angesehen wurde."""
    def w(k):
        return (feld.get(k) or [""])[0]
    kennung = w("pruefung")
    if not KENNUNG.fullmatch(kennung):
        raise Antwort(400, "Zu diesem Anlegen gehoert keine Pruefung. Von vorn: /neu")
    stand = json_datei(os.path.join(ERLEDIGT, kennung + ".json")) or {}
    befund = stand.get("befund") or {}
    if stand.get("art") != "compose_pruefen" or not befund.get("ok"):
        raise Antwort(400, "Diese Pruefung gibt es nicht oder sie war nicht erfolgreich. "
                           "Von vorn: /neu")
    if befund.get("gefahren"):
        raise Antwort(400, "In dieser Compose-Datei steht, womit ein Container auf den "
                           "Server greift - aus der Seite wird sie nicht angelegt.")
    try:
        with open(os.path.join(ERLEDIGT, kennung + ".compose"), encoding="utf-8") as f:
            compose = f.read(MAX_COMPOSE + 1)
    except OSError:
        raise Antwort(400, "Die gepruefte Compose-Datei ist nicht mehr da. Von vorn: /neu")
    netz = w("netz") if w("netz_wahl") == "vorhanden" else ""
    # Nur Werte fuer Variablen, die der Befund nennt und die keine
    # Geheimnisse sind - was sonst im Formular steht, faellt weg.
    offen = {x["name"] for x in befund.get("variablen") or [] if not x.get("geheim")}
    werte = {k: w("wert_" + k) for k in sorted(offen) if w("wert_" + k)}
    return {"name": str(stand.get("name") or ""), "compose": compose, "werte": werte,
            "dienst": w("dienst"), "port": w("port"), "netz": netz,
            "geteilt": w("geteilt") if netz else "", "anmeldung": w("anmeldung"),
            "grund": w("grund")}


# ---------------------------------------------------------- Darstellung
def e(s):
    return html.escape(str(s), quote=True)


TOKENS = """
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
  --feature-good:oklch(0.88 0.16 158); --track:oklch(0.94 0.004 250);
  --shadow:0 24px 60px -20px oklch(0.4 0.03 250 / 0.22);
}
body[data-theme="dark"]{
  --bg:oklch(0.16 0.012 258); --app:oklch(0.2 0.012 258);
  --surface:oklch(0.235 0.013 258); --chrome:oklch(0.205 0.012 258);
  --line:oklch(0.31 0.014 258); --line-soft:oklch(0.27 0.012 258); --hover:oklch(0.27 0.013 258);
  --ink:oklch(0.96 0.004 250); --ink-2:oklch(0.87 0.006 250); --ink-3:oklch(0.69 0.01 250);
  --accent:oklch(0.62 0.16 262); --accent-hover:oklch(0.69 0.16 262);
  --accent-soft:oklch(0.33 0.06 262); --accent-ink:oklch(0.85 0.09 262); --bar:oklch(0.38 0.06 262);
  --on-accent:oklch(0.16 0.012 258);
  --good:oklch(0.8 0.14 158); --good-soft:oklch(0.29 0.05 158);
  --warm-soft:oklch(0.33 0.05 60); --warm-ink:oklch(0.86 0.08 60);
  --danger:oklch(0.7 0.16 25); --overlay:oklch(0.2 0.012 258);
  --feature:oklch(0.31 0.07 262); --feature-ink:oklch(0.97 0.004 250);
  --feature-ink-2:oklch(0.8 0.02 250); --feature-line:oklch(0.42 0.05 262);
  --feature-good:oklch(0.85 0.15 158); --track:oklch(0.3 0.014 258);
  --shadow:0 24px 60px -20px oklch(0.05 0 0 / 0.6);
}
"""

STIL = """
@font-face{font-family:Sora;src:url(/schriften/sora-latin.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:Sora;src:url(/schriften/sora-latin-ext.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+2020-20AB}
@font-face{font-family:'Instrument Sans';src:url(/schriften/instrument-latin.woff2)format('woff2');
  font-weight:400 700;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:'Instrument Sans';src:url(/schriften/instrument-latin-ext.woff2)format('woff2');
  font-weight:400 700;font-display:swap;unicode-range:U+0100-02AF,U+1E00-1E9F,U+2020-20AB}
@font-face{font-family:'JetBrains Mono';src:url(/schriften/jetbrains-latin.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:'JetBrains Mono';src:url(/schriften/jetbrains-latin-ext.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0100-02AF,U+1E00-1E9F,U+2020-20AB}

/* Muss VOR allen display-Regeln stehen, sonst bleibt ein verstecktes
   Element sichtbar (CLAUDE.md §8.1). */
[hidden]{display:none!important}

*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink-2);
  font-family:'Instrument Sans',system-ui,sans-serif;font-size:14px;line-height:1.5;
  -webkit-text-size-adjust:100%}
h1,h2,h3,.sora{font-family:Sora,'Instrument Sans',sans-serif;font-weight:600;
  letter-spacing:-0.02em;color:var(--ink);margin:0}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}

button:focus-visible, a:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }

.huelle{display:grid;grid-template-columns:248px 1fr;min-height:100vh}
.seite{background:var(--chrome);border-right:1px solid var(--line);
  display:flex;flex-direction:column;padding:20px 0}
.marke{display:flex;gap:10px;align-items:center;padding:0 20px 22px;
  color:inherit;text-decoration:none}
/* Die Marke gehoert nach §5 auf JEDE Ansicht, oben links. Am Handy ist die
   Sidebar weg - ohne diese verkleinerte Fassung waere sie dort auch weg,
   und das ist im Browser aufgefallen, nicht beim Lesen. */
.marke.klein{display:none}
.kachel{width:30px;height:30px;border-radius:8px;background:var(--accent);
  color:var(--on-accent);display:grid;place-items:center;
  font-family:Sora,sans-serif;font-weight:600;font-size:16px;flex:none}
.marke .n{font-family:Sora,sans-serif;font-weight:600;font-size:14px;color:var(--ink);
  line-height:1.2}
.marke .u{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3)}
nav a{display:flex;align-items:center;min-height:44px;padding:0 20px;gap:10px;
  color:var(--ink-2);text-decoration:none;border-left:4px solid transparent;font-weight:500}
nav a:hover{background:var(--hover)}
nav a[aria-current=page]{border-left-color:var(--accent);background:var(--accent-soft);
  color:var(--accent-ink);font-weight:600}
nav .unten{margin-top:auto}

.haupt{min-width:0;display:flex;flex-direction:column}
header{min-height:76px;background:var(--chrome);border-bottom:1px solid var(--line);
  display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 32px}
header .titel{min-width:0}
header .ktx{font-size:12px;color:var(--ink-3)}
header a.ich{color:var(--ink-2);text-decoration:none;font-weight:500;
  min-height:44px;display:flex;align-items:center;padding:0 10px;border-radius:10px}
header a.ich:hover{background:var(--hover)}
main{padding:24px 32px 64px;max-width:1280px;margin:0 auto;width:100%;min-width:0}

.karte{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px;min-width:0}
.karte > h2{font-size:15px}
.karte .ktx{font-size:12px;color:var(--ink-3);margin-top:2px}
.reihe{display:grid;gap:16px;margin-bottom:20px}
.kpi4{grid-template-columns:repeat(4,minmax(0,1fr))}
.kpi3{grid-template-columns:repeat(3,minmax(0,1fr))}
.kpi .lbl{font-size:12px;color:var(--ink-3)}
.kpi .wert{font-family:Sora,sans-serif;font-weight:600;font-size:30px;color:var(--ink);
  letter-spacing:-0.02em;line-height:1.1}
.kpi .sub{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--ink-3);margin-top:4px}

table{width:100%;border-collapse:collapse}
thead th{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);text-align:left;font-weight:500;
  padding:0 10px 8px 0;white-space:nowrap}
tbody td{font-size:13px;color:var(--ink-2);padding:9px 10px 9px 0;
  border-top:1px solid var(--line-soft);vertical-align:top}
tbody tr:hover{background:var(--hover)}
td.z{text-align:right;font-family:'JetBrains Mono',monospace}
th.z{text-align:right}
.scroll{overflow:auto;max-height:70vh}
.scroll thead th{position:sticky;top:0;background:var(--surface)}
/* Der Scrollbalken bleibt SICHTBAR. §5 laesst ihn bei Zierflaechen
   verschwinden - bei einer Tabelle mit hunderten Zeilen ist er Inhalt:
   er sagt, dass da noch mehr ist. */

/* Spaltenbreiten von Hand. Ohne sie zieht die Abbildspalte alles an sich
   und die Zustandsspalte bricht "Up 13 days (healthy)" auf vier Zeilen -
   im Browser nachgemessen. */
table.werkzeuge{table-layout:fixed}
table.werkzeuge td:nth-child(1),table.werkzeuge th:nth-child(1){width:15%}
table.werkzeuge td:nth-child(2),table.werkzeuge th:nth-child(2){width:22%}
table.werkzeuge td:nth-child(3),table.werkzeuge th:nth-child(3){width:15%}
table.werkzeuge td:nth-child(4),table.werkzeuge th:nth-child(4){width:16%}
table.werkzeuge td:nth-child(5),table.werkzeuge th:nth-child(5){width:16%}
table.werkzeuge td:nth-child(6),table.werkzeuge th:nth-child(6){width:16%}
table.werkzeuge td, td.lang{overflow-wrap:anywhere}
/* Die Zelle mit dem Knopf bricht nie - sonst steht "Aufheben" senkrecht (F-02). */
td.griff{white-space:nowrap;width:1%}
@media (max-width:900px){
  table.werkzeuge{table-layout:auto;min-width:760px}
}

.marker{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;
  font-weight:600;white-space:nowrap}
.m-gut{background:var(--good-soft);color:var(--good)}
.m-warm{background:var(--warm-soft);color:var(--warm-ink)}
.m-weg{background:var(--accent-soft);color:var(--accent-ink)}
.m-rot{background:var(--danger);color:var(--on-accent)}

.feature{background:var(--feature);color:var(--feature-ink);border:1px solid var(--feature-line);
  border-radius:14px;padding:18px}
.feature .lbl{color:var(--feature-ink-2);font-size:12px}
.feature .wert{font-family:Sora,sans-serif;font-weight:600;font-size:36px;
  letter-spacing:-0.02em;line-height:1.1}
.feature .sub{font-family:'JetBrains Mono',monospace;font-size:11px;
  color:var(--feature-ink);margin-top:6px}

.leer{color:var(--ink-3);font-size:13px;padding:12px 0}
.hinweis{border-top:1px solid var(--line-soft);padding:12px 0}
.hinweis:first-child{border-top:0}
.hinweis .wo{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--ink)}
.hinweis .was{font-size:13px;color:var(--ink-2);margin-top:4px}

.segment{display:inline-flex;background:var(--track);border-radius:10px;padding:3px;gap:3px}
/* 44 statt der 38 aus §5: §9 ist nicht verhandelbar, und diese Seite wird
   auch am Handy benutzt. Im Browser nachgemessen - mit 38 meldete die
   Abnahme drei zu kleine Ziele je Ansicht. */
.segment button{border:0;background:transparent;color:var(--ink-3);font:inherit;font-weight:600;
  font-size:13px;border-radius:8px;padding:0 14px;min-height:44px;cursor:pointer}
.segment button[aria-pressed=true]{background:var(--surface);color:var(--ink);
  box-shadow:0 1px 2px oklch(0.4 0.03 250 / .18)}
.knopf{display:inline-flex;align-items:center;justify-content:center;min-height:44px;
  padding:0 18px;border-radius:10px;background:var(--accent);color:var(--on-accent);
  font-weight:600;text-decoration:none;border:0;font:inherit;font-weight:600;cursor:pointer}
.knopf:hover{background:var(--accent-hover)}
.erkl{font-size:12px;color:var(--ink-3);margin-top:6px}
dl.konto{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;margin:0}
dl.konto dt{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3)}
dl.konto dd{margin:0;color:var(--ink-2)}

/* Bedienen (A-02). Ein Primaerknopf je Ansicht (§5) - alles andere ist ein
   Rahmenknopf. Anhalten ist rot umrandet, aber nicht rot gefuellt: es ist
   keine Loeschung, nur eine Unterbrechung. */
.aktionen{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px}
.aktionen form{margin:0}
.knopf-rahmen{display:inline-flex;align-items:center;justify-content:center;min-height:44px;
  padding:0 16px;border-radius:10px;background:transparent;color:var(--ink);
  border:1px solid var(--line);font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.knopf-rahmen:hover{background:var(--hover)}
.knopf-gefahr{color:var(--danger);border-color:var(--danger)}
button:disabled{opacity:.55;cursor:not-allowed}
.feld{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1 1 220px}
.feld label{font-size:12px;color:var(--ink-3)}
.feld input{min-height:44px;border:1px solid var(--line);border-radius:10px;
  background:var(--surface);color:var(--ink);font:inherit;
  font-family:'JetBrains Mono',monospace;font-size:13px;padding:0 12px;min-width:0}
.feld textarea, .feld select{border:1px solid var(--line);border-radius:10px;
  background:var(--surface);color:var(--ink);font:inherit;min-width:0;padding:10px 12px}
.feld textarea{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.5;
  min-height:320px;resize:vertical}
.feld select{min-height:44px;font-family:'JetBrains Mono',monospace;font-size:13px}
fieldset{border:1px solid var(--line-soft);border-radius:10px;padding:12px 14px;margin:0;
  min-width:0;display:flex;flex-direction:column;gap:8px}
legend{font-size:12px;color:var(--ink-3);padding:0 4px}
label.wahl{display:flex;gap:10px;align-items:flex-start;min-height:44px;padding:6px 0;
  color:var(--ink-2);cursor:pointer}
label.wahl input{margin-top:3px;width:18px;height:18px;flex:none}
/* In einer Spalte sind 220 px Grundmass eine HOEHE - die Felder standen
   mit halben Bildschirmen Luft untereinander (im Browser gesehen, von
   keiner Messung gefunden). Die Zeilenregel gilt nur in einer Zeile. */
.formular{display:flex;flex-direction:column;gap:14px;margin-top:12px;max-width:760px}
.formular .feld, fieldset .feld{flex:none}
/* Ein Pfad aus einer fremden Datei hat keine Trennstelle - ohne das schob
   er die Seite bei 360 px auf 515 px Breite (im Browser gemessen). */
ul.gefahren{margin:10px 0 0;padding-left:20px;color:var(--ink-2);overflow-wrap:anywhere}
.erkl{overflow-wrap:anywhere}
ul.gefahren li{margin:4px 0}
pre.ausgabe{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.5;
  color:var(--ink-2);background:var(--app);border:1px solid var(--line-soft);
  border-radius:10px;padding:12px;margin:12px 0 0;white-space:pre-wrap;
  overflow-wrap:anywhere;max-height:60vh;overflow:auto}
/* min-width: "n8n" ist 24 px breit - im Browser gemessen. §9 verlangt
   44 x 44, auch fuer einen kurzen Namen. */
a.zeile{color:var(--ink);font-weight:600;text-decoration:none;
  display:inline-flex;align-items:center;min-height:44px;min-width:44px}
a.zeile:hover{text-decoration:underline}
a.mehr{color:var(--accent-ink);font-weight:600;text-decoration:none;
  display:inline-flex;align-items:center;min-height:44px;min-width:44px}
a.mehr:hover{text-decoration:underline}
.reiter{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.reiter a{min-height:44px;display:inline-flex;align-items:center;padding:0 12px;
  border-radius:10px;border:1px solid var(--line);color:var(--ink-2);text-decoration:none;
  font-family:'JetBrains Mono',monospace;font-size:12px}
.reiter a[aria-current=true]{background:var(--accent-soft);color:var(--accent-ink);
  border-color:transparent}
.zwei{grid-template-columns:minmax(0,1.55fr) minmax(0,1fr)}
dl.fakten{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 16px;margin:12px 0 0}
dl.fakten dt{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);padding-top:2px}
dl.fakten dd{margin:0;color:var(--ink-2);overflow-wrap:anywhere;min-width:0}
a.kpi-verweis{text-decoration:none;color:inherit;display:block}
a.kpi-verweis:hover .karte{background:var(--hover)}

table.auftraege td{vertical-align:middle}
table.auftraege td.wann{white-space:nowrap}
/* Eine kurze Karte neben einer langen wird nicht auf deren Hoehe gezogen -
   sonst steht unter "Jetzt sichern" eine halbe Seite Leere. */
.reihe.oben{align-items:start}
/* Am Handy: "Wer" weg, und Datum und Uhrzeit untereinander - sonst fiel
   "fehlgeschlagen" rechts aus der Karte (bei 360 px gemessen). */
@media (max-width:480px){
  table.auftraege .wer{display:none}
  table.auftraege td.wann{white-space:normal;width:1%}
}

.tabbar{display:none}
@media (max-width:900px){
  /* §3: am Handy nichts unter 12 px. Die 10-11 px fuer Labels, Marker und
     Tabellenkoepfe gelten am Schreibtisch - am Handy waren es 296 Stellen
     auf 14 Ansichten, im Browser gemessen (N-102). */
  thead th, dl.fakten dt, dl.konto dt, .marker, .kpi .sub, .feature .sub{font-size:12px}
  .zwei{grid-template-columns:1fr}
  .huelle{grid-template-columns:1fr}
  .seite{display:none}
  header{padding:12px 20px;min-height:auto;flex-wrap:wrap;
    justify-content:flex-start;gap:10px}
  .marke.klein{display:flex;padding:0;flex:1 1 100%;min-height:44px}
  .marke.klein .kachel{width:26px;height:26px;font-size:14px}
  .marke.klein .n{font-family:Sora,sans-serif;font-weight:600;font-size:14px;color:var(--ink)}
  header .titel{flex:1 1 auto}
  header .ich{margin-left:auto}
  main{padding:16px 20px calc(88px + env(safe-area-inset-bottom))}
  .kpi4,.kpi3{grid-template-columns:repeat(2,minmax(0,1fr))}
  .karte{border-radius:18px}
  .tabbar{display:grid;grid-template-columns:repeat(4,1fr);position:fixed;
    left:0;right:0;bottom:0;background:var(--chrome);border-top:1px solid var(--line);
    padding-bottom:env(safe-area-inset-bottom);z-index:5}
  /* 12px ist die Untergrenze aus §3 - darunter geht nichts. Damit
     "Einstellungen" bei 360px trotzdem hineinpasst, wird der Abstand
     schmaler statt der Schrift kleiner. Im Browser bei 360 nachgemessen. */
  .tabbar a{min-height:56px;display:flex;align-items:center;justify-content:center;
    color:var(--ink-3);text-decoration:none;font-size:12px;font-weight:600;
    border-top:3px solid transparent;padding:0 2px;text-align:center;
    letter-spacing:-0.01em;overflow:hidden}
  /* Nicht --accent auf --chrome: im Dunkelmodus sind das gemessene 3.3:1,
     und 12px sind kein grosser Text (§8 verlangt 4.5:1). Die
     Kontrast-Ausnahme aus §2 greift - das naechsthellere Token ist
     --accent-ink. Die Farbe als Signal bleibt: der 3px-Strich oben ist
     weiter --accent, und Farbe ist hier ohnehin nicht die einzige
     Information. */
  .tabbar a[aria-current=page]{color:var(--accent-ink);border-top-color:var(--accent)}
  .marke .u{display:none}
}
@media (max-width:420px){ .kpi4,.kpi3{grid-template-columns:1fr} }
"""

NAV = (("/", "Uebersicht"), ("/werkzeuge", "Werkzeuge"), ("/netze", "Netze"),
       ("/firewall", "Firewall"), ("/auftraege", "Auftraege"),
       ("/einstellungen", "Einstellungen"))
# Am Handy vier Eintraege, der letzte "Einstellungen" (§6). Netze und
# Firewall erreicht man dort ueber die Kacheln auf der Uebersicht.
TABS = (("/", "Uebersicht"), ("/werkzeuge", "Werkzeuge"), ("/auftraege", "Auftraege"),
        ("/einstellungen", "Einstellungen"))


def seite(titel, ktx, inhalt, pfad, ich, thema, nachher=""):
    tabs = "".join(
        '<a href="%s"%s>%s</a>' % (p, ' aria-current="page"' if p == pfad else "", e(t))
        for p, t in TABS)
    nav = "".join(
        '<a href="%s"%s%s>%s</a>'
        % (p, ' aria-current="page"' if p == pfad else "",
           ' class="unten"' if p == "/einstellungen" else "", e(t))
        for p, t in NAV)
    return """<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>%(titel)s - %(name)s</title>
<style>%(tokens)s%(stil)s</style>
</head>
<body data-theme="dark">
<div class="huelle">
  <div class="seite">
    <a class="marke" href="/"><span class="kachel" aria-hidden="true">%(marke)s</span>
      <span><span class="n">%(name)s</span><br><span class="u">%(unter)s</span></span></a>
    <nav>%(nav)s</nav>
  </div>
  <div class="haupt">
    <header>
      <a class="marke klein" href="/"><span class="kachel" aria-hidden="true">%(marke)s</span>
        <span class="n">%(name)s</span></a>
      <div class="titel"><h1 style="font-size:21px">%(titel)s</h1>
        <div class="ktx">%(ktx)s</div></div>
      <a class="ich" href="/einstellungen">%(ich)s</a>
    </header>
    <main>%(inhalt)s</main>
  </div>
</div>
<nav class="tabbar" aria-label="Bereiche">%(tabs)s</nav>
<script>
// Die Wahl liegt in der Datenbank, nicht nur im Browser - sonst ist sie auf
// dem Handy wieder weg (CLAUDE.md §6a). Der Server schreibt sie hier hinein;
// "system" folgt der Einstellung des Geraets.
(function(){
  var w = %(thema)s;
  function an(){
    var d = (w === 'system')
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : (w === 'dunkel' ? 'dark' : 'light');
    document.body.dataset.theme = d;
  }
  an();
  try{
    window.matchMedia('(prefers-color-scheme: dark)')
          .addEventListener('change', function(){ if (w === 'system') an(); });
  }catch(err){}
  // Ein Auftrag wird nicht doppelt abgeschickt (§10): der Knopf ist
  // gesperrt, sobald die Absendung laeuft. Was fragen soll, fragt vorher.
  // Gesperrt wird ERST NACH dem Absenden (setTimeout): ein gesperrter
  // Knopf faellt aus dem Formular heraus, und die Darstellung (System /
  // Hell / Dunkel) steht im Wert des gedrueckten Knopfs - im Browser
  // gemessen, als die Umschaltung sonst still nichts mehr tat.
  document.addEventListener('submit', function(ev){
    var f = ev.target, frage = f.getAttribute('data-frage');
    if (frage && !window.confirm(frage)) { ev.preventDefault(); return; }
    setTimeout(function(){
      var k = f.querySelectorAll('button');
      for (var i = 0; i < k.length; i++) { k[i].disabled = true; }
    }, 0);
  });
  // Zeiten in der Ortszeit des Betrachters (siehe zeit() im Server).
  var z = document.querySelectorAll('time[datetime]');
  for (var q = 0; q < z.length; q++) {
    var d = new Date(z[q].getAttribute('datetime'));
    if (!isNaN(d)) {
      var zw = function(n){ return (n < 10 ? '0' : '') + n; };
      z[q].textContent = zw(d.getDate()) + '.' + zw(d.getMonth() + 1) + '. '
                       + zw(d.getHours()) + ':' + zw(d.getMinutes());
    }
  }
  // Ein Protokoll steht mit der aeltesten Zeile oben - gebraucht wird
  // meist die neueste. Also steht es beim Laden am Ende.
  var p = document.querySelectorAll('pre.ausgabe');
  for (var j = 0; j < p.length; j++) { p[j].scrollTop = p[j].scrollHeight; }
})();
</script>%(nachher)s
</body></html>""" % {
        "titel": e(titel), "ktx": e(ktx), "inhalt": inhalt, "nav": nav, "tabs": tabs,
        "tokens": TOKENS, "stil": STIL, "marke": MARKE, "name": e(TITEL),
        "unter": e(UNTERZEILE), "ich": e(ich), "thema": json.dumps(thema),
        "nachher": nachher,
    }


def marker_schutz(s, grund):
    if s == "authentik":
        return '<span class="marker m-gut">Authentik</span>'
    if s == "OFFEN":
        return ('<span class="marker m-rot">OFFEN - ohne Anmeldung</span>'
                + (' <span class="ktx mono">%s</span>' % e(grund) if grund else ""))
    if s == "oeffentlich":
        return '<span class="marker m-warm">oeffentlich: %s</span>' % e(grund)
    if s:
        return ('<span class="marker m-warm">eigene Anmeldung</span>'
                + (' <span class="ktx">%s</span>' % e(grund) if grund else ""))
    return '<span class="ktx">kein Router</span>'


# Farbe ist nie die einzige Information (§2): jeder Marker traegt das Wort.
STATUS = {
    "ok": ("m-gut", "erledigt"),
    "fehler": ("m-rot", "fehlgeschlagen"),
    "zeit": ("m-rot", "Zeit abgelaufen"),
    "abgelehnt": ("m-warm", "abgelehnt"),
    "abgebrochen": ("m-warm", "abgebrochen"),
    "laeuft": ("m-weg", "laeuft"),
    "wartet": ("m-weg", "wartet"),
}


def marker_status(status):
    klasse, wort = STATUS.get(status, ("m-warm", status or "?"))
    return '<span class="marker %s">%s</span>' % (klasse, e(wort))


def marker_zustand(z):
    return {"laeuft": '<span class="marker m-gut">laeuft</span>',
            "teilweise": '<span class="marker m-rot">laeuft teilweise</span>',
            }.get(z, '<span class="marker m-warm">angehalten</span>')


def kpi(lbl, wert, sub, verweis=""):
    karte = ('<div class="karte kpi"><div class="lbl">%s</div>'
             '<div class="wert">%s</div><div class="sub">%s</div></div>'
             % (e(lbl), e(wert), e(sub)))
    if verweis:
        return '<a class="kpi-verweis" href="%s">%s</a>' % (e(verweis), karte)
    return karte


def zahl(n):
    """12345 -> '12.345' (§7). Was keine Zahl ist, steht als '-' da."""
    try:
        return "{:,}".format(int(n)).replace(",", ".")
    except (TypeError, ValueError):
        return "-"


def zeit_kurz(iso):
    """'2026-09-30T12:04:05+02:00' -> '30.09. 12:04' (§7)."""
    try:
        z = datetime.datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    return z.strftime("%d.%m. %H:%M")


def zeit(iso):
    """Eine Zeit, die der Browser in die Ortszeit des Betrachters setzt.
    Der Container laeuft in UTC und kennt keine Zeitzonen (kein tzdata im
    Abbild); der Browser kennt die richtige. Ohne Skript steht die
    Serverzeit da - falsch um die Zeitverschiebung, aber nicht leer."""
    kurz = zeit_kurz(iso)
    if not kurz:
        return "-"
    return '<time datetime="%s">%s</time>' % (e(iso), e(kurz))


def ziel_text(a):
    return ziel_von(a) or "-"


def auftrag_zeilen(liste):
    # Auftrag und Ziel in EINER Spalte: am Handy waren es fuenf Spalten auf
    # 320 px, und der Stand - das Wichtigste - fiel rechts heraus.
    return "".join(
        '<tr><td class="mono wann">%s</td><td><a class="zeile" href="/auftrag/%s">%s</a>'
        ' <span class="ktx mono">%s</span></td><td class="wer">%s</td><td>%s</td></tr>'
        % (zeit(a.get("angelegt") or a.get("beginn")), e(a["kennung"]),
           e(ARTEN.get(a.get("art"), ((), a.get("art") or "?"))[1]),
           e(ziel_von(a)), e(a.get("wer") or "-"), marker_status(a.get("status")))
        for a in liste)


def auftrag_tabelle(liste, leer):
    if not liste:
        return '<div class="leer">%s</div>' % leer
    return ('<div class="scroll" style="margin-top:12px"><table class="auftraege">'
            '<thead><tr><th>Wann</th><th>Auftrag</th><th class="wer">Wer</th>'
            '<th>Stand</th></tr></thead><tbody>%s</tbody></table></div>'
            % auftrag_zeilen(liste))


def knopf(art, ziel_feld, ziel, beschriftung, klasse="knopf-rahmen", frage="",
          gesperrt=""):
    """Ein Auftrag ist ein eigenes Formular mit versteckten Feldern - so
    geht der Wert nicht verloren, wenn der Knopf beim Absenden gesperrt
    wird (§10)."""
    if gesperrt:
        return ('<span><button type="button" class="%s" disabled>%s</button>'
                '<span class="erkl" style="display:block">%s</span></span>'
                % (klasse, e(beschriftung), e(gesperrt)))
    return ('<form method="post" action="/auftrag"%s>'
            '<input type="hidden" name="art" value="%s">%s'
            '<button type="submit" class="%s">%s</button></form>'
            % (' data-frage="%s"' % e(frage) if frage else "", e(art),
               '<input type="hidden" name="%s" value="%s">' % (e(ziel_feld), e(ziel))
               if ziel_feld else "", klasse, e(beschriftung)))


def firewall_kachel(fw):
    if fw is None:
        return kpi("Firewall", "-", "noch keine Lage", "/firewall")
    b = fw["bouncer"]
    if not fw["crowdsec"].get("laeuft"):
        sub = "CrowdSec laeuft nicht"
    elif not b:
        sub = "kein Bouncer - nichts wird gesperrt"
    elif all((x.get("still_s") is None or x.get("still_s") > BOUNCER_STILL_S) for x in b):
        sub = "Bouncer still - nichts wird gesperrt"
    else:
        sub = "Sperren, der Bouncer holt ab"
    return kpi("Firewall", len(fw["sperren"]), sub, "/firewall")


def ansicht_uebersicht(l, auftraege, betrieb, fw=None):
    mangel = beanstandungen(l)
    dienste = [d for w in l["werkzeuge"] for d in w["dienste"]]
    laeuft = sum(1 for d in dienste if d["zustand"] == "running")
    routen = sorted({h for d in dienste for h in d["hosts"]})

    if mangel:
        hero = ('<div class="feature"><div class="lbl">Zu klaeren</div>'
                '<div class="wert">%d</div>'
                '<div class="sub">Punkte, die jemand ansehen sollte</div></div>'
                % len(mangel))
    else:
        hero = ('<div class="feature"><div class="lbl">Zu klaeren</div>'
                '<div class="wert">0</div>'
                '<div class="sub">Kein Router ohne Anmeldung, kein offener Port</div></div>')

    liste = "".join(
        '<div class="hinweis"><div class="wo">%s &middot; %s</div>'
        '<div class="was">%s</div></div>' % (e(art), e(wo), e(text))
        for art, wo, text in mangel) or \
        '<div class="leer">Nichts zu klaeren. Jeder Router hat eine Anmeldung ' \
        'oder eine Erklaerung, kein Dienst veroeffentlicht einen Port, und ' \
        'jeder Container haengt in dem Netz, das sein Label nennt.</div>'

    letzte = auftrag_tabelle(
        auftraege[:5],
        "Noch kein Auftrag. Starten, Aktualisieren und Anhalten gehen auf der "
        "Seite eines Werkzeugs &ndash; <a class=\"mehr\" href=\"/werkzeuge\">"
        "zu den Werkzeugen</a>." if betrieb else
        "Noch kein Auftrag. Bedienen darf die Gruppe %s." % e(GRUPPE_BETRIEB))

    # Die Hero-Kennzahl steht ZUERST - am Handy ist sie sonst die vierte
    # Karte, und §6 verlangt sie oben. Was der Betreiber als erstes sehen
    # soll, ist nicht "9 Werkzeuge", sondern "3 Punkte zu klaeren".
    return ('<div class="reihe kpi3">%s</div>'
            '<div class="reihe kpi4">%s%s%s%s</div>'
            '<div class="reihe zwei">'
            '<div class="karte"><h2>Zu klaeren</h2>'
            '<div class="ktx">Aus den Labels der laufenden Container gelesen, '
            'nicht geraten.</div><div style="margin-top:10px">%s</div></div>'
            '<div class="karte"><h2>Letzte Auftraege</h2>'
            '<div class="ktx">Was von hier aus angestossen wurde. '
            '<a class="mehr" href="/auftraege">Alle</a></div>%s</div></div>'
            % (hero + kpi("Routen", len(routen), "Hostnamen mit Zertifikat")
               + kpi("Container", "%d / %d" % (laeuft, len(dienste)), "laufen / gesamt"),
               kpi("Werkzeuge", len(l["werkzeuge"]), "Compose-Projekte", "/werkzeuge"),
               kpi("Netze", len(l["netze"]), "im Docker", "/netze"),
               firewall_kachel(fw),
               kpi("Fassung", VERSION, "Prolo Admin"),
               liste, letzte))


def ansicht_werkzeuge(sicht, bestand, betrieb=False):
    zeilen = []
    for s in sicht:
        schutz = sorted({d["schutz"] for d in s["dienste"] if d["schutz"]})
        offen = [d for d in s["dienste"] if d["schutz"] == "OFFEN"
                 or (d["ports"] and not d["ports_grund"])]
        if not s["dienste"]:
            # Ohne Container gibt es keine Labels zu lesen - "kein Router"
            # waere geraten, und bei einem angehaltenen Wiki falsch.
            schutz_html = '<span class="ktx">erst nach dem Start lesbar</span>'
        elif offen:
            schutz_html = '<span class="marker m-rot">Luecke</span>'
        elif "authentik" in schutz:
            schutz_html = '<span class="marker m-gut">Authentik</span>'
        elif schutz:
            schutz_html = '<span class="marker m-warm">%s</span>' % e(
                "eigene Anmeldung" if schutz[0] not in ("oeffentlich",) else "oeffentlich")
        else:
            schutz_html = '<span class="ktx">kein Router</span>'
        name = ('<a class="zeile" href="/werkzeug/%s">%s</a>' % (e(s["name"]), e(s["name"]))
                if NAME.fullmatch(s["name"]) else '<b>%s</b>' % e(s["name"]))
        zeilen.append(
            '<tr><td>%s<div class="ktx">%s</div></td><td>%s<div class="ktx mono">%d / %d</div></td>'
            '<td>%s</td><td>%s</td></tr>'
            % (name, e(s["art"] or ("-" if s["ordner"] else "ohne Ordner")),
               marker_zustand(s["zustand"]), s["laufen"], s["gesamt"],
               "<br>".join('<span class="mono">%s</span>' % e(h) for h in s["hosts"])
               or '<span class="ktx">-</span>', schutz_html))
    hinweis = ""
    if bestand is None:
        hinweis = ('<div class="hinweis"><div class="was">Nur, was Docker kennt: '
                   'der Bestand der Werkzeugordner fehlt noch. Angehaltene '
                   'Werkzeuge stehen erst hier, wenn das Auftragsbuch auf dem '
                   'Server eingerichtet ist: <span class="mono">sudo prolo '
                   'einrichten</span> (gefahrlos zu wiederholen).</div></div>')
    if not zeilen:
        return ('<div class="karte"><h2>Werkzeuge</h2>%s'
                '<div class="leer">Es laeuft noch nichts, und der Bestand nennt '
                'kein Werkzeug. Ein neues legt man auf dem Server an:<br>'
                '<span class="mono">sudo prolo neu &lt;name&gt;</span></div></div>'
                % hinweis)
    anlegen = ('<div class="aktionen"><a class="knopf" href="/neu">Werkzeug anlegen</a>'
               '<span class="erkl">aus der Compose-Datei eines Herstellers</span></div>'
               if betrieb else "")
    return ('<div class="karte"><h2>Werkzeuge</h2>'
            '<div class="ktx">Ein Werkzeug ist ein Ordner mit docker-compose.yml. '
            'Bedienen, Protokolle und Einzelheiten auf seiner Seite.</div>' + anlegen + '%s'
            '<div class="scroll" style="margin-top:12px"><table class="liste">'
            '<thead><tr><th>Werkzeug</th><th>Zustand</th><th>Erreichbar unter</th>'
            '<th>Schutz</th></tr></thead><tbody>%s</tbody></table></div></div>'
            % (hinweis, "".join(zeilen)))


def ansicht_werkzeug(s, auftraege, betrieb, protokoll):
    """Ein Werkzeug: Bedienen, Dienste, Protokoll, letzte Auftraege."""
    name = s["name"]
    b = s["bestand"] or {}
    # Bedienen. Genau ein Primaerknopf (§5): laeuft es, ist das
    # "Neu starten", sonst "Starten".
    if not betrieb:
        bedienen = ('<div class="leer">Bedienen darf die Gruppe <span class="mono">'
                    '%s</span>. Zuweisen laesst sich das in Authentik, nicht hier.</div>'
                    % e(GRUPPE_BETRIEB))
    elif not s["bedienbar"]:
        bedienen = ('<div class="leer">Zu diesem Namen gibt es auf dem Server keinen '
                    'Werkzeugordner - der Container wurde nicht mit prolo angelegt. '
                    'Von hier aus laesst er sich darum nicht bedienen.</div>')
    else:
        k = []
        if s["zustand"] == "angehalten":
            k.append(knopf("start", "werkzeug", name, "Starten", "knopf"))
        else:
            k.append(knopf("neustart", "werkzeug", name, "Neu starten", "knopf"))
            # "prolo start" auf ein laufendes Werkzeug legt neu an, was sich
            # an seiner Konfiguration geaendert hat - ein neues Netz bei
            # Traefik zum Beispiel. Neu starten tut das nicht (N-58).
            k.append(knopf("start", "werkzeug", name,
                           "Fehlende starten" if s["zustand"] == "teilweise"
                           else "Konfiguration uebernehmen"))
        k.append(knopf("aktualisieren", "werkzeug", name, "Aktualisieren"))
        k.append(knopf("pruefen", "werkzeug", name, "Pruefen"))
        if s["zustand"] != "angehalten":
            k.append(knopf(
                "stop", "werkzeug", name, "Anhalten", "knopf-rahmen knopf-gefahr",
                frage="%s anhalten? Es ist danach nicht mehr erreichbar, bis es "
                      "wieder gestartet wird. Daten bleiben." % name,
                gesperrt=("Haelt den Zugang offen - anhalten nur auf dem Server: "
                          "sudo prolo stop %s" % name) if name in KERN else ""))
        bedienen = ('<div class="aktionen">%s</div>'
                    '<div class="erkl">Jeder Knopf legt einen Auftrag ab; ausgefuehrt '
                    'wird er auf dem Server mit prolo &ndash; mit Startsperre, und '
                    'beim Aktualisieren mit Sicherung vorher und Rueckweg. '
                    '&bdquo;Konfiguration uebernehmen&ldquo; legt neu an, was sich '
                    'an den Dateien geaendert hat (z. B. ein neues Netz bei Traefik); '
                    '&bdquo;Neu starten&ldquo; startet nur neu.</div>'
                    % "".join(k))

    dienste = "".join(
        '<tr><td><b>%s</b><div class="ktx mono">%s</div></td><td class="mono">%s</td>'
        '<td>%s<div class="ktx">%s</div></td><td class="mono">%s</td><td>%s</td></tr>'
        % (e(d["dienst"]), e(d["container"]), e(d["abbild"]),
           '<span class="marker m-gut">laeuft</span>' if d["zustand"] == "running"
           else '<span class="marker m-rot">%s</span>' % e(d["zustand"]), e(d["lage"]),
           e(", ".join(d["netze"])) or "-",
           marker_schutz(d["schutz"], d["schutz_grund"])
           + ('<br><span class="marker m-rot">Port %s offen</span>' % e(", ".join(d["ports"]))
              if d["ports"] and not d["ports_grund"] else ""))
        for d in s["dienste"])
    if not dienste:
        abb = "".join('<tr><td><b>%s</b></td><td class="mono">%s</td>'
                      '<td><span class="marker m-warm">angehalten</span></td>'
                      '<td class="mono">%s</td><td>-</td></tr>'
                      % (e(d.get("dienst", "")), e(d.get("abbild", "")),
                         e(", ".join(b.get("netze") or [])) or "-")
                      for d in b.get("dienste") or [] if isinstance(d, dict))
        dienste = abb or ('<tr><td colspan="5" class="leer">Kein Container und '
                          'kein Bestand - ist der Ordner gerade erst angelegt, '
                          'erscheint er nach dem naechsten Auftrag.</td></tr>')
    fakten = ('<dl class="fakten"><dt>Art</dt><dd>%s</dd><dt>Erreichbar</dt><dd class="mono">%s</dd>'
              '<dt>Netze</dt><dd class="mono">%s</dd><dt>Volumes</dt><dd class="mono">%s</dd>'
              '<dt>Sicherung</dt><dd>%s</dd></dl>'
              % (e({"eigen": "eigener Code", "fremd": "Fremdwerkzeug (Herstellerdatei + unsere Zutat)",
                    "plattform": "Teil der Plattform"}.get(s["art"], s["art"] or "unbekannt")),
                 e(", ".join(s["hosts"])) or "-",
                 e(", ".join(b.get("netze") or sorted({n for d in s["dienste"] for n in d["netze"]})))
                 or "-",
                 e(", ".join(b.get("volumes") or [])) or "-",
                 ("sicherung.conf vorhanden" if b.get("sicherung")
                  else ('<span class="marker m-rot">keine sicherung.conf</span>'
                        if s["ordner"] else "unbekannt"))))
    if s["fehler"]:
        fakten += ('<div class="hinweis"><div class="wo">docker compose config</div>'
                   '<div class="was">%s</div></div>' % e(s["fehler"]))

    if protokoll is None:
        prot = ('<div class="leer">Protokolle liest die Gruppe <span class="mono">%s'
                '</span>.</div>' % e(GRUPPE_BETRIEB)) if not betrieb else \
               '<div class="leer">Kein laufender Container - kein Protokoll.</div>'
    else:
        wahl, text = protokoll
        reiter = "".join(
            '<a href="/werkzeug/%s?dienst=%s"%s>%s</a>'
            % (e(name), e(d["dienst"]), ' aria-current="true"' if d["dienst"] == wahl else "",
               e(d["dienst"]))
            for d in s["dienste"]) if len(s["dienste"]) > 1 else ""
        prot = ('%s<pre class="ausgabe">%s</pre>'
                '<div class="aktionen"><a class="knopf-rahmen" href="/werkzeug/%s?dienst=%s">'
                'Neu laden</a><span class="erkl">die letzten %d Zeilen</span></div>'
                % ('<div class="reiter">%s</div>' % reiter if reiter else "",
                   e(text) or "(leer)", e(name), e(wahl), PROTOKOLL_ZEILEN))

    eigene = [a for a in auftraege if a.get("werkzeug") == name][:10]
    return ('<div class="reihe zwei">'
            '<div class="karte"><h2>Bedienen</h2><div class="ktx">%s</div>%s</div>'
            '<div class="karte"><h2>Auf dem Server</h2><div class="ktx">Aus dem Bestand '
            'der Werkzeugordner.</div>%s</div></div>'
            '<div class="reihe" style="grid-template-columns:1fr">'
            '<div class="karte"><h2>Dienste</h2><div class="ktx">Ein Dienst ist ein '
            'Container aus der Compose-Datei.</div>'
            '<div class="scroll" style="margin-top:12px"><table class="werkzeuge">'
            '<thead><tr><th>Dienst</th><th>Abbild</th><th>Zustand</th><th>Netz</th>'
            '<th>Schutz</th></tr></thead><tbody>%s</tbody></table></div></div>'
            '<div class="karte"><h2>Protokoll</h2><div class="ktx">Was der Container '
            'selbst ausgibt.</div>%s</div>'
            '<div class="karte"><h2>Auftraege fuer %s</h2>%s</div></div>'
            % (e({"laeuft": "Laeuft.", "teilweise": "Laeuft nur teilweise.",
                  "angehalten": "Angehalten."}[s["zustand"]]),
               bedienen, fakten, dienste, prot, e(name),
               auftrag_tabelle(eigene, "Fuer dieses Werkzeug noch kein Auftrag.")))


def ansicht_neu(name="", compose=""):
    """Eine Compose-Datei einwerfen (A-03). Erst ansehen, dann anlegen - der
    erste Schritt hat keine Nebenwirkung."""
    return ('<div class="reihe zwei oben"><div class="karte"><h2>Compose-Datei einwerfen</h2>'
            '<div class="ktx">Die Datei des Herstellers, so wie sie in seiner Doku steht. '
            'Sie wird unveraendert uebernommen; Netz, Route, Anmeldung und Grenzen '
            'kommen von uns daneben.</div>'
            '<form method="post" action="/neu/pruefen" class="formular">'
            '<div class="feld"><label for="name">Name - wird Ordner und Subdomain</label>'
            '<input id="name" name="name" required maxlength="40" value="%s" '
            'pattern="[a-z0-9][a-z0-9\\-]{0,39}" placeholder="z. B. uptime" '
            'autocomplete="off" spellcheck="false"></div>'
            '<div class="feld"><label for="compose">docker-compose.yml des Herstellers</label>'
            '<textarea id="compose" name="compose" required spellcheck="false" '
            'placeholder="services:&#10;  app:&#10;    image: hersteller/app:1.2.3">%s</textarea></div>'
            '<div class="aktionen"><button type="submit" class="knopf">Pruefen</button>'
            '<span class="erkl">legt noch nichts an</span></div></form></div>'
            '<div class="karte"><h2>Was passiert</h2><div class="ktx">Zwei Schritte.</div>'
            '<dl class="fakten"><dt>1 Pruefen</dt><dd>Der Server liest die Datei mit docker '
            'compose: welche Dienste, welche Ports, welche Volumes, welche Variablen - und '
            'ob darin etwas steht, womit ein Container auf den Server greift (privileged, '
            'Host-Netz, Docker-Socket, Pfade vom Server). Dann wird nichts angelegt.</dd>'
            '<dt>2 Anlegen</dt><dd>Mit Dienst, Port, Netz und Anmeldung, die du bestaetigst: '
            'Ordner, override-Datei (eigenes Netz, Route, Zertifikat, Grenzen, ohne die '
            'Ports des Herstellers), Sicherung aller Volumes, geheime Variablen fuer '
            'prolo geheimnisse.</dd>'
            '<dt>Danach</dt><dd>Name beim DNS-Anbieter eintragen, bei Authentik die '
            'Anwendung anlegen, Starten.</dd></dl></div></div>'
            % (e(name), e(compose)))


def befund_html(stand, netze):
    """Der Befund eines compose_pruefen-Auftrags - und, wenn nichts dagegen
    spricht, das Formular zum Anlegen."""
    b = stand.get("befund") or {}
    name = str(stand.get("name") or "")
    if not b.get("ok"):
        return ('<div class="karte"><h2>Nicht zu gebrauchen</h2><div class="hinweis">'
                '<div class="was">%s</div></div><div class="aktionen">'
                '<a class="knopf-rahmen" href="/neu">Zurueck</a></div></div>'
                % e(b.get("fehler") or "Der Server hat keinen Befund geliefert."))
    dienste = "".join(
        '<tr><td class="mono"><b>%s</b></td><td class="mono">%s</td><td class="mono">%s</td>'
        '<td>%s</td></tr>'
        % (e(d["name"]), e(d["abbild"]),
           e(", ".join(sorted({p["ziel"] for p in d["ports"]} | set(d["expose"])))) or "-",
           '<span class="marker m-warm">Hilfsdienst</span>' if d.get("hilfsdienst") else "")
        for d in b.get("dienste") or [])
    teile = ['<div class="karte"><h2>Dienste</h2><div class="ktx">Was die Datei startet. '
             'Die Ports des Herstellers werden nicht veroeffentlicht - erreichbar ist nur '
             'der Dienst, zu dem Traefik fuehrt.</div><div class="scroll" style="margin-top:12px">'
             '<table><thead><tr><th>Dienst</th><th>Abbild</th><th>Ports</th><th></th></tr>'
             '</thead><tbody>%s</tbody></table></div></div>' % dienste]
    gefahren = b.get("gefahren") or []
    if gefahren:
        teile.append(
            '<div class="karte" style="border-color:var(--danger)"><h2>Wird nicht angelegt</h2>'
            '<div class="ktx">In der Datei steht, womit ein Container aus seinem Kaefig auf '
            'den Server greift:</div><ul class="gefahren">%s</ul>'
            '<div class="erkl">Aus der Seite wird so etwas nie angelegt - sie ist die Stelle, '
            'an der man am ehesten hereinkommt. Muss es sein: auf dem Server, dort wird '
            'einzeln nachgefragt: <span class="mono">sudo prolo neu %s --compose &lt;datei&gt;</span>'
            '</div></div>'
            % ("".join('<li><b class="mono">%s</b>: %s</li>' % (e(g["dienst"]), e(g["was"]))
                       for g in gefahren), e(name)))
    elif not b.get("name_frei", True):
        teile.append('<div class="karte"><h2>Den Namen gibt es schon</h2><div class="leer">'
                     'Ein Werkzeug %s liegt schon auf dem Server. Anderen Namen waehlen: '
                     '<a class="mehr" href="/neu">zurueck</a>.</div></div>' % e(name))
    else:
        teile.append(anlegen_html(stand, b, netze))
    extra = []
    if b.get("volumes"):
        extra.append('<dt>Volumes</dt><dd class="mono">%s</dd>' % e(", ".join(b["volumes"])))
    if b.get("binds"):
        extra.append('<dt>Ordner</dt><dd class="mono">%s</dd>'
                     % e(", ".join(sorted({x["pfad"] for x in b["binds"]}))))
    if b.get("variablen"):
        extra.append('<dt>Variablen</dt><dd class="mono">%s</dd>' % ", ".join(
            e(v["name"]) + (' <span class="marker m-weg">geheim</span>' if v.get("geheim") else "")
            for v in b["variablen"]))
    if extra:
        teile.append('<div class="karte"><h2>Was gesichert und gefuellt wird</h2>'
                     '<div class="ktx">Volumes und Ordner kommen in die sicherung.conf, '
                     'geheime Variablen in die geheimnisse.conf - prolo geheimnisse '
                     '--verteilen fuellt sie mit Zufallswerten.</div>'
                     '<dl class="fakten">%s</dl></div>' % "".join(extra))
    return "".join(teile)


def anlegen_html(stand, b, netze):
    v = b.get("vorschlag") or {}
    name = str(stand.get("name") or "")
    optionen = "".join(
        '<option value="%s" data-port="%s"%s>%s%s</option>'
        % (e(d["name"]),
           e((sorted({p["ziel"] for p in d["ports"]} | set(d["expose"])) or [""])[0]
             if len({p["ziel"] for p in d["ports"]} | set(d["expose"])) == 1 else ""),
           " selected" if d["name"] == v.get("dienst") else "", e(d["name"]),
           " (Hilfsdienst)" if d.get("hilfsdienst") else "")
        for d in b.get("dienste") or [])
    vorhanden = "".join('<option value="%s">%s</option>' % (e(n), e(n)) for n in netze)
    offen = [x for x in b.get("variablen") or [] if not x.get("geheim")]
    werte = ""
    if offen:
        werte = ('<fieldset><legend>Werte fuer die .env - Geheimnisse wuerfelt der Server '
                 'selbst</legend>%s</fieldset>' % "".join(
                     '<div class="feld"><label for="w-%(n)s">%(n)s%(p)s</label>'
                     '<input id="w-%(n)s" name="wert_%(n)s" value="%(v)s" maxlength="500"%(r)s '
                     'spellcheck="false"></div>'
                     % {"n": e(x["name"]), "v": e(x.get("vorgabe") or ""),
                        "p": " (Pflicht)" if x.get("pflicht") else " (hat eine Vorgabe)",
                        "r": " required" if x.get("pflicht") else ""}
                     for x in offen))
    return (
        '<div class="karte"><h2>Anlegen</h2><div class="ktx">Pruefe den Vorschlag - er ist aus '
        'der Datei gelesen, nicht geraten; wo sie nichts Eindeutiges sagt, ist das Feld leer.</div>'
        '<form method="post" action="/neu/anlegen" class="formular">'
        '<input type="hidden" name="pruefung" value="%(k)s">'
        '<div class="feld"><label for="dienst">Zu welchem Dienst fuehrt Traefik</label>'
        '<select id="dienst" name="dienst">%(opt)s</select></div>'
        '<div class="feld"><label for="port">Auf welchem Port lauscht er im Container</label>'
        '<input id="port" name="port" inputmode="numeric" pattern="[0-9]{1,5}" required '
        'value="%(port)s" placeholder="steht in der Doku des Herstellers"></div>'
        '<fieldset><legend>Netz</legend>'
        '<label class="wahl"><input type="radio" name="netz_wahl" value="neu" checked>'
        '<span>eigenes Netz <span class="mono">netz-%(name)s</span><span class="erkl" '
        'style="display:block">empfohlen: was hier kompromittiert wird, erreicht nichts '
        'anderes (N-45)</span></span></label>'
        '<label class="wahl"><input type="radio" name="netz_wahl" value="vorhanden">'
        '<span>ein vorhandenes teilen</span></label>'
        '<div class="feld"><label for="netz">Welches</label><select id="netz" name="netz">'
        '<option value="">-</option>%(vorh)s</select></div>'
        '<div class="feld"><label for="geteilt">Warum teilen (nur beim Teilen, Pflicht)</label>'
        '<input id="geteilt" name="geteilt" maxlength="200"></div></fieldset>'
        '<fieldset><legend>Anmeldung - eine Entscheidung, darum ohne Vorgabe</legend>'
        '<label class="wahl"><input type="radio" name="anmeldung" value="authentik" required>'
        '<span>Authentik davor<span class="erkl" style="display:block">niemand kommt an das '
        'Werkzeug, ohne sich zentral anzumelden</span></span></label>'
        '<label class="wahl"><input type="radio" name="anmeldung" value="eigene">'
        '<span>die eigene Anmeldung des Werkzeugs<span class="erkl" style="display:block">nur, '
        'wenn Webhooks, API oder eine Handy-App an Authentik scheitern - dann 2FA im Werkzeug '
        'einschalten (§17a)</span></span></label>'
        '<div class="feld"><label for="grund">Grund (bei eigener Anmeldung Pflicht)</label>'
        '<input id="grund" name="grund" maxlength="200"></div></fieldset>'
        '%(werte)s'
        '<div class="aktionen"><button type="submit" class="knopf">Anlegen</button>'
        '<span class="erkl">startet noch nicht</span></div></form></div>'
        '<script>(function(){var s=document.getElementById("dienst"),'
        'p=document.getElementById("port");s.addEventListener("change",function(){'
        'var o=s.options[s.selectedIndex];p.value=o.getAttribute("data-port")||"";});})();'
        '</script>'
        % {"k": e(stand["kennung"]), "opt": optionen, "port": e(v.get("port") or ""),
           "name": e(name), "vorh": vorhanden, "werte": werte})


def ansicht_netze(l, betrieb):
    zeilen = "".join(
        '<tr><td class="mono"><b>%s</b></td><td class="mono">%s</td><td>%s</td>'
        '<td class="z">%d</td><td class="mono">%s</td></tr>'
        % (e(n["name"]), e(n["treiber"]),
           '<span class="marker m-gut">intern</span>' if n["intern"]
           else '<span class="ktx">nach aussen</span>',
           len(n["container"]), e(", ".join(n["container"])) or "-")
        for n in l["netze"])
    anlegen = ""
    if betrieb:
        anlegen = ('<div class="karte"><h2>Netz anlegen</h2>'
                   '<div class="ktx">Legt das Netz in Docker an und traegt es bei '
                   'Traefik ein (prolo netze anlegen). Danach muss Traefik neu '
                   'angelegt werden &ndash; auf der Seite von traefik: Starten '
                   'bzw. Neu starten reicht nicht, der Auftrag sagt es.</div>'
                   '<form method="post" action="/auftrag" class="aktionen">'
                   '<input type="hidden" name="art" value="netz_anlegen">'
                   '<div class="feld"><label for="netz">Name</label>'
                   '<input id="netz" name="netz" required maxlength="40" '
                   'pattern="[a-z0-9][a-z0-9\\-]{0,39}" placeholder="netz-werkzeug" '
                   'autocomplete="off" spellcheck="false"></div>'
                   '<button type="submit" class="knopf" style="align-self:flex-end">'
                   'Netz anlegen</button></form>'
                   '<div class="erkl">Nur Kleinbuchstaben, Ziffern und Bindestrich. '
                   'Ueblich: netz-&lt;werkzeug&gt; &ndash; jedes Werkzeug in seinem '
                   'eigenen Netz, nur Traefik in allen (N-45).</div></div>')
    if not zeilen:
        # Ein leerer Zustand erklaert den naechsten Schritt (§14a.4) -
        # "keine Netze" allein ist eine Feststellung, kein Hinweis.
        return ('<div class="reihe" style="grid-template-columns:1fr">'
                '<div class="karte"><h2>Netze</h2>'
                '<div class="leer">Docker meldet keine Netze. Entweder laeuft '
                'noch nichts, oder der Vermittler vor dem Docker-Socket '
                'antwortet nicht. Auf dem Server nachsehen:<br>'
                '<span class="mono">prolo netze</span> &ndash; zeigt dasselbe '
                'aus den Dateien.<br><span class="mono">sudo prolo protokoll '
                'socket-proxy</span> &ndash; sagt, ob der Vermittler laeuft.'
                '</div></div>%s</div>' % anlegen)
    return ('<div class="reihe" style="grid-template-columns:1fr">'
            '<div class="karte"><h2>Netze</h2>'
            '<div class="ktx">Jedes Werkzeug haengt in seinem eigenen Netz, nur '
            'Traefik in allen (N-45). Schliessen und umziehen geht auf dem '
            'Server mit <span class="mono">prolo netze</span>.</div>'
            '<div class="scroll" style="margin-top:12px"><table>'
            '<thead><tr><th>Netz</th><th>Treiber</th><th>Art</th>'
            '<th>Container</th><th>Wer haengt drin</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div>%s</div>' % (zeilen, anlegen))


HERKUNFT = {"crowdsec": ("m-weg", "erkannt"), "cscli": ("m-warm", "von Hand"),
            "capi": ("m-weg", "Gemeinschaft"), "lists": ("m-weg", "Blockliste")}


def firewall_warnungen(fw):
    """Was an der Firewall nicht stimmt - je Ursache ein Satz mit dem Weg
    daraus (§7). Leer heisst: nichts zu klaeren."""
    w = []
    alter = None
    try:
        alter = (jetzt() - datetime.datetime.fromisoformat(str(fw.get("stand")))).total_seconds()
    except (TypeError, ValueError):
        pass
    if alter is None or alter > FIREWALL_ALT_S:
        w.append(("Stand", "Die Lage ist aelter als %d Minuten - der Zeitgeber auf dem Server "
                           "schreibt sie sonst alle fuenf. Auf dem Server: systemctl status "
                           "prolo-auftraege.timer" % (FIREWALL_ALT_S // 60)))
    if not fw["crowdsec"].get("laeuft"):
        w.append(("CrowdSec", "laeuft nicht - es wird nichts erkannt und nichts Neues "
                              "gesperrt. Starten auf der Seite von crowdsec."))
        return w + [("Meldung", f) for f in fw["fehler"] if "laeuft nicht" not in f]
    if not fw["bouncer"]:
        w.append(("Bouncer", "Kein Bouncer angemeldet: CrowdSec erkennt Angriffe, aber "
                             "niemand sperrt sie aus. Auf dem Server: sudo prolo einrichten "
                             "(nennt die zwei Befehle, gefahrlos zu wiederholen)."))
    for b in fw["bouncer"]:
        still = b.get("still_s")
        if still is None:
            w.append(("Bouncer", "%s hat noch nie abgefragt - laeuft er? Auf dem Server: "
                                 "systemctl status crowdsec-firewall-bouncer" % b.get("name")))
        elif still > BOUNCER_STILL_S:
            w.append(("Bouncer", "%s fragt seit %d Minuten nicht mehr ab - neue Sperren "
                                 "kommen nicht an. Auf dem Server: systemctl status "
                                 "crowdsec-firewall-bouncer" % (b.get("name"), still // 60)))
    for quelle, n in sorted(fw["gelesen"].items()):
        if not n.get("zeilen"):
            w.append(("Quelle", "Aus %s kam seit dem Start von CrowdSec keine Zeile - "
                                "stimmt der Pfad in crowdsec/erfassung/?" % quelle))
    return w + [("Meldung", f) for f in fw["fehler"]]


def firewall_formular(art, felder, knopf_text, klasse="knopf-rahmen"):
    return ('<form method="post" action="/auftrag" class="formular">'
            '<input type="hidden" name="art" value="%s">%s'
            '<div class="aktionen"><button type="submit" class="%s">%s</button></div></form>'
            % (e(art), felder, klasse, e(knopf_text)))


def ansicht_firewall(fw, betrieb, quelle, auftraege):
    if fw is None:
        return ('<div class="reihe" style="grid-template-columns:1fr"><div class="karte">'
                '<h2>Noch keine Lage</h2><div class="leer">Die Lage der Firewall schreibt der '
                'Server alle fuenf Minuten - sobald es den Ordner crowdsec/ gibt und das '
                'Auftragsbuch eingerichtet ist. Auf dem Server: sudo prolo einrichten '
                '(gefahrlos zu wiederholen). Was die Firewall tut: crowdsec/LIESMICH.md.'
                '</div>%s</div></div>'
                % (knopf("firewall_lesen", "", "", "Jetzt nachsehen") if betrieb else ""))

    sperren, meldungen, freigaben = fw["sperren"], fw["meldungen"], fw["freigaben"]
    mit_sperre = sum(1 for m in meldungen if m.get("zur_sperre"))
    lebt = [b for b in fw["bouncer"]
            if b.get("still_s") is not None and b["still_s"] <= BOUNCER_STILL_S]
    if lebt:
        bouncer = kpi("Bouncer", "holt ab", "zuletzt vor %d s" % min(b["still_s"] for b in lebt))
    elif fw["bouncer"]:
        bouncer = kpi("Bouncer", "still", "neue Sperren kommen nicht an")
    else:
        bouncer = kpi("Bouncer", "fehlt", "es wird nichts gesperrt")
    hero = ('<div class="feature"><div class="lbl">Gesperrt</div><div class="wert">%d</div>'
            '<div class="sub">Adressen, dazu %s aus der Gemeinschafts-Blockliste</div></div>'
            % (len(sperren), zahl(fw["gemeinschaft"])))

    warnungen = firewall_warnungen(fw)
    warn = ('<div class="reihe" style="grid-template-columns:1fr"><div class="karte">'
            '<h2>Zu klaeren</h2>%s</div></div>'
            % "".join('<div class="hinweis"><div class="wo">%s</div><div class="was">%s</div></div>'
                      % (e(wo), e(was)) for wo, was in warnungen)) if warnungen else ""

    def herkunft(o):
        klasse, wort = HERKUNFT.get(str(o or "").lower(), ("m-warm", o or "?"))
        return '<span class="marker %s">%s</span>' % (klasse, e(wort))

    # Zwei Spalten, nicht drei: bei 360 px stand der Knopf sonst halb
    # verdeckt im Scrollkasten ("Au...") - nur im Bild gefunden (F-02).
    zeilen = "".join(
        '<tr><td class="lang"><span class="mono">%s</span> %s<div class="ktx">%s%s &middot; noch %s</div></td>'
        '<td class="griff">%s</td></tr>'
        % (e(s.get("wert")), herkunft(s.get("herkunft")), e(s.get("regel")),
           (" &middot; " + e(s.get("land"))) if s.get("land") else "", e(s.get("bleibt")),
           knopf("firewall_aufheben", "adresse", s.get("wert") or "", "Aufheben",
                 frage="Sperre fuer %s aufheben?" % s.get("wert")) if betrieb else "")
        for s in sperren[:200])
    tabelle_sperren = ('<div class="scroll" style="margin-top:12px"><table><thead><tr>'
                       '<th>Adresse und Grund</th><th></th></tr></thead>'
                       '<tbody>%s</tbody></table></div>' % zeilen) if sperren else \
        ('<div class="leer">Gerade ist keine Adresse gesperrt. Wer in eine Regel laeuft, '
         'steht hier - mit dem Grund und wie lange noch.</div>')

    if betrieb:
        dauer = "".join('<option value="%s"%s>%s</option>'
                        % (w, " selected" if w == "24h" else "", t) for w, t in DAUERN)
        sperren_form = firewall_formular(
            "firewall_sperren",
            '<div class="feld"><label for="fw-adresse">Adresse oder Netz</label>'
            '<input id="fw-adresse" name="adresse" required maxlength="49" autocomplete="off" '
            'spellcheck="false" placeholder="203.0.113.7 oder 203.0.113.0/24"></div>'
            '<div class="feld"><label for="fw-dauer">Dauer</label>'
            '<select id="fw-dauer" name="dauer">%s</select></div>'
            '<div class="feld"><label for="fw-grund">Grund</label>'
            '<input id="fw-grund" name="grund" required maxlength="200" '
            'placeholder="steht spaeter an der Sperre"></div>' % dauer,
            "Sperren", "knopf")
        eigene = ('<div class="erkl">Deine Adresse gerade: <span class="mono">%s</span> - '
                  'die laesst sich hier nicht sperren.</div>%s'
                  % (e(quelle), firewall_formular(
                      "firewall_erlauben",
                      '<input type="hidden" name="adresse" value="%s">'
                      '<input type="hidden" name="grund" value="eigene Adresse">' % e(quelle),
                      "Meine Adresse freigeben"))) if quelle else ""
        sperren_karte = ('<div class="karte"><h2>Adresse sperren</h2><div class="ktx">'
                         'Sofort, fuer alle Werkzeuge und SSH. Interne Adressen und Netze '
                         'groesser als /16 lehnt der Server ab.</div>%s%s</div>'
                         % (sperren_form, eigene))
    else:
        sperren_karte = ('<div class="karte"><h2>Adresse sperren</h2><div class="leer">'
                         'Sperren und Freigeben darf die Gruppe %s.</div></div>'
                         % e(GRUPPE_BETRIEB))

    mzeilen = "".join(
        '<tr><td class="mono wann">%s</td><td class="lang"><span class="mono">%s</span>%s'
        '<div class="ktx">%s &middot; %s Ereignis(se)</div></td><td class="griff">%s</td></tr>'
        % (zeit(m.get("zeit")), e(m.get("adresse")),
           (' <span class="ktx">%s</span>' % e(m.get("land"))) if m.get("land") else "",
           e(m.get("regel")), e(m.get("anzahl")),
           '<span class="marker m-rot">Sperre</span>' if m.get("zur_sperre") else
           '<span class="marker m-weg">beobachtet</span>' if m.get("beobachtet") else
           '<span class="marker m-warm">keine Sperre</span>')
        for m in meldungen[:100])
    tabelle_meldungen = ('<div class="scroll" style="margin-top:12px"><table><thead><tr>'
                         '<th>Wann</th><th>Wer und was</th><th>Folge</th></tr></thead>'
                         '<tbody>%s</tbody></table></div>' % mzeilen) if meldungen else \
        ('<div class="leer">In den letzten sieben Tagen hat keine Regel angeschlagen. '
         'Scanner finden jeden Server - bleibt das tagelang leer, lohnt ein Blick auf '
         '&bdquo;Was gelesen wird&ldquo;.</div>')

    fzeilen = "".join(
        '<tr><td class="lang"><span class="mono">%s</span><div class="ktx">%s</div></td>'
        '<td class="griff">%s</td></tr>'
        % (e(f.get("wert")), e(f.get("grund")),
           knopf("firewall_nicht_erlauben", "adresse", f.get("wert") or "", "Entfernen",
                 frage="%s wieder sperrbar machen?" % f.get("wert")) if betrieb else "")
        for f in freigaben)
    freigabe_form = firewall_formular(
        "firewall_erlauben",
        '<div class="feld"><label for="fr-adresse">Adresse oder Netz</label>'
        '<input id="fr-adresse" name="adresse" required maxlength="49" autocomplete="off" '
        'spellcheck="false"></div><div class="feld"><label for="fr-grund">Grund</label>'
        '<input id="fr-grund" name="grund" required maxlength="200" '
        'placeholder="z. B. Buero, Zuhause"></div>', "Freigeben") if betrieb else ""
    freigabe_karte = ('<div class="karte"><h2>Freigabeliste</h2><div class="ktx">Diese Adressen '
                      'werden nie gesperrt, auch wenn sie in eine Regel laufen.</div>%s%s</div>'
                      % (('<div class="scroll" style="margin-top:12px"><table><tbody>%s</tbody>'
                          '</table></div>' % fzeilen) if freigaben else
                         '<div class="leer">Noch leer. Die eigene Adresse gehoert hierher - '
                         'wer sich selbst aussperrt, kommt nur noch ueber den Server herein.</div>',
                         freigabe_form))

    regeln = "".join(
        '<div class="hinweis"><div class="wo mono">%s</div><div class="was">%s</div>'
        '<div class="erkl">%s &middot; crowdsec/regeln/%s</div></div>'
        % (e(r.get("name")), e(r.get("beschreibung")), e(r.get("mass")), e(r.get("datei")))
        for r in fw["regeln"]) or \
        '<div class="leer">Keine eigenen Regeln - nur die aus dem Hub.</div>'
    gelesen = "".join(
        '<div class="hinweis"><div class="wo mono">%s</div><div class="was">%s Zeilen, '
        '%s erkannt</div></div>' % (e(q), zahl(n.get("zeilen")), zahl(n.get("erkannt")))
        for q, n in sorted(fw["gelesen"].items()))
    gelesen_karte = ('<div class="karte"><h2>Was gelesen wird</h2><div class="ktx">Seit dem '
                     'letzten Start von CrowdSec.</div>%s<div class="erkl">Dazu, freiwillig: '
                     'die CrowdSec-Konsole als Karte und Verlauf - <a class="mehr" '
                     'href="https://app.crowdsec.net" rel="noopener">app.crowdsec.net</a>, '
                     'Einrichtung in crowdsec/LIESMICH.md.</div></div>'
                     % (gelesen or '<div class="leer">Keine Quelle eingetragen.</div>'))

    letzte = auftrag_tabelle(auftraege[:5], "Noch kein Auftrag an die Firewall.")
    nachsehen = knopf("firewall_lesen", "", "", "Jetzt nachsehen") if betrieb else ""

    return ('<div class="reihe kpi4">%s%s%s%s</div>%s'
            '<div class="reihe zwei oben"><div class="karte"><h2>Aktive Sperren</h2>'
            '<div class="ktx">Eigene und erkannte - die Gemeinschafts-Blockliste steht nur '
            'als Zahl oben.</div>%s</div>%s</div>'
            '<div class="reihe zwei oben"><div class="karte"><h2>Meldungen</h2>'
            '<div class="ktx">Die letzten sieben Tage, neueste zuerst.</div>%s</div>%s</div>'
            '<div class="reihe zwei oben"><div class="karte"><h2>Eigene Regeln</h2>'
            '<div class="ktx">In crowdsec/regeln/ - eine neue Datei, dann crowdsec neu '
            'starten (crowdsec/LIESMICH.md).</div>%s</div>%s</div>'
            '<div class="reihe" style="grid-template-columns:1fr"><div class="karte">'
            '<h2>Letzte Auftraege an die Firewall</h2><div class="ktx">Die Lage oben frischt '
            'der Server alle fuenf Minuten auf und nach jedem Auftrag.</div>%s'
            '<div class="aktionen" style="margin-top:12px">%s</div></div></div>'
            % (hero, kpi("Meldungen", len(meldungen), "in 7 Tagen, %d mit Sperre" % mit_sperre),
               bouncer, kpi("Freigaben", len(freigaben), "werden nie gesperrt"), warn,
               tabelle_sperren, sperren_karte, tabelle_meldungen, freigabe_karte,
               regeln, gelesen_karte, letzte, nachsehen))


def ansicht_auftraege(auftraege, betrieb):
    sichern = ""
    if betrieb:
        sichern = ('<div class="karte"><h2>Sicherung</h2><div class="ktx">Alle '
                   'Werkzeuge nach ihrer sicherung.conf, verschluesselt '
                   '(prolo sichern). Die Kopie gehoert danach weg vom Server.</div>'
                   '<div class="aktionen">%s</div></div>'
                   % knopf("sichern", "", "", "Jetzt sichern", "knopf"))
    return ('<div class="reihe zwei oben"><div class="karte"><h2>Auftraege</h2>'
            '<div class="ktx">Neueste zuerst. Ausgefuehrt werden sie auf dem Server '
            'mit prolo; wer sie angestossen hat, steht im Protokoll des Servers.'
            '</div>%s</div>%s</div>'
            % (auftrag_tabelle(auftraege, "Noch kein Auftrag. Starten, Aktualisieren "
                               "und Anhalten gehen auf der Seite eines Werkzeugs."),
               sichern or '<div class="karte"><h2>Sicherung</h2><div class="leer">'
                          'Anstossen darf die Gruppe %s.</div></div>' % e(GRUPPE_BETRIEB)))


def auftrag_hinweis(lage):
    """Was jemand wissen muss, der vor einem wartenden Auftrag steht."""
    if lage.get("status") != "wartet":
        return ""
    try:
        alter = (jetzt() - datetime.datetime.fromisoformat(lage.get("angelegt"))).total_seconds()
    except (TypeError, ValueError):
        alter = 0
    if alter < 30:
        return "Wird gleich abgeholt."
    return ("Seit %d Sekunden nicht abgeholt. Der Waechter auf dem Server laeuft "
            "vermutlich nicht. Nachsehen: sudo systemctl status "
            "prolo-auftraege.path - eingerichtet wird er mit sudo prolo "
            "einrichten." % alter)


def auftrag_json(lage, ausgabe):
    klasse, wort = STATUS.get(lage.get("status"), ("m-warm", lage.get("status") or "?"))
    return {"kennung": lage["kennung"], "status": lage.get("status"),
            "wort": wort, "klasse": klasse, "ausgabe": ausgabe,
            "hinweis": auftrag_hinweis(lage),
            "offen": lage.get("status") in OFFEN_STATUS}


def ansicht_auftrag(lage, ausgabe, netze=(), betrieb=False):
    d = auftrag_json(lage, ausgabe)
    fakten = ('<dl class="fakten"><dt>Auftrag</dt><dd>%s</dd><dt>Ziel</dt><dd class="mono">%s</dd>'
              '<dt>Wer</dt><dd>%s</dd><dt>Angelegt</dt><dd class="mono">%s</dd>'
              '<dt>Beginn</dt><dd class="mono">%s</dd><dt>Ende</dt><dd class="mono">%s</dd>'
              '<dt>Rueckgabe</dt><dd class="mono">%s</dd></dl>'
              % (e(ARTEN.get(lage.get("art"), ((), lage.get("art") or "?"))[1]),
                 e(ziel_text(lage)), e(lage.get("wer") or "-"),
                 zeit(lage.get("angelegt")), zeit(lage.get("beginn")), zeit(lage.get("ende")),
                 e(lage.get("rueckgabe") if lage.get("rueckgabe") is not None else "-")))
    grund = ('<div class="hinweis"><div class="wo">Grund</div><div class="was">%s</div></div>'
             % e(lage["grund"])) if lage.get("grund") else ""
    weiter = ""
    ziel = lage.get("werkzeug") or (lage.get("name") if lage.get("art") == "neu" else "")
    if ziel and NAME.fullmatch(str(ziel)):
        weiter = ('<a class="mehr" href="/werkzeug/%s">zu %s</a>' % (e(ziel), e(ziel)))
    if str(lage.get("art") or "").startswith("firewall_"):
        weiter = ('<a class="mehr" href="/firewall">zur Firewall</a> <span class="erkl">'
                  'Die Lage dort ist in wenigen Sekunden aufgefrischt.</span>')
    # A-03: nach dem Anlegen ist Starten der naechste Griff.
    if lage.get("art") == "neu" and lage.get("status") == "ok" and betrieb and ziel:
        weiter = ('<div class="aktionen">%s%s</div><div class="erkl">Vorher: den Namen beim '
                  'DNS-Anbieter eintragen und - bei Authentik davor - dort die Anwendung '
                  'anlegen und dem Outpost zuweisen. Ist ein neues Netz entstanden, muss '
                  'Traefik es uebernehmen: auf der Seite von <a class="mehr" '
                  'href="/werkzeug/traefik">traefik</a> &bdquo;Konfiguration '
                  'uebernehmen&ldquo;. Was sonst noch fehlt, steht in der Ausgabe unter '
                  '"Noch zu tun".</div>'
                  % (knopf("start", "werkzeug", ziel, "Starten", "knopf"), weiter))
    return ('<div class="reihe zwei"><div class="karte"><h2>Stand</h2>'
            '<div style="margin-top:10px"><span id="stand" class="marker %s">%s</span></div>'
            '<div id="hinweis" class="erkl">%s</div>%s%s<div>%s</div></div>'
            '<div class="karte"><h2>Ausgabe</h2><div class="ktx">Was prolo auf dem '
            'Server geschrieben hat.</div><pre class="ausgabe" id="ausgabe">%s</pre></div></div>'
            % (d["klasse"], e(d["wort"]), e(d["hinweis"]), fakten, grund, weiter,
               e(ausgabe) or ("(noch keine)" if d["offen"] else "(keine)"))
            + ('<div class="reihe" style="grid-template-columns:1fr">%s</div>'
               % befund_html(lage, netze)
               if lage.get("art") == "compose_pruefen" and lage.get("status") in ("ok", "fehler")
               and betrieb else ""))


def auftrag_nachladen(kennung):
    """Solange ein Auftrag offen ist, holt die Seite alle zwei Sekunden den
    Stand - ohne Neuladen, die Ausgabe waechst mit. Ist er fertig, laedt
    die Seite einmal neu und zeigt Ende und Rueckgabe."""
    return """<script>
(function(){
  var k = %s, s = document.getElementById('stand'),
      h = document.getElementById('hinweis'), a = document.getElementById('ausgabe');
  function holen(){
    fetch('/api/auftrag/' + k, {credentials: 'same-origin'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){
        if (!d) { setTimeout(holen, 5000); return; }
        s.textContent = d.wort; s.className = 'marker ' + d.klasse;
        h.textContent = d.hinweis;
        if (d.ausgabe) { a.textContent = d.ausgabe; a.scrollTop = a.scrollHeight; }
        if (d.offen) { setTimeout(holen, 2000); } else { location.reload(); }
      })
      .catch(function(){ setTimeout(holen, 5000); });
  }
  setTimeout(holen, 1500);
})();
</script>""" % json.dumps(kennung)


def ansicht_einstellungen(nutzer, meldung, betrieb):
    seg = "".join(
        '<button type="submit" name="thema" value="%s" aria-pressed="%s">%s</button>'
        % (w, "true" if nutzer["thema"] == w else "false", t)
        for w, t in (("system", "System"), ("hell", "Hell"), ("dunkel", "Dunkel")))
    kopf = ('<div class="karte" style="border-color:var(--good);margin-bottom:16px">'
            '%s</div>' % e(meldung)) if meldung else ""
    return kopf + """
<div class="reihe" style="grid-template-columns:1fr">
  <div class="karte">
    <h2>Darstellung</h2>
    <div class="ktx">Gilt fuer dieses Konto auf allen Geraeten - die Wahl liegt
      in der Datenbank, nicht nur in diesem Browser.</div>
    <form method="post" action="/einstellungen/thema" style="margin-top:12px">
      <div class="segment" role="group" aria-label="Darstellung">%(seg)s</div>
      <div class="erkl">System folgt der Einstellung des Geraets.</div>
    </form>
  </div>
  <div class="karte">
    <h2>Was diese Seite tut</h2>
    <div class="ktx">Und warum sie es nicht selbst tut.</div>
    <p style="font-size:13px;margin:12px 0 0">
      Sie <b>liest</b> ueber den Vermittler vor dem Docker-Socket &ndash; die
      Container, die Netze und die Protokolle &ndash; und sonst nichts. Sie hat
      keinen Zugriff auf <span class="mono">/opt/stack</span>, also auch nicht
      auf <span class="mono">.env</span>-Dateien oder Zertifikate.</p>
    <p style="font-size:13px;margin:10px 0 0">
      Sie <b>handelt ueber Auftraege</b>. Starten, Anhalten, Aktualisieren,
      Sichern: die Seite legt einen Auftrag ab, und auf dem Server fuehrt
      <span class="mono">prolo</span> ihn aus &ndash; mit derselben Startsperre,
      Sicherung und demselben Rueckweg wie auf der Kommandozeile. Schreibenden
      Zugriff auf Docker hat sie nicht: wer den hat, hat den ganzen Server.</p>
    <dl class="konto" style="margin-top:12px">
      <dt>Sehen</dt><dd>Gruppe <span class="mono">%(lesen)s</span></dd>
      <dt>Bedienen</dt><dd>Gruppe <span class="mono">%(betrieb_gr)s</span> &ndash;
        %(du)s</dd>
    </dl>
  </div>
  <div class="karte">
    <h2>Konto</h2>
    <div class="ktx">Verwaltet wird das zentral in Authentik, nicht hier.</div>
    <dl class="konto" style="margin-top:12px">
      <dt>Anmeldename</dt><dd class="mono">%(id)s</dd>
      <dt>Anzeigename</dt><dd>%(name)s</dd>
      <dt>E-Mail</dt><dd class="mono">%(mail)s</dd>
    </dl>
    <p style="margin:16px 0 0">
      <a class="knopf" href="/outpost.goauthentik.io/sign_out">Abmelden / neu laden</a></p>
    <div class="erkl">Das ist eine Weiterleitung zur Anmeldung &ndash; die Seite
      laedt danach neu.</div>
  </div>
</div>""" % {"seg": seg, "id": e(nutzer["nutzer_id"]),
             "name": e(nutzer["anzeigename"] or "-"),
             "mail": e(nutzer["email"] or "-"),
             "lesen": e(GRUPPE_LESEN), "betrieb_gr": e(GRUPPE_BETRIEB),
             "du": "du bist darin" if betrieb else "du bist nicht darin"}


# -------------------------------------------------------------- Dienst
class Handler(BaseHTTPRequestHandler):
    server_version = "prolo-admin/" + VERSION
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Keine Kopfzeilen ins Protokoll (§22) - nur Weg und Kode.
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ---------------------------------------------------- Die zwei Tueren
    def einlass_pruefen(self):
        if urlparse(self.path).path in EINLASS_FREI:
            return
        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")
        if hmac.compare_digest(mit, EINLASS_B):
            return
        raise Antwort(401, "Diese Anfrage kam nicht ueber den Zugang dieses "
                           "Servers.")

    def angemeldet(self):
        """Wer ist das, und darf er hier sein?

        Zwei Tueren (§17): Authentik laesst aufs Grundstueck, diese Pruefung
        ins Haus. Ausgewertet werden nur die EIGENEN Gruppen - alles, was
        nicht mit '%s' anfaengt, wird hier an einer Stelle verworfen und
        nicht an sieben.
        """
        kennung = (self.headers.get("X-Authentik-Username") or "").strip()
        if not kennung:
            raise Antwort(401, "Nicht angemeldet. Diese Seite liegt hinter der "
                               "Anmeldung.")
        roh = self.headers.get("X-Authentik-Groups") or ""
        gruppen = {g.strip() for g in re.split(r"[,|;]", roh) if g.strip()}
        meine = {g for g in gruppen if g.startswith(GRUPPE_PRAEFIX)}
        if GRUPPE_LESEN not in meine:
            raise Antwort(403,
                          "Dafuer braucht es die Gruppe '%s'. In Authentik "
                          "zuweisen lassen - hier kann das niemand."
                          % GRUPPE_LESEN)
        nutzer = nutzer_holen(kennung,
                              (self.headers.get("X-Authentik-Name") or "").strip(),
                              (self.headers.get("X-Authentik-Email") or "").strip())
        nutzer["betrieb"] = GRUPPE_BETRIEB in meine
        return nutzer

    def betrieb_noetig(self, nutzer):
        if not nutzer["betrieb"]:
            raise Antwort(403, "Bedienen darf die Gruppe '%s'. In Authentik "
                               "zuweisen lassen - hier kann das niemand."
                               % GRUPPE_BETRIEB)

    def gleicher_ursprung(self):
        """Kommt diese Absendung von dieser Seite?

        Ohne das koennte eine fremde Seite im Namen des Angemeldeten
        absenden. Viel steht hier nicht auf dem Spiel - nur die Darstellung -,
        aber eine Tuer, die man einmal offen laesst, bleibt offen, wenn
        spaeter mehr dahinter liegt.
        """
        ziel = self.headers.get("Host") or ""
        quelle = self.headers.get("Origin") or ""
        if not quelle:
            # Kein Origin: dann muss der Browser sagen, dass es dieselbe
            # Seite ist. Sagt er gar nichts, wird abgelehnt.
            if (self.headers.get("Sec-Fetch-Site") or "") == "same-origin":
                return
            raise Antwort(403, "Die Absendung kam nicht von dieser Seite.")
        if urlparse(quelle).netloc != ziel:
            raise Antwort(403, "Die Absendung kam nicht von dieser Seite.")

    # -------------------------------------------------------- Verteilung
    def do_GET(self):
        self._lauf(self.verteilen_get)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._lauf(self.verteilen_post)

    def _lauf(self, was):
        try:
            self.einlass_pruefen()
            was()
        except (BrokenPipeError, ConnectionResetError):
            # Der Browser ist weg, bevor die Antwort ankam. Das ist kein
            # Fehler des Dienstes, und eine Fehlerseite hinterherzuschicken
            # hiesse, noch einmal in dieselbe geschlossene Leitung zu
            # schreiben (N-82).
            self.close_connection = True
        except Antwort as a:
            self.fehlerseite(a.kode, a.text)
        except Exception:
            # Kein interner Pfad und kein Datenbankfehler im Klartext (§22).
            import traceback
            traceback.print_exc()
            self.fehlerseite(500, "Da ist bei uns etwas schiefgegangen. Der "
                                  "Fehler steht im Protokoll des Servers.")

    def verteilen_get(self):
        url = urlparse(self.path)
        pfad = url.path
        if pfad == "/gesundheit":
            return self.roh(200, b"ok", "text/plain; charset=utf-8")
        if pfad == "/api/version":
            return self.json_aus(200, {"name": "prolo-admin", "version": VERSION})
        if pfad.startswith("/schriften/"):
            return self.schrift(pfad)

        nutzer = self.angemeldet()
        fr = parse_qs(url.query)
        ich = nutzer["anzeigename"] or nutzer["nutzer_id"]
        betrieb = nutzer["betrieb"]

        def zeigen(titel, ktx, inhalt, nav, nachher=""):
            return self.html(seite(titel, ktx, inhalt, nav, ich, nutzer["thema"], nachher))

        if pfad == "/einstellungen":
            return zeigen("Einstellungen", "Darstellung, Rechte und Konto",
                          ansicht_einstellungen(nutzer, (fr.get("ok") or [""])[0], betrieb),
                          pfad)
        # "stand", nicht "lage": der Name gehoert der Funktion lage() weiter
        # unten, und eine lokale Zuweisung verdeckt sie in der GANZEN Methode.
        if pfad.startswith("/api/auftrag/"):
            stand, ausgabe = auftrag_lesen(pfad[len("/api/auftrag/"):])
            return self.json_aus(200, auftrag_json(stand, ausgabe))
        if pfad.startswith("/auftrag/"):
            kennung = pfad[len("/auftrag/"):]
            stand, ausgabe = auftrag_lesen(kennung)
            titel = "%s %s" % (ARTEN.get(stand.get("art"), ((), stand.get("art") or "?"))[1],
                               ziel_von(stand))
            netze = []
            if stand.get("art") == "compose_pruefen" and betrieb:
                try:
                    netze = teilbare_netze(lage())
                except Antwort:
                    netze = []
            return zeigen(titel.strip(), "Auftrag %s" % kennung,
                          ansicht_auftrag(stand, ausgabe, netze, betrieb), "/auftraege",
                          auftrag_nachladen(kennung)
                          if stand.get("status") in OFFEN_STATUS else "")
        if pfad == "/neu":
            self.betrieb_noetig(nutzer)
            return zeigen("Werkzeug anlegen", "Aus der Compose-Datei eines Herstellers",
                          ansicht_neu(), "/werkzeuge")
        if pfad == "/auftraege":
            return zeigen("Auftraege", "Was von hier aus angestossen wurde",
                          ansicht_auftraege(auftraege_lesen(), betrieb), pfad)
        if pfad == "/api/lage":
            return self.json_aus(200, lage())
        if pfad == "/firewall":
            fw = firewall_lesen()
            ktx = ("CrowdSec erkennt, der Bouncer sperrt - Stand %s" % zeit_kurz(fw.get("stand"))
                   if fw and zeit_kurz(fw.get("stand")) else "CrowdSec erkennt, der Bouncer sperrt")
            return zeigen("Firewall", ktx,
                          ansicht_firewall(fw, betrieb, quelle_von(self.headers.get("X-Forwarded-For")),
                                           [a for a in auftraege_lesen()
                                            if str(a.get("art") or "").startswith("firewall_")]),
                          pfad)

        l = lage()
        if pfad == "/":
            return zeigen("Uebersicht", "Was laeuft, und was jemand ansehen sollte",
                          ansicht_uebersicht(l, auftraege_lesen(grenze=5), betrieb,
                                             firewall_lesen()), pfad)
        if pfad == "/werkzeuge":
            bestand = bestand_lesen()
            return zeigen("Werkzeuge", "Laufend und angehalten, mit Namen und Schutz",
                          ansicht_werkzeuge(werkzeuge_sicht(l, bestand), bestand, betrieb), pfad)
        if pfad.startswith("/werkzeug/"):
            name = pfad[len("/werkzeug/"):]
            s = next((x for x in werkzeuge_sicht(l, bestand_lesen())
                      if x["name"] == name and NAME.fullmatch(name)), None)
            if s is None:
                raise Antwort(404, "Ein Werkzeug %s kennt weder Docker noch der "
                                   "Bestand. Alle Werkzeuge: /werkzeuge" % name[:40])
            protokoll = None
            laufend = [d for d in s["dienste"] if d["id"]]
            if betrieb and laufend:
                wahl = (fr.get("dienst") or [""])[0]
                d = next((x for x in laufend if x["dienst"] == wahl), laufend[0])
                try:
                    text = protokoll_lesen(d["id"])
                except Antwort as a:
                    text = "Das Protokoll liess sich nicht lesen: %s" % a.text
                protokoll = (d["dienst"], text)
            ktx = "%s - %d von %d Diensten laufen" % (
                {"eigen": "eigener Code", "fremd": "Fremdwerkzeug",
                 "plattform": "Plattform"}.get(s["art"], "Werkzeug"),
                s["laufen"], s["gesamt"])
            return zeigen(name, ktx, ansicht_werkzeug(s, auftraege_lesen(), betrieb,
                                                      protokoll), "/werkzeuge")
        if pfad == "/netze":
            return zeigen("Netze", "Wer haengt wo - und was das bedeutet",
                          ansicht_netze(l, betrieb), pfad)
        raise Antwort(404, "Diese Seite gibt es nicht. Zurueck zur Uebersicht: /")

    def formular(self, grenze=4096):
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > grenze:
            raise Antwort(413, "Das war zu viel fuer ein Formular.")
        return parse_qs(self.rfile.read(laenge).decode("utf-8", "replace"))

    def verteilen_post(self):
        pfad = urlparse(self.path).path
        nutzer = self.angemeldet()
        if pfad == "/einstellungen/thema":
            self.gleicher_ursprung()
            feld = self.formular()
            thema_setzen(nutzer["nutzer_id"], (feld.get("thema") or [""])[0])
            return self.weiter("/einstellungen?ok=Darstellung+gespeichert.")
        if pfad == "/auftrag":
            self.gleicher_ursprung()
            self.betrieb_noetig(nutzer)
            feld = self.formular()
            kennung, _ = auftrag_ablegen(
                (feld.get("art") or [""])[0],
                {k: (feld.get(k) or [""])[0]
                 for k in ("werkzeug", "netz", "adresse", "dauer", "grund")},
                nutzer["nutzer_id"], quelle_von(self.headers.get("X-Forwarded-For")))
            return self.weiter("/auftrag/%s" % kennung)
        if pfad == "/neu/pruefen":
            self.gleicher_ursprung()
            self.betrieb_noetig(nutzer)
            # Eine Compose-Datei ist groesser als ein Knopfdruck: bis 256 KiB,
            # URL-kodiert bis zum Dreifachen.
            feld = self.formular(grenze=3 * MAX_COMPOSE + 4096)
            kennung, _ = auftrag_ablegen(
                "compose_pruefen",
                {"name": (feld.get("name") or [""])[0],
                 "compose": (feld.get("compose") or [""])[0]},
                nutzer["nutzer_id"])
            return self.weiter("/auftrag/%s" % kennung)
        if pfad == "/neu/anlegen":
            self.gleicher_ursprung()
            self.betrieb_noetig(nutzer)
            feld = self.formular()
            kennung, _ = auftrag_ablegen("neu", anlegen_felder(feld), nutzer["nutzer_id"])
            return self.weiter("/auftrag/%s" % kennung)
        raise Antwort(404, "Diesen Weg gibt es nicht.")

    # ----------------------------------------------------------- Antwort
    def schrift(self, pfad):
        name = os.path.basename(pfad)
        if not re.fullmatch(r"[a-z0-9-]+\.(woff2|txt)", name):
            raise Antwort(404, "Diese Datei gibt es nicht.")
        ziel = os.path.join(SCHRIFTEN, name)
        if not os.path.isfile(ziel):
            raise Antwort(404, "Diese Datei gibt es nicht.")
        with open(ziel, "rb") as f:
            inhalt = f.read()
        art = "font/woff2" if name.endswith(".woff2") else "text/plain; charset=utf-8"
        self.roh(200, inhalt, art, {"Cache-Control": "public, max-age=31536000, immutable"})

    def roh(self, kode, koerper, art, extra=None):
        self.send_response(kode)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        # Diese Seite laedt nichts von aussen und braucht kein eval.
        # connect-src 'self': die Auftragsseite holt ihren Stand nach (A-02).
        # Ohne das verbot default-src 'none' dem Browser jeden fetch - der
        # Auftrag lief durch, und die Seite stand fuer immer auf "wartet".
        # Im Browser gemessen, nicht in den Tests: die kennen keine CSP.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "font-src 'self'; script-src 'unsafe-inline'; "
                         "connect-src 'self'; "
                         "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def html(self, text):
        self.roh(200, text.encode("utf-8"), "text/html; charset=utf-8")

    def json_aus(self, kode, obj):
        self.roh(kode, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                 "application/json; charset=utf-8")

    def weiter(self, ziel):
        self.send_response(303)
        self.send_header("Location", ziel)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def fehlerseite(self, kode, text):
        # Eine Fehlerseite sagt, was zu tun ist (§7) - nicht nur, was kaputt
        # ist. Und sie fuehrt zurueck, statt den Menschen stehen zu lassen.
        koerper = ("""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(k)d - %(name)s</title><style>%(tokens)s%(stil)s</style></head>
<body data-theme="dark"><main style="max-width:560px;margin:0 auto;padding:48px 20px">
<div class="karte"><h2 class="mono" style="font-size:12px;color:var(--ink-3)">FEHLER %(k)d</h2>
<p style="font-size:15px;color:var(--ink);margin:10px 0 0">%(t)s</p>
<p style="margin:18px 0 0"><a class="knopf" href="/">Zur Uebersicht</a></p>
</div></main></body></html>""" % {"k": kode, "t": e(text), "tokens": TOKENS,
                                  "stil": STIL, "name": e(TITEL)}).encode("utf-8")
        self.roh(kode, koerper, "text/html; charset=utf-8")


def main():
    # --version bleibt ohne Nebenwirkung: der Aufruf kommt aus Skripten (§24a).
    if "--version" in sys.argv:
        print(VERSION)
        return
    if not EINLASS:
        sys.stderr.write(
            "FEHLER: PROLO_EINLASS ist nicht gesetzt.\n\n"
            "Ohne diesen Wert kann das Werkzeug nicht unterscheiden, ob eine\n"
            "Anfrage vom Zugang dieses Servers kommt oder von einem anderen\n"
            "Container im selben Netz. Es startet darum nicht.\n\n"
            "Gerade hier wiegt das schwer: diese Seite zeigt, wo die Luecken\n"
            "sind. Das ist fuer den Betreiber eine Hilfe und fuer jeden\n"
            "anderen eine Einkaufsliste.\n\n"
            "So geht es weiter:\n"
            "  1. sudo prolo geheimnisse --verteilen\n"
            "  2. sudo prolo start admin\n\n"
            "Der Wert ist ein Geheimnis wie ein Passwort: nicht in Git und\n"
            "nicht in einen Chat (CLAUDE.md §21, §22).\n")
        sys.exit(2)
    # KEIN signal.signal(SIGPIPE, SIG_DFL) hier (N-82). Das gehoert in ein
    # Kommandozeilenwerkzeug, dessen Ausgabe in "head" laeuft - in einem
    # Dienst beendet es den GANZEN Prozess, sobald ein einziger Browser die
    # Verbindung schliesst, bevor die Antwort geschrieben ist. Gemessen:
    # eine abgebrochene Verbindung, und der Dienst war weg (Rueckgabe -13).
    # Python ignoriert SIGPIPE von sich aus; der Schreibfehler kommt dann
    # als BrokenPipeError in genau dem einen Faden an und wird in _lauf
    # still verworfen.
    datenbank_anlegen()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write("Prolo Admin %s laeuft auf Port %d. Daten: %s. "
                     "Docker-Vermittler: %s\n" % (VERSION, PORT, DATEN, DOCKER_API))
    srv.serve_forever()


if __name__ == "__main__":
    main()
