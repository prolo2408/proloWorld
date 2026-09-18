#!/bin/bash
# Prueft, dass beide Tools byteweise dieselben Schriften ausliefern (B-19).
#
# CLAUDE.md verlangt, dass die Tools als Familie erkennbar sind. Wenn
# Bordbuch und Wiki verschiedene Schriftfassungen ausliefern, fliegt das
# niemandem auf - man sieht es erst, wenn zwei Fenster nebeneinander stehen.
#
# B-31 hat gezeigt, wie schnell zwei Kopien derselben Datei auseinanderlaufen:
# 6394 Zeilen mit drei Unterschieden waren nach wenigen Aenderungen um 314
# Zeilen verschieden. Darum diese Pruefung, statt sich darauf zu verlassen.
#
# Aufruf:  ./werkzeuge/schriften-pruefen.sh
set -u
cd "$(dirname "$0")/.."

ERWARTET="instrument-latin.woff2 instrument-latin-ext.woff2 jetbrains-latin.woff2
jetbrains-latin-ext.woff2 sora-latin.woff2 sora-latin-ext.woff2
OFL-sora.txt OFL-instrument.txt OFL-jetbrains.txt"

FEHLER=0

for DATEI in $ERWARTET; do
  A="bordbuch/schriften/$DATEI"
  B="wiki/schriften/$DATEI"
  if [ ! -f "$A" ]; then echo "FEHLT   $A" >&2; FEHLER=1; continue; fi
  if [ ! -f "$B" ]; then echo "FEHLT   $B" >&2; FEHLER=1; continue; fi
  if cmp -s "$A" "$B"; then
    printf "gleich  %-28s %8d Bytes\n" "$DATEI" "$(wc -c < "$A")"
  else
    echo "UNGLEICH $DATEI - die Tools liefern verschiedene Fassungen aus" >&2
    FEHLER=1
  fi
done

# Jede @font-face-Regel muss auf eine Datei zeigen, die es gibt.
for TOOL in bordbuch wiki; do
  while read -r NAME; do
    [ -z "$NAME" ] && continue
    if [ ! -f "$TOOL/schriften/$NAME" ]; then
      echo "FEHLER  $TOOL/index.html verweist auf schriften/$NAME - die Datei fehlt" >&2
      FEHLER=1
    fi
  done < <(grep -oE "url\('/schriften/[^']+'\)" "$TOOL/index.html" \
           | sed -E "s|url\('/schriften/||; s|'\)||" | sort -u)
done

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Beide Tools liefern dieselben Schriften aus, und jede Regel hat ihre Datei."
else
  echo "SCHRIFTEN-PRUEFUNG FEHLGESCHLAGEN." >&2
fi
exit "$FEHLER"
