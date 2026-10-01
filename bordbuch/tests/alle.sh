#!/bin/bash
# Alle Tests, Server und Oberflaeche. Rueckgabewert 0 nur, wenn beides gruen ist.
set -u
cd "$(dirname "$0")/.."
FEHLER=0

echo "=== Server (Python) ==="
python3 -m unittest discover -s tests -t tests || FEHLER=1

echo
echo "=== Oberflaeche (Node) ==="
if command -v node >/dev/null 2>&1; then
  node tests/test_geld_oberflaeche.mjs || FEHLER=1
  node tests/test_wege.mjs || FEHLER=1
  node tests/test_thema.mjs || FEHLER=1
else
  echo "node ist nicht installiert - die Oberflaechen-Tests wurden UEBERSPRUNGEN." >&2
  echo "Das ist kein Erfolg: bitte node installieren oder die Tests von Hand laufen lassen." >&2
  FEHLER=1
fi

echo
echo "=== Vertrag mit dem Betrieb: hat der Test Zaehne? (§13a) ==="
python3 tests/gegenprobe_vertrag.py || FEHLER=1

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Alles gruen."
else
  echo "TESTS FEHLGESCHLAGEN." >&2
fi
exit "$FEHLER"
