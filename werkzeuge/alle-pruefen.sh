#!/bin/bash
# werkzeuge/alle-pruefen.sh
#
# Ein Lauf fuer alles (N-97): jede Pruefung und jede Gegenprobe dieses
# Stapels, mit einer Tabelle am Ende und einem Rueckgabewert, der nur dann
# 0 ist, wenn ALLES gruen ist.
#
# Warum es das braucht: eine Mutation in prolo-befehle-pruefen.py liess
# sich seit N-61 nicht mehr einbauen. Die Gegenprobe war damit rot - und
# niemand hat es gemerkt, weil sie nur laeuft, wenn jemand sie von Hand
# aufruft. Eine Pruefung, die niemand ausfuehrt, prueft nichts.
#
# Gefunden wird alles am Dateisystem, nicht an einer Liste (§16): jede
# werkzeuge/*-pruefen.sh, jede Gegenprobe, jedes <werkzeug>/tests/alle.sh.
# Eine neue Pruefung braucht hier keine Zeile.
#
#   ./werkzeuge/alle-pruefen.sh              alles (gut eine Stunde)
#   ./werkzeuge/alle-pruefen.sh --schnell    ohne Gegenproben (Minuten)
#   ./werkzeuge/alle-pruefen.sh --teil 2/4   nur jede vierte Pruefung, ab
#                                            der zweiten (N-111)
#   ./werkzeuge/alle-pruefen.sh --liste      nur die Namen, nichts ausfuehren
#
# --teil ist fuer GitHub: dort laufen die Teile nebeneinander, jeder auf
# einer eigenen Maschine. Am Stueck lief der Lauf in die Zeitgrenze von 45
# Minuten und wurde abgebrochen - mit lauter gruenen Zeilen davor (N-111).
# Die Teile werden aus DERSELBEN Liste geschnitten wie der ganze Lauf,
# reihum nach Nummer: was es gibt, landet in genau einem Teil.
# werkzeuge/aufteilung-pruefen.sh haelt das fest.
#
# Die Ausgabe jeder Pruefung landet in einer Datei; hier steht nur, ob sie
# gruen war, und bei Rot die letzten Zeilen. Nie durch eine Pipe gelesen
# (N-39): der Rueckgabewert ist der der Pruefung selbst.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
SCHNELL=0; LISTE=0; TEIL=1; TEILE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --schnell) SCHNELL=1 ;;
    --liste)   LISTE=1 ;;
    --teil)
      if [[ "${2:-}" =~ ^([1-9][0-9]*)/([1-9][0-9]*)$ ]] \
         && [ "${BASH_REMATCH[1]}" -le "${BASH_REMATCH[2]}" ]; then
        TEIL=${BASH_REMATCH[1]}; TEILE=${BASH_REMATCH[2]}; shift
      else
        echo "--teil erwartet <nummer>/<anzahl>, die Nummer von 1 bis zur Anzahl - etwa --teil 2/4." >&2
        exit 2
      fi ;;
    *) echo "Unbekannt: $1 - moeglich sind --schnell, --teil <nummer>/<anzahl> und --liste." >&2
       exit 2 ;;
  esac
  shift
done

PROTOKOLLE=$(mktemp -d)
ERGEBNIS=()
ROT=0
NR=0      # laufende Nummer in der ganzen Liste - daran haengt der Teil
GELAUFEN=0

abschnitt() { [ "$LISTE" -eq 1 ] || printf '\n%s\n' "$1"; }

lauf() {   # lauf <name> <befehl...>
  local NAME="$1"; shift
  NR=$((NR + 1))
  [ $(( (NR - 1) % TEILE + 1 )) -eq "$TEIL" ] || return 0
  if [ "$LISTE" -eq 1 ]; then
    printf '%s\n' "$NAME"; return 0
  fi
  GELAUFEN=$((GELAUFEN + 1))
  local DATEI="$PROTOKOLLE/$(printf '%s' "$NAME" | tr '/ ' '__').log"
  local START=$SECONDS R
  printf '  %-52s ' "$NAME"
  ( cd "$STACK" && "$@" ) > "$DATEI" 2>&1
  R=$?
  if [ "$R" -eq 0 ]; then
    printf 'gruen  %4ss\n' "$((SECONDS - START))"
  else
    printf 'ROT    %4ss  (Rueckgabe %s)\n' "$((SECONDS - START))" "$R"
    grep -E '^(FEHLER|ENTWISCHT|DURCHGERUTSCHT|ABBRUCH|DANEBEN|FAIL|ERROR)|NICHT EINGEBAUT|unentdeckt' "$DATEI" \
      | head -5 | sed 's/^/        /'
    ROT=$((ROT + 1))
    ERGEBNIS+=("$NAME")
  fi
}

abschnitt 'Pruefungen der Werkzeuge mit eigenem Code'
for A in "$STACK"/*/tests/alle.sh; do
  [ -e "$A" ] || continue
  W=$(basename "$(dirname "$(dirname "$A")")")
  lauf "$W/tests/alle.sh" bash "$A"
done

abschnitt 'Pruefungen des Stapels'
for P in "$HIER"/*-pruefen.sh; do
  [ -e "$P" ] || continue
  [ "$(basename "$P")" = "alle-pruefen.sh" ] && continue
  lauf "werkzeuge/$(basename "$P")" bash "$P"
done
lauf "werkzeuge/prolo-befehle-pruefen.py" python3 "$HIER/prolo-befehle-pruefen.py" "$STACK"

if [ "$SCHNELL" -eq 0 ]; then
  abschnitt 'Gegenproben (haben die Pruefungen Zaehne? §13a)'
  for G in "$HIER"/*-gegenprobe.py; do
    [ -e "$G" ] || continue
    case "$(basename "$G")" in
      # braucht Stapel und Pruefer als Argumente - laeuft ueber seinen Pruefer
      geheimnisse-gegenprobe.py) continue ;;
    esac
    lauf "werkzeuge/$(basename "$G")" python3 "$G"
  done
  lauf "werkzeuge/prolo-befehle-pruefen.py --gegenprobe" \
       python3 "$HIER/prolo-befehle-pruefen.py" --gegenprobe
  # Die Gegenproben der Werkzeuge selbst. admin ruft seine aus alle.sh,
  # bordbuch und www nicht - ohne diese Zeilen liefen sie nur von Hand.
  for G in "$STACK"/*/tests/gegenprobe.sh "$STACK"/*/tests/gegenprobe.py; do
    [ -e "$G" ] || continue
    W=$(basename "$(dirname "$(dirname "$G")")")
    grep -q "gegenprobe" "$STACK/$W/tests/alle.sh" 2>/dev/null && continue
    case "$G" in
      *.sh) lauf "$W/tests/$(basename "$G")" bash "$G" ;;
      *.py) lauf "$W/tests/$(basename "$G")" python3 "$G" ;;
    esac
  done
  # Pruefer mit eingebauter Gegenprobe: erkannt am Schalter, nicht am Namen.
  for P in "$HIER"/*-pruefen.sh; do
    [ -e "$P" ] || continue
    [ "$(basename "$P")" = "alle-pruefen.sh" ] && continue
    grep -q -- '--gegenprobe' "$P" || continue
    lauf "werkzeuge/$(basename "$P") --gegenprobe" bash "$P" --gegenprobe
  done
fi

if [ "$LISTE" -eq 1 ]; then
  rm -rf "$PROTOKOLLE"; exit 0
fi
printf '\n'
WAS="Alles"
[ "$TEILE" -gt 1 ] && WAS="Teil $TEIL von $TEILE"
if [ "$ROT" -eq 0 ]; then
  printf '%s gruen (%d Pruefungen).\n' "$WAS" "$GELAUFEN"
  rm -rf "$PROTOKOLLE"
  exit 0
fi
printf '%s: %d von %d rot: %s\n' "$WAS" "$ROT" "$GELAUFEN" "${ERGEBNIS[*]}"
printf 'Die ganzen Ausgaben liegen in %s\n' "$PROTOKOLLE"
exit 1
