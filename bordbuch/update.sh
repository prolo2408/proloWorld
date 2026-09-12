#!/usr/bin/env bash
#
# Bordbuch aktualisieren — holt die neueste Fassung von GitHub und spielt sie ein.
#
#   sudo ./update.sh                          neueste Veröffentlichung
#   sudo ./update.sh --version 1.2.0          bestimmte Fassung
#   sudo ./update.sh --from /tmp/paket.tar.gz aus einer Datei
#   sudo ./update.sh --pruefen                nur nachsehen, nichts ändern
#   sudo ./update.sh --token ghp_xxx          privates Repository
#
# Bei einem privaten Repository braucht GitHub einen Lesezugriff. Reihenfolge,
# in der das Skript danach sucht: --token, dann BORDBUCH_TOKEN aus der Umgebung,
# dann die Datei .env neben diesem Skript (Zeile BORDBUCH_TOKEN=...).
#
# Der Ablauf ist so gebaut, dass ein Fehlschlag nichts kaputt macht:
#   1. Datenbank und alte Programmdateien sichern
#   2. neue Dateien einspielen
#   3. Dienst neu starten und Gesundheit prüfen
#   4. antwortet er nicht → alles zurückrollen und den alten Stand starten
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${BORDBUCH_REPO:-}"
TOKEN="${BORDBUCH_TOKEN:-}"
WUNSCH=""
QUELLE=""
NUR_PRUEFEN=0
PORT_WUNSCH=""
OHNE_DIENST=0
command -v systemctl >/dev/null 2>&1 || OHNE_DIENST=1

while [ $# -gt 0 ]; do
  case "$1" in
    --version) WUNSCH="$2"; shift 2 ;;
    --from)    QUELLE="$2"; shift 2 ;;
    --repo)    REPO="$2";   shift 2 ;;
    --token)   TOKEN="$2";  shift 2 ;;
    --dir)     DIR="$2";    shift 2 ;;
    --port)    PORT_WUNSCH="$2"; shift 2 ;;
    --pruefen|--check) NUR_PRUEFEN=1; shift ;;
    --ohne-dienst|--no-service) OHNE_DIENST=1; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unbekannte Option: $1"; exit 1 ;;
  esac
done

sagen(){ printf '\033[1;33m▸\033[0m %s\n' "$*"; }
gut(){   printf '\033[1;32m✓\033[0m %s\n' "$*"; }
fehler(){ printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$DIR/server.py" ] || fehler "In $DIR liegt kein Bordbuch"
# Token aus der Ablage neben dem Programm, falls nicht anders angegeben.
if [ -z "$TOKEN" ] && [ -f "$DIR/.env" ]; then
  TOKEN=$(grep -m1 '^BORDBUCH_TOKEN=' "$DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
fi
if [ -z "$REPO" ] && [ -f "$DIR/.env" ]; then
  REPO=$(grep -m1 '^BORDBUCH_REPO=' "$DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
fi
# Kopfzeilen für curl. Ohne Token bleibt das Feld leer - dann geht nur öffentlich.
KOPF=(-H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28')
[ -n "$TOKEN" ] && KOPF+=(-H "Authorization: Bearer $TOKEN")
HIER=$(python3 "$DIR/server.py" --version)

# Port aus der Dienstdatei lesen, damit die Gesundheitsprüfung stimmt.
PORT=$(grep -oE '\-\-port [0-9]+' /etc/systemd/system/bordbuch.service 2>/dev/null | awk '{print $2}' || true)
PORT=${PORT_WUNSCH:-${PORT:-8080}}

# --- Welche Fassung ist die neueste? ---------------------------------------
if [ -z "$QUELLE" ]; then
  [ -n "$REPO" ] || fehler "Keine Quelle. Entweder --repo BENUTZER/PROJEKT angeben,
  BORDBUCH_REPO setzen oder mit --from eine Datei einspielen."
  sagen "Frage GitHub nach der neuesten Fassung von $REPO$([ -n "$TOKEN" ] && echo ' (mit Token)')"
  CODE=$(curl -sS --max-time 15 -o /tmp/bb-release.json -w '%{http_code}' \
    "${KOPF[@]}" "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null || echo 000)
  case "$CODE" in
    200) INFO=$(cat /tmp/bb-release.json) ;;
    404) fehler "GitHub findet $REPO nicht — drei mögliche Gründe:
  1. Das Repository ist privat und der Token fehlt oder darf es nicht lesen.
     Token anlegen (fein abgestimmt, nur Contents: Read) und mit --token
     übergeben oder in $DIR/.env als BORDBUCH_TOKEN= eintragen.
  2. Der Name ist falsch geschrieben (erwartet: BENUTZER/PROJEKT).
  3. Es gibt noch keine Veröffentlichung (Release) im Repository." ;;
    401) fehler "Der Token wird abgelehnt (401). Abgelaufen oder falsch kopiert?" ;;
    403) fehler "GitHub verweigert den Zugriff (403). Meist eine Zugriffsgrenze —
  in einer Stunde nochmal versuchen. Mit Token sind die Grenzen deutlich höher." ;;
    000) fehler "GitHub nicht erreichbar. Hat der Pi Internet?" ;;
    *)   fehler "GitHub antwortet mit HTTP $CODE" ;;
  esac
  rm -f /tmp/bb-release.json
  NEU=$(printf '%s' "$INFO" | python3 -c \
    'import sys,json;print(json.load(sys.stdin).get("tag_name","").lstrip("vV"))')
  [ -n "$NEU" ] || fehler "Keine Veröffentlichung gefunden. Ist im Projekt ein Release angelegt?"
  [ -n "$WUNSCH" ] && NEU="$WUNSCH"

  VERGLEICH=$(python3 - "$NEU" "$HIER" <<'PY'
import sys,re
t=lambda v:[int(x) for x in re.findall(r"\d+",v)[:3]]+[0,0,0]
a,b=t(sys.argv[1])[:3],t(sys.argv[2])[:3]
print(1 if a>b else (0 if a==b else -1))
PY
)
  echo "  hier: $HIER   ·   dort: $NEU"
  if [ "$VERGLEICH" -le 0 ] && [ -z "$WUNSCH" ]; then
    gut "Du hast schon die neueste Fassung."
    exit 0
  fi
  if [ "$NUR_PRUEFEN" = "1" ]; then
    sagen "Neuere Fassung verfügbar: $NEU (mit „sudo ./update.sh\" einspielen)"
    exit 0
  fi
  ARCHIV=$(mktemp /tmp/bordbuch-XXXXXX.tar.gz)
  sagen "Lade Fassung $NEU"
  # Über die API geladen, weil dieser Weg auch bei privaten Repositories mit
  # Token funktioniert - der Weg über github.com/archive tut das nicht.
  curl -fsSL --max-time 180 -o "$ARCHIV" "${KOPF[@]}" \
    "https://api.github.com/repos/$REPO/tarball/v$NEU" \
    || curl -fsSL --max-time 180 -o "$ARCHIV" "${KOPF[@]}" \
       "https://api.github.com/repos/$REPO/tarball/$NEU" \
    || fehler "Herunterladen fehlgeschlagen. Bei privatem Repository: Token prüfen."
  # Ein Fehlerdokument von GitHub ist kein Archiv - vor dem Auspacken merken.
  tar tzf "$ARCHIV" >/dev/null 2>&1 \
    || fehler "Die geladene Datei ist kein Archiv. Wahrscheinlich hat GitHub eine
  Fehlermeldung geschickt (fehlender Zugriff oder Tag v$NEU gibt es nicht)."
else
  [ -f "$QUELLE" ] || fehler "Datei nicht gefunden: $QUELLE"
  ARCHIV="$QUELLE"
  NEU="(aus Datei)"
  [ "$NUR_PRUEFEN" = "1" ] && { sagen "Prüfen mit --from ist nicht vorgesehen"; exit 0; }
fi

if [ "$OHNE_DIENST" = "0" ] && [ "$(id -u)" != "0" ]; then
  fehler "Zum Einspielen bitte mit sudo aufrufen"
fi

# --- Auspacken und prüfen, bevor irgendetwas ersetzt wird ------------------
TMP=$(mktemp -d)
aufraeumen(){ rm -rf "$TMP"; }
trap aufraeumen EXIT

tar xzf "$ARCHIV" -C "$TMP" || fehler "Archiv kann nicht gelesen werden"
NEUDIR=$(find "$TMP" -name server.py -maxdepth 3 -printf '%h\n' | head -1)
[ -n "$NEUDIR" ] || fehler "Im Archiv ist kein server.py"
[ -f "$NEUDIR/index.html" ] || fehler "Im Archiv fehlt index.html"

# Syntaxprüfung: eine kaputte Datei darf den laufenden Dienst nicht ersetzen.
python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$NEUDIR/server.py" \
  || fehler "server.py im Archiv ist fehlerhaft — nichts geändert"
FASSUNG_NEU=$(python3 "$NEUDIR/server.py" --version)
sagen "Archiv geprüft, enthält Fassung $FASSUNG_NEU"

# --- Sicherung -------------------------------------------------------------
STEMPEL=$(date +%Y%m%d-%H%M%S)
SICHER="$DIR/.sicherung-$STEMPEL"
mkdir -p "$SICHER"
cp "$DIR/server.py" "$DIR/index.html" "$SICHER/"
for db in "$DIR"/bordbuch.db "$DIR"/ladelog.db; do
  [ -f "$db" ] && cp "$db" "$SICHER/" || true
done
gut "Gesichert nach $(basename "$SICHER") (Datenbank und alte Programmdateien)"

# --- Einspielen ------------------------------------------------------------
BESITZER=$(stat -c '%U:%G' "$DIR/server.py")
[ "$OHNE_DIENST" = "0" ] && systemctl stop bordbuch 2>/dev/null || true
install -m 644 -o "${BESITZER%%:*}" -g "${BESITZER##*:}" "$NEUDIR/server.py"  "$DIR/server.py"
install -m 644 -o "${BESITZER%%:*}" -g "${BESITZER##*:}" "$NEUDIR/index.html" "$DIR/index.html"
for extra in bordbuch-demo.html ANLEITUNG.md CHANGELOG.md update.sh install.sh; do
  [ -f "$NEUDIR/$extra" ] && install -m 644 "$NEUDIR/$extra" "$DIR/$extra" || true
done
chmod 755 "$DIR/update.sh" "$DIR/install.sh" 2>/dev/null || true

# Ohne systemd kann das Skript nicht neu starten und auch nicht prüfen -
# es sagt, was zu tun ist, statt einen Erfolg zu behaupten.
if [ "$OHNE_DIENST" = "1" ]; then
  echo
  gut "Dateien ersetzt (Fassung $FASSUNG_NEU)."
  echo "  Kein systemd: bitte selbst neu starten, dann kurz prüfen:"
  echo "     cd $DIR && python3 server.py --port $PORT"
  echo "     curl -s localhost:$PORT/api/version"
  echo
  echo "  Alter Stand liegt in $(basename "$SICHER") — zurück mit:"
  echo "     cp $SICHER/server.py $SICHER/index.html $DIR/"
  exit 0
fi

systemctl start bordbuch

# --- Gesundheitsprüfung ----------------------------------------------------
ANTWORT=""
for i in $(seq 1 24); do
  ANTWORT=$(curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/version" 2>/dev/null || true)
  [ -n "$ANTWORT" ] && break
  sleep 0.5
done

if [ -z "$ANTWORT" ]; then
  printf '\033[1;31m✗ Die neue Fassung antwortet nicht — ich rolle zurück.\033[0m\n'
  systemctl stop bordbuch 2>/dev/null || true
  cp "$SICHER/server.py" "$SICHER/index.html" "$DIR/"
  systemctl start bordbuch
  sleep 2
  if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/version" >/dev/null 2>&1; then
    fehler "Zurückgerollt auf $HIER. Die Daten sind unberührt.
  Was schiefging steht in: journalctl -u bordbuch -n 50"
  fi
  fehler "Rückrollen hat auch nicht geholfen. Sicherung liegt in $SICHER
  Wiederherstellen: sudo cp $SICHER/* $DIR/ && sudo systemctl restart bordbuch"
fi

LAEUFT=$(printf '%s' "$ANTWORT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
STAND=$(printf '%s' "$ANTWORT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["schema"])')

echo
gut "Bordbuch $LAEUFT läuft (Datenstand $STAND)."
echo
echo "  Ergänzte Datenbankfelder stehen im Log:"
echo "     journalctl -u bordbuch -n 20"
echo
echo "  Sicherung des alten Stands (kann nach einigen Tagen weg):"
echo "     $SICHER"
echo
# Alte Sicherungen ausdünnen: die letzten fünf behalten.
ls -1dt "$DIR"/.sicherung-* 2>/dev/null | tail -n +6 | xargs -r rm -rf
