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
cp "$HIER/prolo" "$HIER/neu.sh" "$HIER/netze.sh" "$T/stack/werkzeuge/"
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
#
# Seit N-61 steht der Erzeuger in werkzeuge/neu.sh, und geprueft wird er
# dort: werkzeuge/neu-pruefen.sh laesst ihn wirklich laufen und liest
# danach "docker compose config" - beide Dateien zusammengesetzt, mit dem
# echten docker. Das ist eine staerkere Probe als alles, was hier stand
# (Dateien zaehlen und nach Zeichenfolgen greppen), also steht es nur noch
# dort und nicht an zwei Stellen halb.
#
# Hier bleibt die Frage, die nur HIER zu beantworten ist: reicht der
# Einstiegspunkt den Befehl ueberhaupt weiter?
A=$(prolo neu 2>&1); R=$?
pruefe "neu ohne Namen wird abgelehnt" "1" "$R"
echo "$A" | grep -q "prolo neu <name>" && E=ja || E=nein
pruefe "und sagt, wie es geht" "ja" "$E"
grep -q 'exec "$HIER/neu.sh"' "$HIER/prolo" && E=ja || E=nein
pruefe "neu reicht an werkzeuge/neu.sh weiter" "ja" "$E"
grep -q 'exec "$HIER/netze.sh"' "$HIER/prolo" && E=ja || E=nein
pruefe "netze reicht an werkzeuge/netze.sh weiter" "ja" "$E"
[ -x "$HIER/neu-pruefen.sh" ] && E=ja || E=nein
pruefe "und der ausfuehrende Pruefer dazu ist da" "ja" "$E"

# Fuer die naechsten Abschnitte ein Tool von Hand - hier geht es um
# entfernen, archiv und zurueckholen, nicht um das Anlegen.
pdfeditor_anlegen() {
  mkdir -p "$T/stack/pdfeditor"
  cat > "$T/stack/pdfeditor/docker-compose.yml" <<'PDF'
services:
  pdfeditor:
    image: nginx:1.27-alpine
PDF
  printf 'VOLUMES="pdfeditor_pdfeditor_daten"\n' > "$T/stack/pdfeditor/sicherung.conf"
}
pdfeditor_anlegen

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
pdfeditor_anlegen
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

# Und zwar nicht nur in der Hilfe, sondern auch bei einem echten Befehl,
# der den Ort WIRKLICH benutzt. "neu" scheidet dafuer seit N-61 aus - es
# legt zuerst ein Netz an und braucht dazu Docker. "protokoll" braucht den
# Ort genauso: es muss den Werkzeugordner finden.
A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" protokoll gibtsnicht 2>&1)
echo "$A" | grep -q "Kein Tool 'gibtsnicht' unter $T/stack" && E=ja || E=nein
pruefe "und ein echter Befehl arbeitet im richtigen Ordner" "ja" "$E"

A=$(PATH="$T/bin:$PATH" "$T/anderswo/prolo" status --kurz 2>&1)
echo "$A" | grep -q "pdfeditor" && E=ja || E=nein
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
# Wird ein Notzertifikat als solches erkannt? (N-57)
#
# "prolo status" zeigte fuer prolo.me "364 Tage ()" an - als waere alles in
# Ordnung. Dahinter stand Traefiks Notzertifikat. Die Erkennung las nur das
# O=-Feld, und Traefiks Notzertifikat hat keines; herausgekommen ist eine
# leere Zeichenkette, und die Warnung suchte darin nach "traefik".
#
# Erwartungswerte von Hand, nicht aus der Ausgabe uebernommen (§13).
DEUT="$T/deuten.sh"
sed -n '/^zertifikat_deuten()/,/^}/p;/^zertifikat_notbehelf()/,/^}/p' \
  "$HIER/prolo" > "$DEUT"
# shellcheck disable=SC1090
. "$DEUT"

roh() { printf 'notAfter=Sep 20 10:00:00 2027 GMT\nissuer=%s\n' "$1"; }
deute() { local R; R=$(zertifikat_deuten "$(roh "$1")"); printf '%s' "${R#*|}"; }
notbehelf() { zertifikat_notbehelf "$(deute "$1")" && echo ja || echo nein; }

pruefe "Let's Encrypt wird am O=-Feld erkannt" \
  "Let's Encrypt" "$(deute "C = US, O = Let's Encrypt, CN = R11")"
pruefe "Traefiks Notzertifikat wird am CN= erkannt" \
  "TRAEFIK DEFAULT CERT" "$(deute "CN = TRAEFIK DEFAULT CERT")"
pruefe "ein Herausgeber ohne O= und CN= heisst 'unbekannt'" \
  "unbekannt" "$(deute "C = XX")"
pruefe "Traefiks Notzertifikat gilt als Notbehelf" "ja" "$(notbehelf "CN = TRAEFIK DEFAULT CERT")"
pruefe "ein unbekannter Herausgeber gilt als Notbehelf" "ja" "$(notbehelf "C = XX")"
pruefe "Let's Encrypt gilt NICHT als Notbehelf" "nein" \
  "$(notbehelf "C = US, O = Let's Encrypt, CN = R11")"
# Ohne Ablaufdatum gibt es nichts zu deuten - dann lieber gar nichts sagen.
zertifikat_deuten "issuer=CN = irgendwas" >/dev/null 2>&1 && E=ja || E=nein
pruefe "ohne notAfter meldet die Deutung einen Fehlschlag" "nein" "$E"

# ----------------------------------------------------------------------
# Steht in den Anleitungen ein Befehl, den es gar nicht gibt? (N-51)
#
# Ein erfundener Unterbefehl (compose) stand in der Bedienungsseite, in dem
# Geruest, das "prolo neu" schreibt, und in drei Fehlermeldungen der
# Werkzeuge - gegeben hat es ihn nie. Wer ihn tippt, bekommt "Unbekannt:".
# Eine Anleitung, die in einen Fehler fuehrt, ist schlimmer als keine, weil
# man ihr glaubt und den Fehler bei sich sucht.
#
# Der Befehlsname steht hier mit Absicht NICHT ausgeschrieben: sonst faellt
# diese Pruefung ueber ihren eigenen Kommentar (N-36, und danach noch
# sechsmal). Eine Ausnahme fuer diese Datei waere der bequemere Weg und das
# groessere Loch.
#
# Gesucht wird nur an BEFEHLSSTELLE - am Zeilenanfang, hinter sudo, hinter
# &&/;/| - und nur in Codebloecken. Sonst faellt die Pruefung ueber ihren
# eigenen Fliesstext ("prolo ruft die Skripte auf") und ueber Dateilisten
# ("-rw------- 1 prolo prolo acme.json"). Das ist hier schon sechsmal
# passiert (N-33, N-36, N-39, N-44, N-45, N-50).
A=$(python3 "$HIER/prolo-befehle-pruefen.py" "$(dirname "$HIER")" 2>&1); R=$?
echo "$A"
[ "$R" -eq 0 ] || FEHLER=1

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "GEGENPROBE FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
