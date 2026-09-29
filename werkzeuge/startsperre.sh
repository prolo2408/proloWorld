#!/bin/bash
# werkzeuge/startsperre.sh
#
# Wird GELESEN, nicht ausgefuehrt:  . "$HIER/startsperre.sh"
# Erwartet $STACK (Stapelwurzel) und $HIER (werkzeuge/) beim Aufrufer.
#
# Warum eine eigene Datei (N-85): drei Wege lassen einen Dienst los -
#   prolo start          (werkzeuge/prolo)
#   prolo aktualisieren  (werkzeuge/aktualisieren.sh)
#   prolo einrichten     (werkzeuge/einrichten.sh)
# und bis N-85 kannte nur der erste die Sperre. Eine Herstellerdatei, die
# mit einer neuen Fassung ihre ports:-Zeile zurueckbringt, ging mit
# "prolo aktualisieren" ungehindert ins offene Netz - auf genau dem Weg,
# den man fuer den sicheren haelt, weil er sichert und zurueckrollt.
#
# Eine Sperre, die nur an einer von drei Tueren steht, ist eine Empfehlung.

sperre_fehler() { printf '%s\n' "$*" >&2; }

# Bevor etwas losgelassen wird: zwei Dinge, die man einem Werkzeug von
# aussen nicht ansieht und die beide den ganzen Schutz aufheben (N-61).
#
#   1. Eine veroeffentlichte ports:-Zeile. Damit ist der Dienst an Traefik,
#      an der Anmeldung UND an der Firewall vorbei erreichbar (§19). Bei
#      einem Fremdwerkzeug bringt der Hersteller sie fast immer mit - und
#      unsere override-Datei kann sie nicht wieder wegnehmen, Compose
#      haengt Listen aneinander.
#   2. Ein Router ohne Anmeldung und ohne Erklaerung. Ein fehlendes
#      middlewares= sieht genauso aus wie ein vergessenes (N-59).
#
# Gemessen wird an der ZUSAMMENGESETZTEN Konfiguration ("docker compose
# config"), nicht an einer Datei - sonst sieht die Pruefung die Haelfte.
#
# Das ist eine Sperre in den gefuehrten Wegen, nicht in Docker: wer es
# wirklich will, kann immer noch "cd <ordner> && docker compose up -d"
# tippen. Die gefuehrten Wege sollen nur nicht die sein, auf denen man aus
# Versehen einen Dienst ins offene Netz stellt.
start_pruefen() {
  local TOOL="$1" Z T D NN TN SCHUTZ PORTS GRUND GETEILT HOSTS OFFENR FEHLT=0

  if grep -q 'PROLO-PLATZHALTER' "$STACK/$TOOL/docker-compose.yml" 2>/dev/null; then
    sperre_fehler "NICHT gestartet: in $TOOL/docker-compose.yml steht noch der"
    sperre_fehler "Platzhalter von 'prolo neu'."
    sperre_fehler ""
    sperre_fehler "  Die docker-compose.yml des Herstellers gehoert dort hinein,"
    sperre_fehler "  ihre ports:-Zeile weg, und dann die Zeile PROLO-PLATZHALTER"
    sperre_fehler "  loeschen. Das Warum steht in $TOOL/LIESMICH.md."
    return 1
  fi

  [ -x "$HIER/netze.sh" ] || return 0
  while IFS='|' read -r Z T D NN TN SCHUTZ PORTS GRUND GETEILT HOSTS OFFENR; do
    [ "$Z" = dienst ] || continue
    if [ -n "$PORTS" ] && [ -z "$GRUND" ]; then
      sperre_fehler "NICHT gestartet: $TOOL/$D veroeffentlicht Port(s) $PORTS auf dem Host."
      sperre_fehler ""
      sperre_fehler "  Damit waere der Dienst an Traefik, an der Anmeldung und an der"
      sperre_fehler "  Firewall vorbei erreichbar (CLAUDE.md §19). Erreichbar bleibt"
      sperre_fehler "  er ueber seinen Hostnamen - das macht Traefik."
      sperre_fehler ""
      sperre_fehler "  Abhilfe: die ports:-Zeile in $TOOL/docker-compose.yml entfernen."
      sperre_fehler "  Muss sie wirklich sein, wird sie erklaert:"
      sperre_fehler "    labels: [ \"prolo.ports=<warum>\" ]"
      FEHLT=1
    fi
    if [ "$SCHUTZ" = OFFEN ]; then
      # Den Router beim Namen nennen, nicht das Werkzeug (N-84): bei zwei
      # Routern ist der ungeschuetzte oft gerade NICHT der, der so heisst
      # wie das Werkzeug.
      local R="${OFFENR%%,*}"
      case "$R" in ""|"(Vorgabe)") R="$TOOL" ;; esac
      sperre_fehler "NICHT gestartet: $TOOL/$D hat einen Router ohne Anmeldung: ${OFFENR:-?}"
      sperre_fehler ""
      sperre_fehler "  Entweder Authentik davor:"
      sperre_fehler "    - \"traefik.http.routers.$R.middlewares=authentik@file\""
      sperre_fehler "  oder - wenn das Werkzeug seine eigene Anmeldung mitbringt -"
      sperre_fehler "  erklaert (CLAUDE.md §17a):"
      sperre_fehler "    - \"prolo.anmeldung=eigene\""
      sperre_fehler "    - \"prolo.anmeldung.grund=<warum>\""
      sperre_fehler "  oder - wenn genau dieser Router oeffentlich sein soll:"
      sperre_fehler "    - \"prolo.oeffentlich=$R\""
      FEHLT=1
    fi
  done < <("$HIER/netze.sh" --dienste "$TOOL" 2>/dev/null)
  return "$FEHLT"
}

