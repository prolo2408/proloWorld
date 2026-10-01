#!/bin/bash
# /opt/stack/backup.sh
#
# Zentrale Sicherung aller Tools. Liest je Tool die sicherung.conf
# (CLAUDE.md §23) und legt genau EINEN Stand pro Tag ab.
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
# Die drei Orte lassen sich von aussen setzen - nur, damit sich dieses
# Skript im Ablauf pruefen laesst (werkzeuge/sicherung-lauf-pruefen.sh,
# N-86). Auf dem Server gelten die Vorgaben.
STACK="${PROLO_STACK:-/opt/stack}"
# Das Hilfsabbild fuer tar in Volumes - feste Fassung, nie latest (§19,
# N-108). Steht gleich in backup.sh, werkzeuge/prolo und
# werkzeuge/wiederherstellen.sh; werkzeuge/abbilder-pruefen.sh haelt es zusammen.
HILFSABBILD="alpine:3.22.6"
BACKUPS="${PROLO_SICHERUNGEN:-/opt/backups}"
BESITZER="${PROLO_BESITZER:-prolo}"
ZIEL="$BACKUPS/$DATUM"
SCHLUESSEL="$STACK/.backup-schluessel.pub"
FEHLER=0

# Genau ein Stand pro Tag - ein erneuter Lauf ersetzt den alten (Abschnitt 15).
rm -rf "$ZIEL"
mkdir -p "$ZIEL"

# --- Weiss die Sicherung ueberhaupt, was es zu sichern gibt? --------
#
# Frueher stand hier ein fester Block, der acme.json kopierte - der einzige
# Toolname im zentralen Skript, und damit der einzige Grund, warum traefik
# ohne eigene sicherung.conf durchkam. Jetzt hat es eine (N-76), und
# stattdessen misst dieser Schritt, ob IRGENDEIN Werkzeug Daten ablegt,
# die in keiner sicherung.conf stehen.
#
# Gemessen wird die zusammengesetzte Compose-Konfiguration, nicht eine
# Datei - bei einem Fremdwerkzeug steht die Haelfte im Overlay (§16).
LUECKEN=""
if [ -x "$STACK/werkzeuge/volumes.py" ]; then
  LUECKEN=$(python3 "$STACK/werkzeuge/volumes.py" "$STACK" 2>/dev/null \
            | grep '|FEHLT$' || true)
fi
if [ -n "$LUECKEN" ]; then
  {
    echo
    echo "ACHTUNG: hier entstehen Daten, die NICHT gesichert werden."
    echo
    echo "  Das ist keine Warnung, sondern eine Luecke: was hier nicht steht,"
    echo "  ist nach einem Verlust weg. Je Zeile die genannte Zeile in die"
    echo "  sicherung.conf des Werkzeugs - oder, wenn es wirklich keine"
    echo "  Sicherung braucht, VOLUMES_OHNE mit einer Begruendung:"
    echo
    # Die Zeile haengt von der ART ab. Ein Bind-Mount gehoert NICHT in
    # VOLUMES - das ist fuer benannte Docker-Volumes. Eine Meldung, die
    # die falsche Zeile nennt, schickt in den naechsten Fehlversuch
    # (N-78).
    printf '%s\n' "$LUECKEN" | while IFS='|' read -r T ART NAME _; do
      case "$ART" in
        volume)    ZEILE="VOLUMES=\"... $NAME\"" ; WAS="benanntes Docker-Volume" ;;
        bind)      ZEILE="ORDNER=\"... $NAME\""  ; WAS="Ordner im Werkzeugordner" ;;
        binddatei) ZEILE="DATEIEN=\"... $NAME\"" ; WAS="Datei im Werkzeugordner" ;;
        *)         ZEILE="VOLUMES_OHNE=\"$NAME|<warum>\""; WAS="$ART" ;;
      esac
      printf '  %s  (%s)\n' "$T/$NAME" "$WAS"
      printf '      %s\n' "$ZEILE"
      printf '      oder  VOLUMES_OHNE="%s|<warum>"\n\n' "$NAME"
    done
    echo "  Nachsehen, was ein Werkzeug anlegt:"
    echo "    python3 $STACK/werkzeuge/volumes.py $STACK <werkzeug>"
    echo
  } >&2
  FEHLER=1
fi

# --- Alle Tools durchgehen ------------------------------------------
for KONF in "$STACK"/*/sicherung.conf; do
  [ -e "$KONF" ] || continue
  TOOL=$(basename "$(dirname "$KONF")")

  VOLUMES=""; DB_CONTAINER=""; DB_USER=""; DB_NAME=""; DATEIEN=""
  ORDNER=""; SQLITE=""; HINWEIS=""; VOLUMES_OHNE=""
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
      # Keine halbe Datei liegen lassen (N-86), wie bei SQLite unten: gzip
      # schreibt auch aus einer leeren Leitung eine gueltige .gz. Im Archiv
      # saehe sie aus wie eine Sicherung - leer oder mittendrin abgebrochen.
      rm -f "$ZIEL/$TOOL/datenbank.sql.gz"
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
    docker run --rm -v "$V":/daten -v "$ZIEL/$TOOL":/backup "$HILFSABBILD" \
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
    if [ -f "$STACK/$TOOL/$D" ]; then
      # Mit Pfad, nicht flach (N-101): "konf/app.yml" landete vorher als
      # "app.yml" im Archiv - und die Wiederherstellung suchte es unter
      # "konf/app.yml", fand nichts und meldete FEHLT.
      mkdir -p "$(dirname "$ZIEL/$TOOL/$D")"
      cp "$STACK/$TOOL/$D" "$ZIEL/$TOOL/$D"
    elif [ "$FREIWILLIG" -eq 1 ]; then
      echo "  Hinweis: $STACK/$TOOL/$D gibt es nicht - uebersprungen."
    else
      echo "  WARNUNG: $STACK/$TOOL/$D fehlt" >&2
      FEHLER=1
    fi
  done

  # Bind-Mounts aus dem Tool-Ordner. DATEIEN kopiert nur Dateien ([ -f ... ]);
  # ./data und ./certs bei Authentik sind Ordner und wurden von KEINER
  # Sicherung erfasst - dort liegen Medien, eigene Vorlagen und Zertifikate.
  for O in ${ORDNER:-}; do
    FREIWILLIG=0
    case "$O" in "?"*) FREIWILLIG=1; O="${O#\?}" ;; esac
    if [ -d "$STACK/$TOOL/$O" ]; then
      # Ein Ordner mit Unterpfad ("auftraege/erledigt") braucht den Ordner
      # davor auch im Archiv (N-101). Ohne ihn scheiterte tar, und mit ihm
      # jede Aktualisierung - gemessen beim ersten echten Lauf.
      mkdir -p "$(dirname "$ZIEL/$TOOL/$O.tar.gz")"
      tar czf "$ZIEL/$TOOL/$O.tar.gz" -C "$STACK/$TOOL" "$O"
    elif [ "$FREIWILLIG" -eq 1 ]; then
      echo "  Hinweis: $STACK/$TOOL/$O gibt es nicht - uebersprungen."
    else
      echo "  WARNUNG: Ordner $STACK/$TOOL/$O fehlt" >&2
      FEHLER=1
    fi
  done

  # Der Werkzeugordner selbst (N-87): Compose-Dateien, conf-Dateien,
  # LIESMICH. Bisher verliess sich die Sicherung dafuer aufs Git - aber
  # "prolo neu" legt Werkzeuge auf dem Server an, und die stehen in keinem
  # Git. Nach einem Serververlust waeren ihre Daten da und niemand wuesste
  # mehr, wie man sie startet.
  #
  # Ausgenommen: was ohnehin einzeln gesichert wird (ORDNER), und Ordner,
  # die ausdruecklich keine Sicherung brauchen (VOLUMES_OHNE, z. B. die
  # Zugriffsprotokolle von Traefik) - die koennen gross werden und gehoeren
  # nicht in eine Konfiguration.
  AUSNAHMEN=()
  for O in ${ORDNER:-}; do AUSNAHMEN+=("--exclude=$TOOL/${O#\?}"); done
  while IFS='|' read -r NAME _; do
    [ -n "$NAME" ] && [ -d "$STACK/$TOOL/$NAME" ] && AUSNAHMEN+=("--exclude=$TOOL/$NAME")
  done <<< "${VOLUMES_OHNE:-}"
  if ! tar czf "$ZIEL/$TOOL/werkzeug.tar.gz" -C "$STACK" \
         ${AUSNAHMEN[@]+"${AUSNAHMEN[@]}"} "$TOOL"; then
    echo "  WARNUNG: der Werkzeugordner $TOOL liess sich nicht sichern" >&2
    rm -f "$ZIEL/$TOOL/werkzeug.tar.gz"
    FEHLER=1
  fi
done

# --- Rechte VOR dem Verschluesseln ----------------------------------
# Nicht mehr selektiv auf zwei Dateinamen, sondern auf alles: die
# Volume-Archive sind genauso schuetzenswert wie die .env darin.
chmod 700 "$BACKUPS"
find "$BACKUPS" -type d -exec chmod 700 {} +
find "$BACKUPS" -type f -exec chmod 600 {} +

# --- Verschluesseln -------------------------------------------------
# Der oeffentliche Schluessel darf auf dem Server liegen, der private NICHT -
# liegt er hier, ist die Verschluesselung sinnlos. Er gehoert ausschliesslich
# in den Passwortmanager und auf den Arbeitsrechner.
#   Erzeugen dort:  age-keygen -o ~/.age/prolo.key
#   Oeffentlichen Teil hierher:  /opt/stack/.backup-schluessel.pub
#
# Wohin das Archiv kommt, entscheidet sich ERST NACH dem Lauf (N-86).
# Vorher schrieb age direkt auf <datum>.tar.gz.age - und "prolo
# aktualisieren" sichert vor jedem Lauf. Ging am Nachmittag etwas schief
# (Authentiks Datenbank gerade nicht erreichbar), ersetzte der halbe Stand
# den vollstaendigen vom Morgen. Die eine Sicherung des Tages war dann
# genau die, die fehlschlug.
#
#   ohne Fehler                    -> ersetzt den Stand des Tages
#   mit Fehlern, Tag schon belegt  -> daneben: <datum>-unvollstaendig-<zeit>
#   mit Fehlern, Tag noch leer     -> wird der Stand des Tages (besser als
#                                     nichts, und FEHLER bleibt gesetzt)
#
# "<datum>-unvollstaendig-..." sortiert VOR "<datum>.tar.gz.age" ('-' vor
# '.'), also nimmt "prolo wiederherstellen" ohne --stand weiter den
# vollstaendigen.
if [ -f "$SCHLUESSEL" ] && command -v age >/dev/null 2>&1; then
  ARCHIV="$BACKUPS/$DATUM.tar.gz.age"
  NEU="$BACKUPS/.$DATUM.tar.gz.age.neu"
  if tar czf - -C "$BACKUPS" "$DATUM" | age -R "$SCHLUESSEL" -o "$NEU"; then
    rm -rf "$ZIEL"                      # nur die verschluesselte Fassung bleibt
    chmod 600 "$NEU"
    if [ "$FEHLER" -ne 0 ] && [ -f "$ARCHIV" ]; then
      DANEBEN="$BACKUPS/$DATUM-unvollstaendig-$(date +%H%M%S).tar.gz.age"
      mv "$NEU" "$DANEBEN"
      echo "Verschluesselt, aber UNVOLLSTAENDIG: $DANEBEN" >&2
      echo "  Der vollstaendige Stand des Tages bleibt unangetastet:" >&2
      echo "    $ARCHIV" >&2
    else
      mv "$NEU" "$ARCHIV"
      echo "Verschluesselt: $ARCHIV"
    fi
  else
    rm -f "$NEU"
    echo "WARNUNG: Verschluesseln fehlgeschlagen - der Klartextstand bleibt liegen." >&2
    FEHLER=1
  fi
elif [ ! -f "$SCHLUESSEL" ]; then
  echo "WARNUNG: kein Schluessel unter $SCHLUESSEL - Sicherung bleibt im KLARTEXT." >&2
  echo "         CLAUDE.md §23 verlangt eine verschluesselte Sicherung." >&2
  FEHLER=1
else
  echo "WARNUNG: 'age' ist nicht installiert (apt install age) - Sicherung bleibt im KLARTEXT." >&2
  FEHLER=1
fi

# --- Aufraeumen -----------------------------------------------------
# Aufbewahrung: drei Monate. Beides, Ordner und verschluesselte Archive.
find "$BACKUPS" -maxdepth 1 -mindepth 1 -type d -mtime +90 -exec rm -rf {} +
find "$BACKUPS" -maxdepth 1 -type f -name '*.tar.gz.age' -mtime +90 -delete
chown -R "$BESITZER":"$BESITZER" "$BACKUPS"

# --- Rueckmeldung ---------------------------------------------------
# Eine Sicherung, deren Scheitern niemand merkt, ist keine Sicherung.
# Die Ueberwachung schlaegt an, wenn .letzter-erfolg aelter als zwei Tage ist.
if [ "$FEHLER" -eq 0 ]; then
  date -Iseconds > "$BACKUPS/.letzter-erfolg"
  echo "Backup fertig: $DATUM"
else
  echo "BACKUP MIT FEHLERN - bitte nachsehen. .letzter-erfolg wurde NICHT gesetzt." >&2
  if [ -n "$LUECKEN" ]; then
    # Zweimal dasselbe zu sagen ist hier Absicht: die Liste steht ganz
    # oben, und wer eine lange Sicherung laufen laesst, sieht nur das Ende.
    echo "  Darunter ungesicherte Daten - die Liste steht oben in dieser Ausgabe." >&2
  fi
  exit 1
fi
