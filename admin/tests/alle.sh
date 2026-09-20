#!/bin/bash
# Alle Tests der Admin-Uebersicht. Rueckgabewert 0 nur, wenn alles gruen ist.
set -u
cd "$(dirname "$0")/.."
FEHLER=0

echo "=== Dienst, Rechte und Lage (Python) ==="
python3 -m unittest discover -s tests -t tests -v 2>&1 | tail -5 || FEHLER=1
python3 -m unittest discover -s tests -t tests >/dev/null 2>&1 || FEHLER=1

echo
echo "=== Gegenprobe: haben die Tests Zaehne? (§13a) ==="
./tests/gegenprobe.sh || FEHLER=1

echo
echo "=== Die Fassung steht an drei Stellen gleich ==="
V_PY=$(python3 server.py --version)
V_YML=$(grep -m1 'image: prolo-admin:' docker-compose.yml | sed 's/.*prolo-admin://;s/ .*//')
V_MD=$(head -1 CHANGELOG.md | sed 's/^# //')
echo "  server.py $V_PY | docker-compose.yml $V_YML | CHANGELOG.md $V_MD"
if [ "$V_PY" != "$V_YML" ] || [ "$V_PY" != "$V_MD" ]; then
  echo "FEHLER  die drei Fassungsnummern stimmen nicht ueberein (§16)" >&2
  FEHLER=1
fi

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
