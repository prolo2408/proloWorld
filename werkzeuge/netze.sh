#!/usr/bin/env bash
# werkzeuge/netze.sh
#
# Die Netze: sehen, anlegen, schliessen - und ein Werkzeug umziehen.
#
# Warum es das gibt (N-62): die Netztrennung aus N-45 ist die wichtigste
# Schutzschicht des Stacks - jedes Werkzeug in seinem eigenen Netz, nur
# Traefik in allen. Sie war aber nur von Hand herzustellen: "docker network
# create", dann zwei Stellen in der Traefik-Datei, dann Traefik neu bauen
# (N-58). Vier Griffe, von denen drei leise ausfallen koennen.
#
# Und man konnte nicht NACHSEHEN. "Welche Netze gibt es, wer haengt drin,
# haengt Traefik ueberall mit?" war eine Frage an drei docker-Befehle und
# fuenf Dateien.
#
# Aufruf:
#   netze.sh                       Uebersicht
#   netze.sh --namen               nur die Netznamen, eine je Zeile
#   netze.sh anlegen <netz>        anlegen und bei Traefik eintragen
#   netze.sh schliessen <netz>     abbauen - nur, wenn niemand mehr drin ist
#   netze.sh umziehen <tool> <netz>  Werkzeug in ein anderes Netz
#
# Rueckgabe: 0 in Ordnung, 1 Fehler, 2 Uebersicht mit Beanstandungen.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
TRAEFIK_YML="$STACK/traefik/docker-compose.yml"

melde()     { printf '%s\n' "$*"; }
fehler()    { printf '%s\n' "$*" >&2; }
abschnitt() { printf '\n\033[1m%s\033[0m\n' "$*"; }
# Eine zu lange Spalte schiebt die ganze Zeile aus dem Fenster. Lieber
# abschneiden und das sichtbar machen.
kurz() { local s="$1" n="$2"
  [ "${#s}" -le "$n" ] && printf '%s' "$s" || printf '%s..' "${s:0:$((n-2))}"; }

root_noetig() {
  [ "$(id -u)" -eq 0 ] && return 0
  fehler "Dieser Befehl braucht root: sudo prolo netze $*"
  exit 1
}

# Docker-eigene Netze. Sie gehoeren keinem Werkzeug und werden nie
# angelegt oder geschlossen.
DOCKER_EIGEN="bridge host none"

TMP_FEHLER=$(mktemp)
trap 'rm -f "$TMP_FEHLER"' EXIT

# ----------------------------------------------------------------------
# Die Wahrheit ueber ein Werkzeug steht in seiner ZUSAMMENGESETZTEN
# Konfiguration, nicht in einer einzelnen Datei: seit N-61 liegt neben der
# Hersteller-Datei eine docker-compose.override.yml, und "docker compose"
# liest beide. "docker compose config" setzt sie zusammen - und zwar OHNE
# laufenden Docker-Dienst, also auch auf einem Rechner, auf dem gar nichts
# laeuft. Das ist eine Messung, keine Nachbildung mit regulaeren Ausdruecken.
# ----------------------------------------------------------------------
tools() {
  local d
  for d in "$STACK"/*/docker-compose.yml; do
    [ -e "$d" ] || continue
    basename "$(dirname "$d")"
  done
}

# --no-interpolate ist wesentlich: ohne das scheitert "config" an jedem
# ${...} aus einer .env, die es gerade nicht gibt - auf einem frischen Klon
# also an fast allem. Netze und Labels benutzen keine Variablen; die
# Interpolation waere hier nur eine zusaetzliche Fehlerquelle.
konfig_json() {   # $1 = Werkzeug; die Meldung landet in $TMP_FEHLER
  # Die Meldung geht ueber eine DATEI, nicht ueber eine Variable: der
  # Aufrufer schreibt "j=$(konfig_json x)", und alles, was dabei an
  # Variablen gesetzt wird, bleibt in der Subshell der Ersetzung zurueck.
  # Genau daran ist die erste Fassung gescheitert - sie meldete brav
  # "Docker sagt:" und danach eine leere Zeile (N-64).
  : > "$TMP_FEHLER"
  (cd "$STACK/$1" 2>/dev/null \
   && docker compose config --no-interpolate --format json 2>"$TMP_FEHLER")
}

# Die Meldung des letzten konfig_json-Aufrufs, eine Zeile, ohne "|" (das
# trennt hier die Felder) und auf eine lesbare Laenge gekuerzt.
konfig_fehler() {
  local m
  m=$(grep -v '^[[:space:]]*$' "$TMP_FEHLER" 2>/dev/null | head -1 \
      | tr -d '|' | cut -c1-160)
  printf '%s' "${m:-docker compose hat ohne Meldung abgebrochen}"
}

konfig_befehl() { printf 'cd %s/%s && docker compose config --no-interpolate' "$STACK" "$1"; }

docker_da() { docker network ls >/dev/null 2>&1; }

# ----------------------------------------------------------------------
# Alles, was die Dateien sagen, in einer Zeile je Fund:
#   netz|<netz>|<werkzeug>            ein Werkzeug erklaert dieses Netz
#   dienst|<werkzeug>|<dienst>|<netze>|<label>|<schutz>|<ports>|<grund>|
#          <geteilt>|<hosts>|<router ohne Anmeldung>
# ----------------------------------------------------------------------
erklaert() {   # $1 = optionaler Filter auf ein Werkzeug
  local t j
  for t in $(tools); do
    [ -z "${1:-}" ] || [ "$t" = "$1" ] || continue
    j=$(konfig_json "$t") || true
    [ -n "$j" ] || { printf 'kaputt|%s|%s\n' "$t" "$(konfig_fehler)"; continue; }
    printf '%s' "$j" | python3 -c '
import json, re, sys
t = sys.argv[1]
d = json.load(sys.stdin)

# Welche Netze erklaert dieser Ordner, und wie?
#   extern = liegt draussen, jemand anders legt es an
#   eigen  = dieser Ordner legt es an (socket-proxy macht das mit "socket")
# "default" bleibt weg: das legt Compose je Projekt an, es ist keine
# gemeinsame Flaeche und niemand kann hinein.
projekt = d.get("name") or t
for schluessel, v in sorted((d.get("networks") or {}).items()):
    v = v or {}
    name = v.get("name") or schluessel
    # Projekteigene Netze bleiben weg. Compose legt sie je Projekt an und
    # nennt sie "<projekt>_<schluessel>" - da kommt niemand von aussen
    # hinein, und Traefik hat darin nichts verloren (authentik/internal ist
    # genau so eines). Ein Netz mit EIGENEM Namen ist dagegen eine
    # gemeinsame Flaeche, auch wenn es dieser Ordner anlegt: socket-proxy
    # legt "socket" an, und Traefik haengt mit drin.
    if not v.get("external") and name == "%s_%s" % (projekt, schluessel):
        continue
    print("netz|%s|%s|%s" % (name, t, "extern" if v.get("external") else "eigen"))

for dienst, srv in sorted((d.get("services") or {}).items()):
    netze = sorted((srv.get("networks") or {}).keys())
    label = srv.get("labels") or {}
    if isinstance(label, list):
        label = dict(z.split("=", 1) for z in label if "=" in z)
    tn = label.get("traefik.docker.network", "")
    # Womit ist dieser Dienst geschuetzt? Nicht geraten, sondern aus den
    # Labels gelesen - und zwar JE ROUTER (N-84). Vorher reichte EIN
    # authentik@file irgendwo, und der ganze Dienst galt als geschuetzt.
    # Ein zweiter Router ohne Anmeldung daneben - genau der Fall, vor dem
    # §17a warnt - fiel damit weder "prolo start" noch "prolo netze" auf.
    # grenze-pruefen.sh hat es im Repository schon immer je Router
    # geprueft; auf dem Server, wo "prolo neu" Werkzeuge ohne Git anlegt,
    # lief nur diese Stelle.
    router = sorted({k[len("traefik.http.routers."):-len(".rule")]
                     for k in label
                     if k.startswith("traefik.http.routers.") and k.endswith(".rule")})
    oeffentlich = {x for x in label.get("prolo.oeffentlich", "").split(",") if x}
    ungeschuetzt = [
        r for r in router
        if r not in oeffentlich
        and "authentik@file" not in label.get("traefik.http.routers.%s.middlewares" % r, "")]
    # traefik.enable ohne eigenen Router: Traefik legt dann selbst einen
    # an, mit einer Vorgaberegel und OHNE Middleware. Offen ist er trotzdem.
    if label.get("traefik.enable") == "true" and not router:
        ungeschuetzt = ["(Vorgabe)"]
    # Die eigene Anmeldung deckt, was ohne Authentik bleibt - nur dann.
    # Ist alles hinter Authentik, bleibt es "authentik", auch wenn das
    # Werkzeug zusaetzlich eine eigene Anmeldung hat (wie in admin/).
    if ungeschuetzt and label.get("prolo.anmeldung"):
        schutz = label["prolo.anmeldung"]
        ungeschuetzt = []
    elif ungeschuetzt:
        schutz = "OFFEN"
    elif router and oeffentlich:
        schutz = "oeffentlich"
    elif router:
        schutz = "authentik"
    elif tn:
        schutz = "OFFEN"
        ungeschuetzt = ["(Vorgabe)"]
    else:
        schutz = ""
    # Veroeffentlichte Ports. Eine ports:-Zeile hebelt Firewall UND
    # Anmeldung gleichzeitig aus (CLAUDE.md §19) - darum werden sie
    # gezaehlt und nicht ueberlesen. Muss eine sein (Traefik: 80/443),
    # wird sie ERKLAERT, mit prolo.ports=<grund>. Ein fehlendes Label
    # sieht sonst genauso aus wie ein vergessenes (N-59).
    ports = []
    for pp in (srv.get("ports") or []):
        if isinstance(pp, dict) and pp.get("published"):
            ports.append(str(pp["published"]))
        elif isinstance(pp, str) and ":" in pp:
            ports.append(pp.split(":")[0])
    grund = label.get("prolo.ports", "")
    # Wer sich ein Netz mit einem anderen Werkzeug teilt, sagt es (N-62).
    # Und unter welchem Namen dieser Dienst erreichbar sein will: zwei
    # Router auf demselben Hostnamen sind ein Wettlauf, den Traefik
    # entscheidet und niemand sieht (N-68).
    geteilt = label.get("prolo.netz.geteilt", "")
    hosts = []
    for k, v in sorted(label.items()):
        if k.startswith("traefik.http.routers.") and k.endswith(".rule"):
            hosts += re.findall(r"Host\(`([^`]+)`\)", v)
    print("dienst|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s" % (
        t, dienst, ",".join(netze), tn, schutz, ",".join(ports), grund,
        geteilt, ",".join(sorted(set(hosts))), ",".join(ungeschuetzt)))
' "$t"
  done
}

traefik_netze() {
  konfig_json traefik | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("\n".join(sorted((d.get("networks") or {}).keys())))
' 2>/dev/null
}

# ----------------------------------------------------------------------
# Traefik eintragen / austragen.
#
# Zwei Stellen in derselben Datei, und beide muessen stimmen: der
# networks:-Block des DIENSTES und der networks:-Block ganz UNTEN. Fehlt
# einer, findet Traefik das Netz nicht und der Router bleibt tot - ohne
# Fehlermeldung. Darum steht das hier einmal und nicht in jeder Anleitung
# neu (CLAUDE.md §12: mehrere Stellen sind auch eine Transaktion - erst
# pruefen, ob beide gehen, dann schreiben).
# ----------------------------------------------------------------------
traefik_schreiben() {   # $1 = anlegen|austragen  $2 = Netz
  python3 - "$TRAEFIK_YML" "$1" "$2" <<'PY'
import io, re, sys
pfad, was, netz = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(pfad, encoding="utf-8").read()

# 1. Der networks:-Block des Dienstes traefik (vier Leerzeichen eingerueckt).
dienst = re.search(r"\n    networks:\n((?:      - \S+\n)+)", s)
# 2. Der networks:-Block ganz unten (Schluessel auf Spalte 2).
unten = re.search(r"\nnetworks:\n(.*)$", s, re.S)
if not dienst or not unten:
    sys.stderr.write("Die Traefik-Datei sieht anders aus als erwartet - "
                     "networks:-Block nicht gefunden. Nichts geaendert.\n")
    sys.exit(1)

liste = re.findall(r"- (\S+)", dienst.group(1))
hat_unten = re.search(r"^  %s:\s*$" % re.escape(netz), unten.group(1), re.M) is not None

if was == "anlegen":
    if netz in liste and hat_unten:
        print("schon-drin"); sys.exit(0)
    neu = sorted(set(liste) | {netz})
    s = s[:dienst.start(1)] + "".join("      - %s\n" % n for n in neu) + s[dienst.end(1):]
    if not hat_unten:
        # Neu einsortieren, alphabetisch, vor dem ersten groesseren Eintrag.
        unten = re.search(r"\nnetworks:\n(.*)$", s, re.S)
        block = unten.group(1)
        eintrag = "  %s:\n    external: true\n" % netz
        stellen = [(m.start(), m.group(1)) for m in re.finditer(r"^  (\S+):\s*$", block, re.M)]
        ziel = len(block)
        for pos, name in stellen:
            if name > netz:
                ziel = pos; break
        block = block[:ziel] + eintrag + block[ziel:]
        s = s[:unten.start(1)] + block
    print("eingetragen")
else:
    if netz not in liste and not hat_unten:
        print("war-nicht-drin"); sys.exit(0)
    neu = [n for n in liste if n != netz]
    if not neu:
        sys.stderr.write("Das waere das letzte Netz von Traefik. Nichts geaendert.\n")
        sys.exit(1)
    s = s[:dienst.start(1)] + "".join("      - %s\n" % n for n in neu) + s[dienst.end(1):]
    unten = re.search(r"\nnetworks:\n(.*)$", s, re.S)
    block = re.sub(r"^  %s:\n(?:    .*\n)*" % re.escape(netz), "", unten.group(1), flags=re.M)
    s = s[:unten.start(1)] + block
    print("ausgetragen")

io.open(pfad, "w", encoding="utf-8").write(s)
PY
}

# ----------------------------------------------------------------------
befehl_uebersicht() {
  local BEANSTANDET=0
  local DATEN TF KAPUTT
  DATEN=$(erklaert)
  TF=$(traefik_netze)
  KAPUTT=$(printf '%s\n' "$DATEN" | awk -F'|' '$1=="kaputt"{print $2}' | paste -sd' ' -)
  [ -n "$KAPUTT" ] && BEANSTANDET=1

  abschnitt "Netze"
  docker_da || melde "  (docker antwortet nicht - es steht nur, was die Dateien sagen)"
  printf '  %-20s %-24s %-8s %-7s %s\n' NETZ "GEHOERT ZU" TRAEFIK DOCKER CONTAINER

  local NETZE N WER IN_TF IN_DOCKER ANZ
  NETZE=$(printf '%s\n' "$DATEN" | awk -F'|' '$1=="netz"{print $2}' | sort -u)
  if docker_da; then
    NETZE=$(printf '%s\n%s\n' "$NETZE" \
            "$(docker network ls --format '{{.Name}}' | grep -vx -e bridge -e host -e none)" \
            | grep -v '^$' | sort -u)
  fi

  for N in $NETZE; do
    # Traefik haengt in allen und steht dafuer in einer eigenen Spalte -
    # in dieser hier waere es nur Rauschen.
    WER=$(printf '%s\n' "$DATEN" \
          | awk -F'|' -v n="$N" '$1=="netz" && $2==n && $3!="traefik"{print $3}' \
          | sort -u | paste -sd, -)
    [ -n "$WER" ] || WER="(niemand)"
    printf '%s\n' "$TF" | grep -qx "$N" && IN_TF=ja || IN_TF=NEIN
    IN_DOCKER="?"; ANZ="?"
    if docker_da; then
      if docker network inspect "$N" >/dev/null 2>&1; then
        IN_DOCKER=ja
        ANZ=$(docker network inspect -f '{{len .Containers}}' "$N" 2>/dev/null || echo "?")
      else
        IN_DOCKER=NEIN; BEANSTANDET=1
      fi
    fi
    printf '  %-20s %-24s %-8s %-7s %s\n' "$N" "$WER" "$IN_TF" "$IN_DOCKER" "$ANZ"
  done

  abschnitt "Werkzeuge"
  printf '  %-13s %-15s %-24s %-11s %s\n' WERKZEUG DIENST NETZ SCHUTZ "OFFENE PORTS"
  local Z T D NN TN SCHUTZ PORTS PASST
  while IFS='|' read -r Z T D NN TN SCHUTZ PORTS GRUND GETEILT HOSTS OFFENR; do
    [ "$Z" = dienst ] || continue
    # Dienste ohne Traefik-Bezug (Datenbank, Worker) haben hier nichts zu
    # suchen - die sollen gerade NICHT im Werkzeugnetz haengen. Offene
    # Ports melden sie trotzdem.
    if [ -z "$TN" ] && [ -z "$PORTS" ]; then continue; fi
    printf '  %-13s %-15s %-24s %-11s %s\n' "$T" "$D" "$(kurz "${NN:--}" 24)" \
           "${SCHUTZ:--}" "$([ -n "$PORTS" ] && printf '%s%s' "$PORTS" \
             "$([ -n "$GRUND" ] && printf ' (%s)' "$(kurz "$GRUND" 30)")" || printf -- '-')"
    [ "$SCHUTZ" = OFFEN ] && BEANSTANDET=1
    [ -n "$PORTS" ] && [ -z "$GRUND" ] && BEANSTANDET=1
    if [ -n "$TN" ]; then
      printf '%s' ",$NN," | grep -q ",$TN," || BEANSTANDET=1
    fi
  done <<< "$DATEN"

  # --- Was nicht stimmt -------------------------------------------------
  local HINWEISE="" KT KM
  while IFS='|' read -r Z KT KM; do
    [ "$Z" = kaputt ] || continue
    HINWEISE="$HINWEISE
  $KT: die Konfiguration laesst sich nicht lesen. Docker sagt:
     $KM
     Selbst nachsehen - genau diesen Aufruf macht prolo:
       $(konfig_befehl "$KT")"
    if printf '%s' "$KM" | grep -qi "permission denied\|not permitted\|kein Zugriff"; then
      HINWEISE="$HINWEISE
     Das ist kein kaputtes Werkzeug, das sind Rechte: die Dateien unter
     $STACK gehoeren root. Noch einmal mit sudo prolo netze."
    fi
    HINWEISE="$HINWEISE
"
  done <<< "$DATEN"
  for N in $NETZE; do
    WER=$(printf '%s\n' "$DATEN" | awk -F'|' -v n="$N" '$1=="netz" && $2==n{print $3}' | sort -u)
    [ -n "$WER" ] || continue
    printf '%s\n' "$TF" | grep -qx "$N" || { BEANSTANDET=1; HINWEISE="$HINWEISE
  $N: Traefik haengt NICHT mit drin - von aussen ist da nichts erreichbar.
     Abhilfe: sudo prolo netze anlegen $N
"; }
    if docker_da && ! docker network inspect "$N" >/dev/null 2>&1; then
      HINWEISE="$HINWEISE
  $N: gibt es im Docker nicht.
     Abhilfe: sudo prolo netze anlegen $N
"
    fi
  done

  while IFS='|' read -r Z T D NN TN SCHUTZ PORTS GRUND GETEILT HOSTS OFFENR; do
    [ "$Z" = dienst ] || continue
    if [ -n "$PORTS" ] && [ -z "$GRUND" ]; then
      HINWEISE="$HINWEISE
  $T/$D veroeffentlicht Port(s) $PORTS auf dem Host.
     Damit ist der Dienst an Traefik, an der Anmeldung und an der Firewall
     VORBEI erreichbar (CLAUDE.md §19). Die ports:-Zeile gehoert weg, oder
     - wenn sie sein muss - erklaert: Label prolo.ports=<grund>.
"
    fi
    [ "$SCHUTZ" = OFFEN ] && HINWEISE="$HINWEISE
  $T/$D hat einen Router OHNE Anmeldung und ohne Erklaerung: ${OFFENR:-?}
     Entweder middlewares=authentik@file an genau diesem Router ergaenzen,
     oder - wenn das Werkzeug seine eigene Anmeldung mitbringt - mit
     prolo.anmeldung=eigene erklaeren (CLAUDE.md §17a). Soll der Router
     mit Absicht oeffentlich sein: prolo.oeffentlich=<router>.
"
    if [ -n "$TN" ] && ! printf '%s' ",$NN," | grep -q ",$TN,"; then
      HINWEISE="$HINWEISE
  $T/$D: Label traefik.docker.network=$TN, der Dienst haengt aber in [$NN].
     Traefik sucht dann in einem Netz, in dem der Dienst nicht ist.
"
    fi
  done <<< "$DATEN"

  # --- Zwei Werkzeuge, ein Netz - und keiner sagt es (N-62/N-68) --------
  # Die Uebersicht ZEIGTE das schon ("netz-n8n  n8n,n8n_alt"), nannte es
  # aber nicht als Problem. Eine Zeile, die man selbst deuten muss, ist
  # keine Meldung.
  local WER_ALLE OHNE
  for N in $NETZE; do
    # Gezaehlt werden nur die, die sich in ein FREMDES Netz haengen
    # (art=extern). Wer sein Netz selbst anlegt, teilt nichts - er ist der
    # Eigentuemer. socket ist genau dieser Fall: socket-proxy legt es an,
    # admin haengt sich hinein. Erst ein ZWEITER Gast ist eine gemeinsame
    # Flaeche, und die gehoert erklaert.
    WER_ALLE=$(printf '%s\n' "$DATEN" \
               | awk -F'|' -v n="$N" \
                 '$1=="netz" && $2==n && $3!="traefik" && $4=="extern"{print $3}' \
               | sort -u)
    [ "$(printf '%s\n' "$WER_ALLE" | grep -c .)" -gt 1 ] || continue
    OHNE=""
    for T in $WER_ALLE; do
      printf '%s\n' "$DATEN" \
        | awk -F'|' -v t="$T" '$1=="dienst" && $2==t && $9!=""{print}' \
        | grep -q . || OHNE="$OHNE $T"
    done
    if [ -n "$OHNE" ]; then
      BEANSTANDET=1
      HINWEISE="$HINWEISE
  $N teilen sich mehrere Werkzeuge: $(printf '%s' "$WER_ALLE" | tr '\n' ' ')
     In einem Netz erreicht jeder Container jeden anderen direkt - ohne
     Traefik und ohne Anmeldung (N-45). Erlaubt ist das, aber als
     Entscheidung, nicht aus Versehen. Wer teilt, sagt warum:
       - \"prolo.netz.geteilt=<grund>\"
     Es fehlt bei:$OHNE
"
    fi
  done

  # --- Zwei Router auf demselben Hostnamen (N-68) -----------------------
  # Traefik nimmt dann einen davon, und welchen, sieht man nirgends. Das
  # ist genau der Zustand nach einer halben Umbenennung: der alte Ordner
  # liegt noch da und beansprucht denselben Namen wie der neue.
  local DOPPELT H
  DOPPELT=$(printf '%s\n' "$DATEN" \
            | awk -F'|' '$1=="dienst" && $10!=""{n=split($10,a,","); for(i=1;i<=n;i++) print a[i]}' \
            | sort | uniq -d)
  for H in $DOPPELT; do
    BEANSTANDET=1
    HINWEISE="$HINWEISE
  $H wird von mehreren Diensten beansprucht:
$(printf '%s\n' "$DATEN" | awk -F'|' -v h="$H" \
    '$1=="dienst" && index(","$10",", ","h",")>0 {print "       " $2 "/" $3}')
     Traefik nimmt einen davon, und welchen, sieht man nirgends. Einer der
     beiden gehoert weg oder auf einen anderen Namen.
"
  done

  # Der Fall aus N-58: die Datei sagt X, der laufende Container haengt in Y.
  # Ein Netz erreicht einen laufenden Container nicht nachtraeglich - Docker
  # verbindet beim Anlegen. Das sieht man NUR im Vergleich.
  if docker_da; then
    local ID IST
    while IFS='|' read -r Z T D NN TN SCHUTZ PORTS GRUND GETEILT HOSTS OFFENR; do
      [ "$Z" = dienst ] || continue
      [ -n "$TN" ] || continue
      ID=$( (cd "$STACK/$T" && docker compose ps -q "$D" 2>/dev/null) | head -1)
      [ -n "$ID" ] || continue
      IST=$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
            "$ID" 2>/dev/null)
      if ! printf '%s' " $IST" | grep -q " $TN "; then
        BEANSTANDET=1
        HINWEISE="$HINWEISE
  $T/$D LAEUFT in [$(printf '%s' "$IST" | tr -s ' ')], erklaert ist $TN.
     Ein neues Netz erreicht einen laufenden Container nicht (N-58) - Docker
     verbindet beim Anlegen. Abhilfe: sudo prolo start $T
"
      fi
    done <<< "$DATEN"
  fi

  if [ -n "$HINWEISE" ]; then
    abschnitt "Zu klaeren"
    printf '%s' "$HINWEISE"
  fi

  melde ""
  melde "  anlegen:    sudo prolo netze anlegen <netz>"
  melde "  schliessen: sudo prolo netze schliessen <netz>"
  melde "  umziehen:   sudo prolo netze umziehen <werkzeug> <netz>"
  [ "$BEANSTANDET" -eq 0 ] || return 2
  return 0
}

# ----------------------------------------------------------------------
befehl_anlegen() {
  root_noetig anlegen "$@"
  local N="${1:-}"
  [ -n "$N" ] || { fehler "Aufruf: prolo netze anlegen <netz>"; exit 1; }
  case "$N" in
    *[!a-z0-9-]*) fehler "Nur Kleinbuchstaben, Ziffern und Bindestrich."; exit 1 ;;
  esac
  for E in $DOCKER_EIGEN; do
    [ "$N" = "$E" ] && { fehler "$N ist ein Docker-eigenes Netz."; exit 1; }
  done

  local GETAN=0
  if docker_da && docker network inspect "$N" >/dev/null 2>&1; then
    melde "  Netz $N gibt es schon."
  else
    melde "  docker network create $N"
    if docker network create "$N" >/dev/null; then GETAN=1
    else fehler "  Anlegen hat nicht geklappt - die Meldung von docker steht oben."; exit 1; fi
  fi

  local ERG
  ERG=$(traefik_schreiben anlegen "$N") || exit 1
  case "$ERG" in
    schon-drin)  melde "  Traefik kennt $N bereits." ;;
    eingetragen) melde "  In $TRAEFIK_YML eingetragen (Dienst und Block unten)."; GETAN=1 ;;
  esac

  if [ "$GETAN" -eq 1 ]; then
    melde ""
    melde "  Traefik muss dafuer NEU ANGELEGT werden, nicht nur neu gestartet:"
    melde "  Docker verbindet einen Container beim Anlegen mit seinen Netzen,"
    melde "  ein laufender bekommt ein neues Netz nicht nachtraeglich (N-58)."
    melde ""
    melde "    sudo prolo start traefik"
    melde ""
    melde "  (prolo start ist 'docker compose up -d' - das legt neu an, sobald"
    melde "   sich die Konfiguration geaendert hat.)"
  fi
}

# ----------------------------------------------------------------------
befehl_schliessen() {
  root_noetig schliessen "$@"
  local N="${1:-}"
  [ -n "$N" ] || { fehler "Aufruf: prolo netze schliessen <netz>"; exit 1; }
  for E in $DOCKER_EIGEN; do
    [ "$N" = "$E" ] && { fehler "$N ist ein Docker-eigenes Netz."; exit 1; }
  done
  [ "$N" = socket ] && { fehler "socket traegt die Verbindung von Traefik zum Docker-Vermittler."; exit 1; }

  # Erklaert es noch jemand? Dann wuerde das Schliessen ein Werkzeug
  # unerreichbar machen - das ist keine Aufraeumaktion, das ist ein Ausfall.
  local WER
  WER=$(erklaert | awk -F'|' -v n="$N" '$1=="netz" && $2==n && $3!="traefik"{print $3}' \
        | sort -u | paste -sd', ' -)
  if [ -n "$WER" ]; then
    fehler "  NICHT geschlossen: $N wird noch erklaert von: $WER"
    fehler ""
    fehler "  Erst umziehen, dann schliessen:"
    fehler "    sudo prolo netze umziehen <werkzeug> <anderes-netz>"
    exit 1
  fi

  if docker_da && docker network inspect "$N" >/dev/null 2>&1; then
    local ANZ; ANZ=$(docker network inspect -f '{{len .Containers}}' "$N")
    if [ "$ANZ" -gt 0 ]; then
      fehler "  NICHT geschlossen: es haengen noch $ANZ Container in $N:"
      docker network inspect -f '{{range .Containers}}    {{.Name}}
{{end}}' "$N" >&2
      exit 1
    fi
  fi

  local ERG
  ERG=$(traefik_schreiben austragen "$N") || exit 1
  [ "$ERG" = ausgetragen ] && melde "  Aus $TRAEFIK_YML ausgetragen."
  if docker_da && docker network inspect "$N" >/dev/null 2>&1; then
    docker network rm "$N" >/dev/null && melde "  docker network rm $N"
  fi
  melde ""
  melde "  Traefik zieht nach:  sudo prolo start traefik"
}

# ----------------------------------------------------------------------
# Umziehen. Das Riskanteste hier, darum mit Kopie und Rueckweg:
#   1. Kopie jeder Datei, die angefasst wird
#   2. ersetzen
#   3. MESSEN, ob dabei das Richtige herausgekommen ist
#   4. stimmt es nicht: alles zurueck, nichts halb geaendert (§12)
# ----------------------------------------------------------------------
befehl_umziehen() {
  root_noetig umziehen "$@"
  local T="${1:-}" NEU="${2:-}"
  [ -n "$T" ] && [ -n "$NEU" ] || { fehler "Aufruf: prolo netze umziehen <werkzeug> <netz>"; exit 1; }
  [ -f "$STACK/$T/docker-compose.yml" ] || { fehler "Kein Werkzeug '$T' unter $STACK."; exit 1; }
  case "$T" in
    traefik) fehler "Traefik haengt in ALLEN Netzen - der zieht nicht um."; exit 1 ;;
  esac

  local ALT
  ALT=$(erklaert | awk -F'|' -v t="$T" '$1=="netz" && $3==t && $4=="extern"{print $2}' \
        | grep -vx socket | head -1)
  [ -n "$ALT" ] || { fehler "$T erklaert kein aeusseres Netz - da ist nichts umzuziehen."; exit 1; }
  [ "$ALT" = "$NEU" ] && { melde "  $T haengt schon in $NEU."; exit 0; }

  melde "  $T: $ALT  ->  $NEU"

  # Das Zielnetz muss es geben, sonst startet danach nichts mehr.
  if ! traefik_netze | grep -qx "$NEU"; then
    fehler ""
    fehler "  NICHT umgezogen: Traefik haengt nicht in $NEU."
    fehler "  Erst anlegen:  sudo prolo netze anlegen $NEU"
    exit 1
  fi

  local DATEIEN D KOPIEN=""
  DATEIEN=$(grep -rl -e "$ALT" "$STACK/$T"/docker-compose.yml \
              "$STACK/$T"/docker-compose.override.yml 2>/dev/null || true)
  [ -n "$DATEIEN" ] || { fehler "  $ALT steht in keiner Compose-Datei von $T."; exit 1; }

  for D in $DATEIEN; do
    cp "$D" "$D.vor-umzug" || { fehler "  Kopie von $D ging nicht. Nichts geaendert."; exit 1; }
    KOPIEN="$KOPIEN $D"
  done

  zurueck() { local D; for D in $KOPIEN; do mv "$D.vor-umzug" "$D"; done; }

  for D in $DATEIEN; do
    # Nur die drei Stellen, an denen ein Netzname etwas BEDEUTET. Ein
    # blindes sed ueber die ganze Datei wuerde auch Kommentare und
    # Volume-Namen treffen.
    python3 - "$D" "$ALT" "$NEU" <<'PY'
import io, re, sys
p, alt, neu = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(p, encoding="utf-8").read()
a = re.escape(alt)
s = re.sub(r"^(\s+- )%s(\s*)$" % a, r"\g<1>%s\g<2>" % neu, s, flags=re.M)   # Liste
s = re.sub(r"^(  )%s(:\s*)$" % a, r"\g<1>%s\g<2>" % neu, s, flags=re.M)     # Block unten
s = s.replace("traefik.docker.network=%s" % alt, "traefik.docker.network=%s" % neu)
io.open(p, "w", encoding="utf-8").write(s)
PY
  done

  # --- Messen, nicht hoffen --------------------------------------------
  local PRUEF
  PRUEF=$(erklaert | awk -F'|' -v t="$T" '$1=="netz" && $3==t && $4=="extern"{print $2}' \
          | grep -vx socket | sort | paste -sd, -)
  if [ "$PRUEF" != "$NEU" ]; then
    fehler ""
    fehler "  ABBRUCH: nach dem Ersetzen erklaert $T [$PRUEF], erwartet war $NEU."
    fehler "  Alles zurueckgenommen, keine Datei bleibt halb geaendert."
    zurueck
    exit 1
  fi
  local LABEL
  LABEL=$(erklaert | awk -F'|' -v t="$T" '$1=="dienst" && $2==t && $5!=""{print $5}' \
          | sort -u | paste -sd, -)
  if [ -n "$LABEL" ] && [ "$LABEL" != "$NEU" ]; then
    fehler ""
    fehler "  ABBRUCH: das Label traefik.docker.network sagt [$LABEL], das Netz ist $NEU."
    fehler "  Alles zurueckgenommen."
    zurueck
    exit 1
  fi

  for D in $KOPIEN; do rm -f "$D.vor-umzug"; done
  melde "  Geaendert:$(printf ' %s' $DATEIEN)"
  melde ""
  melde "  Jetzt neu anlegen, damit der Container das Netz auch bekommt (N-58):"
  melde "    sudo prolo start $T"
  melde ""
  melde "  Danach ist $ALT moeglicherweise leer:"
  melde "    sudo prolo netze schliessen $ALT"
}

# ----------------------------------------------------------------------
case "${1:-}" in
  ""|--uebersicht) befehl_uebersicht ;;
  --namen)         erklaert | awk -F'|' '$1=="netz"{print $2}' | sort -u ;;
  --dienste)       shift; erklaert "${1:-}" | grep '^dienst|' ;;
  anlegen)         shift; befehl_anlegen "$@" ;;
  schliessen)      shift; befehl_schliessen "$@" ;;
  umziehen)        shift; befehl_umziehen "$@" ;;
  *) fehler "netze: (nichts) | anlegen <netz> | schliessen <netz> | umziehen <tool> <netz>"
     exit 1 ;;
esac
