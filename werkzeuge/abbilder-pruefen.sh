#!/bin/bash
# werkzeuge/abbilder-pruefen.sh - Hilfsabbilder nur mit fester Fassung (N-108)
#
# Sicherung, Wiederherstellung und prolo starten fuer tar ein kleines
# Hilfsabbild. Bis N-108 hiess es schlicht "alpine" - also alpine:latest,
# ausgerechnet auf dem Weg, der im Ernstfall zaehlt, und entgegen §19
# ("feste Fassungsnummer, niemals latest"). Jetzt nennt jedes der Skripte
# HILFSABBILD, und dieser Pruefer haelt fest:
#
#   1. jedes "docker run" in diesen Skripten nimmt "$HILFSABBILD"
#   2. HILFSABBILD steht ueberall gleich da, mit fester Fassung (Ziffern)
#
#   ./werkzeuge/abbilder-pruefen.sh
#   ./werkzeuge/abbilder-pruefen.sh --gegenprobe
set -u
HIER="$(cd "$(dirname "$0")" && pwd)"
STACK="$(dirname "$HIER")"
SKRIPTE="backup.sh werkzeuge/prolo werkzeuge/wiederherstellen.sh"

pruefen() {   # pruefen <wurzel> -> ok/FEHLER-Zeilen, Rueckgabe 0/1
  python3 - "$1" $SKRIPTE <<'PY'
import re, sys
wurzel, dateien = sys.argv[1], sys.argv[2:]
fehler = 0
werte = {}
for d in dateien:
    t = open("%s/%s" % (wurzel, d), encoding="utf-8").read()
    m = re.findall(r'(?m)^HILFSABBILD="([^"]*)"', t)
    werte[d] = m[0] if len(m) == 1 else None
    # Jede Zeile mit "docker run" samt ihren Fortsetzungszeilen
    zeilen = t.split("\n")
    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        if re.search(r"^\s*[^#]*\bdocker run\b", z):
            aufruf = z
            while aufruf.rstrip().endswith("\\") and i + 1 < len(zeilen):
                i += 1
                aufruf = aufruf.rstrip()[:-1] + " " + zeilen[i]
            if '"$HILFSABBILD"' not in aufruf:
                print("FEHLER %s:%d  docker run ohne \"$HILFSABBILD\": %s" % (d, i + 1, aufruf.strip()[:90]))
                fehler = 1
        i += 1
gleich = set(werte.values())
fest = all(v and re.fullmatch(r"[a-z0-9./-]+:[0-9][0-9.]*", v) for v in werte.values())
if len(gleich) == 1 and fest:
    print("ok     HILFSABBILD steht in %d Skripten gleich und fest: %s" % (len(werte), gleich.pop()))
else:
    print("FEHLER HILFSABBILD nicht ueberall gleich und fest: %s"
          % ", ".join("%s=%s" % (d, v) for d, v in sorted(werte.items())))
    fehler = 1
if not fehler:
    print("ok     jedes docker run in %s nimmt \"$HILFSABBILD\"" % ", ".join(dateien))
sys.exit(fehler)
PY
}

if [ "${1:-}" != "--gegenprobe" ]; then
  pruefen "$STACK"; exit $?
fi

# Gegenprobe - auf Kopien (N-34, N-60)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
GEFUNDEN=0; DURCH=""
probe() {   # probe <name> <datei> <sed-ausdruck>
  rm -rf "$T/s"; mkdir -p "$T/s/werkzeuge"
  local d; for d in $SKRIPTE; do cp "$STACK/$d" "$T/s/$d"; done
  sed -i "$3" "$T/s/$2"
  if cmp -s "$STACK/$2" "$T/s/$2"; then
    printf 'NICHT EINGEBAUT  %s\n' "$1"; DURCH="$DURCH$1; "; return
  fi
  if pruefen "$T/s" > /dev/null; then
    printf 'DURCHGERUTSCHT   %s\n' "$1"; DURCH="$DURCH$1; "
  else
    printf 'gefunden         %s\n' "$1"; GEFUNDEN=$((GEFUNDEN + 1))
  fi
}
probe "backup.sh nimmt wieder alpine ohne Fassung" backup.sh \
  's#/backup "$HILFSABBILD" \\#/backup alpine \\#'
probe "prolo nennt eine andere Fassung" werkzeuge/prolo \
  's#^HILFSABBILD="alpine:[0-9.]*"#HILFSABBILD="alpine:3.21.0"#'
probe "wiederherstellen.sh nimmt latest" werkzeuge/wiederherstellen.sh \
  's#^HILFSABBILD="alpine:[0-9.]*"#HILFSABBILD="alpine:latest"#'
probe "ein Aufruf ueber zwei Zeilen ohne Hilfsabbild" werkzeuge/wiederherstellen.sh \
  '0,/-v "$STANDORDNER\/$t":\/ein "$HILFSABBILD" \\/s##-v "$STANDORDNER/$t":/ein alpine \\#'
echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"; exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
