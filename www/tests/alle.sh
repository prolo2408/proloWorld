#!/bin/bash
# Alle Tests des Freigabe-Werkzeugs. Rueckgabewert 0 nur, wenn alles gruen ist.
set -u
cd "$(dirname "$0")/.."
FEHLER=0

echo "=== Dienst und Rechte (Python) ==="
python3 -m unittest discover -s tests -t tests || FEHLER=1

echo
echo "=== Vertrag mit dem Betrieb: hat der Test Zaehne? (§13a) ==="
python3 tests/gegenprobe_vertrag.py || FEHLER=1

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
