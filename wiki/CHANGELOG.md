# Wiki — Aenderungen

## Wichtig zum Einspielen

**Eingespielte Seiten bringen eigenen Code mit. Spiele nur Seiten ein, deren
Herkunft du kennst.** Das ist Absicht und der Kern der Architektur: die Seiten
sind eigenstaendig und haben eigenes Verhalten. Es heisst aber auch, dass eine
Seite aus fremder Quelle - von einem Kollegen, aus einem Export, von einem
Sprachmodell erzeugt - Code ist, den du auf deinem Server laufen laesst.

Zwei Schichten schuetzen dabei (beide aus der Pruefung vom 14.09.2026):

- Die Seiten laufen in einem **abgeschotteten Rahmen mit eigenem, opakem
  Origin**. Sie kommen nicht an die Wiki-Schnittstelle, nicht an Cookies,
  nicht an die Anmeldung und nicht an die Huelle. Vorher war eine
  eingespielte Seite gleichbedeutend mit Code-Ausfuehrung auf
  `wiki.prolo.me` (B-03 Teil 4).
- Die Pruefung beim Einspielen zeigt unter **"Was diese Seite mitbringt"**,
  welches Verhalten im Code steckt: Skriptbloecke, Abrufe nach draussen,
  Zugriffe auf Cookies oder Speicher, iframes. Das sind Hinweise, keine
  Fehler - aber sie stehen vor dem "Uebernehmen"-Knopf, nicht dahinter
  (B-07).

## Fassung 1.2.0

### Behoben: die Suche fand nicht, was auf der Seite steht
„tcp" ergab null Treffer, obwohl TCP in der Tabelle der Transportprotokolle
sichtbar ist. Der Grund: Der Server kann kein JavaScript. Eine Seite, die
ihre Tabellen, Glossare und Schrittfolgen erst im Browser aufbaut, hat diesen
Inhalt nirgends im HTML — und der Index las nur das HTML.

Der Index hat jetzt zwei zusätzliche Quellen:

| Quelle | Woher | Für wen |
|---|---|---|
| gemeldeter Text | Die Seite schickt nach dem Laden, was sie anzeigt | Seiten mit dem aktuellen Pflichtteil |
| Skripttext | Zeichenketten aus den Skriptblöcken, Code herausgefiltert | alle Seiten, ohne Änderung an der Seite |

Die erste Quelle ist genau, die zweite ungenau aber sofort da. Wer eine alte
Seite hat, spielt nichts neu ein: **Verwaltung › Index neu** genügt, danach
findet die Suche auch den Inhalt aus den Skripten. Eine Seite, die den
aktuellen Pflichtteil trägt, meldet ihren Text beim nächsten Öffnen selbst —
dann verschwindet die ungenaue Quelle wieder.

### Behoben: eine gelöschte Seite legte die Suche für immer still
Der eigentliche Grund, warum die Suche nichts fand. Der Suchindex nutzt
dieselbe Zeilennummer wie die Trefferliste. Beim Löschen einer Seite wurden
die Treffer entfernt, die Zeilen im Suchindex blieben aber liegen — und die
nächste eingespielte Seite stieß darauf. Der Indexaufbau brach ab
(`IntegrityError: constraint failed`), und zwar dauerhaft: auch **Index neu**
lief in denselben Fehler. Wer einmal eine Seite gelöscht hatte, hatte danach
eine Wissenssammlung ohne Suche.

Jetzt nimmt das Löschen den Index mit; Reste werden beim Start weggeräumt
(mit Zeile im Protokoll) und zusätzlich immer dann, wenn **Index neu**
gedrückt wird. Für eine betroffene Datenbank heißt das: einspielen, starten,
einmal **Index neu** — danach findet die Suche wieder alles.

### Behoben: „Server Fehler" beim Einspielen, obwohl die Seite da war
Der Suchindex wird nach dem Festschreiben gebaut. Ging dabei etwas schief —
ein PDF-Anhang, den `pdftotext` nicht mochte, eine Eigenheit der
Volltextsuche —, war die Seite gespeichert und die Antwort trotzdem ein
Serverfehler. Wer neu lud, sah die Seite. Jetzt gilt: die Seite ist
übernommen, und wenn der Index nicht gebaut werden konnte, steht genau das
da, samt Weg (*Index neu*). Der Grund landet im Protokoll des Containers.

### Neu: jeder darf Seiten schreiben
- **Neue Seite** steht jetzt allen Angemeldeten offen, nicht nur Verwaltern.
- Eine **bestehende** Seite ändert, wer sie angelegt hat — und jeder
  Verwalter. Sonst überschreibt einer die Arbeit des anderen.
- Eine **Freigabe** kann nur auf eigene Gruppen zeigen: wer eine Seite für
  `wiki-technik` freigibt, muss selbst darin sein. Der Editor zeigt die
  eigenen Gruppen als Knöpfe — getippt werden muss nichts.
- Der **Verwalter** sieht in der Verwaltung alle Seiten mit Urheber und kann
  die Freigabe je Seite ändern, ohne die Seite neu einzuspielen. Die Änderung
  geht in die Datenbank **und** in den Meta-Block der Datei, damit das
  nächste Bearbeiten sie nicht zurückdreht.
- **Fassungen, Zurücksetzen und Löschen** darf ebenfalls der Urheber — sonst
  könnte er seine eigene Arbeit nicht zurückholen.

### Behoben: der Urheber verlor sein Recht, sobald der Verwalter die Seite anfasste
Gefunden beim Durchspielen der Rechte von oben, als fünfzehnte von fünfzehn
Prüfungen. „Urheber" wurde aus der Spalte gelesen, die bei **jeder** Übernahme
neu geschrieben wird — sie heißt also eigentlich „zuletzt gespeichert von".
Folge: Wer das Wiki verwaltet und beim Aufräumen eine fremde Seite anfasst,
nahm ihrem Urheber damit das Schreibrecht. Jetzt merkt sich die Seite ihren
Urheber getrennt; er bleibt, auch wenn ein Verwalter speichert.

**Beim ersten Start nach dem Einspielen** trägt der Server die neue Spalte
nach und füllt sie aus der Fassungsgeschichte: Die erste archivierte Fassung
trägt die Kennung dessen, der sie geschrieben hat. Es wird nur hinzugefügt,
nichts überschrieben, und das Protokoll des Containers sagt es. Seiten ohne
Fassungsgeschichte behalten die bisherige Kennung.

### Neu: Bausteine statt langer Textwüste
Unter jedem Textfeld im Editor steht jetzt ein Kasten mit Bausteinen. Ein
Klick setzt die Vorlage an der Schreibmarke ein:

| Baustein | Was daraus wird |
|---|---|
| **Rechner** | Felder, Formel, Ergebnis — rechnet im Browser mit |
| **Schritte** | nummerierte Abfolge, jeder Schritt mit Titel |
| **Kennzahlen** | Werte groß nebeneinander, mit Beschriftung |
| **Gegenüberstellung** | zwei bis vier Seiten nebeneinander |
| **Begriffsliste** | Wort und Erklärung zum Nachschlagen |
| **Klapptext** | Überschrift, die man aufklappt |

Dazu die einfachen Knöpfe: Tabelle, Merkkasten, Warnung, Gut zu wissen,
Codeblock, Liste.

Der **Rechner** bringt ein eigenes kleines Rechenwerk mit — **kein `eval`**.
Es kennt Zahlen, Feldnamen und `+ - * / ( )`, und nichts weiter. Alles andere
ergibt „keine Zahl" statt eines Funktionsaufrufs; das ist geprüft, auch gegen
`alert(1)`, `a.constructor` und `fetch("/")`.

### Neu: PDF anhängen und auf eine Seite darin verweisen
Der Baustein **PDF**: Datei auswählen, Sprungziele eintragen
(*Beschriftung · Seite*), fertig. Die Datei wird ein Anhang der Seite, und
die Knöpfe öffnen sie im Wiki — rechts neben dem Text, damit man mitlesen
kann. Bei großen Handbüchern ist die Seitenzahl der eigentliche Punkt.

Anzeigen muss das die **Hülle**, nicht die Seite: Eine eingespielte Seite läuft
in einem abgeschotteten Rahmen, dessen Regeln `frame-src` und `object-src` auf
`none` setzen. Das bleibt so — die Seite bittet die Hülle über eine Nachricht,
und die Hülle öffnet den Anhang. Der Dateiname steht nicht im Knopf, sondern
wird zur Laufzeit aus der Marke gelesen, die der Server beim Ausgliedern setzt;
so bleibt der Knopf richtig, auch wenn die Datei einen anderen Namen bekommt.

Ein **Suchtreffer aus einem PDF** springt jetzt auch dorthin: Seite öffnen und
das PDF auf der Fundseite aufmachen, statt nur zu melden, wo es steht.

### Behoben: beim Bearbeiten verlor eine Seite ihre Anhänge
Wurde eine Seite mit Anhang neu gespeichert, verschwand die Registrierung des
Anhangs: Die Datei lag schon auf dem Server, die neue Fassung nannte sie nur
noch — und `uebernehmen()` legte nur an, was mitgeschickt wurde. Folge: Der
Abruf lieferte `application/octet-stream` statt `application/pdf` (der Browser
lädt herunter statt anzuzeigen), die Seite meldete keine Anhänge mehr, und der
Text des PDFs fiel aus der Suche. Jetzt bleiben die Anhänge, die die neue
Fassung noch nennt und deren Datei noch da ist.

### Geändert: die Abschnitte stehen links
„Auf dieser Seite" steht jetzt in der Seitenleiste über dem Themenbaum, nicht
mehr als Leiste über dem Text — so wie es eine gut gemachte Inhaltsseite
selbst macht. Der offene Abschnitt ist markiert.

### Geändert: Seiten entstehen an einem Ort
In der Verwaltung gab es eine Ablage zum Einspielen und in der Seitenleiste
„Neue Seite" — zwei Wege für dieselbe Sache. Jetzt entsteht jede Seite unter
**Neue Seite**; wer schon eine HTML-Datei hat, klappt dort „Ich habe schon
eine HTML-Datei" auf. Die Verwaltung ist für alle Seiten, Freigaben,
Fassungen und Löschen da.

### Geprüft
- Suche: reproduziert (null Treffer für „tcp" an einer Seite, die ihre
  Tabelle im Skript baut), behoben, beide Quellen einzeln nachgemessen.
- Einspielen mit absichtlich gesprengtem Indexaufbau: HTTP 200, Seite im
  Baum, Hinweis statt Fehler, Grund im Protokoll.
- Rechte: 15 Fälle am laufenden Server mit drei Nutzern — anlegen als
  normaler Nutzer, fremde Seite überschreiben (403), eigene ändern, fremde
  Gruppe vergeben (403), eigene Gruppe vergeben, Sichtbarkeit je Gruppe
  (1 / 2 / 3 Seiten), fremde Fassungen (403), Verwalter ändert die Freigabe
  (Datenbank **und** Datei), Verwaltung als normaler Nutzer (403).
- Urheberspalte: auf der Datenbank nachgemessen, die der Rechtedurchgang
  hinterlassen hat — Seite mit Fassungen von `lena`, zuletzt gespeichert von
  `artur` → Urheber `lena`; danach kommt `lena` wieder an ihre Fassungen
  (HTTP 200, vorher 403) und speichert (Fassung 4), `max` nicht.
- Bausteine: Seite mit allen sechs erzeugt, 0 Fehler und 0 Warnungen in der
  Importprüfung, 320–1200 px ohne seitliches Scrollen; der Rechner im Browser
  gefahren (18 × 0,32 = 5,76, dann 20 × 0,45 = 9, Text im Feld → „—", mal
  Null → 0).
- Kompletter Durchlauf als **normaler** Nutzer: Seite mit Rechner-Baustein
  anlegen, eigene Gruppe vergeben, speichern, lesen, suchen. Keine
  JS-Fehler.
- 55 Editortests und 26 Servertests (`./tests/alle.sh`).

## Fassung 1.1.0

**Neu: der Seiten-Editor.** Seiten lassen sich jetzt im Wiki selbst
schreiben — ohne HTML, ohne Datei, ohne Editor auf dem Rechner.

- **Neue Seite** in der Seitenleiste, **Bearbeiten** im Kopf einer offenen
  Seite. Beides nur für Verwalter, weil Speichern dieselbe Berechtigung
  braucht wie Einspielen (`/api/import`).
- Eine kleine, vollständig dokumentierte Auszeichnung: Absätze, Titel,
  Listen, fett, Code, Codeblöcke, drei Kastenarten, Tabellen und Verweise
  auf andere Wiki-Seiten (`[[kennung]]`). Die Liste im Editor unter *Wie
  schreibe ich hier?* ist die ganze Sprache.
- Der Editor **erzeugt eine gewöhnliche Wiki-Seite** und schickt sie durch
  dieselbe Strecke wie eine eingespielte Datei: `/api/pruefen` legt die
  Vorschau an, `/api/import` übernimmt. Fassungen, Rücksprung und Suche
  funktionieren damit unverändert.
- Getippter Text wird immer zuerst geschützt. Wer `<script>` schreibt, sieht
  `<script>` auf der Seite. Ein Verweis wird ein Knopf, der die Hülle bittet
  zu öffnen — kein `href`, weil eine Seite im abgeschotteten Rahmen nicht
  selbst navigieren darf.
- Die getippte Quelle steht im Meta-Block je Abschnitt unter `markup`; nur
  deshalb lässt sich eine Seite später wieder aufklappen. Unter `text` steht
  wie gehabt der Suchstoff, dort ohne Auszeichnung.
- Eine Seite, die nicht aus dem Editor kommt, lässt sich trotzdem öffnen —
  mit deutlichem Hinweis, dass Speichern die eigene Gestaltung durch die
  Standardgestaltung ersetzt. Die alte Fassung bleibt über *Fassungen*
  erreichbar.
- **Noch nicht drin:** Anhänge. Wer Bilder oder PDFs braucht, spielt eine
  Datei ein.

**Merkzettel lassen sich jetzt setzen.** Der Server konnte sie schon
(`/api/lesezeichen`) und die Übersicht zeigte sie an — nur einen Knopf dafür
gab es nirgends, die Schnittstelle war von der Oberfläche aus unerreichbar.
Jetzt steht **Merken** im Kopf einer offenen Seite und schaltet um.

**Abschnittsleiste.** Unter dem Kopf steht bei Seiten mit mindestens zwei
Abschnitten „Auf dieser Seite" mit einem Knopf je Abschnitt. Der Sprung läuft
über denselben Weg wie ein Suchtreffer (`wiki-springen`), lädt den Rahmen
also nicht neu. Die Git-Anleitung mit ihren sieben Abschnitten war vorher nur
durch Scrollen zu überblicken.

**Zwei Korrekturen am Pflichtteil jeder Seite** (Befunde N-06 und N-07,
beide beim Bau des Editors aufgefallen):

- Das Thema gilt ab der ersten Zeile aus `prefers-color-scheme`. Vorher kam
  es erst mit der Nachricht der Hülle — gemessen 10 ms nach dem ersten
  Anstrich, also blitzte bei hellem Wiki jedes Mal die dunkle Fassung auf.
- Der Textdurchlauf der Suchhervorhebung lässt `script` und `style` aus.
  Vorher markierte er auch Skriptkommentare: für das Wort „Nachricht" 11
  Marken, davon 7 im Skript — und weil die erste Marke im Skript kein
  Layout hat, sprang die Seite gar nicht (`scrollY 0`). Jetzt 4 Marken,
  keine im Skript, Sprung an die Fundstelle.

Geändert in `test-seite.html`, in `vorlagen/git-und-github.html` und im
Vorlagenblock von `EINRICHTUNG.md`.

**Neu: `wiki/tests/`.** Das Wiki hatte keine Tests. Jetzt prüfen 11
Python-Tests die mitgelieferten Seiten mit derselben Funktion, die beim
Einspielen läuft, und 36 Node-Tests den Editor. `./tests/alle.sh` läuft
beides. Die Zähne der Tests sind mit zehn Mutationen nachgewiesen, in
`tests/README.md` aufgeführt — eine davon hat einen echten Testfehler
gefunden (der Kennungstest prüfte nur zwei der vier Sonderbuchstaben).

## Fassung 1.0.0

**Bewusst offen gelassen (B-46):** `poppler-utils` wird ohne Fassungsangabe
installiert. Eine feste apt-Fassung wirkt reproduzierbar, ist es aber nicht:
Debian nimmt alte Paketfassungen aus dem Spiegel, sobald eine
Sicherheitsaktualisierung nachrückt — der Bau schlägt dann fehl, und zwar
genau dann, wenn man dringend neu bauen muss. Die Reproduzierbarkeit kommt
hier vom festen Basisabbild `python:3.13-slim-bookworm`, das den Paketstand
einer Debian-Veröffentlichung festlegt. Wer es doch festschreiben will, muss
den Spiegel mit festhalten (snapshot.debian.org).

Die Fassung steht ab jetzt an drei Stellen und muss zusammenpassen
(Befund B-23): `VERSION` in `server.py`, `image: wiki:<fassung>` im
`docker-compose.yml` und diese Datei. Abfragen am laufenden System:

    curl -s http://wiki:8080/api/version      # intern, ohne Anmeldung
    python3 server.py --version               # ohne Nebenwirkung

Vorher gab es keine davon — am laufenden System liess sich nicht feststellen,
welche Fassung arbeitet.

## 2026-09-14 — Fassung 0.1

Erstes Grundgeruest.

- Shell mit Themenbaum, Suche, Seitenanzeige im iframe und Verwaltung
- Anmeldung ausschliesslich ueber die Authentik-Kopfzeilen, ohne Gastzugang
- Freigabe je Seite und je Themenzweig, wirkt auch auf Baum und Suchtreffer
- Suche: FTS5 mit Praefix- und Teilwortindex, Wortvorschlag bei Tippfehlern,
  Treffer auf Abschnittsebene mit Sprung zum Anker
- Import prueft die Datei gegen Regelblatt und Betriebsregeln, legt eine
  Vorschau an und schreibt erst nach Bestaetigung
- Eingebettete Base64-Bloecke ueber 200 kB werden zu Anhaengen; PDF-Anhaenge
  werden seitenweise durchsuchbar
- Jede Uebernahme legt die bisherige Fassung ab, Ruecksprung per Klick
