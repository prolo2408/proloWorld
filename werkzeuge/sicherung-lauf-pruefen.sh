#!/bin/bash
# werkzeuge/sicherung-lauf-pruefen.sh
#
# Ablaufprobe fuer backup.sh (N-86). sicherung-pruefen.sh prueft, OB alles
# in einer sicherung.conf steht; dieses Skript prueft, was backup.sh mit
# dem Archiv TUT - vor allem an einem Tag mit mehr als einem Lauf.
#
# Der Anlass: "prolo aktualisieren" sichert vor jedem Lauf. Ging der
# zweite Lauf eines Tages schief, ersetzte sein halbes Archiv das
# vollstaendige vom Morgen.
#
# Gearbeitet wird in einem Wegwerfordner, mit einer Docker-Attrappe und
# dem echten age. Die Pfade setzt backup.sh aus PROLO_STACK,
# PROLO_SICHERUNGEN und PROLO_BESITZER.
#
#   ./werkzeuge/sicherung-lauf-pruefen.sh
#   ./werkzeuge/sicherung-lauf-pruefen.sh --gegenprobe
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WURZEL="$(dirname "$HIER")"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
S="$T/stack"; B="$T/backups"
FEHLER=0

pruefe() {
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}

command -v age >/dev/null 2>&1 && command -v age-keygen >/dev/null 2>&1 || {
  # Kein Ueberspringen: ein uebersprungener Test ist kein gruener Test.
  echo "FEHLER age/age-keygen fehlt - ohne das laesst sich die Sicherung nicht pruefen" >&2
  exit 1
}

# --- Wegwerfstack ---------------------------------------------------------
mkdir -p "$S/werkzeuge" "$S/dbtool" "$T/bin" "$B"
cp "$WURZEL/backup.sh" "$S/backup.sh"
# Einstieg fuer die Mutationsprobe: ein sed-Ausdruck auf die KOPIE (N-34).
[ -z "${SICHERUNG_MUTATION:-}" ] || sed -i "$SICHERUNG_MUTATION" "$S/backup.sh"

printf 'VOLUMES=""\nDB_CONTAINER="db"\nDB_USER="u"\nDB_NAME="n"\n' > "$S/dbtool/sicherung.conf"
printf 'DATEIEN="eine.conf"\nORDNER=""\nSQLITE=""\nHINWEIS=""\n' >> "$S/dbtool/sicherung.conf"
echo "inhalt" > "$S/dbtool/eine.conf"

age-keygen -o "$T/geheim.key" 2>/dev/null
grep '^# public key:' "$T/geheim.key" | cut -d' ' -f4 > "$S/.backup-schluessel.pub"

# Docker-Attrappe: nur pg_dump wird gebraucht. PG_KAPUTT=1 laesst es
# scheitern, wie ein Datenbankcontainer, der gerade neu startet.
cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
if [ "$1" = exec ] && [ "$3" = pg_dump ]; then
  [ "${PG_KAPUTT:-0}" = 1 ] && { echo "pg_dump: connection refused" >&2; exit 1; }
  echo "-- SQL-Stand ${PG_STAND:-1}"; exit 0
fi
exit 0
STUB
chmod +x "$T/bin/docker"

D=$(date +%Y-%m-%d)
lauf() {
  PATH="$T/bin:$PATH" PROLO_STACK="$S" PROLO_SICHERUNGEN="$B" \
    PROLO_BESITZER="$(id -un)" bash "$S/backup.sh" > "$T/ausgabe" 2>&1
}
pruefsumme() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
inhalt() {     # Liste der Dateien in einem Archiv
  age -d -i "$T/geheim.key" "$1" | tar tzf - | sort
}
datei_aus() {  # $1 Archiv, $2 Pfad darin
  age -d -i "$T/geheim.key" "$1" | tar xzOf - "$2" 2>/dev/null | gzip -dc 2>/dev/null
}

echo "=== Ablaufprobe backup.sh ==="

# 1. Ein guter Lauf ------------------------------------------------------
PG_STAND=morgen lauf; R=$?
pruefe "guter Lauf: Rueckgabe 0" "0" "$R"
pruefe "guter Lauf: das Archiv des Tages liegt da" "ja" \
  "$([ -f "$B/$D.tar.gz.age" ] && echo ja || echo nein)"
pruefe "guter Lauf: der Erfolgsvermerk ist gesetzt" "ja" \
  "$([ -f "$B/.letzter-erfolg" ] && echo ja || echo nein)"
MORGEN=$(pruefsumme "$B/$D.tar.gz.age")

# 2. Derselbe Tag, der Lauf scheitert (N-86) -----------------------------
rm -f "$B/.letzter-erfolg"
PG_KAPUTT=1 lauf; R=$?
pruefe "halber Lauf: Rueckgabe 1" "1" "$R"
pruefe "halber Lauf: das Archiv vom Morgen ist UNVERAENDERT" "$MORGEN" \
  "$(pruefsumme "$B/$D.tar.gz.age")"
DANEBEN=$(ls "$B"/"$D"-unvollstaendig-*.tar.gz.age 2>/dev/null | head -1)
pruefe "halber Lauf: sein Archiv liegt daneben, nicht darueber" "1" \
  "$(ls "$B"/"$D"-unvollstaendig-*.tar.gz.age 2>/dev/null | grep -c .)"
pruefe "halber Lauf: der Morgen hat noch seine Datenbank" "-- SQL-Stand morgen" \
  "$(datei_aus "$B/$D.tar.gz.age" "$D/dbtool/datenbank.sql.gz")"
if [ -n "$DANEBEN" ]; then
  pruefe "halber Lauf: KEINE leere Datenbankdatei im halben Archiv" "nein" \
    "$(inhalt "$DANEBEN" | grep -q 'datenbank.sql.gz' && echo ja || echo nein)"
  pruefe "halber Lauf: was ging, ist trotzdem drin" "ja" \
    "$(inhalt "$DANEBEN" | grep -q "$D/dbtool/eine.conf" && echo ja || echo nein)"
fi
pruefe "halber Lauf: kein Erfolgsvermerk" "nein" \
  "$([ -f "$B/.letzter-erfolg" ] && echo ja || echo nein)"
grep -q "UNVOLLSTAENDIG" "$T/ausgabe" && E=ja || E=nein
pruefe "halber Lauf: sagt, dass er daneben liegt" "ja" "$E"

# Welchen Stand nimmt "prolo wiederherstellen" ohne --stand? Dieselbe
# Regel wie in wiederherstellen.sh: der letzte nach Sortierung.
pruefe "ohne --stand gilt weiter der vollstaendige" "$D.tar.gz.age" \
  "$(ls -1 "$B"/*.tar.gz.age | sort | tail -1 | xargs basename)"

# 3. Ein guter Lauf danach ersetzt den Stand des Tages ------------------
PG_STAND=abend lauf; R=$?
pruefe "guter Lauf danach: Rueckgabe 0" "0" "$R"
pruefe "guter Lauf danach: ersetzt den Stand des Tages" "-- SQL-Stand abend" \
  "$(datei_aus "$B/$D.tar.gz.age" "$D/dbtool/datenbank.sql.gz")"

# 4. Ein neuer Tag, und der erste Lauf scheitert -------------------------
#    Dann wird er der Stand des Tages - besser als gar keiner.
rm -f "$B"/*.tar.gz.age
PG_KAPUTT=1 lauf; R=$?
pruefe "erster Lauf scheitert: Rueckgabe 1" "1" "$R"
pruefe "erster Lauf scheitert: wird trotzdem der Stand des Tages" "ja" \
  "$([ -f "$B/$D.tar.gz.age" ] && echo ja || echo nein)"
pruefe "erster Lauf scheitert: kein zweites Archiv daneben" "0" \
  "$(ls "$B"/"$D"-unvollstaendig-*.tar.gz.age 2>/dev/null | grep -c .)"
pruefe "kein halbfertiges .neu bleibt liegen" "0" \
  "$(ls -A "$B" | grep -c '\.neu$')"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "ABLAUFPROBE FEHLGESCHLAGEN." >&2; fi

# --- Mutationsprobe (§13a) -------------------------------------------------
if [ "${1:-}" = "--gegenprobe" ] && [ -z "${SICHERUNG_MUTATION:-}" ]; then
  echo
  echo "=== Mutationsprobe ==="
  DURCH=0; N=0
  while IFS='|' read -r NAME AUSDRUCK; do
    [ -n "$NAME" ] || continue
    N=$((N + 1))
    # Die Mutation muss sich auch einbauen lassen - sonst waere "gefunden"
    # nur ein unveraendertes Skript, das zufaellig rot ist.
    cp "$WURZEL/backup.sh" "$T/probe.sh"; sed -i "$AUSDRUCK" "$T/probe.sh"
    if cmp -s "$WURZEL/backup.sh" "$T/probe.sh"; then
      printf 'ABBRUCH   %s (Mutation liess sich nicht einbauen)\n' "$NAME"
      DURCH=$((DURCH + 1)); continue
    fi
    if SICHERUNG_MUTATION="$AUSDRUCK" bash "$0" >/dev/null 2>&1; then
      printf 'ENTWISCHT %s  <-- Testluecke\n' "$NAME"; DURCH=$((DURCH + 1))
    else
      printf 'gefunden  %s\n' "$NAME"
    fi
  done <<'MUT'
ein halber Lauf ueberschreibt den Stand des Tages (N-86)|s/if \[ "\$FEHLER" -ne 0 \] \&\& \[ -f "\$ARCHIV" \]; then/if false; then/
eine gescheiterte Datenbanksicherung bleibt als leere Datei liegen|s/^      rm -f "\$ZIEL\/\$TOOL\/datenbank.sql.gz"$/      :/
das halbe Archiv sortiert hinter den vollstaendigen|s/\$DATUM-unvollstaendig-/$DATUM.zz-unvollstaendig-/
ein guter Lauf ersetzt den Stand des Tages nicht|s/^      mv "\$NEU" "\$ARCHIV"$/      [ -f "$ARCHIV" ] || mv "$NEU" "$ARCHIV"/
MUT
  echo "gefunden: $((N - DURCH))   entwischt: $DURCH"
  [ "$DURCH" -eq 0 ] || exit 1
fi
exit "$FEHLER"
