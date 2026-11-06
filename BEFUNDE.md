# Befunde

Was schiefging, warum, und was daraus folgt. Fast jede Regel in `CLAUDE.md`
hat hier eine Narbe.

Die Befunde `B-01` bis `B-49`, `N-01` bis `N-113`, `U-01` bis `U-04`,
`A-01` bis `A-03` und `F-01`/`F-02` gehören zur ersten Fassung des Stacks
(mit Wiki, Bordbuch und `www` im selben Repository). Sie stehen in
`NEUE-BEFUNDE.md` in der Git-Geschichte, letzter Stand Commit `4d16fd7`:

    git show 4d16fd7:NEUE-BEFUNDE.md

Neue Befunde bekommen die nächste freie Nummer: **N-149**.

---

## U-05 — ProloWelt wird nur noch der Unterbau

**Anlass:** Die eigenen Tools lagen im selben Repository wie der Unterbau,
und der Unterbau war über 100 Prüfskripte, Gegenproben und Querprüfungen
gewachsen, die einander zusammenhielten. Gewünscht war: ein Repository, das
sich mit `git clone` und einem Skript auf einem Server einrichten lässt;
Traefik und Authentik als Dienstleistung; Tools getrennt davon, über eine
Seite und eine Kommandozeile installier- und verwaltbar; Sicherungen, die
sicher funktionieren; so einfach wie möglich.

**Neu:**

- `install.sh` + `prolo einrichten`: vom frischen Server zum laufenden
  Unterbau, gefahrlos zu wiederholen.
- Ein Compose-Projekt für den Unterbau statt fünf Ordnern; Werte aus
  `/etc/prolo`, Netze der Tools in einer erzeugten Datei.
- Authentik richtet seine Anmeldung per Blueprint selbst ein: ein Provider
  im Domain-Modus für alle Subdomains. Vorher: drei Handgriffe je Tool in
  der Oberfläche von Authentik, von denen der dritte am häufigsten vergessen
  wurde.
- Tools unter `/opt/tools/<name>/`, aus einem Abbild, einer Compose-Datei
  oder einem Git-Repository; Netz, Router, Anmeldung, Ports und Volumes
  erzeugt prolo.
- Sicherung ohne `sicherung.conf`: prolo findet die Volumes eines Tools an
  seinen Containern, hält an, packt, verschlüsselt, startet wieder und liest
  jedes Stück. Wiederherstellung von Tool, entferntem Tool und Unterbau.
- Die Admin-Seite liest den Status, den der Agent schreibt, statt Docker
  selbst zu fragen – sie hängt in keinem Netz außer dem zu Traefik.
- `kern/auftrag.py` ist die eine Liste der Aufträge für Seite und Agent
  (vorher zwei Listen und ein Skript, das sie verglich).

**Entfallen**, mit Grund:

| was | warum |
|---|---|
| `wiki/`, `bordbuch/`, `www/`, `n8n/` | Tools gehören nicht in den Unterbau (Git-Geschichte, siehe README) |
| `crowdsec/`, `werkzeuge/firewall.py` | brauchte einen Bouncer aus fremder Paketquelle auf dem Host; ersetzt durch ufw (nur 22/80/443), Ratenbremse und Anmeldung vor allem |
| `X-Prolo-Einlass` | sicherte ab, dass ein anderer Container im gemeinsamen Netz nicht vorbeikommt – das eigene Netz je Tool leistet das jetzt ohne Geheimnis |
| `sicherung.conf`, `aktualisierung.conf`, `geheimnisse.conf` je Tool, `volumes.py` | prolo liest dasselbe aus den Containern; nichts mehr, das zur Konfiguration passen muss |
| 30 `*-pruefen.sh`/`*-gegenprobe.py` | prüften vor allem, dass Listen zueinander passen, die es nicht mehr gibt; ersetzt durch 46 Einheitstests, eine Gegenprobe mit 24 eingebauten Fehlern und einen echten Durchlauf mit 23 Prüfungen |
| `logrotate`-Regel | Docker dreht die Protokolle selbst (`max-size`) |
| Archiv entfernter Tools (`.archiv/`) | Entfernen sichert vorher; zurückholen geht aus der Sicherung |

---

## Beim Umbau gefunden und behoben

Alle im neuen Code, bevor er veröffentlicht war – festgehalten, weil jeder
davon auf einem Server zugeschlagen hätte.

### N-114 — Authentik startet auf einem Kern ohne IPv6 nie

Authentik lauscht von sich aus auf `[::]`. Auf einem Kern mit
`ipv6.disable=1`: „Address family not supported by protocol (os error 97)“,
Neustart in Schleife, Worker tot. Dieselbe Narbe wie N-92 beim
Docker-Vermittler – und der alte Server hatte genau so einen Kern.
**Jetzt:** `AUTHENTIK_LISTEN__HTTP/HTTPS/METRICS=0.0.0.0:…`. Gemessen:
gesund nach 40 s statt 8 Neustarts in 5 Minuten.

### N-115 — Der Blueprint scheitert beim allerersten Start still

Beim ersten Start lief der Blueprint, bevor Authentik seine
Standard-Abläufe angelegt hatte (`!Find` auf den Autorisierungsablauf fand
nichts). Status „error“, kein Provider, keine Anmeldung – und nichts sagte es.
Und selbst wenn er wirkt: der eingebaute Outpost lädt den Provider erst
Sekunden später und beantwortet bis dahin jede Anmeldeprüfung mit 404 – so
fiel ein Durchlauf, dessen Vorgänger grün war.
**Jetzt:** `einrichten` wendet ihn ausdrücklich an und prüft die **Wirkung**,
mit bis zu fünf Minuten Geduld: hängt der Provider im Domain-Modus am
Outpost, und leitet der Outpost eine Anfrage für `admin.<domain>` zur
Anmeldung weiter (302)? Gegenprobe: falsche Domain → erkannt. Danach zwei
volle Durchläufe von null an grün (23/23).

### N-116 — Der Hauptdienst verlor sein `default`-Netz

`docker compose config` schreibt das unsichtbare `default` ausdrücklich hin;
die Abfrage „hat der Dienst Netze?“ war darum immer wahr, und die
override-Datei setzte nur `prolo`. Bei App + Datenbank hätte die App ihre
Datenbank nicht mehr gefunden. **Jetzt:** alle bisherigen Netze werden
übernommen. Einheitstest und Durchlauf („App erreicht ihre Datenbank“);
Gegenprobe findet den Rückfall.

### N-117 — Jede Sicherung wartete 60 s auf die Admin-Seite

Als PID 1 im Container gibt es für SIGTERM keine Vorgabe; `docker stop`
wartete die vollen 60 s. Gemessen: 60,2 s, danach 0 s.

### N-118 — Ein kaputtes Tool ließ sich nicht zurückholen

Die Sicherung vor dem Zurückholen las die `prolo.conf` des Tools – war die
kaputt, scheiterte sie, und damit das Zurückholen genau in dem Fall, für den
es da ist. **Jetzt:** die Sicherung prüft nur, ob es das Tool gibt; scheitert
sie trotzdem, nennt die Meldung den Weg (`--ohne-sicherung`).

### N-119 — Abgewiesene Absendungen blieben in der Leitung

Wies die Admin-Seite einen POST ab, bevor sie seinen Inhalt gelesen hatte
(403 bei fremdem Ursprung), lag der Inhalt in der Keep-alive-Verbindung und
wurde als nächste Anfrage gelesen („Bad request syntax ('art=sichern')“).
**Jetzt:** nach jeder Fehlerantwort wird die Verbindung geschlossen.

### N-120 — `docker ps` scheiterte beim Anlegen eines Tools

`--format '{{json .}}'` greift auf `Size` zu; dafür berechnet Docker bei
jedem Aufruf die Größe jedes Containers – langsam, und bei einem Container,
der gerade entsteht, „snapshotter.Usage failed“. Ein Tool wurde dadurch
mitten im Anlegen wieder weggeräumt. **Jetzt:** nur die gebrauchten Felder.

### N-121 — „Zum Tool“ führte auf eine 404

Der Agent meldete den Auftrag als fertig, bevor er den neuen Status
geschrieben hatte. **Jetzt:** erst der Status, dann „fertig“. Im Browser
nachgeprüft.

### N-122 — Das Erst-Passwort stand in jedem Protokoll

Die Zusammenfassung von `einrichten` druckte es bei jedem Lauf – auch nach
jedem nächtlichen Update, ins Journal und in die Aufträge der Admin-Seite.
**Jetzt:** nur beim allerersten Lauf.

### N-123 — Docker Hub nicht erreichbar hieß „Update fehlgeschlagen“

Ein gedrosseltes Docker Hub (429) ließ das nächtliche Update scheitern,
obwohl alles weiterlief – jede Nacht dieselbe Warnung wäre Tapete. **Jetzt:**
Warnung im Status, kein Fehlschlag; `tool add` macht mit einem schon
vorhandenen Abbild weiter.

### N-124 — `prolo status` ohne sudo endete in einem Traceback

**Jetzt:** „Keine Berechtigung für /etc/prolo/prolo.conf – mit sudo
aufrufen: sudo prolo status“.

### N-125 — Die Adressen der Tools waren 16 px hohe Ziele

§9 verlangt 44 × 44. Gefunden von der Messung im Browser (18 Stellen),
jetzt 0.

### N-126 — Die angezeigte Befehlszeile kürzte das Abbild

`prolotest/web:1` stand als `web:1` im Auftrag – gekürzt werden sollten nur
die Pfade der Hilfsdateien des Agenten.

### N-127 — Die Prüfung schrieb ins Repository

`py_compile` legt `__pycache__` an; als normaler Nutzer: „Permission denied“,
als root unbemerkt Müll im Arbeitsstand. **Jetzt:** Syntaxprüfung mit `ast`.
Gefunden, weil `alle.sh` nicht als root lief.

---

## N-128 — Die Installation ließ sich auf einem frischen Server nicht abarbeiten

Der erste Befehl war `sudo git clone` – auf einem frischen Debian fehlen git
und oft sudo. DNS stand erst nach der Installation, obwohl Traefik die
Zertifikate beim ersten Start holt. Für ein privates Repository stand nur
„Deploy Key“ da, nicht wie. **Jetzt:** sieben Schritte in `README.md`, in
der Reihenfolge, in der sie funktionieren, mit einer Tabelle „Wenn es hakt“.

---

## N-129 — Wie man ein Tool anlegt, stand nur als drei Befehlszeilen da

Beim ersten echten Tool (Vaultwarden) war offen, wie die Compose-Datei
aussehen soll, welche Anmeldung richtig ist und was danach zu tun bleibt.
**Jetzt:** in `README.md` der Weg über die Admin-Seite mit Bildern, Regeln
für eine Compose-Datei, ein Text, mit dem man sich eine schreiben lässt, und
`beispiele/vaultwarden.yml` – echt installiert: Seite 200, App-Schnittstelle
meldet `https://vault.<domain>`, kein offener Port, Registrierung nach
`SIGNUPS_ALLOWED=false` + `prolo tool start` abgewiesen, Volume in der
Sicherung gelesen.

---

## N-130 — Ohne Port in der Datei scheiterte jede Compose-Datei auf einem frischen Server

Beim ersten Tool auf dem neuen Server (Vaultwarden aus
`beispiele/vaultwarden.yml`): „Auf welchem Port antwortet vaultwarden? Die
Datei sagt es nicht.“ Steht kein Port in der Datei, liest prolo ihn aus dem
Abbild (`EXPOSE`) – aber `tool add` fragte das Abbild, **bevor** es die
Abbilder holte. Auf dem Testrechner lag das Abbild schon, darum fiel es dort
nicht auf. **Jetzt:** erst holen und bauen, dann den Port bestimmen.
Nachgestellt mit `traefik/whoami:v1.10` (nicht vorhanden, kein Port in der
Datei): vorher rc=1 mit genau dieser Meldung, danach Port 80 und die Seite
antwortet. Der Durchlauf prüft es jetzt bei jedem Push.

---

## N-131 — Nach dem Anlegen ließ sich an einem Tool nichts mehr ändern

Gewünscht beim ersten echten Tool: Vaultwarden brauchte nachträglich ein
`ADMIN_TOKEN` und `SIGNUPS_ALLOWED=false`. Die Admin-Seite konnte nur Port
und Anmeldung ändern; Compose-Datei und `.env` nur von Hand auf dem Server,
ohne Sicherung, ohne Prüfung auf Gefahren und ohne Weg zurück.
**Jetzt:** *Bearbeiten* auf der Seite eines Tools und `prolo tool edit`:

- erst **prüfen** (in einer Probe neben `app/`, Pfade gelten trotzdem relativ
  zu `app/`): versteht Compose die Datei, gibt es den Dienst mit der
  Oberfläche noch, keine Gefahr von der Seite. Eine kaputte oder gefährliche
  Datei wird abgewiesen, **bevor** die Sicherung das Tool anhält – gemessen
  2 s statt Sicherung plus Absage;
- dann sichern, dann ändern; kommt das Tool nicht hoch, gilt wieder der
  Stand davor – Datei, `.env`, `prolo.conf`, Override und Container;
- die Seite bekommt die Datei und die **Namen** der Variablen, nie ihre
  Werte; Variablen werden gesetzt oder ersetzt, `$` bleibt in einfachen
  Anführungszeichen wörtlich (Hash von `vaultwarden hash`);
- die Datei eines Git-Tools gehört dem Repository – die Seite bietet sie
  nicht an, `prolo tool edit --compose` lehnt ab (sonst scheiterte das
  nächste `git pull`).

Beim Messen im Browser fiel der erste Titel des Auftrags auf („Compose-Datei
und Variablen ändern“ bricht am Handy in Silben) – jetzt „Bearbeiten“.

---

## N-132 — Der Durchlauf löschte die Volumes eines angehaltenen Unterbaus

`tests/durchlauf.py` weigerte sich nur, wenn Container des Projekts `prolo`
da waren. Bei einem **angehaltenen** Unterbau (Container weg, Volumes da)
lief er los: Authentik fand eine Datenbank mit fremdem Passwort und kam nicht
hoch (gemessen: abgebrochen nach 46 s) – und das Aufräumen (`down -v`)
löschte danach die Volumes. Auf einem Server wäre das die Anmeldung samt
allen Nutzern gewesen. **Jetzt:** er weigert sich bei Containern **oder**
Volumes eines seiner Projekte. Probe: ein Volume mit dem Etikett
`prolo` → rc=2, „nichts angefasst“, Volume noch da; auf einer sauberen
Maschine meldet die Prüfung nichts.

---

## N-133 — Am Handy zerbrachen die Titel der Aufträge in Silben

„Tool installier-en“, „Compo-se-Datei“: in den Listen der Aufträge nahmen
Zeit und Zustand als starre Spalten so viel Breite, dass für den Titel bei
360 px kaum etwas blieb – und `overflow-wrap:anywhere` brach dann mitten im
Wort. Die Messung auf Klickflächen und Kontrast sah das nicht; gefunden beim
Ansehen der Bilder (N-131). **Jetzt:** am Handy steht die Zeit klein unter
dem Titel statt in einer eigenen Spalte. Gemessen mit einer neuen Probe, die
je Wort zählt, ob es über zwei Zeilen läuft (5 Seiten, 3 Breiten, 339
Wörter): vorher 34 gebrochen, jetzt 0.

---

## N-134 — Private Git-Repositories ließen sich nicht installieren

`git clone` lief mit `GIT_TERMINAL_PROMPT=0` und ohne Zugangsdaten. Ein
privates Repository scheiterte darum mit „could not read Username …
terminal prompts disabled“ – eine Meldung, die nicht sagt, was zu tun ist.
Ein Tool, dessen Repository *nachträglich* privat wurde, ließ sich ab da
nicht mehr aktualisieren (gefunden am Spiel `golf`). Der Ausweg von Hand
(Token in die URL) hätte den Token ins Protokoll des Auftrags und nach
`prolo.conf` geschrieben.

**Jetzt:** Git-Zugänge, einer je Anbieter, in `/etc/prolo/git-zugang.json`
(root, 0600, in der Sicherung). Einpflegen auf der Admin-Seite unter
Einstellungen oder mit `prolo git-zugang setzen`; Klonen und Aktualisieren
holen ihn über einen eigenen Helfer.

- **Kein `credential.helper store`:** der löscht bei einer Absage (401) den
  Eintrag – ein abgelaufener Token wäre still verschwunden. Probe mit echtem
  git: `git credential reject` nach `fill` – der Zugang bleibt (Test).
- Der Token geht als Datei an prolo (`--token-datei`, im Auftragsordner
  0600, danach gelöscht), nie als Argument; die Lage des Auftrags und
  `status.json` tragen ihn nicht. Geprüft im Test über Lage, Protokoll und
  Übersicht; die Seite gibt ihn auch nach einem Fehler im Formular nicht
  zurück.
- Vor dem Speichern fragt prolo GitHub (`/rate_limit`): 401 heißt
  abgelehnt, **nichts gespeichert** (der alte Zugang bleibt); die
  Kopfzeile `github-authentication-token-expiration` liefert das
  Ablaufdatum. 14 Tage vorher ein Hinweis unter „Was zu tun ist“, danach ein
  Fehler – mit dem Befehl, der es behebt.
- Scheitert `git clone` oder `git pull`, sagt die Meldung jetzt, woran:
  privat ohne Zugang, Token abgelehnt, oder das Repository ist beim Token
  nicht ausgewählt.
- *Zugang testen* liest die Zweige eines Repositorys, so wie Installieren
  und Aktualisieren holen, und frischt dabei das Ablaufdatum auf.

Gemessen: Einheitstests 51 → 65, Gegenprobe 31 → 39 eingebaute Fehler,
alle gefunden. Im Browser (Einstellungen, 360/768/1920, hell/dunkel): kein
seitliches Scrollen, alle Klickflächen ≥ 44 px, am Handy nichts unter 12 px.
Die erste Fassung der Liste war eine Tabelle – bei 360 px lagen Ablauf und
*Entfernen* außerhalb der Karte (die Messung auf seitliches Scrollen der
Seite sah das nicht; eine neue Messung auf Scrollen **in** Elementen fand es:
2 von 6 Ansichten). Jetzt eine Liste, die umbricht: 0 von 6.

Nicht gelaufen: `tests/durchlauf.py` (hier kein Docker-Dienst) – der
Durchlauf installiert ohnehin kein Git-Tool; er läuft beim Push in der CI.

---

## N-135 — Die Prüfung der Compose-Dateien war eine Sperrliste

`gefahren()` suchte nach `privileged`, `cap_add`, `devices`, dem
Docker-Socket, Bind-Mounts von außen und `external`-Volumes. Alles andere
ging durch – auch über die Admin-Seite, die verspricht, mit Gefahren nichts
anzulegen. Gefunden bei einem Angriff von allen Seiten, jedes Stück mit
`docker compose config` und der echten Prüfung nachgestellt:

| Weg | Wirkung |
|---|---|
| Volume mit `driver_opts: {type: none, o: bind, device: /}` | ganzes Dateisystem des Servers schreibbar – root |
| Volume mit `name: prolo_authentik-db` | Datenbank von Authentik gelesen und schreibbar (gemessen: Inhalt gelesen) |
| Netz mit `name: prolo-authentik` | im internen Netz von Authentik (gemessen) |
| `secrets`/`configs` mit `file: /etc/prolo/…` | Sicherungsschlüssel, Geheimnisse des Unterbaus |
| `volumes_from: [container:…]`, `pid`/`ipc: container:…` | Volumes, Prozesse (samt Umgebung) eines fremden Containers |
| `post_start` mit `privileged: true`, `provider:`, `use_api_socket`, `gpus` | neu in Compose, der Liste unbekannt |
| `security_opt: seccomp=unconfined`, `oom_score_adj: -900`, `logging: syslog` | Schutz aus, Server verdrängt, Protokoll nach außen |
| `build` mit `context: /etc`, `ssh`, `network: host`, `additional_contexts`, `cache_from: type=local` | Dateien und Schlüssel des Servers ins Abbild |

**Jetzt:** `kern/kaefig.py`, eine **Erlaubnisliste**. Jeder Schlüssel, den
prolo nicht ausdrücklich kennt, ist eine Gefahr – lernt Compose etwas Neues,
ist es gesperrt, bis jemand es geprüft hat. Volumes und Netze heißen
`<tool>_…` oder gar nicht; `name:`, `driver_opts`, `ipam` und fremde Treiber
sind Gefahren. Namen mit `prolo…` (Dienst, Container, Alias) vergibt nur
der Unterbau.

Geprüft: alle 18 Wege oben als Einheitstest, je einer; die Herstellerdateien
von Nextcloud, Paperless-ngx, n8n, Gitea, Immich und `beispiele/vaultwarden.yml`
mit `docker compose config` – keine neue Gefahr (Gitea und Immich hängen
`/etc/localtime` ein, das war schon vorher eine). Einheitstests 65 → 67,
Gegenprobe 39 → 47 eingebaute Fehler, alle gefunden (einer zuerst nicht: der
eingebaute Fehler war zu schwach, die Prüfung fing ihn trotzdem – ersetzt).

---

## N-136 — Was im Ordner eines Tools liegt, behandelte prolo als eigen

`app/` ist die Datei des Herstellers oder ein `git clone` – also fremd. prolo
las und schrieb dort als root, als wäre es sein Ordner:

- **Schreiben durch einen Verweis:** `datei_schreiben` legte `<datei>.neu` mit
  `O_TRUNC` an und folgte dabei einem Verweis. Ein Repository mit
  `.env.neu -> /root/.ssh/authorized_keys` und einer `.env`, die mit einem
  SSH-Schlüssel beginnt: `env_fuellen` schreibt die alte `.env` samt
  gewürfeltem Passwort **dorthin** – sshd überliest die Zeile mit dem
  Passwort, der Schlüssel gilt. Root über ein Git-Repository. Gemessen:
  die Zieldatei enthielt danach den Inhalt der `.env`.
- **Lesen durch einen Verweis:** `.env -> /etc/prolo/geheim.env` – Compose
  setzt `${AUTHENTIK_SECRET_KEY}` aus den Geheimnissen des Unterbaus ein
  (gemessen mit `docker compose config`).
- **Was ein Container einhängt, kann er ändern:** eine Einhängung von
  `./.git` (Hooks, die root beim nächsten `git pull` ausführt), ein
  `env_file` in einem eingehängten Ordner, eine Einhängung in einer
  Einhängung (der Container ersetzt den inneren Ordner durch einen Verweis
  auf `/`, der nächste Start hängt den Server ein) – alles ging durch.

**Jetzt:**

- `datei_schreiben` löscht, was neben der Datei liegt, und legt sie mit
  `O_EXCL | O_NOFOLLOW` neu an.
- `kaefig.verweise(app)` findet jeden Verweis nach draußen – **gleich nach
  dem Klonen**, bevor irgendetwas die Dateien liest. Ordner, die Container
  einhängen, sind ausgenommen: dort liest prolo nichts.
- `Pruefung.ordner`: keine Einhängung von `.git`, keiner Datei, die prolo
  oder Compose als root lesen (`.env`, Compose-Datei, `env_file`,
  `secrets`/`configs`, Dockerfile), keine Einhängung in einer anderen, kein
  Weg über einen Verweis.

Geprüft: der Angriff von oben echt mit `prolo tool add --git` (Repository mit
`.env.neu`-Verweis), über die Admin-Seite (`--von-web`) und auf der
Kommandozeile: beide Male abgelehnt, bevor etwas geschrieben wurde, die
Zieldatei unberührt, kein Ordner liegen geblieben. Einheitstests 67 → 69,
Gegenprobe 47 → 53 eingebaute Fehler, alle gefunden (einer zuerst nicht:
das Löschen allein schützt schon, der eingebaute Fehler nimmt jetzt beide
Schichten weg).

---

## N-137 — `include:` holte die Geheimnisse eines anderen Tools

`include: [ /opt/tools/vault/app/docker-compose.yml ]` nimmt die Dienste
der anderen Datei auf – und setzt ihre Variablen aus der `.env` **ihres**
Ordners ein. Gemessen: das Modell des neuen Tools enthielt den Wert aus der
`.env` des anderen. `extends: {file: …}` holt ebenso einen fremden Dienst
samt `env_file`. Im Ergebnis von `docker compose config` ist von beidem
nichts mehr zu sehen; keine Liste kann es finden. Dazu: `env_file` wird in
`config` aufgelöst – ein Pfad vom Server tauchte nie auf; und `${HOME}`,
`${SUDO_USER}`, `${SSH_AUTH_SOCK}` kamen aus der Umgebung von root.

**Jetzt:** `kaefig.modell()` – die Prüfung läuft als Nutzer `prolo-pruefer`
(ohne Login, ohne Rechte; `prolo einrichten` legt ihn an) auf einer Kopie des
Tools (ohne `.git`, ohne eingehängte Ordner, ohne Dateien über 1 MB). Compose
kann dort nur lesen, was im Tool liegt oder ohnehin jeder lesen darf; jedes
andere `include`, `extends` oder ein Verweis scheitert mit „permission
denied“, und die Meldung sagt, warum. `--no-env-resolution` lässt die Pfade
von `env_file` stehen. Jeder `docker compose` eines Tools läuft mit einer
festen Umgebung (`docker.tool_env()`) – Prüfung und Start sehen dieselben
Werte. Die Probe-Dateien neben `app/` beim Bearbeiten sind entfallen.

Geprüft echt mit `prolo tool add`/`tool edit --von-web` als root:
`include` und `extends` auf ein anderes Tool, `env_file: /etc/shadow` –
alle abgelehnt; ein harmloses Tool angelegt und bearbeitet – läuft. Neu im
Durchlauf: Volume mit dem Namen der Authentik-Datenbank, `include` eines
anderen Tools. Einheitstests 69 → 73, Gegenprobe 53 → 56.

---

## N-138 — Geprüft wurde nur beim Anlegen und Bearbeiten

*Aktualisieren* eines Git-Tools holte mit `git pull` eine neue
Compose-Datei und startete sie ungeprüft: ein Repository, beim Anlegen
harmlos, bekam einen Commit mit `privileged: true` – ein Klick auf
*Aktualisieren*, und der Container lief mit allen Rechten. Ebenso Starten,
Neustarten, *Einstellungen ändern* und Zurückholen aus einer Sicherung: was
seit dem Anlegen an den Dateien geändert wurde (von Hand, durch eine
Wiederherstellung), startete, wie es lag.

**Jetzt:** `tools.kaefig_pruefen()` vor jedem Start – das Modell der
Dateien, wie sie jetzt liegen, durch den Käfig (N-135 bis N-137).

- *Aktualisieren* prüft nach `git pull`; ist die neue Fassung gefährlich,
  setzt es das Repository auf den Stand davor zurück (`git reset --hard`) –
  nichts Halbes, der laufende Container bleibt, wie er war.
- Was ein Mensch auf der Kommandozeile bestätigt hat (`--ja` oder die
  Rückfrage), steht in `prolo.bestaetigt` im Ordner des Tools; das fragt
  nicht noch einmal, auch nicht von der Seite. Jede **neue** Gefahr lehnt
  die Seite ab, die Kommandozeile fragt.
- „Von der Seite“ heißt jetzt: jeder Auftrag des Agenten (`PROLO_AGENT=1`),
  nicht nur `--von-web` bei Anlegen und Bearbeiten.
- Die Ordner, die ein Tool einhängt, kennt die Prüfung auch bei einem
  angehaltenen Tool (aus der Datei): sie werden nicht mitkopiert – sonst
  kopierte sie die Fotos eines Fotoarchivs.

Geprüft echt als root: Git-Tool angelegt, gefährlicher Commit,
`tool update` über den Agenten → abgelehnt, Repository zurück auf dem alten
Commit, Container ohne Rechte; Datei von Hand mit `driver_opts` versehen →
`start`/`restart` von der Seite und `start` ohne Terminal abgelehnt.
(Unterwegs: `w:/w` liest Compose als Windows-Laufwerk – kein Volume `w`;
die Prüfung hatte recht, mein Test nicht.) Neu im Durchlauf: Neustart einer
von Hand gefährlich gemachten Datei. Einheitstests 73 → 76, Gegenprobe
56 → 60.

---

## N-139 — Ein Docker-Abbild konnte `admin.` und `auth.` übernehmen

Traefik las seine Router aus den Labels **aller** Container (Docker-Provider
über `socket-proxy`). Labels kommen nicht nur aus der Compose-Datei, sondern
auch aus dem **Abbild** (`LABEL` im Dockerfile) – prolo ersetzte nur die des
Hauptdienstes in der Datei. Ein Abbild mit
`LABEL traefik.http.routers.x.rule=Host(\`admin.<domain>\`)` und hoher
`priority` – installiert auf dem einfachsten Weg, „Ein Abbild“ – bekam die
Admin-Seite; mit `auth.` die Anmeldeseite, also dein Passwort, mit echtem
Zertifikat. Gemessen mit Traefik 3.6.25: vorher „ECHTE ADMIN-SEITE“, mit
dem Container „FALSCHE ADMIN-SEITE (vom Angreifer)“.

**Jetzt:** Traefik sieht Docker nicht mehr. Kein Docker-Provider, kein
`socket-proxy`, kein Socket. Die Router schreibt prolo als Dateien:
`unterbau.yml` (auth, Rückweg der Anmeldung, admin – von `prolo einrichten`
aus `prolo.conf`) und `tool-<name>.yml` je Tool (beim Anlegen, Ändern,
Bearbeiten, Zurückholen; weg beim Entfernen). Ziele haben Namen, die kein
Tool tragen darf: `prolo-authentik`, `prolo-admin`, `prolo-tool-<name>`
(Netz-Alias; `kaefig.py` sperrt `prolo…` für Dienste, Container, Aliasse).
Dass Docker die Namen in der Reihenfolge der Netznamen auflöst (`prolo-*` vor
`tool-*`, gemessen), ist damit keine Voraussetzung mehr.

Bestehende Server: `prolo einrichten` (auch nach `prolo update`) schreibt
die Zusatzdatei jedes Tools neu und legt es neu an – **nach der Prüfung**
(N-138). Findet die neue Prüfung bei einem alten Tool etwas, bleibt es, wie
es ist, und „Was zu tun ist“ sagt: `sudo prolo einrichten` und bestätigen.

Geprüft mit echtem Traefik aus dem neuen `docker-compose.yml` (Abbild aus
dem Release 3.6.25), Authentik und Admin-Seite als Attrappen:
`admin.` über die Datei erreichbar; das Tool mit den Fallen-Labels bleibt
unter seinem eigenen Namen, `admin.` bleibt echt; lehnt die Anmeldung ab,
sind Admin-Seite und geschütztes Tool zu, das Tool ohne Anmeldung offen;
`tool rm` nimmt den Router weg (404). Alter Server nachgestellt
(Zusatzdatei ohne Alias): Tool 502, nach `tools_auffrischen` 200; Tool mit
neuer Gefahr bleibt stehen, mit Meldung; mit Terminal fragt es und merkt
sich die Antwort. Neu im Durchlauf: Abbild mit Fallen-Labels. Einheitstests
76 → 75 (drei Prüfungen der Labels durch zwei der Router-Datei ersetzt),
Gegenprobe 60 → 62, alle gefunden.

---

## N-140 — Das Anmelde-Cookie für alle Tools galt auch für die Admin-Seite

Der Provider im Domain-Modus setzt sein Cookie für `.<domain>`. Der Browser
schickt es an **jedes** Tool mit – auch an eines ohne Anmeldung
(Vaultwarden, n8n, eine öffentliche Seite). Ein Tool, das übernommen wird
(eine Lücke in n8n reicht), sieht es in jeder Anfrage und kommt damit auf
`admin.<domain>`: Tools entfernen, „ohne Anmeldung“ schalten, alte Stände
zurückholen.

**Jetzt:** ein eigener Provider `ProloWelt Admin` im Modus
`forward_single` für `admin.<domain>`, **ohne** `cookie_domain` – sein Cookie
gilt nur dort. Der eingebaute Outpost nimmt für einen Namen zuerst den
Provider, der genau ihn hat. Beide Provider stehen im Haupt-Blueprint, nur
dort wird die Liste des Outposts gesetzt (zwei Blueprints, die dieselbe
Liste setzen, nähmen sich den Provider bei jedem Anwenden wieder weg). Die
Bindung an die Admin-Gruppe steht für sich (`prolowelt-admin-gruppe.yaml`):
fehlt die Gruppe, scheitert nur sie, die Anmeldung bleibt, und `einrichten`
sagt es.

`prolo einrichten` prüft die **Wirkung**: der Outpost muss `admin.<domain>`
nach `https://admin.<domain>/outpost.goauthentik.io/start` weiterleiten
(eigener Provider) und ein Tool nach `auth.<domain>` – sonst Abbruch mit dem
Grund. Läuft nichts davon, gilt der Stand von vorher: der Domain-Provider
beantwortet auch `admin.`.

Geprüft: Einheitstests für Blueprint und Auswertung der Weiterleitung,
Einheitstests 75 → 77, Gegenprobe 62 → 64. **Nicht hier gelaufen:** echtes
Authentik (Docker Hub ist von hier nicht erreichbar) – der Durchlauf prüft
es auf dem Server (Weiterleitung für `admin.` jetzt nach `admin.`).

---

## N-141 — Die Admin-Seite war aus dem ganzen Internet erreichbar

Wer `admin.<domain>` aufrief, kam bis zur Anmeldung – von überall. Die
Anmeldung schützt; aber die Seite, die den ganzen Server steuert, muss nicht
jedem Rechner der Welt ihre Anmeldeseite zeigen (Passwort-Raten, eine Lücke in
Authentik, ein gestohlenes Cookie – alles braucht erst den Weg dorthin).

**Jetzt:** `ADMIN_NETZE` in `prolo.conf` (leer = wie bisher). Steht dort etwas,
hängt vor der Anmeldung eine `ipAllowList` von Traefik; geprüft wird die echte
Gegenstelle, keine Kopfzeile. Falsche Einträge meldet `prolo` mit Beispiel.

Geprüft mit echtem Traefik: ohne Eintrag 200; nur `203.0.113.7/32` → 403, das
Tool daneben weiter 200; eigenes Netz erlaubt → 200; mit `X-Forwarded-For`,
`X-Real-Ip` oder `Forwarded` auf die erlaubte Adresse → weiter 403; `kein-netz`
→ Meldung. Einheitstests 77 → 78, Gegenprobe 64 → 65.

---

## N-142 — Ein Ordner im Eingang legte den Agenten lahm

Der Eingang des Auftragsbuchs gehört der Admin-Seite. Legt sie dort – etwa
übernommen – einen **Ordner** `<kennung>.json` ab, scheitert `os.remove`
mit `IsADirectoryError`; der Agent stirbt, systemd startet ihn neu, er stirbt
wieder – und nimmt keinen Auftrag mehr an. Gemessen.

**Jetzt:** `agent.weg()` räumt auch Ordner weg und überlebt jeden anderen
Fehler beim Wegräumen mit einer Zeile im Protokoll. Einheitstests 78 → 79,
Gegenprobe 65 → 66.

---

## N-143 — Ein zu weites `ADMIN_NETZE` ließ jedes Tool durch

Beim Angriff auf den eigenen Fix (N-141) gefunden: ein Tool spricht Traefik
aus seinem Netz an – seine Adresse liegt in einem Bereich, den Docker vergibt
(172.16.0.0/12, 192.168.0.0/16). Wer dort `ADMIN_NETZE=172.16.0.0/12`
einträgt (oder `0.0.0.0/0`), lässt jedes Tool an die Netzsperre vorbei.
Gemessen: Anfrage mit Absender im Netz eines Tools → 200, mit
`203.0.113.7/32` → 403.

**Jetzt:** `orte.admin_netze` lehnt jedes Netz ab, das sich mit diesen
Bereichen oder einem Netz überschneidet, das es auf dem Server schon gibt –
und sagt, was stattdessen hingehört. Einheitstests 79 → 80, Gegenprobe
66 → 67.

---

## N-144 — `tool set --host admin.<domain>` gab die Admin-Seite einem Tool

Beim Anlegen prüfte prolo, dass ein Tool nicht `admin.` oder `auth.` heißt
und kein anderes Tool denselben Namen hat – beim Ändern mit `tool set --host`
nicht. Gemessen: `prolo tool set seite --host admin.prolo.test` → „ok“, und
`admin.prolo.test` zeigte die Seite des Tools, ohne Anmeldung, samt Cookie
der Admin-Seite an das Tool. Nur auf der Kommandozeile (root) – aber ein
Tippfehler genügt.

**Jetzt:** `tools.host_pruefen` – dieselbe Prüfung beim Anlegen und
Ändern, auch wenn sich nur die Anmeldung ändert. Gemessen: abgelehnt mit
„gehört dem Unterbau“. Einheitstests 80 → 81, Gegenprobe 67 → 68.

---

## N-145 — `include:` lädt aus Git und OCI-Registries nach

Am eigenen Fix (N-137) gefunden: Compose lädt `include:` nicht nur aus
Dateien, sondern von sich aus auch aus Git (`https://….git`, `git@…`) und
aus Registries (`oci://…`) – gemessen: Compose versucht beides ohne jede
Einstellung. Die Prüfung holte sich damit eine Fassung, der echte Start
Sekunden später noch einmal – der Angreifer liefert der ersten eine harmlose
und der zweiten eine andere. Als root holte Compose dabei über SSH mit den
Schlüsseln von root.

**Jetzt:** die Prüfung läuft zusätzlich **ohne Netz**: als root
`unshare --net` + `setpriv` auf `prolo-pruefer` (`--clear-groups`,
`--no-new-privs`), in Tests ein eigener Nutzer-Namensraum ohne Netz – auf
den eigenen Nutzer abgebildet, nicht auf root (`unshare -r` ließ den
Prozess eigene Dateien trotz `chmod 0` lesen; der Test fand es). Jede
entfernte Quelle scheitert, die Meldung sagt warum; was die Prüfung nicht
besteht, startet nie. (Aus Dateien im Tool lädt `include` weiter.)

Unterwegs, vor dem Commit gefunden: die Hilfsfunktion übergab dem Prüfer den
Ordner, den man ihr nannte – mit `/tmp` als Argument im neuen Schritt des
Durchlaufs hätte sie `/tmp` des Servers dem Prüfer gegeben (hier im
Arbeitsbereich so geschehen und zurückgestellt). Jetzt übergibt nur
`modell()` seinen eigenen, frischen Ordner; nach einer Prüfung gehört in
`/tmp` nichts dem Prüfer (gemessen: 0).

Geprüft als root mit `tool add --von-web`: `include` aus OCI und Git →
abgelehnt mit „lädt etwas aus dem Netz nach“; `include`/`extends` eines
anderen Tools weiter abgelehnt; harmloses Tool läuft. Wirkung im Test: der
Prüfbefehl sieht nur `lo`. Neu im Durchlauf: Prüfer ohne Netz, als
`prolo-pruefer`. Einheitstests 81 → 83, Gegenprobe 68 → 70.

---

## N-146 — Die Prüfung hing an einer Fassung von Compose

Gefunden vom CI (GitHub, `ubuntu-24.04`): `kaefig.modell` rief
`docker compose config --no-env-resolution`. Gemessen mit den Fassungen von
GitHub: **2.29 und 2.33 kennen den Schalter nicht** – dort wäre jede Prüfung
gescheitert und kein Tool mehr anzulegen gewesen; **2.36 und 2.39** kennen
ihn, zeigen `env_file` aber trotzdem nicht im Modell; 5.7 zeigt es. Der
Einheitstest, der den Pfad im Modell erwartete, war auf dem Runner rot.

**Jetzt:** `kaefig.env_pfade_sichtbar()` gibt den Schalter nur, wenn
`docker compose config --help` ihn nennt. Der Schutz hängt nicht daran:
`env_file` liest der Prüfer ohne Rechte – an eine Datei, die nur root lesen
darf, kommt er nicht. Gemessen mit 2.33, 2.36 und 5.7 je echt mit
`tool add --von-web`: `env_file` auf eine Datei mit 0600 in einem Ordner mit
0700 → abgelehnt; harmloses Tool → läuft; `secrets`, Volume-Name, `include`,
`include` aus dem Netz → abgelehnt.

**Bleibt:** mit Compose vor 5.x geht ein `env_file` auf eine Datei durch, die
**jeder** auf dem Server lesen darf (gemessen mit einer Datei 0644). Solche
Dateien sind keine Geheimnisse; `install.sh` installiert Compose aus dem
Paketlager von Docker, also eine neue Fassung, die den Pfad zeigt.

Der Test für `env_file` erwartet jetzt die Wirkung (abgelehnt), nicht die
Darstellung. Einheitstests 83 → 84, Gegenprobe 70 (ein eingebauter Fehler
zielt jetzt auf die Prüfung statt auf den Schalter).

Danach, ebenfalls vom CI: auf `ubuntu-24.04` sind eigene Nutzer-Namensräume
gesperrt (AppArmor) – der Test „Prüfung ohne Netz“ im Testmodus wird dort
übersprungen, und sein eingebauter Fehler blieb unentdeckt. Der Testmodus
ist nur für die Tests da; der Weg als root hat seinen eigenen eingebauten
Fehler und einen Schritt im Durchlauf. Der Eintrag für den Testmodus ist
heraus: Gegenprobe 70 → 69.

---

## N-147 — Die Wirkungsprüfung des Admin-Providers erwartete die falsche Weiterleitung

Gefunden im ersten echten Durchlauf mit Authentik 2026.8 (CI): `einrichten`
brach ab – „admin. geht nicht über den eigenen Provider“. Die Antworten des
Outposts zeigten das Gegenteil:

```
admin.prolo.test           302 https://auth.prolo.test/application/o/authorize/?client_id=wmvG…&redirect_uri=https://admin.prolo.test/outpost.goauthentik.io/callback…
prolo-pruefung.prolo.test  302 https://auth.prolo.test/application/o/authorize/?client_id=UH7N…&redirect_uri=https://auth.prolo.test/outpost.goauthentik.io/callback…
```

Zwei Provider (zwei `client_id`), und der Rückweg der Admin-Seite führt nach
`admin.` – dort setzt der Outpost sein Cookie, nur für diesen Namen. N-140
wirkt. Falsch war die Annahme, *wie* Authentik weiterleitet: nicht erst über
`<name>/outpost.goauthentik.io/start`, sondern gleich zu `authorize`.

**Jetzt:** `unterbau.rueckweg()` liest den Rückweg (`redirect_uri`; für
ältere Fassungen der Weg über `/outpost.goauthentik.io/start`), und geprüft
wird, worauf es ankommt: Rückweg der Admin-Seite nach `admin.`, eines Tools
nach `auth.`. Der Durchlauf benutzt dieselbe Auswertung. Der Einheitstest
nimmt die gemessenen Antworten von oben als Fall, dazu den Gegenfall (Rückweg
der Admin-Seite nach `auth.`).

---

## N-148 — Eine Neuinstallation scheiterte zufällig beim ersten Start von Authentik

Älter als die Funde davor: schon der CI-Lauf von `main` (8742a76) war rot,
und zwei der drei Durchläufe für diesen Pull Request auch –
`prolo einrichten` meldete „Der Unterbau kam nicht vollständig hoch“ mit
`failed to create symlink: …/prolo_authentik-data/_data/media: file exists`.
Server und Worker hängen dasselbe Volume `authentik-data` ein; beim ersten
Start füllt Docker das leere Volume aus dem Abbild (dort liegt der Verweis
`/data/media`) – starten beide zugleich, kopieren beide, und einer scheitert.
Ein laufender Server ist nicht betroffen (sein Volume ist längst gefüllt),
wohl aber jede Neuinstallation und jeder Umzug.

Nachgestellt mit einem kleinen Abbild mit demselben Verweis: 100 Starts
gleichzeitig → 1 mal „file exists“ (das Abbild von Authentik ist größer, das
Fenster weiter: im CI 2 von 3); mit dem Worker nach dem Server → 0 von 100.

**Jetzt:** der Worker startet nach dem Server (`depends_on … service_started`)
– zwei gleichzeitige Kopien gibt es dann nicht mehr. Einheitstests 84 → 85,
Gegenprobe 69 → 70.

