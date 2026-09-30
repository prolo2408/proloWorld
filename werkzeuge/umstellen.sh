#!/bin/bash
# werkzeuge/umstellen.sh
#
# Nach dem Auslagern (auslagern.sh): den Werkzeugordner in proloWorld auf
# das veroeffentlichte Abbild umstellen (U-04). Danach behandelt der Betrieb
# das Werkzeug wie jedes fremde: Herstellerdatei + unsere Zutat, geholt
# statt gebaut.
#
#   werkzeuge/umstellen.sh <werkzeug> [--ohne-abbildpruefung]
#
# Was passiert - alles im Git vorgemerkt, NICHT eingecheckt:
#   - aus <werkzeug>/ geht alles weg, was nicht dem Betrieb gehoert
#     (Code, Tests, Schriften, Doku - das liegt jetzt im Werkzeug-Repo)
#   - docker-compose.yml verliert ihr "build:" - sie ist jetzt genau die
#     Herstellerdatei, die an der Veroeffentlichung haengt
#   - aktualisierung.conf: TYP=image statt build
#   - LIESMICH.md sagt, wem welche Datei gehoert
#   - beim Wiki: das Bedienhandbuch zieht nach doku/
#
# Es prueft VORHER, dass das Abbild zu holen ist. Ohne das haette der
# Server nach dem naechsten "prolo aktualisieren" ein Werkzeug, das sich
# weder bauen noch holen laesst.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

melde()  { printf '%s\n' "$*"; }
fehler() { printf '%s\n' "$*" >&2; }

W=""; OHNE_PRUEFUNG=0
for a in "$@"; do
  case "$a" in
    --ohne-abbildpruefung) OHNE_PRUEFUNG=1 ;;
    -*) fehler "Unbekannt: $a"; exit 2 ;;
    *) [ -z "$W" ] && W="$a" || { fehler "Zu viele Angaben."; exit 2; } ;;
  esac
done
[ -n "$W" ] || { fehler "Aufruf: werkzeuge/umstellen.sh <werkzeug> [--ohne-abbildpruefung]"; exit 2; }

ORDNER="$STACK/$W"
# Was dem Betrieb gehoert und bleibt. Alles andere im Ordner ist Werkzeug.
BLEIBT="docker-compose.yml docker-compose.override.yml sicherung.conf aktualisierung.conf geheimnisse.conf .env.beispiel .gitignore LIESMICH.md"

# --- Vorbedingungen (§12: vor der ersten Aenderung) ----------------------
[ -f "$ORDNER/docker-compose.yml" ] || { fehler "$W/docker-compose.yml fehlt."; exit 1; }
[ -f "$ORDNER/Dockerfile" ] || { fehler "$W hat kein Dockerfile mehr - schon umgestellt?"; exit 1; }
for d in docker-compose.override.yml sicherung.conf aktualisierung.conf; do
  [ -f "$ORDNER/$d" ] || { fehler "$W/$d fehlt - ohne sie gibt es nichts zu betreiben."; exit 1; }
done
BILD=$(grep -m1 -E '^\s*image:' "$ORDNER/docker-compose.yml" \
       | sed -E 's/^\s*image:\s*//; s/\s*#.*$//; s/"//g')
case "$BILD" in
  ghcr.io/prolo2408/*:*) ;;
  *) fehler "Die Herstellerdatei nennt '$BILD' - erwartet ist ghcr.io/prolo2408/$W:<fassung> (U-01)."
     exit 1 ;;
esac
if [ -n "$(git -C "$STACK" status --porcelain -- "$W" 2>/dev/null)" ]; then
  fehler "In $W/ liegen nicht eingecheckte Aenderungen - erst einchecken."
  git -C "$STACK" status --short -- "$W" | sed 's/^/  /' >&2
  exit 1
fi
if [ "$OHNE_PRUEFUNG" -eq 0 ]; then
  melde "Ist $BILD zu holen?"
  if ! AUSGABE=$(docker manifest inspect "$BILD" 2>&1); then
    fehler ""
    fehler "$BILD laesst sich nicht holen. docker sagt:"
    printf '%s\n' "$AUSGABE" | tail -3 | sed 's/^/  /' >&2
    fehler ""
    fehler "Genau dieser Aufruf war es:  docker manifest inspect $BILD"
    fehler ""
    fehler "Ist die Fassung noch nicht veroeffentlicht: im Werkzeug-Repository"
    fehler "  git tag v${BILD##*:} && git push --tags"
    fehler "und warten, bis der Arbeitsablauf durch ist."
    case "$AUSGABE" in
      *denied*|*unauthorized*|*"no basic auth"*)
        fehler "Die Meldung sagt: keine Berechtigung. Ist das Paket privat, einmalig:"
        fehler "  docker login ghcr.io -u prolo2408   (Token mit read:packages)" ;;
    esac
    fehler ""
    fehler "Nichts wurde angefasst."
    exit 1
  fi
  melde "  ja."
fi

# --- Umstellen ------------------------------------------------------------
cd "$STACK" || exit 1

# Das Bedienhandbuch von proloWorld lag als Wiki-Seite im Wiki. Es
# beschreibt den Betrieb - also bleibt es hier, in doku/.
if [ "$W" = wiki ] && [ -f "$ORDNER/vorlagen/prolo-bedienen.html" ]; then
  mkdir -p "$STACK/doku"
  git mv "$W/vorlagen/prolo-bedienen.html" doku/prolo-bedienen.html
  sed -i 's#`wiki/vorlagen/prolo-bedienen.html`#`doku/prolo-bedienen.html`#g' CLAUDE.md
  git add CLAUDE.md
  melde "  doku/prolo-bedienen.html  (vorher wiki/vorlagen/)"
fi

WEG=0
while IFS= read -r -d '' pfad; do
  rel="${pfad#"$ORDNER"/}"
  erster="${rel%%/*}"
  case " $BLEIBT " in *" $erster "*) continue ;; esac
  if git ls-files --error-unmatch "$pfad" >/dev/null 2>&1; then
    git rm -q -r -- "$pfad"
  else
    rm -rf -- "$pfad"
  fi
  WEG=$((WEG + 1))
done < <(find "$ORDNER" -mindepth 1 -maxdepth 1 -print0)
melde "  $WEG Eintraege aus $W/ entfernt (sie liegen im Werkzeug-Repository)"

# build: und die zwei Kommentarzeilen darueber gehen weg - der Rest bleibt
# Zeichen fuer Zeichen die Herstellerdatei.
python3 - "$ORDNER/docker-compose.yml" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = re.sub(r"(?m)^\s*# build: nur fuer den Bau aus dem Quellcode\..*\n\s*# veroeffentlicht, holt der Betrieb es von ghcr\.io\.\n", "", t)
t = re.sub(r"(?m)^\s*build:\s*\.\s*\n", "", t)
open(p, "w", encoding="utf-8").write(t)
PY
sed -i 's/^TYP="build"/TYP="image"/' "$ORDNER/aktualisierung.conf"

cat > "$ORDNER/LIESMICH.md" <<MD
# $W — was hier liegt und wem es gehört

Der Code von $W liegt in seinem eigenen Repository,
**github.com/prolo2408/$W**. Hier liegt nur, was der Betrieb braucht.

| Datei | gehört | Inhalt |
|---|---|---|
| \`docker-compose.yml\` | dem **Werkzeug** | die Herstellerdatei, wie sie an der Veröffentlichung hängt. Nur die Fassung in \`image:\` wird hier geändert. |
| \`docker-compose.override.yml\` | dem **Betrieb** | Netz, Route, Anmeldung, Speichergrenzen |
| \`sicherung.conf\`, \`aktualisierung.conf\`, \`geheimnisse.conf\` | dem Betrieb | was gesichert, wie aktualisiert, welche Geheimnisse |
| \`.env.beispiel\` | dem Betrieb | Vorlage für \`.env\` (die selbst nie ins Git) |

**Eine neue Fassung einspielen:** im Werkzeug-Repository veröffentlichen
(\`git tag v<fassung> && git push --tags\`), dann hier die Nummer in
\`docker-compose.yml\` hochsetzen und

    sudo prolo aktualisieren $W

Das sichert vorher, holt das Abbild und rollt bei Fehlschlag zurück.
MD
git add "$ORDNER"

melde ""
melde "$W ist umgestellt - vorgemerkt, nicht eingecheckt:"
git status --short -- "$W" doku CLAUDE.md | head -12 | sed 's/^/  /'
[ "$(git status --short -- "$W" | wc -l)" -gt 12 ] && melde "  ..."
cat <<WEITER

Weiter:
  1. Nachsehen und einchecken:
       git diff --cached --stat
       git commit -m "$W: vom Werkzeug-Repository, Abbild $BILD"
  2. Auf dem Server:
       sudo prolo aktualisieren $W
     Das holt $BILD statt zu bauen, legt den Container neu an und
     behaelt die Volumes. Scheitert es, rollt es zurueck.
WEITER
