#!/usr/bin/env bash
# ProloWelt auf einem Server einrichten (Debian oder Ubuntu).
#
#   sudo git clone https://github.com/prolo2408/proloWorld /opt/prolo
#   sudo /opt/prolo/install.sh --domain prolo.me --email du@prolo.me
#
# Was es tut - jeder Schritt sieht erst nach, ob er noetig ist, darum ist
# es gefahrlos zu wiederholen:
#
#   1. Pakete: git, age, python3 (und Docker, falls es fehlt)
#   2. Sicherheitsaktualisierungen des Systems jede Nacht (unattended-upgrades)
#   3. Firewall (ufw): nur SSH, 80 und 443 von aussen
#   4. "prolo" als Befehl, dann "prolo einrichten": Einstellungen,
#      Geheimnisse, Sicherungsschluessel, Traefik, Authentik, Admin-Seite,
#      Agent und naechtliche Sicherung
#
# Weitere Angaben:
#   --schluessel <datei>   einen vorhandenen Sicherungsschluessel uebernehmen
#                          (Umzug: dann lassen sich die alten Sicherungen oeffnen)
#   --ohne-firewall        ufw nicht anfassen
set -euo pipefail

HIER="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
FIREWALL=1
WEITER=()
while [ $# -gt 0 ]; do
  case "$1" in
    --ohne-firewall) FIREWALL=0; shift ;;
    --domain|--email|--schluessel)
      [ $# -ge 2 ] || { echo "$1 braucht einen Wert." >&2; exit 2; }
      WEITER+=("$1" "$2"); shift 2 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unbekannt: $1  (prolo -h zeigt alles)" >&2; exit 2 ;;
  esac
done

# apt leise - und bei einem Fehler mit allem, was es gesagt hat.
apt_install() {
  local LOG; LOG="$(mktemp)"
  if ! DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" >"$LOG" 2>&1; then
    cat "$LOG"; rm -f "$LOG"
    echo "apt-get install $* ging nicht - die Meldung steht oben." >&2
    exit 1
  fi
  rm -f "$LOG"
}
schritt() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()      { printf '  \033[32mok\033[0m      %s\n' "$*"; }
getan()   { printf '  \033[34mgetan\033[0m   %s\n' "$*"; }
achtung() { printf '  \033[33mACHTUNG\033[0m  %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Braucht root:  sudo $0"; exit 1; }
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Dieses Skript kennt nur Debian und Ubuntu (apt-get). Auf anderen Systemen:"
  echo "  Docker mit compose-Plugin, git, age und python3 von Hand installieren, dann"
  echo "  sudo $HIER/prolo einrichten"
  exit 1
fi

# ------------------------------------------------------------------- 1
schritt "Pakete"
FEHLT=()
for P in git age python3 tar curl ca-certificates; do
  dpkg -s "$P" >/dev/null 2>&1 || FEHLT+=("$P")
done
if [ ${#FEHLT[@]} -gt 0 ]; then
  apt-get update -qq
  apt_install "${FEHLT[@]}"
  getan "installiert: ${FEHLT[*]}"
else
  ok "git, age, python3"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), compose $(docker compose version --short)"
else
  # Der Weg, den Docker selbst empfiehlt: richtet die Paketquelle von Docker
  # ein und installiert Docker samt compose-Plugin.
  echo "  Docker fehlt - installiere es über https://get.docker.com ..."
  curl -fsSL https://get.docker.com | sh >/dev/null
  getan "Docker installiert"
fi
systemctl enable --now docker >/dev/null 2>&1 || true

# ------------------------------------------------------------------- 2
schritt "Sicherheitsaktualisierungen des Systems"
if ! dpkg -s unattended-upgrades >/dev/null 2>&1; then
  apt_install unattended-upgrades
fi
AUTO=/etc/apt/apt.conf.d/20auto-upgrades
SOLL='APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";'
if [ -f "$AUTO" ] && [ "$(cat "$AUTO")" = "$SOLL" ]; then
  ok "unattended-upgrades spielt Sicherheitsaktualisierungen jede Nacht ein"
else
  printf '%s\n' "$SOLL" > "$AUTO"
  getan "unattended-upgrades eingeschaltet"
fi

# ------------------------------------------------------------------- 3
schritt "Firewall"
if [ "$FIREWALL" -eq 0 ]; then
  ok "übersprungen (--ohne-firewall)"
else
  dpkg -s ufw >/dev/null 2>&1 || apt_install ufw
  # Der SSH-Port, auf dem sshd wirklich lauscht - und der, ueber den diese
  # Sitzung gerade kommt. Ohne beides wird ufw NICHT eingeschaltet: lieber
  # keine Firewall als ein ausgesperrter Server.
  PORTS=""
  if command -v sshd >/dev/null 2>&1; then
    PORTS="$(sshd -T 2>/dev/null | awk '$1=="port"{print $2}' | sort -u | tr '\n' ' ')"
  fi
  if [ -n "${SSH_CONNECTION:-}" ]; then
    PORTS="$PORTS $(printf '%s' "$SSH_CONNECTION" | awk '{print $4}')"
  fi
  PORTS="$(tr ' ' '\n' <<< "$PORTS" | grep -E '^[0-9]+$' | sort -u | tr '\n' ' ' || true)"
  if [ -z "$PORTS" ]; then
    achtung "SSH-Port nicht erkennbar - ufw bleibt aus, damit sich niemand aussperrt."
    echo "           Von Hand: ufw allow <ssh-port>/tcp && ufw allow 80,443/tcp && ufw enable"
  else
    for P in $PORTS; do ufw allow "$P/tcp" >/dev/null; done
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    if ufw status | grep -q "Status: active"; then
      ok "ufw aktiv: SSH ($PORTS), 80, 443"
    else
      ufw --force enable >/dev/null
      getan "ufw eingeschaltet: von außen nur SSH ($PORTS), 80 und 443"
    fi
  fi
fi

# ------------------------------------------------------------------- 4
schritt "prolo"
chmod +x "$HIER/prolo"
if [ "$(readlink -f /usr/local/bin/prolo 2>/dev/null)" = "$HIER/prolo" ]; then
  ok "/usr/local/bin/prolo"
else
  ln -sf "$HIER/prolo" /usr/local/bin/prolo
  getan "/usr/local/bin/prolo zeigt auf $HIER/prolo"
fi
if [ "$HIER" != "/opt/prolo" ]; then
  achtung "Der Unterbau liegt in $HIER - vorgesehen ist /opt/prolo. Geht trotzdem."
fi

exec "$HIER/prolo" einrichten ${WEITER[@]+"${WEITER[@]}"}
