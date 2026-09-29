#!/usr/bin/env bash
# werkzeuge/einrichten-pruefen.sh
#
# Tut "prolo einrichten" wirklich nur das, was noch fehlt? (N-54)
#
# Das ist die einzige Eigenschaft, auf die es bei diesem Skript ankommt.
# Ein Einrichtungsskript, das beim zweiten Lauf etwas ueberschreibt, ist
# gefaehrlicher als gar keines: man ruft es arglos auf, weil "es tut ja
# nur, was fehlt" - und verliert eine .env.
#
# Gearbeitet wird auf einer KOPIE im Kratzblock, mit einer Docker-Attrappe
# auf dem PATH. Nie am echten Stack: eine Probe, die zurueckrollt, nimmt
# eine noch nicht eingecheckte Korrektur mit (N-34).
#
#   ./werkzeuge/einrichten-pruefen.sh
#   ./werkzeuge/einrichten-pruefen.sh --gegenprobe
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
GEGENPROBE=0
[ "${1:-}" = "--gegenprobe" ] && GEGENPROBE=1

FEHLER=0
sag() { if [ "$1" = "ok" ]; then printf 'ok     %s\n' "$2"
        else printf 'FEHLER %s\n' "$2"; [ -n "${3:-}" ] && printf '       -> %s\n' "$3"
             FEHLER=1; fi; }

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

# --- Docker-Attrappe: merkt sich Netze und laufende Dienste in Dateien,
#     damit "schon da" beim zweiten Lauf auch wirklich schon da ist.
mkdir -p "$T/bin"
cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
N="$DOCKER_ATTRAPPE/netze"; L="$DOCKER_ATTRAPPE/laufen"
touch "$N" "$L"
V="$DOCKER_ATTRAPPE/verbunden"; touch "$V"
case "$1 $2" in
  "network inspect") grep -qx "$3" "$N" && exit 0 || exit 1 ;;
  "network create")  echo "$3" >> "$N"; echo "id-$3"; exit 0 ;;
  "compose version") echo "Docker Compose version v2.0.0"; exit 0 ;;
esac
# docker inspect <id> --format '...Networks...'  -> die Netze des Containers
if [ "$1" = "inspect" ]; then
  case "$*" in
    *Networks*) sed -n "s/^${2#c-} //p" "$V"; exit 0 ;;
    *) echo healthy; exit 0 ;;
  esac
fi
# "compose config" misst die Sperre (N-85). Es braucht keinen laufenden
# Dienst, also geht es ans echte docker - wie in neu-pruefen.sh.
if [ "$1" = "compose" ] && [ "$2" = "config" ]; then exec /usr/bin/docker "$@"; fi
if [ "$1" = "compose" ]; then
  DIR="$PWD"
  for i in "$@"; do case "$VOR" in --project-directory) DIR="$i" ;; esac; VOR="$i"; done
  case " $* " in
    *" ps "*) grep -qx "$(basename "$DIR")" "$L" && echo "c-$(basename "$DIR")"; exit 0 ;;
    *" up "*)
      W=$(basename "$DIR")
      # N-90: so scheitert ein echtes "up" beim ersten Start - erst
      # Fortschritt, ganz unten die Ursache.
      if [ "$W" = "ohnesocket" ]; then
        printf ' Image fremd/x:1 Pulling \n 7e8a Pulling fs layer\n 7e8a Download complete\n' >&2
        echo "network socket declared as external, but could not be found" >&2
        exit 1
      fi
      grep -qx "$W" "$L" || echo "$W" >> "$L"
      # "up -d" verbindet den Container mit allen erklaerten Netzen -
      # genau das, was echtes compose tut, wenn sich die Netze geaendert haben.
      sed -i "/^$W /d" "$V"
      for NZ in $(cat "$DIR/docker-compose.yml" "$DIR/docker-compose.override.yml" 2>/dev/null \
                  | grep -A50 '^networks:' \
                  | sed -n 's/^  \([A-Za-z0-9_.-]*\):$/\1/p' | sort -u); do
        echo "$W $NZ" >> "$V"
      done
      exit 0 ;;
  esac
fi
[ "$1" = "inspect" ] && { echo healthy; exit 0; }
exit 0
STUB
chmod +x "$T/bin/docker"
export DOCKER_ATTRAPPE="$T/att"; mkdir -p "$DOCKER_ATTRAPPE"

# --- Kopie des Stacks: nur, was das Skript liest
kopieren() {
  local Z="$1"; mkdir -p "$Z/werkzeuge"
  cp "$HIER/einrichten.sh" "$HIER/geheimnisse.py" "$HIER/prolo" \
     "$HIER/startsperre.sh" "$HIER/netze.sh" "$Z/werkzeuge/"
  local D
  for D in "$STACK"/*/docker-compose.yml; do
    [ -e "$D" ] || continue
    local W; W=$(basename "$(dirname "$D")")
    mkdir -p "$Z/$W"; cp "$D" "$Z/$W/"
    [ -f "$STACK/$W/docker-compose.override.yml" ] \
      && cp "$STACK/$W/docker-compose.override.yml" "$Z/$W/"
    [ -f "$STACK/$W/geheimnisse.conf" ] && cp "$STACK/$W/geheimnisse.conf" "$Z/$W/"
    [ -f "$STACK/$W/.env.beispiel" ] && cp "$STACK/$W/.env.beispiel" "$Z/$W/"
    if [ -f "$STACK/$W/dynamic/einlass.yml.beispiel" ]; then
      mkdir -p "$Z/$W/dynamic"
      cp "$STACK/$W/dynamic/einlass.yml.beispiel" "$Z/$W/dynamic/"
    fi
  done
  # Ein Fremdwerkzeug, dessen Netz und Name NUR in der override-Datei
  # stehen - und dessen Netz Traefik (noch) nicht nennt. Genau so sieht
  # ein Werkzeug aus, das "prolo neu" gerade angelegt hat (N-83). n8n
  # taugt dafuer nicht: sein Netz steht zusaetzlich bei Traefik und wuerde
  # darueber angelegt, auch wenn die override-Datei ungelesen bliebe.
  mkdir -p "$Z/fremdprobe"
  cat > "$Z/fremdprobe/docker-compose.yml" <<'YML'
services:
  fremdprobe:
    image: fremd/probe:1.0
YML
  cat > "$Z/fremdprobe/docker-compose.override.yml" <<'YML'
services:
  fremdprobe:
    networks:
      - netz-fremdprobe
    labels:
      - "traefik.http.routers.fremdprobe.rule=Host(`fremdprobe.prolo.me`)"
networks:
  netz-fremdprobe:
    external: true
YML
  # N-91: die sicherung.conf von Traefik und die Dateien aus dem Git, die
  # er einhaengt. acme.json und log/ entstehen erst auf dem Server.
  cp "$STACK/traefik/sicherung.conf" "$Z/traefik/"
  cp "$STACK/traefik/traefik.yml" "$Z/traefik/"
  # Ein Werkzeug, das eine Konfigurationsdatei einhaengt, die FEHLT - das
  # darf nicht still als leerer Ordner entstehen.
  mkdir -p "$Z/ohnekonf"
  printf 'services:\n  ohnekonf:\n    image: x:1\n    volumes:\n      - ./wichtig.yml:/etc/wichtig.yml:ro\n' \
    > "$Z/ohnekonf/docker-compose.yml"
  # Ein Werkzeug, dessen Start an einem fehlenden Netz scheitert (N-90).
  mkdir -p "$Z/ohnesocket"
  printf 'services:\n  ohnesocket:\n    image: fremd/x:1\n' > "$Z/ohnesocket/docker-compose.yml"
  # Ein Werkzeug mit einem unerklaerten offenen Port (N-85). Die Sperre
  # aus "prolo start" muss auch beim Einrichten greifen.
  mkdir -p "$Z/offenport"
  cat > "$Z/offenport/docker-compose.yml" <<'YML'
services:
  offenport:
    image: fremd/offen:1.0
    ports:
      - "8099:80"
YML
  # Sicherungsschluessel, sonst kommt Schritt 7 nicht dran
  age-keygen 2>/dev/null > "$Z/probe.key"
  grep '^# public key:' "$Z/probe.key" | cut -d' ' -f4 > "$Z/.backup-schluessel.pub"
}

lauf() {  # lauf <wurzel> [--trocken]
  ( cd "$1" && PATH="$T/bin:$PATH" HOME="$1" \
      bash "$1/werkzeuge/einrichten.sh" ${2:-} < /dev/null 2>&1 )
}

pruefen_einmal() {
  local W="$1"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"

  local A1 R1
  A1=$(lauf "$W"); R1=$?
  echo "$A1" > "$W/lauf1.txt"

  grep -q "getan" <<<"$A1" && sag ok "erster Lauf richtet wirklich etwas ein" \
    || sag FEHLER "erster Lauf hat nichts getan" "dann prueft der zweite nichts"

  # Alles, was da sein muss, ist da
  local FEHLT=0 W2
  for W2 in "$W"/*/geheimnisse.conf; do
    [ -e "$W2" ] || continue
    local ORD; ORD=$(dirname "$W2")
    while IFS='|' read -r NAME DATEI REST; do
      case "$NAME" in ''|\#*) continue ;; esac
      [ -f "$ORD/$DATEI" ] || { echo "       fehlt: $ORD/$DATEI"; FEHLT=1; }
    done < "$W2"
  done
  [ "$FEHLT" -eq 0 ] && sag ok "jede erklaerte Geheimnisdatei ist angelegt" \
    || sag FEHLER "eine erklaerte Geheimnisdatei fehlt nach dem Lauf"

  # Die Marke steht ueberall gleich
  local WERTE
  WERTE=$(PATH="$T/bin:$PATH" python3 "$W/werkzeuge/geheimnisse.py" 2>&1 \
          | grep "PROLO_EINLASS " | head -1)
  grep -q "gleich an allen" <<<"$WERTE" \
    && sag ok "die Einlassmarke steht an allen Stellen gleich" \
    || sag FEHLER "die Einlassmarke steht nicht ueberall gleich" "$WERTE"

  # --- Der Kern: zweiter Lauf
  local VORHER NACHHER A2
  VORHER=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  A2=$(lauf "$W"); echo "$A2" > "$W/lauf2.txt"
  NACHHER=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)

  [ "$VORHER" = "$NACHHER" ] \
    && sag ok "zweiter Lauf laesst jede Datei byteweise, wie sie war" \
    || sag FEHLER "zweiter Lauf hat eine Datei veraendert" \
           "genau das darf ein Einrichtungsskript nie"

  grep -q "getan" <<<"$A2" \
    && sag FEHLER "zweiter Lauf meldet noch 'getan'" "es sollte nichts mehr zu tun geben" \
    || sag ok "zweiter Lauf tut nichts mehr"

  grep -q "steht schon an allen" <<<"$A2" \
    && sag ok "zweiter Lauf erkennt das Geheimnis als vollstaendig" \
    || sag FEHLER "zweiter Lauf erkennt das vorhandene Geheimnis nicht"

  # --- Der Fall aus der Praxis: Traefik laeuft schon, das Netz kommt
  # spaeter (N-58). Von aussen sah das aus wie "Gateway Timeout".
  sed -i "/^traefik /d" "$DOCKER_ATTRAPPE/verbunden"
  echo "traefik altes-netz" >> "$DOCKER_ATTRAPPE/verbunden"
  local A4
  A4=$(lauf "$W")
  grep -q "traefik neu verbunden" <<<"$A4" \
    && sag ok "ein laufender Traefik wird in ein neues Netz nachgehaengt" \
    || sag FEHLER "ein neues Netz erreicht einen laufenden Container nicht" \
           "genau so entsteht ein Gateway Timeout: Traefik kennt das Netz des Werkzeugs nicht"
  grep -q "^traefik netz-wiki$" "$DOCKER_ATTRAPPE/verbunden" \
    && sag ok "danach haengt Traefik wirklich im Werkzeugnetz" \
    || sag FEHLER "Traefik haengt danach immer noch nicht im Werkzeugnetz"
  # Und beim naechsten Lauf ist wieder Ruhe.
  local A5; A5=$(lauf "$W")
  grep -q "traefik neu verbunden" <<<"$A5" \
    && sag FEHLER "haengt bei jedem Lauf neu" "das waere kein 'nur was fehlt'" \
    || sag ok "beim naechsten Lauf wird nichts mehr nachgehaengt"

  # Das selbst angelegte Netz darf er nicht anfassen
  grep -qx "socket" "$DOCKER_ATTRAPPE/netze" \
    && sag FEHLER "hat 'socket' von Hand angelegt" \
           "socket-proxy legt es selbst an, internal:true - von Hand waere es ein Bridge-Netz" \
    || sag ok "das selbst erzeugte Netz 'socket' bleibt unangetastet"

  grep -qx "netz-wiki" "$DOCKER_ATTRAPPE/netze" \
    && sag ok "die externen netz-* wurden angelegt" \
    || sag FEHLER "netz-wiki wurde nicht angelegt"

  # N-85: ein offener Port wird auch beim Einrichten nicht losgelassen.
  grep -qx "offenport" "$DOCKER_ATTRAPPE/laufen" \
    && sag FEHLER "einrichten hat einen Dienst mit offenem Port gestartet" \
           "genau das verweigert prolo start - die Sperre stand nur an einer Tuer" \
    || sag ok "ein offener Port wird auch beim Einrichten nicht gestartet (N-85)"
  grep -q "offenport NICHT gestartet" "$W/lauf1.txt" \
    && grep -q "8099" "$W/lauf1.txt" \
    && sag ok "und es wird gesagt, warum - mit dem Port" \
    || sag FEHLER "der Grund fuer das Nicht-Starten fehlt in der Ausgabe"

  # N-91: acme.json ist eine DATEI mit 0600, log/ ein Ordner - nicht das,
  # was Docker aus einer fehlenden Quelle macht.
  [ -f "$W/traefik/acme.json" ] && [ "$(stat -c %a "$W/traefik/acme.json")" = 600 ] \
    && sag ok "acme.json ist eine Datei mit 0600 (N-91)" \
    || sag FEHLER "acme.json ist keine Datei mit 0600" \
           "dann legt Docker einen Ordner an, und Traefik holt kein Zertifikat"
  [ -d "$W/traefik/log" ] && sag ok "log/ ist ein Ordner" || sag FEHLER "log/ fehlt"
  grep -q "ohnekonf/wichtig.yml fehlt" "$W/lauf1.txt" \
    && sag ok "eine fehlende Konfigurationsdatei wird gemeldet, nicht erfunden" \
    || sag FEHLER "eine fehlende Konfigurationsdatei wird nicht gemeldet"
  [ -e "$W/ohnekonf/wichtig.yml" ] \
    && sag FEHLER "eine fehlende Konfigurationsdatei wurde angelegt" "leer ist sie falsch, nicht fehlend" \
    || sag ok "und nicht angelegt"
  # Das Ueberbleibsel eines frueheren Starts: ein leerer ORDNER acme.json.
  rm -f "$W/traefik/acme.json"; mkdir "$W/traefik/acme.json"
  lauf "$W" > "$W/lauf-acme.txt"
  [ -f "$W/traefik/acme.json" ] && [ "$(stat -c %a "$W/traefik/acme.json")" = 600 ] \
    && sag ok "ein leerer Ordner acme.json wird durch eine Datei ersetzt" \
    || sag FEHLER "der leere Ordner acme.json bleibt stehen"
  # Und einer mit Inhalt wird NICHT angefasst.
  rm -f "$W/traefik/acme.json"; mkdir "$W/traefik/acme.json"; echo x > "$W/traefik/acme.json/drin"
  lauf "$W" > "$W/lauf-acme2.txt"
  [ -f "$W/traefik/acme.json/drin" ] \
    && sag ok "ein Ordner mit Inhalt wird nicht angefasst" \
    || sag FEHLER "ein Ordner mit Inhalt wurde geloescht"
  rm -rf "$W/traefik/acme.json"; : > "$W/traefik/acme.json"; chmod 600 "$W/traefik/acme.json"

  # N-90: warum etwas nicht hochkam, steht da - im Wortlaut von docker,
  # ohne das Rauschen davor, und mit dem Weg daraus.
  grep -q "network socket declared as external, but could not be found" "$W/lauf1.txt" \
    && sag ok "der Grund steht im Wortlaut von docker da (N-90)" \
    || sag FEHLER "der Grund, warum ein Dienst nicht hochkam, fehlt" \
           "vorher: 'sudo prolo protokoll' - das zeigt bei einem nie angelegten Container nichts"
  grep -q "fs layer" "$W/lauf1.txt" \
    && sag FEHLER "der Fortschritt von docker steht in der Meldung" "Rauschen verdeckt die Ursache" \
    || sag ok "und ohne den Fortschritt davor"
  grep -q "muss socket-proxy zuerst" "$W/lauf1.txt" \
    && sag ok "und mit dem Weg daraus" \
    || sag FEHLER "der Weg aus einem fehlenden Netz fehlt"

  # N-95: die Gruppen kommen aus den Werkzeugen - auch "admin", die in der
  # alten, festen Liste fehlte.
  grep -qE "^    admin +admin " "$W/lauf1.txt" \
    && sag ok "die Gruppe der Admin-Seite wird genannt (N-95)" \
    || sag FEHLER "die Gruppe 'admin' fehlt in der Liste" \
           "dann legt sie niemand an, und die Admin-Seite weist mit 403 ab"
  N_SOLL=$(grep -ho 'prolo\.gruppen=[^"]*' "$W"/*/docker-compose.yml "$W"/*/docker-compose.override.yml 2>/dev/null \
           | sed 's/^prolo\.gruppen=//' | tr ';' '\n' | grep -c '=')
  N_IST=$(sed -n '/Gruppen in Authentik anlegen/,/Ohne die Gruppe/p' "$W/lauf1.txt" | grep -cE '^    [a-z0-9-]+ ')
  [ "$N_SOLL" -gt 0 ] && [ "$N_SOLL" -eq "$N_IST" ] \
    && sag ok "alle $N_SOLL erklaerten Gruppen stehen in der Liste" \
    || sag FEHLER "die Liste nennt $N_IST von $N_SOLL erklaerten Gruppen"

  # N-83: was nur in der override-Datei steht, zaehlt genauso.
  grep -qx "netz-fremdprobe" "$DOCKER_ATTRAPPE/netze" \
    && sag ok "ein Netz aus der override-Datei wird angelegt (N-83)" \
    || sag FEHLER "das Netz aus der override-Datei wurde nicht angelegt" \
           "ein Fremdwerkzeug bekaeme auf einem frischen Server einen toten Router"
  grep -q "^    fremdprobe.prolo.me$" "$W/lauf1.txt" \
    && sag ok "ein Name aus der override-Datei steht in der DNS-Liste (N-83)" \
    || sag FEHLER "der Name aus der override-Datei fehlt in der DNS-Liste" \
           "dann fehlt beim Anbieter der A-Eintrag, und niemand weiss es"
  # Und jeder Name aus IRGENDEINER Compose-Datei - gezaehlt mit grep, nicht
  # mit dem Code, der geprueft wird.
  local N_SOLL N_IST
  N_SOLL=$(cat "$W"/*/docker-compose.yml "$W"/*/docker-compose.override.yml 2>/dev/null \
           | grep -o 'Host(`[^`]*`)' | sort -u | wc -l)
  N_IST=$(grep -c '^    [a-z0-9.-]*\.[a-z]*$' "$W/lauf1.txt")
  [ "$N_SOLL" -eq "$N_IST" ] \
    && sag ok "die DNS-Liste nennt alle $N_SOLL Namen aus den Compose-Dateien" \
    || sag FEHLER "die DNS-Liste nennt $N_IST von $N_SOLL Namen"

  # Ein Trockenlauf fasst nichts an
  local V3 N3
  V3=$(find "$W" -name '.env' | sort | xargs md5sum 2>/dev/null)
  lauf "$W" --trocken > /dev/null
  N3=$(find "$W" -name '.env' | sort | xargs md5sum 2>/dev/null)
  [ "$V3" = "$N3" ] && sag ok "--trocken fasst keine Datei an" \
    || sag FEHLER "--trocken hat etwas veraendert"
}

if [ "$GEGENPROBE" -eq 0 ]; then
  pruefen_einmal "$T/stack"
  echo
  [ "$FEHLER" -eq 0 ] && echo "Alles gruen." || echo "EINRICHTUNGSPRUEFUNG FEHLGESCHLAGEN." >&2
  exit "$FEHLER"
fi

# ---------------------------------------------------------- Gegenprobe
echo "Gegenprobe: jede eingebaute Schwaeche muss auffallen."
echo
GEFUNDEN=0; DURCH=""
probe() {   # probe "Name" "sed-Ausdruck auf einrichten.sh"
  local NAME="$1" AUSDRUCK="$2" W="$T/m$((++GEFUNDEN))"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  local ALT NEU A
  lauf "$W" > /dev/null                       # erster Lauf
  ALT=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  A=$(lauf "$W")                               # zweiter Lauf
  NEU=$(find "$W" -name '.env' -o -name 'einlass.yml' | sort | xargs md5sum 2>/dev/null)
  if [ "$ALT" != "$NEU" ] || grep -q "getan" <<<"$A"; then
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  else
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"
    DURCH="$DURCH$NAME; "
  fi
}

probe "die .env wird immer neu aus der Vorlage kopiert" \
      's|elif \[ -f "$PFAD" \]; then|elif false; then|'
probe "die fehlende Zeile wird immer angehaengt" \
      's|&& ! grep -q "\^$NAME=" "$PFAD"|\&\& true|'

# Die Probe zu N-58 braucht einen anderen Massstab als die beiden oben:
# hier geht es nicht um Dateien, sondern darum, ob ein laufender Container
# in ein neues Netz nachgehaengt wird.
netzprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/n$((++GEFUNDEN))"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  lauf "$W" > /dev/null
  sed -i "/^traefik /d" "$DOCKER_ATTRAPPE/verbunden"
  echo "traefik altes-netz" >> "$DOCKER_ATTRAPPE/verbunden"
  lauf "$W" > /dev/null
  if grep -q "^traefik netz-wiki$" "$DOCKER_ATTRAPPE/verbunden"; then
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  else
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  fi
}
netzprobe "ein laufender Container wird nie nachgehaengt" \
          's|FEHLT=$(netze_fehlen "$T")|FEHLT=""|'
netzprobe "fehlende Netze werden gar nicht erst gesucht" \
          's|^netze_fehlen() {|netze_fehlen() { return 0;|'

# N-83: die override-Datei wird nicht gelesen - weder fuer Netze noch fuer
# Namen. Der Massstab ist, was nach dem Lauf fehlt.
# N-85: die Sperre fehlt beim Einrichten. Massstab: laeuft der Dienst mit
# dem offenen Port nach dem Lauf?
sperrprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/s$((++GEFUNDEN))"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  lauf "$W" > /dev/null
  if grep -qx "offenport" "$DOCKER_ATTRAPPE/laufen"; then
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  else
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  fi
}
sperrprobe "einrichten startet ohne die Sperre" \
  '0,/if ! SPERRE=$(start_pruefen "$T" 2>\&1); then/! s|if ! SPERRE=$(start_pruefen "$T" 2>\&1); then|if false; then|'

# N-90: der Grund wird wieder verschluckt.
meldeprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/g$((++GEFUNDEN))" A
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  A=$(lauf "$W")
  if grep -q "network socket declared as external" <<<"$A" && ! grep -q "fs layer" <<<"$A"; then
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  else
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  fi
}
meldeprobe "die Meldung von docker wird verschluckt" \
  's|^    docker_sagt "$T" "$AUSGABE"$|    :|'
meldeprobe "das Rauschen wird nicht herausgefiltert" \
  "s#^RAUSCHEN=.*#RAUSCHEN='NIEMALS-SO-EINE-ZEILE'#"

# N-91: acme.json wird nicht vorbereitet.
acmeprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/a$((++GEFUNDEN))"
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  mkdir -p "$W/traefik/acme.json"      # wie nach einem frueheren Start
  lauf "$W" > /dev/null
  if [ -f "$W/traefik/acme.json" ] && [ "$(stat -c %a "$W/traefik/acme.json")" = 600 ]; then
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  else
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  fi
}
acmeprobe "der leere Ordner acme.json bleibt stehen (N-91)" \
  's#^    elif \[ -d "$Z" \] \&\& \[ -z "$(ls -A "$Z")" \]; then$#    elif false; then#'
acmeprobe "acme.json wird ohne 0600 angelegt (N-91)" \
  's#: > "$Z" \&\& chmod 600 "$Z" \&\& f_tat "$W/$P angelegt#: > "$Z" \&\& f_tat "$W/$P angelegt#; s#rmdir "$Z" \&\& : > "$Z" \&\& chmod 600 "$Z"#rmdir "$Z" \&\& : > "$Z"#'

# N-95: die Gruppen kommen nicht aus den Werkzeugen.
gruppenprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/r$((++GEFUNDEN))" A
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  A=$(lauf "$W")
  if grep -qE "^    admin +admin " <<<"$A"; then
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  else
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  fi
}
gruppenprobe "die Gruppen stehen nicht mehr in der Liste (N-95)" \
  's#^if zeilen:$#if False:#'
gruppenprobe "das Label prolo.gruppen wird nicht gelesen (N-95)" \
  's#for m in re.finditer(r"prolo\\.gruppen=#for m in [] or re.finditer(r"NIE-prolo\\.gruppen=#'

overrideprobe() {
  local NAME="$1" AUSDRUCK="$2" W="$T/o$((++GEFUNDEN))" A
  rm -rf "$DOCKER_ATTRAPPE"; mkdir -p "$DOCKER_ATTRAPPE"
  kopieren "$W"
  sed -i "$AUSDRUCK" "$W/werkzeuge/einrichten.sh"
  A=$(lauf "$W")
  if grep -qx "netz-fremdprobe" "$DOCKER_ATTRAPPE/netze" \
     && grep -q "^    fremdprobe.prolo.me$" <<<"$A"; then
    printf '%2d. %-46s DURCHGERUTSCHT\n' "$GEFUNDEN" "$NAME"; DURCH="$DURCH$NAME; "
  else
    printf '%2d. %-46s gefunden\n' "$GEFUNDEN" "$NAME"
  fi
}
overrideprobe "Namen nur aus der Datei des Herstellers" \
  '0,/"docker-compose.yml", "docker-compose.override.yml"/! s|("docker-compose.yml", "docker-compose.override.yml")|("docker-compose.yml",)|'
overrideprobe "Netze nur aus der Datei des Herstellers" \
  '0,/"docker-compose.yml", "docker-compose.override.yml"/ s|("docker-compose.yml", "docker-compose.override.yml")|("docker-compose.yml",)|'

echo
if [ -n "$DURCH" ]; then
  echo "Durchgerutscht: $DURCH"
  echo "Das ist eine Testluecke, keine Meinungsfrage (§13a)."
  exit 1
fi
echo "Alle $GEFUNDEN Schwaechen wurden gefunden."
