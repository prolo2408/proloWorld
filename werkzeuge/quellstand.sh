#!/bin/bash
# werkzeuge/quellstand.sh
#
# Haengt der Stand auf der Platte hinter dem Git zurueck - und wenn ja, holen.
#
# Der Anlass: bei TYP=build baut aktualisieren.sh aus dem, was im Ordner
# liegt. Wer vergisst zu ziehen, baut die alte Fassung neu; docker meldet
# brav "CACHED", am Ende steht FERTIG, und geaendert hat sich nichts. Am
# 15.09.2026 genau so passiert.
#
# Die Pruefung stand danach mitten in aktualisieren.sh - sie lief also nur
# beim Aktualisieren, nicht bei "prolo status" und nicht bei "prolo pruefen",
# und geholt hat sie nie: der Mensch musste "git pull" von Hand tippen. Jetzt
# steht sie einmal hier, und drei Stellen rufen sie (N-38).
#
# Aufruf:
#   quellstand.sh --pruefen   nachsehen und berichten
#   quellstand.sh --holen     nachsehen und, wenn noetig, vorspulen
#   quellstand.sh --kurz      eine Zeile, fuer "prolo status"
#
# Rueckgabe:
#    0  aktuell - nichts zu tun
#   10  hinterher (nur bei --pruefen; bei --holen wird geholt)
#   11  nicht pruefbar: kein git, kein Netz, abgeloester Kopf
#   20  geholt. WICHTIG fuer Aufrufer, die selbst im Repo liegen: sie sind
#       damit moeglicherweise ersetzt worden und muessen neu starten.
#    1  Holen war noetig, ging aber nicht - der Grund steht in der Ausgabe.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
WAS="${1:---pruefen}"

melde() { printf '%s\n' "$*"; }
kurz()  { [ "$WAS" = "--kurz" ]; }
# Bei --kurz genau eine Zeile, sonst der ausfuehrliche Text.
zeile() { kurz && printf '%s\n' "$1"; }
lang()  { kurz || melde "$*"; }

nicht_pruefbar() {
  zeile "nicht pruefbar ($1)"
  lang "  Quellstand         nicht pruefbar ($1)"
  exit 11
}

[ -d "$STACK/.git" ] || nicht_pruefbar "kein Git-Arbeitsstand unter $STACK"
command -v git >/dev/null 2>&1 || nicht_pruefbar "git ist nicht installiert"

# Gehoert der Arbeitsstand einem anderen Nutzer, verweigert git jede Auskunft
# ("dubious ownership") - und das sieht aus wie "kein Netz". Auf dem Server
# gehoert /opt/stack root, und wer ohne sudo nachsieht, laeuft genau darauf zu.
if ! ZWEIG=$(git -C "$STACK" rev-parse --abbrev-ref HEAD 2>&1); then
  case "$ZWEIG" in
    *"dubious ownership"*|*"safe.directory"*)
      zeile "nicht pruefbar (Besitzverhaeltnisse)"
      lang "  Quellstand         nicht pruefbar - git verweigert die Auskunft"
      lang "                     zu $STACK (fremder Besitzer)."
      lang "                     Abhilfe: git config --global --add safe.directory $STACK"
      exit 11 ;;
    *) nicht_pruefbar "git antwortet nicht" ;;
  esac
fi
[ "$ZWEIG" != "HEAD" ] || nicht_pruefbar "abgeloester Kopf - kein Zweig"

# Holen darf fehlschlagen (kein Netz, kein Schluessel). Das ist kein Grund
# abzubrechen, nur einer, nichts zu behaupten.
timeout 20 git -C "$STACK" fetch --quiet origin "$ZWEIG" 2>/dev/null \
  || nicht_pruefbar "kein Zugriff auf origin"

HINTER=$(git -C "$STACK" rev-list --count "HEAD..origin/$ZWEIG" 2>/dev/null || echo 0)
VORAUS=$(git -C "$STACK" rev-list --count "origin/$ZWEIG..HEAD" 2>/dev/null || echo 0)
# Nur GEAENDERTE verfolgte Dateien zaehlen als Hindernis. Unverfolgte ("??")
# stoeren ein Vorspulen nicht - git bricht von sich aus ab, falls eine geholte
# Datei eine von ihnen ueberschreiben wuerde, und diese Meldung geben wir dann
# weiter. Sie mitzuzaehlen hiesse: ein einzelnes vergessenes Notizblatt im
# Ordner blockiert jede Aktualisierung.
SCHMUTZ=$(git -C "$STACK" status --porcelain 2>/dev/null | grep -v '^??' || true)
ANZ_SCHMUTZ=0
[ -n "$SCHMUTZ" ] && ANZ_SCHMUTZ=$(printf '%s\n' "$SCHMUTZ" | wc -l | tr -d ' ')

# Ein Hindernis, das dieses Skript bereits KENNT, gehoert in jede Meldung,
# die einen Weg nennt - nicht erst in die, die man beim Hineinlaufen zu
# sehen bekommt (N-60). "3 Commit(s) hinter origin/main" ist wahr, und
# "git pull" daneben ist richtig - und zusammen fuehren sie in eine Mauer,
# solange die eigene Aenderung verschwiegen wird, an der genau dieses
# git pull abbricht.
#
# Der Weg heraus nennt die KOPIE vor dem Verwerfen, und zwar in dieser
# Reihenfolge: "git checkout --" loescht eigene Arbeit ohne Rueckfrage
# (CLAUDE.md §15). Und er nennt die Datei beim Namen statt <datei> - eine
# Meldung, die den Weg beschreibt, aber nicht die Stelle, ist ein Raetsel
# (N-35).
schmutz_melden() {
  local ERSTE KOPIE
  ERSTE=$(printf '%s\n' "$SCHMUTZ" | head -1 | sed 's/^...//; s/^"//; s/"$//')
  KOPIE="${HOME:-/tmp}/$(basename "$ERSTE").von-hand"
  melde "  BLOCKIERT: im Arbeitsstand liegen eigene Aenderungen an"
  melde "             $ANZ_SCHMUTZ verfolgten Datei(en). Daran bricht jedes Holen ab -"
  melde "             auch ein 'git pull' von Hand."
  melde ""
  printf '%s\n' "$SCHMUTZ" | sed 's/^/             /' | head -12
  melde ""
  melde "             Erst die Kopie, dann verwerfen - in dieser Reihenfolge:"
  melde "               cd $STACK"
  melde "               cp $ERSTE $KOPIE"
  melde "               git checkout -- $ERSTE"
  melde ""
  melde "             Danach erneut holen. Was anders war, zeigt danach:"
  melde "               diff -u $ERSTE $KOPIE"
}

if [ "${HINTER:-0}" -eq 0 ]; then
  if [ "${VORAUS:-0}" -gt 0 ]; then
    zeile "aktuell, $VORAUS Commit(s) noch nicht gepusht (origin/$ZWEIG)"
    lang "  Quellstand         aktuell, aber $VORAUS Commit(s) nur hier"
    lang "                     (noch nicht bei origin/$ZWEIG)"
  else
    zeile "aktuell (origin/$ZWEIG)"
    lang "  Quellstand         aktuell (origin/$ZWEIG)"
  fi
  exit 0
fi

# --- Ab hier: es liegt etwas Neueres bereit ----------------------------
if [ "$ANZ_SCHMUTZ" -gt 0 ]; then
  zeile "$HINTER Commit(s) hinter origin/$ZWEIG - Holen blockiert ($ANZ_SCHMUTZ geaenderte Datei(en))"
else
  zeile "$HINTER Commit(s) hinter origin/$ZWEIG"
fi
lang "  Quellstand         $HINTER Commit(s) HINTER origin/$ZWEIG"
if ! kurz; then
  melde ""
  git -C "$STACK" log --oneline "HEAD..origin/$ZWEIG" 2>/dev/null \
    | sed 's/^/                     /' | head -10
  melde ""
fi
kurz && exit 10

if [ "$WAS" = "--pruefen" ]; then
  melde "  ACHTUNG: es liegt eine neuere Fassung bereit, die hier noch nicht"
  melde "           ausgecheckt ist. Bei eigenem Code (TYP=build) wuerde jetzt"
  melde "           die ALTE Fassung neu gebaut - docker meldet dabei CACHED,"
  melde "           und am Ende staende FERTIG, obwohl sich nichts geaendert"
  melde "           hat."
  melde ""
  if [ "$ANZ_SCHMUTZ" -gt 0 ]; then
    schmutz_melden
  else
    melde "           Holen:  prolo quelle --holen"
    melde "                   (oder: cd $STACK && git pull origin $ZWEIG)"
  fi
  exit 10
fi

# --- --holen ------------------------------------------------------------
# Zwei Faelle, in denen NICHT geholt wird. Beide enden mit dem Weg heraus,
# nicht mit einem stillen Fehlschlag: ein Skript, das eigene Arbeit
# wegraeumt, ist schlimmer als eins, das nichts tut (CLAUDE.md §15).
if [ -n "$SCHMUTZ" ]; then
  melde "  NICHT geholt - aus demselben Grund, an dem auch ein 'git pull'"
  melde "  von Hand abbricht:"
  melde ""
  schmutz_melden
  exit 1
fi
if [ "${VORAUS:-0}" -gt 0 ]; then
  melde "  NICHT geholt: der Zweig ist $VORAUS Commit(s) voraus UND $HINTER"
  melde "                zurueck - die Staende sind auseinandergelaufen."
  melde ""
  melde "           Vorspulen geht dann nicht, und selbst zusammenfuehren"
  melde "           soll dieses Skript nicht. Von Hand entscheiden:"
  melde "             cd $STACK && git log --oneline --graph --all -12"
  exit 1
fi

melde "  Holen ... (git pull --ff-only origin $ZWEIG)"
if ! AUSGABE=$(git -C "$STACK" pull --ff-only --quiet origin "$ZWEIG" 2>&1); then
  melde "  FEHLER beim Holen:"
  printf '%s\n' "$AUSGABE" | sed 's/^/                     /' | head -10
  exit 1
fi
NEU=$(git -C "$STACK" rev-parse --short HEAD 2>/dev/null)
melde "  Geholt: $HINTER Commit(s), Stand jetzt $NEU."
exit 20
