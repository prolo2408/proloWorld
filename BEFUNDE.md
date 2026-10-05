# Befunde

Was schiefging, warum, und was daraus folgt. Fast jede Regel in `CLAUDE.md`
hat hier eine Narbe.

Die Befunde `B-01` bis `B-49`, `N-01` bis `N-113`, `U-01` bis `U-04`,
`A-01` bis `A-03` und `F-01`/`F-02` gehören zur ersten Fassung des Stacks
(mit Wiki, Bordbuch und `www` im selben Repository). Sie stehen in
`NEUE-BEFUNDE.md` in der Git-Geschichte, letzter Stand Commit `4d16fd7`:

    git show 4d16fd7:NEUE-BEFUNDE.md

Neue Befunde bekommen die nächste freie Nummer: **N-133**.

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
