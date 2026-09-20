#!/bin/bash
# admin/tests/gegenprobe.sh
#
# Die Tests muessen Zaehne haben (CLAUDE.md §13a). Handgerechnete
# Erwartungswerte sind notwendig, aber nicht genug: ein Test kann gruen
# sein, weil er nichts prueft.
#
# Darum baut dieses Skript absichtlich Fehler ein und verlangt, dass JEDER
# von einem Test gefunden wird. Gearbeitet wird auf einer KOPIE in einem
# Wegwerfordner - eine Probe, die ueber "git checkout" zurueckrollt,
# loescht eine noch nicht eingecheckte Korrektur mit weg (N-34).
set -uo pipefail
cd "$(dirname "$0")/.."
QUELLE="$(pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
GEFUNDEN=0; ENTWISCHT=0

cp -a "$QUELLE/server.py" "$QUELLE/tests" "$T/"
rm -rf "$T/tests/__pycache__"

probe() {
  local name="$1" alt="$2" neu="$3"
  cp "$QUELLE/server.py" "$T/server.py"
  # Ein alter __pycache__ laesst eine Mutationsprobe still gruen bleiben.
  rm -rf "$T/tests/__pycache__" "$T/__pycache__"
  if ! python3 - "$T/server.py" "$alt" "$neu" <<'PY'
import io, sys
p, alt, neu = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(p, encoding="utf-8").read()
if s.count(alt) != 1:
    sys.stderr.write("Muster %dx gefunden: %r\n" % (s.count(alt), alt))
    sys.exit(1)
io.open(p, "w", encoding="utf-8").write(s.replace(alt, neu))
PY
  then
    printf 'ABBRUCH   %s (Mutation liess sich nicht einbauen)\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1)); return
  fi
  if (cd "$T" && python3 -m unittest discover -s tests -t tests >"$T/lauf.txt" 2>&1); then
    printf 'ENTWISCHT %s  <-- Testluecke\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1))
  else
    printf 'gefunden  %s\n' "$name"
    grep -E '^(FAIL|ERROR):' "$T/lauf.txt" | sed 's/^/            /' | head -4
    GEFUNDEN=$((GEFUNDEN + 1))
  fi
}

probe "ein Router ohne Anmeldung gilt als geschuetzt" \
  '    return ("OFFEN", "")' \
  '    return ("authentik", "")'

probe "die Marke von Traefik wird nicht mehr geprueft (N-44)" \
  '        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")' \
  '        return
        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")'

probe "die Marke wird nur am Anfang verglichen" \
  '        if hmac.compare_digest(mit, EINLASS_B):' \
  '        if mit and EINLASS_B.startswith(mit):'

probe "jede Gruppe darf herein" \
  '        if GRUPPE_LESEN not in meine:' \
  '        if not gruppen:'

probe "eine fremde Gruppe mit aehnlichem Namen zaehlt mit" \
  '        meine = {g for g in gruppen if g.startswith(GRUPPE_PRAEFIX)}' \
  '        meine = {g.split("-")[-1] for g in gruppen}'

probe "Labels werden ungefiltert ausgegeben" \
  '    return html.escape(str(s), quote=True)' \
  '    return str(s)'

probe "ein offener Port faellt nicht auf" \
  '            if d["ports"] and not d["ports_grund"]:' \
  '            if False:'

probe "auch ein erklaerter Port wird beanstandet" \
  '            if d["ports"] and not d["ports_grund"]:' \
  '            if d["ports"]:'

probe "Label und tatsaechliches Netz werden nicht verglichen (N-58)" \
  '            if d["netz_label"] and d["netz_label"] not in d["netze"]:' \
  '            if False:'

probe "ein angehaltener Container faellt nicht auf" \
  '            if d["zustand"] not in ("running", ""):' \
  '            if False:'

probe "eine Absendung von einer fremden Seite wird angenommen" \
  '        if urlparse(quelle).netloc != ziel:' \
  '        if False:'

probe "jeder Pfad zum Docker-Vermittler ist erlaubt" \
  '    if pfad not in DOCKER_PFADE:' \
  '    if False:'

probe "ein unbekanntes Thema wird gespeichert" \
  '    if thema not in THEMEN:' \
  '    if False:'

probe "ein Dienst ohne Router gilt als offen" \
  '''    if labels.get("traefik.enable") != "true":
        return ("", "")''' \
  '''    if False:
        return ("", "")'''

echo
echo "gefunden: $GEFUNDEN   entwischt: $ENTWISCHT"
[ "$ENTWISCHT" -eq 0 ] || exit 1
