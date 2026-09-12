# Änderungen

Geschrieben für den Nutzer, nicht für Entwickler: was ist neu, was war falsch,
was muss ich wissen. Neueste Fassung oben.

Fassungsnummern: letzte Stelle = Fehlerbehebung, mittlere = neue Funktion,
erste = etwas Bestehendes bricht.

---

---

## 2.1.0 — 2026-09-12

### Neu
- **Abmelden-Knopf** oben rechts und im Profilbereich. Er führt zu
  `/outpost.goauthentik.io/sign_out`, beendet die Sitzung also dort, wo sie
  liegt — bei der Anmeldung vor Bordbuch. Mit `--abmelde-pfad` änderbar, leer
  lässt den Knopf verschwinden.
- **Wer angemeldet ist, steht jetzt immer in der Kopfzeile** (Anzeigename und
  Anmeldename) — damit beim Wechsel zwischen Konten erkennbar bleibt, als wer
  man unterwegs ist.
- **`X-Authentik-Name`** wird als Anzeigename übernommen und nachgezogen, wenn
  er sich in der Anmeldung ändert; `X-Authentik-Email` wird angezeigt.

### Geändert
- **Im Container startet Bordbuch wieder auf `0.0.0.0`.** Dort schützt nicht die
  Bindung, sondern die fehlende `ports:`-Zeile im Compose-File — Bordbuch
  erkennt den Container und weist beim Start darauf hin. Ohne Container bleibt
  es bei `127.0.0.1`.

---

## 2.0.0 — 2026-09-11

> **Achtung, das ist ein Umstieg.** Bordbuch bringt keine eigene Profilwahl mehr
> mit und lauscht nur noch auf `127.0.0.1`. Ohne vorgeschaltete Anmeldung hinter
> einem Reverse Proxy ist es nach dem Update nur vom Pi selbst erreichbar.

### Neu
- **Die Anmeldung übernimmt eine vorgeschaltete Identitätsinstanz** (Authentik
  o. ä.) per Forward-Auth. Bordbuch liest bei jeder Anfrage
  `X-authentik-username` und legt beim ersten Besuch automatisch ein Profil an.
  Benutzer anlegen, umbenennen oder löschen geht nur noch dort.
- **Freigaben.** Unter *Einstellungen → Profil* gibst du anderen gezielt Einblick
  in dein Profil — wahlweise **nur lesen** oder **auch eintragen** — und nimmst
  das jederzeit zurück. Daneben steht, was andere dir freigegeben haben; oben
  rechts schaltest du zwischen den Profilen um.
- **Profil zurücksetzen** statt löschen: leert Autos, Ladungen, Tankungen und
  Wartungen. Das Profil selbst gehört zur Anmeldung und bleibt.

### Geändert
- **Die Gesamtsicherung** (*Verwaltung → Alles sichern*) verlangt jetzt die
  Gruppe `bordbuch-admin` aus `X-authentik-groups` — vorher war sie ohne jede
  Prüfung abrufbar. Der Gruppenname lässt sich mit `--admin-gruppe` ändern.
- **Der Server startet nicht mehr auf einer offenen Adresse**, weil der
  Anmeldekopf dort fälschbar wäre. Mit `--header-vertrauen` geht es trotzdem,
  wenn der Zugang anders abgesichert ist.
- Die Profilwahl „Wer bist du?" ist ersatzlos entfallen.

### Behoben
- **Jeder im Heimnetz konnte jedes Profil öffnen** und über
  `/api/admin/export` sämtliche Daten aller Profile herunterladen. Beides ist zu.

### Für den Umstieg
- Ein bestehendes Profil verknüpfst du einmalig mit einem Anmeldenamen:
  `python3 server.py --verknuepfe anna=Anna` — sonst entsteht beim ersten
  Aufruf ein neues, leeres Profil daneben. Deine Daten gehen dabei nie verloren.
- Datenstand 4 → 5 (neue Felder am Profil, neue Tabelle `freigaben`).
  Bestehende Datenbanken laufen unverändert weiter.

---

## 1.6.2 — 2026-09-04

### Geändert
- Der Umschalter „5 · 10 · 50 · 100 · Alle" steht bei Ladungen und Tankungen
  jetzt **oben und unten** an der Liste — bei langen Listen von beiden Enden
  erreichbar, ohne ganz durchscrollen zu müssen.

---

## 1.6.1 — 2026-09-04

### Geändert
- Der Umschalter „5 · 10 · 50 · 100 · Alle" steht bei Ladungen und Tankungen
  jetzt oben über der Liste statt darunter — unten übersah man ihn leicht.

---

## 1.6.0 — 2026-09-04

### Geändert
- **Ladungen und Tankungen laden stückweise.** Statt alle auf einmal (was bei
  Jahren an Daten die Seite langsam macht) stehen die neuesten 10 da, mit einem
  Umschalter „5 · 10 · 50 · 100 · Alle". Die Summenzeile bleibt die Summe über
  alles.
- **Der Assistent fragt beim Anlegen eines Autos weder nach dem Literpreis noch
  nach globalen Startwerten.** Verbrauch trägst du einmal pro Auto ein (mit
  sinnvollen Vorschlägen), danach passt Bordbuch ihn aus deinen Fahrten von
  selbst an — nichts davon musst du pflegen.
- **Der Kilometerstand ist überall freiwillig.** Hast du ihn gerade nicht (fährt
  jemand anderes), lässt du ihn leer; Bordbuch rechnet Verbrauch und Vorhersage
  aus den Tankungen, sobald wieder ein Stand dabei ist — ohne je eine Zahl zu
  erfinden.

### Entfernt
- Die Live-Spritpreise (Beta) aus 1.5.0 sind wieder raus. Eine fremde
  Schnittstelle stand hier in keinem guten Verhältnis zum Nutzen; der Spritpreis
  kommt weiter aus dem Median deiner Tankungen.

## 1.4.0 — 2026-09-03

### Neu
- **Einrichtungs-Assistent beim ersten Start.** Neue Profile werden Schritt für
  Schritt durch das erste Auto geführt (Antrieb, Verbrauch, Wartungserinnerungen
  für HU/Öl/Inspektion/Reifen), statt vor leeren Formularen zu stehen. Derselbe
  Assistent hilft bei jedem weiteren Auto.
- **Strompreis mit Verlauf statt Einzelwert.** Ein Tarifwechsel bekommt ein
  „Gilt ab"-Datum. Jede Ladung zählt mit dem Preis, der an ihrem Tag galt —
  vergangene Ladungen, Jahresvergleiche und schon weitergegebene Abrechnungen
  bleiben stabil. Wer den alten Preis rückwirkend korrigieren will, setzt bewusst
  einen Haken.
- **Spritpreis aus deinen Tankungen.** Statt einen Literpreis zu pflegen, nimmt
  Bordbuch den Median deiner letzten Tankungen (ein Ausreißer wie eine einzelne
  Super-Plus-Tankung verzieht ihn nicht). Das Eingabefeld erscheint nur noch,
  solange du weniger als drei Tankungen hast.
- **Mehr fremde Dateiformate ohne Umbenennen gelesen:** englische Doppelnamen
  („Gross Amount"), camelCase, Einheiten und Klammern im Spaltennamen,
  „Zählerstand Start/Ende", getrennte Datum- und Zeitspalten sowie `volume`.

### Geändert
- **Einstellungen von sieben auf fünf klar benannte Unterpunkte** gestrafft.
- **„Alle Autos im Vergleich" steht jetzt im Tab Fahrzeug** (wo man ausliest),
  nicht mehr in den Einstellungen — und nur, wenn es mehr als ein Auto gibt.
- **Fragezeichen-Hilfen** an den Feldern statt Dauertext daneben.
- **Lange Listen werden stückweise angezeigt** (40 auf einmal, mit „mehr zeigen").
  Bei tausenden Vorgängen bleibt die Seite bedienbar; die Summenzeile bleibt die
  Summe über alles.

### Behoben
- **Ein Tarifwechsel veränderte rückwirkend alle vergangenen Ladungen** — ein
  stiller Datenfehler in genau den Zahlen, für die das Programm da ist. Siehe „Neu".
- **Ein Ergänzen einer Sicherung überschrieb den Preisverlauf** des Zielprofils.
  Jetzt bleiben vorhandene Einstellungen beim Zusammenführen erhalten.
- **Die Hilfe im Preis-Dialog schloss den Dialog** und verwarf die Eingabe —
  Hilfe und Formular liegen jetzt auf getrennten Ebenen.

### Noch offen (nächste Runde)
- Zweideutige Datumsformate (04/07 vs 07/04) spaltenweise erkennen, ein
  Zuordnungsdialog für unbekannte Spalten, Doppeltipp auf Speichern, das
  Bearbeiten importierter Ladungen und Online-Preise (Tankerkönig).

---

## 1.3.0 — 2026-09-03

### Neu
- **Lade- und Tankdateien landen automatisch an der richtigen Stelle.** Liest du
  im Formular eine Datei ein, erkennt Bordbuch jetzt selbst, ob es Ladungen oder
  Tankungen sind, und bringt dich zur passenden Ansicht — auch wenn du beim
  Hybrid auf dem falschen Formular geklickt hast. Vorher schlug das mit einer
  Fehlermeldung fehl; jetzt sagt Bordbuch „Das ist eine Tankliste —" und führt
  dich hin. Gilt in beide Richtungen und für CSV wie XLSX.

---

## 1.2.0 — 2026-09-03

### Neu
- **Zeilen direkt hineinkopieren.** Lässt sich eine Datei nicht lesen, kannst du
  die Tabelle jetzt aus der Rechnung, einer E-Mail oder der Wallbox-Seite
  markieren, kopieren und in ein Feld einfügen — ganz ohne Datei. Auch aus PDF
  kopierter Text (mit Leerzeichen statt Semikolon) wird erkannt.
- **Fremde JSON-Exporte** von Tank- und Lade-Apps werden gelesen: Bordbuch sucht
  darin die Tabelle und wendet die normale Spaltenerkennung an.

### Behoben
- **Eine JSON-Datei im Stapel blockierte den ganzen Wurf.** Mehrere Dateien auf
  einmal, eine JSON dabei — und es passierte nichts. Jetzt werden die Tabellen
  normal verarbeitet und die JSON getrennt behandelt.
- **„84.210 km" wurde zu Kilometerstand 84.** Eine Einheit hinter der Zahl
  brachte die Tausendererkennung durcheinander — ein stiller Fehler, der den
  Verbrauch verfälschte. Einheiten werden jetzt vor dem Rechnen entfernt.
- **Abrechnungen mit Adressblock** (Absender, Rechnungsnummer, dann erst die
  Spalten) wurden abgewiesen. Die Kopfzeile wird jetzt bis Zeile 30 gesucht,
  reine Vorspannzeilen übersprungen.
- **XLSX mit Deckblatt** (Daten erst im zweiten Blatt) wurde abgewiesen. Jetzt
  werden alle Arbeitsblätter gelesen; bei einem Blatt je Monat zusammengeführt.

### Geändert
- **Nicht gelesene Dateien werden benannt.** Wirfst du eine PDF-Rechnung mit
  einer CSV zusammen ein, sagt Bordbuch, dass die PDF nicht gelesen wurde —
  statt sie stumm zu übergehen.

### Noch offen (nächste Runde)
- Ein Zuordnungsdialog für unbekannte Spalten (dann ist Umbenennen nie mehr
  nötig), doppeltes Speichern per Doppeltipp, das Bearbeiten importierter
  Ladungen und einige Server-Feinheiten.

---

## 1.1.1 — 2026-09-01

### Behoben
- **Der eigene CSV-Export ließ sich nicht wieder einlesen.** Eine Datei mit
  Lade- und Tankzeilen wurde komplett als Ladungen gelesen. Jetzt teilt
  Bordbuch sie anhand der Spalte „Art" richtig in Ladungen und Tankungen auf.
- **Excel-Tabellen mit echten Datumszellen** wurden abgewiesen — Excel legt ein
  Datum als Zahl ab. Diese Zahlen werden jetzt als Datum erkannt; jede von Hand
  in Excel gepflegte Tankliste geht damit hinein.
- **Dateien in Windows-Kodierung (ANSI/Latin-1)** bekamen kaputte Umlaute im
  Ort. Die Kodierung wird jetzt erkannt (erst UTF-8, sonst Windows-1252).
- **Der eingestellte MwSt-Satz wirkte nicht** — Netto wurde immer mit 19 %
  gerechnet, auch bei 20 % oder 7 %. Jetzt gilt der Satz aus den Einstellungen,
  in der Oberfläche wie auf dem Server.
- **Eine sehr große Ladung** (z. B. 250 kWh am Schnelllader) wurde
  fälschlich durch 1000 geteilt. Die Umrechnung Wh→kWh entscheidet jetzt über
  die ganze Spalte, nicht je Zeile.
- Kleinere Rundungsfehler beim Import (Zählerstand-Differenz, abgeleitetes
  Netto) behoben; die Fehlermeldung nennt jetzt den richtigen Grund.

### Geändert
- **Mehr Tank-Apps und Abrechnungen ohne Umbenennen erkannt** (u. a. Fuelio,
  spanische und englische Spaltennamen, weitere Tankkarten).
- **Tankkarten-Abrechnungen ohne Literspalte** (nur Datum + Betrag, wie
  DKV/UTA) werden angenommen — sie zählen für die Kosten, nicht den Verbrauch.
- Spaltenerkennung trifft ganze Wörter statt Wortteile („Ort" wird nicht mehr
  in „Spritsorte" gefunden).
- **Das zuletzt gewählte Profil bleibt nach dem Neuladen erhalten.**
- Bricht die Verbindung zum Server ab, erscheint eine deutsche Meldung mit dem
  Hinweis, dass die Eingaben stehen bleiben.

### Noch offen (nächste Runde)
- Doppeltipp auf „Speichern", Bearbeiten importierter Ladungen, ein
  Zuordnungsdialog für unbekannte Spalten und einige Server-Feinheiten.

---

## 1.1.0 — 2026-08-28

### Neu
- **Automatische Sicherung.** Ein systemd-Timer legt jede Nacht eine Kopie der
  Datenbank an; die letzten 14 bleiben, ältere werden aufgeräumt. Wann zuletzt
  gesichert wurde, steht unter Einstellungen → Daten. `install.sh` richtet den
  Timer gleich mit ein; von Hand siehe Anleitung, „Automatische Sicherung".

### Geändert
- **Der Import liest mehr Formate ohne Umbenennen.** Deutlich mehr Spaltennamen
  werden erkannt (etwa „Tankvolumen", „Volumen" oder „Menge" für die Liter). Das
  Feld „Teilbetankung" wird richtig herum verstanden (0 = voll, 1 = Teil) — auch
  wenn eine App es umgekehrt zu „Vollgetankt" führt. Ein Tank-Export aus einer
  fremden App geht damit meist ohne Nacharbeit hinein.
- **Wenn eine Datei nicht lesbar ist**, erscheint jetzt eine Seite, die sagt,
  was fehlt und was zu tun ist (Kopfzeile prüfen, Spalten benennen, als CSV oder
  XLSX exportieren) — statt einer kurzen Meldung, die gleich wieder verschwindet.

### Wichtig zu wissen
- Die automatische Sicherung liegt in `backups/` neben der Datenbank, also auf
  demselben Gerät. Gegen einen Defekt der SD-Karte schützt das nicht — dafür
  zusätzlich ab und zu die Sicherung außer Haus kopieren (Anleitung,
  „Sicherung").

---

## 1.0.0 — 2026-08-28

Erste gezählte Fassung. Aus „Ladelog" ist **Bordbuch** geworden, weil längst
nicht mehr nur Ladungen darin stehen.

### Enthalten
* **Ladungen und Tankungen** für mehrere Fahrzeuge und Profile, alle Antriebe
  (Elektro, Plug-in-Hybrid, Benzin, Diesel). Erfassen, ändern, löschen, mit
  Belegfoto.
* **Verbrauch aus Kilometerständen** — Tank zu Tank, Teilbetankungen zählen mit.
* **Wartung & Service**: TÜV, Ölwechsel, Inspektion und mehr, fällig nach
  Kilometern oder Zeit. Vorhersage aus der eigenen Fahrleistung, Farbstufen,
  Logbuch und Werkstattkosten je Jahr.
* **Auffälligkeiten**: teure Preise, hoher Verbrauch, unmögliche Kilometerstände,
  fällige Wartungen, veränderter Verbrauch — mit „übernehmen" auf einen Klick.
* **Bericht** als Kostenaufstellung und als **Abrechnung** (Mengennachweis für
  Arbeitgeber oder Finanzamt), druckbar und als CSV.
* **Import** von CSV und XLSX: Ladeabrechnungen, openWB, Heim-Wallboxen
  (VoltBox), Tanklisten. Spalten werden über die Überschrift erkannt.
* **Sicherung** je Profil und über alle Profile, Wiederherstellen ergänzend oder
  ersetzend.
* **Fassungsanzeige und Update-Suche** unter Einstellungen → Verwaltung,
  `install.sh` und `update.sh` mit Rückrollen.

### Wichtig zu wissen
* Beim **Plug-in-Hybrid** gibt es keinen gemessenen Verbrauch je Energieart —
  die Tachostrecke enthält immer Kilometer der anderen Art. Stattdessen werden
  Strecke, Kosten je 100 km und die Mengen bezogen auf die Gesamtstrecke
  gezeigt, ausdrücklich als „keine Verbrauchsangabe" gekennzeichnet.
* **Netto und MwSt** werden aus dem Bruttobetrag abgeleitet, wenn die Abrechnung
  kein Netto ausweist. Der Satz ist einstellbar (Einstellungen → Tarife).
* **Kein Passwort.** Wer im Heimnetz ist, kann jedes Profil öffnen. Nicht ins
  offene Internet stellen.

### Umstieg von Ladelog
Nur die Dateien austauschen. Eine vorhandene `ladelog.db` wird weiter benutzt,
der alte Dienstname und der alte Anfragekopf funktionieren unverändert. Details
in der Anleitung, Abschnitt „Umstieg von Ladelog".

---

## Vorlage für den nächsten Eintrag

```markdown
## 1.2.0 — JJJJ-MM-TT

### Neu
- …

### Behoben
- …

### Geändert
- …

### Wichtig zu wissen
- …
```
