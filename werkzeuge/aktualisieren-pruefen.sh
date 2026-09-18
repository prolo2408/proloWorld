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
  "compose config") echo "probe:1.0.0"; exit 0 ;;
  "info ")        exit "${DOCKER_INFO_EXIT:-0}" ;;
esac
[ "$1" = "info" ] && exit "${DOCKER_INFO_EXIT:-0}"
if [ "$1" = "image" ]; then
  # KENNUNG steuert, ob sich das Abbild "geaendert" hat.
  echo "sha256:${KENNUNG:-alt}"; exit 0
fi
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
    # .State.Running liefert true/false, NICHT den Text "running". Genau
    # daran ist die Pruefung "unveraenderte Abbilder" zuerst gescheitert:
    # die Attrappe antwortete "running", alle_laufen verglich mit "true"
    # und kam nie zum Ergebnis "laeuft".
    *State.Running*) [ "$ST" = "running" ] && echo true || echo false ;;
    *State.Status*)  echo "$ST" ;;
    *Health*)        echo "$GE" ;;
    *RestartCount*)  echo "$NS" ;;
    *)               echo "$ST" ;;
  esac
fi
exit 0
STUB
chmod +x "$T/bin/docker"

# Die Rechtepruefung haengt an "id -u". Damit die Gegenprobe unabhaengig
# davon laeuft, ob sie selbst als root startet, wird id ueber eine Attrappe
# gesteuert: UID_VORGABE=0 heisst root, alles andere ein normaler Nutzer.
printf '#!/bin/bash\n[ "$1" = "-u" ] && echo "${UID_VORGABE:-0}" || exec /usr/bin/id "$@"\n' \
  > "$T/bin/id"
chmod +x "$T/bin/id"

# Fuer die Vorpruefung: age vorhanden, Schluessel gueltig.
printf '#!/bin/bash\necho "age 1.2.1"\n' > "$T/bin/age"; chmod +x "$T/bin/age"
echo "age1beispielbeispielbeispielbeispielbeispielbeispielbeispiel" \
  > "$T/stack/.backup-schluessel.pub"

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

A=$(lauf gesund)
echo "$A" | grep -q 'permission denied' && E=ja || E=nein
pruefe "Abbruchtext nennt den Rechte-Fall" "ja" "$E"
echo "$A" | grep -q 'age ist nicht installiert' && E=ja || E=nein
pruefe "Abbruchtext nennt den age-Fall" "ja" "$E"

A=$(PATH="$T/bin:$PATH" LAGE=gesund "$T/stack/werkzeuge/aktualisieren.sh" \
      --ohne-sicherung probe 2>&1)
echo "$A" | grep -q '^FERTIG' && E=ja || E=nein
pruefe "--ohne-sicherung laeuft trotz Sicherungsfehler durch" "ja" "$E"
echo "$A" | grep -q 'UEBERSPRUNGEN' && E=ja || E=nein
pruefe "--ohne-sicherung sagt deutlich, dass es uebersprungen wurde" "ja" "$E"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"

# 4c. Ohne root wird abgebrochen, bevor irgendetwas laeuft.
A=$(PATH="$T/bin:$PATH" UID_VORGABE=1000 LAGE=gesund \
      "$T/stack/werkzeuge/aktualisieren.sh" probe 2>&1 || true)
echo "$A" | grep -q 'ABBRUCH: das Skript braucht root' && E=ja || E=nein
pruefe "ohne root wird sofort abgebrochen" "ja" "$E"
echo "$A" | grep -q '\[1/4\]' && E=ja || E=nein
pruefe "und zwar BEVOR ein Tool angefasst wird" "nein" "$E"

# 4d. Die Sicherung laeuft einmal je Lauf, nicht je Tool.
printf '#!/bin/bash\necho "SICHERUNGSLAUF"\nexit 0\n' > "$T/stack/backup.sh"
chmod +x "$T/stack/backup.sh"
mkdir -p "$T/stack/zwei"
printf 'services:\n  x:\n    image: x:1\n' > "$T/stack/zwei/docker-compose.yml"
printf 'TYP="image"\nPRUEF_URL=""\nPRUEF_WARTEN=4\n' > "$T/stack/zwei/aktualisierung.conf"
rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
N=$(PATH="$T/bin:$PATH" LAGE=gesund "$T/stack/werkzeuge/aktualisieren.sh" probe zwei 2>&1 \
    | grep -c "SICHERUNGSLAUF")
pruefe "Sicherung laeuft einmal je Lauf, nicht je Tool" "1" "$N"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"

# 4e. Ein Abbild mit Kommentar dahinter darf nicht zerfallen.
mkdir -p "$T/stack/komm"
cat > "$T/stack/komm/docker-compose.yml" <<'Y'
services:
  x:
    image: ghcr.io/beispiel/ding:0.3.0   # feste Fassung, Betriebsregeln 5
Y
Z=$(PATH="$T/bin:$PATH" LAGE=gesund "$T/stack/werkzeuge/aktualisieren.sh" --trocken komm 2>&1 \
    | sed -n '/Eingetragene Fassung/,/Rueckweg/p' | grep -c '^        ')
pruefe "Abbild mit Kommentar bleibt eine Zeile" "1" "$Z"

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

# 8. Vorpruefung: leerer Schluessel wird erkannt
: > "$T/stack/.backup-schluessel.pub"
A=$(lauf gesund)
echo "$A" | grep -q 'ist LEER' && E=ja || E=nein
pruefe "leerer Sicherungsschluessel wird erkannt" "ja" "$E"
echo "$A" | grep -q 'Sicherung. laeuft' && E=ja || E=nein
pruefe "und die Sicherung startet gar nicht erst" "nein" "$E"

# 9. Vorpruefung: fehlender Schluessel, mit Anleitung statt Selbsterzeugung
rm -f "$T/stack/.backup-schluessel.pub"
A=$(lauf gesund)
echo "$A" | grep -q 'age-keygen -o ~/.age/prolo.key' && E=ja || E=nein
pruefe "fehlender Schluessel nennt den Weg auf dem Arbeitsrechner" "ja" "$E"
echo "$A" | grep -q 'NICHT erzeugt werden' && E=ja || E=nein
pruefe "und erzeugt ihn ausdruecklich NICHT selbst" "ja" "$E"
echo "age1beispielbeispielbeispielbeispielbeispielbeispielbeispiel" \
  > "$T/stack/.backup-schluessel.pub"

# 10. Vorpruefung: docker nicht erreichbar
A=$(PATH="$T/bin:$PATH" DOCKER_INFO_EXIT=1 LAGE=gesund \
      "$T/stack/werkzeuge/aktualisieren.sh" probe 2>&1 || true)
echo "$A" | grep -q 'docker antwortet nicht' && E=ja || E=nein
pruefe "docker nicht erreichbar wird vorher erkannt" "ja" "$E"

# 11. Unveraenderte Abbilder -> kein Neustart
rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
A=$(PATH="$T/bin:$PATH" KENNUNG=gleich LAGE=gesund \
      "$T/stack/werkzeuge/aktualisieren.sh" probe 2>&1)
echo "$A" | grep -q 'Keine neue Fassung' && E=ja || E=nein
pruefe "unveraenderte Abbilder fuehren nicht zum Neustart" "ja" "$E"
echo "$A" | grep -q 'FERTIG. probe ist aktuell' && E=ja || E=nein
pruefe "und werden als 'aktuell' gemeldet" "ja" "$E"
[ -f "$T/stack/probe/.stand-erfolgreich.yml" ] && E=ja || E=nein
pruefe "der Rueckweg wird auch ohne Neustart gesetzt" "ja" "$E"

# 12. Der Fall, der den ersten Entwurf entlarvt hat: nichts Neues, aber der
#     Container ist krank. "Laeuft" darf nicht "ist in Ordnung" heissen.
rm -f "$T/stack/probe/.stand-erfolgreich.yml"; fassung_setzen 1.0.0
A=$(PATH="$T/bin:$PATH" KENNUNG=gleich LAGE=krank \
      "$T/stack/werkzeuge/aktualisieren.sh" probe 2>&1 || true)
echo "$A" | grep -q 'Kein Neustart noetig' && E=ja || E=nein
pruefe "ohne neue Abbilder wird nicht neu gestartet" "ja" "$E"
echo "$A" | grep -q 'FEHLER:' && E=ja || E=nein
pruefe "aber ein kranker Container faellt trotzdem auf" "ja" "$E"
echo "$A" | grep -q 'ist aktuell' && E=ja || E=nein
pruefe "und wird NICHT als aktuell gemeldet" "nein" "$E"

# 15. Der Quellstand: erkennen, holen, und die Faelle, in denen NICHT geholt
#     werden darf. Geprueft wird werkzeuge/quellstand.sh direkt und ueber
#     aktualisieren.sh (N-38).
GIT_T="$T/gitstack"
QUELLSTAND="$HIER/quellstand.sh"
if command -v git >/dev/null 2>&1 && [ -x "$QUELLSTAND" ]; then

  # Ein "fernes" Repo mit einem Commit mehr als der Arbeitsstand.
  gitstack_bauen() {
    rm -rf "$GIT_T" "$T/fern"
    mkdir -p "$T/fern" && git -C "$T/fern" init -q -b haupt
    git -C "$T/fern" config user.email t@t; git -C "$T/fern" config user.name t
    echo eins > "$T/fern/datei"; git -C "$T/fern" add -A
    git -C "$T/fern" commit -q -m eins
    git clone -q "$T/fern" "$GIT_T"
    git -C "$GIT_T" config user.email t@t; git -C "$GIT_T" config user.name t
    echo zwei > "$T/fern/datei"; git -C "$T/fern" add -A
    git -C "$T/fern" commit -q -m "zwei - die neue Fassung"

    mkdir -p "$GIT_T/werkzeuge" "$GIT_T/probe"
    cp "$SKRIPT_UNTER_TEST" "$QUELLSTAND" "$GIT_T/werkzeuge/"
    printf '#!/bin/bash\nexit 0\n' > "$GIT_T/backup.sh"; chmod +x "$GIT_T/backup.sh"
    printf 'services:\n  probe:\n    image: probe:1.0.0\n' > "$GIT_T/probe/docker-compose.yml"
    printf 'TYP="build"\nPRUEF_URL=""\nPRUEF_WARTEN=4\n' > "$GIT_T/probe/aktualisierung.conf"
    echo "age1beispiel" > "$GIT_T/.backup-schluessel.pub"
  }
  stand() { git -C "$GIT_T" rev-parse --short HEAD; }

  # --- quellstand.sh allein -------------------------------------------
  gitstack_bauen
  A=$("$GIT_T/werkzeuge/quellstand.sh" --pruefen 2>&1); R=$?
  pruefe "hinterher: Rueckgabe 10" "10" "$R"
  echo "$A" | grep -q "1 Commit(s) HINTER origin/haupt" && E=ja || E=nein
  pruefe "hinterher: die Zahl steht in der Meldung" "ja" "$E"
  echo "$A" | grep -q "zwei - die neue Fassung" && E=ja || E=nein
  pruefe "hinterher: was bereitliegt, wird benannt" "ja" "$E"
  echo "$A" | grep -q "prolo quelle --holen" && E=ja || E=nein
  pruefe "hinterher: der Weg zum Holen steht dabei" "ja" "$E"

  Z=$("$GIT_T/werkzeuge/quellstand.sh" --kurz 2>&1); R=$?
  pruefe "--kurz: genau eine Zeile" "1" "$(printf '%s\n' "$Z" | wc -l)"
  pruefe "--kurz: Rueckgabe 10" "10" "$R"

  VORHER=$(stand)
  A=$("$GIT_T/werkzeuge/quellstand.sh" --holen 2>&1); R=$?
  pruefe "holen: Rueckgabe 20 (geholt, Neustart noetig)" "20" "$R"
  [ "$(stand)" != "$VORHER" ] && E=ja || E=nein
  pruefe "holen: der Stand hat sich wirklich bewegt" "ja" "$E"
  pruefe "holen: die geholte Fassung liegt da" "zwei" "$(cat "$GIT_T/datei")"
  A=$("$GIT_T/werkzeuge/quellstand.sh" --pruefen 2>&1); R=$?
  pruefe "danach: Rueckgabe 0" "0" "$R"
  echo "$A" | grep -q "aktuell" && E=ja || E=nein
  pruefe "danach: gilt als aktuell" "ja" "$E"

  # Eigene Aenderung an einer VERFOLGTEN Datei: nicht anfassen.
  gitstack_bauen
  echo "meine Arbeit" > "$GIT_T/datei"
  VORHER=$(stand)
  A=$("$GIT_T/werkzeuge/quellstand.sh" --holen 2>&1); R=$?
  pruefe "eigene Aenderung: Rueckgabe 1" "1" "$R"
  pruefe "eigene Aenderung: der Stand bleibt stehen" "$VORHER" "$(stand)"
  pruefe "eigene Aenderung: die Datei bleibt, wie sie war" "meine Arbeit" "$(cat "$GIT_T/datei")"
  echo "$A" | grep -q "NICHT geholt" && E=ja || E=nein
  pruefe "eigene Aenderung: es wird gesagt, dass nichts geholt wurde" "ja" "$E"

  # Eine unverfolgte Datei darf ein Vorspulen NICHT blockieren.
  gitstack_bauen
  echo notiz > "$GIT_T/mein-zettel.txt"
  A=$("$GIT_T/werkzeuge/quellstand.sh" --holen 2>&1); R=$?
  pruefe "unverfolgte Datei blockiert nicht" "20" "$R"
  pruefe "und bleibt liegen" "notiz" "$(cat "$GIT_T/mein-zettel.txt")"

  # Auseinandergelaufen: voraus UND zurueck. Da entscheidet der Mensch.
  gitstack_bauen
  echo drei > "$GIT_T/eigenes"; git -C "$GIT_T" add -A
  git -C "$GIT_T" commit -q -m "eigener Commit"
  VORHER=$(stand)
  A=$("$GIT_T/werkzeuge/quellstand.sh" --holen 2>&1); R=$?
  pruefe "auseinandergelaufen: Rueckgabe 1" "1" "$R"
  pruefe "auseinandergelaufen: der Stand bleibt stehen" "$VORHER" "$(stand)"
  echo "$A" | grep -q "auseinandergelaufen" && E=ja || E=nein
  pruefe "auseinandergelaufen: der Grund wird benannt" "ja" "$E"

  # Kein Git-Arbeitsstand: nicht pruefbar, aber kein Fehlschlag.
  mkdir -p "$T/ohnegit/werkzeuge"
  cp "$QUELLSTAND" "$T/ohnegit/werkzeuge/"
  A=$("$T/ohnegit/werkzeuge/quellstand.sh" --kurz 2>&1); R=$?
  pruefe "ohne Git: Rueckgabe 11" "11" "$R"
  echo "$A" | grep -q "nicht pruefbar" && E=ja || E=nein
  pruefe "ohne Git: sagt 'nicht pruefbar' statt etwas zu behaupten" "ja" "$E"

  # --- und ueber aktualisieren.sh --------------------------------------
  # Vorher brach der Lauf hier ab und der Mensch musste "git pull" tippen.
  # Jetzt holt das Skript selbst, startet mit dem geholten Stand neu und
  # baut dann.
  gitstack_bauen
  A=$(PATH="$T/bin:$PATH" LAGE=gesund "$GIT_T/werkzeuge/aktualisieren.sh" probe 2>&1 || true)
  echo "$A" | grep -q "Geholt: 1 Commit" && E=ja || E=nein
  pruefe "aktualisieren holt den neuen Stand selbst" "ja" "$E"
  # Nicht die ANKUENDIGUNG pruefen, sondern die TAT: ein Neustart heisst,
  # dass der Lauf von vorn beginnt - die Kopfzeile steht dann zweimal da.
  # (Die erste Fassung dieser Zeile suchte die Meldung "Neustart ..." - und
  # blieb gruen, als ich das exec zur Probe durch ein ":" ersetzte. Eine
  # Meldung ist kein Beweis.)
  pruefe "und startet wirklich neu (der Lauf beginnt zweimal)" "2" \
         "$(echo "$A" | grep -c "Tools in dieser Reihenfolge")"
  pruefe "und holt dabei genau einmal" "1" "$(echo "$A" | grep -c "Geholt: ")"
  echo "$A" | grep -q "Quellstand         aktuell" && E=ja || E=nein
  pruefe "der zweite Lauf sieht den Stand als aktuell" "ja" "$E"
  echo "$A" | grep -q "\[1/4\]" && E=ja || E=nein
  pruefe "und baut danach wirklich" "ja" "$E"
  pruefe "der geholte Inhalt liegt da" "zwei" "$(cat "$GIT_T/datei")"

  gitstack_bauen
  A=$(PATH="$T/bin:$PATH" LAGE=gesund "$GIT_T/werkzeuge/aktualisieren.sh" --ohne-holen probe 2>&1 || true)
  echo "$A" | grep -q "\[1/4\]" && E=ja || E=nein
  pruefe "--ohne-holen baut den Stand auf der Platte trotzdem" "ja" "$E"
  pruefe "--ohne-holen holt wirklich nicht" "eins" "$(cat "$GIT_T/datei")"

  gitstack_bauen
  A=$(PATH="$T/bin:$PATH" LAGE=gesund "$GIT_T/werkzeuge/aktualisieren.sh" --trocken probe 2>&1 || true)
  pruefe "--trocken holt nicht" "eins" "$(cat "$GIT_T/datei")"

  # Und der Fall, der bleiben muss: eigene Aenderung -> Abbruch, nichts gebaut.
  gitstack_bauen
  echo "meine Arbeit" > "$GIT_T/datei"
  A=$(PATH="$T/bin:$PATH" LAGE=gesund "$GIT_T/werkzeuge/aktualisieren.sh" probe 2>&1 || true)
  echo "$A" | grep -q "ABBRUCH" && E=ja || E=nein
  pruefe "eigene Aenderung: der Lauf bricht ab" "ja" "$E"
  echo "$A" | grep -q "\[1/4\]" && E=ja || E=nein
  pruefe "eigene Aenderung: und es wird nichts gebaut" "nein" "$E"
else
  echo "uebersprungen  Quellstand-Pruefung (git oder quellstand.sh fehlt)"
fi

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Alles gruen."
else
  echo "GEGENPROBE FEHLGESCHLAGEN." >&2
fi
exit "$FEHLER"
