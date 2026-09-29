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
#   ./werkzeuge/alle-pruefen.sh            alles
#   ./werkzeuge/alle-pruefen.sh --schnell  ohne Gegenproben (Minuten statt
#                                          einer Viertelstunde)
#
# Die Ausgabe jeder Pruefung landet in einer Datei; hier steht nur, ob sie
# gruen war, und bei Rot die letzten Zeilen. Nie durch eine Pipe gelesen
# (N-39): der Rueckgabewert ist der der Pruefung selbst.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
SCHNELL=0
[ "${1:-}" = "--schnell" ] && SCHNELL=1

PROTOKOLLE=$(mktemp -d)
ERGEBNIS=()
ROT=0

lauf() {   # lauf <name> <befehl...>
  local NAME="$1"; shift
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

printf '\nPruefungen der Werkzeuge mit eigenem Code\n'
for A in "$STACK"/*/tests/alle.sh; do
  [ -e "$A" ] || continue
  W=$(basename "$(dirname "$(dirname "$A")")")
  lauf "$W/tests/alle.sh" bash "$A"
done

printf '\nPruefungen des Stapels\n'
for P in "$HIER"/*-pruefen.sh; do
  [ -e "$P" ] || continue
  [ "$(basename "$P")" = "alle-pruefen.sh" ] && continue
  lauf "werkzeuge/$(basename "$P")" bash "$P"
done
lauf "werkzeuge/prolo-befehle-pruefen.py" python3 "$HIER/prolo-befehle-pruefen.py" "$STACK"

if [ "$SCHNELL" -eq 0 ]; then
  printf '\nGegenproben (haben die Pruefungen Zaehne? §13a)\n'
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
  # Pruefer mit eingebauter Gegenprobe: erkannt am Schalter, nicht am Namen.
  for P in "$HIER"/*-pruefen.sh; do
    [ -e "$P" ] || continue
    [ "$(basename "$P")" = "alle-pruefen.sh" ] && continue
    grep -q -- '--gegenprobe' "$P" || continue
    lauf "werkzeuge/$(basename "$P") --gegenprobe" bash "$P" --gegenprobe
  done
fi

printf '\n'
if [ "$ROT" -eq 0 ]; then
  printf 'Alles gruen.\n'
  rm -rf "$PROTOKOLLE"
  exit 0
fi
printf '%d rot: %s\n' "$ROT" "${ERGEBNIS[*]}"
printf 'Die ganzen Ausgaben liegen in %s\n' "$PROTOKOLLE"
exit 1
