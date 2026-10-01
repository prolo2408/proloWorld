#!/bin/bash
# werkzeuge/python-pruefen.sh - uebersetzt jeder Python-Code ohne Warnung? (N-112)
#
# In admin/server.py stand '\-' in einem gewoehnlichen Text - eine
# ungueltige Escape-Folge. Python 3.11 schweigt dazu, ab 3.12 kommt eine
# SyntaxWarning, eine kuenftige Fassung macht einen Fehler daraus. Die
# Warnung kommt nur beim UEBERSETZEN: liegt schon ein __pycache__ da, ist
# sie weg. So war die Pruefung auf GitHub gruen, solange die Admin-Tests
# vorher liefen, und rot, sobald ein Teil ohne sie auskam (N-111) - und
# lokal, mit 3.11, nie.
#
# Hier wird jeder Python-Code frisch uebersetzt, mit jeder Warnung als
# Fehler - das faengt es mit JEDER Fassung, auch mit 3.11 (dort ist es eine
# DeprecationWarning). Und nichts wird dabei geschrieben, auch kein
# __pycache__:
#
#   1. jede *.py-Datei
#   2. jeder Python-Heredoc (python3 ... <<'PY' ... PY) in Skripten und
#      Workflows - dort steckt ebenso viel Python wie in den .py-Dateien
#
#   ./werkzeuge/python-pruefen.sh
#   ./werkzeuge/python-pruefen.sh --gegenprobe
set -u
HIER="$(cd "$(dirname "$0")" && pwd)"
STACK="$(dirname "$HIER")"

pruefen() {   # pruefen <wurzel> -> ok/FEHLER-Zeilen, Rueckgabe 0/1
  python3 - "$1" <<'PY'
import os, re, sys, textwrap, warnings
wurzel = sys.argv[1]
AUSLASSEN = {".git", "__pycache__", "node_modules", ".archiv"}
# python3 [irgendwas] <<'PY' ... PY - auch eingerueckt (Workflows) und mit <<-.
# Eine Kommentarzeile beginnt keinen: sonst faellt der Pruefer ueber den
# eigenen Kopf, der genau so ein Beispiel nennt (N-36).
HEREDOC = re.compile(r"^(?![ \t]*#)[^\n]*?\bpython3?\b[^\n]*<<-?[ \t]*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n[ \t]*\2[ \t]*$",
                     re.S | re.M)
fehler, dateien, heredocs = [], 0, 0

def uebersetzen(code, name):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            compile(code, name, "exec", dont_inherit=True)
        except (SyntaxError, Warning) as e:
            fehler.append("%s: %s: %s" % (name, type(e).__name__, e))

for ordner, unter, namen in os.walk(wurzel):
    unter[:] = sorted(u for u in unter if u not in AUSLASSEN)
    for n in sorted(namen):
        pfad = os.path.join(ordner, n)
        rel = os.path.relpath(pfad, wurzel)
        if os.path.islink(pfad):
            continue
        try:
            with open(pfad, encoding="utf-8") as f:
                text = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        if n.endswith(".py"):
            dateien += 1
            uebersetzen(text, rel)
            continue
        for m in HEREDOC.finditer(text):
            heredocs += 1
            zeile = text.count("\n", 0, m.start()) + 1
            uebersetzen(textwrap.dedent(m.group(3)), "%s:%d (Heredoc)" % (rel, zeile))

if dateien == 0 or heredocs == 0:
    fehler.append("nichts gefunden (%d Dateien, %d Heredocs) - falscher Ordner?" % (dateien, heredocs))
for f in fehler:
    print("FEHLER " + f)
if not fehler:
    print("ok     %d Python-Dateien und %d Python-Heredocs uebersetzen ohne Warnung"
          % (dateien, heredocs))
sys.exit(1 if fehler else 0)
PY
}

if [ "${1:-}" != "--gegenprobe" ]; then
  pruefen "$STACK"; R=$?
  [ "$R" -eq 0 ] && echo "Alles gruen."
  exit "$R"
fi

# Gegenprobe - auf Kopien (N-34, N-60). Kopiert wird nur, was der Pruefer
# liest: jede Datei mit Python darin.
K=$(mktemp -d); trap 'rm -rf "$K"' EXIT
GEFUNDEN=0; DURCH=""
kopie() {
  rm -rf "$K/s"; mkdir -p "$K/s"
  ( cd "$STACK" && git ls-files -z -- '*.py' '*.sh' '*.yml' 'werkzeuge/*' \
      | xargs -0 cp --parents -t "$K/s" )
}
# Leerlauf: die UNVERAENDERTE Kopie muss gruen sein. Sonst waere jede
# Mutation "gefunden", nur weil die Kopie nicht taugt.
kopie
if ! pruefen "$K/s" > "$K/leerlauf" 2>&1; then
  echo "ABBRUCH  die unveraenderte Kopie ist schon rot:"; cat "$K/leerlauf"; exit 1
fi
probe() {   # probe <name> <datei> <sed-ausdruck>
  kopie
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
probe "admin/server.py wieder mit '\\-' (N-112)" admin/server.py \
  's#\[a-z0-9\\\\-\]{0,39}#[a-z0-9\\-]{0,39}#'
probe "ein Muster '\\d' in einer Datei tief im Baum" werkzeuge/crowdsec-probe/probe.py \
  '0,/^import /s#^import #X = "\\d"\nimport #'
probe "ein Muster '\\d' in einem Heredoc eines Skripts" werkzeuge/abbilder-pruefen.sh \
  's#^import re, sys$#import re, sys\nX = "\\d"#'
probe "ein Muster '\\d' in einem eingerueckten Heredoc eines Workflows" wiki/.github/workflows/abbild.yml \
  '0,/^\( *\)import /s#^\( *\)import #\1X = "\\d"\n\1import #'
probe "ein Muster '\\d' im Heredoc mit <<\"PY\" (backup.sh)" backup.sh \
  's#^import sqlite3, sys$#import sqlite3, sys\nX = "\\d"#'
echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"; exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
