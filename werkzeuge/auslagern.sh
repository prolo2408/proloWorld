#!/bin/bash
# werkzeuge/auslagern.sh
#
# Ein eigenes Werkzeug in sein eigenes Repository umziehen - MIT seiner
# Geschichte (U-04).
#
#   werkzeuge/auslagern.sh <werkzeug> <ziel-url> [--trocken]
#
# Beispiel:
#   werkzeuge/auslagern.sh bordbuch git@github.com:prolo2408/bordbuch.git
#
# Voraussetzungen:
#   - das Ziel-Repository ist auf GitHub angelegt und LEER: ohne README,
#     ohne .gitignore, ohne Lizenz. Ein Ziel mit Inhalt wird nicht
#     angefasst - hier wird nichts ueberschrieben.
#   - der Arbeitsstand des Werkzeugs ist eingecheckt
#
# Was passiert:
#   1. git subtree split: die Geschichte von <werkzeug>/ wird eine eigene
#      Geschichte, mit dem Ordner als Wurzel. Jeder Commit, der das
#      Werkzeug beruehrt hat, kommt mit - "git log" und "git blame"
#      funktionieren im neuen Repository wie hier.
#   2. Auf dieser Geschichte ein letzter Commit: die Dateien, die dem
#      BETRIEB gehoeren, gehen dort weg (override-Datei, sicherung.conf,
#      aktualisierung.conf, geheimnisse.conf; beim Wiki das Bedienhandbuch
#      von proloWorld). Sie bleiben hier.
#   3. git push nach <ziel-url>, Zweig main.
#
# In proloWorld aendert sich dabei NICHTS. Der Werkzeugordner bleibt, wie er
# ist, bis das Abbild veroeffentlicht ist - dann stellt umstellen.sh ihn um.
# Wer zuerst umstellt und dann auslagert, verliert nichts: die Geschichte
# steht im Git. Aber er hat eine Weile ein Werkzeug, das sich nicht bauen
# und nicht holen laesst.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

melde()  { printf '%s\n' "$*"; }
fehler() { printf '%s\n' "$*" >&2; }

W=""; ZIEL=""; TROCKEN=0
for a in "$@"; do
  case "$a" in
    --trocken|-n) TROCKEN=1 ;;
    -*) fehler "Unbekannt: $a"; exit 2 ;;
    *) if [ -z "$W" ]; then W="$a"; elif [ -z "$ZIEL" ]; then ZIEL="$a"
       else fehler "Zu viele Angaben."; exit 2; fi ;;
  esac
done
if [ -z "$W" ] || { [ -z "$ZIEL" ] && [ "$TROCKEN" -eq 0 ]; }; then
  fehler "Aufruf: werkzeuge/auslagern.sh <werkzeug> <ziel-url> [--trocken]"
  fehler "  z. B. werkzeuge/auslagern.sh bordbuch git@github.com:prolo2408/bordbuch.git"
  exit 2
fi

# Die Dateien, die dem Betrieb gehoeren. Sie bleiben in proloWorld.
BETRIEB="docker-compose.override.yml sicherung.conf aktualisierung.conf geheimnisse.conf LIESMICH.md"
# Und was im Werkzeug-Repository nichts verloren hat, obwohl es im Ordner
# lag: das Bedienhandbuch von proloWorld ist eine Wiki-SEITE, aber es
# beschreibt den Betrieb, nicht das Wiki.
case "$W" in wiki) BETRIEB="$BETRIEB vorlagen/prolo-bedienen.html" ;; esac

# --- Vorbedingungen, bevor irgendetwas passiert (§12) ------------------
git -C "$STACK" rev-parse --git-dir >/dev/null 2>&1 \
  || { fehler "$STACK ist kein Git-Arbeitsstand."; exit 1; }
git -C "$STACK" subtree --help >/dev/null 2>&1 \
  || { fehler "'git subtree' fehlt. Auf Debian/Ubuntu gehoert es zu git selbst;"
       fehler "sonst: das Paket git-subtree bzw. git-contrib installieren."; exit 1; }
[ -f "$STACK/$W/Dockerfile" ] && [ -f "$STACK/$W/server.py" ] \
  || { fehler "$W ist kein Werkzeug mit eigenem Code (kein Dockerfile/server.py) -"
       fehler "oder es ist schon ausgelagert."; exit 1; }
for d in CLAUDE.md README.md .github/workflows/abbild.yml tests/test_vertrag.py; do
  [ -f "$STACK/$W/$d" ] || { fehler "$W/$d fehlt - das neue Repository braucht es (U-03)."; exit 1; }
done
if [ -n "$(git -C "$STACK" status --porcelain -- "$W")" ]; then
  fehler "In $W/ liegen nicht eingecheckte Aenderungen:"
  git -C "$STACK" status --short -- "$W" | sed 's/^/  /' >&2
  fehler "Ausgelagert wird die GESCHICHTE - was nicht eingecheckt ist, kaeme"
  fehler "nicht mit. Erst einchecken, dann noch einmal."
  exit 1
fi
if [ "$TROCKEN" -eq 0 ]; then
  if ! REFS=$(git ls-remote "$ZIEL" 2>&1); then
    fehler "Das Ziel ist nicht erreichbar. git sagt:"
    printf '%s\n' "$REFS" | sed 's/^/  /' >&2
    fehler ""
    fehler "Genau dieser Aufruf war es:  git ls-remote $ZIEL"
    exit 1
  fi
  if [ -n "$REFS" ]; then
    fehler "Das Ziel $ZIEL ist nicht leer:"
    printf '%s\n' "$REFS" | head -5 | sed 's/^/  /' >&2
    fehler ""
    fehler "Hier wird nichts ueberschrieben. Das Repository auf GitHub ohne"
    fehler "README, .gitignore und Lizenz neu anlegen - oder, wenn der Inhalt"
    fehler "weg darf, dort von Hand leeren."
    exit 1
  fi
fi

ZWEIG="auslagern/$W"
if git -C "$STACK" rev-parse --verify --quiet "refs/heads/$ZWEIG" >/dev/null; then
  fehler "Den Zweig $ZWEIG gibt es schon - von einem frueheren Versuch."
  fehler "Ansehen:  git -C $STACK log --oneline -3 $ZWEIG"
  fehler "Weg damit, wenn er nicht mehr gebraucht wird:  git -C $STACK branch -D $ZWEIG"
  exit 1
fi

# --- 1. Die Geschichte des Ordners als eigene Geschichte ----------------
melde "Trenne die Geschichte von $W/ heraus ..."
SPLIT_FEHLER=$(mktemp)
git -C "$STACK" subtree split --prefix="$W" -b "$ZWEIG" >/dev/null 2>"$SPLIT_FEHLER" || {
  fehler "git subtree split ist gescheitert:"; sed 's/^/  /' "$SPLIT_FEHLER" >&2
  rm -f "$SPLIT_FEHLER"; exit 1; }
rm -f "$SPLIT_FEHLER"
N=$(git -C "$STACK" rev-list --count "$ZWEIG")
melde "  $N Commits"

# --- 2. Die Betriebsdateien gehen dort weg ------------------------------
BAUM=$(mktemp -d)
aufraeumen() {
  git -C "$STACK" worktree remove --force "$BAUM" >/dev/null 2>&1 || rm -rf "$BAUM"
}
trap aufraeumen EXIT
git -C "$STACK" worktree add -q "$BAUM" "$ZWEIG"
WEG=""
for d in $BETRIEB; do
  if [ -e "$BAUM/$d" ]; then git -C "$BAUM" rm -q -- "$d"; WEG="$WEG $d"; fi
done
if [ -n "$WEG" ]; then
  git -C "$BAUM" \
    -c user.name="$(git -C "$STACK" config user.name || echo prolo)" \
    -c user.email="$(git -C "$STACK" config user.email || echo prolo@localhost)" \
    commit -q -m "Betriebsdateien bleiben in proloWorld

Entfernt:$WEG

Sie gehoeren dem Betrieb (prolo2408/proloWorld), nicht dem Werkzeug:
Netz, Route, Anmeldung, Grenzen, Sicherung und Aktualisierung stehen
dort. Hier steht der Code und die Herstellerdatei docker-compose.yml."
  melde "  entfernt:$WEG"
fi

if [ "$TROCKEN" -eq 1 ]; then
  melde ""
  melde "Trockenlauf - nichts wurde geschoben. So saehe die Wurzel aus:"
  ls -A "$BAUM" | grep -v '^\.git$' | sed 's/^/  /'
  aufraeumen; trap - EXIT
  git -C "$STACK" branch -D -q "$ZWEIG"
  exit 0
fi

# --- 3. Schieben --------------------------------------------------------
melde "Schiebe nach $ZIEL ..."
if ! git -C "$STACK" push -q "$ZIEL" "$ZWEIG:refs/heads/main"; then
  fehler "Das Schieben ist gescheitert (Meldung von git steht oben)."
  fehler "Der Zweig $ZWEIG bleibt fuer einen zweiten Versuch liegen:"
  fehler "  git -C $STACK push $ZIEL $ZWEIG:refs/heads/main"
  exit 1
fi
aufraeumen; trap - EXIT
git -C "$STACK" branch -D -q "$ZWEIG"

FASSUNG=$(python3 "$STACK/$W/server.py" --version 2>/dev/null || echo "?")
cat <<WEITER

$W liegt jetzt in $ZIEL - $N Commits Geschichte.
In proloWorld hat sich nichts geaendert.

Weiter, in dieser Reihenfolge:

  1. Im neuen Repository die erste Fassung veroeffentlichen:
       git clone $ZIEL && cd $W
       git tag v$FASSUNG && git push --tags
     Der Arbeitsablauf baut ghcr.io/prolo2408/$W:$FASSUNG (Actions-Reiter).

  2. Ist das Abbild da, hier umstellen - es entfernt den Code aus
     $W/ und laesst die Betriebsdateien stehen:
       werkzeuge/umstellen.sh $W

  3. Ist das Paket auf ghcr.io privat, muss der Server es holen duerfen,
     einmalig:
       docker login ghcr.io -u prolo2408
     (Passwort: ein Token mit dem Recht read:packages)
WEITER
