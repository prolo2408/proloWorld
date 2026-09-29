#!/usr/bin/env bash
# werkzeuge/zugriff-pruefen.sh
#
# Sagt "prolo abweisungen" die Wahrheit - und sagt es nichts, was es nicht
# sagen darf? (N-80)
#
# Das Zweite ist der wichtigere Teil. In den Pfaden des Zugriffsprotokolls
# stehen die Zugangslinks von www (/z/<Marke>, 192 Bit). Ein Werkzeug, das
# Protokollzeilen auf den Schirm schreibt, schreibt sie mit - und der
# Betreiber kopiert die Ausgabe in den naechsten Chat (§22). Darum steht
# hier eine Zeile, die genau das misst.
#
# Gebaut wird ein Protokoll mit VON HAND gezaehlten Zahlen in einem
# Wegwerfordner; der Pruefling liest es dort und nie im Arbeitsstand.
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
FEHLER=0

# Ein ganzer kleiner Stack im Wegwerfordner: zugriff.py leitet seinen Ort
# aus der eigenen Lage ab, also liegt es hier und liest hier.
mkdir -p "$T/werkzeuge" "$T/traefik/log" "$T/traefik/dynamic"
cp "$HIER/zugriff.py" "$T/werkzeuge/zugriff.py"
cp "$HIER/../traefik/dynamic/sicherheit.yml" "$T/traefik/dynamic/"

# Einstieg fuer die Mutationsprobe (N-34, N-60): sie aendert die KOPIE.
if [ -n "${PROLO_MUTATION:-}" ]; then
  python3 "$PROLO_MUTATION" "$T/werkzeuge" || {
    echo "FEHLER Mutation liess sich nicht einbauen" >&2; exit 3; }
fi

pruefe() {  # $1 Text  $2 erwartet  $3 ist
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' \
       "$1" "$2" "$3"; FEHLER=1; fi
}

# --- Das Protokoll, von Hand gezaehlt ----------------------------------
#
#   n8n.prolo.me    10 Zeilen, davon 3x 429 aus 2 Quellen, 1x 503
#   wiki.prolo.me    4 Zeilen, nichts abgewiesen
#   www.prolo.me     2 Zeilen, davon 1x 429 auf /z/<64 Zeichen Marke>
#   auth.prolo.me    1 Zeile,  429 auf einen Pfad mit 40 Zeichen Merkmal
#                    AUSSERHALB von /z/ - dort greift nur die Laengenregel
#
# Die Marke ist GEHEIM64ZEICHEN..., damit man im Text danach suchen kann.
MARKE="Qx7$(printf 'K%.0s' {1..61})"
python3 - "$T/traefik/log/zugriff.log" "$MARKE" <<'PY'
import json, sys
raus, marke = [], sys.argv[2]
def z(host, code, pfad, client):
    raus.append(dict(RequestHost=host, DownstreamStatus=code,
                     RequestPath=pfad, ClientHost=client,
                     StartUTC="2026-09-29T10:%02d:00Z" % (len(raus) % 60)))
for i in range(6): z("n8n.prolo.me", 200, "/assets/index-9f3a2b%d.js" % i, "1.2.3.4")
z("n8n.prolo.me", 429, "/assets/chunk-aa11.js", "1.2.3.4")
z("n8n.prolo.me", 429, "/assets/chunk-bb22.js", "1.2.3.4")
z("n8n.prolo.me", 429, "/rest/settings",        "5.6.7.8")
z("n8n.prolo.me", 503, "/rest/settings",        "1.2.3.4")
for i in range(4): z("wiki.prolo.me", 200, "/seite/start", "1.2.3.4")
z("www.prolo.me", 200, "/", "9.9.9.9")
z("www.prolo.me", 429, "/z/" + marke, "9.9.9.9")
z("auth.prolo.me", 429, "/api/v3/flows/executor/" + "S9t" + "W" * 37, "9.9.9.9")
open(sys.argv[1], "w").write("\n".join(json.dumps(x) for x in raus) + "\n")
PY

AUS="$(python3 "$T/werkzeuge/zugriff.py" 2>&1)"
RC=$?

# --- 1. Die Marke darf nirgends stehen (§22) ---------------------------
pruefe "die Marke aus dem Zugangslink steht NICHT in der Ausgabe" \
       "0" "$(printf '%s' "$AUS" | grep -c "${MARKE:0:20}")"
pruefe "stattdessen steht dort der Platzhalter" \
       "1" "$(printf '%s' "$AUS" | grep -c '/z/<Marke>')"
# Zwei Regeln schuetzen hier, und jede muss FUER SICH durchfallen koennen:
# die eine kennt /z/ und /s/, die andere kuerzt alles Lange. Ohne diesen
# zweiten Fall deckt die erste die zweite zu und eine Mutation entwischt.
pruefe "auch ein langes Merkmal ausserhalb von /z/ wird gekuerzt" \
       "0" "$(printf '%s' "$AUS" | grep -c 'WWWWWWWWWW')"
pruefe "und zwar sichtbar gekuerzt, nicht weggelassen" \
       "1" "$(printf '%s' "$AUS" | grep -c 'S9tW…')"

# --- 2. Die Zahlen stimmen (von Hand gezaehlt) -------------------------
zeile() { printf '%s' "$AUS" | grep -E "^  $1 +[0-9]" | tr -s ' '; }
pruefe "n8n: 10 Anfragen, 3 abgewiesen, 1 Fehler, 2 Quellen" \
       "n8n.prolo.me 10 3 1 2" "$(zeile n8n.prolo.me | sed 's/^ //')"
pruefe "wiki: 4 Anfragen, nichts abgewiesen" \
       "wiki.prolo.me 4 0 0 0" "$(zeile wiki.prolo.me | sed 's/^ //')"
pruefe "www: 2 Anfragen, 1 abgewiesen" \
       "www.prolo.me 2 1 0 1" "$(zeile www.prolo.me | sed 's/^ //')"

# --- 3. Gleichartige Dateien werden zusammengezogen --------------------
# Zwei verschiedene abgewiesene .js-Dateien, eine Zeile mit "2 x".
pruefe "die beiden abgewiesenen Teile stehen als eine Zeile" \
       "1" "$(printf '%s' "$AUS" | grep -cE '/assets/\*\.js +2 x')"

# --- 4. Ursache und Wirkung stehen verbunden da (§7, N-69) -------------
pruefe "der Satz je Name nennt das WEIL (3 betroffene Namen)" \
       "3" "$(printf '%s' "$AUS" | grep -c 'abgewiesen, WEIL')"
pruefe "die Erklaerung kommt genau EINMAL, nicht je Name" \
       "1" "$(printf '%s' "$AUS" | grep -c '429 setzt Traefik SELBST')"

# --- 5. Die Meldung nennt Datei UND Befehl (§7, N-67) ------------------
pruefe "sie nennt die Datei, in der die Werte stehen" \
       "1" "$(printf '%s' "$AUS" | grep -c 'traefik/dynamic/sicherheit.yml')"
pruefe "sie nennt die eingestellten Werte" \
       "1" "$(printf '%s' "$AUS" | grep -cE 'average 50 .* burst 700 .* 200')"
pruefe "sie nennt den Befehl und dass er wiederholbar ist" \
       "1" "$(printf '%s' "$AUS" | grep -c 'prolo start traefik')"

# --- 6. Gedrehte Dateien werden mitgelesen -----------------------------
gzip -c "$T/traefik/log/zugriff.log" > "$T/traefik/log/zugriff.log.1.gz"
AUS2="$(python3 "$T/werkzeuge/zugriff.py" 2>&1)"
pruefe "die gedrehte Datei zaehlt mit (doppelte Zahlen)" \
       "n8n.prolo.me 20 6 2 2" \
       "$(printf '%s' "$AUS2" | grep -E '^  n8n.prolo.me +[0-9]' | tr -s ' ' | sed 's/^ //')"
rm -f "$T/traefik/log/zugriff.log.1.gz"

# --- 7. Der saubere Fall sagt auch etwas -------------------------------
python3 - "$T/traefik/log/zugriff.log" <<'PY'
import json, sys
open(sys.argv[1], "w").write("\n".join(json.dumps(dict(
    RequestHost="wiki.prolo.me", DownstreamStatus=200, RequestPath="/",
    ClientHost="1.2.3.4", StartUTC="2026-09-29T10:00:00Z")) for _ in range(5)) + "\n")
PY
AUS3="$(python3 "$T/werkzeuge/zugriff.py" 2>&1)"
pruefe "ohne Abweisungen sagt es, was das bedeutet" \
       "1" "$(printf '%s' "$AUS3" | grep -c 'liegt es nicht an der Bremse')"
pruefe "und behauptet dann keine Ursache" \
       "0" "$(printf '%s' "$AUS3" | grep -c 'abgewiesen, WEIL')"

# --- 8. Fehlt das Protokoll, nennt es den Weg (N-67) -------------------
rm -f "$T/traefik/log/"*
AUS4="$(python3 "$T/werkzeuge/zugriff.py" 2>&1)"; RC4=$?
pruefe "ohne Protokoll ein Fehlschlag, kein stilles Nichts" "1" "$RC4"
pruefe "und der Befehl, der es einschaltet" \
       "1" "$(printf '%s' "$AUS4" | grep -c 'prolo start traefik')"

echo ""
if [ "$FEHLER" = 0 ]; then echo "Alles gruen."; else echo "Es gibt Beanstandungen."; fi
exit "$FEHLER"
