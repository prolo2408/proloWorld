#!/bin/bash
# werkzeuge/aufteilung-pruefen.sh - geht bei der Aufteilung etwas verloren? (N-111)
#
# Auf GitHub laeuft alle-pruefen.sh in Teilen nebeneinander (--teil n/m),
# weil der Lauf am Stueck in die Zeitgrenze lief. Eine Aufteilung hat eine
# eigene Art zu scheitern: eine Pruefung faellt zwischen zwei Teile und
# laeuft nirgends - und alle Teile sind gruen. Das haelt dieser Pruefer fest:
#
#   1. --liste nennt jede Pruefung, die es gibt, und fuehrt nichts aus
#   2. fuer 1 bis 7 Teile: die Teile zusammen ergeben genau die ganze Liste,
#      jede Pruefung in genau einem Teil
#   3. ein unmoeglicher Teil (0/4, 5/4, 2, x/y) wird abgewiesen, statt
#      still null Pruefungen gruen zu melden
#   4. der Workflow schneidet die Teile aus strategy.job-index/job-total,
#      nicht aus festen Zahlen, und der Sammeljob "alles" wird nur gruen,
#      wenn jeder Teil gruen ist
#
#   ./werkzeuge/aufteilung-pruefen.sh
#   ./werkzeuge/aufteilung-pruefen.sh --gegenprobe
set -u
HIER="$(cd "$(dirname "$0")" && pwd)"
STACK="$(dirname "$HIER")"

pruefen() {   # pruefen <wurzel> -> ok/FEHLER-Zeilen, Rueckgabe 0/1
  local W="$1" F=0 A="$1/werkzeuge/alle-pruefen.sh" T B
  T=$(mktemp -d)
  B=$(command -v bash)
  # Was alle-pruefen.sh ausfuehren wuerde, laeuft ueber "bash" und "python3"
  # aus dem PATH. Hier sind beide Attrappen, die nur mitschreiben: faengt
  # --liste an auszufuehren, steht es in $T/ausgefuehrt - statt eine Stunde
  # lang echte Pruefungen zu starten.
  mkdir "$T/attrappe"
  local b
  for b in bash python3; do
    printf '#!/bin/sh\necho "$0 $*" >> "%s/ausgefuehrt"\n' "$T" > "$T/attrappe/$b"
    chmod +x "$T/attrappe/$b"
  done
  alle() { PATH="$T/attrappe:$PATH" timeout 30 "$B" "$A" "$@"; }

  # 1. Die ganze Liste
  alle --liste > "$T/ganz" 2> "$T/fehler"
  local R=$?
  if [ "$R" -ne 0 ] || [ -e "$T/ausgefuehrt" ]; then
    echo "FEHLER --liste fuehrt aus oder scheitert (Rueckgabe $R): $(head -c 200 "$T/fehler" "$T/ausgefuehrt" 2>/dev/null | tr '\n' ' ')"
    F=1
  fi
  # Von Hand erwartet: jedes <werkzeug>/tests/alle.sh, jede
  # werkzeuge/*-pruefen.sh ausser alle-pruefen.sh - und jede, die einen
  # Schalter --gegenprobe hat, ein zweites Mal mit ihm
  local fehlt=0 p n
  for p in "$W"/*/tests/alle.sh "$W"/werkzeuge/*-pruefen.sh; do
    [ -e "$p" ] || continue
    n="${p#"$W"/}"
    [ "$n" = "werkzeuge/alle-pruefen.sh" ] && continue
    grep -qxF "$n" "$T/ganz" || { echo "FEHLER --liste nennt $n nicht"; fehlt=1; }
    case "$n" in
      *-pruefen.sh)
        grep -q -- '--gegenprobe' "$p" && ! grep -qxF "$n --gegenprobe" "$T/ganz" \
          && { echo "FEHLER --liste nennt $n --gegenprobe nicht"; fehlt=1; } ;;
    esac
  done
  [ "$fehlt" -eq 0 ] && [ "$F" -eq 0 ] \
    && echo "ok     --liste nennt $(wc -l < "$T/ganz") Pruefungen, jede Pruefung samt Gegenprobe, und fuehrt nichts aus"
  [ "$fehlt" -eq 0 ] || F=1

  # 2. Die Teile ergeben zusammen genau die ganze Liste
  local m i sauber=1
  for m in 1 2 3 4 5 6 7; do
    : > "$T/zusammen"
    for i in $(seq 1 "$m"); do
      if ! alle --teil "$i/$m" --liste >> "$T/zusammen" 2>> "$T/fehler"; then
        echo "FEHLER --teil $i/$m scheitert"; sauber=0
      fi
    done
    if ! diff <(sort "$T/ganz") <(sort "$T/zusammen") > "$T/diff"; then
      echo "FEHLER $m Teile ergeben nicht die ganze Liste: $(grep '^[<>]' "$T/diff" | head -3 | tr '\n' ' ')"
      sauber=0
    fi
  done
  [ -s "$T/ganz" ] && [ ! -e "$T/ausgefuehrt" ] || sauber=0
  if [ "$sauber" -eq 1 ]; then
    echo "ok     1 bis 7 Teile ergeben je genau die ganze Liste - nichts fehlt, nichts doppelt"
  else
    F=1
  fi

  # 3. Unmoegliche Teile werden abgewiesen
  local falsch abgewiesen=1
  for falsch in 0/4 5/4 2 x/y 1/0 ""; do
    alle --teil "$falsch" --liste > "$T/aus" 2>&1
    R=$?
    if [ "$R" -ne 2 ]; then
      echo "FEHLER --teil '$falsch' nicht abgewiesen (Rueckgabe $R)"; abgewiesen=0
    fi
  done
  if [ "$abgewiesen" -eq 1 ]; then
    echo "ok     unmoegliche Teile (0/4, 5/4, 2, x/y, 1/0, leer) abgewiesen"
  else
    F=1
  fi

  # 4. Der Workflow
  if python3 - "$W/.github/workflows/pruefen.yml" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
aufrufe = re.findall(r"(?m)^\s*run:.*alle-pruefen\.sh.*$", t)
teil = r'--teil "\$\(\( \$\{\{ strategy\.job-index \}\} \+ 1 \)\)/\$\{\{ strategy\.job-total \}\}"'
fehler = []
if not aufrufe:
    fehler.append("ruft alle-pruefen.sh gar nicht auf")
for a in aufrufe:
    if not re.search(teil, a):
        fehler.append("Teil nicht aus job-index/job-total: " + a.strip())
# Der Sammeljob: laeuft immer und prueft das Ergebnis aller Teile
m = re.search(r"(?ms)^  alles:\n(.*?)(?=^  \S|\Z)", t)
if not m:
    fehler.append("kein Sammeljob 'alles'")
else:
    s = m.group(1)
    need = re.search(r"(?m)^    needs:\s*(\S+)", s)
    if not need:
        fehler.append("Sammeljob ohne needs")
    else:
        if not re.search(r"(?m)^    if:\s*always\(\)", s):
            fehler.append("Sammeljob ohne 'if: always()' - bei rotem Teil liefe er gar nicht")
        if not re.search(r'"\$\{\{ needs\.%s\.result \}\}" != success' % re.escape(need.group(1)), s):
            fehler.append("Sammeljob prueft needs.%s.result nicht gegen success" % need.group(1))
for f in fehler:
    print("FEHLER Workflow: " + f)
sys.exit(1 if fehler else 0)
PY
  then
    echo "ok     Workflow: Teile aus job-index/job-total, Sammeljob 'alles' gruen nur mit allen Teilen"
  else
    F=1
  fi
  rm -rf "$T"
  return "$F"
}

if [ "${1:-}" != "--gegenprobe" ]; then
  pruefen "$STACK"; R=$?
  [ "$R" -eq 0 ] && echo "Alles gruen."
  exit "$R"
fi

# Gegenprobe - auf Kopien (N-34, N-60). Kopiert wird, was --liste ansieht:
# werkzeuge/, jedes <werkzeug>/tests/ und der Workflow.
K=$(mktemp -d); trap 'rm -rf "$K"' EXIT
GEFUNDEN=0; DURCH=""
probe() {   # probe <name> <datei> <sed-ausdruck>
  rm -rf "$K/s"; mkdir -p "$K/s/.github/workflows"
  cp -r "$STACK/werkzeuge" "$K/s/"
  local t
  for t in "$STACK"/*/tests; do
    mkdir -p "$K/s/$(basename "$(dirname "$t")")"
    cp -r "$t" "$K/s/$(basename "$(dirname "$t")")/"
  done
  cp "$STACK/.github/workflows/pruefen.yml" "$K/s/.github/workflows/"
  sed -i "$3" "$K/s/$2"
  if cmp -s "$STACK/$2" "$K/s/$2"; then
    printf 'NICHT EINGEBAUT  %s\n' "$1"; DURCH="$DURCH$1; "; return
  fi
  if pruefen "$K/s" > /dev/null 2>&1; then
    printf 'DURCHGERUTSCHT   %s\n' "$1"; DURCH="$DURCH$1; "
  else
    printf 'gefunden         %s\n' "$1"; GEFUNDEN=$((GEFUNDEN + 1))
  fi
}
probe "Teile zaehlen ab null - der letzte fehlt" werkzeuge/alle-pruefen.sh \
  's#(NR - 1) % TEILE + 1#NR % TEILE#'
probe "ein Teil nimmt die Nummer doppelt" werkzeuge/alle-pruefen.sh \
  's#-eq "$TEIL" \] || return 0#-ge "$TEIL" ] || return 0#'
probe "--liste fuehrt doch aus" werkzeuge/alle-pruefen.sh \
  '/printf .%s\\n. "\$NAME"; return 0/s#; return 0##'
probe "--liste laesst die Gegenproben aus" werkzeuge/alle-pruefen.sh \
  's#^if \[ "\$SCHNELL" -eq 0 \]; then#if [ "$SCHNELL" -eq 0 ] \&\& [ "$LISTE" -eq 0 ]; then#'
probe "5/4 wird angenommen" werkzeuge/alle-pruefen.sh \
  's#\[ "\${BASH_REMATCH\[1\]}" -le "\${BASH_REMATCH\[2\]}" \]#true#'
probe "Workflow mit fester Teilzahl" .github/workflows/pruefen.yml \
  's#/\${{ strategy.job-total }}#/4#'
probe "Sammeljob ohne if: always()" .github/workflows/pruefen.yml \
  '/^    if: always()/d'
probe "Sammeljob prueft das Ergebnis nicht" .github/workflows/pruefen.yml \
  's#!= success#!= egal#'
echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"; exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
