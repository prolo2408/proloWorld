#!/usr/bin/env bash
# werkzeuge/neu.sh
#
# Ein neues Werkzeug anlegen - und zwar fertig, nicht als Hausaufgabenliste.
#
# Vorher legte "prolo neu" ein Geruest an und sagte dann vier Dinge, die
# noch "von Hand" zu tun seien: Netz anlegen, Netz bei Traefik eintragen
# (an zwei Stellen), Authentik einrichten, Compose ausfuellen. Genau solche
# Listen fallen beim Abtippen aus (N-54), und beim Netz faellt es erst auf,
# wenn der Router tot bleibt.
#
# Zwei Arten von Werkzeug, und der Unterschied ist grundsaetzlich (N-61):
#
#   fremd   n8n, Vaultwarden, Seafile ... Die laufen so, wie der Hersteller
#           es vorschlaegt. Seine docker-compose.yml wird UNVERAENDERT
#           uebernommen; alles, was von uns kommt, steht daneben in einer
#           docker-compose.override.yml. "docker compose" liest beide von
#           selbst. Bei einer neuen Fassung ersetzt man die Hersteller-Datei
#           und fertig - unsere Zutat bleibt liegen.
#
#   eigen   wiki, bordbuch, www. Eigener Code, eigenes Dockerfile, und die
#           Anmeldung macht IMMER Authentik (§17). Da gibt es nichts zu
#           fragen.
#
# Aufruf, alles fragbar und alles vorgebbar:
#   neu.sh <name> [--art fremd|eigen] [--abbild ABBILD] [--dienst NAME]
#                 [--port N] [--host NAME] [--netz NETZ|--netz-neu]
#                 [--anmeldung authentik|eigene] [--grund TEXT]
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
DOMAENE="${PROLO_DOMAENE:-prolo.me}"

melde()  { printf '%s\n' "$*"; }
fehler() { printf '%s\n' "$*" >&2; }
titel()  { printf '\n\033[1m%s\033[0m\n' "$*"; }

NAME=""; ART=""; ABBILD=""; DIENST=""; PORT=""; HOST=""; NETZ=""
ANMELDUNG=""; GRUND=""; OHNE_NETZ=0

while [ $# -gt 0 ]; do
  case "$1" in
    --art)       ART="${2:-}"; shift 2 ;;
    --abbild)    ABBILD="${2:-}"; shift 2 ;;
    --dienst)    DIENST="${2:-}"; shift 2 ;;
    --port)      PORT="${2:-}"; shift 2 ;;
    --host)      HOST="${2:-}"; shift 2 ;;
    --netz)      NETZ="${2:-}"; shift 2 ;;
    --netz-neu)  NETZ="neu"; shift ;;
    --ohne-netz) OHNE_NETZ=1; shift ;;
    --anmeldung) ANMELDUNG="${2:-}"; shift 2 ;;
    --grund)     GRUND="${2:-}"; shift 2 ;;
    -*)          fehler "Unbekannt: $1"; exit 1 ;;
    *)           [ -z "$NAME" ] && NAME="$1" || { fehler "Zu viele Namen."; exit 1; }
                 shift ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { fehler "Dieser Befehl braucht root: sudo prolo neu <name>"; exit 1; }
[ -n "$NAME" ] || { fehler "Aufruf: prolo neu <name>"; exit 1; }
case "$NAME" in
  *[!a-z0-9-]*) fehler "Nur Kleinbuchstaben, Ziffern und Bindestrich (CLAUDE.md §16)."
                fehler "Der Ordnername ist gleichzeitig die Subdomain."; exit 1 ;;
esac
[ -e "$STACK/$NAME" ] && { fehler "$STACK/$NAME gibt es schon."; exit 1; }

# Der Ordner ist nicht da - aber steht er im Git? Dann ist er nicht neu
# anzulegen, sondern zurueckzuholen (N-66). Genau das ist passiert: n8n
# wurde auf dem Server entfernt, lag aber weiter im Repository, und der
# naechste Griff war "prolo neu n8n". Ein Geruest darueberzuschreiben
# haette die Datei verdraengt, die laengst richtig war - und beim naechsten
# Holen einen Konflikt gegeben.
if command -v git >/dev/null 2>&1 \
   && git -C "$STACK" ls-files --error-unmatch "$NAME" >/dev/null 2>&1; then
  fehler "Es gibt $NAME schon - im Git, nur hier nicht ausgecheckt:"
  git -C "$STACK" ls-files "$NAME" | sed 's/^/  /' >&2
  fehler ""
  fehler "  Das will ZURUECKGEHOLT werden, nicht neu angelegt:"
  fehler "    cd $STACK && git checkout -- $NAME/"
  fehler ""
  fehler "  Soll es wirklich weg, gehoert es auch im Git weg - sonst holt"
  fehler "  der naechste Pull es zurueck oder bricht daran ab:"
  fehler "    cd $STACK && git rm -r $NAME && git commit -m \"$NAME entfernt\""
  exit 1
fi

# Fragen nur, wenn jemand da ist, der antworten kann. Sonst ist ein
# fehlender Wert ein Fehler und keine stille Vorgabe (CLAUDE.md §11).
fragbar() { [ -t 0 ]; }
frage() {   # $1 Text  $2 Vorgabe (leer = Pflicht)  -> Antwort auf stdout
  local text="$1" vorgabe="${2:-}" a
  if ! fragbar; then
    [ -n "$vorgabe" ] && { printf '%s' "$vorgabe"; return 0; }
    fehler "Ohne Terminal muss '$text' als Schalter mitgegeben werden."
    exit 1
  fi
  read -rp "  $text${vorgabe:+ [$vorgabe]}: " a </dev/tty
  printf '%s' "${a:-$vorgabe}"
}

# ----------------------------------------------------------------------
titel "Neues Werkzeug: $NAME"

# --- 1. Art -----------------------------------------------------------
if [ -z "$ART" ]; then
  melde ""
  melde "  Was fuer ein Werkzeug?"
  melde "    1) fremd  - laeuft wie vom Hersteller vorgeschlagen. Seine"
  melde "                docker-compose.yml bleibt unveraendert; wir legen"
  melde "                nur Netz, Route und Zertifikat daneben."
  melde "    2) eigen  - eigener Code mit Dockerfile (wie wiki, bordbuch)."
  melde "                Die Anmeldung macht immer Authentik."
  case "$(frage "Wahl" "1")" in
    1|fremd) ART=fremd ;;
    2|eigen) ART=eigen ;;
    *) fehler "1 oder 2."; exit 1 ;;
  esac
fi
case "$ART" in fremd|eigen) : ;; *) fehler "--art ist fremd oder eigen."; exit 1 ;; esac

# --- 2. Abbild --------------------------------------------------------
if [ "$ART" = fremd ]; then
  if [ -z "$ABBILD" ]; then
    melde ""
    melde "  Der volle Name des Abbilds steht in der Doku des Herstellers -"
    melde "  er ist selten nur der Werkzeugname. Beispiele:"
    melde "    docker.n8n.io/n8nio/n8n:1.121.0"
    melde "    vaultwarden/server:1.34.1"
    melde "    seafileltd/seafile-mc:11.0.13"
    melde "  Suchen geht auch:  prolo suchen $NAME"
    ABBILD=$(frage "Abbild des Herstellers, mit Fassung")
  fi
else
  [ -n "$ABBILD" ] || ABBILD="$NAME:0.1.0"
fi
[ -n "$ABBILD" ] || { fehler "Ohne Abbild geht es nicht."; exit 1; }
printf '%s' "$ABBILD" | grep -q ':' \
  || { fehler "'$ABBILD' hat keine Fassung, und ohne die geht es nicht"
       fehler "(§19: nie latest, immer fest - Datenbankmigrationen bei"
       fehler "Hauptversionen sind nicht umkehrbar)."
       fehler ""
       fehler "  Der volle Name steht in der Doku des Herstellers und ist"
       fehler "  selten nur der Werkzeugname. n8n heisst zum Beispiel"
       fehler "  docker.n8n.io/n8nio/n8n:1.121.0, nicht n8n."
       fehler "  Suchen:  prolo suchen $ABBILD"; exit 1; }
printf '%s' "$ABBILD" | grep -q ':latest$' \
  && { fehler "'latest' ist verboten (§19). Datenbankmigrationen bei"
       fehler "Hauptversionen sind nicht umkehrbar - die Fassung gehoert fest."; exit 1; }

# --- 3. Dienstname, Port, Hostname ------------------------------------
[ -n "$DIENST" ] || DIENST=$(frage "Dienstname in der Compose-Datei" "$NAME")
[ -n "$PORT" ]   || PORT=$(frage "Interner Port des Dienstes" "8080")
case "$PORT" in *[!0-9]*|"") fehler "Der Port ist eine Zahl."; exit 1 ;; esac
[ -n "$HOST" ]   || HOST=$(frage "Hostname" "$NAME.$DOMAENE")

# --- 4. Netz ----------------------------------------------------------
# Jedes Werkzeug in seinem eigenen Netz ist der Normalfall (N-45). Ein
# gemeinsames Netz ist erlaubt - aber es ist eine Entscheidung, keine
# Bequemlichkeit, und sie wird im Label festgehalten.
VORHANDEN=$("$HIER/netze.sh" --namen 2>/dev/null | grep -vx socket || true)
if [ -z "$NETZ" ]; then
  melde ""
  melde "  Netz"
  melde "    1) neues Netz netz-$NAME   (empfohlen: was hier kompromittiert"
  melde "                               wird, erreicht nichts anderes)"
  melde "    2) ein vorhandenes benutzen"
  if [ "$(frage "Wahl" "1")" = 2 ]; then
    melde ""
    printf '%s\n' "$VORHANDEN" | sed 's/^/    /'
    NETZ=$(frage "Welches")
    printf '%s\n' "$VORHANDEN" | grep -qx "$NETZ" \
      || { fehler "Das Netz $NETZ gibt es nicht. Erst anlegen:"
           fehler "  sudo prolo netze anlegen $NETZ"; exit 1; }
    GETEILT=$(frage "Warum teilen sich zwei Werkzeuge dieses Netz")
    [ -n "$GETEILT" ] || { fehler "Ohne Grund nicht - ein geteiltes Netz hebt"
                           fehler "die Abschottung zwischen zwei Werkzeugen auf."; exit 1; }
  else
    NETZ="netz-$NAME"
  fi
elif [ "$NETZ" = neu ]; then
  NETZ="netz-$NAME"
fi
GETEILT="${GETEILT:-}"
case "$NETZ" in *[!a-z0-9-]*) fehler "Netzname: nur Kleinbuchstaben, Ziffern, Bindestrich."; exit 1 ;; esac

# --- 5. Anmeldung -----------------------------------------------------
if [ "$ART" = eigen ]; then
  # §17 laesst hier keine Wahl: eigener Code baut NIE eine eigene Anmeldung.
  [ -z "$ANMELDUNG" ] || [ "$ANMELDUNG" = authentik ] \
    || { fehler "Eigener Code laeuft immer hinter Authentik (§17)."; exit 1; }
  ANMELDUNG=authentik
elif [ -z "$ANMELDUNG" ]; then
  melde ""
  melde "  Anmeldung - das ist eine Sicherheitsentscheidung, darum ohne Vorgabe."
  melde "    1) Authentik davorschalten"
  melde "       Niemand kommt an das Werkzeug, ohne sich zentral anzumelden."
  melde "       Richtig fuer alles, was keine brauchbare eigene Anmeldung hat."
  melde "    2) eigene Anmeldung des Werkzeugs"
  melde "       Richtig fuer n8n, Vaultwarden, Seafile: die bringen eine mit,"
  melde "       und ein Teil ihrer Oberflaeche (Webhooks, API, Handy-App)"
  melde "       kann eine ForwardAuth-Anmeldung gar nicht durchlaufen."
  melde "       Bedingungen dafuer stehen in CLAUDE.md §17a - vor allem:"
  melde "       2FA in dieser eigenen Anmeldung EINSCHALTEN."
  case "$(frage "Wahl (1 oder 2)")" in
    1|authentik) ANMELDUNG=authentik ;;
    2|eigene)    ANMELDUNG=eigene ;;
    *) fehler "1 oder 2 - hier gibt es keine Vorgabe."; exit 1 ;;
  esac
fi
case "$ANMELDUNG" in authentik|eigene) : ;; *) fehler "--anmeldung ist authentik oder eigene."; exit 1 ;; esac
if [ "$ANMELDUNG" = eigene ] && [ -z "$GRUND" ]; then
  GRUND=$(frage "Warum keine Authentik davor (kommt ins Label und in die sicherung.conf)")
  [ -n "$GRUND" ] || { fehler "Ohne Grund nicht. Ein fehlendes middlewares= sieht"
                       fehler "sonst genauso aus wie ein vergessenes (N-59)."; exit 1; }
fi

# ----------------------------------------------------------------------
titel "Das wird angelegt"
melde "  Ordner      $STACK/$NAME"
melde "  Art         $ART"
melde "  Abbild      $ABBILD"
melde "  Dienst      $DIENST  (Port $PORT)"
melde "  Hostname    $HOST"
melde "  Netz        $NETZ${GETEILT:+  (geteilt: $GETEILT)}"
melde "  Anmeldung   $ANMELDUNG${GRUND:+  ($GRUND)}"
if fragbar; then
  [ "$(frage "Anlegen? (j/n)" "j")" = j ] || { melde "  Abgebrochen, nichts angelegt."; exit 0; }
fi

# Das Netz ZUERST. Es ist der Schritt, der scheitern kann - Docker kann
# aus sein, Traefiks Datei kann anders aussehen. Scheitert er, steht sonst
# ein Ordner da, der nie erreichbar wird, und niemand sieht den Unterschied
# zu einem fertigen Werkzeug (CLAUDE.md §12: erst pruefen, ob alles geht,
# dann schreiben).
if [ "$OHNE_NETZ" -eq 0 ]; then
  titel "Netz"
  "$HIER/netze.sh" anlegen "$NETZ" || {
    fehler ""
    fehler "  ABBRUCH: das Netz liess sich nicht einrichten. Es wurde KEIN"
    fehler "  Ordner angelegt - ein Werkzeug ohne Netz ist von aussen nicht"
    fehler "  erreichbar, und das sieht man ihm nicht an."
    fehler ""
    fehler "  Wer den Ordner trotzdem will und das Netz spaeter nachholt:"
    fehler "    sudo prolo neu $NAME --ohne-netz ..."
    exit 1
  }
fi

mkdir -p "$STACK/$NAME" || { fehler "Ordner liess sich nicht anlegen."; exit 1; }

# ----------------------------------------------------------------------
# Die Labels. Sie stehen an genau einer Stelle, damit die beiden Arten
# nicht auseinanderlaufen.
# ----------------------------------------------------------------------
labels() {   # $1 = Einrueckung
  local E="$1"
  printf '%s- "traefik.enable=true"\n' "$E"
  printf '%s- "traefik.docker.network=%s"\n' "$E" "$NETZ"
  printf '%s- "traefik.http.services.%s.loadbalancer.server.port=%s"\n' "$E" "$NAME" "$PORT"
  printf '%s- "traefik.http.routers.%s.rule=Host(`%s`)"\n' "$E" "$NAME" "$HOST"
  printf '%s- "traefik.http.routers.%s.entrypoints=websecure"\n' "$E" "$NAME"
  printf '%s- "traefik.http.routers.%s.tls.certresolver=letsencrypt"\n' "$E" "$NAME"
  printf '%s- "traefik.http.routers.%s.service=%s"\n' "$E" "$NAME" "$NAME"
  if [ "$ANMELDUNG" = authentik ]; then
    printf '%s# Ohne diese Zeile steht der Dienst offen im Netz.\n' "$E"
    printf '%s- "traefik.http.routers.%s.middlewares=authentik@file"\n' "$E" "$NAME"
  else
    printf '%s# Kein authentik@file - und das ist ein Entschluss, kein\n' "$E"
    printf '%s# Versehen. Genau dafuer steht das Label darunter (N-59).\n' "$E"
    printf '%s# Bedingungen: CLAUDE.md §17a. Vor allem 2FA einschalten.\n' "$E"
    printf '%s- "prolo.anmeldung=eigene"\n' "$E"
    printf '%s- "prolo.anmeldung.grund=%s"\n' "$E" "$GRUND"
  fi
  [ -n "$GETEILT" ] && printf '%s- "prolo.netz.geteilt=%s"\n' "$E" "$GETEILT"
  return 0
}

grenzen() {  # $1 = Einrueckung
  local E="$1"
  printf '%s# Grenzen nach CLAUDE.md §19. Ohne sie bringt ein Speicherleck in\n' "$E"
  printf '%s# EINEM Werkzeug den ganzen Server in den OOM-Killer.\n' "$E"
  printf '%s#\n' "$E"
  printf '%s# Braucht der Dienst eine Linux-Faehigkeit zurueck, wird sie\n' "$E"
  printf '%s# EINZELN ergaenzt - cap_drop bleibt stehen:\n' "$E"
  printf '%s#   cap_add: [ CHOWN, SETUID, SETGID ]\n' "$E"
  printf '%smem_limit: 512m\n' "$E"
  printf '%spids_limit: 256\n' "$E"
  printf '%ssecurity_opt:\n%s  - no-new-privileges:true\n' "$E" "$E"
  printf '%scap_drop:\n%s  - ALL\n' "$E" "$E"
  printf '%srestart: unless-stopped\n' "$E"
}

# ----------------------------------------------------------------------
if [ "$ART" = fremd ]; then
  cat > "$STACK/$NAME/docker-compose.yml" <<YML
# /opt/stack/$NAME/docker-compose.yml
#
# HIER KOMMT DIE DATEI DES HERSTELLERS HIN - unveraendert.
#
# Alles, was von uns kommt (Netz, Route, Zertifikat, Anmeldung, Grenzen),
# steht daneben in docker-compose.override.yml. "docker compose" liest
# beide von selbst. Bei einer neuen Fassung ersetzt man NUR diese Datei -
# die Zutat bleibt liegen.
#
# Eine ports:-Zeile des Herstellers darf stehen bleiben: die override-Datei
# nimmt sie beim Dienst "$DIENST" mit "ports: !reset []" wieder weg (N-103).
# Erreichbar ist der Dienst ueber https://$HOST - das macht Traefik.
#
# Heisst der Dienst beim Hersteller ANDERS als "$DIENST", den Namen in der
# override-Datei anpassen - sonst greift unsere Zutat ins Leere, und
# "prolo start $NAME" haelt an, weil der Port offen bliebe.
#
# Dann diese Kommentarzeile loeschen (sie ist die Sperre):
# PROLO-PLATZHALTER

services:
  $DIENST:
    image: $ABBILD
YML

  {
    cat <<YML
# /opt/stack/$NAME/docker-compose.override.yml
#
# UNSERE ZUTAT. Die Hersteller-Datei daneben bleibt unveraendert.
#
# Angelegt mit "prolo neu $NAME" am $(date +%Y-%m-%d).
#
# Was hier drinsteht und sonst nichts:
#   - das Netz $NETZ (Abschottung, N-45)
#   - die Route auf $HOST und das Zertifikat
#   - die Anmeldung: $ANMELDUNG
#   - die Grenzen nach §19
#
# Was hier NICHT hineingehoert: environment, volumes, command - das ist
# Sache des Herstellers und steht in seiner Datei.

services:
  $DIENST:
    # Die ports:-Zeile des Herstellers faellt hier weg - seine Datei
    # bleibt, wie sie ist (N-103, Compose ab 2.24.4). Ohne das waere der
    # Dienst an Traefik, an der Anmeldung und an der Firewall vorbei
    # erreichbar (§19).
    ports: !reset []
    networks:
      - $NETZ
YML
    grenzen "    "
    printf '    labels:\n'
    labels "      "
    cat <<YML

networks:
  # Angelegt und bei Traefik eingetragen von "prolo netze anlegen $NETZ".
  # Nur Traefik haengt in allen Werkzeugnetzen (N-45) - die Werkzeuge
  # erreichen einander dadurch nicht.
  $NETZ:
    external: true
YML
  } > "$STACK/$NAME/docker-compose.override.yml"

  cat > "$STACK/$NAME/LIESMICH.md" <<MD
# $NAME

Fremdwerkzeug. Laeuft so, wie der Hersteller es vorschlaegt.

| Datei | wem sie gehoert |
|---|---|
| \`docker-compose.yml\` | **dem Hersteller** - unveraendert uebernehmen, bei einer neuen Fassung ersetzen |
| \`docker-compose.override.yml\` | **uns** - Netz, Route, Zertifikat, Anmeldung, Grenzen |

\`docker compose\` liest beide von selbst. Was tatsaechlich dabei
herauskommt, zeigt:

\`\`\`bash
cd /opt/stack/$NAME && docker compose config
\`\`\`

## Aufsetzen

1. Die \`docker-compose.yml\` des Herstellers hier hineinkopieren -
   **unveraendert**, auch mit ihrer \`ports:\`-Zeile: die override-Datei
   nimmt sie mit \`ports: !reset []\` wieder weg (N-103). Erreichbar ist
   der Dienst ueber \`https://$HOST\`.
2. Heisst der Dienst dort anders als \`$DIENST\`, den Namen in
   \`docker-compose.override.yml\` angleichen.
3. Die Zeile \`PROLO-PLATZHALTER\` loeschen.
4. \`sudo prolo start $NAME\`

## Anmeldung

$([ "$ANMELDUNG" = authentik ] \
  && printf '%s' "Authentik ist davorgeschaltet. In Authentik noch eine Anwendung
fuer \`$HOST\` anlegen **und dem Outpost zuweisen** - ohne die Zuweisung
antwortet die Anmeldung mit 403." \
  || printf '%s' "**Eigene Anmeldung des Werkzeugs**, kein Authentik davor.

Grund: $GRUND

Bedingungen aus CLAUDE.md §17a, alle Pflicht:
eigenes Netz (\`$NETZ\`), Ratenbremse am Eingang (kommt von Traefik),
**2FA in der eigenen Anmeldung eingeschaltet**, und dieser Vermerk hier.")
MD
else
  # --- eigener Code: eine Datei, Dockerfile daneben ---------------------
  {
    cat <<YML
# /opt/stack/$NAME/docker-compose.yml
#
# Angelegt mit "prolo neu $NAME" am $(date +%Y-%m-%d).
#
# Eigener Code: die Anmeldung macht Authentik (§17). Kein Login-Formular,
# keine Registrierung, keine Passwortspeicherung - die Identitaet kommt als
# X-Authentik-* von Traefik, und das Werkzeug prueft vorher X-Prolo-Einlass
# (N-44). Ohne PROLO_EINLASS in der .env startet es nicht.
#
# Bewusst KEINE ports-Zeile: der Dienst ist ausschliesslich ueber Traefik
# erreichbar. Das ist nicht Gewohnheit, sondern der eigentliche Schutz.

services:
  $DIENST:
    build: .
    image: $ABBILD
    container_name: $NAME
YML
    grenzen "    "
    cat <<YML
    environment:
      PROLO_EINLASS: \${PROLO_EINLASS:?PROLO_EINLASS fehlt in $NAME/.env - siehe traefik/dynamic/einlass.yml.beispiel}
    volumes:
      - ${NAME}_daten:/daten
    networks:
      - $NETZ
YML
    printf '    labels:\n'
    labels "      "
    cat <<YML

volumes:
  ${NAME}_daten:                    # von aussen: ${NAME}_${NAME}_daten

networks:
  $NETZ:
    external: true
YML
  } > "$STACK/$NAME/docker-compose.yml"

  cat > "$STACK/$NAME/Dockerfile" <<'DOCKER'
FROM python:3.13-alpine
# Kein Fremdpaket (CLAUDE.md): Standardbibliothek und SQLite reichen.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py /app/
EXPOSE 8080
CMD ["python3", "/app/server.py"]
DOCKER
  printf '%s\n' "__pycache__/" "tests/" ".env*" "*.md" > "$STACK/$NAME/.dockerignore"

  cat > "$STACK/$NAME/geheimnisse.conf" <<CONF
# /opt/stack/$NAME/geheimnisse.conf
# Eine Zeile je Wert: NAME|DATEI|FORM|WECHSEL|Erklaerung - und NIE ein Wert.
# WECHSEL: harmlos | sitzungen | haende  (CLAUDE.md §23a)
PROLO_EINLASS|.env|env|harmlos|Die Marke von Traefik. Steht an mehreren Stellen - prolo geheimnisse --neu wechselt sie ueberall zusammen, erst Traefik, dann die Werkzeuge.
CONF
  printf '%s\n' "PROLO_EINLASS=" > "$STACK/$NAME/.env.beispiel"
  cat > "$STACK/$NAME/CHANGELOG.md" <<MD
# 0.1.0

Angelegt mit \`prolo neu $NAME\`.
MD
fi

# ----------------------------------------------------------------------
cat > "$STACK/$NAME/sicherung.conf" <<CONF
# /opt/stack/$NAME/sicherung.conf
# Angelegt mit "prolo neu $NAME". Damit ist das Werkzeug in backup.sh drin -
# zentral ist nichts zu aendern.

# Namen pruefen mit: docker volume ls | grep $NAME
VOLUMES="$([ "$ART" = eigen ] && printf '%s' "${NAME}_${NAME}_daten")"

# Fuer einen eigenen Datenbank-Container ausfuellen, sonst leer lassen.
DB_CONTAINER=""
DB_USER=""
DB_NAME=""

# Ein "?" davor heisst: darf fehlen, ohne dass die Sicherung als
# fehlgeschlagen gilt.
DATEIEN="?.env"

# SQLite IM Container, Form "behaelter:/pfad/zur.db". Leer lassen, wenn es
# keine gibt - sonst meldet jede Sicherung einen Fehler.
SQLITE=""

ORDNER=""

# Was mit Absicht NICHT gesichert wird, je Zeile "name|warum".
# Ohne Begruendung beanstandet es werkzeuge/volumes.py - und das soll es.
VOLUMES_OHNE=""

HINWEIS="Angelegt am $(date +%Y-%m-%d) mit prolo neu.
Art: $ART. Netz: $NETZ. Hostname: $HOST.
ANMELDUNG: $ANMELDUNG$([ "$ANMELDUNG" = eigene ] && printf '%s' " - KEIN Authentik davor.
Grund: $GRUND
Bedingungen nach CLAUDE.md §17a: eigenes Netz, Ratenbremse am Eingang,
2FA in der eigenen Anmeldung EINGESCHALTET.")
$([ "$ART" = fremd ] && printf '%s' "
SICHERUNG NOCH NICHT VOLLSTAENDIG: die Herstellerdatei gibt es zu diesem
Zeitpunkt noch nicht, also steht in VOLUMES nichts. Nach dem Einsetzen
der Compose-Datei des Herstellers zeigt

  python3 /opt/stack/werkzeuge/volumes.py /opt/stack $NAME

welche Volumes das Werkzeug anlegt - mit ihrem LAUFZEITnamen, der
<ordner>_<schluessel> lautet und nicht der Schluessel ist. Jedes davon
gehoert in VOLUMES oder mit Begruendung in VOLUMES_OHNE. Solange eines
fehlt, bricht die Sicherung ab und sagt welches (N-76).")
Die Volume-Namen sind geraten - vor der ersten Sicherung einmal nachsehen."
CONF

cat > "$STACK/$NAME/aktualisierung.conf" <<CONF
# /opt/stack/$NAME/aktualisierung.conf
# Angelegt mit "prolo neu $NAME".

# "image" = fertiges Abbild, "build" = eigenes Dockerfile im Ordner
TYP="$([ "$ART" = eigen ] && printf 'build' || printf 'image')"

# Interne Adresse - Dienstname und interner Port, NICHT die oeffentliche
# Domain. Der Pfad muss OHNE Anmeldung erreichbar sein (§17), sonst misst
# die Pruefung die Anmeldung statt den Dienst.
PRUEF_URL="http://$DIENST:$PORT/"

# Obergrenze, kein fester Schlaf. Hochsetzen bei Diensten, die beim Start
# Migrationen fahren.
PRUEF_WARTEN=60
CONF

# Die tool-eigene .gitignore gewinnt fuer Dateien in diesem Ordner gegen die
# Wurzeldatei - und sie muss die Ausnahmen MITTRAGEN (N-53). Wer hier
# ".env*" schreibt, ohne "!.env.beispiel" daneben, faengt seine eigene
# Vorlage mit: auf der Platte ist alles da, im Repository nichts, und
# auffallen tut es erst beim naechsten frischen Klon.
{
  printf '%s\n' ".env" ".env.*" "!.env.beispiel" "daten/" "*.db" "*.db-*" \
                "*.sqlite" ".vorschau/" "*.vor-stand-*" "__pycache__/"
} > "$STACK/$NAME/.gitignore"

# ----------------------------------------------------------------------
titel "Angelegt"
ls -1A "$STACK/$NAME" | sed 's/^/  /'

titel "Noch zu tun"
N=1
if [ "$ART" = fremd ]; then
  melde "  $N. Die docker-compose.yml des Herstellers unveraendert in"
  melde "     $STACK/$NAME/docker-compose.yml kopieren und die Zeile"
  melde "     PROLO-PLATZHALTER loeschen. Seine ports:-Zeile darf bleiben -"
  melde "     die override-Datei nimmt sie weg.  ($NAME/LIESMICH.md)"
  N=$((N+1))
fi
melde "  $N. Subdomain $HOST beim Anbieter auf die Server-IP setzen."
melde "     Pruefen mit: prolo dns"
N=$((N+1))
if [ "$ANMELDUNG" = authentik ]; then
  melde "  $N. In Authentik eine Anwendung fuer $HOST anlegen UND sie dem"
  melde "     Outpost zuweisen. Ohne die Zuweisung antwortet die Anmeldung"
  melde "     mit 403, und das sieht aus wie ein kaputtes Werkzeug."
  N=$((N+1))
fi
if [ "$ART" = eigen ]; then
  melde "  $N. .env anlegen und PROLO_EINLASS eintragen:"
  melde "       sudo prolo geheimnisse --verteilen"
  N=$((N+1))
fi
if [ "$OHNE_NETZ" -eq 1 ]; then
  melde "  $N. Das Netz nachholen:  sudo prolo netze anlegen $NETZ"
  N=$((N+1))
fi
if [ "$ART" = fremd ]; then
  # Der Schritt, der bei bitwarden gefehlt hat (N-76). Er steht NACH dem
  # Einsetzen der Herstellerdatei, weil es vorher nichts zu messen gibt -
  # und VOR dem Starten, weil danach Daten entstehen.
  melde "  $N. Sagen, was gesichert werden soll:"
  melde "       python3 $STACK/werkzeuge/volumes.py $STACK $NAME"
  melde "     zeigt jedes Volume und jeden Bind-Mount dieses Werkzeugs."
  melde "     Jedes davon gehoert in $NAME/sicherung.conf - entweder in"
  melde "     VOLUMES (wird gesichert) oder mit Begruendung in"
  melde "     VOLUMES_OHNE. Solange eines fehlt, bricht die Sicherung ab."
  N=$((N+1))
fi
melde "  $N. Starten:  sudo prolo start $NAME"
melde ""
melde "  Nachsehen, was dabei herauskommt:"
melde "    cd $STACK/$NAME && docker compose config"
melde "    prolo netze"
melde "    python3 $STACK/werkzeuge/volumes.py $STACK $NAME"
