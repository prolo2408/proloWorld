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

Daneben liegt, was **allen** Tools gemeinsam ist — kein Tool, also auch
keine `sicherung.conf` und keine `aktualisierung.conf`:

```
/opt/stack/
├── backup.sh               zentrale Sicherung (Abschnitt 15)
├── werkzeuge/              gemeinsame Skripte
│   ├── aktualisieren.sh        zentrale Aktualisierung (Abschnitt 20)
│   ├── aktualisieren-pruefen.sh  stellt deren Verhalten nach
│   ├── pre-commit              Vorab-Test (Abschnitt 11)
│   ├── dockerfile-pruefen.sh
│   └── schriften-pruefen.sh
├── prolo-regelblatt.md
└── prolo-betriebsregeln.md
```

**Neue gemeinsame Skripte gehören nach `werkzeuge/`**, nicht in die Wurzel.
`backup.sh` liegt aus Bestandsgründen dort und bleibt, wo es ist: der Pfad
steht in der Cron-Zeile jedes Servers, und ein Umzug bricht still die
nächtliche Sicherung.

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
- **Speicher-, Prozess- und Rechtegrenzen sind Pflicht** (aus B-29). Kein
  Container hatte sie, mit drei Folgen: ein Speicherleck in einem Tool brachte
  den **ganzen** Server in den OOM-Killer statt nur sich selbst; die Container
  liefen mit dem vollen Standardsatz an Linux-Fähigkeiten, obwohl keiner davon
  welche braucht; und ohne `no-new-privileges` ermöglicht eine Datei mit
  gesetztem setuid-Bit im Abbild eine Rechteausweitung.

  ```yaml
      mem_limit: 512m          # bordbuch, wiki: 512m · n8n: 2g · authentik: 1g
      pids_limit: 256
      security_opt:
        - no-new-privileges:true
      cap_drop:
        - ALL
  ```

  Zwei Dienste brauchen einzelne Fähigkeiten zurück, und zwar nur diese:
  **Traefik** `NET_BIND_SERVICE` (80 und 443 sind privilegierte Ports — ohne
  die Fähigkeit startet es nicht), **PostgreSQL** `CHOWN`, `SETUID`, `SETGID`,
  `FOWNER`, `DAC_OVERRIDE` (es legt beim Start seinen Datenordner an und
  wechselt dabei auf den unprivilegierten Nutzer).

  `read_only: true` zusätzlich, wo das Programmverzeichnis nicht beschrieben
  wird — beim **Bordbuch** möglich (es schreibt nur in Volumes), beim **Wiki
  nicht**: `pdftotext` legt Zwischendateien ab und der Vorschauordner
  `/seiten/.vorschau` wird zur Laufzeit gefüllt. Dazu dann `tmpfs` für `/tmp`
  und `PYTHONDONTWRITEBYTECODE=1` im Dockerfile, sonst versucht Python bei
  jedem Start erfolglos, `__pycache__` neben `server.py` zu schreiben.

- **Pfade ohne Anmeldung** kann ein Tool auch **selbst** bereitstellen, nicht
  nur als zweiter Router ohne Middleware (aus B-44). Das Wiki macht es so:
  `/gesundheit` und `/api/version` antworten ohne Anmeldekopf, alles andere
  nicht. Das ist fachlich richtig — `aktualisieren.sh` und die
  Gesundheitsprüfung erreichen den Dienst intern am Traefik vorbei und hätten
  über die Middleware gar keinen Weg. Beide Varianten sind erlaubt; welche ein
  Tool benutzt, gehört in den `HINWEIS` seiner `sicherung.conf`, damit man es
  bei einer Prüfung nicht suchen muss. Ein solcher Pfad darf **nichts
  Schützenswertes** ausgeben: „ok" und eine Fassungsnummer, mehr nicht.

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

### 6a. Verbindliche Benennungskonvention

Aus B-30. Bis dahin stand die Regel nur halb da, und das Ergebnis war ein
Schema, in dem in **einer Zeile** beides nebeneinander steht:

```sql
nutzer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
```

Deutsche Spalte, englische Tabelle. Über das Schema hinweg: `wartung`,
`werkstatt`, `freigaben` gegen `users`, `cars`, `sessions`, `fuelings`;
`art`, `notiz`, `betrieb` gegen `cost`, `odo`, `liters`, `note`. In manchen
Tabellen stehen `note` **und** `notiz` nebeneinander, je nachdem wann sie
entstanden sind.

Verbindlich ab jetzt:

1. **Tabellen und Spalten mit fachlicher Bedeutung: deutsch, ohne Umlaute.**
   `nutzer`, `fahrzeug`, `ladevorgang`, `tankvorgang`, `wartung`, `werkstatt`,
   `freigabe`.
2. **Jede Größe mit Einheit im Namen** — steht oben schon und wurde nur
   teilweise befolgt: `menge_l`, `energie_kwh`, `betrag_ct`, `stand_km`,
   `dauer_s`. `betrag_ct` ist mit B-04 der erste Fall, der es einhält.
3. **Schlüssel einheitlich `<tabelle>_id`:** `nutzer_id`, `fahrzeug_id`.
4. **`nutzer_id` bedeutet überall dasselbe.** Heute nicht: im Bordbuch ist es
   ein `INTEGER` auf `users(id)`, im Wiki ein `TEXT` mit dem
   Authentik-Anmeldenamen. **Festgelegt: überall der Anmeldename als `TEXT`.**
   Damit braucht das Bordbuch auf Dauer keine eigene Nutzertabelle, was §4
   entgegenkommt („Es gibt **keine** Oberfläche, in der ein Nutzer andere
   Nutzer anlegt"). Das Wiki hält es bereits so.
5. **Die JSON-Schnittstelle folgt dem Schema**, keine eigene Schreibweise.
   Die Tabelle `JSON_TO_COL` im Bordbuch ist heute eine Übersetzungsschicht,
   die es bei einheitlicher Benennung nicht bräuchte.

**Umsetzung: nicht in einem Zug.** Neue Felder folgen ab sofort der
Konvention; bestehende werden bei der nächsten ohnehin nötigen Migration
mitgezogen. Der Umbau von `users`/`nutzer_id` im Bordbuch ist ein eigener
Arbeitsschritt mit Datenmigration und gehört nach dem Dreischritt aus
Abschnitt 19a behandelt — er ist **nicht** Teil von B-30.

Was aus B-30 **sofort** erledigt wurde, weil es ein echter Fehler mit Wirkung
war: das Trennzeichen der Gruppen (Pipe, Komma, Semikolon).

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
/opt/stack/werkzeuge/aktualisieren.sh <toolname>
```

Ablauf: sichern → holen bzw. bauen → neu starten → prüfen, bis der Dienst
gesund ist → bei Fehler auf den letzten erfolgreichen Stand zurückrollen.

Geprüft wird bis zu `PRUEF_WARTEN` Sekunden lang, nicht *genau* so lange:
ist der Dienst früher da, geht es sofort weiter. Der Rückweg ist der Stand
des letzten **erfolgreichen** Laufs — warum das der entscheidende Punkt ist,
steht in Abschnitt 20.

## 19. `aktualisierung.conf` — Pflicht je Tool

```bash
# /opt/stack/<toolname>/aktualisierung.conf

# "image" = fertiges Abbild aus einer Registry
# "build" = eigenes Dockerfile im Ordner
TYP="image"

# Interne Adresse, unter der der Dienst antworten muss.
# Containername und interner Port - NICHT die oeffentliche Domain,
# sonst haengt die Pruefung an der Anmeldung fest.
# Darf leer bleiben: hat der Container eine eigene Gesundheitspruefung
# (HEALTHCHECK im Dockerfile oder healthcheck: in der compose-Datei),
# genuegt die. Sie ist naeher an der Wahrheit als ein Aufruf von aussen.
PRUEF_URL="http://<container>:<port>/"

# Obergrenze in Sekunden, KEINE feste Wartezeit. Das Skript fragt alle zwei
# Sekunden nach und ist fertig, sobald alle Container gesund sind.
# Hochsetzen bei Diensten, die beim Start Migrationen fahren.
PRUEF_WARTEN=30

# Nur bei Tools mit MEHREREN Containern noetig (bisher allein authentik):
# aus wessen Netz die URL-Pruefung laeuft. Ohne die Angabe nimmt das Skript
# den ersten Container - bei authentik waere das die Datenbank.
HAUPT="<containername>"
```

**Die Werte je Tool stehen in den Dateien, nicht hier.** Eine Tabelle an
dieser Stelle wäre eine zweite Wahrheit, die still veraltet — genau das war
sie bis jetzt: sie führte drei Tools auf, zu dem Zeitpunkt gab es sechs, und
die Wartezeiten stimmten mit keiner Datei mehr überein.

Was tatsächlich eingestellt ist, zeigt:

```bash
werkzeuge/aktualisieren.sh --liste     # welche Tools, welche ohne conf
grep -r "" */aktualisierung.conf       # alle Werte auf einmal
```

Authentik braucht spürbar länger als der Rest, weil beim Start Migrationen
laufen.

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

`werkzeuge/aktualisieren.sh`, ausführbar. Daneben liegt
`werkzeuge/aktualisieren-pruefen.sh`, das sein Verhalten nachstellt.

**Die Datei im Repository ist maßgeblich, nicht die Beschreibung hier** —
dieselbe Regel wie für `backup.sh` in Abschnitt 15, und aus demselben Grund.
An dieser Stelle stand bis jetzt ein vollständiger Skriptabdruck, der **nie
ausgeführt worden war**. Er enthielt drei Fehler, die alle erst beim
Nachstellen sichtbar wurden:

1. `docker inspect "$TOOL"` — es gibt keinen Container namens `authentik`,
   sondern `authentik-db`, `authentik-server` und `authentik-worker`. Für
   das einzige Tool mit mehreren Containern wäre die Prüfung **immer** mit
   „Container läuft nicht" gescheitert.
2. `sed -i "s|image:.*|image: $ALT|"` zum Zurückrollen — das trifft *jede*
   `image:`-Zeile. Nachgestellt: bei drei Diensten wurden alle drei auf das
   Abbild der Datenbank gesetzt. Bei Authentik hätte das Server und Worker
   in Postgres verwandelt.
3. **Der schwerwiegendste:** die Rückfallfassung wurde aus der
   `docker-compose.yml` gelesen, *bevor* aktualisiert wurde. Bei `TYP=image`
   trägt man die neue Version aber selbst dort ein und startet **danach** das
   Skript. Gelesen wurde also die schon eingetragene neue Nummer — das
   Zurückrollen schrieb die Fassung zurück, die eben gescheitert war.

Aufruf — **mit `sudo`**, sonst kommt es nicht an docker und `/opt/backups`:

```bash
sudo werkzeuge/aktualisieren.sh <tool> [<tool> ...]
sudo werkzeuge/aktualisieren.sh --alle
werkzeuge/aktualisieren.sh --liste            # nur auflisten, ohne sudo
werkzeuge/aktualisieren.sh --trocken <tool>   # Ablauf zeigen, ohne sudo
```

Ohne root bricht es **vor** dem ersten Tool ab und sagt das. Ohne diese
Prüfung lief es mitten hinein und meldete `permission denied while trying to
connect to the docker API` — eine Meldung, die nach einem Docker-Problem
aussieht und nicht nach einem fehlenden `sudo`.

### Was es leistet

- **Kein Toolname im Skript.** Ein Tool ist ein Ordner mit
  `docker-compose.yml`, alles Tool-eigene steht in seiner
  `aktualisierung.conf`. Ein neues Tool braucht keine Zeile im Skript.
- **Sicherung zuerst**, sichtbar und nicht nach `/dev/null` — und **einmal
  je Lauf, nicht je Tool**. `backup.sh` sichert immer den gesamten Stack;
  sie je Tool aufzurufen hieß bei `--alle` sechs vollständige Sicherungen
  hintereinander und im Fehlerfall sechsmal dieselbe Meldung.
  Schlägt sie fehl, wird nicht aktualisiert. Die Meldung nennt die beiden
  häufigen Gründe: fehlendes `sudo` (dann stehen Rechtefehler im Protokoll)
  oder ein fehlender `age`-Schlüssel — dann liegt die Sicherung zwar da,
  aber im Klartext. Für den geklärten zweiten Fall gibt es
  `--ohne-sicherung`, und der Lauf schreibt deutlich ins Protokoll, dass
  übersprungen wurde.
- **Abbruch ohne `image:`-Zeile** (B-23). Ohne sie gibt es keinen Rückweg.
- **Prüfung über die Gesundheitsprüfung des Containers**, `PRUEF_URL` nur
  ersatzweise. `PRUEF_WARTEN` ist eine Obergrenze: gefragt wird alle zwei
  Sekunden, im Erfolgsfall ist der Lauf sofort durch.
- **Rückweg vom letzten *erfolgreichen* Lauf.** Nach jedem Erfolg wird der
  Stand als `.stand-erfolgreich.yml` abgelegt; nur der gilt als Rückweg.
  Gibt es keinen — das Tool wurde so noch nie erfolgreich aktualisiert —,
  bleibt die `docker-compose.yml` **unangetastet**, und das Skript verweist
  auf `git`. Lieber gar kein Rückweg als ein falscher.
- **Reihenfolge wird erzwungen:** `socket-proxy` vor `traefik` vor
  `authentik`. Der Socket-Vermittler legt das Netz an, das Traefik braucht
  (B-02); alphabetisch sortiert liefe es falsch herum.
- **Ein Fehlschlag stoppt nicht den Rest.** Am Ende steht, was durch ist und
  was nicht; der Rückgabewert ist ungleich null, sobald eines gescheitert
  ist.

### Grenzen, die man kennen muss

Bei `TYP="build"` bringt das Zurückrollen der `docker-compose.yml` das alte
Verhalten **nicht** zurück: die Fassung steckt im Quellcode, nicht in der
`image:`-Zeile. Das Skript sagt das und nennt den Weg über `git checkout`.

Und: hat die neue Fassung die Datenbank bereits migriert, reicht Zurückrollen
grundsätzlich nicht — siehe Abschnitt 22.

**Die Prüfung sagt „der Container läuft", nicht „der Dienst tut, was er
soll".** Am 15.09.2026 auf dem Server erlebt (N-05): Traefik lief einwandfrei,
das Skript meldete zu Recht `FERTIG`, und trotzdem lieferte es für alle
Subdomains sein selbst ausgestelltes Notzertifikat aus — es kam wegen der
Dateirechte nicht an `acme.json`. Kein Absturz, keine rote Meldung, nur eine
Zeile im Protokoll. Aufgefallen ist es, weil jemand die Seite im Browser
aufgerufen hat.

Für Tools **ohne** `PRUEF_URL` — und Traefik ist genau so eines — ist die
Prüfung damit oberflächlich. Nach einer Aktualisierung an der Tür gehört
deshalb ein Blick in den Browser dazu, nicht nur ins Protokoll.

### Dateirechte bei Bind-Mounts

Aus derselben Sache, weil es jeden Dienst mit `cap_drop: ALL` trifft: ein
Container läuft zwar oft als root, aber `cap_drop: ALL` nimmt ihm
`CAP_DAC_OVERRIDE` — die Fähigkeit, mit der root sonst jede
Dateirechteprüfung umgeht. Danach gelten die normalen Rechtebits.

**Eingehängte Dateien müssen daher dem Nutzer gehören, unter dem der Dienst
im Container läuft** — bei einer Datei mit `600`, die `prolo` gehört, kommt
ein als root laufender Container mit `cap_drop: ALL` nicht mehr daran.

Beim Einhängen einer neuen Datei also immer prüfen:

```bash
ls -la <datei>                       # wem gehoert sie?
docker exec <container> id           # als wem laeuft der Dienst?
```

## 21. Ablauf im Alltag

**Fertiges Abbild (n8n, Authentik, Traefik, socket-proxy):**

```bash
nano /opt/stack/n8n/docker-compose.yml     # neue Versionsnummer eintragen
sudo /opt/stack/werkzeuge/aktualisieren.sh n8n
```

Nie mehrere Hauptversionen auf einmal überspringen. Von 1.68 auf 1.72 ist
unkritisch; von 1.x auf 2.x erst die Umstellungshinweise lesen.

**Eigener Code (Bordbuch, Wiki):**

Beide liegen im Git. Der Weg führt darüber — nicht über ein Archiv nach
`/tmp`. Der eigenständige Weg ohne Docker ist mit B-34 entfallen
(`install.sh`, `update.sh`, `bordbuch.service` sind gelöscht).

```bash
cd /opt/stack
git status                                 # erst sehen, ob lokal etwas abweicht
git pull origin main
sudo /opt/stack/werkzeuge/aktualisieren.sh bordbuch
```

Die Fassung in der `image:`-Zeile gehört bei eigenem Code **mit dem
Quellcode zusammen erhöht**, nicht danach: sie ist das Etikett des Abbilds,
das aus genau diesem Stand gebaut wird.

**Alles auf einmal**, in der richtigen Reihenfolge:

```bash
sudo /opt/stack/werkzeuge/aktualisieren.sh --alle
```

**Vorher sehen, was passieren würde:**

```bash
/opt/stack/werkzeuge/aktualisieren.sh --trocken --alle
```

### Rückweg

Bei fertigen Abbildern rollt das Skript selbst zurück, sofern es einen Stand
aus einem früheren erfolgreichen Lauf gibt. Bei eigenem Code führt der Weg
über git:

```bash
cd /opt/stack && git log --oneline -5 -- bordbuch
git checkout <alter-commit> -- bordbuch
cd bordbuch && sudo docker compose up -d --build
```

Hat die neue Fassung die Datenbank bereits migriert, reicht das nicht —
Abschnitt 22. Bordbuch legt vor jeder Migration eine Kopie neben die
Datenbank (`.vor-stand-<n>`, aus B-13); das ist der kurze Weg zurück, solange
sie noch da ist.

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
/opt/stack/werkzeuge/aktualisieren.sh --liste       # hat jedes Tool eine conf?
```

**Lebt die Sicherung noch?** Abschnitt 15 verlangt eine Überwachung, die
anschlägt, wenn `/opt/backups/.letzter-erfolg` älter als zwei Tage ist. Eine
solche Überwachung gibt es bisher **nicht** — bis sie existiert, ist das hier
der Ersatz, und der Handgriff gehört in dieselbe Runde wie alles andere:

```bash
M=/opt/backups/.letzter-erfolg
if [ ! -e "$M" ]; then
  echo "ACHTUNG: es gibt keinen Vermerk ueber eine erfolgreiche Sicherung."
elif [ -n "$(find "$M" -mtime +2)" ]; then
  echo "ACHTUNG: letzte erfolgreiche Sicherung ist aelter als zwei Tage:"
  cat "$M"
else
  echo -n "letzte erfolgreiche Sicherung: "; cat "$M"
fi
```

Geprüft mit einer frischen und einer fünf Tage alten Datei. Der naheliegende
Einzeiler `find … -mtime +2 && echo ACHTUNG` **funktioniert nicht**: `find`
gibt auch ohne Treffer 0 zurück, die Warnung käme also immer — und eine
Warnung, die immer kommt, liest nach einer Woche niemand mehr. Darum wird
die Ausgabe geprüft, nicht der Rückgabewert.

Gibt die Zeile eine Warnung aus — oder die Datei fehlt ganz —, ist zuerst
das zu klären und nichts zu aktualisieren. Eine Sicherung, deren Scheitern
niemand merkt, ist keine Sicherung; eine monatliche Handprüfung ist dafür
eigentlich zu selten, und sie ersetzt die Überwachung nicht.

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
- [ ] `mem_limit`, `pids_limit`, `no-new-privileges` und `cap_drop: ALL` gesetzt
      (B-29) — und nur die Fähigkeiten zurückgegeben, die der Dienst wirklich
      braucht
- [ ] `read_only: true` geprüft: möglich oder mit Begründung nicht
- [ ] Bei `cap_drop: ALL`: gehören alle eingehängten Dateien dem Nutzer, unter
      dem der Dienst im Container läuft? Ohne `CAP_DAC_OVERRIDE` hilft root
      nicht mehr über fremde Rechtebits hinweg (N-05)
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
- [ ] `aktualisierung.conf` angelegt — taucht das Tool bei
      `werkzeuge/aktualisieren.sh --liste` ohne den Zusatz „(ohne
      aktualisierung.conf)" auf?
- [ ] Eigene Gesundheitsprüfung im `Dockerfile` (`HEALTHCHECK`) oder in der
      compose-Datei. Sie ist die bessere Prüfung; `PRUEF_URL` ist der Ersatz,
      wenn es keine gibt
- [ ] `PRUEF_URL`, falls gesetzt: intern und ohne Anmeldung erreichbar —
      Containername und interner Port, **nicht** die öffentliche Domain
- [ ] Bei eigenem Code: `CHANGELOG.md` mit Datum je Änderung
- [ ] Einmal testweise aktualisiert **und einmal testweise zurückgerollt**

**Nach jedem frischen Klon**
- [ ] `ln -sf ../../werkzeuge/pre-commit .git/hooks/pre-commit` gesetzt —
      `.git/hooks` wird nicht mitversioniert, der Haken ist sonst weg

Der vorletzte Punkt ist der wichtigste. Ein Rückweg, den niemand ausprobiert
hat, ist kein Rückweg.

Und er entsteht nicht von selbst: `aktualisieren.sh` legt seinen Rückweg
erst **nach dem ersten erfolgreichen Lauf** an. Beim allerersten Mal gibt es
nichts, worauf zurückgerollt werden könnte — dann führt der Weg über `git`.
Genau deshalb steht „einmal testweise aktualisiert" **vor** „zurückgerollt".
