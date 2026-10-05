# ProloWelt – die Regeln

Verbindlich für jede Sitzung und jeden Agenten, die an diesem Repository
arbeiten.

**Leitsatz:** Funktionierender Code ist der Anfang, nicht das Ziel. Ein
Werkzeug ist fertig, wenn es auch dann noch etwas Vernünftiges tut, wenn
etwas schiefgeht – und wenn man es gerne benutzt. **Und es bleibt einfach:**
was keinen Fehler verhindert und keinem Menschen hilft, kommt nicht hinein.

Was ProloWelt ist: der **Unterbau** für selbst gehostete Tools – Traefik,
Authentik, Admin-Seite, Sicherung, Updates. Die Tools selbst stehen **nicht**
hier; sie liegen auf dem Server unter `/opt/tools/<name>/`.

| Datei | Inhalt |
|---|---|
| **diese hier** | die Regeln |
| `README.md` | die Bedienung: installieren, Alltag, Sicherung, Umzug, Fehlersuche |
| `BEFUNDE.md` | was schiefging und warum – fast jede Regel hier hat dort eine Narbe |
| `CHANGELOG.md` | die Fassungen |
| `prolo` + `kern/` | der Befehl und alles dahinter (Python, nur Standardbibliothek) |
| `docker-compose.yml` | der Unterbau als ein Compose-Projekt `prolo` |
| `admin/` | die Admin-Seite |
| `tests/` | `alle.sh`, Einheitstests, Gegenprobe, `durchlauf.py` |

---

# TEIL 0 – WIE HIER GEARBEITET WIRD

- **Ein Befund, ein Arbeitsschritt, ein Commit.** Die Commit-Nachricht
  beginnt mit der Nummer (`N-129: …`). Neue Befunde bekommen die nächste
  freie Nummer in `BEFUNDE.md`.
- **Nichts still nebenbei ändern.** Was beim Arbeiten auffällt, wird ein
  neuer Befund mit eigenem Schritt.
- **Prüfschritte werden ausgeführt, nicht überlegt.** Im Commit steht, was
  lief und was herauskam – **mit Zahlen**.
- **Erwartungswerte von Hand.** Nie die Ausgabe des Codes als Erwartung
  übernehmen.
- **Tests müssen Zähne haben.** Jede neue Prüfung kommt mit einem Eintrag in
  `tests/gegenprobe.py`: der Fehler, den sie finden soll, wird eingebaut, und
  sie muss rot werden. Die Gegenprobe arbeitet in einer **Kopie** – der
  Rückweg einer Probe darf nie die eigene, noch nicht eingecheckte Arbeit
  sein.
- **Vor dem Push läuft `tests/alle.sh` ganz – und nicht als root**, und nicht
  durch eine Pipe gelesen (`alle.sh | tail` liefert den Rückgabewert von
  `tail`). Wer `kern/`, `docker-compose.yml`, `traefik/` oder `authentik/`
  anfasst, fährt zusätzlich `sudo python3 tests/durchlauf.py`.
- **Eine Oberfläche ist erst geprüft, wenn sie im Browser geladen wurde** –
  hinter der echten Anmeldung, drei Breiten (360, 768, 1920), beide Themen.
  Und der Prüfer wird gegengeprobt: „nichts gefunden“ zählt erst, wenn
  gezeigt ist, dass er etwas finden *kann*.
- **Eine Meldung ist kein Beweis.** Geprüft wird die Wirkung (hängt der
  Provider am Outpost?), nicht der Text, der sie ankündigt.
- **Weniger ist mehr.** Kein Test, der nur prüft, dass sich nichts ändert;
  keine zweite Liste, die man mit einer ersten abgleichen muss – lieber eine
  gemeinsame Quelle (`kern/auftrag.py` für Admin-Seite und Agent).

---

# TEIL I – OBERFLÄCHE (die Admin-Seite)

## 1. Grundhaltung

Ruhig, sachlich, datennah. Keine Verläufe, keine Emojis, keine Illustrationen.
Eine Akzentfarbe (Blau), sonst Graustufen; Farbe bedeutet immer etwas.
Dunkelmodus ist Standard, Hellmodus gleichwertig. **Lesbarkeit schlägt
Palette:** ist eine Kombination schlecht lesbar, wird sie geändert.

## 2. Farbtoken

Nie Farbwerte direkt in Komponenten. Die Token stehen in `admin/server.py`
(`TOKENS`), Umschaltung über `data-theme` auf `<body>`.

| Token | wofür | nicht |
|---|---|---|
| `--accent` | genau **eine** Primäraktion je Ansicht, aktive Navigation | große Flächen |
| `--accent-soft` / `--accent-ink` | Badges, aktive Nav-Zeile / Text darauf | Karten |
| `--good` | gesund, erfolgreich gelesen | |
| `--warm-soft/ink` | Hinweise, „ohne Anmeldung“ | zerstörende Aktionen |
| `--danger` | Entfernen, Fehler | Warnungen |
| `--feature` | höchstens **eine** farbige Fläche je Ansicht | |

Text auf `--accent` läuft über `--on-accent`. **Farbe ist nie die einzige
Information** – jeder Marker trägt sein Wort. Kontrast: Text mindestens
4.5:1, große Schrift 3:1. Wer ein neues Token braucht, ergänzt es in
`TOKENS` mit klarer Bedeutung.

## 3. Schrift, Form, Bausteine

- **Sora** 600 für Überschriften und Kennzahlen, **Instrument Sans** für
  alles andere, **JetBrains Mono** für Rohwerte, Befehle, Tabellenköpfe.
  Liegen als woff2 in `admin/schriften/` – nichts von außen (CSP).
- Seitentitel 20–22 px, Kennzahl 30–40, Kartentitel 15, Fließtext 13–14,
  Label 10–12. **Am Handy nichts unter 12 px.**
- Karten: `--surface`, 1 px `--line`, Radius 14, **kein Schatten**. Gruppen mit
  `flex/grid` + `gap`; Raster-Kinder brauchen `min-width:0`.
- Inhalt auf `max-width:1280px` begrenzt. Keine halbleeren Rasterzeilen.
- **Marke** oben links: Kachel 30 px in `--accent`, ein Buchstabe, daneben
  Name und Einordnung in Monospace-Versalien. Ein Klick führt zur Übersicht.
- **Kennzahl:** Label, Wert, Einheit daneben (kleiner, eigenes Element),
  darunter eine Monospace-Zeile mit Herkunft.
- **Desktop:** Sidebar 248 px, Kopf mit Titel und Kontextzeile, rechts der
  Primärknopf und der Anzeigename (Verweis auf die Einstellungen).
  **Handy:** Kopf mit kleiner Marke, Tabbar mit 4 Einträgen, der letzte
  „Einstellungen“.

## 4. Einstellungen

Unter `/einstellungen`: Darstellung (System / Hell / Dunkel – **pro Nutzer in
der Datenbank**), dann Konto (nur zur Anzeige) mit „Abmelden / neu laden“
nach `/outpost.goauthentik.io/sign_out`.

## 5. Sprache

Deutsch, sachlich. **Oberfläche und Meldungen mit echten Umlauten.**
Befehle bleiben, wie man sie tippt (`prolo backup pruefen`). Zahlen deutsch
(`19,3 MB`, `01.10. 03:30`).

**Fehlermeldungen sagen, was zu tun ist** – und nennen den Befehl, der es
erledigt, nicht die Aufgabe. Eine Meldung, die einen Weg nennt, nennt auch
das Hindernis darauf. Sie verschweigt nicht die Ursache, die sie in der Hand
hatte (keine `2>/dev/null` über einem Fehlschlag), und sie sagt **weil**,
wenn sie Ursache und Wirkung beide kennt. Und was nichts zu sagen hat, sagt
nichts – dieselbe Warnung jede Nacht ist Tapete.

## 6. Bedienbarkeit (nicht verhandelbar)

- Pflichtblock: `[hidden]{display:none!important}` vor allen
  `display`-Regeln, sichtbarer Fokusrahmen, keine Animation bei
  Bewegungsreduzierung.
- **Klickflächen mindestens 44 × 44 px**, ab 360 px ohne seitliches Scrollen,
  `env(safe-area-inset-bottom)`.
- `<label for>` an jedem Feld. Kein reines Icon ohne Text.
- Jede Aktion bestätigt sich sichtbar; Knöpfe sind während der Absendung
  gesperrt; Fehler im Formular lassen die Eingaben stehen.
- Was zerstört (Entfernen, Zurückholen), fragt vorher – und sichert vorher.

---

# TEIL II – ROBUSTHEIT

## 7. Eingaben sind grundsätzlich falsch

Jede Eingabe von außen – Formular, Auftrag, Compose-Datei, Kopfzeile – wird
geprüft, bevor sie irgendwo landet. Befehle gehen **als Liste** an
`subprocess`, **nie durch eine Shell**. Was aus dem Container der Admin-Seite
kommt, ist fremde Eingabe: er könnte übernommen sein.

**Keine stillen Vorgabewerte.** Fehlt ein Wert, wird das gemeldet – nicht
geraten (`env_fuellen` fragt nach, statt eine Variable leer zu lassen).

## 8. Fehler dürfen nichts kaputt machen

- **Kein halber Zustand.** Ein Tool, das nicht hochkommt, wird ganz wieder
  weggeräumt (Ordner, Volumes, Netz). Eine Sicherung entsteht als
  `.laufend-*` und wird erst am Ende umbenannt. Dateien: erst daneben
  schreiben, dann umbenennen.
- **Erst prüfen, dann anfassen.** Eine Wiederherstellung liest den Stand
  vollständig, bevor sie etwas ersetzt – und sichert den jetzigen Stand
  vorher.
- Ein Werkzeug, das eigene Arbeit überschreiben könnte, tut nichts und sagt
  warum (`prolo update` bei Änderungen von Hand).
- Netzwerkfehler sind keine Katastrophe: nicht erreichbares Docker Hub heißt
  „mit dem Vorhandenen weiter“ und eine Warnung, kein Abbruch.

## 9. Datenverlust ist die einzige echte Katastrophe

- **Eine Sicherung gilt erst, wenn sie wieder gelesen wurde** – jedes Stück
  entschlüsselt und vollständig durch `tar` geprüft.
- Datenbanken werden **angehalten** gesichert, nie im Lauf kopiert.
- Was ein Tool außerhalb seines Ordners einhängt, wird nicht gesichert – und
  das wird **gesagt**, nicht verschwiegen.
- Vor Update, Entfernen und Zurückholen wird gesichert. Ohne vollständige
  Sicherung kein nächtliches Update.
- Löschen fragt nach.

---

# TEIL III – BETRIEB

## 10. Die Orte

| Ort | Inhalt | gehört |
|---|---|---|
| `/opt/prolo` | dieses Repository | Git – `prolo update` |
| `/etc/prolo` | `prolo.conf`, `geheim.env`, `backup.key/.pub` | root, 0700 |
| `/var/lib/prolo` | Zertifikate, Traefik-Dateien, Auftragsbuch | root |
| `/opt/tools/<name>` | je Tool ein Ordner | root, 0700 |
| `/opt/backup` | Sicherungen | root, 0700 |

**Im Repository liegt nichts, was den Server ausmacht** – keine Einstellung,
kein Geheimnis, kein Tool. Darum lässt es sich jederzeit neu klonen.
Geheimnisse, Werte aus `.env` und Schlüssel nie in Git, nie in einen Chat,
nie in ein Protokoll (auch nicht das Erst-Passwort nach dem ersten Lauf).

## 11. Was `prolo einrichten` tut

Jeder Schritt sieht erst nach, ob er nötig ist – der Befehl läuft beliebig
oft, beim zweiten Mal passiert nichts Neues, und nichts Vorhandenes wird
überschrieben. **Wer einen Einrichtungsschritt braucht, ergänzt ihn dort**,
nicht in einer Anleitung zum Abtippen. `install.sh` installiert nur Pakete,
Firewall und Systemupdates und ruft dann `prolo einrichten`.

## 12. Der Unterbau

- **Ein Compose-Projekt** `prolo`. Aufgerufen nur über `prolo` (setzt die
  Werte aus `/etc/prolo` ein und hängt `unterbau-netze.yml` an); von Hand:
  `prolo compose …`.
- **Nur Traefik hat Ports.** Er sieht Docker nur lesend über `socket-proxy`.
- Am Eingang, für **jeden** Router: Ratenbremse, Löschen der
  `X-authentik-*`-Kopfzeilen, Sicherheitskopfzeilen. Die Liste der gelöschten
  Kopfzeilen muss alle `authResponseHeaders` enthalten (Test).
- **Authentik** schützt per Blueprint (`authentik/blueprints/`) die ganze
  Domain mit einem Provider im Domain-Modus – ein neues Tool braucht in
  Authentik nichts. `einrichten` wendet den Blueprint ausdrücklich an und
  prüft danach, ob er wirkt.
- **Die Admin-Seite hat keinen Zugriff auf Docker.** Sie legt Aufträge in
  `/var/lib/prolo/agent/ein` ab; der Agent (`prolo agent`, systemd) prüft sie
  mit `kern/auftrag.py` und führt sie über `prolo` aus. Was dort nicht
  erlaubt ist, geht von der Seite nicht.
- Jeder Dienst: `mem_limit`, `pids_limit`, `no-new-privileges`,
  `cap_drop: ALL` (zurück nur, was nötig ist: Traefik `NET_BIND_SERVICE`,
  Postgres die fünf fürs Starten), `restart: unless-stopped`,
  Protokolldrehung. Ein Dienst, der PID 1 ist, beendet sich auf SIGTERM.
- **Nur IPv4 lauschen** (`0.0.0.0`): auf Kernen mit `ipv6.disable=1` startet
  sonst nichts.
- Abbilder auf **Nebenfassung** festgelegt (`traefik:v3.6`) – Fehlerbehebungen
  kommen nachts von selbst; ein Sprung auf eine neue Neben- oder Hauptfassung
  nur per Commit. Nie mehrere Hauptfassungen einer Datenbank auf einmal.
- Die Fassungsnummer steht **nur** in `VERSION`.

## 13. Tools

- Ein Tool ist `/opt/tools/<name>/` mit `app/` (Herstellerdatei oder git
  clone, **unverändert**), `prolo.conf` und `prolo.override.yml` (von prolo
  erzeugt). Was gilt, ist `docker compose config` beider Dateien zusammen.
- **Jedes Tool in seinem eigenen Netz** `tool-<name>`; nur Traefik hängt
  zusätzlich darin. Der Hauptdienst behält seine bisherigen Netze (sonst
  findet er seine Datenbank nicht).
- **Keine Ports** (`ports: !reset []`), **Anmeldung als Vorgabe**,
  benannte Volumes für jedes `VOLUME` des Abbilds.
- Gefahren (`privileged`, Socket, Host-Pfade, `network_mode`, `cap_add`,
  Geräte …) legt die Admin-Seite **nie** an; auf der Kommandozeile fragt
  prolo nach.

## 14. Sicherung und Wiederherstellung

So, für jedes Tool und den Unterbau gleich: **anhalten → packen → mit `age`
verschlüsseln → wieder starten → jedes Stück lesen**. Ein Stand ist ein
Ordner mit `MANIFEST.json` (Prüfsummen). Aufbewahrt wird `BACKUP_TAGE`, die
drei neuesten vollständigen immer. Der geheime Schlüssel liegt auf dem
Server (für das Prüfen und Zurückholen) **und** gehört in den
Passwortmanager; bei einem Umzug wird er mitgebracht (`--schluessel`), damit
es bei **einem** Schlüssel bleibt.

**Die Wiederherstellung wird geübt** – `tests/durchlauf.py` tut es bei jedem
Push: Tool, entferntes Tool und Unterbau, mit Prüfung des Inhalts.

## 15. Update

`prolo update`: Änderungen von Hand → anhalten. Neue Commits → sichern,
`git merge --ff-only`, **mit dem neuen Code neu starten** (`einrichten
--nach-update`), Ergebnis in `/var/lib/prolo/update.json`. Keine neuen
Commits → neue Abbilder holen, nur bei Änderung sichern und neu starten.
Der Agent lädt neuen Code, indem er sich selbst neu startet, sobald er
nichts zu tun hat – ein Neustart von außen bräche den laufenden Auftrag ab.

---

# TEIL IV – CHECKLISTE

- [ ] Ein Befund, ein Commit, Nummer in der ersten Zeile, Zahlen im Text
- [ ] `tests/alle.sh` grün, als normaler Nutzer, ohne Pipe gelesen
- [ ] neue Prüfung → Eintrag in `tests/gegenprobe.py`, der rot wird
- [ ] Kern/Compose geändert → `sudo python3 tests/durchlauf.py` grün
- [ ] Admin-Seite geändert → im Browser hinter der Anmeldung, 3 Breiten,
      2 Themen, Kontrast und Klickflächen gemessen, Bilder angesehen
- [ ] Meldungen sagen, was zu tun ist – mit dem Befehl
- [ ] nichts Schützenswertes in Git, Chat oder Protokoll
- [ ] `README.md` passt noch zu dem, was der Code tut
