#!/bin/bash
# werkzeuge/aktualisieren-pruefen.sh
#
# Gegenprobe fuer aktualisieren.sh. Baut einen Stack aus Attrappen auf und
# faelscht "docker" auf dem PATH, damit jeder Zustand herstellbar ist -
# gesund, krank, Dauerneustart, tot.
#
# Der Grund fuer dieses Skript: die beiden Fehler, die im Entwurf aus
# Betriebsregeln 20 steckten, waren beide nur im Ablauf zu sehen, nicht beim
# Lesen. Ohne ausgefuehrte Probe faellt so etwas erst im Ernstfall auf - und
# das ist genau der Moment, in dem man sich darauf verlassen wollte.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKRIPT_UNTER_TEST="$HIER/aktualisieren.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

FEHLER=0
pruefe() {
  local name="$1" erwartet="$2" ist="$3"
  if [ "$ist" = "$erwartet" ]; then
    printf 'ok     %s\n' "$name"
  else
    printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$name" "$erwartet" "$ist"
    FEHLER=1
  fi
}

# --- Attrappen-Stack aufbauen -------------------------------------------
mkdir -p "$T/bin" "$T/stack/werkzeuge" "$T/stack/probe"
cp "$SKRIPT_UNTER_TEST" "$T/stack/werkzeuge/"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"
printf 'TYP="image"\nPRUEF_URL=""\nPRUEF_WARTEN=4\n' > "$T/stack/probe/aktualisierung.conf"

fassung_setzen() {
  cat > "$T/stack/probe/docker-compose.yml" <<Y
services:
  probe:
    image: probe:$1
    container_name: probe
Y
}
fassung_jetzt() { grep 'image:' "$T/stack/probe/docker-compose.yml" | tr -d ' '; }

cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
case "$1 $2" in
  "compose ps")   echo "c1"; exit 0 ;;
  "compose logs") exit 0 ;;
  "compose pull"|"compose up"|"compose build") exit 0 ;;
esac
if [ "$1" = "inspect" ]; then
  FMT="${*: -1}"
  case "$LAGE" in
    gesund)   ST=running; GE=healthy;   NS=0 ;;
    krank)    ST=running; GE=unhealthy; NS=0 ;;
    startet)  ST=running; GE=starting;  NS=0 ;;
    neustart) ST=running; GE=healthy;   NS=7 ;;
    tot)      ST=exited;  GE=ohne;      NS=0 ;;
  esac
  case "$FMT" in
    *Name*)          echo "/probe" ;;
    *State.Status*)  echo "$ST" ;;
    *Health*)        echo "$GE" ;;
    *RestartCount*)  echo "$NS" ;;
    *)               echo "$ST" ;;
  esac
fi
exit 0
STUB
chmod +x "$T/bin/docker"

lauf() { PATH="$T/bin:$PATH" LAGE="$1" "$T/stack/werkzeuge/aktualisieren.sh" probe 2>&1; }

echo "=== Gegenprobe aktualisieren.sh ==="

# 1. Zustaende
fassung_setzen 1.0.0
echo "$(lauf gesund)" | grep -q '^FERTIG' && E=ja || E=nein
pruefe "gesunder Container gilt als Erfolg" "ja" "$E"

for lage in krank startet tot; do
  rm -f "$T/stack/probe/.stand-erfolgreich.yml"
  fassung_setzen 1.0.0
  echo "$(lauf "$lage")" | grep -q 'FEHLER:' && E=ja || E=nein
  pruefe "Zustand '$lage' gilt als Fehlschlag" "ja" "$E"
done

rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
echo "$(lauf neustart)" | grep -q 'startet staendig neu' && E=ja || E=nein
pruefe "Dauerneustart wird benannt" "ja" "$E"

# 2. Erfolg darf nicht die volle Wartezeit brauchen
rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
S=$(date +%s); lauf gesund >/dev/null; D=$(( $(date +%s) - S ))
[ "$D" -lt 4 ] && E=ja || E=nein
pruefe "Erfolg wartet nicht die vollen 4s (gebraucht: ${D}s)" "ja" "$E"

# 3. Der Kern: Rueckweg kommt vom letzten ERFOLG, nicht vom Stand beim Start.
#    Genau hier lag der Fehler im Entwurf aus Betriebsregeln 20.
rm -f "$T/stack/probe/.stand-erfolgreich.yml"
fassung_setzen 1.0.0
lauf gesund >/dev/null                      # Lauf 1: Erfolg, legt Rueckweg an
fassung_setzen 2.0.0                        # Nutzer traegt neue Fassung ein
lauf krank >/dev/null                       # Lauf 2: scheitert
pruefe "Fehlschlag rollt auf die letzte erfolgreiche Fassung zurueck" \
       "image:probe:1.0.0" "$(fassung_jetzt)"

# 4. Ohne vorherigen Erfolg wird die Datei NICHT angefasst
rm -f "$T/stack/probe/.stand-erfolgreich.yml"
fassung_setzen 3.0.0
lauf krank >/dev/null
pruefe "ohne Rueckweg bleibt die docker-compose.yml unveraendert" \
       "image:probe:3.0.0" "$(fassung_jetzt)"

# 4b. Scheiternde Sicherung bricht ab - und --ohne-sicherung geht daran vorbei.
#     Das ist der Fall "kein age-Schluessel": backup.sh endet mit 1, obwohl
#     die Sicherung geschrieben wurde.
printf '#!/bin/bash\nexit 1\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"
rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
echo "$(lauf gesund)" | grep -q 'ABBRUCH: die Sicherung endete' && E=ja || E=nein
pruefe "scheiternde Sicherung bricht ab" "ja" "$E"

echo "$(lauf gesund)" | grep -q 'age-Schluessel' && E=ja || E=nein
pruefe "Abbruchtext nennt den haeufigsten Grund" "ja" "$E"

A=$(PATH="$T/bin:$PATH" LAGE=gesund "$T/stack/werkzeuge/aktualisieren.sh" \
      --ohne-sicherung probe 2>&1)
echo "$A" | grep -q '^FERTIG' && E=ja || E=nein
pruefe "--ohne-sicherung laeuft trotz Sicherungsfehler durch" "ja" "$E"
echo "$A" | grep -q 'UEBERSPRUNGEN' && E=ja || E=nein
pruefe "--ohne-sicherung sagt deutlich, dass es uebersprungen wurde" "ja" "$E"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"

# 5. Fehlende image:-Zeile bricht ab (B-23)
cat > "$T/stack/probe/docker-compose.yml" <<'Y'
services:
  probe:
    build: .
Y
echo "$(lauf gesund)" | grep -q 'fehlt eine image:-Zeile' && E=ja || E=nein
pruefe "ohne image:-Zeile wird abgebrochen" "ja" "$E"

# 6. Mehrere Dienste: ALLE Abbilder werden erfasst, nicht nur das erste
mkdir -p "$T/stack/mehr"
cat > "$T/stack/mehr/docker-compose.yml" <<'Y'
services:
  db:
    image: postgres:16.10-alpine
  server:
    image: server:2026.8.2
Y
A=$(PATH="$T/bin:$PATH" LAGE=gesund "$T/stack/werkzeuge/aktualisieren.sh" --trocken mehr 2>&1 \
    | grep -c -E '^ {8}(postgres|server):')
pruefe "mehrere Dienste werden alle erfasst" "2" "$A"

# 7. Reihenfolge: socket-proxy vor traefik vor authentik
for t in socket-proxy traefik authentik spaeter; do
  mkdir -p "$T/stack/$t"; printf 'services:\n  x:\n    image: x:1\n' > "$T/stack/$t/docker-compose.yml"
done
R=$(PATH="$T/bin:$PATH" "$T/stack/werkzeuge/aktualisieren.sh" --alle --trocken 2>&1 \
    | grep -m1 'Tools in dieser Reihenfolge' | sed 's/.*: //')
case "$R" in
  "socket-proxy traefik authentik"*) E=ja ;;
  *) E="nein ($R)" ;;
esac
pruefe "Abhaengigkeitsreihenfolge wird erzwungen" "ja" "$E"

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Alles gruen."
else
  echo "GEGENPROBE FEHLGESCHLAGEN." >&2
fi
exit "$FEHLER"
