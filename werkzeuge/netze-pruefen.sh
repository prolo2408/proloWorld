#!/usr/bin/env bash
# werkzeuge/netze-pruefen.sh
#
# Steht die Netztrennung noch? (N-45)
#
# Der Anlass: Wiki, Bordbuch, n8n und Authentik hingen im selben Docker-Netz
# "proxy". In einem Docker-Netz erreicht jeder Container jeden anderen direkt
# - ohne Traefik, ohne Anmeldung. Damit war der Weg von n8n zum Wiki offen:
# n8n fuehrt angeklickte Ablaeufe mit einem HTTP-Baustein aus und hat
# Webhook-Pfade ohne Anmeldung. Kein Exploit noetig.
#
# Jetzt haengt jedes Werkzeug in seinem eigenen Netz und nur Traefik in
# allen. Das ist eine Eigenschaft, die man beim Lesen einer einzelnen Datei
# NICHT sieht - sie entsteht erst aus allen zusammen. Darum dieses Skript.
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

python3 - "$STACK" <<'PY'
import os, re, sys
stack = sys.argv[1]
fehler = 0

def sag(ok, text, zusatz=""):
    global fehler
    print(("ok     " if ok else "FEHLER ") + text + (("  -> " + zusatz) if zusatz and not ok else ""))
    if not ok:
        fehler += 1

def ohne_kommentare(s):
    return "\n".join(z for z in s.split("\n") if not z.lstrip().startswith("#"))

def compose(name):
    p = os.path.join(stack, name, "docker-compose.yml")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return ohne_kommentare(f.read())

def dienste(s):
    """{Dienstname: (Netze, Netz-Label)} aus einer compose-Datei."""
    aus = {}
    for m in re.finditer(r"^(  [a-z0-9-]+):\s*$", s, re.M):
        name = m.group(1).strip()
        rest = s[m.end():]
        ende = re.search(r"^  \S", rest, re.M)
        block = rest[:ende.start()] if ende else rest
        n = re.search(r"^    networks:\n((?:      - .*\n)+)", block, re.M)
        aus[name] = (re.findall(r"- (\S+)", n.group(1)) if n else [],
                     re.findall(r"traefik\.docker\.network=(\S+?)\"", block))
    return aus

# Welche Ordner sind Werkzeuge? Alles mit docker-compose.yml ausser den
# dreien, die zur Grundausstattung gehoeren.
GRUND = {"traefik", "authentik", "socket-proxy"}
alle = sorted(o for o in os.listdir(stack)
              if os.path.exists(os.path.join(stack, o, "docker-compose.yml")))
werkzeuge = [o for o in alle if o not in GRUND]
sag(len(werkzeuge) >= 2, "es gibt Werkzeuge zu pruefen (%d)" % len(werkzeuge),
    "ohne sie prueft dieses Skript nichts")

tf = compose("traefik") or ""
tf_netze = set(dienste(tf).get("traefik", ([], []))[0])

# --- 1. Kein Werkzeug haengt noch im gemeinsamen Netz -------------------
# Gesucht wird die NETZREFERENZ, nicht das Wort: der Dienst socket-proxy
# heisst so und haengt in keinem Netz "proxy". Ein Pruefer, der eine
# Zeichenfolge sucht, meldet hier einen Fehler, den es nicht gibt (N-36).
NETZ_PROXY = (r"^      - proxy\s*$",          # im networks: eines Dienstes
              r"^  proxy:\s*$",               # im Block ganz unten
              r"traefik\.docker\.network=proxy")
for o in alle:
    s = compose(o) or ""
    treffer = [m for muster in NETZ_PROXY
               for m in re.findall(muster, s, re.M)]
    sag(not treffer, "%s: haengt nicht mehr im gemeinsamen Netz" % o,
        "solange irgendwer in proxy haengt, ist die Trennung keine")

# --- 2. Jedes Werkzeug hat GENAU ein Netz mit Traefik -------------------
eigen = {}
for o in alle:
    s = compose(o)
    if s is None:
        continue
    for dienst, (netze, label) in dienste(s).items():
        oeffentlich = [n for n in netze if n in tf_netze and n != "socket"]
        if not label and not oeffentlich:
            continue          # Datenbank, Worker: hat nichts mit Traefik zu tun
        if o == "traefik":
            continue
        sag(len(oeffentlich) == 1,
            "%s/%s: genau ein Netz mit Traefik (%s)" % (o, dienst, oeffentlich),
            "zwei gemeinsame Netze heben die Trennung wieder auf")
        sag(bool(label), "%s/%s: nennt sein Netz im Label" % (o, dienst),
            "ohne das Label sucht Traefik sich eines aus - seit N-45 gibt "
            "es keine Vorgabe mehr, auf die es zurueckfallen koennte")
        if label and oeffentlich:
            sag(label[0] == oeffentlich[0],
                "%s/%s: Label und Netz stimmen ueberein" % (o, dienst),
                "Label %s, Netz %s" % (label[0], oeffentlich[0]))
        for n in oeffentlich:
            eigen.setdefault(n, []).append(o)

# --- 3. Kein Netz wird von zwei Werkzeugen geteilt ----------------------
for netz, wer in sorted(eigen.items()):
    sag(len(set(wer)) == 1, "%s gehoert genau einem Werkzeug (%s)"
        % (netz, ", ".join(sorted(set(wer)))),
        "zwei Werkzeuge in einem Netz erreichen einander wieder direkt")

# --- 4. Traefik haengt in JEDEM davon -----------------------------------
for netz in sorted(eigen):
    sag(netz in tf_netze, "Traefik haengt in %s" % netz,
        "sonst ist das Werkzeug von aussen gar nicht erreichbar")

# --- 5. Keine Vorgabe mehr im Docker-Anbieter ---------------------------
with open(os.path.join(stack, "traefik", "traefik.yml"), encoding="utf-8") as f:
    statisch = ohne_kommentare(f.read())
sag("network: proxy" not in statisch,
    "traefik.yml: keine Netz-Vorgabe auf proxy mehr",
    "eine Vorgabe auf ein Netz, das es nicht gibt, ist schlimmer als keine")

# --- 6. Die Vorlage fuer neue Werkzeuge macht es richtig ----------------
with open(os.path.join(stack, "werkzeuge", "prolo"), encoding="utf-8") as f:
    prolo = f.read()
sag("- netz-$NAME" in prolo and "traefik.docker.network=netz-$NAME" in prolo,
    "prolo legt neue Werkzeuge mit eigenem Netz an",
    "sonst faellt das naechste Werkzeug hinter die Trennung zurueck")

print("")
print("Alles gruen." if not fehler else "%d Fehler." % fehler)
sys.exit(1 if fehler else 0)
PY
