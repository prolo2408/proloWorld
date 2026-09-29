#!/bin/bash
# werkzeuge/wiederherstellen-pruefen.sh
#
# Gegenprobe zu werkzeuge/wiederherstellen.sh (N-77).
#
# Der Kern ist kein Einzeltest, sondern ein RUNDLAUF: sichern, die Daten
# wirklich vernichten, zurueckspielen, und danach die INHALTE vergleichen.
# "Der Befehl lief durch" ist kein Beweis - geprueft wird, ob dieselben
# Bytes wieder dastehen.
#
# Docker ist gefaelscht, bewegt aber echte Archive (wie in
# prolo-pruefen.sh): ein Volume ist ein Ordner unter $VOLUMEHEIM, und
# "docker run ... tar" fuehrt wirklich tar aus. Eine Attrappe, die nur
# "exit 0" sagt, wuerde jeden Rundlauf bestehen, ohne ein Byte zu bewegen.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
FEHLER=0
S="$T/stack"; B="$T/backups"; export VOLUMEHEIM="$T/volumes"
mkdir -p "$S/werkzeuge" "$B" "$VOLUMEHEIM" "$T/bin"

pruefe() {
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}

cp "$HIER/wiederherstellen.sh" "$S/werkzeuge/"
[ -z "${PROLO_MUTATION:-}" ] || python3 "$PROLO_MUTATION" "$S/werkzeuge" || {
  echo "FEHLER Mutation liess sich nicht einbauen" >&2; exit 3; }

# --- Docker-Attrappe: bewegt echte Bytes ------------------------------
# "compose config" braucht keinen Daemon und wird darum NICHT gefaelscht,
# sondern an das echte docker durchgereicht. Eine Attrappe, die auch das
# erfindet, prueft am Ende nur sich selbst.
ECHTES_DOCKER=$(command -v docker || true)
cat > "$T/bin/docker" <<STUB
#!/bin/bash
ECHT="$ECHTES_DOCKER"
STUB
cat >> "$T/bin/docker" <<'STUB'
if [ "$1 $2" = "compose config" ] && [ -n "$ECHT" ]; then exec "$ECHT" "$@"; fi
if [ "$1 $2" = "compose stop" ] || [ "$1 $2" = "compose up" ]; then exit 0; fi
if [ "$1" = "run" ]; then
  VOL=""; EIN=""; AB=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -v) case "$2" in *:/daten) VOL="${2%%:*}" ;; *:/ein) EIN="${2%%:*}" ;;
                       *:/ab) AB="${2%%:*}" ;; esac; shift ;;
      alpine) shift; break ;;
    esac
    shift
  done
  mkdir -p "$VOLUMEHEIM/$VOL"
  if [ "$1" = "tar" ]; then           # sichern: tar czf /ab/X.tar.gz -C /daten .
    shift
    ZIEL=$(printf '%s' "$2" | sed "s|^/ab/|$AB/|")
    ( cd "$VOLUMEHEIM/$VOL" && tar czf "$ZIEL" . ) 2>/dev/null
    exit $?
  fi
  # sh -c "..." - die Pfade umbiegen und wirklich ausfuehren
  BEFEHL=$(printf '%s' "$3" | sed -e "s|/daten|$VOLUMEHEIM/$VOL|g" -e "s|/ein|$EIN|g")
  sh -c "$BEFEHL"
  exit $?
fi
exit 0
STUB
chmod +x "$T/bin/docker"
export PATH="$T/bin:$PATH"

# --- Ein Werkzeug mit Volume, Ordner, Datei und SQLite ----------------
mkdir -p "$S/probe" "$VOLUMEHEIM/probe_daten" "$S/probe/beilagen"
cat > "$S/probe/docker-compose.yml" <<'Y'
services:
  probe:
    image: probe:1
    volumes:
      - daten:/daten
volumes:
  daten:
Y
cat > "$S/probe/sicherung.conf" <<'CONF'
VOLUMES="probe_daten"
DB_CONTAINER=""
DB_USER=""
DB_NAME=""
DATEIEN="wichtig.txt"
SQLITE="probe:/daten/probe.db"
ORDNER="beilagen"
CONF

# Inhalte, die sich unterscheiden lassen
echo "ORIGINAL-VOLUME" > "$VOLUMEHEIM/probe_daten/inhalt.txt"
echo "ORIGINAL-DATEI"  > "$S/probe/wichtig.txt"
echo "ORIGINAL-BEILAGE" > "$S/probe/beilagen/b1.txt"
# Im Volume liegt die Datenbank so, wie ein tar sie erwischt - hier
# absichtlich mit ALTEM Inhalt. Die heile Kopie daneben hat den richtigen.
# So faellt auf, wenn der SQLite-Schritt gar nicht laeuft: dann gewinnt
# der alte Stand aus dem Volume, und niemand merkt es.
python3 - "$VOLUMEHEIM/probe_daten/probe.db" "VOLUME-DB-ALT" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("CREATE TABLE t(x TEXT)")
con.execute("INSERT INTO t VALUES(?)", (sys.argv[2],))
con.commit(); con.close()
PY

# --- Ein Archiv bauen, genau im Aufbau von backup.sh ------------------
STAND=2026-09-21
mkdir -p "$T/bau/$STAND/probe"
# Ein Journal MIT INS ARCHIV: so sieht es aus, wenn die Sicherung das
# Volume erwischt, waehrend geschrieben wird. Beim Einspielen kommt es
# zurueck - und passt dann nicht mehr zu der heilen Datenbank, die
# obendrauf kommt. Nur das gezielte Entfernen rettet das.
echo "JOURNAL AUS DEM ARCHIV" > "$VOLUMEHEIM/probe_daten/probe.db-wal"
( cd "$VOLUMEHEIM/probe_daten" && tar czf "$T/bau/$STAND/probe/probe_daten.tar.gz" . )
rm -f "$VOLUMEHEIM/probe_daten/probe.db-wal"
cp "$S/probe/wichtig.txt" "$T/bau/$STAND/probe/"
tar czf "$T/bau/$STAND/probe/beilagen.tar.gz" -C "$S/probe" beilagen
python3 - "$T/bau/$STAND/probe/probe.db" "ORIGINAL-DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("CREATE TABLE t(x TEXT)")
con.execute("INSERT INTO t VALUES(?)", (sys.argv[2],))
con.commit(); con.close()
PY
( cd "$T/bau" && tar czf "$B/$STAND.tar.gz" "$STAND" )

lauf() { PROLO_BACKUPS="$B" bash "$S/werkzeuge/wiederherstellen.sh" "$@" 2>&1; }

echo "=== Gegenprobe Wiederherstellen ==="

# --- 1. Die Probe: nichts anfassen ------------------------------------
A=$(lauf --probe); R=$?
pruefe "die Probe laeuft durch" "0" "$R"
printf '%s' "$A" | grep -q "Nichts angefasst" && E=ja || E=nein
pruefe "und sagt, dass sie nichts angefasst hat" "ja" "$E"
pruefe "der jetzige Stand ist unveraendert" "ORIGINAL-VOLUME" \
  "$(cat "$VOLUMEHEIM/probe_daten/inhalt.txt")"

# --- 2. Ein kaputtes Stueck muss auffallen ----------------------------
cp "$B/$STAND.tar.gz" "$T/heil.tar.gz"
mkdir -p "$T/kaputt/$STAND/probe"
cp -r "$T/bau/$STAND/probe/." "$T/kaputt/$STAND/probe/"
printf 'kein gueltiges gzip' > "$T/kaputt/$STAND/probe/probe_daten.tar.gz"
( cd "$T/kaputt" && tar czf "$B/$STAND.tar.gz" "$STAND" )
A=$(lauf --probe); R=$?
pruefe "ein kaputtes Volume-Archiv faellt auf" "1" "$R"
printf '%s' "$A" | grep -q "KAPUTT" && E=ja || E=nein
pruefe "und wird als KAPUTT benannt" "ja" "$E"

# --- 3. Eine kaputte SQLite-Datei auch --------------------------------
mkdir -p "$T/kaputtdb/$STAND/probe"
cp -r "$T/bau/$STAND/probe/." "$T/kaputtdb/$STAND/probe/"
rm -f "$T/kaputtdb/$STAND/probe/probe.db"
python3 - "$T/kaputtdb/$STAND/probe/probe.db" <<'PY'
import sqlite3, sys
p = sys.argv[1]
con = sqlite3.connect(p)
con.execute("CREATE TABLE t(x TEXT)")
for i in range(200):
    con.execute("INSERT INTO t VALUES(?)", ("zeile-%d" % i,))
con.commit(); con.close()
# Kopf und Wurzelseite bleiben heil, eine spaetere Seite nicht. Genau so
# sieht eine Datei aus, die ein tar mitten im Schreiben erwischt hat.
with open(p, "r+b") as f:
    f.seek(4096 + 100)
    f.write(b"\xff" * 400)
PY
( cd "$T/kaputtdb" && tar czf "$B/$STAND.tar.gz" "$STAND" )
A=$(lauf --probe); R=$?
pruefe "eine kaputte SQLite-Datei faellt auf" "1" "$R"

# --- 4. Ein fehlendes Stueck auch -------------------------------------
mkdir -p "$T/ohne/$STAND/probe"
cp -r "$T/bau/$STAND/probe/." "$T/ohne/$STAND/probe/"
rm "$T/ohne/$STAND/probe/wichtig.txt"
( cd "$T/ohne" && tar czf "$B/$STAND.tar.gz" "$STAND" )
A=$(lauf --probe); R=$?
pruefe "eine fehlende Pflichtdatei faellt auf" "1" "$R"
printf '%s' "$A" | grep -q "FEHLT" && E=ja || E=nein
pruefe "und wird als FEHLT benannt" "ja" "$E"

# --- 5. DER RUNDLAUF --------------------------------------------------
cp "$T/heil.tar.gz" "$B/$STAND.tar.gz"
# Jetzt wirklich alles vernichten.
echo "ZERSTOERT" > "$VOLUMEHEIM/probe_daten/inhalt.txt"
rm -f "$VOLUMEHEIM/probe_daten/probe.db"
echo "ZERSTOERT" > "$S/probe/wichtig.txt"
rm -rf "$S/probe/beilagen"
# Und ein altes -wal daneben, das nach dem Einspielen weg sein MUSS.
echo "ALTES JOURNAL" > "$VOLUMEHEIM/probe_daten/probe.db-wal"
# Dazu eine Datei, die im Archiv NICHT vorkommt. Nach dem Einspielen darf
# sie nicht mehr da sein: ein Volume wird ersetzt, nicht ergaenzt. Sonst
# ueberlebt genau das, was man loswerden wollte - eine halb
# zurueckgespielte Datenbank zum Beispiel.
echo "UEBRIGGEBLIEBEN" > "$VOLUMEHEIM/probe_daten/fremd.txt"

A=$(lauf --ja); R=$?
pruefe "der Rundlauf laeuft durch" "0" "$R"
[ "$R" -eq 0 ] || printf '%s\n' "$A" | tail -25

pruefe "das Volume ist wieder da" "ORIGINAL-VOLUME" \
  "$(cat "$VOLUMEHEIM/probe_daten/inhalt.txt" 2>/dev/null)"
pruefe "die Datei ist wieder da" "ORIGINAL-DATEI" \
  "$(cat "$S/probe/wichtig.txt" 2>/dev/null)"
pruefe "der Ordner ist wieder da" "ORIGINAL-BEILAGE" \
  "$(cat "$S/probe/beilagen/b1.txt" 2>/dev/null)"
# Der eigentliche Beweis: ORIGINAL-DB steht NUR in der Einzelkopie. Kommt
# VOLUME-DB-ALT heraus, lief der SQLite-Schritt nicht - und das Volume hat
# den Fehler verdeckt (dieselbe Falle wie N-68, N-72, N-76).
# ZUERST das Journal - und zwar, BEVOR irgendwer die Datenbank oeffnet.
#
# Das ist hier schiefgegangen: die Abfrage unten stand vorher darueber,
# und SQLite spielt beim Oeffnen ein vorhandenes -wal ein und LOESCHT es
# danach. Die Pruefzeile hat also genau den Schaden weggeraeumt, den sie
# nachweisen sollte, und war deshalb immer gruen. Ein Test, der seinen
# eigenen Beweis anfasst, misst sich selbst.
[ -e "$VOLUMEHEIM/probe_daten/probe.db-wal" ] && E=ja || E=nein
pruefe "das fremde -wal ist entfernt" "nein" "$E"
[ -e "$VOLUMEHEIM/probe_daten/fremd.txt" ] && E=ja || E=nein
pruefe "was nicht im Archiv steht, ueberlebt das Einspielen nicht" "nein" "$E"
pruefe "die eingespielte Datei ist nur fuer root lesbar" "600" \
  "$(stat -c%a "$S/probe/wichtig.txt" 2>/dev/null)"
pruefe "die heile Datenbank liegt OBEN auf dem Volume-Stand" "ORIGINAL-DB" \
  "$(python3 -c "
import sqlite3,sys
try: print(sqlite3.connect(sys.argv[1]).execute('SELECT x FROM t').fetchone()[0])
except Exception as e: print('kaputt: %s' % e)
" "$VOLUMEHEIM/probe_daten/probe.db" 2>/dev/null)"

# --- 6. Der Rueckweg aus dem Rundlauf ---------------------------------
KOPIE=$(ls -1d "$B"/.vor-wiederherstellung-* 2>/dev/null | head -1)
[ -n "$KOPIE" ] && E=ja || E=nein
pruefe "der Stand VOR der Wiederherstellung wurde weggelegt" "ja" "$E"
[ -f "$KOPIE/probe/probe_daten.tar.gz" ] && E=ja || E=nein
pruefe "und enthaelt das alte Volume" "ja" "$E"
pruefe "und zwar mit dem zerstoerten Inhalt, nicht dem neuen" "ZERSTOERT" \
  "$(tar xzOf "$KOPIE/probe/probe_daten.tar.gz" ./inhalt.txt 2>/dev/null)"

# --- 7. Ohne Bestaetigung passiert nichts -----------------------------
echo "WIEDER-ZERSTOERT" > "$VOLUMEHEIM/probe_daten/inhalt.txt"
A=$(lauf < /dev/null); R=$?
pruefe "ohne Terminal und ohne --ja wird abgebrochen" "1" "$R"
pruefe "und es wurde nichts angefasst" "WIEDER-ZERSTOERT" \
  "$(cat "$VOLUMEHEIM/probe_daten/inhalt.txt")"

# --- 8. Verschluesselt: ohne Schluessel geht nichts, mit schon --------
if command -v age >/dev/null 2>&1; then
  age-keygen -o "$T/schluessel.key" 2>/dev/null
  grep -o 'age1[a-z0-9]*' "$T/schluessel.key" | head -1 > "$T/schluessel.pub"
  age -R "$T/schluessel.pub" -o "$B/$STAND.tar.gz.age" < "$T/heil.tar.gz"
  rm -f "$B/$STAND.tar.gz"
  A=$(lauf --probe); R=$?
  pruefe "ein verschluesseltes Archiv ohne Schluessel wird abgelehnt" "1" "$R"
  printf '%s' "$A" | grep -q "Arbeitsrechner" && E=ja || E=nein
  pruefe "und die Meldung sagt, wo der Schluessel liegt" "ja" "$E"
  A=$(lauf --probe --schluessel "$T/schluessel.key"); R=$?
  pruefe "mit Schluessel laeuft die Probe durch" "0" "$R"
  A=$(lauf --probe --schluessel "$T/schluessel.pub"); R=$?
  pruefe "mit dem FALSCHEN Schluessel nicht" "1" "$R"
else
  echo "uebersprungen  age fehlt"
fi

# --- 8b. Ein Archiv ohne ein einziges brauchbares Werkzeug -----------
# "Nichts zu tun" ist kein Erfolg. Genau das hat dieser Befehl beim
# Bauen gemeldet - "vollstaendig und lesbar" ueber einen leeren Plan.
rm -f "$B"/*.tar.gz.age
mkdir -p "$T/fremd/$STAND/gibtsnichtmehr"
echo x > "$T/fremd/$STAND/gibtsnichtmehr/irgendwas"
( cd "$T/fremd" && tar czf "$B/$STAND.tar.gz" "$STAND" )
A=$(lauf --probe); R=$?
pruefe "ein Werkzeug ohne sicherung.conf ist ein Fehler" "1" "$R"
printf '%s' "$A" | grep -q "OHNE-CONF" && E=ja || E=nein
pruefe "und wird als OHNE-CONF benannt" "ja" "$E"

# Und der andere Fall: ueberhaupt kein Werkzeug im Archiv. "Nichts zu tun"
# ist kein Erfolg - genau das hat dieser Befehl beim Bauen gemeldet.
rm -rf "$T/leer"; mkdir -p "$T/leer/$STAND"
( cd "$T/leer" && tar czf "$B/$STAND.tar.gz" "$STAND" )
A=$(lauf --probe); R=$?
pruefe "ein Archiv ganz ohne Werkzeug ist ein Fehler" "1" "$R"
printf '%s' "$A" | grep -q "nichts, was sich zurueckspielen liesse" && E=ja || E=nein
pruefe "und sagt das auch" "ja" "$E"
cp "$T/heil.tar.gz" "$B/$STAND.tar.gz"

# --- 8c. Ein Werkzeug, das es hier nicht mehr gibt (N-87) -------------
# Der Fall nach einem Serververlust: "prolo neu" hat es angelegt, im Git
# stand es nie. Die Sicherung hat seinen Ordner - der wird angelegt. Und
# ein VORHANDENER Ordner wird dabei nie ueberschrieben (§15).
mkdir -p "$T/neuling/$STAND/neuling" "$T/neuling/$STAND/probe" "$T/nbau/neuling"
cp -r "$T/bau/$STAND/probe/." "$T/neuling/$STAND/probe/"
printf 'services:\n  neuling:\n    image: neu:1\n' > "$T/nbau/neuling/docker-compose.yml"
printf 'VOLUMES=""\nDATEIEN="notiz.txt"\nORDNER=""\nSQLITE=""\n' > "$T/nbau/neuling/sicherung.conf"
tar czf "$T/neuling/$STAND/neuling/werkzeug.tar.gz" -C "$T/nbau" neuling
echo "NOTIZ-AUS-DER-SICHERUNG" > "$T/neuling/$STAND/neuling/notiz.txt"
# Und fuer probe einen Ordnerstand, der NICHT gewinnen darf:
mkdir -p "$T/pbau/probe"
printf 'services:\n  probe:\n    image: ALT-AUS-DER-SICHERUNG:1\n' > "$T/pbau/probe/docker-compose.yml"
cp "$S/probe/sicherung.conf" "$T/pbau/probe/"
tar czf "$T/neuling/$STAND/probe/werkzeug.tar.gz" -C "$T/pbau" probe
( cd "$T/neuling" && tar czf "$B/$STAND.tar.gz" "$STAND" )
rm -rf "$S/neuling"

A=$(lauf --probe); R=$?
pruefe "fehlendes Werkzeug: die Probe laeuft durch (N-87)" "0" "$R"
printf '%s' "$A" | grep -q "wird beim Einspielen angelegt: neuling" && E=ja || E=nein
pruefe "fehlendes Werkzeug: die Probe sagt, dass es angelegt wird" "ja" "$E"
[ -e "$S/neuling" ] && E=ja || E=nein
pruefe "fehlendes Werkzeug: die Probe legt NICHTS an" "nein" "$E"

A=$(lauf --ja); R=$?
pruefe "fehlendes Werkzeug: das Einspielen laeuft durch" "0" "$R"
[ "$R" -eq 0 ] || printf '%s\n' "$A" | tail -15
pruefe "fehlendes Werkzeug: seine Compose-Datei ist wieder da" "ja" \
  "$(grep -q 'image: neu:1' "$S/neuling/docker-compose.yml" 2>/dev/null && echo ja || echo nein)"
pruefe "fehlendes Werkzeug: und seine Daten auch" "NOTIZ-AUS-DER-SICHERUNG" \
  "$(cat "$S/neuling/notiz.txt" 2>/dev/null)"
pruefe "ein vorhandener Ordner wird NICHT ueberschrieben" "nein" \
  "$(grep -q 'ALT-AUS-DER-SICHERUNG' "$S/probe/docker-compose.yml" && echo ja || echo nein)"
cp "$T/heil.tar.gz" "$B/$STAND.tar.gz"

# --- 9. Ein Stand, den es nicht gibt ----------------------------------
A=$(lauf --probe --stand 1999-01-01); R=$?
pruefe "ein unbekannter Stand ist ein Fehler, nicht der neueste" "1" "$R"
printf '%s' "$A" | grep -q "Vorhanden sind" && E=ja || E=nein
pruefe "und es wird gezeigt, welche es gibt" "ja" "$E"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "GEGENPROBE FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
