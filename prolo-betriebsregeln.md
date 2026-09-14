# Prolo — Betriebsregeln für den Stack

Verbindlich für jeden Agenten und jede Sitzung, die ein Tool für diesen
Server baut, ändert, sichert oder aktualisiert.

Begleitdatei: **`prolo-regelblatt.md`** regelt Design, Bedienbarkeit,
Robustheit und Nutzerfreundlichkeit. Diese Datei regelt alles rundherum.

**Umgebung:** Debian 13, Docker, Traefik als Reverse-Proxy, Authentik als
Anmeldung, Basisdomain `prolo.me`. Alles unter `/opt/stack/`, ein
privates Git-Repository.

---

# TEIL I — AUFBAU EINES TOOLS

## 1. Verzeichnis und Struktur

Jedes Tool bekommt genau einen Ordner unter `/opt/stack/`:

```
/opt/stack/<toolname>/
├── docker-compose.yml      Pflicht
├── sicherung.conf          Pflicht — was gesichert wird
├── aktualisierung.conf     Pflicht — wie aktualisiert wird
├── Dockerfile              nur bei eigenem Code
├── CHANGELOG.md            nur bei eigenem Code
├── .env                    nur wenn Geheimnisse noetig, NIE in Git
└── <quellcode>
```

Der Ordnername ist kleingeschrieben, ohne Leerzeichen und Umlaute, und
identisch mit der Subdomain: Ordner `bordbuch` → `bordbuch.prolo.me`.

## 2. Anmeldung: niemals selbst bauen

**Kein Tool bringt eine eigene Anmeldung mit.** Kein Login-Formular, keine
Registrierung, keine Passwortspeicherung, kein Zurücksetzen per E-Mail.

Die Identität kommt als HTTP-Kopf von Traefik:

| Kopf | Inhalt |
|---|---|
| `X-Authentik-Username` | Anmeldename, **der Schlüssel** für eigene Datensätze |
| `X-Authentik-Email` | E-Mail |
| `X-Authentik-Name` | Anzeigename |
| `X-Authentik-Groups` | Gruppen, kommagetrennt |

Pflichtverhalten:

- Fehlt `X-Authentik-Username`, wird die Anfrage **abgewiesen**. Kein
  Vorgabenutzer, kein Gastzugang, kein stilles Weiterlaufen.
- Unbekannter Anmeldename legt automatisch einen Nutzer-Datensatz an
  (Just-in-Time-Provisioning).
- Wiedererkennung läuft über den Anmeldenamen, **nicht** über die E-Mail.
  E-Mail-Adressen ändern sich.
- Gruppen dürfen für tool-interne Rollen ausgewertet werden.

## 3. Abmelden

Jedes Tool mit Oberfläche braucht:

- eine eigene **Einstellungsseite** unter `/einstellungen` (Aufbau siehe
  `prolo-regelblatt.md`, Abschnitt 6a)
- dort im Bereich „Konto" einen Knopf **„Abmelden / neu laden"**, der auf
  `/outpost.goauthentik.io/sign_out` zeigt
- im Header den Anzeigenamen des angemeldeten Nutzers, verlinkt auf die
  Einstellungsseite

Ein lokales Löschen von Cookies reicht nicht — die Sitzung liegt bei
Authentik. Ohne diesen Knopf kann niemand das Konto wechseln. Die
doppelte Beschriftung ist Absicht: Es ist eine Weiterleitung, die Seite
lädt dabei neu.

## 4. Datentrennung

Sobald ein Tool Daten pro Person hält:

- Jeder fachliche Datensatz bekommt ein Feld `nutzer_id`.
- Abfragen filtern standardmäßig auf den angemeldeten Nutzer.
- Freigaben an andere Nutzer laufen über eine eigene Tabelle im Tool,
  nicht über Authentik.
- Es gibt **keine** Oberfläche, in der ein Nutzer andere Nutzer anlegt,
  löscht oder deren Stammdaten bearbeitet. Das macht Authentik.

## 5. Container-Regeln

Verbindlich in jeder `docker-compose.yml`:

- **Keine `ports:`-Zeile.** Das ist der eigentliche Schutz: Der Dienst ist
  nur über Traefik erreichbar. Eine `ports:`-Zeile hebelt Firewall und
  Anmeldung gleichzeitig aus.
- Netzwerk `proxy` (extern), zusätzlich `internal` für Datenbanken.
- Datenbanken und Hilfsdienste hängen **nur** im Netz `internal`.
- `restart: unless-stopped`
- **Feste Versionsnummer beim Image, niemals `latest`.** Datenbank-
  migrationen bei Hauptversionen sind nicht umkehrbar.
- Persistente Daten liegen in benannten Volumes, nicht im Container.

Traefik-Labels nach diesem Muster (`<tool>` ersetzen):

```yaml
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=proxy"
      - "traefik.http.services.<tool>.loadbalancer.server.port=<port>"
      - "traefik.http.routers.<tool>.rule=Host(`<tool>.prolo.me`)"
      - "traefik.http.routers.<tool>.entrypoints=websecure"
      - "traefik.http.routers.<tool>.tls.certresolver=letsencrypt"
      - "traefik.http.routers.<tool>.middlewares=authentik@file"
      - "traefik.http.routers.<tool>.service=<tool>"
```

**Ausnahme Webhooks:** Pfade, die von außen ohne Anmeldung erreichbar sein
müssen, bekommen einen zweiten Router **ohne** die
`authentik@file`-Middleware und mit höherer `priority`. Diese Ausnahme ist
in der `sicherung.conf` unter `HINWEIS=` zu vermerken.

## 6. Sprache und Benennung

- Fachbegriffe auf Deutsch (`tankvorgang`, `ladevorgang`, `fahrzeug`),
  technische Begriffe in der Konvention der jeweiligen Sprache.
- Keine Umlaute in Bezeichnern: `blockiergebuehr`, nicht `blockiergebühr`.
- Jede Größe mit Einheit im Namen: `menge_l`, `energie_kwh`.
- Geldbeträge niemals als Fließkommazahl.
- Keine Steuersätze, Preise oder Wirkungsgrade fest im Code — die gehören
  in Konfiguration mit Gültigkeitsdatum.

## 7. Ein neues Tool einhängen — Ablauf

1. DNS-Eintrag bei IONOS: A-Record `<tool>` auf die Server-IP. **Keinen
   AAAA-Record**, oder auf die IPv6 des Servers zeigen lassen — sonst
   scheitert die Zertifikatsausstellung.
2. Ordner unter `/opt/stack/<tool>/` anlegen, Compose-Datei schreiben.
3. `sicherung.conf` und `aktualisierung.conf` anlegen.
4. `docker compose up -d`
5. In Authentik: **Anwendungen → Anwendungen → Erstellen**, Provider
   `forward-auth-domain` zuweisen.
6. **Anwendungen → Outposts → authentik Embedded Outpost → Bearbeiten** →
   neue Anwendung mit auswählen. *Dieser Schritt wird am häufigsten
   vergessen und äußert sich als „Not Found" von Authentik.*
7. Von außen aufrufen, Anmelde-Weiterleitung prüfen.
8. Sicherung und Aktualisierung je einmal testweise durchlaufen lassen.

---

# TEIL II — SCHÜTZENSWERTE DATEN

Der teuerste Fehler wäre, Zugangsdaten oder persönliche Daten versehentlich
nach außen zu geben. Einmal in einem Git-Verlauf gelandet, bleiben sie auch
nach dem Löschen in alten Commits auffindbar.

## 8. Was das System nie verlässt

Nie in Git, nie in ein Abbild, nie in ein Protokoll, nie in eine
Fehlermeldung, nie in einen Chat mit einem Agenten:

| Kategorie | Beispiele |
|---|---|
| Zugangsdaten | `.env`, `PG_PASS`, `AUTHENTIK_SECRET_KEY`, API-Schlüssel |
| Schlüssel und Zertifikate | `acme.json`, private SSH-Schlüssel, `*.key`, `*.pem` |
| Sitzungsdaten | Cookies, JWT aus `X-Authentik-Jwt`, Sitzungskennungen |
| Nutzerdaten | Datenbanken, E-Mail-Adressen, Anmeldenamen echter Personen |
| Hochgeladenes | Belege, Tankquittungen, Fotos, Importdateien |
| Sicherungen | alles unter `/opt/backups` |

## 9. Umgang mit Geheimnissen

- Alle Geheimnisse in `.env` im Tool-Ordner — nie im Compose-File, nie im
  Dockerfile, nie im Quellcode.
- Erzeugung: `openssl rand -base64 36`
- Jedes neu erzeugte Geheimnis wandert zusätzlich in den Passwortmanager.
  Ohne Schlüssel ist eine Datensicherung wertlos.
- **Niemals per `ENV` ins Dockerfile schreiben.** Das landet dauerhaft im
  Abbild und ist mit `docker history` auslesbar.
- Wenn ein Geheimnis doch einmal irgendwo aufgetaucht ist, gilt es als
  verbrannt: neu erzeugen, nicht verstecken.

## 10. Pflicht-Einträge in `.gitignore`

`/opt/stack/.gitignore` enthält mindestens:

```
**/.env
**/.env.*
**/acme.json
**/*.key
**/*.pem
**/*.db
**/*.sqlite
**/*.sql
**/*.dump
**/receipts/
**/belege/
**/daten/
**/backups/
authentik/data/
authentik/certs/
```

Dazu, aus B-49 nachgetragen:

```
**/.env.*
!**/.env.beispiel
**/*.db-wal
**/*.db-shm
**/*.db-journal
**/seiten/
**/.vorschau/
**/*.vor-stand-*
```

Die Zeile `!**/.env.beispiel` ist nötig, weil `**/.env.*` sonst die
Beispieldatei mitfängt — und die soll ausdrücklich im Repository stehen.
`**/*.vor-stand-*` fängt die Kopien, die eine Migration nach Abschnitt 19a
anlegt.

**Zusätzlich eine `.gitignore` je Tool.** Die Wurzeldatei allein trägt nicht:
sie ist leicht zu übersehen, und ein Tool, das eine neue Art von Daten ablegt,
bringt seine Regel am besten dort mit, wo die Daten entstehen. Vorbild ist
`bordbuch/.gitignore`; `wiki/.gitignore` ist danach gebaut und um `seiten/`
und `.vorschau/` ergänzt.

Wer ein Tool anlegt, das eine neue Art von Daten ablegt, ergänzt die Regel
**im selben Arbeitsschritt** — nicht später.

## 11. Vor jedem Push prüfen

```bash
cd /opt/stack
git status              # Liste tatsaechlich lesen
git diff --cached       # was wirklich hochgeht
```

Taucht dort etwas aus Abschnitt 8 auf: **nicht committen**, erst die
`.gitignore` korrigieren.

Dazu gibt es einen Vorab-Test. Er liegt **versioniert** unter
`werkzeuge/pre-commit` (aus B-49) — vorher stand er nur in `.git/hooks/` und
war damit bei jedem frischen Klon weg, ohne dass es jemandem auffiel.

```bash
cd /opt/stack
ln -sf ../../werkzeuge/pre-commit .git/hooks/pre-commit
ls -l .git/hooks/pre-commit          # haengt er?
```

**Das muss nach jedem frischen Klon neu gesetzt werden.** `.git/hooks` wird von
Git nicht mitversioniert; die Datei im Repository ist die Vorlage, der
Symlink ist die Einrichtung.

Zwei Dinge, über die man beim Schreiben eines solchen Hakens stolpert:

- **`grep -PE` gibt es nicht.** grep lässt sich nicht beide Sprachen
  gleichzeitig vorgeben und meldet „conflicting matchers specified" — der
  Haken tut dann gar nichts und lässt die Datei durch. Das Muster braucht
  `-P` allein, weil es mit `(?!beispiel)` eine PCRE-Eigenschaft benutzt.
- **`--diff-filter=ACM`**, damit eine *gelöschte* `.env` den Commit nicht
  blockiert.

Ist eine Datei wirklich beabsichtigt, ist das eine bewusste Entscheidung:
`git commit --no-verify`.

Das ist ein Netz, kein Ersatz fürs Hinschauen.

## 12. Protokolle, Fehlermeldungen, Dateiweitergabe

- Keine Geheimnisse oder vollständigen Kopfzeilen ins Log. Beim
  Protokollieren `X-Authentik-Jwt` und `Cookie` weglassen oder kürzen.
- Fehlermeldungen an den Nutzer enthalten keine internen Pfade oder
  Datenbankfehler im Original.
- Beim Hochladen von Code zur Analyse sauber packen:

```bash
tar czf /tmp/<tool>-code.tar.gz \
  --exclude='.env' --exclude='*.db' --exclude='receipts' \
  --exclude='backups' --exclude='__pycache__' \
  -C /opt/stack/<tool> .
tar tzf /tmp/<tool>-code.tar.gz    # vorher hineinsehen
```

---

# TEIL III — SICHERUNG

## 13. Grundsatz

Ein Backup auf demselben Server ist **kein Backup**. Es braucht immer eine
Kopie außer Haus.

Drei Arten von Inhalten, drei Wege:

| Was | Wohin |
|---|---|
| Konfiguration (Compose, Dockerfile, `*.conf`) | Git, privates Repository |
| Geheimnisse (`.env`, `acme.json`) | Passwortmanager **und** verschlüsselte Sicherung |
| Daten (Datenbanken, Volumes) | `backup.sh`, danach weg vom Server |

## 14. `sicherung.conf` — Pflicht je Tool

Das zentrale Skript liest diese Dateien automatisch ein. Dadurch ist beim
Anlegen eines neuen Tools **nichts** am Backup zu ändern.

```bash
# /opt/stack/<toolname>/sicherung.conf

# Benannte Docker-Volumes. Namen pruefen mit:
#   docker volume ls | grep <toolname>
VOLUMES="<projekt>_<volume> <projekt>_<volume2>"

# Datenbank-Container fuer einen sauberen Dump.
# Leer lassen bei SQLite oder ohne eigene Datenbank.
DB_CONTAINER=""
DB_USER=""
DB_NAME=""

# Dateien aus dem Tool-Ordner, die mitgesichert werden (meist .env).
# Ein "?" davor heisst "darf fehlen" - ohne "?" ist das Fehlen ein Fehler.
DATEIEN=".env"

# Ordner aus dem Tool-Ordner, die mitgesichert werden (neu aus B-08).
# Noetig fuer Bind-Mounts: DATEIEN kopiert nur Dateien, und Ordner wie
# authentik/data oder authentik/certs wurden darum von KEINER Sicherung
# erfasst. Auch hier gilt das "?" fuer freiwillige Eintraege.
ORDNER=""

# SQLite-Datenbanken IM CONTAINER, als "behaelter:/pfad/zur.db" (neu aus
# B-08). Sie werden mit sqlite3.backup() gesichert, nicht aus dem Volume
# kopiert - siehe unten, warum das wesentlich ist.
SQLITE=""

# Hinweis fuer spaeter, z. B. ungeschuetzte Webhook-Pfade.
HINWEIS=""
```

**Regel: Ein Volume, das nicht in einer `sicherung.conf` steht, existiert
für das Backup nicht.**

### Warum SQLite ein eigenes Feld braucht

Bordbuch und Wiki laufen im WAL-Modus (`PRAGMA journal_mode=WAL`). Ein `tar`
über das Volume greift `.db`, `.db-wal` und `.db-shm` zu **verschiedenen
Zeitpunkten** ab. Das Ergebnis kann eine unbrauchbare Datenbank sein — und man
merkt es erst beim Wiederherstellen, also im schlechtesten Moment.

`sqlite3.backup()` aus der Standardbibliothek liest einen in sich
geschlossenen Stand, auch während geschrieben wird. Der Container muss dafür
**nicht** angehalten werden. Nachgeprüft: während 600 Einfügungen pro Sekunde
lief die Sicherung durch und kam mit `integrity_check: ok` und einem
abgeschlossenen Stand heraus.

Das Volume-Archiv bleibt zusätzlich — es enthält die Belege. Die Datenbank
**darin** gilt aber nicht mehr als Sicherung.

Stand für die bestehenden Tools:

```
authentik:    VOLUMES="authentik_database"  DB_CONTAINER="authentik-db"
              DB_USER="authentik"  DB_NAME="authentik"  DATEIEN=".env"
              ORDNER="data certs ?custom-templates"
n8n:          VOLUMES="n8n_n8n_data"
bordbuch:     VOLUMES="bordbuch_bordbuch_daten bordbuch_bordbuch_belege"
              DATEIEN="?.env"  SQLITE="bordbuch:/daten/bordbuch.db"
wiki:         VOLUMES="wiki_wiki_daten wiki_wiki_seiten"
              DATEIEN=".env"   SQLITE="wiki:/daten/wiki.db"
socket-proxy: alles leer - der Dienst hat keine Daten. Die Datei ist
              trotzdem Pflicht (Abschnitt 1).
```

## 15. Zentrales Sicherungsskript

`/opt/stack/backup.sh`, ausführbar (`chmod +x`), erste Zeile `#!/bin/bash`.

**Die Datei im Repository ist maßgeblich, nicht der Abdruck hier.** Bis B-08
wichen beide voneinander ab: hier stand `rm -rf "$ZIEL"` vor `mkdir -p`, im
Skript fehlte es — ein zweiter Lauf am selben Tag mischte damit alt und neu,
und Archive eines entfernten Tools blieben liegen und sahen aus wie gültige
Sicherungen.

Was das Skript seit B-08 zusätzlich leistet:

- **Verschlüsselung** am Ende des Laufs mit `age`. Der **öffentliche**
  Schlüssel liegt unter `/opt/stack/.backup-schluessel.pub`, der **private**
  gehört ausschließlich in den Passwortmanager und auf den Arbeitsrechner —
  liegt er auf dem Server, ist die Verschlüsselung sinnlos.
  Erzeugen dort: `age-keygen -o ~/.age/prolo.key`. Fehlt der Schlüssel oder
  ist `age` nicht installiert, sagt das Skript das deutlich und endet mit
  einem Fehler, statt still Klartext liegen zu lassen.
- **Rechte auf alles**, nicht auf zwei Dateinamen: `chmod 700` auf die
  Verzeichnisse, `600` auf jede Datei. Die Volume-Archive sind genauso
  schützenswert wie die `.env` darin.
- **`SQLITE=`** für einen konsistenten Datenbankstand (siehe Abschnitt 14).
- **`ORDNER=`** für Bind-Mounts.
- **Fehlertoleranz je Schritt:** ein fehlendes `acme.json` bricht nicht mehr
  die gesamte Sicherung ab, bevor ein einziges Tool gesichert ist. Jeder
  Schritt merkt sich seinen Fehler; am Ende entscheidet `FEHLER` über den
  Rückgabewert.
- **`/opt/backups/.letzter-erfolg`** wird nur bei einem fehlerfreien Lauf
  gesetzt. **Dafür braucht es eine Überwachung, die anschlägt, wenn die Datei
  älter als zwei Tage ist** — eine Sicherung, deren Scheitern niemand merkt,
  ist keine Sicherung.

Zum Vergleich der ursprüngliche Aufbau:

```bash
#!/bin/bash
set -euo pipefail

DATUM=$(date +%Y-%m-%d)
ZIEL="/opt/backups/$DATUM"
BESITZER="prolo"

# Genau ein Stand pro Tag - ein erneuter Lauf ersetzt den alten.
rm -rf "$ZIEL"
mkdir -p "$ZIEL"

cp /opt/stack/traefik/acme.json "$ZIEL/acme.json"

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

# Aufbewahrung: drei Monate
find /opt/backups -maxdepth 1 -mindepth 1 -type d -mtime +90 -exec rm -rf {} +

chown -R "$BESITZER":"$BESITZER" /opt/backups
find /opt/backups -name ".env" -o -name "acme.json" | xargs -r chmod 600

echo "Backup fertig: $ZIEL"
```

Täglich per `sudo crontab -e`:

```
30 3 * * * /opt/stack/backup.sh >> /var/log/backup.log 2>&1
```

## 16. Kopie außer Haus

Auf dem Arbeitsrechner (WSL), `~/vps/backup-sync.sh`:

```bash
#!/bin/bash
BASIS="$HOME/vps"; ZIEL="$BASIS/backups"
MARKE="$BASIS/.letzter-sync"; PROTOKOLL="$BASIS/sync.log"
HEUTE=$(date +%Y-%m-%d)
mkdir -p "$ZIEL"
[ -f "$MARKE" ] && [ "$(cat "$MARKE")" = "$HEUTE" ] && exit 0

if rsync -avz --timeout=30 prolo@prolo.me:/opt/backups/ "$ZIEL/" >> "$PROTOKOLL" 2>&1; then
    echo "$HEUTE" > "$MARKE"; echo "[$(date '+%F %T')] OK" >> "$PROTOKOLL"
    echo "VPS-Backup synchronisiert."
else
    echo "[$(date '+%F %T')] FEHLER" >> "$PROTOKOLL"
    echo "ACHTUNG: VPS-Backup-Sync fehlgeschlagen. Details: $PROTOKOLL" >&2
fi
```

Aufruf über `~/.bashrc` und zusätzlich als tägliche Aufgabe in der
Windows-Aufgabenplanung (`wsl.exe -d Ubuntu -- /home/<name>/vps/backup-sync.sh`),
damit es auch läuft, wenn WSL tagelang nicht geöffnet wird.

**Der Ordner mit den Sicherungen darf nicht in einem Cloud-Sync liegen** —
dort stehen `.env` und `acme.json` unverschlüsselt drin.

## 17. Wiederherstellung testen

Der Schritt, den fast alle überspringen und der als einziger zählt. Einmal
komplett durchspielen, solange nur Testdaten drin sind:

```bash
cd /opt/stack/authentik
sudo docker compose down
sudo docker volume rm authentik_database
sudo docker compose up -d postgresql && sleep 20
gunzip -c /opt/backups/<datum>/authentik/datenbank.sql.gz \
  | sudo docker exec -i authentik-db psql -U authentik authentik
sudo docker compose up -d
```

Danach anmelden und prüfen, ob Nutzer und Anwendungen wieder da sind.

---

# TEIL IV — AKTUALISIERUNG

## 18. Grundsatz

**Vor jeder Aktualisierung wird gesichert.** Ohne Sicherung gibt es keinen
Rückweg: Die neue Fassung verändert die Datenbank oft so, dass die alte sie
nicht mehr lesen kann.

Ein Befehl für alle Tools:

```bash
sudo /opt/stack/aktualisieren.sh <toolname>
```

Ablauf: sichern → alte Fassung merken → holen bzw. bauen → neu starten →
30 Sekunden prüfen → bei Fehler automatisch zurückrollen.

## 19. `aktualisierung.conf` — Pflicht je Tool

```bash
# /opt/stack/<toolname>/aktualisierung.conf

# "image" = fertiges Abbild aus einer Registry
# "build" = eigenes Dockerfile im Ordner
TYP="image"

# Interne Adresse, unter der der Dienst antworten muss.
# Containername und interner Port - NICHT die oeffentliche Domain,
# sonst haengt die Pruefung an der Anmeldung fest.
PRUEF_URL="http://<container>:<port>/"

# Wartezeit nach dem Start in Sekunden. Bei traegen Diensten hochsetzen.
PRUEF_WARTEN=30
```

Stand für die bestehenden Tools:

```
authentik: TYP="image"  PRUEF_URL="http://authentik-server:9000/-/health/live/"  PRUEF_WARTEN=90
n8n:       TYP="image"  PRUEF_URL="http://n8n:5678/healthz"                      PRUEF_WARTEN=45
bordbuch:  TYP="build"  PRUEF_URL="http://bordbuch:8080/"                        PRUEF_WARTEN=20
```

Authentik braucht spürbar länger, weil beim Start Migrationen laufen.

### 19a. Datenbank-Migrationen: Hinweis, Kopie, Transaktion

Gilt für jede Migration in jedem Tool, das eine eigene Datenbank mitbringt.
Aus B-13: fünf `ALTER TABLE` liefen hintereinander, jedes sofort wirksam.
Bricht der Vorgang nach der dritten Tabelle ab — Stromausfall, voller
Datenträger, `SIGKILL` durch den Container-Neustart —, steht die Datenbank in
einem Mischzustand, und der Container startet in einer Schleife neu.

Darum sind diese drei Schritte Pflicht, in dieser Reihenfolge:

1. **Hinweis auf die Sicherung — bevor etwas passiert.** Das Tool schreibt
   beim Start, welche Änderungen anstehen, dass sie nicht umkehrbar sind und
   wie man abbricht. Ein Hinweis nach der ersten Änderung ist wertlos.
2. **Kopie der bisherigen Datei anlegen.** Nach dem Muster
   `<datenbank>.vor-stand-<n>`. Die Kopie bleibt liegen; sie kostet einmalig
   den Platz der Datenbank und ist das Einzige, was nach einer
   schiefgegangenen Migration noch hilft.
3. **Alle Änderungen in einer Transaktion.** Entweder ist die Datenbank
   vollständig im alten oder vollständig im neuen Stand — nichts dazwischen.
   SQLite kann `ALTER TABLE` innerhalb einer Transaktion.

Zwei Dinge, über die man dabei stolpert:

- **`executescript()` beendet eine offene Transaktion.** In Python schickt
  `sqlite3` davor ein implizites `COMMIT`. Wer `CREATE TABLE IF NOT EXISTS`
  per `executescript()` ausführt, kann das also nicht in dieselbe Transaktion
  packen. Unkritisch, solange dort nur idempotente Anweisungen stehen: ein
  abgebrochener Lauf wird beim nächsten Start vollendet. Alles, was Daten
  anfasst oder umbenennt, gehört in die Transaktion.
- **Reihenfolge.** Umbenennungen müssen vor dem Anlegen von Indizes laufen,
  die auf den neuen Spaltennamen stehen — sonst scheitert das Anlegen an der
  alten Spalte.

**Ein Aufruf, der nur nach der Fassung fragt, migriert nicht.** `--version`
wird von der Gesundheitsprüfung und von Skripten benutzt und bleibt ohne
Nebenwirkung. Für eine gezielte Migration — etwa zum Ausprobieren auf einer
Kopie — gibt es `--migrieren`:

```bash
cp bordbuch.db /tmp/probe.db
python3 server.py --db /tmp/probe.db --migrieren
ls -la /tmp/probe.db.vor-stand-*          # Kopie muss da sein
sqlite3 /tmp/probe.db "PRAGMA integrity_check;"        # ok
sqlite3 /tmp/probe.db "SELECT COUNT(*) FROM sessions;" # Anzahl unveraendert
```

## 20. Zentrales Aktualisierungsskript

`/opt/stack/aktualisieren.sh`, ausführbar:

```bash
#!/bin/bash
set -euo pipefail

TOOL="${1:-}"
ORDNER="/opt/stack/$TOOL"

if [ -z "$TOOL" ] || [ ! -d "$ORDNER" ]; then
  echo "Aufruf: $0 <toolname>"; echo "Verfuegbar:"
  for D in /opt/stack/*/docker-compose.yml; do
    [ -e "$D" ] && echo "  - $(basename "$(dirname "$D")")"
  done
  exit 1
fi

TYP="image"; PRUEF_URL=""; PRUEF_WARTEN=30
[ -f "$ORDNER/aktualisierung.conf" ] && . "$ORDNER/aktualisierung.conf"

echo "=== $TOOL aktualisieren ==="

echo "[1/5] Sicherung laeuft ..."
/opt/stack/backup.sh > /dev/null
echo "      erledigt."

ALT=$(grep -E '^\s*image:' "$ORDNER/docker-compose.yml" | head -1 | sed 's/.*image:\s*//' | tr -d '"')
# Ohne image:-Zeile gibt es keinen Rueckweg (B-23). Lieber gar nicht
# aktualisieren als ohne Rueckweg: bis dahin blieb ALT leer,
# .letzte-fassung enthielt nichts, und das Zurueckrollen unten haette
# stillschweigend ins Nichts gegriffen.
if [ -z "$ALT" ]; then
  echo "ABBRUCH: in $ORDNER/docker-compose.yml fehlt eine image:-Zeile."
  echo "         Ohne sie gibt es keinen Rueckweg (Betriebsregeln 5)."
  echo "         Auch bei einem eigenen Dockerfile gehoert sie dazu -"
  echo "         'build: .' UND 'image: <tool>:<fassung>'."
  exit 1
fi
echo "$ALT" > "$ORDNER/.letzte-fassung"
echo "[2/5] Bisherige Fassung: $ALT"

cd "$ORDNER"
echo "[3/5] Neue Fassung wird bereitgestellt ..."
if [ "$TYP" = "build" ]; then docker compose build --pull; else docker compose pull; fi

echo "[4/5] Container wird neu gestartet ..."
docker compose up -d

echo "[5/5] Pruefe ${PRUEF_WARTEN}s lang ..."
sleep "$PRUEF_WARTEN"

FEHLER=0
NEUSTARTS=$(docker inspect "$TOOL" --format '{{.RestartCount}}' 2>/dev/null || echo "0")
LAEUFT=$(docker inspect "$TOOL" --format '{{.State.Running}}' 2>/dev/null || echo "false")
[ "$LAEUFT" != "true" ] && { echo "  FEHLER: Container laeuft nicht."; FEHLER=1; }
[ "$NEUSTARTS" -gt 2 ]  && { echo "  FEHLER: Container startet staendig neu."; FEHLER=1; }

if [ -n "$PRUEF_URL" ] && [ "$FEHLER" -eq 0 ]; then
  if ! docker run --rm --network proxy curlimages/curl:latest \
       -sf -o /dev/null --max-time 10 "$PRUEF_URL"; then
    echo "  FEHLER: Dienst antwortet nicht unter $PRUEF_URL"; FEHLER=1
  fi
fi

if [ "$FEHLER" -eq 0 ]; then
  echo ""; echo "FERTIG. $TOOL laeuft."
  docker compose logs --tail 10
else
  echo ""; echo "!!! FEHLGESCHLAGEN - rolle zurueck auf $ALT"
  docker compose logs --tail 40
  if [ "$TYP" != "build" ]; then
    sed -i "s|image:.*|image: $ALT|" "$ORDNER/docker-compose.yml"
    docker compose up -d
    echo "Zurueckgerollt. ACHTUNG: Wenn die neue Fassung die Datenbank"
    echo "bereits migriert hat, zusaetzlich die Sicherung einspielen."
  else
    echo "Eigenes Abbild - Quellcode zuruecksetzen und neu bauen."
  fi
  exit 1
fi
```

## 21. Ablauf im Alltag

**Fertiges Abbild (n8n, Authentik, Traefik):**

```bash
nano /opt/stack/n8n/docker-compose.yml     # neue Versionsnummer eintragen
sudo /opt/stack/aktualisieren.sh n8n
```

Nie mehrere Hauptversionen auf einmal überspringen. Von 1.68 auf 1.72 ist
unkritisch; von 1.x auf 2.x erst die Umstellungshinweise lesen.

**Eigener Code (Bordbuch):**

```bash
cp -r /opt/stack/bordbuch /opt/stack/bordbuch.alt
cd /opt/stack/bordbuch
tar xzf /tmp/bordbuch-neu.tar.gz --strip-components=1 -C .
sudo /opt/stack/aktualisieren.sh bordbuch
```

Rückweg:

```bash
cd /opt/stack && sudo rm -rf bordbuch && sudo mv bordbuch.alt bordbuch
cd bordbuch && sudo docker compose up -d --build
```

Nach Erfolg aufräumen: `sudo rm -rf /opt/stack/bordbuch.alt`

## 22. Wenn Zurückrollen allein nicht reicht

Erkennbar an Meldungen über unbekannte Spalten oder eine zu neue
Schema-Fassung im Protokoll. Dann muss die Sicherung eingespielt werden —
siehe Abschnitt 17 für PostgreSQL.

Bei SQLite-Tools wie dem Bordbuch:

```bash
cd /opt/stack/bordbuch
sudo docker compose down
sudo docker run --rm -v bordbuch_bordbuch_daten:/daten \
  -v /opt/backups/<datum>/bordbuch:/backup alpine \
  sh -c "rm -rf /daten/* && tar xzf /backup/bordbuch_bordbuch_daten.tar.gz -C /daten"
sudo docker compose up -d
```

## 23. Monatliche Pflege

```bash
sudo apt update && sudo apt upgrade          # Betriebssystem
sudo docker image prune -a                   # Platz freigeben
grep -rn "image:" /opt/stack/*/docker-compose.yml   # was ist veraltet?
```

Die gefundenen Versionsnummern mit den Releases-Seiten abgleichen.
**Sicherheitsaktualisierungen bei Authentik und Traefik haben Vorrang** —
die stehen an der Tür. Bei n8n und eigenen Tools reicht ein gemütlicherer
Takt.

Nach jeder Aktualisierung:

```bash
cd /opt/stack && git add . && git commit -m "<tool> auf <version>" && git push
```

---

# TEIL V — ADMINISTRATION IN AUTHENTIK

Kurzreferenz für die wiederkehrenden Handgriffe. Alles über die
Weboberfläche, kein Code.

## 24. Gruppen und Nutzer

Drei Ebenen: **Benutzer** (eine Person) → **Gruppe** (Sammlung von
Benutzern) → **Bindung** (welche Gruppe darf auf welche Anwendung).

Ohne Bindung darf jeder eingeloggte Nutzer auf die Anwendung.

- **Gruppen:** Verzeichnis → Gruppen → Erstellen. Nach Tool und Rolle
  benennen (`bordbuch-nutzer`, `n8n-nutzer`), nicht nach Personen.
  „Ist Superuser" **nicht** anhaken — das gibt Authentik-Adminrechte.
- **Benutzer:** Verzeichnis → Benutzer → Erstellen. Der **Benutzername ist
  später schwer änderbar**, weil er als `X-Authentik-Username` zum
  Schlüssel für die Datensätze in den Tools wird. Kurz und stabil wählen.
- **Zugriff einschränken:** Anwendungen → [Anwendung] → Reiter
  Richtlinien/Gruppen/Benutzer-Bindungen → Erstellen → Gruppe binden.
  **Dich selbst nicht vergessen**, sonst sperrst du dich aus.
- **E-Mail oder Name ändern:** geht nicht über „Einstellungen", sondern
  über Verzeichnis → Benutzer → Bearbeiten.

Testen immer im privaten Browserfenster, damit die eigene Sitzung
erhalten bleibt. Und den Gegentest machen: Nutzer aus der Gruppe nehmen,
Seite neu laden — er darf nicht mehr durchkommen.

## 25. Absicherung des Admin-Kontos

- MFA einrichten: Benutzermenü → Einstellungen → MFA-Geräte → TOTP.
- Optional: eigenen Admin-Benutzer anlegen, Gruppe „authentik Admins"
  zuweisen, **im privaten Fenster testen**, erst dann `akadmin`
  deaktivieren (nicht löschen).

---

# TEIL VI — CHECKLISTE

Ein Tool gilt erst als fertig, wenn alle Punkte erfüllt sind. Die
Design- und Qualitätspunkte stehen in `prolo-regelblatt.md`.

**Aufbau**
- [ ] Ordner unter `/opt/stack/<toolname>/`, Name = Subdomain
- [ ] DNS-Eintrag gesetzt, kein verwaister AAAA-Record
- [ ] `docker-compose.yml` ohne `ports:`, im Netz `proxy`
- [ ] Feste Versionsnummer beim Image, kein `latest`
- [ ] Traefik-Labels inklusive `authentik@file`
- [ ] Anwendung in Authentik angelegt **und dem Outpost zugewiesen**
- [ ] Von außen aufgerufen, Anmelde-Weiterleitung geprüft

**Anmeldung**
- [ ] Kein eigener Login, Header werden ausgewertet
- [ ] Fehlender Username-Header führt zur Abweisung
- [ ] Einstellungsseite `/einstellungen` mit „Abmelden / neu laden"
- [ ] Anzeigename im Header, verlinkt auf die Einstellungen
- [ ] `nutzer_id` an allen personenbezogenen Datensätzen

**Daten und Geheimnisse**
- [ ] Geheimnisse in `.env`, nicht in Git, Kopie im Passwortmanager
- [ ] Keine Geheimnisse im Dockerfile (`ENV`) oder im Protokoll
- [ ] `.gitignore` um neue Datenarten des Tools ergänzt
- [ ] `git status` vor dem Push gelesen

**Betrieb**
- [ ] `sicherung.conf` angelegt, Volume-Namen geprüft
- [ ] `aktualisierung.conf` angelegt, `PRUEF_URL` intern und erreichbar
- [ ] Bei eigenem Code: `CHANGELOG.md` mit Datum je Änderung
- [ ] Einmal testweise aktualisiert **und einmal testweise zurückgerollt**

Der letzte Punkt ist der wichtigste. Ein Rückweg, den niemand ausprobiert
hat, ist kein Rückweg.
