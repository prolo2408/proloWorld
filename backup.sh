#!/bin/bash
set -euo pipefail

DATUM=$(date +%Y-%m-%d)
ZIEL="/opt/backups/$DATUM"
BESITZER="prolo"
mkdir -p "$ZIEL"

# --- Feste Bestandteile ---------------------------------------------
cp /opt/stack/traefik/acme.json "$ZIEL/acme.json"

# --- Alle Tools durchgehen ------------------------------------------
for KONF in /opt/stack/*/sicherung.conf; do
  [ -e "$KONF" ] || continue
  TOOL=$(basename "$(dirname "$KONF")")

  VOLUMES=""; DB_CONTAINER=""; DB_USER=""; DB_NAME=""; DATEIEN=""; HINWEIS=""
  # shellcheck disable=SC1090
  . "$KONF"

  echo "Sichere $TOOL"
  mkdir -p "$ZIEL/$TOOL"

  if [ -n "$DB_CONTAINER" ]; then
    docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" \
      | gzip > "$ZIEL/$TOOL/datenbank.sql.gz"
  fi

  for V in $VOLUMES; do
    docker run --rm -v "$V":/daten -v "$ZIEL/$TOOL":/backup alpine \
      tar czf "/backup/$V.tar.gz" -C /daten . 2>/dev/null \
      || echo "  WARNUNG: Volume $V nicht gefunden"
  done

  for D in $DATEIEN; do
    [ -f "/opt/stack/$TOOL/$D" ] && cp "/opt/stack/$TOOL/$D" "$ZIEL/$TOOL/"
  done
done

# --- Aufraeumen und Rechte ------------------------------------------
find /opt/backups -maxdepth 1 -mindepth 1 -type d -mtime +90 -exec rm -rf {} +
chown -R "$BESITZER":"$BESITZER" /opt/backups
find /opt/backups -name ".env" -o -name "acme.json" | xargs -r chmod 600

echo "Backup fertig: $ZIEL"
