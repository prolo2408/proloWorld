#!/bin/bash
# werkzeuge/crowdsec-pruefen.sh - die Firewall unter echtem CrowdSec (F-01)
#
# Startet CrowdSec aus crowdsec/docker-compose.yml, speist Zeilen mit von
# Hand festgelegtem Ausgang ein und vergleicht die Sperren. Die Einzelheiten
# stehen in werkzeuge/crowdsec-probe/probe.py.
#
#   ./werkzeuge/crowdsec-pruefen.sh              die Probe
#   ./werkzeuge/crowdsec-pruefen.sh --gegenprobe baut Fehler ein und
#                                                verlangt, dass JEDER auffaellt
#
# Braucht docker und das Abbild aus crowdsec/docker-compose.yml. Fehlt
# docker, ist das ein Fehler: ein uebersprungener Test ist kein gruener.
set -u
HIER="$(cd "$(dirname "$0")" && pwd)"
STACK="$(dirname "$HIER")"
PROBE="$HIER/crowdsec-probe/probe.py"

if [ "${1:-}" != "--gegenprobe" ]; then
  python3 "$PROBE" "$STACK"; R=$?
  echo
  [ "$R" -eq 0 ] && echo "crowdsec-pruefen: gruen" || echo "crowdsec-pruefen: ROT"
  exit "$R"
fi

# ------------------------------------------------------------ Gegenprobe
# Auf einer Kopie, nie im Arbeitsstand (N-34, N-60). Kopiert wird, was die
# Probe liest: crowdsec/, die zwei Traefik-Dateien und prolo firewall.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
kopie() {
  local Z="$1"; rm -rf "$Z"; mkdir -p "$Z/traefik/log"
  ( cd "$STACK" && git ls-files -z crowdsec | xargs -0 -I{} cp --parents {} "$Z/" )
  cp "$STACK/traefik/traefik.yml" "$STACK/traefik/docker-compose.yml" "$Z/traefik/"
  mkdir -p "$Z/werkzeuge"; cp "$STACK/werkzeuge/firewall.py" "$Z/werkzeuge/"
}

GEFUNDEN=0; DURCH=""; N=0
mutation() {   # mutation <name> <datei> <alt> <neu> <erwartete Zeile>
  local NAME="$1" DATEI="$2" ALT="$3" NEU="$4" ERWARTET="$5" Z="$T/m" A R
  N=$((N + 1)); kopie "$Z"
  if ! python3 - "$Z/$DATEI" "$ALT" "$NEU" <<'PY'
import sys
p, alt, neu = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(p, encoding="utf-8").read()
if t.count(alt) != 1:
    sys.exit(1)
open(p, "w", encoding="utf-8").write(t.replace(alt, neu))
PY
  then
    printf '%2d. %-58s NICHT EINGEBAUT (Muster nicht genau einmal in %s)\n' "$N" "$NAME" "$DATEI"
    DURCH="$DURCH$NAME; "; return
  fi
  A=$(python3 "$PROBE" "$Z"); R=$?
  # Nicht "irgendetwas ist rot" - die RICHTIGE Zeile muss rot sein.
  if [ "$R" -ne 0 ] && grep "^FEHLER" <<<"$A" | grep -qF "$ERWARTET"; then
    printf '%2d. %-58s gefunden\n' "$N" "$NAME"; GEFUNDEN=$((GEFUNDEN + 1))
  else
    printf '%2d. %-58s DURCHGERUTSCHT\n' "$N" "$NAME"
    grep "^FEHLER" <<<"$A" | head -2 | sed 's/^/      /'
    DURCH="$DURCH$NAME; "
  fi
}

mutation "der Eimer fuer Zugangslinks fasst 10 statt 9" \
  crowdsec/regeln/zugangslink-raten.yaml "capacity: 9" "capacity: 10" \
  "10 unbekannte Zugangslinks"
mutation "der Eimer fuer Zugangslinks fasst 8 statt 9" \
  crowdsec/regeln/zugangslink-raten.yaml "capacity: 9" "capacity: 8" \
  "9 unbekannte Zugangslinks"
mutation "die Falle kennt /wp-login.php nicht" \
  crowdsec/regeln/falle.yaml "'/wp-login.php', " "" \
  "ein Aufruf von /wp-login.php"
mutation "eigene Regeln sperren nur 4 statt 24 Stunden" \
  crowdsec/profiles.yaml "    duration: 24h" "    duration: 4h" \
  "10 unbekannte Zugangslinks"
mutation "Wiederholungstaeter werden nicht laenger gesperrt" \
  crowdsec/profiles.yaml "duration_expr: Sprintf('%dh', (GetDecisionsCount(Alert.GetValue()) + 1) * 4)" "" \
  "nach einer frueheren Sperre"
mutation "die Erfassung liest eine andere Datei als Traefik schreibt" \
  crowdsec/erfassung/traefik.yaml "/var/log/traefik/zugriff.log" "/var/log/traefik/access.log" \
  "Traefik schreibt, wo CrowdSec liest"
mutation "Traefik schreibt eine andere Datei" \
  traefik/traefik.yml "filePath: /var/log/traefik/zugriff.log" "filePath: /var/log/traefik/access.log" \
  "Traefik schreibt, wo CrowdSec liest"
mutation "config.yaml.local zeigt nicht auf die Erfassung" \
  crowdsec/config.yaml.local "acquisition_dir: /prolo/erfassung" "acquisition_dir: /etc/crowdsec/acquis.d" \
  "liest beide Protokolle"
mutation "die eigenen Regeln liegen nicht, wo CrowdSec sucht" \
  crowdsec/docker-compose.yml "./regeln:/etc/crowdsec/scenarios/prolo:ro" "./regeln:/etc/crowdsec/regeln:ro" \
  "die eigenen Regeln aus regeln/ sind geladen"
mutation "die lokale API steht an allen Adressen offen" \
  crowdsec/docker-compose.yml '"127.0.0.1:8080:8080"' '"8080:8080"' \
  "nur auf 127.0.0.1"
mutation "die Grenzen fehlen" \
  crowdsec/docker-compose.yml "    cap_drop:
      - ALL
" "" \
  "Grenzen nach §19"
mutation "der Bouncer-Schluessel ist fest eingetragen" \
  crowdsec/docker-compose.yml 'BOUNCER_KEY_firewall: "${CROWDSEC_BOUNCER_SCHLUESSEL:?' 'BOUNCER_KEY_firewall: "fest${CROWDSEC_BOUNCER_SCHLUESSEL:?' \
  "der Bouncer-Schluessel kommt aus"

# prolo firewall
mutation "firewall sperrt auch interne Adressen" \
  werkzeuge/firewall.py "if zum_sperren and (not netz.is_global or netz.is_multicast):" "if False:" \
  "lehnt eine private Adresse ab"
mutation "firewall sperrt ein /8" \
  werkzeuge/firewall.py "MIN_PRAEFIX = {4: 16, 6: 48}" "MIN_PRAEFIX = {4: 8, 6: 32}" \
  "groesser als /16"
mutation "firewall sperrt, was auf der Freigabeliste steht" \
  werkzeuge/firewall.py "    f = auf_der_liste(wert)
    if f:" "    f = None
    if f:" \
  "eine freigegebene Adresse laesst sich nicht sperren"
mutation "firewall rechnet Tage als Stunden" \
  werkzeuge/firewall.py '"%dh" % (n * 24 if einheit == "d" else n)' '"%dh" % n' \
  "13 Tage sind 312 Stunden"
mutation "firewall --json vergisst eine Quelle" \
  werkzeuge/firewall.py "    for q in erfasste_dateien():
        l[\"gelesen\"][q]" "    for q in erfasste_dateien()[:0]:
        l[\"gelesen\"][q]" \
  "vor der ersten Zeile nennt firewall --json beide Quellen"
mutation "firewall sperrt ohne Grund" \
  werkzeuge/firewall.py '    if not text:
        raise Nein("ohne Grund' '    if False:
        raise Nein("ohne Grund' \
  "ohne Grund wird nicht gesperrt"

echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"
  echo "Das ist eine Testluecke, keine Meinungsfrage (§13a)."
  exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
