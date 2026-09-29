#!/bin/bash
# werkzeuge/aktualisieren.sh
#
# Zentrales Aktualisierungsskript (CLAUDE.md §24).
#
# Aufruf:
#   aktualisieren.sh <tool> [<tool> ...]   ein oder mehrere Tools
#   aktualisieren.sh --alle                alle gefundenen Tools
#   aktualisieren.sh --liste               nur auflisten, nichts tun
#   aktualisieren.sh --trocken <tool>      Ablauf zeigen, nichts anfassen
#   aktualisieren.sh --ohne-sicherung ...  Ausnahme, siehe unten
#   aktualisieren.sh --ohne-holen ...      baut den Stand auf der Platte,
#                                          auch wenn origin weiter ist
#
# Der Kern des Entwurfs: im Skript steht KEIN Toolname. Tools werden am
# Dateisystem erkannt, alles Tool-eigene steht in der jeweiligen
# aktualisierung.conf. Ein neues Tool braucht damit keine Zeile hier.
#
# Abweichungen vom Entwurf in CLAUDE.md §24, jede aus einem konkreten
# Fehler heraus:
#
#   1. Container werden ueber "docker compose ps -q" gefunden, nicht ueber
#      den Toolnamen. Der Entwurf machte "docker inspect $TOOL" - fuer
#      authentik gibt es aber ueberhaupt keinen Container "authentik",
#      sondern authentik-db, authentik-server und authentik-worker. Der
#      Entwurf waere dort immer mit "Container laeuft nicht" gescheitert.
#
#   2. Zurueckgerollt wird ueber eine Kopie der docker-compose.yml, nicht
#      ueber sed. Der Entwurf machte
#      sed -i "s|image:.*|image: $ALT|" - das trifft JEDE image-Zeile.
#      Bei authentik (drei Abbilder) haette es alle drei auf das Abbild der
#      Datenbank gesetzt und die Datei zerstoert.
#
#   3. Geprueft wird zuerst ueber die Gesundheitspruefung des Containers und
#      nur ersatzweise ueber PRUEF_URL. Der Entwurf holte dafuer
#      curlimages/curl:latest - ein latest-Abbild, was CLAUDE.md §19
#      gerade verbietet, bei jedem Lauf neu geladen und im internen Netz von
#      socket-proxy gar nicht erreichbar. Bordbuch, Wiki und Authentik haben
#      eine eigene Gesundheitspruefung; die ist naeher an der Wahrheit.
#
#   4. PRUEF_WARTEN ist eine Obergrenze, kein fester Schlaf. Gewartet wird,
#      bis der Container gesund ist - im Erfolgsfall Sekunden statt immer
#      die vollen 20 oder 30.
#
#   5. Der Rueckbezug stammt vom letzten ERFOLGREICHEN Lauf, nicht vom
#      Dateistand beim Start. Das ist der wichtigste Unterschied. Bei
#      TYP=image traegt man die neue Fassung selbst in die
#      docker-compose.yml ein und startet DANN das Skript. Der Entwurf las
#      seine Rueckfallfassung aber genau dort aus ("ALT=$(grep image: ...)"
#      vor dem pull) - also die schon eingetragene neue Nummer. Sein
#      sed-Zurueckrollen schrieb damit die Fassung zurueck, die eben
#      gescheitert war: ein Zurueckrollen, das nichts zurueckrollt.
#      Darum wird hier nach jedem Erfolg eine Kopie als
#      .stand-erfolgreich.yml abgelegt, und nur die gilt als Rueckweg.
set -euo pipefail

# Pfade aus dem Skriptort ableiten, nicht festschreiben: so laeuft es auch
# aus einem Klon heraus, nicht nur unter /opt/stack.
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
SICHERUNG="$STACK/backup.sh"
# Dieselbe Sperre wie "prolo start" (N-85). Ohne sie ging eine
# Herstellerdatei, die ihre ports:-Zeile zurueckbringt, mit einem
# Aktualisierungslauf ungehindert ins offene Netz.
# shellcheck source=werkzeuge/startsperre.sh
. "$HIER/startsperre.sh"

TROCKEN=0
OHNE_SICHERUNG=0
OHNE_HOLEN=0

# ----------------------------------------------------------------------
# Hilfsmittel
# ----------------------------------------------------------------------
melde()  { printf '%s\n' "$*"; }

eingerueckt() {
  # Mehrzeiliges einruecken. printf '  %s\n' "$mehrzeilig" rueckt NUR die
  # erste Zeile ein, unquotiert zerfaellt es an Leerzeichen - beides schon
  # passiert. Darum zeilenweise.
  local zeile
  while IFS= read -r zeile; do
    [ -n "$zeile" ] && printf '        %s\n' "$zeile"
  done <<< "$1"
}
abschnitt() { printf '\n=== %s ===\n' "$*"; }

tools_finden() {
  # Ein Tool ist ein Ordner mit docker-compose.yml. Nichts weiter.
  local d
  for d in "$STACK"/*/docker-compose.yml; do
    [ -e "$d" ] || continue
    basename "$(dirname "$d")"
  done
}

tun() {
  # Jede Aenderung laeuft hierueber, damit --trocken ueberall wirkt.
  if [ "$TROCKEN" -eq 1 ]; then melde "      [trocken] $*"; return 0; fi
  "$@"
}

abbild_kennungen() {
  # Die Kennungen (sha256) aller Abbilder dieses Tools, sortiert. Leer,
  # wenn noch keines da ist - dann gilt es als "neu".
  docker compose config --images 2>/dev/null | sort | while IFS= read -r a; do
    [ -n "$a" ] && docker image inspect "$a" --format '{{.Id}}' 2>/dev/null || echo "fehlt:$a"
  done
}

container_kennungen() {
  # Alle Container dieses Werkzeugs, auch angehaltene, sortiert. Ein
  # Container, den "up -d" NEU anlegt, bekommt eine neue Kennung - daran
  # und nur daran sieht man, ob sich etwas geaendert hat (N-88).
  docker compose ps -a -q 2>/dev/null | sort
}

# ----------------------------------------------------------------------
# Ein Tool aktualisieren. Gibt 0 bei Erfolg, 1 bei Fehlschlag.
# ----------------------------------------------------------------------
ein_tool() {
  local TOOL="$1"
  local ORDNER="$STACK/$TOOL"

  abschnitt "$TOOL aktualisieren"

  if [ ! -f "$ORDNER/docker-compose.yml" ]; then
    melde "ABBRUCH: $ORDNER/docker-compose.yml fehlt."
    return 1
  fi

  # Vorgaben - bewusst so, dass ein Tool ohne conf trotzdem laeuft.
  local TYP="image" PRUEF_URL="" PRUEF_WARTEN=30 HAUPT=""
  if [ -f "$ORDNER/aktualisierung.conf" ]; then
    # shellcheck disable=SC1090
    . "$ORDNER/aktualisierung.conf"
  else
    melde "HINWEIS: keine aktualisierung.conf - CLAUDE.md §16 verlangt sie."
    melde "         Es gilt: TYP=image, keine URL-Pruefung, ${PRUEF_WARTEN}s Grenze."
  fi

  # --- Rueckweg sichern, BEVOR etwas passiert --------------------------
  # Die image-Zeilen dienen nur der Anzeige und dem Protokoll. Der echte
  # Rueckweg ist die Kopie der Datei: die stimmt auch bei mehreren Diensten.
  # Der Kommentar HINTER dem Abbild muss weg, sonst zerfaellt "image: x:1
  # # feste Fassung" in sechs Woerter. Und die Ausgabe laeuft ueber eine
  # Schleife statt ueber printf mit unquotiertem $ABBILDER - sonst trennt die
  # Shell erneut an Leerzeichen.
  local ABBILDER
  ABBILDER=$(grep -E '^[[:space:]]*image:' "$ORDNER/docker-compose.yml" \
             | sed -e 's/^[[:space:]]*image:[[:space:]]*//' \
                   -e 's/[[:space:]]*#.*$//' \
                   -e 's/[[:space:]]*$//' \
             | tr -d '"' || true)
  if [ -z "$ABBILDER" ]; then
    melde "ABBRUCH: in $ORDNER/docker-compose.yml fehlt eine image:-Zeile."
    melde "         Ohne sie gibt es keinen Rueckweg (CLAUDE.md §19, B-23)."
    melde "         Auch bei eigenem Dockerfile gehoert sie dazu -"
    melde "         'build: .' UND 'image: <tool>:<fassung>'."
    return 1
  fi
  melde "[1/4] Eingetragene Fassung:"
  eingerueckt "$ABBILDER"

  # Der Rueckweg ist der Stand des letzten ERFOLGREICHEN Laufs - nicht der
  # Stand von jetzt. Siehe Punkt 5 im Kopf.
  local RUECKWEG="$ORDNER/.stand-erfolgreich.yml"
  if [ -f "$RUECKWEG" ]; then
    melde "      Rueckweg vorhanden (letzter erfolgreicher Lauf):"
    eingerueckt "$(grep -E '^[[:space:]]*image:' "$RUECKWEG" \
      | sed -e 's/^[[:space:]]*image:[[:space:]]*//' -e 's/[[:space:]]*#.*$//' \
      | tr -d '"')"
  else
    melde "      KEIN Rueckweg: dieses Tool wurde mit diesem Skript noch nie"
    melde "      erfolgreich aktualisiert. Geht es schief, fuehrt der Weg"
    melde "      zurueck ueber git (siehe Meldung am Ende)."
  fi

  cd "$ORDNER"

  # --- Sperre, BEVOR etwas geholt oder gestartet wird (N-85) ------------
  # Ein offener Port oder ein Router ohne Anmeldung wird gar nicht erst
  # losgelassen. Kein Zurueckrollen: es ist nichts passiert, und die
  # laufenden Container bleiben, wie sie waren.
  if [ "$TROCKEN" -eq 0 ] && ! start_pruefen "$TOOL"; then
    melde ""
    melde "ABBRUCH: $TOOL wurde NICHT aktualisiert - Grund steht oben."
    melde "         Was laeuft, laeuft weiter wie vorher."
    return 1
  fi

  # --- Neue Fassung holen und vergleichen ------------------------------
  # Erst nachsehen, OB es etwas Neues gibt. Vorher wurde jedes Tool bei
  # jedem Lauf neu gestartet, auch wenn sich nichts geaendert hatte - das
  # ist unnoetige Unterbrechung fuer nichts.
  #
  # Verglichen werden die Abbild-Kennungen vor und nach dem Holen bzw.
  # Bauen. Das ist genauer als ein Blick auf die Versionsnummer: es faengt
  # auch ein neu gebautes Abbild aus geaendertem Quellcode.
  melde "[2/4] Sehe nach, ob es etwas Neues gibt (TYP=$TYP) ..."
  local VORHER NACHHER
  VORHER=$(abbild_kennungen)
  if [ "$TYP" = "build" ]; then
    tun docker compose build --pull
  else
    tun docker compose pull
  fi
  NACHHER=$(abbild_kennungen)

  if [ "$TROCKEN" -eq 0 ] && [ "$VORHER" != "$NACHHER" ]; then
    melde "      Neue Abbilder vorhanden."
  fi

  # "docker compose up -d" laeuft IMMER (N-88). Es ist von sich aus
  # sparsam: Compose legt nur neu an, was sich geaendert hat - Abbild ODER
  # Konfiguration -, und laesst alles andere laufen. Eine eigene
  # Entscheidung davor ist ueberfluessig und war falsch: sie las die
  # Tabelle von "docker compose ps" nach "created", und das steht in
  # JEDER Kopfzeile (Spalte CREATED). Mit echtem Docker kam darum nie
  # "kein Neustart noetig" heraus - der Zweig war tot, und die Attrappe
  # im Pruefskript, die keine Kopfzeile druckte, hat es verdeckt.
  #
  # Ob etwas neu angelegt wurde, sagen die Container-Kennungen vorher und
  # nachher - gemessen, nicht vorhergesagt.
  local IDS_VORHER IDS_NACHHER NEU_ANGELEGT=1
  IDS_VORHER=$(container_kennungen)
  melde "[3/4] docker compose up -d ..."
  tun docker compose up -d
  IDS_NACHHER=$(container_kennungen)
  if [ "$TROCKEN" -eq 0 ] && [ -n "$IDS_VORHER" ] && [ "$IDS_VORHER" = "$IDS_NACHHER" ]; then
    NEU_ANGELEGT=0
    melde "      Nichts neu angelegt - Abbilder und Konfiguration sind"
    melde "      unveraendert, die Container laufen weiter wie vorher."
  fi

  # Geprueft wird IMMER - auch wenn nichts neu gestartet wurde.
  #
  # Ein frueherer Entwurf sprang hier heraus und meldete "ist aktuell",
  # sobald sich die Abbilder nicht geaendert hatten und die Container
  # liefen. Die Gegenprobe hat das sofort aufgedeckt: ein Container kann
  # laufen UND ungesund sein. "Laeuft" ist nicht "tut, was es soll" - genau
  # der Unterschied, an dem N-05 haengt. Ohne Neustart zu pruefen kostet
  # ein paar Sekunden und faengt einen Dienst, der seit dem letzten Lauf
  # stillschweigend kaputtgegangen ist.

  # --- Pruefen --------------------------------------------------------
  melde "[4/4] Pruefe, hoechstens ${PRUEF_WARTEN}s ..."
  if [ "$TROCKEN" -eq 1 ]; then melde "      [trocken] uebersprungen"; return 0; fi

  if pruefen "$TOOL" "$PRUEF_WARTEN" "$PRUEF_URL" "$HAUPT"; then
    melde ""
    if [ "$NEU_ANGELEGT" -eq 0 ]; then
      melde "FERTIG. $TOOL ist aktuell und laeuft."
    else
      melde "FERTIG. $TOOL laeuft."
      docker compose logs --tail 10
    fi
    # Erst JETZT wird der Stand zum Rueckweg fuer das naechste Mal.
    cp "$ORDNER/docker-compose.yml" "$ORDNER/.stand-erfolgreich.yml"
    printf '%s\n' "$ABBILDER" > "$ORDNER/.letzte-fassung"
    return 0
  fi

  melde ""
  melde "!!! FEHLGESCHLAGEN - $TOOL wird zurueckgerollt."
  docker compose logs --tail 40
  zurueckrollen "$TOOL" "$ORDNER" "$TYP"
  return 1
}

# ----------------------------------------------------------------------
# Pruefung: erst laufen alle Container, dann Gesundheit, dann ersatzweise URL.
# ----------------------------------------------------------------------
pruefen() {
  local TOOL="$1" GRENZE="$2" URL="$3" HAUPT="$4"
  local IDS ENDE JETZT

  IDS=$(docker compose ps -q || true)
  if [ -z "$IDS" ]; then
    melde "  FEHLER: kein Container laeuft (docker compose ps ist leer)."
    return 1
  fi

  ENDE=$(( $(date +%s) + GRENZE ))
  while :; do
    local alles_gut=1 id zustand gesund neustarts name
    for id in $IDS; do
      name=$(docker inspect "$id" --format '{{.Name}}' | sed 's|^/||')
      zustand=$(docker inspect "$id" --format '{{.State.Status}}')
      gesund=$(docker inspect "$id" \
               --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}ohne{{end}}')
      neustarts=$(docker inspect "$id" --format '{{.RestartCount}}')

      if [ "$zustand" != "running" ]; then alles_gut=0; fi
      if [ "$gesund" = "unhealthy" ]; then alles_gut=0; fi
      if [ "$gesund" = "starting" ]; then alles_gut=0; fi
      if [ "$neustarts" -gt 2 ]; then
        melde "  FEHLER: $name startet staendig neu ($neustarts Neustarts)."
        return 1
      fi
    done
    [ "$alles_gut" -eq 1 ] && break

    JETZT=$(date +%s)
    if [ "$JETZT" -ge "$ENDE" ]; then
      melde "  FEHLER: nach ${GRENZE}s nicht bereit. Stand:"
      for id in $IDS; do
        docker inspect "$id" --format \
          '        {{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}ohne Gesundheitspruefung{{end}}'
      done
      return 1
    fi
    sleep 2
  done

  # Wie viele Container haben eine eigene Gesundheitspruefung?
  local mit_pruefung=0 id
  for id in $IDS; do
    if [ "$(docker inspect "$id" --format '{{if .State.Health}}ja{{else}}nein{{end}}')" = "ja" ]; then
      mit_pruefung=$((mit_pruefung + 1))
    fi
  done
  melde "      alle Container laufen, $mit_pruefung mit eigener Gesundheitspruefung."

  # PRUEF_URL ist der Ersatz, wenn es keine Gesundheitspruefung gibt - und
  # eine zusaetzliche Zusicherung, wenn doch eine da ist.
  if [ -n "$URL" ]; then
    [ -z "$HAUPT" ] && HAUPT=$(docker inspect "$(echo "$IDS" | head -1)" \
                               --format '{{.Name}}' | sed 's|^/||')
    melde "      pruefe $URL aus dem Netz von $HAUPT ..."
    # Im Netz des Containers selbst: dann stimmen Namensaufloesung UND
    # 127.0.0.1, ohne Annahme ueber das Netz. Feste Fassung, kein latest.
    if docker run --rm --network "container:$HAUPT" \
         curlimages/curl:8.11.1 -sf -o /dev/null --max-time 10 "$URL"; then
      melde "      $URL antwortet."
    else
      melde "  FEHLER: $URL antwortet nicht."
      return 1
    fi
  elif [ "$mit_pruefung" -eq 0 ]; then
    melde "      HINWEIS: weder Gesundheitspruefung noch PRUEF_URL - es ist"
    melde "               nur belegt, dass der Container laeuft."
  fi
  return 0
}

# ----------------------------------------------------------------------
# Zurueckrollen: die alte docker-compose.yml zurueck und neu starten.
# ----------------------------------------------------------------------
zurueckrollen() {
  local TOOL="$1" ORDNER="$2" TYP="$3"
  local RUECKWEG="$ORDNER/.stand-erfolgreich.yml"

  if [ ! -f "$RUECKWEG" ]; then
    melde "Kein automatischer Rueckweg: es gibt keinen Stand aus einem"
    melde "frueheren erfolgreichen Lauf ($RUECKWEG fehlt)."
    melde "Die docker-compose.yml bleibt unangetastet, damit nichts"
    melde "Halbfertiges entsteht. Zurueck geht es ueber git:"
    melde "  cd $STACK && git log --oneline -5 -- $TOOL"
    melde "  git checkout <alter-commit> -- $TOOL"
    melde "  cd $ORDNER && docker compose up -d$([ "$TYP" = "build" ] && echo " --build")"
    return 1
  fi

  cp "$RUECKWEG" "$ORDNER/docker-compose.yml"
  melde "docker-compose.yml auf den letzten erfolgreichen Stand zurueck:"
  eingerueckt "$(grep -E '^[[:space:]]*image:' "$ORDNER/docker-compose.yml" \
    | sed -e 's/^[[:space:]]*image:[[:space:]]*//' -e 's/[[:space:]]*#.*$//' \
    | tr -d '"')"

  if [ "$TYP" = "build" ]; then
    # Bei eigenem Code steckt die Fassung im Quellcode, nicht in der
    # image-Zeile. Die Datei allein bringt das alte Verhalten nicht zurueck.
    melde ""
    melde "ACHTUNG: eigenes Abbild. Die docker-compose.yml ist zurueck, das"
    melde "ABBILD aber nicht - das entsteht aus dem Quellcode. Dafuer:"
    melde "  cd $STACK && git log --oneline -5 -- $TOOL"
    melde "  git checkout <alter-commit> -- $TOOL"
    melde "  cd $ORDNER && docker compose up -d --build"
    docker compose up -d || true
  else
    docker compose up -d
  fi
  melde ""
  melde "ACHTUNG: hat die neue Fassung die Datenbank schon migriert, reicht"
  melde "das Zurueckrollen nicht. Dann die Sicherung einspielen -"
  melde "CLAUDE.md §23 und 22. Bordbuch legt zusaetzlich eine Kopie"
  melde "neben die Datenbank (.vor-stand-<n>), siehe B-13."
}

# ----------------------------------------------------------------------
# Aufruf auswerten
# ----------------------------------------------------------------------
verwendung() {
  melde "Aufruf: $(basename "$0") <tool> [<tool> ...] | --alle | --liste"
  melde "        $(basename "$0") --trocken <tool>    zeigt nur, was passieren wuerde"
  melde "        $(basename "$0") --ohne-sicherung <tool>"
  melde "              laesst die Sicherung aus. Nur, wenn nachweislich eine"
  melde "              aktuelle da ist - z. B. weil backup.sh nur am fehlenden"
  melde "              age-Schluessel gescheitert ist."
  melde ""
  melde "Gefundene Tools in $STACK:"
  local t
  for t in $(tools_finden); do
    printf '  - %-14s %s\n' "$t" \
      "$([ -f "$STACK/$t/aktualisierung.conf" ] && echo "" || echo "(ohne aktualisierung.conf)")"
  done
}

# Die urspruenglichen Argumente merken, um sie in Meldungen vorschlagen zu
# koennen ("sudo ... --ohne-sicherung <dieselben Tools>").
URSPRUNG="$*"

ZIELE=()
# Dieselben Argumente noch einmal, aber als Feld: nach einem Holen startet das
# Skript neu (exec), und dafuer muss jedes Argument einzeln erhalten bleiben.
# NICHT in URSPRUNG hineinschreiben - das ist oben eine Zeichenkette fuer
# Meldungen, und ein Feld darin haette sie auf ihr erstes Wort verkuerzt.
AUFRUF=("$@")

while [ $# -gt 0 ]; do
  case "$1" in
    --alle)    mapfile -t ZIELE < <(tools_finden) ;;
    --liste)   verwendung; exit 0 ;;
    --trocken) TROCKEN=1 ;;
    --ohne-sicherung) OHNE_SICHERUNG=1 ;;
    --ohne-holen)     OHNE_HOLEN=1 ;;
    -h|--help) verwendung; exit 0 ;;
    -*)        melde "Unbekannte Option: $1"; verwendung; exit 1 ;;
    *)         ZIELE+=("$1") ;;
  esac
  shift
done

if [ "${#ZIELE[@]}" -eq 0 ]; then verwendung; exit 1; fi

# Reihenfolge ist nicht beliebig: socket-proxy legt das Netz an, das Traefik
# braucht (B-02), und Traefik muss stehen, bevor die Tools dahinter kommen.
# Darum wird eine --alle-Liste sortiert, statt sie alphabetisch zu nehmen.
REIHENFOLGE=(socket-proxy traefik authentik)
sortiert=()
for v in "${REIHENFOLGE[@]}"; do
  for z in "${ZIELE[@]}"; do [ "$z" = "$v" ] && sortiert+=("$z"); done
done
for z in "${ZIELE[@]}"; do
  drin=0
  for v in "${REIHENFOLGE[@]}"; do [ "$z" = "$v" ] && drin=1; done
  [ "$drin" -eq 0 ] && sortiert+=("$z")
done
ZIELE=("${sortiert[@]}")

melde "Tools in dieser Reihenfolge: ${ZIELE[*]}"
[ "$TROCKEN" -eq 1 ] && melde "(Trockenlauf - es wird nichts geaendert)"

# ----------------------------------------------------------------------
# Rechte pruefen, BEVOR irgendetwas laeuft.
#
# Ohne root scheitert alles Wesentliche - docker, /opt/backups, die
# Sicherung -, aber jeweils erst mittendrin und mit einer Meldung, die nach
# einem ganz anderen Problem aussieht ("permission denied while trying to
# connect to the docker API"). Lieber vorher einmal klar.
# ----------------------------------------------------------------------
if [ "$TROCKEN" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
  melde ""
  melde "ABBRUCH: das Skript braucht root."
  melde "         docker, /opt/backups und backup.sh sind sonst nicht"
  melde "         erreichbar - der Lauf wuerde mittendrin scheitern, mit"
  melde "         Meldungen, die nach einem anderen Problem aussehen"
  melde "         (\"permission denied ... docker API\")."
  melde ""
  melde "         sudo $0 $URSPRUNG"
  exit 1
fi

# ----------------------------------------------------------------------
# Vorpruefung: Voraussetzungen klaeren, BEVOR die Sicherung laeuft.
#
# Der Anlass: backup.sh endet mit einem Fehler, wenn age fehlt oder der
# Schluessel nicht da ist - und damit bricht die Aktualisierung ab, mit
# einer Meldung, die man erst lesen und dann von Hand abarbeiten muss.
# Was sich sicher selbst beheben laesst, wird hier behoben; alles andere
# wird so genau benannt, dass ein einziger Befehl reicht.
# ----------------------------------------------------------------------
vorpruefung() {
  local FEHLT=0
  melde ""
  melde "[Vorpruefung]"

  if ! docker info >/dev/null 2>&1; then
    melde "  FEHLER: docker antwortet nicht. Laeuft der Dienst?"
    melde "          sudo systemctl status docker"
    return 1
  fi
  melde "  docker             erreichbar"

  # age: fehlt es, wird es nachinstalliert. Das ist der eine Fall, den das
  # Skript selbst geradebiegen darf - ein Paket aus der Distribution, ohne
  # Auswirkung auf laufende Dienste.
  if command -v age >/dev/null 2>&1; then
    melde "  age                vorhanden"
  else
    melde "  age                fehlt - wird nachinstalliert ..."
    if apt-get install -y -qq age >/dev/null 2>&1 || \
       { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq age >/dev/null 2>&1; }; then
      melde "                     erledigt ($(age --version 2>&1 | head -1))"
    else
      melde "  FEHLER: age liess sich nicht installieren."
      melde "          Von Hand: sudo apt update && sudo apt install age"
      FEHLT=1
    fi
  fi

  # Der Schluessel laesst sich NICHT selbst erzeugen: der private Teil
  # gehoert auf den Arbeitsrechner, nicht hierher (CLAUDE.md §23).
  # Ein Skript, das ihn hier anlegt, macht die Verschluesselung wertlos.
  local SCHL="$STACK/.backup-schluessel.pub"
  if [ ! -f "$SCHL" ]; then
    melde "  FEHLER: $SCHL fehlt."
    melde "          Er kann hier NICHT erzeugt werden - der private Teil"
    melde "          gehoert auf den Arbeitsrechner (CLAUDE.md §23)."
    melde "          Dort:  age-keygen -o ~/.age/prolo.key"
    melde "          Dann:  den age1...-Teil hierher in $SCHL"
    FEHLT=1
  elif [ ! -s "$SCHL" ]; then
    melde "  FEHLER: $SCHL ist LEER."
    melde "          Das passiert, wenn ein 'grep | tee' nichts gefunden hat."
    melde "          Loeschen und den age1...-Teil neu eintragen."
    FEHLT=1
  elif ! grep -q '^age1' "$SCHL"; then
    melde "  FEHLER: in $SCHL steht keine age1...-Zeile."
    FEHLT=1
  else
    melde "  Sicherungsschluessel  vorhanden"
  fi

  # Ist der Quellstand ueberhaupt aktuell? Die Pruefung stand bis N-38 hier
  # mitten im Skript - sie lief damit nur beim Aktualisieren, nicht bei
  # "prolo status" und nicht bei "prolo pruefen". Jetzt steht sie einmal in
  # werkzeuge/quellstand.sh, und drei Stellen rufen dieselbe.
  if [ -x "$HIER/quellstand.sh" ]; then
    # Das "|| QS=$?" ist nicht Zierde: dieses Skript laeuft mit set -e, und
    # quellstand.sh meldet seine Lage ueber den Rueckgabewert (10 = hinterher,
    # 11 = nicht pruefbar). Ohne das || waere schon die Auskunft ein Abbruch -
    # gemessen genau so passiert, der Lauf endete stumm nach dem Holen.
    local QS=0
    "$HIER/quellstand.sh" --pruefen || QS=$?
    [ "$QS" -ne 10 ] || [ "$OHNE_HOLEN" -eq 1 ] || FEHLT=1
  fi

  [ "$FEHLT" -eq 0 ] || return 1
  return 0
}

# ----------------------------------------------------------------------
# Den neuen Stand selbst holen, BEVOR gebaut wird (N-38).
#
# Vorher meldete das Skript nur "N Commit(s) HINTER origin" und brach ab -
# holen musste der Mensch von Hand. Das war jedes Mal derselbe Griff, und
# genau solche Griffe vergisst man.
#
# Nicht geholt wird bei --trocken (der darf nichts anfassen) und bei
# --ohne-holen (wer bewusst den Stand auf der Platte baut).
# ----------------------------------------------------------------------
if [ "$TROCKEN" -eq 0 ] && [ "$OHNE_HOLEN" -eq 0 ] && [ -x "$HIER/quellstand.sh" ]; then
  abschnitt "Quellstand"
  # Siehe vorpruefung: set -e wuerde den Lauf hier beenden, weil "geholt"
  # als Rueckgabewert 20 kommt.
  HOL_ERGEBNIS=0
  "$HIER/quellstand.sh" --holen || HOL_ERGEBNIS=$?
  if [ "$HOL_ERGEBNIS" -eq 20 ]; then
    # Der Pull kann DIESES Skript ersetzt haben. Bash liest ein Skript
    # haeppchenweise von der Platte - weiterlaufen hiesse, halb die alte und
    # halb die neue Fassung auszufuehren. Also neu starten, und zwar genau
    # einmal: die Marke verhindert eine Schleife, falls origin waehrend des
    # Laufs weiterwandert.
    if [ "${PROLO_NACH_HOLEN:-0}" -eq 0 ]; then
      melde "  Neustart mit dem geholten Stand ..."
      export PROLO_NACH_HOLEN=1
      exec "$0" "${AUFRUF[@]}"
    fi
    melde "  (schon einmal geholt - es wird nicht wieder neu gestartet)"
  elif [ "$HOL_ERGEBNIS" -eq 1 ]; then
    melde ""
    melde "ABBRUCH: der neuere Stand liess sich nicht holen. Nichts wurde"
    melde "         angefasst. Wer den Stand auf der Platte bewusst bauen"
    melde "         will, ruft mit --ohne-holen auf."
    exit 1
  fi
fi

if [ "$TROCKEN" -eq 0 ] && [ "$OHNE_SICHERUNG" -eq 0 ]; then
  if ! vorpruefung; then
    melde ""
    melde "ABBRUCH: die Voraussetzungen stimmen nicht. Nichts wurde angefasst."
    exit 1
  fi
fi

# ----------------------------------------------------------------------
# Sicherung: EINMAL fuer den ganzen Lauf.
#
# backup.sh sichert immer den gesamten Stack, nicht ein einzelnes Tool.
# Sie je Tool aufzurufen hiess bei --alle: sechs vollstaendige Sicherungen
# hintereinander, und im Fehlerfall sechsmal dieselbe Meldung.
# ----------------------------------------------------------------------
if [ "$TROCKEN" -eq 1 ]; then
  melde ""
  melde "[Sicherung] [trocken] $SICHERUNG"
elif [ "$OHNE_SICHERUNG" -eq 1 ]; then
  melde ""
  melde "[Sicherung] UEBERSPRUNGEN (--ohne-sicherung)."
  melde "            Das ist die Ausnahme, nicht der Normalfall. B-04 hat"
  melde "            gezeigt, dass eine Migration nicht umkehrbar sein kann."
elif [ ! -x "$SICHERUNG" ]; then
  melde ""
  melde "ABBRUCH: $SICHERUNG fehlt oder ist nicht ausfuehrbar."
  exit 1
else
  melde ""
  melde "[Sicherung] laeuft fuer den ganzen Stack ..."
  if ! "$SICHERUNG"; then
    melde ""
    melde "ABBRUCH: die Sicherung endete mit einem Fehler."
    melde "         Ohne belegte Sicherung wird nicht aktualisiert."
    melde ""
    melde "         Die Meldungen von backup.sh stehen oben - dort steht,"
    melde "         WAS fehlgeschlagen ist. Zwei haeufige Faelle:"
    melde ""
    melde "         - \"permission denied ... docker API\" oder \"Operation not"
    melde "           permitted\": das Skript laeuft ohne root. Mit sudo neu."
    melde "         - \"age ist nicht installiert\" oder \"kein Schluessel\":"
    melde "           die Sicherung liegt da, nur unverschluesselt."
    melde "           Pruefen: ls -la /opt/backups/ | tail -5"
    melde "                    ls -la /opt/stack/.backup-schluessel.pub"
    melde "                    command -v age || echo 'apt install age'"
    melde ""
    melde "         Ist der Grund geklaert und die Sicherung nachweislich da:"
    melde "           sudo $0 --ohne-sicherung $URSPRUNG"
    exit 1
  fi
  melde "            erledigt."
fi

FEHLGESCHLAGEN=()
for t in "${ZIELE[@]}"; do
  if ! ein_tool "$t"; then FEHLGESCHLAGEN+=("$t"); fi
done

abschnitt "Ergebnis"
if [ "${#FEHLGESCHLAGEN[@]}" -eq 0 ]; then
  melde "Alle Tools sind aktualisiert: ${ZIELE[*]}"
  exit 0
fi
melde "Fehlgeschlagen: ${FEHLGESCHLAGEN[*]}"
melde "Die uebrigen sind durch. Protokoll oben lesen, bevor erneut gestartet wird."
exit 1
