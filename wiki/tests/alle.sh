#!/bin/bash
# Alle Wiki-Tests, Server und Oberflaeche. Rueckgabewert 0 nur, wenn beides
# gruen ist.
set -u
cd "$(dirname "$0")/.."
FEHLER=0

echo "=== Server und Seiten (Python) ==="
python3 -m unittest discover -s tests -t tests || FEHLER=1

echo
echo "=== Editor (Node) ==="
if command -v node >/dev/null 2>&1; then
  node tests/test_editor.mjs || FEHLER=1
else
  echo "node ist nicht installiert - der Editortest wurde UEBERSPRUNGEN." >&2
  echo "Das ist kein Erfolg: bitte node installieren oder von Hand laufen lassen." >&2
  FEHLER=1
fi

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
