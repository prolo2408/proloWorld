#!/bin/bash
# /opt/stack/backup.sh
#
# Zentrale Sicherung aller Tools. Liest je Tool die sicherung.conf
# (Betriebsregeln 14) und legt genau EINEN Stand pro Tag ab.
#
# Aus B-08 geaendert - vorher waren es fuenf getrennte Probleme:
#   a) Keine Verschluesselung. acme.json mit den privaten TLS-Schluesseln
#      aller Subdomains und alle .env lagen im Klartext unter /opt/backups
#      und wurden per rsync auf einen Windows-Rechner geschoben.
#   b) Rechte nur auf zwei Dateinamen. Die Volume-Archive - die vollstaendige
#      Bordbuch-Datenbank, alle Tankquittungen, die gesamte
#      Authentik-Datenbank - behielten die Rechte aus der Umask, ueblicherweise
#      0644. Jeder Nutzer auf dem Server konnte sie lesen.
#   c) SQLite wurde im laufenden Betrieb kopiert. Bordbuch und Wiki laufen im
#      WAL-Modus; ein tar ueber das Volume greift .db, .db-wal und .db-shm zu
#      verschiedenen Zeitpunkten ab. Das Ergebnis kann eine unbrauchbare
#      Datenbank sein - und man merkt es erst beim Wiederherstellen.
#   d) Ein zweiter Lauf am selben Tag mischte alt und neu. Archive eines
#      entfernten Tools blieben liegen und sahen aus wie gueltige Sicherungen.
#   e) Kein Abbruchschutz: fehlte acme.json, brach die GESAMTE Sicherung ab,
#      bevor ein einziges Tool gesichert war.

set -euo pipefail

DATUM=$(date +%Y-%m-%d)
ZIEL="/opt/backups/$DATUM"
BESITZER="prolo"
SCHLUESSEL="/opt/stack/.backup-schluessel.pub"
FEHLER=0

# Genau ein Stand pro Tag - ein erneuter Lauf ersetzt den alten (Abschnitt 15).
rm -rf "$ZIEL"
mkdir -p "$ZIEL"

# --- Feste Bestandteile ---------------------------------------------
# Mit ||-Zweig: eine fehlende Datei darf nicht die ganze Sicherung verhindern.
if [ -f /opt/stack/traefik/acme.json ]; then
  cp /opt/stack/traefik/acme.json "$ZIEL/acme.json"
else
  echo "WARNUNG: /opt/stack/traefik/acme.json fehlt" >&2
  FEHLER=1
fi

# --- Alle Tools durchgehen ------------------------------------------
for KONF in /opt/stack/*/sicherung.conf; do
  [ -e "$KONF" ] || continue
  TOOL=$(basename "$(dirname "$KONF")")

  VOLUMES=""; DB_CONTAINER=""; DB_USER=""; DB_NAME=""; DATEIEN=""
  ORDNER=""; SQLITE=""; HINWEIS=""
  # shellcheck disable=SC1090
  . "$KONF"

  echo "Sichere $TOOL"
  mkdir -p "$ZIEL/$TOOL"

  if [ -n "$DB_CONTAINER" ]; then
    if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" \
         | gzip > "$ZIEL/$TOOL/datenbank.sql.gz"; then
      :
    else
      echo "  WARNUNG: pg_dump fuer $DB_CONTAINER fehlgeschlagen" >&2
      FEHLER=1
    fi
  fi

  # SQLite konsistent sichern, VOR dem Volume-Lauf.
  #
  # sqlite3.backup() aus der Standardbibliothek liest einen in sich
  # geschlossenen Stand, auch waehrend geschrieben wird - der Container muss
  # dafuer nicht angehalten werden. Das Volume-Archiv bleibt zusaetzlich (es
  # enthaelt die Belege), die Datenbank DARIN gilt aber nicht mehr als
  # Sicherung.
  for EINTRAG in ${SQLITE:-}; do
    BEHAELTER="${EINTRAG%%:*}"; PFAD="${EINTRAG#*:}"
    NAME=$(basename "$PFAD")
    # Die Kopie wird im Container erzeugt und direkt nach stdout gestreamt.
    #
    # Vorher lief das ueber "docker cp" aus /tmp heraus. Das ist am
    # 15.09.2026 gebrochen, nachdem Bordbuch mit read_only: true und
    # tmpfs /tmp neu gebaut worden war (B-29):
    #   Error response from daemon: Could not find the file
    #   /tmp/bordbuch.db.sicherung in container bordbuch
    # Der Umweg ueber das Dateisystem des Containers ist dafuer gar nicht
    # noetig - cat genuegt, und damit ist es egal, ob /tmp ein tmpfs, ein
    # Volume oder read_only ist.
    #
    # WICHTIG: alles in EINEM sh -c. Ein zweiter docker exec waere ein
    # eigener Prozess; bei einem tmpfs pro exec waere die Datei dort weg.
    if docker exec "$BEHAELTER" sh -c '
set -e
python3 - "$1" "$2" <<"PY"
import sqlite3, sys
q = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
z = sqlite3.connect(sys.argv[2])
q.backup(z); z.close(); q.close()
PY
cat "$2"
rm -f "$2"
' _ "$PFAD" "/tmp/$NAME.sicherung" > "$ZIEL/$TOOL/$NAME" 2>/dev/null \
       && [ -s "$ZIEL/$TOOL/$NAME" ]; then
      echo "  Datenbank gesichert: $NAME ($(stat -c%s "$ZIEL/$TOOL/$NAME") Bytes)"
    else
      echo "  WARNUNG: SQLite-Sicherung von $PFAD fehlgeschlagen" >&2
      rm -f "$ZIEL/$TOOL/$NAME"        # keine halbe Datei liegen lassen
      FEHLER=1
    fi
  done

  for V in $VOLUMES; do
    docker run --rm -v "$V":/daten -v "$ZIEL/$TOOL":/backup alpine \
      tar czf "/backup/$V.tar.gz" -C /daten . 2>/dev/null \
      || { echo "  WARNUNG: Volume $V nicht gefunden" >&2; FEHLER=1; }
  done

  # Ein "?" vor dem Namen heisst: darf fehlen. Das ist noetig, weil sonst
  # jeder Lauf einen Fehler meldet, nur weil ein Tool die Datei im normalen
  # Betrieb gar nicht hat - und eine Sicherung, die immer "mit Fehlern"
  # endet, wird nicht mehr gelesen. Ohne "?" ist eine fehlende Datei ein
  # Fehler: bei authentik/.env waere das Fehlen ernst.
  for D in $DATEIEN; do
    FREIWILLIG=0
    case "$D" in "?"*) FREIWILLIG=1; D="${D#\?}" ;; esac
    if [ -f "/opt/stack/$TOOL/$D" ]; then
      cp "/opt/stack/$TOOL/$D" "$ZIEL/$TOOL/"
    elif [ "$FREIWILLIG" -eq 1 ]; then
      echo "  Hinweis: /opt/stack/$TOOL/$D gibt es nicht - uebersprungen."
    else
      echo "  WARNUNG: /opt/stack/$TOOL/$D fehlt" >&2
      FEHLER=1
    fi
  done

  # Bind-Mounts aus dem Tool-Ordner. DATEIEN kopiert nur Dateien ([ -f ... ]);
  # ./data und ./certs bei Authentik sind Ordner und wurden von KEINER
  # Sicherung erfasst - dort liegen Medien, eigene Vorlagen und Zertifikate.
  for O in ${ORDNER:-}; do
    FREIWILLIG=0
    case "$O" in "?"*) FREIWILLIG=1; O="${O#\?}" ;; esac
    if [ -d "/opt/stack/$TOOL/$O" ]; then
      tar czf "$ZIEL/$TOOL/$O.tar.gz" -C "/opt/stack/$TOOL" "$O"
    elif [ "$FREIWILLIG" -eq 1 ]; then
      echo "  Hinweis: /opt/stack/$TOOL/$O gibt es nicht - uebersprungen."
    else
      echo "  WARNUNG: Ordner /opt/stack/$TOOL/$O fehlt" >&2
      FEHLER=1
    fi
  done
done

# --- Rechte VOR dem Verschluesseln ----------------------------------
# Nicht mehr selektiv auf zwei Dateinamen, sondern auf alles: die
# Volume-Archive sind genauso schuetzenswert wie die .env darin.
chmod 700 /opt/backups
find /opt/backups -type d -exec chmod 700 {} +
find /opt/backups -type f -exec chmod 600 {} +

# --- Verschluesseln -------------------------------------------------
# Der oeffentliche Schluessel darf auf dem Server liegen, der private NICHT -
# liegt er hier, ist die Verschluesselung sinnlos. Er gehoert ausschliesslich
# in den Passwortmanager und auf den Arbeitsrechner.
#   Erzeugen dort:  age-keygen -o ~/.age/prolo.key
#   Oeffentlichen Teil hierher:  /opt/stack/.backup-schluessel.pub
if [ -f "$SCHLUESSEL" ] && command -v age >/dev/null 2>&1; then
  if tar czf - -C /opt/backups "$DATUM" | age -R "$SCHLUESSEL" -o "/opt/backups/$DATUM.tar.gz.age"; then
    rm -rf "$ZIEL"                      # nur die verschluesselte Fassung bleibt
    chmod 600 "/opt/backups/$DATUM.tar.gz.age"
    echo "Verschluesselt: /opt/backups/$DATUM.tar.gz.age"
  else
    echo "WARNUNG: Verschluesseln fehlgeschlagen - der Klartextstand bleibt liegen." >&2
    FEHLER=1
  fi
elif [ ! -f "$SCHLUESSEL" ]; then
  echo "WARNUNG: kein Schluessel unter $SCHLUESSEL - Sicherung bleibt im KLARTEXT." >&2
  echo "         Betriebsregeln 13 verlangt eine verschluesselte Sicherung." >&2
  FEHLER=1
else
  echo "WARNUNG: 'age' ist nicht installiert (apt install age) - Sicherung bleibt im KLARTEXT." >&2
  FEHLER=1
fi

# --- Aufraeumen -----------------------------------------------------
# Aufbewahrung: drei Monate. Beides, Ordner und verschluesselte Archive.
find /opt/backups -maxdepth 1 -mindepth 1 -type d -mtime +90 -exec rm -rf {} +
find /opt/backups -maxdepth 1 -type f -name '*.tar.gz.age' -mtime +90 -delete
chown -R "$BESITZER":"$BESITZER" /opt/backups

# --- Rueckmeldung ---------------------------------------------------
# Eine Sicherung, deren Scheitern niemand merkt, ist keine Sicherung.
# Die Ueberwachung schlaegt an, wenn .letzter-erfolg aelter als zwei Tage ist.
if [ "$FEHLER" -eq 0 ]; then
  date -Iseconds > /opt/backups/.letzter-erfolg
  echo "Backup fertig: $DATUM"
else
  echo "BACKUP MIT FEHLERN - bitte nachsehen. .letzter-erfolg wurde NICHT gesetzt." >&2
  exit 1
fi
