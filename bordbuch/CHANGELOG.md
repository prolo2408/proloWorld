# Änderungen

Geschrieben für den Nutzer, nicht für Entwickler: was ist neu, was war falsch,
was muss ich wissen. Neueste Fassung oben.

Fassungsnummern: letzte Stelle = Fehlerbehebung, mittlere = neue Funktion,
erste = etwas Bestehendes bricht.

---

---

## 2.5.3 — 2026-09-15

### Behoben (Geld)
- **Eingelesene Beträge standen hundertfach in der Datenbank.** Eine Ladung
  für 14,21 € wurde zu 1.421,00 €, eine für 9,84 € zu 984,00 €. Betroffen war
  jeder Import einer Lade- oder Tankliste (CSV, XLSX, JSON) — die Oberfläche
  schickt den Betrag in Cent, und der Server rechnete ihn ein zweites Mal von
  Euro in Cent um.
- **Das Einspielen einer Sicherung machte dasselbe.** Eine Tankung für
  74,12 € kam als 7.412,00 € zurück. Das war der schlimmere der beiden Fälle,
  weil eine Sicherung genau dann eingespielt wird, wenn man sich auf sie
  verlassen muss. Von Hand erfasste Vorgänge waren nie betroffen.

  Beides lag an derselben Verwechslung zweier Funktionen: `cent()` bekommt
  Euro und multipliziert mit 100. Wer damit eine Zahl liest, die schon in Cent
  steht, bekommt den hundertfachen Betrag. Dafür gibt es jetzt `ct_lesen()`,
  und die zwei Stellen benutzen sie.

### Neu: Betragsprüfung für bestehende Datenbanken
Der Fehler ist behoben, aber bereits gespeicherte Zeilen bleiben falsch. Zwei
Schalter am Server:

    python3 server.py --db <datei> --betraege-pruefen     # nur nachsehen
    python3 server.py --db <datei> --betraege-richten      # berichtigen

Geprüft wird auf zwei Wegen. **Sicher** ist der Fall, wenn die zwei
Geldspalten einer Zeile sich um genau Faktor 100 widersprechen — das kann
nicht richtig sein. **Verdächtig** ist eine Zeile, deren Stückpreis nur mit
Faktor 100 erklärbar ist: 7.412,00 € für 42,8 Liter sind 173 € je Liter.
Diese zweite Gruppe entsteht beim Einspielen einer Sicherung, wo beide
Spalten verdorben wurden, und wird nur mit `--auch-unplausible` mitgeändert —
ein Indiz ist kein Beweis. Werkstattrechnungen bleiben außen vor, dort fehlt
die Menge zum Vergleich.

`--betraege-pruefen` ändert nichts und sagt, was es tun würde. Vor dem
Berichtigen eine Sicherung ziehen (Einstellungen › Daten, oder
`sudo prolo sicherung`).

Auf dem Server, wo Bordbuch im Container läuft:

    sudo docker exec bordbuch python3 server.py --db /daten/bordbuch.db --betraege-pruefen
    sudo docker exec bordbuch python3 server.py --db /daten/bordbuch.db --betraege-richten

Das geht auch bei `read_only: true`, weil `/daten` ein Volume ist. Wer schon
einmal eine Lade- oder Tankliste eingelesen oder eine Sicherung eingespielt
hat, sollte einmal nachsehen.

### Behoben (Einrichtung)
- **Der Einrichtungs-Assistent konnte drei von vier Antriebsarten nicht
  anlegen.** „Auto anlegen" meldete einen Tippfehler in einem Feld, das der
  Assistent für diese Antriebsart gar nicht anzeigt — und weil ohne Auto kein
  Weg am Assistenten vorbeiführt, saß ein neuer Benutzer fest. Nur der
  Plug-in-Hybrid ging durch.
- **Scheitert das Anlegen, bleibt die Meldung jetzt stehen** — im Assistenten,
  mit dem Hinweis, dass die Eingaben erhalten sind. Vorher verschwand sie nach
  knapp vier Sekunden.
- **Kein erzwungener Assistent in einem fremden Profil** und keiner ohne
  Schreibrecht.
- **Der Ladeort „Zuhause" gilt jetzt als Heim-Ladepunkt**, sobald im
  Assistenten ein Heimstrompreis eingetragen wird. Vorher zählten Heimladungen
  als „unterwegs", wurden mit dem Anbieterpreis gerechnet, und die Übersicht
  schrieb Sätze wie „Unterwegs hat dich -1,04 € mehr gekostet".
- **„-1,04 € mehr gekostet" gibt es nicht mehr.** Das Vorzeichen steht jetzt
  in den Worten: mehr, weniger, oder „genauso teuer".

### Geprüft
- Alle vier Antriebsarten im Browser durch den Assistenten, je mit frischem
  Anmeldenamen.
- Import einer Lade- und einer Tankliste als CSV über das echte Dateifeld,
  Doppelerkennung, Übernahme; Sicherung schreiben, Profil leeren, Sicherung
  einspielen und die Beträge vergleichen.
- 122 Server-Tests (`tests/alle.sh`), darunter 21 neue für die Cent-Rechnung
  und den Importweg. Die Zähne der Tests sind mit sieben Mutationen
  nachgewiesen.

---

## 2.5.2 — 2026-09-13

### Behoben (Sicherheit)
- **Belegbilder waren nicht an das Profil gebunden.** Wer einen Dateinamen
  kannte, bekam die Rechnung — unabhängig davon, wem sie gehört. Der zufällige
  Name war Verschleierung, kein Zugangsschutz. Jetzt muss man angemeldet sein
  **und** der Beleg muss zum eigenen oder einem freigegebenen Profil gehören;
  nach Entzug der Freigabe ist er sofort wieder gesperrt.

### Behoben
- **Der Stapel-Import verschluckte den Grund fehlgeschlagener Zeilen.** Es stand
  nur „37 von 40 übernommen" da. Jetzt wird gesagt, woran die übrigen scheiterten.

### Geprüft
- 32 Angriffsproben gegen den laufenden Server: fremde Datensätze über die
  Kennung, Grenzen der Freigaben, Pfadangriffe, Herkunftsprüfung, kaputte und
  übergroße Anfragen, SQL- und Skripteinschleusung, Anmeldung und Gruppen.
- Die Oberfläche wurde auf unmaskierten Nutzertext durchsucht: 234 Ausgaben,
  alle maskiert.

---

## 2.5.1 — 2026-09-13

### Behoben
- **Das Thema wirkte nur zur Hälfte.** Kopfleiste und Seitenhintergrund waren
  dunkel, Karten und Text dagegen hell — ein Mischzustand. Ursache: die
  Altnamen (`--panel`, `--text`, `--volt` …) zeigten als Aliase auf die neuen
  Token, standen aber in `:root`, also am `<html>`. CSS löst `var()` auf dem
  Element auf, auf dem die Zeile steht — die Aliase griffen deshalb immer die
  hellen Werte und vererbten sie nach unten, während die Dunkel-Werte am
  `<body>` hängen. Die Aliase stehen jetzt ebenfalls am `<body>`.
- **Alle Emojis sind raus** (CLAUDE.md §1: keine Emojis). Betroffen waren
  Abschnittstitel („⚡ Strom"), Knopfbeschriftungen und Listenzeilen. Wo das
  Symbol wirklich etwas unterschied — Laden gegen Tanken in einer gemischten
  Liste — steht jetzt eine Wortmarke statt eines Bildchens.

---

## 2.5.0 — 2026-09-13

### Neu
- **Das Prolo-Designsystem gilt jetzt** (CLAUDE.md §2). Alle
  Farben kommen aus den vorgegebenen Token in `oklch`; feste Farbwerte stehen
  nur noch im weißen Druckblatt, wo sie hingehören. Die Akzentfarbe ist Blau
  statt Gelb.
- **Hell- und Dunkelmodus.** Dunkel ist der Standard, oben rechts wird
  umgeschaltet, die Wahl bleibt auf dem Gerät. Beide Themen sind auf Kontrast
  nachgerechnet: 14 Text-zu-Fläche-Paare, alle über der Vorgabe.
- **Schriftrollen nach CLAUDE.md §3:** Sora für Überschriften, Kennzahlen und
  Beträge (mit engerer Laufweite), Instrument Sans als Grundschrift, JetBrains
  Mono für Rohwerte.

### Behoben
- **Im Hellmodus wäre die Meldung unlesbar gewesen** — dunkler Text auf dunkler
  Fläche (1,24:1). Die Meldefläche ist in beiden Themen dunkel, der Text erbte
  aber die Themenfarbe. Jetzt gibt es dafür ein eigenes Token.
- Der dekorative Farbverlauf im Seitenhintergrund ist entfernt (CLAUDE.md §1:
  keine Verläufe).

### Hinweis zu den Schriften
- Die drei Schriften werden **nicht** von einer fremden Seite geladen. Sind sie
  auf dem Gerät vorhanden, greifen sie; sonst wird die Systemschrift benutzt.
  Sollen sie überall gleich aussehen, müssen die Schriftdateien mit ausgeliefert
  werden — das ist bewusst offen gelassen.

### Noch offen
- Der Seitenaufbau aus CLAUDE.md §5 (Sidebar 248 px und Kopf 76 px am Rechner,
  Tabbar mit vier Einträgen am Handy) ist **nicht** umgesetzt. Bordbuch hat
  weiterhin seine Reiterleiste.

---

## 2.4.1 — 2026-09-13

### Behoben
- **Der Container startete in einer Endlosschleife**
  (`can't open file '/app/server.py': Permission denied`). `server.py` lag im
  Paket mit den Rechten `600` — nur für root lesbar. `COPY` übernimmt die Rechte
  der Quelldatei, und Bordbuch läuft im Container bewusst als unprivilegierter
  Nutzer, der die eigene Programmdatei dann nicht öffnen konnte. Das Dockerfile
  setzt die Rechte jetzt selbst (`chmod 0644`), unabhängig davon, womit die
  Datei gepackt wurde; zusätzlich wird das Paket mit begradigten Rechten gebaut.

---

## 2.4.0 — 2026-09-12

> **Beim Umstieg zu beachten:** Die Volumes heißen jetzt anders und die Belege
> liegen getrennt. Wer schon eine Fassung laufen hatte, muss die Daten einmal
> umhängen (Befehle unten), sonst startet Bordbuch mit leeren Volumes.

### Neu
- **`aktualisierung.conf`** liegt bei (Pflichtdatei nach CLAUDE.md §16):
  `TYP="build"`, Prüfadresse `http://bordbuch:8080/`, 20 Sekunden Wartezeit.
  Die Prüfung funktioniert, weil Bordbuch `/` bewusst ohne Anmeldekopf
  beantwortet — die Seite selbst ist leer, alle Daten kommen über `/api`.
- **Zwei benannte Volumes** statt einem: `bordbuch_daten` für die Datenbank,
  `bordbuch_belege` für die Belegbilder. Beide stehen in `sicherung.conf`.
- **Knöpfe sperren sich während einer laufenden Aktion** und melden nach einer
  kurzen Wartezeit „Moment …". Damit erzeugt ein Doppeltipp auf *Speichern*
  keine doppelten Einträge mehr — ein Befund, der lange offen war.

### Geändert
- **Der Besitzer heißt überall `nutzer_id`** statt `user_id` — in allen
  Tabellen, allen Abfragen und in der Testversion. Bestehende Datenbanken
  werden beim Start einmalig umbenannt; die Umbenennung ist wiederholbar ohne
  Wirkung und lässt alle Daten unberührt.
- **`.gitignore`** deckt jetzt die vollständige Liste schützenswerter Daten ab
  (`*.key`, `*.pem`, `*.sqlite`, `*.sql`, `*.dump`, `belege/` …).

### Behoben
- **Zwei Farben standen fest im Stil** statt als Token (`--volt-hover`,
  `--hint`). Dabei fiel auf, dass `--dim` an acht Stellen benutzt, aber nie
  definiert war — Nebentext im Assistenten und in den Einstellungszeilen
  erschien dadurch in voller Helligkeit statt gedämpft.

### Umstieg von 2.3.0 (nur wenn schon gelaufen)
```bash
cd /opt/stack/bordbuch && docker compose down
docker run --rm -v bordbuch_daten:/alt -v bordbuch_bordbuch_daten:/neu \
  alpine sh -c "cp -a /alt/. /neu/ && rm -rf /neu/receipts"
docker run --rm -v bordbuch_daten:/alt -v bordbuch_bordbuch_belege:/neu \
  alpine sh -c "cp -a /alt/receipts/. /neu/ 2>/dev/null || true"
docker compose up -d --build
```

---

## 2.3.0 — 2026-09-12

### Entfernt
- **Die automatische Sicherung ist raus** — samt systemd-Dienst und -Timer, dem
  Startparameter `--backup`, der Hintergrundschleife im Container und der
  Statusanzeige unter *Einstellungen → Daten*. Bordbuch schreibt damit von sich
  aus keine Dateien mehr außer Belegen. Gesichert wird dort, wo es hingehört:
  beim zentralen Backup des Stacks über das Volume `bordbuch_daten`.

### Unverändert
- **Sicherung herunterladen** und **Sicherung wiederherstellen** in der
  Oberfläche bleiben genau wie bisher — das ist der Export deiner Daten, nicht
  die automatische Dateisicherung.

---

## 2.2.0 — 2026-09-12

### Neu
- **Bordbuch ist stack-fertig:** `Dockerfile`, `docker-compose.yml` und
  `sicherung.conf` liegen bei. Kein `ports:`, Netz `proxy`, feste Fassung beim
  Abbild, Traefik-Labels mit `authentik@file`, unprivilegierter Nutzer im
  Container. Ohne Fremdpakete — Bordbuch braucht weiter nur die Python-
  Standardbibliothek, also kein `pip` im Abbild.
- **Ein Volume hält alles.** Datenbank, Belege **und** Sicherungen liegen jetzt
  gemeinsam neben der Datenbank (im Container `/daten`). Vorher lagen Belege und
  Sicherungen im Programmverzeichnis — im Container wären sie bei jedem Neubau
  verloren gewesen. Auf dem Pi ändert sich nichts.
- **Tägliche Sicherung ohne systemd:** `BORDBUCH_SICHERUNG_STUNDEN` legt im
  laufenden Dienst einen konsistenten Schnappschuss an (SQLite-Backup-API).
- **Deine Gruppen stehen im Profil** — samt Hinweis, warum die Gesamtsicherung
  sichtbar ist oder fehlt.

### Geändert
- **Bericht und Abrechnung tragen den wirklichen Namen aus der Anmeldung**,
  beim eigenen Profil zusätzlich die E-Mail. Für einen Nachweis beim Arbeitgeber
  oder Finanzamt zählt der echte Name, nicht ein Spitzname.
- **Die Freigabe-Auswahl nennt die E-Mail** — bei ähnlichen Anzeigenamen trifft
  man sonst die falsche Person.
- Ob Bordbuch auf einer offenen Adresse lauschen darf, sagt jetzt
  `BORDBUCH_HEADER_VERTRAUEN` ausdrücklich, statt einer Container-Erkennung zu
  vertrauen, an der der Start hängt.

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
