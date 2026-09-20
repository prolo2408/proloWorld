#!/usr/bin/env python3
"""Prolo Admin - die Lage des Stacks auf einer Seite.

Was dieses Werkzeug ist: eine LESENDE Uebersicht. Welche Werkzeuge gibt es,
laufen sie, in welchem Netz haengen sie, unter welchem Namen sind sie
erreichbar - und vor allem: was davon ist NICHT geschuetzt.

Was es bewusst NICHT ist: eine Fernbedienung. Es startet nichts, haelt
nichts an, legt nichts an. Der Grund steht in docker-compose.yml: dafuer
muesste der Vermittler vor dem Docker-Socket schreibende Aufrufe
durchlassen, und damit waere aus einer Uebersichtsseite der kuerzeste Weg
zur Serveruebernahme geworden. Wer etwas aendern will, nimmt "prolo" auf
dem Server. Kommt das spaeter hierher, dann mit einem eigenen Vermittler
und einer eigenen Entscheidung, nicht nebenbei.

Woher die Daten kommen: ausschliesslich aus zwei lesenden Aufrufen an den
Vermittler (socket-proxy), /containers/json und /networks. Dieses Werkzeug
hat KEINEN Zugriff auf /opt/stack - keine Compose-Datei, keine .env, kein
Zertifikat. Es kann also auch nichts davon preisgeben.

Kein Fremdpaket: Standardbibliothek und SQLite (CLAUDE.md).
"""
import hashlib
import hmac
import html
import json
import os
import re
import signal
import sqlite3
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

VERSION = "0.1.0"

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

MARKE = "A"
NAME = "Prolo Admin"
UNTERZEILE = "STACK-UEBERSICHT"


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
def docker_lesen(pfad):
    """Ein lesender Aufruf an den Vermittler. Nur Pfade aus DOCKER_PFADE."""
    if pfad not in DOCKER_PFADE:
        raise Antwort(500, "Unerlaubter Pfad zum Docker-Vermittler.")
    url = DOCKER_API.rstrip("/") + pfad
    try:
        with urllib.request.urlopen(url, timeout=DOCKER_ZEIT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise Antwort(503,
                      "Der Docker-Vermittler antwortet nicht (%s). Die "
                      "Uebersicht kann nichts anzeigen, solange er still "
                      "ist. Auf dem Server nachsehen: "
                      "sudo prolo protokoll socket-proxy" % e.reason)
    except (ValueError, OSError) as e:
        raise Antwort(503, "Der Docker-Vermittler hat geantwortet, aber nicht "
                           "verstaendlich (%s)." % e)


ROUTER_REGEL = re.compile(r"^traefik\.http\.routers\.([^.]+)\.rule$")
ROUTER_MW = re.compile(r"^traefik\.http\.routers\.([^.]+)\.middlewares$")
HOST_REGEL = re.compile(r"Host\(`([^`]+)`\)")


def schutz_lesen(labels):
    """Womit ist dieser Dienst geschuetzt? Gelesen, nicht geraten.

    Die Middleware-Kette steht in den Labels. Kein authentik@file und keine
    Erklaerung heisst OFFEN - und genau das soll man sehen. Ein fehlendes
    middlewares= sieht sonst aus wie ein vergessenes (N-59).
    """
    if labels.get("traefik.enable") != "true":
        return ("", "")
    ketten = " ".join(w for k, w in labels.items() if ROUTER_MW.match(k))
    if "authentik@file" in ketten:
        return ("authentik", "")
    if labels.get("prolo.anmeldung"):
        return (labels["prolo.anmeldung"], labels.get("prolo.anmeldung.grund", ""))
    if labels.get("prolo.oeffentlich"):
        return ("oeffentlich", labels["prolo.oeffentlich"])
    return ("OFFEN", "")


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
                    "Ein Router ohne Anmeldung und ohne Erklaerung. Entweder "
                    "middlewares=authentik@file ergaenzen oder - wenn das "
                    "Werkzeug eine eigene Anmeldung mitbringt - mit "
                    "prolo.anmeldung=eigene erklaeren (CLAUDE.md §17a)."))
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
table.werkzeuge td{overflow-wrap:anywhere}
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

.tabbar{display:none}
@media (max-width:900px){
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
       ("/einstellungen", "Einstellungen"))


def seite(titel, ktx, inhalt, pfad, ich, thema):
    tabs = "".join(
        '<a href="%s"%s>%s</a>' % (p, ' aria-current="page"' if p == pfad else "", e(t))
        for p, t in NAV)
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
})();
</script>
</body></html>""" % {
        "titel": e(titel), "ktx": e(ktx), "inhalt": inhalt, "nav": nav, "tabs": tabs,
        "tokens": TOKENS, "stil": STIL, "marke": MARKE, "name": e(NAME),
        "unter": e(UNTERZEILE), "ich": e(ich), "thema": json.dumps(thema),
    }


def marker_schutz(s, grund):
    if s == "authentik":
        return '<span class="marker m-gut">Authentik</span>'
    if s == "OFFEN":
        return '<span class="marker m-rot">OFFEN - ohne Anmeldung</span>'
    if s == "oeffentlich":
        return '<span class="marker m-warm">oeffentlich: %s</span>' % e(grund)
    if s:
        return ('<span class="marker m-warm">eigene Anmeldung</span>'
                + (' <span class="ktx">%s</span>' % e(grund) if grund else ""))
    return '<span class="ktx">kein Router</span>'


def kpi(lbl, wert, sub):
    return ('<div class="karte kpi"><div class="lbl">%s</div>'
            '<div class="wert">%s</div><div class="sub">%s</div></div>'
            % (e(lbl), e(wert), e(sub)))


def ansicht_uebersicht(l):
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

    # Die Hero-Kennzahl steht ZUERST - am Handy ist sie sonst die vierte
    # Karte, und §6 verlangt sie oben. Was der Betreiber als erstes sehen
    # soll, ist nicht "9 Werkzeuge", sondern "3 Punkte zu klaeren".
    return ('<div class="reihe kpi3">%s</div>'
            '<div class="reihe kpi3">%s%s%s</div>'
            '<div class="reihe" style="grid-template-columns:1fr">'
            '<div class="karte"><h2>Zu klaeren</h2>'
            '<div class="ktx">Aus den Labels der laufenden Container gelesen, '
            'nicht geraten.</div><div style="margin-top:10px">%s</div></div></div>'
            % (hero + kpi("Routen", len(routen), "Hostnamen mit Zertifikat")
               + kpi("Container", "%d / %d" % (laeuft, len(dienste)), "laufen / gesamt"),
               kpi("Werkzeuge", len(l["werkzeuge"]), "Compose-Projekte"),
               kpi("Netze", len(l["netze"]), "im Docker"),
               kpi("Fassung", VERSION, "Prolo Admin"),
               liste))


def ansicht_werkzeuge(l):
    zeilen = []
    for w in l["werkzeuge"]:
        for d in w["dienste"]:
            zustand = ('<span class="marker m-gut">laeuft</span>'
                       if d["zustand"] == "running"
                       else '<span class="marker m-rot">%s</span>' % e(d["zustand"]))
            ports = ('<span class="marker m-rot">%s</span>' % e(", ".join(d["ports"]))
                     if d["ports"] and not d["ports_grund"]
                     else ('<span class="mono">%s</span> <span class="ktx">%s</span>'
                           % (e(", ".join(d["ports"])), e(d["ports_grund"]))
                           if d["ports"] else '<span class="ktx">-</span>'))
            zeilen.append(
                "<tr><td><b>%s</b><div class=\"ktx mono\">%s</div></td>"
                "<td class=\"mono\">%s</td><td>%s<div class=\"ktx\">%s</div></td>"
                "<td class=\"mono\">%s</td><td>%s</td><td>%s</td></tr>"
                % (e(w["name"]), e(d["dienst"]), e(d["abbild"]), zustand, e(d["lage"]),
                   e(", ".join(d["netze"])) or "-",
                   "<br>".join('<span class="mono">%s</span>' % e(h)
                               for h in d["hosts"]) or '<span class="ktx">-</span>',
                   marker_schutz(d["schutz"], d["schutz_grund"]) + "<br>" + ports))
    if not zeilen:
        return ('<div class="karte"><h2>Werkzeuge</h2>'
                '<div class="leer">Es laeuft noch nichts. Ein neues Werkzeug '
                'legt man auf dem Server an:<br>'
                '<span class="mono">sudo prolo neu &lt;name&gt;</span><br>'
                'Danach steht es hier, sobald es gestartet ist.</div></div>')
    return ('<div class="karte"><h2>Werkzeuge</h2>'
            '<div class="ktx">Ein Werkzeug ist ein Compose-Projekt. Die Angaben '
            'kommen aus den Labels der Container.</div>'
            '<div class="scroll" style="margin-top:12px"><table class="werkzeuge">'
            '<thead><tr><th>Werkzeug / Dienst</th><th>Abbild</th><th>Zustand</th>'
            '<th>Netz</th><th>Erreichbar unter</th><th>Schutz / offene Ports</th>'
            '</tr></thead><tbody>%s</tbody></table></div></div>' % "".join(zeilen))


def ansicht_netze(l):
    zeilen = "".join(
        '<tr><td class="mono"><b>%s</b></td><td class="mono">%s</td><td>%s</td>'
        '<td class="z">%d</td><td class="mono">%s</td></tr>'
        % (e(n["name"]), e(n["treiber"]),
           '<span class="marker m-gut">intern</span>' if n["intern"]
           else '<span class="ktx">nach aussen</span>',
           len(n["container"]), e(", ".join(n["container"])) or "-")
        for n in l["netze"])
    if not zeilen:
        # Ein leerer Zustand erklaert den naechsten Schritt (§14a.4) -
        # "keine Netze" allein ist eine Feststellung, kein Hinweis.
        return ('<div class="karte"><h2>Netze</h2>'
                '<div class="leer">Docker meldet keine Netze. Entweder laeuft '
                'noch nichts, oder der Vermittler vor dem Docker-Socket '
                'antwortet nicht. Auf dem Server nachsehen:<br>'
                '<span class="mono">prolo netze</span> &ndash; zeigt dasselbe '
                'aus den Dateien.<br><span class="mono">sudo prolo protokoll '
                'socket-proxy</span> &ndash; sagt, ob der Vermittler laeuft.'
                '</div></div>')
    return ('<div class="karte"><h2>Netze</h2>'
            '<div class="ktx">Jedes Werkzeug haengt in seinem eigenen Netz, nur '
            'Traefik in allen (N-45). Anlegen, schliessen und umziehen geht auf '
            'dem Server mit <span class="mono">prolo netze</span>.</div>'
            '<div class="scroll" style="margin-top:12px"><table>'
            '<thead><tr><th>Netz</th><th>Treiber</th><th>Art</th>'
            '<th>Container</th><th>Wer haengt drin</th></tr></thead>'
            '<tbody>%s</tbody></table></div></div>' % zeilen)


def ansicht_einstellungen(nutzer, meldung):
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
    <div class="ktx">Und was sie mit Absicht nicht tut.</div>
    <p style="font-size:13px;margin:12px 0 0">
      Sie <b>liest</b>. Zwei Aufrufe an den Vermittler vor dem Docker-Socket
      &ndash; die Liste der Container und die Liste der Netze &ndash; und sonst
      nichts. Sie hat keinen Zugriff auf <span class="mono">/opt/stack</span>,
      also auch nicht auf <span class="mono">.env</span>-Dateien oder
      Zertifikate.</p>
    <p style="font-size:13px;margin:10px 0 0">
      Sie <b>startet und haelt nichts an</b>. Dafuer muesste der Vermittler
      schreibende Aufrufe durchlassen, und damit waere aus einer
      Uebersichtsseite der kuerzeste Weg zur Serveruebernahme geworden.
      Geaendert wird auf dem Server mit <span class="mono">prolo</span>.</p>
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
             "mail": e(nutzer["email"] or "-")}


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
        return nutzer_holen(kennung,
                            (self.headers.get("X-Authentik-Name") or "").strip(),
                            (self.headers.get("X-Authentik-Email") or "").strip())

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
        except Antwort as a:
            self.fehlerseite(a.kode, a.text)
        except Exception:
            # Kein interner Pfad und kein Datenbankfehler im Klartext (§22).
            import traceback
            traceback.print_exc()
            self.fehlerseite(500, "Da ist bei uns etwas schiefgegangen. Der "
                                  "Fehler steht im Protokoll des Servers.")

    def verteilen_get(self):
        pfad = urlparse(self.path).path
        if pfad == "/gesundheit":
            return self.roh(200, b"ok", "text/plain; charset=utf-8")
        if pfad == "/api/version":
            return self.json_aus(200, {"name": "prolo-admin", "version": VERSION})
        if pfad.startswith("/schriften/"):
            return self.schrift(pfad)

        nutzer = self.angemeldet()
        if pfad == "/einstellungen":
            fr = parse_qs(urlparse(self.path).query)
            return self.html(seite(
                "Einstellungen", "Darstellung und Konto",
                ansicht_einstellungen(nutzer, (fr.get("ok") or [""])[0]),
                pfad, nutzer["anzeigename"] or nutzer["nutzer_id"], nutzer["thema"]))
        if pfad == "/api/lage":
            return self.json_aus(200, lage())

        l = lage()
        if pfad == "/":
            return self.html(seite(
                "Uebersicht", "Was laeuft, und was jemand ansehen sollte",
                ansicht_uebersicht(l), pfad,
                nutzer["anzeigename"] or nutzer["nutzer_id"], nutzer["thema"]))
        if pfad == "/werkzeuge":
            return self.html(seite(
                "Werkzeuge", "Container, Abbilder, Routen und Schutz",
                ansicht_werkzeuge(l), pfad,
                nutzer["anzeigename"] or nutzer["nutzer_id"], nutzer["thema"]))
        if pfad == "/netze":
            return self.html(seite(
                "Netze", "Wer haengt wo - und was das bedeutet",
                ansicht_netze(l), pfad,
                nutzer["anzeigename"] or nutzer["nutzer_id"], nutzer["thema"]))
        raise Antwort(404, "Diese Seite gibt es nicht. Zurueck zur Uebersicht: /")

    def verteilen_post(self):
        pfad = urlparse(self.path).path
        nutzer = self.angemeldet()
        if pfad == "/einstellungen/thema":
            self.gleicher_ursprung()
            laenge = int(self.headers.get("Content-Length") or 0)
            if laenge > 4096:
                raise Antwort(413, "Das war zu viel fuer eine Einstellung.")
            feld = parse_qs(self.rfile.read(laenge).decode("utf-8", "replace"))
            thema_setzen(nutzer["nutzer_id"], (feld.get("thema") or [""])[0])
            return self.weiter("/einstellungen?ok=Darstellung+gespeichert.")
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
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "font-src 'self'; script-src 'unsafe-inline'; "
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
                                  "stil": STIL, "name": e(NAME)}).encode("utf-8")
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
    # Ohne das bricht der Dienst mit BrokenPipeError ab, sobald ein Browser
    # eine Antwort nicht zu Ende liest.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    datenbank_anlegen()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write("Prolo Admin %s laeuft auf Port %d. Daten: %s. "
                     "Docker-Vermittler: %s\n" % (VERSION, PORT, DATEN, DOCKER_API))
    srv.serve_forever()


if __name__ == "__main__":
    main()
