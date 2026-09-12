# Bordbuch

Ein Bordbuch für deine Fahrzeuge, das auf einem Raspberry Pi im Heimnetz läuft:
Ladungen, Tankungen, Wartungen und Werkstattkosten für mehrere Autos und mehrere
Personen im Haushalt — mit Auswertungen, Berichten und Nachweisen für Arbeitgeber
oder Finanzamt.

> **Früher hieß dieses Tool „Ladelog".** Der Name passte nicht mehr, seit auch
> Tankungen, Wartungen und Werkstattkosten dazugekommen sind. Beim Update bleiben
> deine Daten erhalten — siehe *Umstieg von Ladelog*.

Zwei Dateien, kein Installationsaufwand, keine Fremdpakete, kein Internetzugang
für den Betrieb. Es genügt Python 3.9, das auf jedem Raspberry Pi OS dabei ist.

**Diese Anleitung in einem Satz:** Dateien auf den Pi kopieren, Dienst einrichten,
im Browser aufrufen — der Rest erklärt sich in der Oberfläche selbst.

---

## Inhalt

**Teil 1 — Einrichten**
Schnellstart · Testen ohne Installation · Was du brauchst · Dateien auf den Pi bringen ·
Bedienung im Alltag · Auf dem Handy wie eine App · Umstieg von Ladelog ·
Aktualisieren · Sicherung · Wichtig zur Sicherheit · Startbefehl im Detail

**Teil 2 — Benutzen**
Bedienung · Erfassen · Warum langsames Heimladen nicht gemeldet wird ·
Ladepunkte einordnen · Abrechnung für Arbeitgeber oder Finanzamt ·
Wartung & Service · Logbuch · Kosten & Rechnungen ·
Wenn sich der Verbrauch verändert · Viele Daten auf einmal ·
Sicherung in der Oberfläche · Verwaltung · Bekannte Grenzen · Befehle

---

# Teil 1 — Einrichten

## Schnellstart

Wenn du dich auf dem Pi auskennst, genügt das:

```bash
sudo mkdir -p /opt/bordbuch
sudo cp server.py index.html /opt/bordbuch/
sudo cp bordbuch.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now bordbuch
```

Dann `http://raspberrypi.local:8080` öffnen. Alles Weitere steht unten.

## Testen ohne Installation

Die Datei **`bordbuch-demo.html`** öffnest du mit einem Doppelklick in jedem
Browser. Sie bringt Beispieldaten mit (drei Fahrzeuge, mehrere Jahre Historie),
speichert nur im Browser und braucht keinen Server. Ideal, um vorher zu sehen,
worauf du dich einlässt. Unter *Einstellungen → Verwaltung* kannst du die
Beispieldaten jederzeit zurücksetzen.

---

## Was du brauchst

* Raspberry Pi (jedes Modell ab Pi 2 genügt; das Tool ist winzig)
* Raspberry Pi OS, per SSH erreichbar oder mit Tastatur und Bildschirm
* Die drei Dateien: `server.py`, `index.html`, `bordbuch.service`

Prüfe zuerst die Python-Version:

```bash
python3 --version
```

Steht dort `3.9` oder höher, kann es losgehen.

---

## Schritt 1 — Dateien auf den Pi bringen

Vom eigenen Rechner aus, im Ordner mit den entpackten Dateien:

```bash
scp server.py index.html bordbuch.service pi@raspberrypi.local:/tmp/
```

Klappt der Name `raspberrypi.local` nicht, nimm die IP-Adresse des Pi, zum Beispiel
`pi@192.168.178.42`. Die findest du im Router oder auf dem Pi selbst mit
`hostname -I`.

Falls du am Pi direkt sitzt, kopiere die Dateien einfach per USB-Stick oder
Dateimanager nach `/tmp`.

---

## Schritt 2 — Ins Zielverzeichnis legen

Jetzt auf dem Pi (per SSH einloggen mit `ssh pi@raspberrypi.local`):

```bash
sudo mkdir -p /opt/bordbuch
sudo mv /tmp/server.py /tmp/index.html /opt/bordbuch/
sudo chown -R pi:pi /opt/bordbuch
```

`/opt/bordbuch` ist der Ort, den die mitgelieferte Dienstdatei erwartet. Ein anderer
Pfad geht auch — dann musst du ihn in Schritt 4 anpassen.

---

## Schritt 3 — Erster Probelauf

```bash
cd /opt/bordbuch
python3 server.py --port 8080
```

Es erscheinen zwei Zeilen:

```
Bordbuch (Stand 4) laeuft auf http://0.0.0.0:8080
Datenbank: /opt/bordbuch/bordbuch.db
```

Öffne nun am Handy oder Rechner im gleichen Netz:

```
http://raspberrypi.local:8080
```

Ohne die vorgeschaltete Anmeldung erscheint „Nicht angemeldet" — das ist beim
Probelauf ohne Proxy richtig so. Beende den Probelauf danach
mit `Strg + C`.

**Kommt nichts?** Dann prüfe der Reihe nach:

| Problem | Ursache und Abhilfe |
|---|---|
| Seite lädt nicht | Falsche Adresse. Nimm `hostname -I` auf dem Pi und dann `http://<IP>:8080` |
| `Address already in use` | Der Port ist belegt. Nimm einen anderen: `--port 8090` |
| `python3: command not found` | Python fehlt: `sudo apt update && sudo apt install python3` |
| Seite lädt, aber leer | `index.html` liegt nicht neben `server.py`. Beide müssen im selben Ordner sein |

---

## Schritt 4 — Als Dienst dauerhaft einrichten

Damit Bordbuch nach jedem Neustart von allein läuft:

```bash
sudo cp /tmp/bordbuch.service /etc/systemd/system/
sudo nano /etc/systemd/system/bordbuch.service
```

Prüfe im Editor die drei Zeilen `User=`, `Group=` und `WorkingDirectory=`. Heißt dein
Benutzer nicht `pi`, trage deinen Namen ein (`whoami` zeigt ihn). Speichern mit
`Strg + O`, `Enter`, schließen mit `Strg + X`.

Dann starten und dauerhaft aktivieren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bordbuch
systemctl status bordbuch
```

Bei `active (running)` läuft alles. Verlasse die Statusanzeige mit `q`.

---

## Bedienung im Alltag

| Zweck | Befehl |
|---|---|
| Läuft der Dienst? | `systemctl status bordbuch` |
| Neu starten | `sudo systemctl restart bordbuch` |
| Anhalten | `sudo systemctl stop bordbuch` |
| Mitlesen, was passiert | `journalctl -u bordbuch -f` |

---

## Auf dem Handy wie eine App

Bordbuch ist auf Handybedienung ausgelegt — große Felder, Zifferntastatur, Kamera für
den Beleg. Damit es sich wie eine App anfühlt:

* **iPhone (Safari):** Seite öffnen → Teilen-Symbol → *Zum Home-Bildschirm*
* **Android (Chrome):** Seite öffnen → Menü ⋮ → *Zum Startbildschirm hinzufügen*

Danach startet Bordbuch mit einem Tippen, ohne Adressleiste. Das funktioniert nur im
Heimnetz — unterwegs ist der Pi nicht erreichbar.

---

## Umstieg von Ladelog

Das Tool hieß früher Ladelog. Beim Update ändert sich nur der Name:

```bash
sudo systemctl stop ladelog
sudo cp /tmp/server.py /tmp/index.html /opt/ladelog/
sudo systemctl start ladelog
```

Das genügt — deine `ladelog.db` wird weiter benutzt (Bordbuch sucht sie
ausdrücklich, wenn keine `bordbuch.db` existiert), und der alte Dienstname
funktioniert unverändert weiter.

Wer auch die Verzeichnisse umbenennen möchte:

```bash
sudo systemctl stop ladelog && sudo systemctl disable ladelog
sudo mv /opt/ladelog /opt/bordbuch
sudo rm /etc/systemd/system/ladelog.service
sudo cp bordbuch.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now bordbuch
```

Die Datenbankdatei darf dabei `ladelog.db` heißen bleiben.

## Aktualisieren

Neue Fassung einspielen, ohne Daten zu verlieren:

```bash
sudo systemctl stop bordbuch
sudo cp /tmp/server.py /tmp/index.html /opt/bordbuch/
sudo systemctl start bordbuch
journalctl -u bordbuch -n 20
```

Die Datenbank wird beim Start automatisch um neue Felder ergänzt; deine Ladungen,
Tankungen und Einstellungen bleiben. Was ergänzt wurde, steht im Log — bei einer
frisch angelegten Datenbank bleibt es still. Mach vorher trotzdem die Sicherung aus
dem Abschnitt oben; das kostet zehn Sekunden.

---

## Sicherung

Am schnellsten geht es in der Oberfläche: *Einstellungen → Verwaltung →
**Ganze Datenbank sichern*** zieht jedes Profil mit allen Fahrzeugen, Ladungen,
Tankungen und Einstellungen in eine Datei. Nur die Belegbilder fehlen darin.

Vollständig und ohne Browser geht es so — zwei Dinge enthalten alles, was dir gehört:

```bash
cd /opt/bordbuch
tar czf ~/bordbuch-sicherung-$(date +%F).tar.gz bordbuch.db receipts
```

Diese Datei irgendwohin kopieren, wo sie den Ausfall der SD-Karte übersteht.
Zusätzlich kannst du in der Oberfläche unter *Einstellungen → Sicherung
herunterladen* eine JSON-Datei ziehen — die lässt sich in jedes Profil
zurückspielen, auch auf einem anderen Pi.

Wiederherstellen ist ein Kopiervorgang:

```bash
sudo systemctl stop bordbuch
cd /opt/bordbuch && tar xzf ~/bordbuch-sicherung-2026-08-26.tar.gz
sudo systemctl start bordbuch
```

### Automatische Sicherung (systemd-Timer)

Damit die Sicherung nicht von deiner Erinnerung abhaengt, kann Bordbuch sie
taeglich selbst anlegen. Der Server kennt dafuer einen eigenen Aufruf, der eine
saubere Kopie der Datenbank zieht -- auch waehrend er laeuft -- und die letzten
14 Sicherungen unter `/opt/bordbuch/backups/` behaelt:

```bash
# Einmal von Hand testen:
cd /opt/bordbuch && python3 server.py --backup
```

Fuer den taeglichen Lauf liegen im Paket zwei Dateien bereit. Einrichten:

```bash
sudo cp bordbuch-backup.service bordbuch-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bordbuch-backup.timer
```

Der Timer stoesst die Sicherung jede Nacht um 3:30 Uhr an; war der Pi dann aus,
wird sie beim naechsten Start nachgeholt. Wie viele Sicherungen behalten werden,
steuerst du mit `--backup-keep` (z. B. `--backup-keep 30`) in der Zeile
`ExecStart=` der Datei `bordbuch-backup.service`. Wann zuletzt gesichert wurde,
zeigt die Oberflaeche unter *Einstellungen -> Daten -> Automatische Sicherung*.

Ob der Timer laeuft und wann er das naechste Mal faellig ist:

```bash
systemctl status bordbuch-backup.timer
systemctl list-timers bordbuch-backup.timer
```

---

## Wichtig zur Sicherheit

**Die Anmeldung passiert vor Bordbuch.** Bordbuch fragt kein Passwort und legt
keine Benutzer an — wer hinein darf, entscheidet eine vorgeschaltete
Anmeldung (Authentik o. ä.) hinter einem Reverse Proxy. Bordbuch liest bei jeder
Anfrage diese Köpfe und legt beim ersten Besuch automatisch ein Profil an:

| Kopf | wofür |
|---|---|
| `X-Authentik-Username` | der Schlüssel zum Profil — ohne ihn keine Anfrage |
| `X-Authentik-Name` | Anzeigename; fehlt er, gilt der Anmeldename |
| `X-Authentik-Email` | nur zur Anzeige |
| `X-Authentik-Groups` | kommagetrennt, entscheidet über die Gesamtsicherung |

Groß- und Kleinschreibung spielt dabei keine Rolle.

**Abmelden** steht oben rechts. Der Knopf führt zu
`/outpost.goauthentik.io/sign_out` — die Sitzung liegt bei der Anmeldung davor,
nicht in Bordbuch; Kekse hier zu löschen würde nichts bringen. Ein anderer Pfad
geht mit `--abmelde-pfad`, ein leerer Wert blendet den Knopf aus. Wer gerade
angemeldet ist, steht immer in der Kopfzeile — wichtig beim Wechsel zwischen
Konten.

**Im Container** ist `0.0.0.0` dagegen richtig — erreichbar ist der Dienst dann
nur über das gemeinsame Docker-Netz. Bedingung: im Compose-File darf **keine
`ports:`-Zeile** stehen, sonst wären die Anmeldeköpfe von außen fälschbar.
Bordbuch erkennt den Container und sagt das beim Start noch einmal.

**Ohne Container lauscht Bordbuch ab Fassung 2.0 nur noch auf `127.0.0.1`.** Das ist keine
Schikane: Wäre der Server direkt im Netz erreichbar, könnte jeder diesen Kopf
selbst setzen und sich als beliebige Person ausgeben — das wäre schlechter als
gar keine Anmeldung, weil es Sicherheit vortäuscht. Der Server weigert sich
deshalb, auf einer offenen Adresse zu starten, und sagt das beim Start auch.
Ist der Zugang anders abgesichert, geht es mit `--header-vertrauen` trotzdem.

Jedes Profil sieht nur seine eigenen Daten. Wer jemandem Einblick geben will,
macht das selbst unter *Einstellungen → Profil → Meine Freigaben* — wahlweise
nur lesen oder auch eintragen. Niemand kann sich selbst Zugriff auf ein fremdes
Profil verschaffen.

*Einstellungen → Verwaltung → Alles sichern* (`/api/admin/export`) liegt jetzt
hinter einer Gruppe: nur wer in `X-authentik-groups` die Gruppe
`bordbuch-admin` mitbringt, sieht sie. Der Gruppenname lässt sich mit
`--admin-gruppe` ändern.

**Stelle den Pi nicht ins offene Internet.** Kein Portforwarding im Router, keine
öffentliche Domain. Willst du von außen ran, nimm ein VPN (WireGuard oder Tailscale)
— dann bist du von unterwegs im Heimnetz und Bordbuch bleibt geschützt.

Soll auch im Heimnetz ein Passwort davor, setze einen Reverse Proxy mit Basic Auth
davor, zum Beispiel Caddy:

```
bordbuch.fritz.box {
    basicauth { papa <passwort-hash> }
    reverse_proxy localhost:8080
}
```

---

## Startbefehl im Detail

```bash
python3 server.py --port 8080 --db bordbuch.db --host 0.0.0.0 --verbose
```

| Option | Standard | Bedeutung |
|---|---|---|
| `--port` | 8080 | Port, auf dem Bordbuch hört |
| `--db` | `bordbuch.db` neben `server.py` | Ort der Datenbankdatei |
| `--host` | `0.0.0.0` | Auf allen Netzwerkkarten erreichbar. `127.0.0.1` beschränkt auf den Pi selbst |
| `--verbose` | aus | Schreibt jede Anfrage ins Log — nützlich bei der Fehlersuche |


---

# Teil 2 — Benutzen


## Bedienung

Wer du bist, weiß Bordbuch schon — das sagt die Anmeldung davor. Jedes Profil hat
eigene Autos und Daten; ist dir eines freigegeben, kannst du oben rechts umschalten.
Oben rechts wählst du das **Auto** — und ab da zeigt jede Ansicht genau dieses
Fahrzeug. Beim Benziner fällt alles Elektrische weg, beim Hybrid siehst du zuerst
die Summe und darunter die Aufteilung in Strom und Sprit.

| Tab | Inhalt |
|---|---|
| Übersicht | Ausgaben, Strecke, Kosten je 100 km, Auffälligkeiten; darunter die Bausteine Strom und/oder Sprit, Verlauf und Monatsprognose |
| Ladungen | Liste, Erfassung, Ändern und Löschen — nur bei Elektro und Hybrid |
| Tankungen | Liste, Erfassung, Ändern und Löschen — nur bei Hybrid, Benzin und Diesel |
| Fahrzeug | Steckbrief ohne Euro-Beträge: Kilometerstand, Verbrauch, Reichweite, Laufleistung, Fahrprofil |
| Auffälligkeiten | Was aus der Reihe fällt — teure Preise, hoher Verbrauch, unmögliche Kilometerstände, fällige Wartungen, veränderter Verbrauch |
| Wartung | **Was ansteht** (mit Vorhersage und Farbstufen), **Logbuch** (was wann gemacht wurde) und **Kosten & Rechnungen** (nach Jahr abrufbar) |
| Preise | Preis je Anbieter (getrennt nach Ladeart) oder Tankstelle, Preisentwicklung, Ladeleistung, Verbrauch je Tankfüllung |
| Verlauf | Woche für Woche (Pfeiltasten ← →), die letzten zwölf Wochen, Jahresvergleich |
| Bericht | Zwei Modi: **Kostenaufstellung** (Monat oder Jahr, Netto/MwSt/Brutto, Excel, CSV, Rechnungsabgleich) und **Abrechnung** (Mengennachweis für Arbeitgeber oder Finanzamt) |
| Einstellungen | Unterpunkte: **Fahrzeuge bearbeiten** (pflegen und vergleichen), **Ladepunkte** (mit Suche einordnen), **Tarife** (Heimstrompreis, Vergleichspreis, Standardverbrauch), **Warnungen**, **Daten** (Import und Sicherung), **Profil**, **Verwaltung** |

### Erfassen — Laden und Tanken gleich aufgebaut

Beide Listen haben denselben Knopf **＋ erfassen** (am Handy unten rechts). Er öffnet
sofort das Formular. Die Felder sind als Fragen formuliert, mit einer Erklärung
darunter — „Was hast du bezahlt?", „Wie viel steht auf dem Tacho?" und so weiter.
Ladung und Tankung folgen derselben Reihenfolge: Datum, Uhrzeit, Betrag, Menge,
Kilometerstand, Ort.

Oben im Formular sitzen die Füllknöpfe:

* **📄 Datei einlesen und prüfen** — eine Datei auswählen, die Felder füllen sich
  selbst, du siehst die Werte und speicherst. Enthält die Datei mehrere Vorgänge,
  wechselt Bordbuch von selbst auf die Prüfliste und übernimmt alle zusammen.
  Passt die Datei nicht zum Formular — hast du beim Hybrid also auf dem
  Ladeformular eine Tankliste erwischt —, merkt Bordbuch das, sagt es dir und
  bringt dich zur richtigen Stelle. Verklicken kostet dich also nichts.
* **Mehrere Dateien ohne Einzelprüfung** — für den Erstbestand: alles zusammen
  einlesen, ohne jeden Vorgang anzusehen.
* **📷 Beleg fotografieren** (nur beim Tanken) — hängt den Kassenbeleg als Nachweis
  an den Eintrag. Die Zahlen liest das Tool **nicht** aus dem Bild; Betrag und Liter
  tippst du selbst. Texterkennung bräuchte eine externe Bibliothek und damit
  Internet — das passt nicht zu einem Tool, das offline im Heimnetz läuft.

Lässt du bei einer Ladung das Kostenfeld leer, rechnet Bordbuch mit deinem
Heimstrompreis.

Jeder Eintrag lässt sich später **ändern** oder **löschen** — auch importierte
Ladungen. In der Liste stehen die Knöpfe unter jeder Zeile, im Änderungsformular
sitzt der Löschknopf mit dabei.

Trage bei jeder Volltankung den **Kilometerstand** ein — nur so kennt Bordbuch den
echten Verbrauch statt eines Schätzwerts. Vertippst du dich, wird die Tankung
markiert („Kilometerstand rückwärts" oder „Kilometerstand prüfen") und der Abschnitt
aus der Rechnung herausgehalten, damit ein Zahlendreher nicht den Schnitt verdirbt.
Sprünge über 5.000 km zwischen zwei Ablesungen fallen ebenfalls heraus — und werden
in den Auffälligkeiten gemeldet, damit du sie nachsehen kannst.

**Teilbetankungen darfst du erfassen.** Gerechnet wird nur zwischen zwei
Volltankungen mit Kilometerstand; alles, was dazwischen getankt wurde, zählt mit.
Beginnt deine Reihe mit einer Teilbetankung, wird dieser erste Abschnitt nicht
gerechnet — niemand weiß, wie voll der Tank vorher war.

**Beim Plug-in-Hybrid** weist Bordbuch **keinen gemessenen Verbrauch** aus. Die
Rechnung „Menge geteilt durch Tachostrecke" setzt voraus, dass alle Kilometer mit
dieser einen Energieart gefahren wurden — beim Hybrid stimmt das nie. Ohne Ladestand
lässt sich der Anteil nicht trennen. Stattdessen zeigt der Reiter *Fahrzeug*, was
auch dort stimmt: Strecke, Kosten je 100 km und die Mengen bezogen auf die gesamte
Strecke, ausdrücklich als „keine Verbrauchsangabe" gekennzeichnet.

### Warum langsames Heimladen nicht gemeldet wird

Die Schwellen „wenig Leistung" und „sehr lange angesteckt" gelten **nur für
öffentliche Ladepunkte** — dort drohen Blockiergebühren oder ein abgebrochener
Vorgang. Zuhause und beim Arbeitgeber ist langsames Laden über viele Stunden der
Normalfall: ein Schuko-Kabel liefert 2 kW über Nacht, das ist kein Fehler. Ordne
deinen Ladepunkt darum als „Zuhause" ein — dann rechnet Bordbuch auch mit deinem
Strompreis.

### Ladepunkte einordnen

Unter Einstellungen jeden Ladepunkt auf **Zuhause**, **Arbeit** oder **Unterwegs**
stellen. Heimladungen werden dann mit deinem Strompreis bewertet (im Bericht mit
`*` markiert), und die Übersicht zeigt, was das Laden unterwegs zusätzlich kostet.

### Abrechnung für Arbeitgeber oder Finanzamt

Im Reiter *Bericht* auf **Abrechnung** umschalten. Die Seite ist ein
**Mengennachweis**: wie viele Kilowattstunden wann und wo geladen wurden. Seit dem
1. Januar 2026 gibt es für Heimladestrom keine Monatspauschale mehr — erstattet wird
die nachgewiesene Menge.

Wählbar sind Zeitraum (Monat oder ganzes Jahr) und Ort: **Zuhause** (der übliche Fall
für den Arbeitgeber), **Unterwegs** (Reisekosten) oder alles. Die Seite zeigt zuerst
die Gesamtmenge, dann zwei Rechenwege nebeneinander — tatsächliche Kosten und Menge
mal einem Satz je kWh —, danach die Einzelaufstellung mit Kilometerstand und
Rechnungsnummer. Jede Zeile ist als **gemessen** oder **gerechnet** gekennzeichnet;
gerechnet heißt, der Betrag kommt aus deinem Heimstrompreis und ist kein
Kostennachweis. Die Kilowattstunden sind davon unberührt.

Den **Satz je kWh** trägst du unter *Einstellungen → Tarife* ein, mit Jahr und
Quelle. Bordbuch schlägt dort bewusst keinen Wert vor: er ändert sich jährlich, und
eine falsche Zahl im Programm wäre schlimmer als ein leeres Feld. Was in deinem Fall
gilt, sagen Arbeitgeber, Lohnbüro oder Steuerberater — Bordbuch ist keine
Steuerberatung.

**Netto und MwSt:** Weist eine Abrechnung kein Netto aus, leitet Bordbuch es aus dem
Bruttobetrag ab — mit dem Satz aus *Einstellungen → Tarife* (voreingestellt 19 %,
im Ausland anders: Österreich 20, Polen 23, Luxemburg 17). In Bericht und Abrechnung
steht dann in der Fußzeile, bei wie vielen Posten der Wert abgeleitet und nicht
ausgewiesen ist.

Ausgabe über „Blatt drucken (PDF)" oder als CSV fürs Lohnbüro.

## Wartung & Service

Im Reiter **Wartung** trägst du je Fahrzeug ein, was regelmäßig fällig wird.
**Kilometer und Zeit dürfen beide angegeben werden** — fällig wird, was zuerst
eintritt. Wer wenig fährt, erreicht die Kilometer nie, braucht das Öl aber
trotzdem; wer viel fährt, umgekehrt. Für die Hauptuntersuchung genügt der Monat
von der Plakette, ein Kilometerintervall gibt es dort nicht.

Vorschläge zum Antippen gibt es für HU, Ölwechsel, Inspektion, Reifenwechsel,
Bremsflüssigkeit, Klimaservice, Zahnriemen und Bremsen. **Werte schlägt Bordbuch
bewusst nicht vor** — Intervalle unterscheiden sich je Hersteller, Motor und Öl
erheblich. Die richtigen Zahlen stehen im Serviceheft.

Aus deinen Kilometerständen rechnet Bordbuch die Fahrleistung je Tag und daraus
ein Datum: *„Ölwechsel — noch 4 200 km, voraussichtlich Mitte November, bei 38 km
am Tag."* Reichen die Ablesungen nicht (weniger als drei über einen Monat), bleibt
es bei den Kilometern; ein erfundenes Datum wäre schlimmer als keines.

Die Ansicht *Was ansteht* zeigt drei Stufen mit Farbe: **rot** überschritten,
**gelb** bald fällig (unter 10 % des Intervalls oder unter vier Wochen), darunter
**Später — der ganze Plan**, nach Termin sortiert. So bleibt auch eine Fälligkeit in
zwei Jahren im Blick. Ist nichts fällig, gibt es kein Abzeichen am Reiter; Fälliges
erscheint zusätzlich unter *Auffälligkeiten*.

### Einmal anlegen, nie wieder

TÜV und Ölwechsel legst du **genau einmal** an. **Als erledigt eintragen** öffnet ein
kurzes Formular — Datum, Kosten, Werkstatt, Kilometerstand (nur wo er zählt), Notiz
und Beleg. Danach stellt sich der Eintrag selbst weiter: aus dem Intervall ergibt
sich der nächste Termin, eine feste Fälligkeit wie die HU rückt um das Intervall
vor. Bei der HU steht der **Preis** im Vordergrund, nicht der Tachostand — dort sagt
er nichts aus.

### Logbuch

Jeder Erledigt-Vermerk landet automatisch im **Logbuch**, gruppiert nach Art, mit
Summe und erkanntem Rhythmus:

```
Hauptuntersuchung (HU/TÜV)   3×   etwa alle 24 Monate   414,20 €
  18.03.2027   138,50 €   TÜV Süd
  09.03.2025   141,20 €   83.400 km · Bremsleitung bemängelt
  14.03.2023   134,50 €   71.200 km · ohne Mängel
```

Eine von Hand erfasste Rechnung kannst du im Formular einer Wartung **zuordnen** —
dann steht sie in derselben Gruppe, auch wenn sie anders heißt.

### Kosten & Rechnungen

Rechnungen trägst du mit Foto oder PDF ein, wie den Tankbeleg. Oben wählst du das
**Jahr** (mit Summe in der Auswahl), und die Seite zeigt nur dieses Jahr: Summe,
Kosten je 100 km, Aufteilung nach Art der Arbeit, ein weißes Blatt zum Drucken und
ein CSV. Genau das, was man braucht, um Ausgaben eines vergangenen Jahres zu
belegen. Eine Kachel nennt zusätzlich, was das Fahrzeug **insgesamt** je 100 km
kostet — Energie plus Werkstatt.

## Wenn sich der Verbrauch verändert

Weicht der gemessene Verbrauch dauerhaft um mehr als 5 % vom eingetragenen Wert
ab (bei mindestens drei gemessenen Abschnitten), meldet sich Bordbuch unter
*Auffälligkeiten* — für Strom und Sprit gleichermaßen. Ein Klick auf **Neuen Wert
übernehmen** schreibt ihn ins Fahrzeugprofil, und der Hinweis verschwindet.
**Passt so** blendet ihn aus, bis sich der Verbrauch weiter verändert. Beim
Plug-in-Hybrid gibt es diesen Hinweis nicht — dort ist der Wert nicht messbar.

Gerechnet wird ohnehin immer mit dem gemessenen Wert; das Übernehmen hält nur das
Profil aktuell.

## Viele Daten auf einmal

Für den Erstbestand: **Einstellungen → Alle CSV-Dateien hierher**. Dort darfst du
beliebig viele Dateien gleichzeitig auswählen oder ins Fenster ziehen. Lade- und
Tanklisten werden am Kopf der Datei automatisch unterschieden; Trennzeichen
(Semikolon, Komma, Tabulator) und deutsches Dezimalkomma erkennt Bordbuch selbst.
Denselben Knopf findest du oben in den Listen als „Viele Dateien einlesen".

Erkannt werden **CSV- und XLSX-Dateien**: Abrechnungen von Ladeanbietern, eigene
Bordbuch-Exporte, einfache Tanklisten, das **Ladeprotokoll von openWB** und die
**Tabellenausgabe von Heim-Wallboxen** (getestet mit der VoltBox/„Smart car charger").
XLSX packt Bordbuch mit den Bordmitteln des Browsers aus — keine Zusatzbibliothek.

Bei Wallbox-Ausgaben kommt einiges anders als in einer CSV: die Kopfzeile steht erst
in Zeile 3, das Datum hat Schrägstriche (`2026/08/26 18:36`), die Dauer ist ein Wort
(`11hour15minute`), und ein Betrag fehlt ganz. Bordbuch findet die Kopfzeile selbst,
rechnet die Dauer um, übernimmt den Gerätenamen als Ladepunkt und bildet den Betrag
aus deinem Heimstrompreis. Im Formular steht dann ein Knopf, mit dem du den
Ladepunkt gleich als „Zuhause" einordnest. Die Zuordnung erfolgt immer über die
Spaltenüberschrift, nie über die Position — bei openWB ist die Spaltenauswahl frei
konfigurierbar. Fehlt eine Pflichtspalte, sagt Bordbuch welche, statt stumm nichts zu
finden. Ein Kilometerstand in der Datei wird übernommen.

Passt ein Teil nicht zum gewählten Auto — etwa Ladungen bei einem Benziner —, wird
der passende Teil übernommen und der Rest benannt. Beim Hybrid kommen Ladungen und
Tankungen hintereinander dran. Bereits vorhandene Ladungen erkennt Bordbuch an der
Vorgangsnummer und überspringt sie.

## Sicherung in der Oberfläche

* **Sicherung herunterladen** (*Einstellungen → Daten*) — eine JSON-Datei mit allem:
  Autos, Ladungen, Tankungen, Wartungsplan, Werkstattrechnungen, Einstellungen.
  Die Belegbilder sind nicht enthalten; dafür `receipts/` mitkopieren.
* **Sicherung wiederherstellen** — *Ergänzen* fügt nur Fehlendes hinzu (Autos über
  den Namen zusammengeführt, Wartungen über Auto und Bezeichnung, Ladungen über die
  Vorgangsnummer). *Alles ersetzen* leert das Profil vorher und **fragt vorher nach**,
  mit Angabe der betroffenen Mengen — es ist der einzige Weg, auf dem Daten
  unwiederbringlich verloren gehen können.

Auf dem Pi liegt alles in `bordbuch.db` (oder `ladelog.db`) plus dem Ordner
`receipts/`. Diese beiden wegzukopieren ist die einfachste vollständige Sicherung.

## Verwaltung

Unter *Einstellungen → Verwaltung* greifst du über alle Profile hinweg zu:

* Übersicht aller Profile mit Fahrzeugen, Vorgängen, Ausgaben und Strecke.
* **Bericht** je Profil: alle Fahrzeuge mit Antrieb, Kilometerstand, Verbrauch
  (gemessen oder geschätzt), Kapazität, Reichweite, Mengen und Kosten — als weißes
  Blatt zum Drucken oder Speichern als PDF.
* **CSV** je Profil oder über alle Fahrzeuge, eine Zeile je Fahrzeug mit allen Werten.
* **Ganze Datenbank sichern** als eine JSON-Datei und wieder einspielen, ergänzend
  oder ersetzend. Belegbilder sind darin nicht enthalten — dafür `receipts/` mitkopieren.

Auch die Verwaltung hat **keine eigene Anmeldung**. Wer im Heimnetz ist, kann sie
öffnen. Wer das nicht möchte, setzt den Reverse Proxy mit Basic Auth davor.

## Bekannte Grenzen

* **Bordbuch braucht die vorgeschaltete Anmeldung.** Ohne Reverse Proxy mit
  Forward-Auth ist es nur vom Pi selbst erreichbar (`127.0.0.1`) und zeigt sonst
  „Nicht angemeldet". Benutzer anlegen, umbenennen oder löschen geht nur dort,
  nicht in Bordbuch.
* **Nicht ins Internet stellen.** Der Server ist für das Heimnetz gedacht.
* Belege: jpg, png, webp, heic oder pdf, maximal 8 MB je Beleg.
* XLSX-Import braucht einen aktuellen Browser (Chrome/Edge ab 80, Safari ab 16.4,
  Firefox ab 113). Ältere melden das und verweisen auf den CSV-Export.
* Die Sicherung enthält die Belegdateien nicht, nur deren Namen — dafür den Ordner
  `receipts/` mitkopieren.
* **Beim Plug-in-Hybrid** gibt es keinen gemessenen Verbrauch je Energieart. Dafür
  müsste Bordbuch den Ladestand kennen; aus Tachostand und Menge ist der Anteil
  nicht zu trennen. Die Werte im Fahrzeugprofil sind dort Schätzungen.
* **Die Monatsprognose** erscheint erst ab dem 7. eines Monats — vorher wäre die
  Hochrechnung aus wenigen Tagen Unsinn.
* **Vorhersagen zur Wartung** sind Schätzungen aus deiner Fahrleistung, keine
  Termine. Ohne genügend Kilometerstände (mindestens drei Ablesungen über einen
  Monat) nennt Bordbuch nur die verbleibenden Kilometer und kein Datum.
* **Netto und MwSt** werden aus dem Bruttobetrag abgeleitet, wenn die Abrechnung
  kein Netto ausweist. Der Satz ist einstellbar; wo abgeleitet wurde, steht es
  in der Fußzeile des Dokuments.
* **Texterkennung auf Belegen** gibt es nicht. Das Foto ist der Nachweis, die Zahlen
  tippst du selbst — OCR bräuchte eine externe Bibliothek und damit Internet.
* Der Server gibt nur `index.html` und die Belege heraus. Datenbank und Quelltext
  sind über den Browser nicht erreichbar.
* Schreibende Anfragen von fremden Webseiten werden abgewiesen (Herkunftsprüfung),
  und ein Profil kann nur sich selbst löschen.
* `/api/admin/export` (Gesamtsicherung) verlangt die Gruppe `bordbuch-admin`.
* Eine Freigabe heißt „mitlesen" oder „mitschreiben" — nicht „übernehmen":
  Fahrzeuge anlegen, Einstellungen ändern, sichern und wiederherstellen bleibt
  auch mit Schreibrecht beim Eigentümer des Profils.
* **Ein Profil lässt sich nicht löschen, nur zurücksetzen.** Wer es gibt, sagt
  die Anmeldung — ein gelöschtes Profil käme beim nächsten Aufruf ohnehin
  zurück. Zurücksetzen leert alle Daten des Profils.

## Befehle auf einen Blick

| Zweck | Befehl |
|---|---|
| Läuft der Dienst? | `systemctl status bordbuch` |
| Neu starten | `sudo systemctl restart bordbuch` |
| Mitlesen | `journalctl -u bordbuch -f` |
| Von Hand starten | `python3 server.py --port 8080 --verbose` |
| Vollständig sichern | `tar czf ~/sicherung.tar.gz bordbuch.db receipts` |

Die Optionen des Startbefehls stehen ausführlich in Teil 1 unter
*Startbefehl im Detail*.

---

*Bordbuch — zwei Dateien, keine Fremdpakete, deine Daten bleiben bei dir.*
