#!/usr/bin/env bash
# Alle Pruefungen, die ohne root und ohne laufenden Unterbau gehen.
#
#   tests/alle.sh                 Einheitstests, Gegenprobe, Syntax, shellcheck
#   sudo tests/alle.sh --durchlauf  dazu der echte Durchlauf mit Docker
#
# Der Rueckgabewert ist der der Pruefungen - nie durch eine Pipe lesen
# (CLAUDE.md, N-39).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
export PYTHONDONTWRITEBYTECODE=1
unset PROLO_ETC PROLO_VAR PROLO_TOOLS PROLO_BACKUP
FEHLER=0
lauf() {
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then echo "   grün: $name"; else echo "   ROT: $name"; FEHLER=$((FEHLER + 1)); fi
}

lauf "Python-Syntax" python3 -c 'import ast, sys
for f in sys.argv[1:]: ast.parse(open(f, encoding="utf-8").read(), f)' \
  prolo kern/*.py admin/server.py tests/*.py
lauf "Einheitstests" python3 -m unittest discover -s tests
lauf "Gegenprobe (haben die Tests Zähne?)" python3 tests/gegenprobe.py
if command -v shellcheck >/dev/null 2>&1; then
  lauf "shellcheck" shellcheck install.sh tests/alle.sh
else
  # Ein uebersprungener Test ist kein gruener Test.
  echo; echo "== shellcheck fehlt (apt install shellcheck)"; FEHLER=$((FEHLER + 1))
fi
if command -v docker >/dev/null 2>&1; then
  lauf "docker-compose.yml ist gueltig" env PROLO_EMAIL=a@b.de PROLO_DOMAIN=b.de PROLO_DOMAIN_RE='b\.de' \
    PROLO_VAR=/var/lib/prolo PG_PASS=x AUTHENTIK_SECRET_KEY=x AUTHENTIK_BOOTSTRAP_PASSWORD=x \
    PROLO_VERSION="$(cat VERSION)" docker compose -f docker-compose.yml config --quiet
fi
if [ "${1:-}" = "--durchlauf" ]; then
  lauf "Durchlauf mit Docker" python3 tests/durchlauf.py
fi

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles grün."; else echo "$FEHLER Pruefung(en) rot."; fi
exit "$FEHLER"
