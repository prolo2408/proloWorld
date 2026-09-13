#!/usr/bin/env bash
#
# Bordbuch einrichten — ein Befehl, danach läuft es.
#
#   sudo ./install.sh                      im entpackten Ordner
#   sudo ./install.sh --port 8090          anderer Port
#   sudo ./install.sh --dir /srv/bordbuch  anderer Ort
#   sudo ./install.sh --user max           anderer Benutzer
#   ./install.sh --ohne-dienst             nur Dateien legen (Container, NAS,
#                                          Systeme ohne systemd)
#   sudo ./install.sh --repo ich/bordbuch --token ghp_xxx
#                                          privates Repository: der Token wird in
#                                          .env abgelegt, nur fuer den Dienst
#                                          lesbar (Rechte 600)
#
# Das Skript ist absichtlich wiederholbar: ein zweiter Aufruf aktualisiert die
# Dateien und lässt Datenbank, Belege und Einstellungen unangetastet.
set -euo pipefail

DIR=/opt/bordbuch
PORT=8080
BENUTZER="${SUDO_USER:-$(id -un)}"
REPO=""
TOKEN=""
OHNE_DIENST=0
# Ohne systemd (Container, manueller Betrieb) wird nur eingerichtet, nicht gestartet.
command -v systemctl >/dev/null 2>&1 || OHNE_DIENST=1

while [ $# -gt 0 ]; do
  case "$1" in
    --dir)  DIR="$2";  shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --user) BENUTZER="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --ohne-dienst|--no-service) OHNE_DIENST=1; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unbekannte Option: $1"; exit 1 ;;
  esac
done

sagen(){ printf '\033[1;33m▸\033[0m %s\n' "$*"; }
fehler(){ printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# --- Voraussetzungen -------------------------------------------------------
if [ "$OHNE_DIENST" = "0" ] && [ "$(id -u)" != "0" ]; then
  fehler "Bitte mit sudo aufrufen: sudo ./install.sh"
fi
command -v python3 >/dev/null || fehler "python3 fehlt. sudo apt install python3"

PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
python3 - <<'PY' || fehler "Python 3.9 oder neuer nötig (gefunden: $PYV)"
import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)
PY
sagen "Python $PYV gefunden"

HIER="$(cd "$(dirname "$0")" && pwd)"
for f in server.py index.html; do
  [ -f "$HIER/$f" ] || fehler "$f liegt nicht neben install.sh"
done

id "$BENUTZER" >/dev/null 2>&1 || fehler "Benutzer „$BENUTZER\" gibt es nicht"

# --- Dateien legen ---------------------------------------------------------
NEUINSTALL=1
[ -f "$DIR/server.py" ] && NEUINSTALL=0

mkdir -p "$DIR" 2>/dev/null || fehler "Kein Schreibrecht für $DIR — mit sudo aufrufen oder --dir wählen"
# Vor dem Überschreiben sichern, falls schon Daten da sind.
if [ "$NEUINSTALL" = "0" ]; then
  for db in "$DIR"/bordbuch.db "$DIR"/ladelog.db; do
    if [ -f "$db" ]; then
      SICHER="$DIR/vorher-$(date +%Y%m%d-%H%M%S).db"
      cp "$db" "$SICHER"
      sagen "Datenbank gesichert: $(basename "$SICHER")"
    fi
  done
fi

install -m 644 "$HIER/server.py"  "$DIR/server.py"
install -m 644 "$HIER/index.html" "$DIR/index.html"
for extra in bordbuch-demo.html ANLEITUNG.md CHANGELOG.md update.sh; do
  [ -f "$HIER/$extra" ] && install -m 644 "$HIER/$extra" "$DIR/$extra" || true
done
[ -f "$DIR/update.sh" ] && chmod 755 "$DIR/update.sh"
mkdir -p "$DIR/receipts"

# Zugangsdaten getrennt von der Dienstdatei ablegen: Unit-Dateien sind fuer alle
# lesbar, diese Datei nicht. Sie enthaelt nur, was wirklich geheim ist.
if [ -n "$REPO" ] || [ -n "$TOKEN" ]; then
  {
    [ -n "$REPO" ]  && echo "BORDBUCH_REPO=$REPO"
    [ -n "$TOKEN" ] && echo "BORDBUCH_TOKEN=$TOKEN"
  } > "$DIR/.env"
  chmod 600 "$DIR/.env"
  [ "$(id -u)" = "0" ] && chown "$BENUTZER":"$BENUTZER" "$DIR/.env" || true
  sagen "Zugangsdaten in $DIR/.env abgelegt (nur fuer $BENUTZER lesbar)"
fi
[ "$(id -u)" = "0" ] && chown -R "$BENUTZER":"$BENUTZER" "$DIR" || true
sagen "Dateien liegen in $DIR"

# --- Ohne systemd: hier ist Schluss ---------------------------------------
if [ "$OHNE_DIENST" = "1" ]; then
  echo
  printf '\033[1;32m✓ Dateien eingerichtet in %s\033[0m\n\n' "$DIR"
  echo "  Kein systemd gefunden (oder --ohne-dienst gewählt). Selbst starten:"
  echo "     cd $DIR && python3 server.py --port $PORT"
  echo
  echo "  Dauerhaft im Hintergrund, ohne systemd:"
  echo "     cd $DIR && nohup python3 server.py --port $PORT >bordbuch.log 2>&1 &"
  echo
  exit 0
fi

# --- Dienst schreiben ------------------------------------------------------
# Bewusst erzeugt statt kopiert: Pfad, Port und Benutzer kommen aus den
# Optionen, damit niemand eine Datei von Hand nachbearbeiten muss.
cat > /etc/systemd/system/bordbuch.service <<DIENST
[Unit]
Description=Bordbuch - Fahrzeugkosten und Wartung
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$BENUTZER
Group=$BENUTZER
WorkingDirectory=$DIR
# Quelle und Token stehen in .env, nicht in dieser fuer alle lesbaren Datei.
EnvironmentFile=-$DIR/.env
ExecStart=/usr/bin/python3 $DIR/server.py --port $PORT
Restart=on-failure
RestartSec=5

# Der Dienst darf nur sein eigenes Verzeichnis beschreiben.
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$DIR

[Install]
WantedBy=multi-user.target
DIENST

systemctl daemon-reload
systemctl enable bordbuch >/dev/null
systemctl restart bordbuch
sagen "Dienst eingerichtet und gestartet"

# --- Prüfen, ob es wirklich läuft -----------------------------------------
for i in $(seq 1 20); do
  ANTWORT=$(curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/version" 2>/dev/null || true)
  [ -n "$ANTWORT" ] && break
  sleep 0.5
done

if [ -z "${ANTWORT:-}" ]; then
  echo
  fehler "Der Dienst antwortet nicht. Log ansehen mit: journalctl -u bordbuch -n 40"
fi

FASSUNG=$(printf '%s' "$ANTWORT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo
printf '\033[1;32m✓ Bordbuch %s läuft.\033[0m\n\n' "$FASSUNG"
echo "  Im Browser öffnen:"
echo "     http://$(hostname).local:$PORT"
[ -n "$IP" ] && echo "     http://$IP:$PORT"
echo
echo "  Nützliche Befehle:"
echo "     systemctl status bordbuch      läuft es?"
echo "     journalctl -u bordbuch -f      mitlesen"
echo "     sudo $DIR/update.sh            aktualisieren"
echo
if [ "$NEUINSTALL" = "1" ]; then
  echo "  Beim ersten Aufruf legst du dein Profil an. Danach unter"
  echo "  Einstellungen › Fahrzeuge bearbeiten das erste Auto eintragen."
else
  echo "  Aktualisierung abgeschlossen. Deine Daten sind unverändert."
fi
echo
