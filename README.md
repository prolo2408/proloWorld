# ProloWelt

Der Unterbau für deine selbst gehosteten Tools – einmal installieren, dann
über eine Verwaltungsseite oder den Befehl `prolo` bedienen.

Was der Unterbau mitbringt:

| | |
|---|---|
| **Traefik** | der Eingang: HTTPS mit Let's-Encrypt-Zertifikaten für jedes Tool, Ratenbremse, Sicherheitskopfzeilen |
| **Authentik** | eine Anmeldung für alle Tools – einmal anmelden, überall drin |
| **Admin-Seite** | `admin.<domain>`: was läuft, Tools installieren und verwalten, Sicherungen |
| **Sicherung** | jede Nacht alles nach `/opt/backup`, verschlüsselt und nach dem Packen wieder gelesen |
| **Updates** | jede Nacht: erst sichern, dann den Unterbau auf den Stand von Git bringen; das Betriebssystem spielt Sicherheitsaktualisierungen selbst ein |

Die Tools selbst stehen **nicht** in diesem Repository. Jedes liegt auf dem
Server in seinem eigenen Ordner unter `/opt/tools/`, läuft in seinem eigenen
Netz hinter der Anmeldung und kommt automatisch in die Sicherung.

---

## Installieren

Auf einem frischen Debian- oder Ubuntu-Server:

```bash
sudo git clone https://github.com/prolo2408/proloWorld /opt/prolo
sudo /opt/prolo/install.sh --domain prolo.me --email du@prolo.me
```

Ist das Repository privat, braucht der Server Lesezugriff darauf (ein
*Deploy Key* bei GitHub) – sonst kann `prolo update` später nichts holen.

`install.sh` installiert, was fehlt (Docker, git, age), schaltet die
nächtlichen Sicherheitsaktualisierungen des Systems und die Firewall ein
(nur SSH, 80, 443) und richtet danach alles Weitere ein. Es lässt sich
gefahrlos wiederholen – vorhandene Einstellungen, Geheimnisse und Schlüssel
bleiben stehen.

Danach, einmalig:

1. **DNS:** beim Anbieter einen Eintrag `*.prolo.me` (A-Record, Wildcard) auf
   die IP des Servers. Dann ist jedes neue Tool sofort erreichbar.
2. **Anmelden:** `https://auth.prolo.me`, Nutzer `akadmin`, das Passwort steht
   am Ende der Ausgabe von `install.sh`. Gleich in Authentik ändern und
   Zwei-Faktor einschalten (Einstellungen → MFA) – dieses Konto ist der
   Schlüssel zu allem.
3. **Sicherungsschlüssel:** `sudo prolo backup schluessel` zeigt ihn. In den
   Passwortmanager kopieren. Ohne ihn lässt sich keine Sicherung auf einem
   neuen Server öffnen.

Die Verwaltung liegt dann unter `https://admin.prolo.me`.

---

## Alltag

Alles geht auf der Admin-Seite **und** auf der Kommandozeile – die Seite
ruft im Hintergrund dieselben Befehle auf.

| Befehl | |
|---|---|
| `sudo prolo status` | was läuft, was zu tun ist |
| `sudo prolo tool list` | installierte Tools |
| `sudo prolo tool add <name> --image <abbild>` | ein Tool installieren (siehe unten) |
| `sudo prolo tool start\|stop\|restart <name>` | |
| `sudo prolo tool update <name>` | sichern, neue Abbilder holen, neu starten |
| `sudo prolo tool logs <name> [-f]` | Protokoll |
| `sudo prolo tool set <name> --anmeldung keine` | Port, Anmeldung oder Adresse ändern |
| `sudo prolo tool rm <name>` | entfernen – vorher wird gesichert |
| `sudo prolo backup` | jetzt sichern |
| `sudo prolo backup list` | vorhandene Sicherungen |
| `sudo prolo restore [<stand>] [--tool <name>]` | zurückholen |
| `sudo prolo update` | Unterbau auf den Stand von Git bringen |
| `sudo prolo einrichten` | alles prüfen und reparieren, was fehlt |

`prolo -h` und `prolo <befehl> -h` zeigen alles.

---

## Tools installieren

Drei Quellen:

```bash
# Ein einzelnes Abbild - Port und Volumes liest prolo aus dem Abbild
sudo prolo tool add uptime --image louislam/uptime-kuma:1

# Die Compose-Datei eines Herstellers - sie bleibt unverändert
sudo prolo tool add n8n --compose ./docker-compose.yml --anmeldung keine

# Ein Repository mit docker-compose.yml (auch eigener Code)
sudo prolo tool add wiki --git https://github.com/prolo2408/wiki.git
```

Das Tool ist danach unter `https://<name>.prolo.me` erreichbar. prolo
sorgt dabei für:

- **ein eigenes Netz** (`tool-<name>`), in dem nur noch Traefik hängt – Tools
  erreichen einander nicht direkt, nur über die Anmeldung,
- **keine offenen Ports** – was der Hersteller veröffentlicht, nimmt prolo
  weg; erreichbar ist das Tool nur über seine Adresse,
- **die Anmeldung davor** (Authentik). Mit `--anmeldung keine` ist das Tool
  öffentlich – nur für Tools mit eigener Anmeldung oder öffentliche Seiten,
- **gewürfelte Geheimnisse**: Variablen wie `DB_PASSWORD`, die die Datei
  verlangt, trägt prolo in die `.env` des Tools ein. Was es nicht kennt,
  fragt es ab (`--env NAME=wert`),
- **benannte Volumes** für alles, was das Abbild ablegt – damit die
  Sicherung es findet.

Compose-Dateien mit Gefahren (`privileged`, Docker-Socket, Pfade vom Server,
`network_mode: host`, zusätzliche Linux-Fähigkeiten …) legt die Admin-Seite
nicht an. Auf der Kommandozeile fragt prolo nach.

Ein Tool liegt so auf dem Server:

```
/opt/tools/uptime/
├── app/                   das Tool selbst: Compose-Datei (bzw. git clone) und .env
├── prolo.conf             was prolo über das Tool weiß (Quelle, Port, Anmeldung)
└── prolo.override.yml     was prolo dazutut (Netz, Router, keine Ports)
```

Von Hand mit docker compose: `sudo prolo tool compose uptime ps`.

---

## Sicherung

Jede Nacht um 03:30 (und vor jedem Update oder Entfernen):

1. jedes Tool kurz anhalten – eine laufende Datenbank lässt sich nicht
   verlässlich kopieren,
2. seinen Ordner und alle seine Volumes packen und mit `age` verschlüsseln,
3. wieder starten, was vorher lief,
4. **jedes Stück wieder entschlüsseln und vollständig lesen**. Erst dann gilt
   die Sicherung als gesichert.

Genauso mit dem Unterbau: Einstellungen, Geheimnisse, Zertifikate, die
Datenbank von Authentik. Ein Stand ist ein Ordner `/opt/backup/<datum>/`,
nur für root lesbar. Sicherungen bleiben 14 Tage liegen (`BACKUP_TAGE` in
`/etc/prolo/prolo.conf`), die drei neuesten immer.

Was ein Tool **außerhalb** seines Ordners einhängt (etwa `/srv/medien`),
wird nicht gesichert – `prolo status` und die Admin-Seite sagen das.

**Eine Sicherung auf demselben Server ist keine Sicherung.** Kopie außer Haus,
zum Beispiel von deinem Rechner aus (die Stände sind verschlüsselt):

```bash
rsync -a root@server:/opt/backup/ ~/prolo-sicherungen/
```

---

## Zurückholen

```bash
sudo prolo restore --tool uptime          # ein Tool, neuester Stand mit ihm
sudo prolo restore 2026-10-01_033000      # alles aus diesem Stand
sudo prolo restore --unterbau             # nur Authentik, Einstellungen, Zertifikate
sudo prolo backup pruefen                 # einen Stand vollständig lesen, nichts anfassen
```

Vor dem Zurückholen wird der jetzige Stand gesichert, und der gewählte Stand
wird erst vollständig geprüft, bevor etwas angefasst wird. Auch ein
entferntes Tool lässt sich so zurückholen, solange seine Sicherung liegt.

### Umzug auf einen neuen Server

```bash
# auf dem neuen Server
sudo git clone https://github.com/prolo2408/proloWorld /opt/prolo
sudo /opt/prolo/install.sh --domain prolo.me --email du@prolo.me \
     --schluessel ./prolo-backup.key            # der Schlüssel aus dem Passwortmanager
sudo rsync -a ~/prolo-sicherungen/ /opt/backup/  # die Sicherungen
sudo prolo restore                               # neuester vollständiger Stand
```

Danach den DNS-Eintrag auf die neue IP setzen.

---

## Updates

- **Der Unterbau** (`prolo update`, jede Nacht nach der Sicherung): holt den
  neuen Stand aus Git und startet mit ihm neu. Die Abbilder sind auf eine
  Nebenfassung festgelegt (`traefik:v3.6`, `authentik/server:2026.8`) –
  Fehlerbehebungen kommen damit von selbst, ein Sprung auf eine neue
  Fassung nur über einen Commit hier. Schalter: `AUTO_UPDATE=nein` in
  `/etc/prolo/prolo.conf`.
- **Die Tools** aktualisierst du selbst, wenn du willst:
  `prolo tool update <name>` oder der Knopf auf der Seite des Tools. Vorher
  wird gesichert.
- **Das Betriebssystem**: `unattended-upgrades` spielt Sicherheitsupdates
  jede Nacht ein.

Hast du im Unterbau von Hand etwas geändert, hält `prolo update` an, statt
es zu überschreiben.

---

## Wo was liegt

| Ort | Inhalt |
|---|---|
| `/opt/prolo` | der Unterbau (dieses Repository) – `prolo update` erneuert ihn |
| `/etc/prolo/prolo.conf` | Domain, E-Mail, Schalter |
| `/etc/prolo/geheim.env` | Geheimnisse des Unterbaus (gewürfelt, nur root) |
| `/etc/prolo/backup.key` | der geheime Sicherungsschlüssel – Kopie in den Passwortmanager |
| `/var/lib/prolo` | Zertifikate, Auftragsbuch der Admin-Seite, Stand |
| `/opt/tools/<name>` | je Tool ein Ordner |
| `/opt/backup` | die Sicherungen |

Zwei Dienste laufen auf dem Server neben Docker: `prolo-agent` (führt die
Aufträge der Admin-Seite aus) und `prolo-nacht.timer` (Sicherung und Update).

---

## Sicherheit – wie es zusammenhängt

- Von außen offen sind nur SSH, 80 und 443 (ufw). Nur Traefik hat Ports.
- Traefik löscht am Eingang jede vom Aufrufer mitgeschickte Anmelde-Kopfzeile
  (`X-authentik-*`); gesetzt werden sie nur von Authentik.
- Jedes Tool hängt in seinem eigenen Netz – ein übernommenes Tool erreicht die
  anderen nicht.
- Traefik sieht Docker nur lesend über einen Vermittler (`socket-proxy`).
- Die Admin-Seite hat **keinen** Zugriff auf Docker. Sie legt Aufträge ab, die
  der Agent auf dem Server prüft und über `prolo` ausführt – nur bekannte
  Aufträge, jedes Feld gegen ein Muster, nie über eine Shell.
- Hinein darf nur, wer in Authentik in der Gruppe `authentik Admins` ist
  (`ADMIN_GRUPPE` in `prolo.conf`).
- Jeder Container des Unterbaus: Speichergrenze, `no-new-privileges`, alle
  Linux-Fähigkeiten weg (bis auf die wenigen, die Traefik und Postgres
  brauchen).

---

## Fehlersuche

| | |
|---|---|
| Browser meldet „nicht sicher“ | DNS zeigt nicht auf diesen Server – Let's Encrypt kann dann kein Zertifikat ausstellen. `sudo prolo compose logs traefik` |
| Admin-Seite sagt „Der Stand ist … alt“ | der Agent läuft nicht: `sudo systemctl status prolo-agent` |
| Tool startet nicht | `sudo prolo tool logs <name>` |
| Anmeldung kommt nicht | `sudo prolo compose logs --tail 50 authentik-server` |
| irgendetwas fehlt | `sudo prolo einrichten` – sieht nach und ergänzt, gefahrlos |

---

## Die früheren eigenen Tools

Wiki, Bordbuch und `www` lagen bis Fassung 1 in diesem Repository und stehen
weiter in seiner Git-Geschichte (letzter Stand: Commit `4d16fd7`). In ein
eigenes Repository holen, mit Geschichte:

```bash
git clone https://github.com/prolo2408/proloWorld wiki && cd wiki
git checkout 4d16fd7 && git switch -c main-wiki
git filter-repo --subdirectory-filter wiki     # pip install git-filter-repo
```

Danach als Tool installieren: `sudo prolo tool add wiki --git <url>`. Sie
prüften die Kopfzeile `X-Prolo-Einlass`, die es im neuen Unterbau nicht mehr
gibt – die Abschottung leistet jetzt das eigene Netz je Tool. Diese Prüfung
muss in ihrem Code entfallen, sonst starten sie nicht.

---

## Entwicklung

```bash
tests/alle.sh                    # Einheitstests, Gegenprobe, shellcheck - ohne root
sudo python3 tests/durchlauf.py  # der echte Durchlauf mit Docker (einige Minuten)
```

Die Regeln für die Arbeit an diesem Repository stehen in `CLAUDE.md`.
