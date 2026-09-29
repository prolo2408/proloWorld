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
cp "$HIER/prolo" "$HIER/neu.sh" "$HIER/netze.sh" "$HIER/volumes.py" \
   "$HIER/quellstand.sh" "$T/stack/werkzeuge/"

# Einstieg fuer die Mutationsprobe (werkzeuge/prolo-gegenprobe.py). Sie
# baut ihre Fehler in die KOPIE im Wegwerfordner ein, nie in die Datei im
# Arbeitsstand - eine Probe, die ueber "git checkout" zurueckrollen
# muesste, loescht eine noch nicht eingecheckte Korrektur mit weg
# (N-34, N-60).
[ -z "${PROLO_MUTATION:-}" ] || python3 "$PROLO_MUTATION" "$T/stack/werkzeuge" || {
  echo "FEHLER Mutation liess sich nicht einbauen" >&2; exit 3; }

# Alles, was den Quelltext von prolo LIEST, liest ab hier die Kopie - sonst
# laeuft die Mutationsprobe gegen eine Datei, die sie gar nicht veraendert
# hat, und ist gruen aus Mangel an Gelegenheit.
QUELLE_PROLO="$T/stack/werkzeuge/prolo"
QUELLE_QUELLSTAND="$T/stack/werkzeuge/quellstand.sh"
printf '#!/bin/bash\nexit 0\n' > "$T/stack/backup.sh"; chmod +x "$T/stack/backup.sh"
printf '#!/bin/bash\n[ "$1" = "-u" ] && echo "${UID_VORGABE:-0}" || exec /usr/bin/id "$@"\n' \
  > "$T/bin/id"; chmod +x "$T/bin/id"

# docker-Attrappe: tar-Aufrufe fuer Volumes echt ausfuehren, damit das
# Zurueckholen wirklich Daten bewegt und nicht nur so tut.
ECHTES_DOCKER=$(command -v docker || true)
cat > "$T/bin/docker" <<STUB
#!/bin/bash
ECHT="$ECHTES_DOCKER"
STUB
cat >> "$T/bin/docker" <<'STUB'
# "compose config" braucht keinen Daemon - durchreichen statt erfinden.
if [ "$1 $2" = "compose config" ] && [ -n "$ECHT" ]; then exec "$ECHT" "$@"; fi
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
grep -q 'exec "$HIER/neu.sh"' "$QUELLE_PROLO" && E=ja || E=nein
pruefe "neu reicht an werkzeuge/neu.sh weiter" "ja" "$E"
grep -q 'exec "$HIER/netze.sh"' "$QUELLE_PROLO" && E=ja || E=nein
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

# 7b. Entfernen sagt, dass der Ordner auch im Git steht (N-66)
# Sonst holt der naechste Pull ihn zurueck oder bricht an den geloeschten
# Dateien ab - und beides sieht aus wie ein Fehler des Werkzeugs.
if command -v git >/dev/null 2>&1; then
  pdfeditor_anlegen
  (cd "$T/stack" && git init -q -b haupt && git config user.email t@t \
   && git config user.name t && git add -A && git commit -q -m stand) || true
  A=$(prolo entfernen pdfeditor 2>&1)
  echo "$A" | grep -q "steht im Git" && E=ja || E=nein
  pruefe "entfernen sagt, dass das Werkzeug im Git steht" "ja" "$E"
  echo "$A" | grep -q "git checkout -- pdfeditor/" && E=ja || E=nein
  pruefe "entfernen nennt den Weg zurueck" "ja" "$E"
  echo "$A" | grep -q "git rm -r pdfeditor" && E=ja || E=nein
  pruefe "entfernen nennt den Weg, es wirklich loszuwerden" "ja" "$E"
  # Und die Gegenrichtung: ohne Git kein Hinweis, sonst ist er Tapete.
  rm -rf "$T/stack/.git"
  pdfeditor_anlegen
  A=$(prolo entfernen pdfeditor 2>&1)
  echo "$A" | grep -q "steht im Git" && E=ja || E=nein
  pruefe "ohne Git kommt der Hinweis nicht" "nein" "$E"
fi
# Wieder hinstellen: die naechsten Abschnitte brauchen das Tool.
pdfeditor_anlegen

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
  cp "$QUELLE_PROLO" "$QUELLE_QUELLSTAND" "$GS/werkzeuge/"
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

  # --- Unerreichbares origin (N-81) ------------------------------------
  # Hier stand ein 2>/dev/null ueber dem fetch. Damit sah ein fehlender
  # Zugang fuer root genauso aus wie ein abgestecktes Netzkabel, und der
  # Betreiber stand vor "kein Zugriff auf origin" ohne jeden Anhaltspunkt.
  # Geprueft wird die WIRKUNG: steht die Meldung von git selbst da?
  git -C "$GS" remote set-url origin "$T/gibt-es-nicht"
  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/prolo" quelle 2>&1 || true)
  echo "$A" | grep -q "nicht pruefbar (kein Zugriff auf origin)" && E=ja || E=nein
  pruefe "unerreichbares origin: sagt, dass es nicht pruefbar ist" "ja" "$E"
  echo "$A" | grep -q "git sagt:" && E=ja || E=nein
  pruefe "und gibt weiter, was git selbst gesagt hat (N-81)" "ja" "$E"
  echo "$A" | grep -qi "does not appear to be a git repository" && E=ja || E=nein
  pruefe "und zwar die Meldung im Wortlaut, nicht umschrieben" "ja" "$E"
  echo "$A" | grep -q "fetch origin haupt" && E=ja || E=nein
  pruefe "und nennt genau den Aufruf zum Nachsehen (N-64)" "ja" "$E"
  # --kurz verspricht eine Zeile - die Erklaerung darf sie nicht sprengen.
  A=$(PATH="$T/bin:$PATH" "$GS/werkzeuge/quellstand.sh" --kurz 2>&1 || true)
  pruefe "--kurz bleibt trotzdem bei einer Zeile" "1" "$(printf '%s\n' "$A" | wc -l | tr -d ' ')"
  git -C "$GS" remote set-url origin "$T/gitfern"
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
  "$QUELLE_PROLO" > "$DEUT"
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
# Ursache und Wirkung standen nebeneinander - gesagt wurde der
# Zusammenhang nie (N-69)
#
# "prolo status" zeigte fuer admin.prolo.me zwei Zellen:
#
#   admin.prolo.me    217.160.0.1 (FREMD)   keine Antwort auf 443
#
# Beide Tatsachen richtig, beide im Fusstext einzeln erklaert - dass die
# erste die URSACHE der zweiten ist, stand nirgends. Gefragt wurde genau
# danach: "Ich weiss nicht, was da der Fix ist."
#
# Erst die reine Folgerung mit Eingaben von Hand (wie bei N-57), danach
# die Wirkung im fertigen Befehl. Eine Funktion, die richtig folgert und
# nirgends aufgerufen wird, hilft niemandem.
FOLG="$T/folgern.sh"
sed -n '/^zertifikat_folgerung()/,/^}/p;/^zertifikat_rat()/,/^}/p' \
  "$QUELLE_PROLO" > "$FOLG"
# shellcheck disable=SC1090
. "$FOLG"

folg()  { zertifikat_folgerung "n.example" "$1" "$2" "1.2.3.4" "9.9.9.9" || true; }
art()   { printf '%s' "$(folg "$1" "$2")" | head -1; }
satz()  { printf '%s' "$(folg "$1" "$2")" | tail -n +2; }
hat()   { printf '%s' "$1" | grep -qF "$2" && echo ja || echo nein; }

# 1. Der Fall des Nutzers: Name zeigt woanders hin, kein Zertifikat.
A=$(satz fremd keins)
pruefe "FREMD ohne Zertifikat: das WEIL wird ausgesprochen" "ja" \
  "$(hat "$A" "n.example hat kein Zertifikat, WEIL der Name auf 1.2.3.4 zeigt")"
pruefe "und der Handgriff steht da, mit der richtigen IP" "ja" \
  "$(hat "$A" "A-Eintrag fuer n.example auf 9.9.9.9 setzen")"
pruefe "und die Art sagt, welche Erklaerung dazugehoert" "dns" "$(art fremd keins)"

# 2. Ohne bekannte eigene IP darf keine erfundene dastehen.
A=$(zertifikat_folgerung "n.example" fremd keins "1.2.3.4" "" || true)
pruefe "ohne bekannte Server-IP wird keine erfunden" "nein" "$(hat "$A" "auf  setzen")"
pruefe "sondern umschrieben" "ja" "$(hat "$A" "auf die IP dieses Servers setzen")"

# 3. Ein Notzertifikat ist kein Zertifikat - dieselbe Folgerung.
pruefe "NOTZERTIFIKAT zaehlt wie keines" "ja" \
  "$(hat "$(satz fremd notbehelf)" "hat kein Zertifikat, WEIL")"

# 4. Name loest gar nicht auf: derselbe Weg, andere Begruendung.
A=$(zertifikat_folgerung "n.example" keine keins "" "9.9.9.9" || true)
pruefe "ein Name ohne Antwort wird als Ursache benannt" "ja" \
  "$(hat "$A" "WEIL der Name ueberhaupt nicht aufloest")"

# 5. Zeigt der Name woanders hin und dort antwortet ein gueltiges
#    Zertifikat, ist das NICHT unseres - beruhigen waere hier falsch.
A=$(satz fremd gut)
pruefe "ein fremdes gueltiges Zertifikat wird als fremdes benannt" "ja" \
  "$(hat "$A" "landet nicht bei uns")"
pruefe "und wird nicht als fehlendes ausgegeben" "nein" "$(hat "$A" "hat kein Zertifikat")"
pruefe "und gehoert trotzdem zur DNS-Erklaerung" "dns" "$(art fremd gut)"

# 6. Zeigt der Name hierher, ist er als Ursache ausgeschlossen - dann
#    darf die Meldung nicht zum DNS-Anbieter schicken.
A=$(zertifikat_folgerung "n.example" hier keins "9.9.9.9" "9.9.9.9" || true)
pruefe "zeigt der Name hierher, liegt es an uns" "ja" \
  "$(hat "$A" "Am Namen liegt es also nicht")"
pruefe "und es wird nicht zum DNS-Anbieter geschickt" "nein" "$(hat "$A" "A-Eintrag")"
pruefe "die Art ist dann eine andere" "acme" "$(art hier keins)"

# 7. Alles in Ordnung heisst: nichts sagen. Eine Folgerung, die immer
#    kommt, ist Tapete und wird nach dem dritten Mal ueberlesen.
zertifikat_folgerung "n.example" hier gut "9.9.9.9" "9.9.9.9" >/dev/null 2>&1 && E=ja || E=nein
pruefe "bei heilem Namen und echtem Zertifikat gibt es nichts zu sagen" "nein" "$E"
A=$(zertifikat_folgerung "n.example" hier gut "9.9.9.9" "9.9.9.9" 2>&1 || true)
pruefe "und es kommt auch kein Text" "" "$A"

# 8. Ein echtes Zertifikat, das bald ablaeuft, ist kein DNS-Problem.
A=$(satz hier ablauf)
pruefe "ein bald ablaufendes Zertifikat wird gemeldet" "ja" \
  "$(hat "$A" "das aber bald ablaeuft")"
pruefe "und nicht als fehlendes ausgegeben" "nein" "$(hat "$A" "hat kein Zertifikat")"
pruefe "mit eigener Art" "ablauf" "$(art hier ablauf)"

# 9. Die Erklaerungen selbst: jede nennt den Befehl, nicht nur die
#    Aufgabe (N-67).
A=$(zertifikat_rat dns)
pruefe "die DNS-Erklaerung nennt den Ort des Handgriffs" "ja" \
  "$(hat "$A" "beim DNS-Anbieter")"
pruefe "und den Befehl, der es sofort versucht" "ja" "$(hat "$A" "sudo prolo start traefik")"
pruefe "und warum der Browser meckert" "ja" "$(hat "$A" "Seite ist nicht sicher")"
pruefe "die acme-Erklaerung nennt das Protokoll" "ja" \
  "$(hat "$(zertifikat_rat acme)" "sudo prolo protokoll traefik")"
pruefe "die Ablauf-Erklaerung nennt die 30 Tage" "ja" \
  "$(hat "$(zertifikat_rat ablauf)" "30 Tagen")"
zertifikat_rat gibtsnicht >/dev/null 2>&1 && E=ja || E=nein
pruefe "zu einer unbekannten Art gibt es keinen Rat" "nein" "$E"

# ----------------------------------------------------------------------
# Und jetzt die Wirkung: kommt es in "prolo status" auch an?
#
# "Eine Meldung ist kein Beweis" gilt auch andersherum - eine Funktion,
# die richtig folgert und nirgends aufgerufen wird, aendert nichts.
# Darum wird der Befehl hier wirklich ausgefuehrt, mit gefaelschtem
# getent, curl und openssl.
mkdir -p "$T/netz"
cat > "$T/netz/curl" <<'STUB'
#!/bin/bash
echo "9.9.9.9"
STUB
cat > "$T/netz/getent" <<'STUB'
#!/bin/bash
case "$2" in
  fremd.beispiel)   echo "1.2.3.4   STREAM fremd.beispiel" ;;
  zweit.beispiel)   echo "1.2.3.4   STREAM zweit.beispiel" ;;
  hier.beispiel)    echo "9.9.9.9   STREAM hier.beispiel" ;;
  notzert.beispiel) echo "9.9.9.9   STREAM notzert.beispiel" ;;
  alt.beispiel)     echo "9.9.9.9   STREAM alt.beispiel" ;;
  *) exit 2 ;;
esac
STUB
# Die Attrappe deckt beide Aufrufe in zertifikat() ab: s_client reicht den
# Namen weiter, x509 macht daraus die Felder, die openssl auch echt
# liefert. fremd.beispiel antwortet gar nicht - genau der Fall von oben.
cat > "$T/netz/openssl" <<'STUB'
#!/bin/bash
if [ "$1" = "s_client" ]; then
  while [ $# -gt 0 ]; do [ "$1" = "-servername" ] && { echo "NAME=$2"; exit 0; }; shift; done
  exit 1
fi
N=$(sed -n 's/^NAME=//p' | head -1)
case "$N" in
  hier.beispiel)
    echo "notAfter=Sep 20 10:00:00 2027 GMT"
    echo "issuer=C = US, O = Let's Encrypt, CN = R11" ;;
  notzert.beispiel)
    echo "notAfter=Sep 20 10:00:00 2027 GMT"
    echo "issuer=CN = TRAEFIK DEFAULT CERT" ;;
  alt.beispiel)
    echo "notAfter=Sep 20 10:00:00 2020 GMT"
    echo "issuer=C = US, O = Let's Encrypt, CN = R11" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$T/netz/curl" "$T/netz/getent" "$T/netz/openssl"
printf 'fremd.beispiel\nzweit.beispiel\nhier.beispiel\nnotzert.beispiel\nalt.beispiel\n' \
  > "$T/stack/werkzeuge/dns-namen.conf"
A=$(PATH="$T/netz:$T/bin:$PATH" "$T/stack/werkzeuge/prolo" status 2>&1 || true)
# Was unter der Tabelle steht - nur das ist die Folgerung. Sonst zaehlte
# die Tabellenzeile selbst als Treffer.
UNTEN=$(printf '%s' "$A" | sed -n '/Was daraus folgt/,$p')

pruefe "status nennt den Zusammenhang beim betroffenen Namen" "ja" \
  "$(hat "$UNTEN" "fremd.beispiel hat kein Zertifikat, WEIL der Name auf 1.2.3.4 zeigt")"
pruefe "status nennt den A-Eintrag mit der gemessenen Server-IP" "ja" \
  "$(hat "$UNTEN" "A-Eintrag fuer fremd.beispiel auf 9.9.9.9 setzen")"
pruefe "status nennt fuer ein Notzertifikat die andere Ursache" "ja" \
  "$(hat "$UNTEN" "notzert.beispiel zeigt hierher, und trotzdem kommt kein Zertifikat")"
# Der Prueferbeweis: ein heiler Name darf UNTEN nicht auftauchen. Ohne
# diese Zeile waere eine Folgerung, die immer kommt, gruen.
pruefe "ein heiler Name taucht unter der Tabelle NICHT auf" "nein" \
  "$(hat "$UNTEN" "hier.beispiel")"
# Ein abgelaufenes Zertifikat ist so gut wie keines - und der Prueflauf
# muss den Fall wirklich herstellen, sonst ist die Zeile darueber gruen
# aus Mangel an Gelegenheit (N-68).
pruefe "die Tabelle nennt das abgelaufene Zertifikat" "ja" \
  "$(hat "$A" "alt.beispiel")"
pruefe "ein abgelaufenes Zertifikat zaehlt wie keines" "ja" \
  "$(hat "$UNTEN" "alt.beispiel zeigt hierher")"
# Und die Tabelle bleibt eine Tabelle.
pruefe "die Tabellenzeile steht trotzdem noch da" "ja" \
  "$(hat "$A" "fremd.beispiel             1.2.3.4 (FREMD)")"
# Die Spalte ZEIGT AUF muss "217.160.0.1 (FREMD)" fassen - 15 Zeichen
# IPv4 plus " (FREMD)" sind 23. War sie 16 breit, schob ausgerechnet die
# auffaellige Zeile die letzte Spalte nach rechts (N-71).
#
# Erwartungswert von Hand aus dem Formatstring '  %-26s %-23s %s':
# zwei Leerzeichen + 26 + Trenner + 23 + Trenner = 53 (grep -b zaehlt ab 0).
spalte() { printf '%s\n' "$1" | grep -F "$2" | head -1 | grep -bom1 "$3" | cut -d: -f1; }
pruefe "die Spalte ZERTIFIKAT beginnt bei einem langen ZEIGT-AUF an Stelle 53" \
  "53" "$(spalte "$A" "fremd.beispiel" "keine Antwort")"
pruefe "und bei einem kurzen an derselben" \
  "53" "$(spalte "$A" "notzert.beispiel" "NOTZERTIFIKAT")"
# Zwei Namen mit derselben Ursache: zwei Saetze, EINE Erklaerung. Zehn
# Zeilen, die sich je Name wiederholen, liest niemand mehr (§7).
pruefe "beide betroffenen Namen bekommen ihren Satz" "2" \
  "$(printf '%s\n' "$UNTEN" | grep -c 'hat kein Zertifikat, WEIL')"
pruefe "die Erklaerung dazu steht genau einmal da" "1" \
  "$(printf '%s\n' "$UNTEN" | grep -c 'sudo prolo start traefik')"
pruefe "und die andere Ursache hat ihre eigene" "1" \
  "$(printf '%s\n' "$UNTEN" | grep -c 'sudo prolo protokoll traefik')"

# prolo dns kennt keine Zertifikate - aber dass eines daran haengt, weiss
# es und sagt es jetzt auch.
A=$(PATH="$T/netz:$T/bin:$PATH" "$T/stack/werkzeuge/prolo" dns 2>&1 || true)
pruefe "dns sagt, dass das Zertifikat daran haengt" "ja" \
  "$(hat "$A" "Daran haengt das Zertifikat")"
pruefe "dns nennt die IP, auf die der A-Eintrag zeigen muss" "ja" \
  "$(hat "$A" "A-Eintrag auf 9.9.9.9 setzen")"
rm -f "$T/stack/werkzeuge/dns-namen.conf"
# ----------------------------------------------------------------------
# Ein Fremdwerkzeug traegt seinen Namen in der override-Datei (N-70)
#
# Seit N-61 steht bei einem Fremdwerkzeug alles von uns - Netz, Route,
# Zertifikat - in der docker-compose.override.yml. hostnamen() las nur
# die Herstellerdatei; der Name fiel damit aus der Aufsicht, ohne dass
# irgendwo etwas rot wurde: die Liste wurde nur kuerzer.
mkdir -p "$T/stack/fremdtool" "$T/stack/eigentool"
printf 'services:\n  f:\n    image: f:1\n' > "$T/stack/fremdtool/docker-compose.yml"
cat > "$T/stack/fremdtool/docker-compose.override.yml" <<'Y'
services:
  f:
    labels:
      - "traefik.http.routers.f.rule=Host(`fremdtool.beispiel`)"
Y
# Und eines, das seinen Namen wie eigener Code in der ersten Datei fuehrt.
# Beide muessen durchkommen - sonst waere die Korrektur nur eine
# Verschiebung derselben Luecke.
cat > "$T/stack/eigentool/docker-compose.yml" <<'Y'
services:
  e:
    image: e:1
    labels:
      - "traefik.http.routers.e.rule=Host(`eigentool.beispiel`)"
Y
A=$(PATH="$T/netz:$T/bin:$PATH" "$T/stack/werkzeuge/prolo" dns 2>&1 || true)
pruefe "ein Name aus der override-Datei wird geprueft" "ja" \
  "$(hat "$A" "fremdtool.beispiel")"
pruefe "und der aus der Herstellerdatei weiterhin auch" "ja" \
  "$(hat "$A" "eigentool.beispiel")"
A=$(PATH="$T/netz:$T/bin:$PATH" "$T/stack/werkzeuge/prolo" status 2>&1 || true)
pruefe "status sieht ihn ebenfalls" "ja" "$(hat "$A" "fremdtool.beispiel")"
rm -rf "$T/stack/fremdtool" "$T/stack/eigentool"
# ----------------------------------------------------------------------
# Der Hinweis beim Starten nennt die Zeile, die WIRKLICH passt (N-78)
#
# bitwarden bindet ./vw-data ein - ein Ordner, kein benanntes Volume.
# Die erste Fassung schickte trotzdem zu VOLUMES=, und das ist die
# falsche Zeile: dort gehoeren nur Docker-Volumes hin. Eine Meldung, die
# in den naechsten Fehlversuch schickt, ist schlimmer als keine (§7).
mkdir -p "$T/stack/bindtool/vw-data"
cat > "$T/stack/bindtool/docker-compose.yml" <<'Y'
services:
  bindtool:
    image: bindtool:1
    volumes:
      - ./vw-data:/data
Y
printf 'VOLUMES=""\nORDNER=""\nDATEIEN=""\n' > "$T/stack/bindtool/sicherung.conf"
A=$(PATH="$T/bin:$PATH" "$T/stack/werkzeuge/prolo" start bindtool 2>&1)
echo "$A" | grep -q 'ORDNER="... vw-data"' && E=ja || E=nein
pruefe "der Hinweis nennt ORDNER= fuer einen gebundenen Ordner" "ja" "$E"
echo "$A" | grep -q 'VOLUMES="... vw-data"' && E=ja || E=nein
pruefe "und eben NICHT VOLUMES=" "nein" "$E"
echo "$A" | grep -q 'VOLUMES_OHNE="vw-data' && E=ja || E=nein
pruefe "der Ausweg mit Begruendung steht daneben" "ja" "$E"
# Und der Prueferbeweis: ist es eingetragen, kommt gar kein Hinweis.
printf 'VOLUMES=""\nORDNER="vw-data"\nDATEIEN=""\n' > "$T/stack/bindtool/sicherung.conf"
A=$(PATH="$T/bin:$PATH" "$T/stack/werkzeuge/prolo" start bindtool 2>&1)
echo "$A" | grep -q 'NICHT gesichert' && E=ja || E=nein
pruefe "ist es eingetragen, schweigt der Hinweis" "nein" "$E"
rm -rf "$T/stack/bindtool"

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
