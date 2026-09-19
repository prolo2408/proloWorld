#!/bin/bash
# werkzeuge/prolo-pruefen.sh
#
# Gegenprobe fuer prolo. Baut einen Attrappen-Stack auf und faelscht docker
# auf dem PATH. Geprueft wird vor allem der Lebenszyklus, bei dem etwas
# kaputtgehen KANN: anlegen, entfernen ins Archiv, zurueckholen.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
FEHLER=0

pruefe() {
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}

mkdir -p "$T/bin" "$T/stack/werkzeuge"
cp "$HIER/prolo" "$T/stack/werkzeuge/"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"
printf '#!/bin/bash\n[ "$1" = "-u" ] && echo "${UID_VORGABE:-0}" || exec /usr/bin/id "$@"\n' \
  > "$T/bin/id"; chmod +x "$T/bin/id"

# docker-Attrappe: tar-Aufrufe fuer Volumes echt ausfuehren, damit das
# Zurueckholen wirklich Daten bewegt und nicht nur so tut.
cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
case "$1 $2" in
  "compose ps")   echo "c1"; exit 0 ;;
  "compose down"|"compose up"|"compose restart"|"compose logs") exit 0 ;;
esac
if [ "$1" = "inspect" ]; then echo true; exit 0; fi
if [ "$1" = "volume" ]; then exit 0; fi
if [ "$1" = "run" ]; then
  # -v <volume>:/daten -v <ziel>:/ab alpine <befehl...>
  VOL=""; AB=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -v) case "$2" in *:/daten) VOL="${2%%:*}" ;; *:/ab) AB="${2%%:*}" ;; esac; shift ;;
      alpine) shift; break ;;
    esac
    shift
  done
  mkdir -p "$VOLUMEHEIM/$VOL"
  if [ "$1" = "tar" ]; then
    shift; ( cd "$VOLUMEHEIM/$VOL" && tar czf "$AB/$(basename "$2")" . ) 2>/dev/null
  else
    # sh -c "cd /daten && tar xzf '/ab/<datei>'"
    D=$(printf '%s' "$*" | sed "s|.*/ab/||; s|'.*||")
    ( cd "$VOLUMEHEIM/$VOL" && tar xzf "$AB/$D" ) 2>/dev/null
  fi
  exit 0
fi
exit 0
STUB
chmod +x "$T/bin/docker"
export VOLUMEHEIM="$T/volumes"
mkdir -p "$VOLUMEHEIM"

prolo() { PATH="$T/bin:$PATH" "$T/stack/werkzeuge/prolo" "$@"; }

echo "=== Gegenprobe prolo ==="

# 1. Anlegen
printf 'nginx:1.27-alpine\n8080\n' | prolo neu pdfeditor >/dev/null 2>&1
[ -f "$T/stack/pdfeditor/docker-compose.yml" ] && E=ja || E=nein
pruefe "neu legt die docker-compose.yml an" "ja" "$E"
[ -f "$T/stack/pdfeditor/sicherung.conf" ] && E=ja || E=nein
pruefe "und die sicherung.conf (damit ist es im Backup)" "ja" "$E"
[ -f "$T/stack/pdfeditor/aktualisierung.conf" ] && E=ja || E=nein
pruefe "und die aktualisierung.conf" "ja" "$E"

grep -q 'authentik@file' "$T/stack/pdfeditor/docker-compose.yml" && E=ja || E=nein
pruefe "das Geruest haengt Authentik davor" "ja" "$E"
grep -q 'cap_drop' "$T/stack/pdfeditor/docker-compose.yml" && E=ja || E=nein
pruefe "und setzt die Grenzen aus CLAUDE.md §19" "ja" "$E"
grep -qE '^\s+ports:' "$T/stack/pdfeditor/docker-compose.yml" && E=ja || E=nein
pruefe "und oeffnet KEINEN Port am Host" "nein" "$E"
python3 -c "import yaml,sys; yaml.safe_load(open('$T/stack/pdfeditor/docker-compose.yml'))" 2>/dev/null \
  && E=ja || E=nein
pruefe "die erzeugte YAML ist gueltig" "ja" "$E"

# 2. latest und fehlende Fassung werden abgelehnt
A=$(printf 'nginx:latest\n8080\n' | prolo neu mitlatest 2>&1)
echo "$A" | grep -q "latest" && E=ja || E=nein
pruefe "'latest' wird abgelehnt" "ja" "$E"
[ -e "$T/stack/mitlatest" ] && E=ja || E=nein
pruefe "und es entsteht kein halbes Tool" "nein" "$E"

A=$(printf 'nginx\n8080\n' | prolo neu ohnefassung 2>&1)
echo "$A" | grep -q "Ohne Fassung" && E=ja || E=nein
pruefe "Abbild ohne Fassung wird abgelehnt" "ja" "$E"

A=$(prolo neu "Gross Falsch" 2>&1)
echo "$A" | grep -q "Kleinbuchstaben" && E=ja || E=nein
pruefe "unerlaubter Name wird abgelehnt" "ja" "$E"

# 3. Entfernen legt ins Archiv statt zu loeschen
mkdir -p "$VOLUMEHEIM/pdfeditor_pdfeditor_daten"
echo "wichtige daten" > "$VOLUMEHEIM/pdfeditor_pdfeditor_daten/inhalt.txt"
prolo entfernen pdfeditor >/dev/null 2>&1
[ -e "$T/stack/pdfeditor" ] && E=ja || E=nein
pruefe "entfernen raeumt den Ordner weg" "nein" "$E"
ls "$T/stack/.archiv/pdfeditor"/*.tar.gz >/dev/null 2>&1 && E=ja || E=nein
pruefe "aber legt ihn ins Archiv" "ja" "$E"
ls "$T/stack/.archiv/pdfeditor"/*.volume.*.tar.gz >/dev/null 2>&1 && E=ja || E=nein
pruefe "samt der Daten aus den Volumes" "ja" "$E"
ls "$T/stack/.archiv/pdfeditor"/*.info >/dev/null 2>&1 && E=ja || E=nein
pruefe "und einer Notiz, was das war" "ja" "$E"

# 4. Tragende Tools sind geschuetzt
for t in traefik authentik socket-proxy; do
  mkdir -p "$T/stack/$t"; printf 'services:\n  x:\n    image: x:1\n' > "$T/stack/$t/docker-compose.yml"
done
A=$(prolo entfernen traefik 2>&1)
echo "$A" | grep -q "traegt den ganzen Stack" && E=ja || E=nein
pruefe "traefik laesst sich nicht wegraeumen" "ja" "$E"
[ -e "$T/stack/traefik" ] && E=ja || E=nein
pruefe "und ist auch wirklich noch da" "ja" "$E"

# 5. Archiv anzeigen
A=$(prolo archiv 2>&1)
echo "$A" | grep -q "pdfeditor" && E=ja || E=nein
pruefe "archiv zeigt das entfernte Tool" "ja" "$E"

# 6. Zurueckholen - ein Stand, also ohne Nachfrage
rm -rf "$VOLUMEHEIM/pdfeditor_pdfeditor_daten"
prolo zurueckholen pdfeditor >/dev/null 2>&1
[ -f "$T/stack/pdfeditor/docker-compose.yml" ] && E=ja || E=nein
pruefe "zurueckholen bringt den Ordner zurueck" "ja" "$E"
[ -f "$VOLUMEHEIM/pdfeditor_pdfeditor_daten/inhalt.txt" ] && E=ja || E=nein
pruefe "und die Daten aus dem Volume" "ja" "$E"
pruefe "die Daten sind unveraendert" "wichtige daten" \
  "$(cat "$VOLUMEHEIM/pdfeditor_pdfeditor_daten/inhalt.txt" 2>/dev/null)"
ls "$T/stack/.archiv/pdfeditor"/*.tar.gz >/dev/null 2>&1 && E=ja || E=nein
pruefe "das Archiv bleibt nach dem Zurueckholen erhalten" "ja" "$E"

# 7. Zweiter Stand -> es MUSS gefragt werden
# Bewusst OHNE Pause: zwei Entfernungen in derselben Sekunde duerfen sich
# nicht gegenseitig ueberschreiben.
prolo entfernen pdfeditor >/dev/null 2>&1
printf 'nginx:1.27-alpine\n8080\n' | prolo neu pdfeditor >/dev/null 2>&1
prolo entfernen pdfeditor >/dev/null 2>&1
# Drei, nicht zwei: der Stand vom ersten Entfernen bleibt beim Zurueckholen
# liegen (wird oben eigens geprueft), dazu kommen die beiden hier.
ANZ=$(ls "$T/stack/.archiv/pdfeditor"/*.tar.gz 2>/dev/null | grep -vc volume)
pruefe "jedes Entfernen ergibt einen eigenen Stand, keiner geht verloren" "3" "$ANZ"
A=$(printf '\n' | prolo zurueckholen pdfeditor 2>&1)
echo "$A" | grep -q "Mehrere Staende" && E=ja || E=nein
pruefe "bei mehreren Staenden wird gefragt" "ja" "$E"

# 8. Unbekanntes Tool
A=$(prolo zurueckholen gibtsnicht 2>&1); echo "$A" | grep -q "Nichts im Archiv" && E=ja || E=nein
pruefe "unbekanntes Tool im Archiv wird benannt" "ja" "$E"
A=$(prolo protokoll gibtsnicht 2>&1); echo "$A" | grep -q "Kein Tool" && E=ja || E=nein
pruefe "unbekanntes Tool bei protokoll wird benannt" "ja" "$E"

# 9. Ohne root wird nichts angefasst
A=$(PATH="$T/bin:$PATH" UID_VORGABE=1000 "$T/stack/werkzeuge/prolo" entfernen pdfeditor 2>&1)
echo "$A" | grep -q "braucht root" && E=ja || E=nein
pruefe "entfernen ohne root wird abgelehnt" "ja" "$E"

# 10. Hilfe und unbekannter Befehl
A=$(prolo hilfe 2>&1); echo "$A" | grep -q "zurueckholen" && E=ja || E=nein
pruefe "hilfe listet die Befehle" "ja" "$E"
prolo quatsch >/dev/null 2>&1 && E=0 || E=1
pruefe "unbekannter Befehl endet mit Fehler" "1" "$E"

# 11. Der Aufruf UEBER EINEN SYMLINK muss denselben Stack finden.
#     Genau daran ist die erste Fassung gescheitert: BASH_SOURCE zeigt auf
#     den Symlink, nicht aufs Ziel - STACK wurde /usr/local, und vier
#     Befehle liefen ins Leere. Der empfohlene Weg ist ein Symlink nach
#     /usr/local/bin, also gehoert genau der geprueft.
mkdir -p "$T/anderswo"
ln -sf "$T/stack/werkzeuge/prolo" "$T/anderswo/prolo"
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" hilfe 2>&1)
echo "$A" | grep -q "Stack unter $T/stack" && E=ja || E=nein
pruefe "ueber einen Symlink wird derselbe Stack gefunden" "ja" "$E"

# Und zwar nicht nur in der Hilfe, sondern auch bei einem echten Befehl.
printf 'nginx:1.27-alpine\n8080\n' | PATH="$T/bin:$PATH" "$T/anderswo/prolo" neu symtest \
  >/dev/null 2>&1
[ -f "$T/stack/symtest/docker-compose.yml" ] && E=ja || E=nein
pruefe "und 'neu' legt im richtigen Ordner an" "ja" "$E"

A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" status --kurz 2>&1)
echo "$A" | grep -q "symtest" && E=ja || E=nein
pruefe "und 'status' findet die Tools" "ja" "$E"

# Auch ueber eine Kette aus zwei Symlinks.
ln -sf "$T/anderswo/prolo" "$T/anderswo/prolo2"
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo2" hilfe 2>&1)
echo "$A" | grep -q "Stack unter $T/stack" && E=ja || E=nein
pruefe "auch ueber eine Kette aus zwei Symlinks" "ja" "$E"

# 12. Zusatznamen aus dns-namen.conf werden mitgelesen
mkdir -p "$T/stack/werkzeuge"
printf '# Kommentar\nzusatz.beispiel.de\n\n' > "$T/stack/werkzeuge/dns-namen.conf"
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" dns 2>&1 || true)
echo "$A" | grep -q "zusatz.beispiel.de" && E=ja || E=nein
pruefe "Zusatznamen aus dns-namen.conf werden geprueft" "ja" "$E"
echo "$A" | grep -q "^  # Kommentar" && E=ja || E=nein
pruefe "Kommentarzeilen werden dabei nicht als Name gelesen" "nein" "$E"

# 13. Ein Name, der NICHT auflaest, darf den Befehl nicht lahmlegen.
#     getent gibt dann 2 zurueck; unter set -euo pipefail riss das vorher
#     die ganze Funktion ab, noch vor der ersten Zeile. Ausgerechnet der
#     Fall, fuer den es den Befehl gibt.
printf 'gibtesganzsicherniemals.invalid\nzweiter.invalid\n' \
  > "$T/stack/werkzeuge/dns-namen.conf"
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" dns 2>&1 || true)
echo "$A" | grep -q "gibtesganzsicherniemals.invalid" && E=ja || E=nein
pruefe "ein nicht aufloesbarer Name wird gemeldet" "ja" "$E"
echo "$A" | grep -q "zweiter.invalid" && E=ja || E=nein
pruefe "und bricht die Liste nicht ab" "ja" "$E"
echo "$A" | grep -q "KEINE ANTWORT" && E=ja || E=nein
pruefe "mit einer verstaendlichen Meldung" "ja" "$E"

# 14. status haelt denselben Fall aus
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" status --kurz 2>&1 || true)
echo "$A" | grep -q "TOOL" && E=ja || E=nein
pruefe "status --kurz laeuft durch" "ja" "$E"

# 15. Der Quellstand (N-38): "prolo quelle" ist eine Auskunft, kein
#     Fehlschlag - auch dann, wenn der Stand hinterherhaengt. Unter set -e
#     waere der Rueckgabewert 10 sonst ein Abbruch.
if command -v git >/dev/null 2>&1 && [ -f "$HIER/quellstand.sh" ]; then
  GS="$T/gitstack"
  rm -rf "$GS" "$T/gitfern"
  mkdir -p "$T/gitfern" && git -C "$T/gitfern" init -q -b haupt
  git -C "$T/gitfern" config user.email t@t; git -C "$T/gitfern" config user.name t
  echo eins > "$T/gitfern/datei"; git -C "$T/gitfern" add -A
  git -C "$T/gitfern" commit -q -m eins
  git clone -q "$T/gitfern" "$GS"
  echo zwei > "$T/gitfern/datei"; git -C "$T/gitfern" add -A
  git -C "$T/gitfern" commit -q -m "zwei - die neue Fassung"
  mkdir -p "$GS/werkzeuge" "$GS/probe"
  cp "$HIER/prolo" "$HIER/quellstand.sh" "$GS/werkzeuge/"
  printf 'services:\n  probe:\n    image: probe:1\n' > "$GS/probe/docker-compose.yml"

  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/prolo" quelle 2>&1); R=$?
  pruefe "prolo quelle: Rueckgabe 0 trotz Rueckstand" "0" "$R"
  echo "$A" | grep -q "1 Commit(s) HINTER" && E=ja || E=nein
  pruefe "prolo quelle: sagt, wie weit es zurueck ist" "ja" "$E"

  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/prolo" status 2>&1 || true)
  echo "$A" | grep -q "1 Commit(s) hinter origin/haupt" && E=ja || E=nein
  pruefe "prolo status nennt den Quellstand mit Zahl, in einer Zeile" "ja" "$E"

  # --kurz verspricht: nichts, was das Netz braucht. Ein git fetch braucht es.
  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/prolo" status --kurz 2>&1 || true)
  echo "$A" | grep -q "hinter origin/haupt" && E=ja || E=nein
  pruefe "und --kurz geht dafuer ausdruecklich NICHT ins Netz" "nein" "$E"
  echo "$A" | grep -q "Quellstand" && E=ja || E=nein
  pruefe "sagt aber, dass es uebersprungen wurde" "ja" "$E"

  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/prolo" hilfe 2>&1 || true)
  echo "$A" | grep -q "quelle \[--holen\]" && E=ja || E=nein
  pruefe "und die Hilfe nennt den Befehl" "ja" "$E"
else
  echo "uebersprungen  Quellstand (git oder quellstand.sh fehlt)"
fi

# ----------------------------------------------------------------------
# Steht in den Anleitungen ein Befehl, den es gar nicht gibt? (N-51)
#
# "sudo prolo compose traefik up -d" stand in der Bedienungsseite und in dem
# Geruest, das "prolo neu" schreibt - und "prolo compose" hat es nie
# gegeben. Wer es tippt, bekommt "Unbekannt: compose". Eine Anleitung, die
# in einen Fehler fuehrt, ist schlimmer als keine, weil man ihr glaubt und
# den Fehler bei sich sucht.
#
# Gesucht wird nur an BEFEHLSSTELLE - am Zeilenanfang, hinter sudo, hinter
# &&/;/| - und nur in Codebloecken. Sonst faellt die Pruefung ueber ihren
# eigenen Fliesstext ("prolo ruft die Skripte auf") und ueber Dateilisten
# ("-rw------- 1 prolo prolo acme.json"). Das ist hier schon sechsmal
# passiert (N-33, N-36, N-39, N-44, N-50).
A=$(python3 "$HIER/prolo-befehle-pruefen.py" "$(dirname "$HIER")" 2>&1); R=$?
echo "$A"
[ "$R" -eq 0 ] || FEHLER=1

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "GEGENPROBE FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
