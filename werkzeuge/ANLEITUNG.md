# Ein Werkzeug anlegen, Netze verwalten, nachsehen

Diese Datei beschreibt drei Griffe. Die Regeln dahinter stehen in
`CLAUDE.md`, die Narben in `NEUE-BEFUNDE.md`.

| ich will … | Befehl |
|---|---|
| ein neues Werkzeug | `sudo prolo neu <name>` |
| sehen, wer in welchem Netz hängt | `prolo netze` |
| ein Netz anlegen / schließen / umziehen | `sudo prolo netze anlegen\|schliessen\|umziehen …` |
| dasselbe im Browser, dazu starten, anhalten, aktualisieren | `https://admin.prolo.me` |
| ein eigenes Werkzeug in sein eigenes Repository | `werkzeuge/auslagern.sh`, dann `werkzeuge/umstellen.sh` (Abschnitt 7) |

---

## 1. Die zwei Arten von Werkzeug

Das ist der wichtigste Unterschied im ganzen Stack.

| | **fremd** | **eigen** |
|---|---|---|
| Beispiele | n8n, Vaultwarden, Seafile | wiki, bordbuch, www, admin |
| woher der Code kommt | vom Hersteller, als fertiges Abbild | von uns, mit `Dockerfile` |
| `docker-compose.yml` | **die Datei des Herstellers, unverändert** | von uns |
| `docker-compose.override.yml` | **unsere Zutat** | — |
| Anmeldung | wird gefragt | immer Authentik (`§17`) |

**Ein Fremdwerkzeug läuft so, wie der Hersteller es vorschlägt.** Unser
einziger Eingriff: ein Name `x.prolo.me`, ein Zertifikat, ein eigenes Netz
und die Grenzen aus `§19`. Alles davon steht in der **zweiten** Datei,
`docker-compose.override.yml` — `docker compose` liest beide von selbst,
ohne `-f` und ohne Umweg.

Der Gewinn: kommt eine neue Fassung, ersetzt man **nur** die Datei des
Herstellers. Unsere Zeilen bleiben liegen und können nicht beim Abschreiben
verloren gehen.

Was dabei herauskommt, zeigt:

```bash
cd /opt/stack/<werkzeug> && docker compose config
```

> Das ist die Wahrheit über ein Werkzeug — nicht eine einzelne Datei.

---

## 2. `sudo prolo neu <name>`

Fragt der Reihe nach:

1. **Art** — fremd oder eigen.
2. **Abbild** — mit fester Fassung. `latest` wird abgelehnt (`§19`):
   Datenbankmigrationen bei Hauptversionen sind nicht umkehrbar.
3. **Dienstname** in der Compose-Datei, **interner Port**, **Hostname**.
4. **Netz** — neues `netz-<name>` (empfohlen) oder ein vorhandenes. Beim
   Teilen wird nach dem Grund gefragt; der landet im Label
   `prolo.netz.geteilt`.
5. **Anmeldung** — **ohne Vorgabe**, ein Enter genügt hier nicht:
   - *Authentik davorschalten* — niemand kommt an das Werkzeug, ohne sich
     zentral anzumelden.
   - *eigene Anmeldung des Werkzeugs* — für n8n, Vaultwarden, Seafile: die
     bringen eine mit, und ein Teil ihrer Oberfläche (Webhooks, API,
     Handy-App) kann eine ForwardAuth-Anmeldung gar nicht durchlaufen.
     Dann wird der **Grund** abgefragt. Bedingungen: `CLAUDE.md §17a` —
     vor allem **2FA in dieser eigenen Anmeldung einschalten**.

Dann legt es an: den Ordner mit allen Dateien, das Docker-Netz, den Eintrag
bei Traefik (beide Stellen) — und sagt zum Schluss, was noch von Hand
bleibt (DNS, Authentik-Anwendung).

**Das Netz kommt zuerst.** Geht es nicht, entsteht gar kein Ordner. Ein
halb angelegtes Werkzeug sieht sonst aus wie ein fertiges.

Alles lässt sich auch als Schalter mitgeben, dann fragt es nichts:

```bash
sudo prolo neu vaultwarden \
  --art fremd --abbild vaultwarden/server:1.34.1 --dienst vaultwarden \
  --port 80 --netz-neu --anmeldung eigene \
  --grund "Handy-App und Browser-Erweiterung sprechen die API direkt"
```

### Danach, bei einem Fremdwerkzeug

1. Die `docker-compose.yml` des Herstellers in die angelegte Datei
   kopieren — sie enthält bis dahin nur einen Platzhalter.
2. **Seine `ports:`-Zeile entfernen.** Erreichbar ist der Dienst über
   `https://<name>.prolo.me`; eine `ports:`-Zeile geht an Traefik, an der
   Anmeldung **und** an der Firewall vorbei (`§19`).
3. Heißt der Dienst dort anders, den Namen in
   `docker-compose.override.yml` angleichen.
4. Die Zeile `PROLO-PLATZHALTER` löschen.
5. `sudo prolo start <name>`

### Ein Werkzeug wieder loswerden

```bash
sudo prolo entfernen <name>
```

Das **löscht nicht**: es hält den Container an und legt den ganzen Ordner
samt Volume-Inhalten ins Archiv unter `/opt/stack/.archiv/`.
`sudo prolo zurueckholen <name>` holt ihn zurück.

**Steht das Werkzeug im Git** — und das tun alle, die hier entstanden sind —,
fehlt danach noch eine Entscheidung. Der Ordner ist von der Platte weg, die
Dateien stehen weiter im Repository:

```bash
cd /opt/stack
git checkout -- <name>/                      # doch behalten: alles zurück
# oder
git rm -r <name> && git commit -m "<name> entfernt"    # überall weg
```

Solange weder das eine noch das andere passiert ist, steht der Arbeitsstand
auf gelöschten Dateien, und der nächste `git pull` bricht daran ab.
`prolo entfernen` sagt das beim Entfernen, und `prolo status` sagt es danach.

> **„Nicht auf der Platte" heißt nicht „gibt es nicht".** Fehlt ein Ordner,
> der im Git steht, will er **zurückgeholt** werden, nicht neu angelegt —
> `prolo neu` lehnt das ab und nennt den Weg.

---

## 3. Die zwei Sperren in `prolo start`

`prolo start` misst vorher die **zusammengesetzte** Konfiguration und
startet nicht, wenn eines davon zutrifft:

| Sperre | Weg heraus |
|---|---|
| ein Dienst veröffentlicht einen Port | `ports:`-Zeile entfernen — oder erklären: `prolo.ports=<grund>` |
| ein Router hat keine Anmeldung | `middlewares=authentik@file` — oder erklären: `prolo.anmeldung=eigene` + `prolo.anmeldung.grund` |
| der Platzhalter steht noch drin | Herstellerdatei einsetzen, Zeile löschen |

Die Sperre sitzt in `prolo`, nicht in Docker. Wer es wirklich will, kann
immer noch `cd /opt/stack/<name> && docker compose up -d` tippen — der
**geführte** Weg soll nur nicht der sein, auf dem man aus Versehen einen
Dienst ins offene Netz stellt.

`prolo stop <name>` hat keine Sperre. Anhalten ist nie gefährlich.

---

## 4. `prolo netze`

Ohne Zusatz: die Übersicht.

```
Netze
  NETZ                 GEHOERT ZU               TRAEFIK  DOCKER  CONTAINER
  netz-admin           admin                    ja       ja      1
  netz-n8n             n8n                      ja       ja      1
  netz-test            (niemand)                ja       ja      0

Werkzeuge
  WERKZEUG      DIENST          NETZ             SCHUTZ      OFFENE PORTS
  n8n           n8n             netz-n8n         eigene      -
  traefik       traefik         netz-…           -           80,443 (Eingang des Stacks)
```

Die Spalte **SCHUTZ** ist die wichtigste. Sie wird aus der
Middleware-Kette **gelesen**, nicht geraten. `OFFEN` heißt: ein Router ohne
Anmeldung und ohne Erklärung. Rückgabewert 2, wenn etwas zu klären ist.

| Befehl | was er tut |
|---|---|
| `sudo prolo netze anlegen <netz>` | `docker network create` **und** beide Stellen bei Traefik |
| `sudo prolo netze schliessen <netz>` | nur, wenn es niemand mehr erklärt und kein Container drin hängt |
| `sudo prolo netze umziehen <tool> <netz>` | Kopie, ersetzen, **messen**, bei Abweichung alles zurück |

Nach `anlegen` und nach `umziehen` gilt:

```bash
sudo prolo start traefik     # bzw. sudo prolo start <tool>
```

> **Ein laufender Container bekommt ein neues Netz nicht nachträglich**
> (`N-58`). Docker verbindet beim Anlegen. `prolo start` ist
> `docker compose up -d` — das legt neu an, sobald sich die Konfiguration
> geändert hat. `neustart` würde **nicht** reichen.

### Einen Testbereich aufmachen

```bash
sudo prolo netze anlegen netz-test
sudo prolo start traefik
sudo prolo neu probier-mal --art fremd --abbild nginx:1.27-alpine \
     --port 80 --netz netz-test --anmeldung authentik
```

Alles in `netz-test` erreicht einander, aber nichts außerhalb. Fertig
damit:

```bash
sudo prolo entfernen probier-mal      # ins Archiv, nicht gelöscht
sudo prolo netze schliessen netz-test
sudo prolo start traefik
```

---

## 5. Die Admin-Seite

`https://admin.prolo.me` — hinter Authentik **und** hinter den eigenen
Gruppen der Seite:

| Gruppe | darf |
|---|---|
| `admin` | sehen: Übersicht, Werkzeuge, Netze, Aufträge |
| `admin-betrieb` | zusätzlich **bedienen** und Protokolle der Container lesen |

Die Hero-Kennzahl ist **nicht** die Zahl der Container, sondern die Zahl
der Punkte zum Klären: ein Router ohne Anmeldung, ein unerklärt offener
Port, ein Container in einem anderen Netz als sein Label sagt, ein Dienst,
der nicht läuft.

**Bedienen.** Jedes Werkzeug hat eine eigene Seite: *Starten* bzw. *Neu
starten*, *Aktualisieren*, *Prüfen*, *Anhalten* (fragt nach), dazu, was auf
dem Server liegt (Art, Netze, Volumes, Sicherung), das Protokoll der
Container und die letzten Aufträge. Auf *Aufträge* gibt es *Jetzt
sichern*, auf *Netze* *Netz anlegen*. Traefik, Authentik, den Vermittler
und die Admin-Seite selbst kann man von dort nicht anhalten — danach gäbe
es keine Seite mehr, von der aus man sie wieder startet.

**Die Seite tut das nicht selbst.** Sie hat keinen schreibenden Zugriff
auf Docker — wer den hat, hat den ganzen Server. Jeder Knopf legt einen
**Auftrag** ins Auftragsbuch (`admin/auftraege/eingang`), und auf dem
Server führt `werkzeuge/auftrag.py` ihn aus, angestoßen von systemd — über
`prolo`, mit Startsperre, Sicherung und Rückweg (`A-01`). Was dort nicht
erlaubt ist, geht auch von der Seite aus nicht. Die Auftragsseite zeigt
den Stand und die Ausgabe, die wächst, solange er läuft.

```bash
python3 /opt/stack/werkzeuge/auftrag.py liste      # wer wann was
sudo systemctl status prolo-auftraege.path         # holt der Waechter ab?
sudo python3 /opt/stack/werkzeuge/auftrag.py abarbeiten   # von Hand
```

Steht ein Auftrag länger als eine halbe Minute auf „wartet", sagt die
Seite das — dann läuft der Wächter nicht; `sudo prolo einrichten` richtet
ihn ein (Schritt 6c, gefahrlos zu wiederholen).

**Lesen** tut sie über den Vermittler vor dem Docker-Socket: Container,
Netze, Protokolle. Kein Zugriff auf `/opt/stack`, also auch nicht auf
`.env`-Dateien oder Zertifikate. Angehaltene Werkzeuge kennt Docker nicht
mehr — die Liste kommt darum zusätzlich aus dem **Bestand** der
Werkzeugordner, den der Ausführer alle fünf Minuten neu schreibt.

Einrichten:

```bash
sudo prolo netze anlegen netz-admin
sudo prolo geheimnisse --verteilen     # schreibt PROLO_EINLASS in admin/.env
sudo prolo einrichten                  # Auftragsbuch und Waechter (6c)
sudo prolo start traefik
sudo prolo aktualisieren admin
```

Dazu in Authentik: eine Anwendung für `admin.prolo.me` anlegen **und dem
Outpost zuweisen**, und die Gruppen `admin` und `admin-betrieb` mit den
Menschen darin. Ohne die Zuweisung antwortet die Anmeldung mit 403, und
das sieht aus wie ein kaputtes Werkzeug.

### Wenn `--verteilen` nach einem frischen Aufbau fragt

Manche Geheimnisse stehen **auch außerhalb ihrer Datei** — `PG_PASS` in
PostgreSQL selbst, `N8N_ENCRYPTION_KEY` im Volume von n8n. Die sind in der
`geheimnisse.conf` als `WECHSEL=haende` markiert: ein *neuer* Wert sperrt
das Werkzeug aus seinen eigenen Daten aus.

Fehlt so ein Wert in **allen** Dateien, kann das zweierlei heißen — es ist
ein frischer Aufbau (dann ist Würfeln genau richtig), oder das Werkzeug
läuft schon und hält den alten woanders. Die Dateien können das nicht
unterscheiden, also fragt `--verteilen` einmal nach:

```
Frisch aufgesetzt, also noch kein alter Wert irgendwo? [j/N]
```

Ohne Terminal — im Skript, über `ssh <host> "…"` — antwortet `--frisch`
dasselbe:

```bash
sudo prolo geheimnisse --verteilen --frisch
```

`--frisch` ist **kein** Generalschlüssel: steht der Wert schon irgendwo,
wird er auch damit nicht angefasst.

---

## 6. Prüfen

```bash
werkzeuge/neu-pruefen.sh          # prolo neu und prolo netze, ausgefuehrt
python3 werkzeuge/neu-gegenprobe.py   # und ob die Pruefung Zaehne hat
werkzeuge/netze-pruefen.sh        # steht die Netztrennung noch?
cd admin && ./tests/alle.sh       # die Admin-Seite
werkzeuge/auftrag-pruefen.sh      # der Ausfuehrer der Auftraege
```

`neu-pruefen.sh` reicht `docker compose config` an das echte `docker`
durch. Das braucht **keinen laufenden Docker-Dienst** — es ist die einzige
Stelle, an der wirklich gemessen und nicht nachgebildet wird.

---

## 7. Ein eigenes Werkzeug in sein eigenes Repository umziehen

`wiki`, `bordbuch` und `www` sind vorbereitet (`U-01` bis `U-03`): jedes
bringt seine `CLAUDE.md`, seinen Arbeitsablauf zum Veröffentlichen und
seinen Vertragstest schon mit. Umgezogen wird in drei Schritten, **in
dieser Reihenfolge** — auf dem eigenen Rechner, nicht auf dem Server.

**1. Leeres Repository anlegen.** Auf GitHub `prolo2408/<werkzeug>`,
**ohne** README, `.gitignore` und Lizenz. Ein Ziel mit Inhalt wird nicht
angefasst.

**2. Auslagern — mit der ganzen Geschichte:**

```bash
werkzeuge/auslagern.sh bordbuch git@github.com:prolo2408/bordbuch.git
werkzeuge/auslagern.sh bordbuch --trocken      # vorher ansehen, schiebt nichts
```

Der Code landet an der Wurzel des neuen Repositorys, jeder Commit, der das
Werkzeug berührt hat, kommt mit. Die Dateien, die dem **Betrieb** gehören
(`docker-compose.override.yml`, `sicherung.conf`, `aktualisierung.conf`,
`geheimnisse.conf`, beim Wiki das Bedienhandbuch), bleiben hier. In
proloWorld ändert sich dabei **nichts**.

Dann im neuen Repository die erste Fassung veröffentlichen:

```bash
git clone git@github.com:prolo2408/bordbuch.git && cd bordbuch
git tag v2.6.2 && git push --tags
```

Der Arbeitsablauf baut `ghcr.io/prolo2408/bordbuch:2.6.2` (Reiter
*Actions*). Ist das Paket privat, braucht der Server einmalig
`docker login ghcr.io -u prolo2408` mit einem Token (`read:packages`).

**3. Umstellen — erst, wenn das Abbild da ist:**

```bash
werkzeuge/umstellen.sh bordbuch
git diff --cached --stat && git commit -m "bordbuch: vom Werkzeug-Repository"
```

Es prüft **vorher**, ob sich das Abbild holen lässt, und fasst sonst
nichts an. Danach liegen in `bordbuch/` nur noch die Betriebsdateien und
die Herstellerdatei ohne `build:` — das Werkzeug wird behandelt wie n8n.
Auf dem Server:

```bash
sudo prolo aktualisieren bordbuch      # holt statt zu bauen, Volumes bleiben
```

**Eine neue Fassung später:** im Werkzeug-Repository taggen, hier die
Nummer in `<werkzeug>/docker-compose.yml` hochsetzen, `sudo prolo
aktualisieren <werkzeug>`.

Geprüft wird das alles mit `werkzeuge/auslagern-pruefen.sh` — es zieht das
Wiki wirklich in ein (lokales) leeres Repository um, lässt dort die Tests
des Werkzeugs allein laufen und stellt in einer Kopie alle drei um.
