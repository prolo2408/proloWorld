#!/usr/bin/env bash
# werkzeuge/neu-pruefen.sh
#
# Gegenprobe fuer "prolo neu" und "prolo netze" (N-61, N-62).
#
# Baut einen Stack aus Attrappen in einem Wegwerfordner auf und faelscht
# "docker" auf dem PATH. Die Attrappe reicht "docker compose config" an das
# ECHTE docker durch - das braucht keinen laufenden Dienst und ist damit
# die einzige Stelle, an der hier wirklich gemessen wird statt nachgebaut.
#
# Geprueft wird die WIRKUNG, nicht die Ankuendigung (N-38): dass die Datei
# hinterher dasteht, dass die zusammengesetzte Konfiguration das Netz und
# die Labels traegt, dass ein Netz an BEIDEN Stellen in der Traefik-Datei
# landet, und dass "prolo start" das ablehnt, was es ablehnen soll.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
S="$T/stack"

FEHLER=0
pruefe() {
  local name="$1" erwartet="$2" ist="$3"
  if [ "$ist" = "$erwartet" ]; then printf 'ok     %s\n' "$name"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$name" "$erwartet" "$ist"
       FEHLER=1; fi
}
enthaelt() { printf '%s' "$2" | grep -qF -- "$1" && echo ja || echo nein; }
passt()    { printf '%s' "$2" | grep -qE -- "$1" && echo ja || echo nein; }

# --- Docker-Attrappe ----------------------------------------------------
mkdir -p "$T/bin"
: > "$T/netze"
cat > "$T/bin/docker" <<'STUB'
#!/bin/bash
# Attrappe. "compose config" geht ans echte docker - das braucht keinen
# Dienst und liefert die wahre zusammengesetzte Konfiguration.
NETZE="${DOCKER_NETZE:?}"
# DOCKER_TOT=1 heisst: der Docker-Dienst antwortet gar nicht. Dann darf
# auch nichts mehr gehen - eine Attrappe, die nicht auflisten, aber noch
# anlegen kann, gibt es in der Wirklichkeit nicht.
[ "${DOCKER_TOT:-0}" = 1 ] && [ "$1" != compose ] && exit 1
case "$1" in
  compose)
    if [ "$2" = config ]; then exec /usr/bin/docker "$@"; fi
    [ "$2" = ps ] && exit 0
    exit 0 ;;
  network)
    case "$2" in
      ls)      cat "$NETZE"; printf 'bridge\nhost\nnone\n'; exit 0 ;;
      create)  grep -qx "$3" "$NETZE" && exit 1
               printf '%s\n' "$3" >> "$NETZE"; echo "$3"; exit 0 ;;
      rm)      grep -v -x "$3" "$NETZE" > "$NETZE.n" && mv "$NETZE.n" "$NETZE"
               echo "$3"; exit 0 ;;
      inspect) if [ "$3" = -f ]; then grep -qx "$5" "$NETZE" || exit 1; echo 0; exit 0; fi
               grep -qx "$3" "$NETZE" || exit 1
               echo '[]'; exit 0 ;;
    esac
    exit 1 ;;
  inspect) exit 1 ;;
esac
exit 1
STUB
chmod +x "$T/bin/docker"
export DOCKER_NETZE="$T/netze"
export PATH="$T/bin:$PATH"

# --- Attrappen-Stack ----------------------------------------------------
mkdir -p "$S/werkzeuge" "$S/traefik"
cp "$HIER/prolo" "$HIER/neu.sh" "$HIER/netze.sh" "$S/werkzeuge/"

# Einstieg fuer die Mutationsprobe (werkzeuge/neu-gegenprobe.py). Sie baut
# ihre Fehler in die KOPIEN im Wegwerfordner ein, nie in die Dateien im
# Arbeitsstand - damit kann eine Probe die eigene Arbeit nicht loeschen
# (N-34, N-60).
[ -z "${PROLO_MUTATION:-}" ] || python3 "$PROLO_MUTATION" "$S/werkzeuge" || {
  echo "FEHLER Mutation liess sich nicht einbauen" >&2; exit 3; }
cat > "$S/traefik/docker-compose.yml" <<'Y'
services:
  traefik:
    image: traefik:v3.6.13
    container_name: traefik
    labels:
      - "prolo.ports=Eingang des Stacks"
    ports:
      - "80:80"
    networks:
      - netz-alt
      - socket

networks:
  netz-alt:
    external: true
  socket:
    external: true
Y
printf 'netz-alt\nsocket\n' > "$T/netze"
NEU="$S/werkzeuge/neu.sh"
NETZE="$S/werkzeuge/netze.sh"
PROLO="$S/werkzeuge/prolo"

echo "== 1. Ein Fremdwerkzeug anlegen =========================================="
A=$("$NEU" fremd1 --art fremd --abbild vaultwarden/server:1.34.1 --dienst vaultwarden \
      --port 80 --netz-neu --anmeldung eigene --grund "API und Handy-App" </dev/null 2>&1); R=$?
pruefe "anlegen: Rueckgabe 0" "0" "$R"
for D in docker-compose.yml docker-compose.override.yml sicherung.conf \
         aktualisierung.conf .gitignore LIESMICH.md; do
  pruefe "anlegen: $D liegt da" "ja" "$([ -f "$S/fremd1/$D" ] && echo ja || echo nein)"
done
pruefe "anlegen: KEIN Dockerfile (das ist Sache des Herstellers)" "nein" \
       "$([ -f "$S/fremd1/Dockerfile" ] && echo ja || echo nein)"

# Die Wirkung, nicht die Datei: was kommt zusammengesetzt heraus?
K=$(cd "$S/fremd1" && docker compose config --no-interpolate 2>&1)
pruefe "wirkung: das Netz steht in der Konfiguration" "ja" "$(enthaelt "netz-fremd1" "$K")"
pruefe "wirkung: die Route steht drin" "ja" \
       "$(enthaelt 'traefik.http.routers.fremd1.rule=Host(`fremd1.prolo.me`)' "$K")"
pruefe "wirkung: das Zertifikat steht drin" "ja" \
       "$(enthaelt "tls.certresolver=letsencrypt" "$K")"
pruefe "wirkung: das Abbild des Herstellers steht drin" "ja" \
       "$(enthaelt "vaultwarden/server:1.34.1" "$K")"
pruefe "wirkung: die Grenzen aus §19 stehen drin" "ja" \
       "$([ "$(enthaelt "mem_limit" "$K")" = ja ] && [ "$(enthaelt "no-new-privileges" "$K")" = ja ] \
          && echo ja || echo nein)"
pruefe "wirkung: eigene Anmeldung ist ERKLAERT, nicht nur weggelassen" "ja" \
       "$(enthaelt "prolo.anmeldung=eigene" "$K")"
pruefe "wirkung: und der Grund steht dabei" "ja" \
       "$(enthaelt "prolo.anmeldung.grund=API und Handy-App" "$K")"
pruefe "wirkung: kein authentik@file (so war es bestellt)" "nein" \
       "$(enthaelt "authentik@file" "$K")"
pruefe "wirkung: keine veroeffentlichten Ports" "nein" "$(enthaelt "published" "$K")"

# Das Netz muss in BEIDEN Bloecken der Traefik-Datei stehen. Eine Stelle
# allein reicht nicht: fehlt der Block unten, kennt Traefik das Netz nicht,
# fehlt der Eintrag beim Dienst, haengt Traefik nicht drin. Beides endet in
# einem toten Router ohne Fehlermeldung.
TY=$(cat "$S/traefik/docker-compose.yml")
pruefe "traefik: Netz beim Dienst eingetragen" "ja" "$(passt "^      - netz-fremd1$" "$TY")"
pruefe "traefik: Netz im Block unten eingetragen" "ja" "$(passt "^  netz-fremd1:$" "$TY")"
pruefe "traefik: der Block unten sagt external" "ja" \
       "$(printf '%s' "$TY" | grep -A1 '^  netz-fremd1:$' | grep -qx '    external: true' \
          && echo ja || echo nein)"
pruefe "docker: das Netz ist angelegt" "ja" \
       "$(grep -qx netz-fremd1 "$T/netze" && echo ja || echo nein)"
pruefe "traefik: die Datei bleibt lesbar" "0" \
       "$(cd "$S/traefik" && docker compose config -q --no-interpolate >/dev/null 2>&1; echo $?)"

echo
echo "== 2. Eigener Code ======================================================="
A=$("$NEU" eigen1 --art eigen --dienst eigen1 --port 8080 --netz-neu </dev/null 2>&1); R=$?
pruefe "eigen: Rueckgabe 0" "0" "$R"
K=$(cd "$S/eigen1" && docker compose config --no-interpolate 2>&1)
pruefe "eigen: Authentik ist davor - ohne Frage (§17)" "ja" "$(enthaelt "authentik@file" "$K")"
pruefe "eigen: keine eigene Anmeldung erklaerbar" "nein" "$(enthaelt "prolo.anmeldung=eigene" "$K")"
pruefe "eigen: PROLO_EINLASS wird verlangt (N-44)" "ja" "$(enthaelt "PROLO_EINLASS" "$K")"
pruefe "eigen: Dockerfile liegt da" "ja" "$([ -f "$S/eigen1/Dockerfile" ] && echo ja || echo nein)"
pruefe "eigen: geheimnisse.conf liegt da" "ja" \
       "$([ -f "$S/eigen1/geheimnisse.conf" ] && echo ja || echo nein)"
pruefe "eigen: geheimnisse.conf enthaelt KEINEN Wert (§23a)" "nein" \
       "$(passt "^PROLO_EINLASS\|.*\|.+=" "$(cat "$S/eigen1/geheimnisse.conf")")"
# N-53: die tool-eigene .gitignore gewinnt gegen die Wurzeldatei. Wer dort
# ".env.*" schreibt, ohne "!.env.beispiel" daneben, faengt die eigene
# Vorlage mit - und merkt es erst beim naechsten frischen Klon.
G=$(cat "$S/eigen1/.gitignore")
pruefe "eigen: .gitignore sperrt .env" "ja" "$(passt "^\.env$" "$G")"
pruefe "eigen: .gitignore traegt die Ausnahme mit (N-53)" "ja" "$(passt '^!\.env\.beispiel$' "$G")"
pruefe "eigen: die Vorlage .env.beispiel liegt da" "ja" \
       "$([ -f "$S/eigen1/.env.beispiel" ] && echo ja || echo nein)"

echo
echo "== 3. Was abgelehnt werden muss =========================================="
A=$("$NEU" GROSS --art fremd --abbild a:1 --netz-neu --anmeldung authentik </dev/null 2>&1); R=$?
pruefe "ablehnen: Grossbuchstaben im Namen" "1" "$R"
A=$("$NEU" latest1 --art fremd --abbild nginx:latest --netz-neu --anmeldung authentik </dev/null 2>&1); R=$?
pruefe "ablehnen: latest als Fassung (§19)" "1" "$R"
pruefe "ablehnen: und es bleibt kein halber Ordner stehen" "nein" \
       "$([ -d "$S/latest1" ] && echo ja || echo nein)"
A=$("$NEU" ohnefassung --art fremd --abbild nginx --netz-neu --anmeldung authentik </dev/null 2>&1); R=$?
pruefe "ablehnen: Abbild ohne Fassung" "1" "$R"
A=$("$NEU" fremd1 --art fremd --abbild a:1 --netz-neu --anmeldung authentik </dev/null 2>&1); R=$?
pruefe "ablehnen: Ordner gibt es schon" "1" "$R"
A=$("$NEU" ohnegrund --art fremd --abbild a:1 --netz-neu --anmeldung eigene </dev/null 2>&1); R=$?
pruefe "ablehnen: eigene Anmeldung ohne Grund (N-59)" "1" "$R"
pruefe "ablehnen: und kein halber Ordner" "nein" \
       "$([ -d "$S/ohnegrund" ] && echo ja || echo nein)"
# --grund MUSS hier mitgegeben werden. Ohne ihn scheitert der Aufruf
# schon an der fehlenden Begruendung - die Zeile waere dann gruen, ohne
# je die §17-Regel zu beruehren. Genau so ist sie beim ersten Lauf der
# Mutationsprobe durchgerutscht.
A=$("$NEU" eigenauth --art eigen --anmeldung eigene --grund "weil ich will" \
      --netz-neu </dev/null 2>&1); R=$?
pruefe "ablehnen: eigener Code mit eigener Anmeldung (§17)" "1" "$R"
pruefe "ablehnen: und §17 ist der genannte Grund" "ja" "$(enthaelt "§17" "$A")"
pruefe "ablehnen: und kein halber Ordner" "nein" \
       "$([ -d "$S/eigenauth" ] && echo ja || echo nein)"

# Der Fall, der die Transaktion beweist: das Netz geht nicht -> nichts wird
# angelegt. Vorher stand sonst ein Ordner da, den niemand von einem
# fertigen Werkzeug unterscheiden kann.
DOCKER_TOT=1 "$NEU" ohnenetz1 --art fremd --abbild a:1 --netz-neu \
  --anmeldung authentik </dev/null >/dev/null 2>&1; R=$?
pruefe "ablehnen: Netz geht nicht -> Rueckgabe 1" "1" "$R"
pruefe "ablehnen: Netz geht nicht -> KEIN Ordner (§12)" "nein" \
       "$([ -d "$S/ohnenetz1" ] && echo ja || echo nein)"

echo
echo "== 4. prolo start: die Sperren ==========================================="
# 4a. Platzhalter steht noch drin
A=$("$PROLO" start fremd1 2>&1); R=$?
pruefe "start: Platzhalter -> Rueckgabe 1" "1" "$R"
pruefe "start: und es wird gesagt, was fehlt" "ja" "$(enthaelt "PROLO-PLATZHALTER" "$A")"

# 4b. Hersteller-Datei eingesetzt, aber mit ports:
cat > "$S/fremd1/docker-compose.yml" <<'Y'
services:
  vaultwarden:
    image: vaultwarden/server:1.34.1
    ports:
      - "8081:80"
Y
A=$("$PROLO" start fremd1 2>&1); R=$?
pruefe "start: offener Port -> Rueckgabe 1" "1" "$R"
pruefe "start: der Port wird benannt" "ja" "$(enthaelt "8081" "$A")"
pruefe "start: und der Weg heraus steht dabei" "ja" "$(enthaelt "ports:-Zeile" "$A")"

# 4c. ohne ports: -> geht durch
cat > "$S/fremd1/docker-compose.yml" <<'Y'
services:
  vaultwarden:
    image: vaultwarden/server:1.34.1
Y
A=$("$PROLO" start fremd1 2>&1); R=$?
pruefe "start: ohne offenen Port laeuft es durch" "0" "$R"

# 4d. Router ganz ohne Anmeldung und ohne Erklaerung
mkdir -p "$S/offen1"
cat > "$S/offen1/docker-compose.yml" <<'Y'
services:
  offen1:
    image: nginx:1.27-alpine
    networks:
      - netz-alt
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=netz-alt"
      - "traefik.http.routers.offen1.rule=Host(`offen1.prolo.me`)"
networks:
  netz-alt:
    external: true
Y
A=$("$PROLO" start offen1 2>&1); R=$?
pruefe "start: Router ohne Anmeldung -> Rueckgabe 1" "1" "$R"
pruefe "start: beide Auswege werden genannt" "ja" \
       "$([ "$(enthaelt "authentik@file" "$A")" = ja ] \
          && [ "$(enthaelt "prolo.anmeldung=eigene" "$A")" = ja ] && echo ja || echo nein)"
pruefe "start: stop bleibt trotzdem moeglich" "0" "$("$PROLO" stop offen1 >/dev/null 2>&1; echo $?)"

# 4e. Zwei Router, einer mit Anmeldung, einer ohne (N-84). Genau das, wovor
# §17a warnt: ein zweiter Router fuer Webhooks, der aus Versehen offen ist.
# Vorher reichte EIN authentik@file irgendwo am Dienst, und der ganze
# Dienst galt als geschuetzt.
mkdir -p "$S/halb1"
cat > "$S/halb1/docker-compose.yml" <<'Y'
services:
  halb1:
    image: nginx:1.27-alpine
    networks:
      - netz-alt
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=netz-alt"
      - "traefik.http.routers.halb1.rule=Host(`halb1.prolo.me`)"
      - "traefik.http.routers.halb1.middlewares=authentik@file"
      - "traefik.http.routers.halb1-haken.rule=Host(`halb1.prolo.me`) && PathPrefix(`/haken`)"
      - "traefik.http.routers.halb1-haken.priority=100"
networks:
  netz-alt:
    external: true
Y
A=$("$PROLO" start halb1 2>&1); R=$?
pruefe "start: zweiter Router ohne Anmeldung -> Rueckgabe 1 (N-84)" "1" "$R"
pruefe "start: der offene Router wird beim Namen genannt" "ja" \
       "$(enthaelt "halb1-haken.middlewares=authentik@file" "$A")"
pruefe "start: und der Ausweg fuer einen gewollt oeffentlichen" "ja" \
       "$(enthaelt "prolo.oeffentlich=halb1-haken" "$A")"
A=$("$NETZE" 2>&1)
pruefe "netze: der halb offene Dienst gilt als OFFEN" "ja" \
       "$(passt "halb1 +halb1 +netz-alt +OFFEN" "$A")"
# Erklaert oeffentlich: dann ist es ein Entschluss und geht durch.
sed -i 's|      - "traefik.http.routers.halb1-haken.priority=100"|&\n      - "prolo.oeffentlich=halb1-haken"|' \
  "$S/halb1/docker-compose.yml"
A=$("$PROLO" start halb1 2>&1); R=$?
pruefe "start: als oeffentlich erklaert -> geht durch" "0" "$R"
rm -rf "$S/halb1"

echo
echo "== 5. prolo netze ========================================================"
A=$("$NETZE" 2>&1); R=$?
pruefe "netze: fremd1 steht in der Uebersicht" "ja" "$(enthaelt "netz-fremd1" "$A")"
pruefe "netze: der ungeschuetzte Router faellt auf" "ja" "$(enthaelt "OFFEN" "$A")"
pruefe "netze: und wird als Beanstandung gewertet" "2" "$R"
pruefe "netze: Traefiks Ports gelten als erklaert" "nein" \
       "$(enthaelt "veroeffentlicht Port(s) 80" "$A")"

pruefe "netze: anlegen ist beliebig oft moeglich" "0" \
       "$("$NETZE" anlegen netz-fremd1 >/dev/null 2>&1; echo $?)"
pruefe "netze: und traegt nichts doppelt ein" "1" \
       "$(grep -c '^      - netz-fremd1$' "$S/traefik/docker-compose.yml")"

A=$("$NETZE" schliessen netz-fremd1 2>&1); R=$?
pruefe "netze: schliessen wird verweigert, solange wer drin ist" "1" "$R"
pruefe "netze: und sagt, wer" "ja" "$(enthaelt "fremd1" "$A")"
pruefe "netze: das Netz steht danach noch in der Traefik-Datei" "ja" \
       "$(passt "^  netz-fremd1:$" "$(cat "$S/traefik/docker-compose.yml")")"


# N-68: zwei Werkzeuge in einem Netz und zwei Router auf demselben Namen.
# Beides ZEIGTE die Uebersicht schon ("netz-n8n  n8n,n8n_alt"), nannte es
# aber nicht als Problem. Eine Zeile, die man selbst deuten muss, ist keine
# Meldung.
zwilling() {   # $1 = Ordner, $2 = geteilt-Grund (leer = keiner)
  mkdir -p "$S/$1"
  { printf 'services:\n  %s:\n    image: x:1\n    networks:\n      - netz-alt\n' "$1"
    printf '    labels:\n      - "traefik.enable=true"\n'
    printf '      - "traefik.docker.network=netz-alt"\n'
    printf '      - "traefik.http.routers.%s.rule=Host(`zwilling.prolo.me`)"\n' "$1"
    printf '      - "traefik.http.routers.%s.middlewares=authentik@file"\n' "$1"
    [ -z "${2:-}" ] || printf '      - "prolo.netz.geteilt=%s"\n' "$2"
    printf 'networks:\n  netz-alt:\n    external: true\n'
  } > "$S/$1/docker-compose.yml"
}
# offen1 haengt seit Abschnitt 4 ebenfalls in netz-alt und hat seine
# Schuldigkeit getan. Bleibt es liegen, sind es DREI Werkzeuge in einem
# Netz, und die Pruefzeile unten misst etwas anderes, als sie glaubt.
rm -rf "$S/offen1"
zwilling zwilling-a; zwilling zwilling-b
A=$("$NETZE" 2>&1); R=$?
pruefe "geteiltes Netz: faellt als Beanstandung auf" "2" "$R"
pruefe "geteiltes Netz: wird benannt" "ja" "$(enthaelt "teilen sich mehrere Werkzeuge" "$A")"
pruefe "geteiltes Netz: beide Werkzeuge stehen dabei" "ja" \
       "$([ "$(enthaelt "zwilling-a" "$A")" = ja ] && [ "$(enthaelt "zwilling-b" "$A")" = ja ] \
          && echo ja || echo nein)"
pruefe "geteiltes Netz: das Label wird genannt" "ja" \
       "$(enthaelt "prolo.netz.geteilt" "$A")"
pruefe "doppelter Hostname: faellt auf" "ja" \
       "$(enthaelt "zwilling.prolo.me wird von mehreren Diensten" "$A")"

# Erklaert: das geteilte Netz ist in Ordnung, der doppelte Name bleibt es
# nicht. Zwei Beanstandungen, die sich nicht gegenseitig stumm schalten.
zwilling zwilling-a "Testbereich"; zwilling zwilling-b "Testbereich"
A=$("$NETZE" 2>&1)
pruefe "erklaert: das geteilte Netz wird nicht mehr beanstandet" "nein" \
       "$(enthaelt "teilen sich mehrere Werkzeuge" "$A")"
pruefe "erklaert: der doppelte Hostname sehr wohl" "ja" \
       "$(enthaelt "zwilling.prolo.me wird von mehreren Diensten" "$A")"
rm -rf "$S/zwilling-a" "$S/zwilling-b"

# Gegenrichtung: ein Netz mit genau einem Gast ist keine gemeinsame
# Flaeche - sonst wuerde socket (socket-proxy legt es an, admin haengt
# sich hinein) jeden Tag denselben Fehlalarm geben. Dieser Fall muss im
# Wegwerfstack WIRKLICH vorkommen, sonst prueft die Zeile nichts: eine
# Mutationsprobe hat genau das gezeigt.
mkdir -p "$S/vermittler" "$S/gast"
printf 'services:\n  vermittler:\n    image: x:1\n    networks:\n      - draht\nnetworks:\n  draht:\n    name: draht\n    internal: true\n' \
  > "$S/vermittler/docker-compose.yml"
printf 'services:\n  gast:\n    image: x:1\n    networks:\n      - draht\nnetworks:\n  draht:\n    external: true\n' \
  > "$S/gast/docker-compose.yml"
A=$("$NETZE" 2>&1)
pruefe "der Fall kommt im Wegwerfstack vor (Eigentuemer + ein Gast)" "ja" \
       "$(enthaelt "draht" "$A")"
pruefe "ein Gast allein: keine Beanstandung" "nein" \
       "$(enthaelt "teilen sich mehrere Werkzeuge" "$A")"
# Und mit einem ZWEITEN Gast wird es einer - sonst waere die Zeile darueber
# auch dann gruen, wenn gar nichts mehr geprueft wird.
mkdir -p "$S/gast2"
sed 's/gast/gast2/' "$S/gast/docker-compose.yml" > "$S/gast2/docker-compose.yml"
A=$("$NETZE" 2>&1)
pruefe "zwei Gaeste: jetzt ist es eine Beanstandung" "ja" \
       "$(enthaelt "draht teilen sich mehrere Werkzeuge" "$A")"
rm -rf "$S/vermittler" "$S/gast" "$S/gast2"

echo
echo "== 6. umziehen ==========================================================="
A=$("$NETZE" umziehen fremd1 netz-gibtsnicht 2>&1); R=$?
pruefe "umziehen: unbekanntes Zielnetz -> Rueckgabe 1" "1" "$R"
pruefe "umziehen: und nichts wurde geaendert" "ja" \
       "$(enthaelt "netz-fremd1" "$(cat "$S/fremd1/docker-compose.override.yml")")"
pruefe "umziehen: keine Kopie bleibt liegen" "nein" \
       "$([ -f "$S/fremd1/docker-compose.override.yml.vor-umzug" ] && echo ja || echo nein)"

A=$("$NETZE" umziehen fremd1 netz-alt 2>&1); R=$?
pruefe "umziehen: nach netz-alt -> Rueckgabe 0" "0" "$R"
K=$(cd "$S/fremd1" && docker compose config --no-interpolate 2>&1)
pruefe "umziehen: die Wirkung - das Netz ist netz-alt" "ja" "$(enthaelt "netz-alt" "$K")"
pruefe "umziehen: netz-fremd1 kommt nicht mehr vor" "nein" "$(enthaelt "netz-fremd1" "$K")"
pruefe "umziehen: das Label ist mitgezogen" "ja" \
       "$(enthaelt "traefik.docker.network=netz-alt" "$K")"
pruefe "umziehen: keine Kopie bleibt liegen" "nein" \
       "$([ -f "$S/fremd1/docker-compose.override.yml.vor-umzug" ] && echo ja || echo nein)"

A=$("$NETZE" schliessen netz-fremd1 2>&1); R=$?
pruefe "schliessen: jetzt geht es" "0" "$R"
pruefe "schliessen: aus der Traefik-Datei raus (Dienst)" "nein" \
       "$(passt "^      - netz-fremd1$" "$(cat "$S/traefik/docker-compose.yml")")"
pruefe "schliessen: aus der Traefik-Datei raus (Block unten)" "nein" \
       "$(passt "^  netz-fremd1:$" "$(cat "$S/traefik/docker-compose.yml")")"
pruefe "schliessen: im Docker weg" "nein" \
       "$(grep -qx netz-fremd1 "$T/netze" && echo ja || echo nein)"
pruefe "schliessen: die Traefik-Datei bleibt lesbar" "0" \
       "$(cd "$S/traefik" && docker compose config -q --no-interpolate >/dev/null 2>&1; echo $?)"
pruefe "schliessen: socket wird nie geschlossen" "1" \
       "$("$NETZE" schliessen socket >/dev/null 2>&1; echo $?)"

echo
echo "== 6b. Ein Werkzeug, das im Git steht, aber nicht auf der Platte ========"
# N-66: n8n wurde auf dem Server entfernt, lag aber weiter im Repository -
# und der naechste Griff war "prolo neu n8n". Ein Geruest darueber haette
# die Datei verdraengt, die laengst richtig war.
if command -v git >/dev/null 2>&1; then
  (cd "$S" && git init -q -b haupt && git config user.email t@t \
   && git config user.name t && git add -A && git commit -q -m stand) || true
  rm -rf "$S/fremd1"
  A=$("$NEU" fremd1 --art fremd --abbild a:1 --netz netz-alt \
        --anmeldung authentik </dev/null 2>&1); R=$?
  pruefe "im Git, nicht ausgecheckt: Rueckgabe 1" "1" "$R"
  pruefe "im Git: kein Geruest darueber" "nein" \
         "$([ -f "$S/fremd1/docker-compose.override.yml" ] && echo ja || echo nein)"
  pruefe "im Git: der Weg zurueck wird genannt" "ja" \
         "$(enthaelt "git checkout -- fremd1/" "$A")"
  pruefe "im Git: und der Weg, es wirklich loszuwerden" "ja" \
         "$(enthaelt "git rm -r fremd1" "$A")"
  # Und die Gegenrichtung: ein Name, den das Git nicht kennt, wird normal
  # angelegt. Sonst waere aus der Bremse eine Sperre fuer alles geworden.
  A=$("$NEU" ganzneu --art fremd --abbild a:1 --netz netz-alt \
        --anmeldung authentik </dev/null 2>&1); R=$?
  pruefe "nicht im Git: wird normal angelegt" "0" "$R"
  rm -rf "$S/.git" "$S/ganzneu"
  (cd "$S" && git checkout -- . 2>/dev/null) || true
else
  echo "uebersprungen  git fehlt"
fi

# Ein Abbild ohne Fassung: die Meldung muss sagen, WO der volle Name steht -
# "n8n" ist nicht der Name des Abbilds, und das weiss man nicht von selbst.
A=$("$NEU" ohnefassung2 --art fremd --abbild n8n --netz netz-alt \
      --anmeldung authentik </dev/null 2>&1); R=$?
pruefe "ohne Fassung: Rueckgabe 1" "1" "$R"
pruefe "ohne Fassung: der volle Name wird erklaert" "ja" \
       "$(enthaelt "docker.n8n.io/n8nio/n8n" "$A")"
pruefe "ohne Fassung: und wie man ihn findet" "ja" "$(enthaelt "prolo suchen" "$A")"

echo
echo "== 7. Wenn eine Konfiguration nicht lesbar ist ==========================="
# N-64: vorher stand nur "liefert keine lesbare Konfiguration" - und der
# Betreiber sah ein Werkzeug fehlen, ohne zu erfahren, WARUM. Die Meldung
# von docker war da, sie wurde nur weggeworfen.
mkdir -p "$S/verbogen"
printf 'services:\n  verbogen:\n    image: x:1\n   schief: ja\n' \
  > "$S/verbogen/docker-compose.yml"
A=$("$NETZE" 2>&1); R=$?
pruefe "kaputt: das Werkzeug wird beim Namen genannt" "ja" "$(enthaelt "verbogen:" "$A")"
pruefe "kaputt: die Meldung von docker steht dabei" "ja" "$(enthaelt "yaml:" "$A")"
pruefe "kaputt: und es gilt als Beanstandung" "2" "$R"
# Der genannte Aufruf muss DERSELBE sein, den prolo gemacht hat. Ein
# Hinweis auf einen anderen Befehl fuehrt an eine andere Stelle als die,
# an der es geklemmt hat - und ohne --no-interpolate scheitert er auf
# einem frischen Klon an etwas voellig anderem.
pruefe "kaputt: der genannte Aufruf ist der, den prolo gemacht hat" "ja" \
       "$(enthaelt "docker compose config --no-interpolate" "$A")"
# Rechte sind etwas anderes als eine kaputte Datei - der sudo-Rat gehoert
# nur dorthin, wo die Meldung ihn hergibt.
pruefe "kaputt: kein sudo-Rat bei einem YAML-Fehler" "nein" "$(enthaelt "mit sudo prolo netze" "$A")"

printf 'services:\n  verbogen:\n    image: x:1\n' > "$S/verbogen/docker-compose.yml"
printf 'KAPUTTE ZEILE OHNE GLEICH\n' > "$S/verbogen/.env"
A=$("$NETZE" 2>&1)
pruefe "kaputt: auch eine unlesbare .env wird benannt" "ja" "$(enthaelt ".env" "$A")"
rm -rf "$S/verbogen"

A=$("$NETZE" 2>&1)
pruefe "heil: ohne kaputte Datei kommt der Hinweis nicht" "nein" \
       "$(enthaelt "laesst sich nicht lesen" "$A")"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "GEGENPROBE FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
