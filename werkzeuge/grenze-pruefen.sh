#!/usr/bin/env bash
# werkzeuge/grenze-pruefen.sh
#
# Steht der Eingang noch? (N-44 Vertrauensgrenze, N-46 Ratenbremse)
#
# Der Anlass, gemessen: eine Anfrage mit "X-Authentik-Groups: wiki-admin"
# bekam vom Wiki 200 und die Verwaltungsdaten, dieselbe ohne Gruppe 403. Die
# Rechtepruefung war also richtig - das Vertrauen in die Kopfzeile nicht. Von
# aussen ist das kein Weg, weil Traefik die Kopfzeilen am Eingang loescht;
# aus dem Docker-Netz heraus schon, denn dort erreicht jeder Container Port
# 8080 eines anderen direkt.
#
# Die Korrektur besteht aus Teilen an fuenf Stellen. Faellt EINE davon weg,
# ist das Loch wieder da - und zwar lautlos, weil alles weiter funktioniert.
# Genau das prueft dieses Skript.
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

python3 - "$STACK" <<'PY'
import ast, os, re, sys
stack = sys.argv[1]
fehler = 0

def sag(ok, text, zusatz=""):
    global fehler
    print(("ok     " if ok else "FEHLER ") + text + (("  -> " + zusatz) if zusatz and not ok else ""))
    if not ok:
        fehler += 1

def freie_pfade(code):
    """Die Freiliste eines Werkzeugs als Pfade, egal wie sie geschrieben ist.

    Das Wiki zerlegt Pfade in Teile (["api", "version"]), das Bordbuch
    vergleicht ganze Pfade ("/api/version"). Beides ist in seinem Werkzeug
    richtig - ein Pruefer, der nur eine Form kennt, meldet darum einen
    Fehler, den es nicht gibt. Genau das ist hier passiert.
    """
    m = re.search(r"EINLASS_FREI = (\(.*?\))\n", code, re.S)
    if not m:
        return set()
    try:
        werte = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return set()
    aus = set()
    for w in werte:
        aus.add(w if isinstance(w, str) else "/" + "/".join(w))
    return aus


def lies(*teile):
    p = os.path.join(stack, *teile)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()

# --- 1. Die Kette am Eingang -------------------------------------------
statisch = lies("traefik", "traefik.yml") or ""
m = re.search(r"^      middlewares:\n((?:\s*#.*\n|\s*- .*\n)+)", statisch, re.M)
kette = re.findall(r"^\s*- (\S+)", m.group(1), re.M) if m else []
sag("vertrauensgrenze@file" in kette,
    "traefik.yml: vertrauensgrenze haengt am Eingang",
    "ohne sie reicht JEDER Router durch, was der Client schickt")
sag("einlass@file" in kette,
    "traefik.yml: einlass haengt am Eingang",
    "ohne sie bekommt kein Werkzeug die Marke und alles antwortet 401")
if "vertrauensgrenze@file" in kette and "einlass@file" in kette:
    sag(kette.index("vertrauensgrenze@file") < kette.index("einlass@file"),
        "traefik.yml: erst loeschen, dann setzen",
        "andersherum loescht die Grenze die eigene Marke wieder")

# --- 1b. Die Ratenbremse (N-46) -----------------------------------------
sag("ratenbremse@file" in kette, "traefik.yml: die Ratenbremse haengt am Eingang",
    "ohne sie kann eine einzelne Quelle in Schleife anklopfen")
sag("gleichzeitig@file" in kette,
    "traefik.yml: die Grenze fuer gleichzeitige Anfragen haengt am Eingang")
if "ratenbremse@file" in kette and "vertrauensgrenze@file" in kette:
    sag(kette.index("ratenbremse@file") < kette.index("vertrauensgrenze@file"),
        "traefik.yml: erst bremsen, dann alles andere",
        "wer zu schnell klopft, soll gar nicht erst bis zur Anmeldung kommen")
sicher_roh = lies("traefik", "dynamic", "sicherheit.yml") or ""
werte = dict(re.findall(r"^\s*(average|burst|amount):\s*(\d+)\s*$",
                        sicher_roh, re.M))
# Von Hand gerechnet: ein Seitenaufruf des Wikis sind etwa 15 Anfragen mit
# Schriften und Schnittstelle. Unter 20 je Sekunde wuerde die Bremse einen
# Menschen treffen - gemessen wurden bei 24/s null Abweisungen.
sag(int(werte.get("average", 0)) >= 20,
    "die Bremse trifft keinen Menschen (average=%s)" % werte.get("average"),
    "ein Seitenaufruf sind rund 15 Anfragen")
sag(0 < int(werte.get("average", 0)) <= 200,
    "die Bremse bremst ueberhaupt (average=%s)" % werte.get("average"),
    "ein zu hoher Wert ist dasselbe wie keine Bremse")
sag(int(werte.get("amount", 0)) > 0,
    "gleichzeitige Anfragen sind begrenzt (amount=%s)" % werte.get("amount"))

# --- 2. Jede Kopfzeile, die Authentik setzen darf, wird vorher geleert ---
auth = lies("traefik", "dynamic", "authentik.yml") or ""
gesetzt = [h.strip().lower() for h in
           re.findall(r"^\s*- (X-[Aa]uthentik-\S+)\s*$", auth, re.M)]
sicher = lies("traefik", "dynamic", "sicherheit.yml") or ""
block = re.search(r"    vertrauensgrenze:\n(.*?)(?=\n    \S|\ntls:)", sicher, re.S)
geleert = ([h.strip().lower() for h in
            re.findall(r'^\s*(X-\S+):\s*""\s*$', block.group(1), re.M)]
           if block else [])
sag(bool(gesetzt), "authentik.yml nennt Kopfzeilen (%d)" % len(gesetzt),
    "ohne sie prueft dieser Abgleich nichts")
fehlt = [h for h in gesetzt if h not in geleert]
sag(not fehlt,
    "sicherheit.yml leert alle %d Kopfzeilen aus authentik.yml" % len(gesetzt),
    "nicht geleert: " + ", ".join(fehlt))
sag("x-prolo-einlass" in geleert,
    "sicherheit.yml leert auch X-Prolo-Einlass",
    "sonst bestimmt der Client die Marke, falls einlass.yml einmal fehlt")

# --- 3. Das Geheimnis liegt richtig ------------------------------------
sag(lies("traefik", "dynamic", "einlass.yml.beispiel") is not None,
    "einlass.yml.beispiel liegt im Repository")
ign = lies(".gitignore") or ""
sag("traefik/dynamic/einlass.yml" in ign,
    ".gitignore haelt einlass.yml heraus",
    "das ist ein Geheimnis wie eine .env (CLAUDE.md §21)")

# Der Platzhalter darf in keiner versionierten Datei als echter Wert stehen.
# Zusammengesetzt, nicht ausgeschrieben: ein Pruefer, der den gesuchten
# Text im Klartext enthaelt, findet sich selbst (wie in N-36 und N-39).
platzhalter = "HIER-EINEN-" + "GEWUERFELTEN-WERT-" + "EINTRAGEN"
treffer = []
for wurzel, ordner, dateien in os.walk(stack):
    ordner[:] = [o for o in ordner if o not in (".git", "__pycache__", "node_modules")]
    for d in dateien:
        p = os.path.join(wurzel, d)
        if p.endswith(".beispiel"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                if platzhalter in f.read():
                    treffer.append(os.path.relpath(p, stack))
        except (UnicodeDecodeError, OSError):
            pass
sag(not treffer, "der Platzhalter steht nur in der Beispieldatei",
    ", ".join(treffer))

# --- 4. Jedes Werkzeug, das die Marke prueft, bekommt sie auch ----------
for werkzeug in ("wiki", "bordbuch"):
    code = lies(werkzeug, "server.py") or ""
    if "PROLO_EINLASS" not in code:
        continue
    compose = lies(werkzeug, "docker-compose.yml") or ""
    sag("PROLO_EINLASS" in compose,
        "%s/docker-compose.yml reicht PROLO_EINLASS durch" % werkzeug)
    sag("${PROLO_EINLASS:?" in compose,
        "%s: fehlender Wert bricht schon beim Hochfahren ab" % werkzeug,
        'ohne ":?" startet der Container und weist dann jede Anfrage ab')
    sag("PROLO_EINLASS" in (lies(werkzeug, ".env.beispiel") or ""),
        "%s/.env.beispiel nennt PROLO_EINLASS" % werkzeug)
    # Die Wirkung, nicht die Zeichenfolge (N-36): der Aufruf muss in BEIDEN
    # Einstiegen stehen. Nur in do_GET waere jede Schreibaktion offen.
    n = len(re.findall(r"self\.einlass_pruefen\(", code))
    sag(n >= 2, "%s: die Grenze steht in do_GET UND do_POST (%d Aufrufe)"
        % (werkzeug, n), "eine Haelfte offen ist nicht halb sicher")
    # Der freie Pfad darf nicht die Wurzel sein.
    frei = re.search(r"EINLASS_FREI = \((.*?)\)", code, re.S)
    sag(frei is not None and '"/"' not in frei.group(1)
        and "[]" not in frei.group(1),
        "%s: die Wurzel steht nicht auf der Freiliste" % werkzeug)

# --- 5. Die Pruefadresse liegt auf einem freien Pfad --------------------
for werkzeug in ("wiki", "bordbuch"):
    conf = lies(werkzeug, "aktualisierung.conf") or ""
    url = re.search(r'PRUEF_URL="([^"]*)"', conf)
    if not url or not url.group(1):
        continue
    pfad = re.sub(r"^https?://[^/]+", "", url.group(1)) or "/"
    code = lies(werkzeug, "server.py") or ""
    sag(pfad in freie_pfade(code),
        "%s: PRUEF_URL zeigt auf einen freien Pfad (%s)" % (werkzeug, pfad),
        "aktualisieren.sh ruft intern auf und hat die Marke nicht - "
        "die Pruefung wuerde immer fehlschlagen und jeden Lauf zurueckrollen")

print("")
print("Alles gruen." if not fehler else "%d Fehler." % fehler)
sys.exit(1 if fehler else 0)
PY
