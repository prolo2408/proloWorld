#!/usr/bin/env bash
# werkzeuge/einrichten-pruefen.sh
#
# Tut "prolo einrichten" wirklich nur das, was noch fehlt? (N-54)
#
# Das ist die einzige Eigenschaft, auf die es bei diesem Skript ankommt.
# Ein Einrichtungsskript, das beim zweiten Lauf etwas ueberschreibt, ist
# gefaehrlicher als gar keines: man ruft es arglos auf, weil "es tut ja
# nur, was fehlt" - und verliert eine .env.
#
# Gearbeitet wird auf einer KOPIE im Kratzblock, mit einer Docker-Attrappe
# auf dem PATH. Nie am echten Stack: eine Probe, die zurueckrollt, nimmt
# eine noch nicht eingecheckte Korrektur mit (N-34).
#
#   ./werkzeuge/einrichten-pruefen.sh
#   ./werkzeuge/einrichten-pruefen.sh --gegenprobe
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
GEGENPROBE=0
[ "${1:-}" = "--gegenprobe" ] && GEGENPROBE=1

FEHLER=0
sag() { if [ "$1" = "ok" ]; then printf 'ok     %s\n' "$2"
        else printf 'FEHLER %s\n' "$2"; [ -n "${3:-}" ] && printf '       -> %s\n' "$3"
             FEHLER=1; fi; }

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

# --- Docker-Attrappe: merkt sich Netze und laufende Dienste in Dateien,
#     damit "schon da" beim zweiten Lauf auch wirklich schon da ist.
mkdir -p "$T/bin"
cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
N="$DOCKER_ATTRAPPE/netze"; L="$DOCKER_ATTRAPPE/laufen"
touch "$N" "$L"
case "$1 $2" in
  "network inspect") grep -qx "$3" "$N" && exit 0 || exit 1 ;;
  "network create")  echo "$3" >> "$N"; echo "id-$3"; exit 0 ;;
  "compose version") echo "Docker Compose version v2.0.0"; exit 0 ;;
esac
if [ "$1" = "compose" ]; then
  DIR="$PWD"
  for i in "$@"; do case "$VOR" in --project-directory) DIR="$i" ;; esac; VOR="$i"; done
  case " $* " in
    *" ps "*) grep -qx "$(basename "$DIR")" "$L" && echo "c-$(basename "$DIR")"; exit 0 ;;
    *" up "*) basename "$DIR" >> "$L"; exit 0 ;;
  esac
fi
[ "$1" = "inspect" ] && { echo healthy; exit 0; }
exit 0
STUB
chmod +x "$T/bin/docker"
export DOCKER_ATTRAPPE="$T/att"; mkdir -p "$DOCKER_ATTRAPPE"

# --- Kopie des Stacks: nur, was das Skript liest
kopieren() {
  local Z="$1"; mkdir -p "$Z/werkzeuge"
  cp "$HIER/einrichten.sh" "$HIER/geheimnisse.py" "$HIER/prolo" "$Z/werkzeuge/"
  local D
  for D in "$STACK"/*/docker-compose.yml; do
    [ -e "$D" ] || continue
    local W; W=$(basename "$(dirname "$D")")
    mkdir -p "$Z/$W"; cp "$D" "$Z/$W/"
    [ -f "$STACK/$W/geheimnisse.conf" ] && cp "$STACK/$W/geheimnisse.conf" "$Z/$W/"
    [ -f "$STACK/$W/.env.beispiel" ] && cp "$STACK/$W/.env.beispiel" "$Z/$W/"
    if [ -f "$STACK/$W/dynamic/einlass.yml.beispiel" ]; then
      mkdir -p "$Z/$W/dynamic"
      cp "$STACK/$W/dynamic/einlass.yml.beispiel" "$Z/$W/dynamic/"
    fi
  done
  # Sicherungsschluessel, sonst kommt Schritt 7 nicht dran
  age-keygen 2>/dev/null > "$Z/probe.key"
  grep '^# public key:' "$Z/probe.key" | cut -d' ' -f4 > "$Z/.backup-schluessel.pub"
}

lauf() {  # lauf <wurzel> [--trocken]
  ( cd "$1" && PATH="$T/bin:$PATH" HOME="$1" \
      bash "$1/werkzeuge/einrichten.sh" ${2:-} < /dev/null 2>&1 )
}

pruefen_einmal() {
  local W="$1"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"

  local A1 R1
  A1=$(lauf "$W"); R1=$?
  echo "$A1" > "$W/lauf1.txt"

  grep -q "getan" <<<"$A1" && sag ok "erster Lauf richtet wirklich etwas ein" \
    || sag FEHLER "erster Lauf hat nichts getan" "dann prueft der zweite nichts"

  # Alles, was da sein muss, ist da
  local FEHLT=0 W2
  for W2 in "$W"/*/geheimnisse.conf; do
    [ -e "$W2" ] || continue
    local ORD; ORD=$(dirname "$W2")
    while IFS='|' read -r NAME DATEI REST; do
      case "$NAME" in ''|\#*) continue ;; esac
      [ -f "$ORD/$DATEI" ] || { echo "       fehlt: $ORD/$DATEI"; FEHLT=1; }
    done < "$W2"
  done
  [ "$FEHLT" -eq 0 ] && sag ok "jede erklaerte Geheimnisdatei ist angelegt" \
    || sag FEHLER "eine erklaerte Geheimnisdatei fehlt nach dem Lauf"

  # Die Marke steht ueberall gleich
  local WERTE
  WERTE=$(PATH="$T/bin:$PATH" python3 "$W/werkzeuge/geheimnisse.py" 2>&1 \
          | grep "PROLO_EINLASS " | head -1)
  grep -q "gleich an allen" <<<"$WERTE" \
    && sag ok "die Einlassmarke steht an allen Stellen gleich" \
    || sag FEHLER "die Einlassmarke steht nicht ueberall gleich" "$WERTE"

  # --- Der Kern: zweiter Lauf
  local VORHER NACHHER A2
  VORHER=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  A2=$(lauf "$W"); echo "$A2" > "$W/lauf2.txt"
  NACHHER=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)

  [ "$VORHER" = "$NACHHER" ] \
    && sag ok "zweiter Lauf laesst jede Datei byteweise, wie sie war" \
    || sag FEHLER "zweiter Lauf hat eine Datei veraendert" \
           "genau das darf ein Einrichtungsskript nie"

  grep -q "getan" <<<"$A2" \
    && sag FEHLER "zweiter Lauf meldet noch 'getan'" "es sollte nichts mehr zu tun geben" \
    || sag ok "zweiter Lauf tut nichts mehr"

  grep -q "steht schon an allen" <<<"$A2" \
    && sag ok "zweiter Lauf erkennt das Geheimnis als vollstaendig" \
    || sag FEHLER "zweiter Lauf erkennt das vorhandene Geheimnis nicht"

  # Das selbst angelegte Netz darf er nicht anfassen
  grep -qx "socket" "$DOCKER_ATTRAPPE/netze" \
    && sag FEHLER "hat 'socket' von Hand angelegt" \
           "socket-proxy legt es selbst an, internal:true - von Hand waere es ein Bridge-Netz" \
    || sag ok "das selbst erzeugte Netz 'socket' bleibt unangetastet"

  grep -qx "netz-wiki" "$DOCKER_ATTRAPPE/netze" \
    && sag ok "die externen netz-* wurden angelegt" \
    || sag FEHLER "netz-wiki wurde nicht angelegt"

  # Ein Trockenlauf fasst nichts an
  local V3 N3
  V3=$(find "$W" -name '.env' | sort | xargs md5sum 2>/dev/null)
  lauf "$W" --trocken > /dev/null
  N3=$(find "$W" -name '.env' | sort | xargs md5sum 2>/dev/null)
  [ "$V3" = "$N3" ] && sag ok "--trocken fasst keine Datei an" \
    || sag FEHLER "--trocken hat etwas veraendert"
}

if [ "$GEGENPROBE" -eq 0 ]; then
  pruefen_einmal "$T/stack"
  echo
  [ "$FEHLER" -eq 0 ] && echo "Alles gruen." || echo "EINRICHTUNGSPRUEFUNG FEHLGESCHLAGEN." >&2
  exit "$FEHLER"
fi

# ---------------------------------------------------------- Gegenprobe
echo "Gegenprobe: jede eingebaute Schwaeche muss auffallen."
echo
GEFUNDEN=0; DURCH=""
probe() {   # probe "Name" "sed-Ausdruck auf einrichten.sh"
  local NAME="$1" AUSDRUCK="$2" W="$T/m$((++GEFUNDEN))"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  local ALT NEU A
  lauf "$W" > /dev/null                       # erster Lauf
  ALT=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  A=$(lauf "$W")                               # zweiter Lauf
  NEU=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  if [ "$ALT" != "$NEU" ] || grep -q "getan" <<<"$A"; then
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  else
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"
    DURCH="$DURCH$NAME; "
  fi
}

probe "die .env wird immer neu aus der Vorlage kopiert" \
      's|elif \[ -f "$PFAD" \]; then|elif false; then|'
probe "die fehlende Zeile wird immer angehaengt" \
      's|&& ! grep -q "\^$NAME=" "$PFAD"|\&\& true|'

echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"
  echo "Das ist eine Testluecke, keine Meinungsfrage (§13a)."
  exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
