#!/bin/bash
# Prueft, dass ALLE Tools byteweise dieselben Schriften ausliefern (B-19).
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

# Die Tools finden sich selbst: jeder Ordner mit einem schriften/. Eine
# feste Liste haette das naechste Tool uebersehen - genau das ist beim
# Anlegen von www/ beinahe passiert.
TOOLS=$(for D in */schriften; do [ -d "$D" ] && dirname "$D"; done | sort)
ERSTES=$(echo "$TOOLS" | head -1)
echo "Verglichen wird gegen $ERSTES:$(echo "$TOOLS" | tr '\n' ' ')"
if [ "$(echo "$TOOLS" | grep -c .)" -lt 2 ]; then
  echo "FEHLER  weniger als zwei Tools mit Schriften - nichts zu vergleichen" >&2
  FEHLER=1
fi

for DATEI in $ERWARTET; do
  A="$ERSTES/schriften/$DATEI"
  if [ ! -f "$A" ]; then echo "FEHLT   $A" >&2; FEHLER=1; continue; fi
  GLEICH=1
  for TOOL in $TOOLS; do
    B="$TOOL/schriften/$DATEI"
    if [ ! -f "$B" ]; then
      echo "FEHLT   $B" >&2; FEHLER=1; GLEICH=0; continue
    fi
    if ! cmp -s "$A" "$B"; then
      echo "UNGLEICH $TOOL/schriften/$DATEI - andere Fassung als $ERSTES" >&2
      FEHLER=1; GLEICH=0
    fi
  done
  [ "$GLEICH" -eq 1 ] && printf "gleich  %-28s %8d Bytes\n" "$DATEI" "$(wc -c < "$A")"
done

# Jede @font-face-Regel muss auf eine Datei zeigen, die es gibt.
for TOOL in $TOOLS; do
  # Wo die Oberflaeche steht, ist je Tool verschieden: index.html bei Wiki
  # und Bordbuch, im server.py bei www. Gesucht wird darum in beidem.
  for QUELLE in "$TOOL/index.html" "$TOOL/server.py"; do
    [ -f "$QUELLE" ] || continue
    while read -r NAME; do
      [ -z "$NAME" ] && continue
      if [ ! -f "$TOOL/schriften/$NAME" ]; then
        echo "FEHLER  $QUELLE verweist auf schriften/$NAME - die Datei fehlt" >&2
        FEHLER=1
      fi
    done < <(grep -oE "/schriften/[a-zA-Z0-9._-]+" "$QUELLE" \
             | sed -E "s|/schriften/||" | sort -u)
  done
done

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Beide Tools liefern dieselben Schriften aus, und jede Regel hat ihre Datei."
else
  echo "SCHRIFTEN-PRUEFUNG FEHLGESCHLAGEN." >&2
fi
exit "$FEHLER"
