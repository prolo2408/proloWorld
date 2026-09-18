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
  (B-07). Seit 1.3.4 zaehlt der **Pflichtteil** dabei nicht mit: er kommt
  aus der Huelle, nicht von der Seite, und eine Warnung, die bei jeder
  Seite angeht, wird nicht gelesen. Weicht er vom Pflichtteil dieser Huelle
  ab, sagt die Karte genau das - und der Block zaehlt wieder als Code der
  Seite (N-40).

## Fassung 1.3.4

Zwei Meldungen, die mehr geschadet als geholfen haben.

- **Der Pflichtteil zaehlt nicht mehr als Code der Seite** (`N-40`). Die
  Karte "Was diese Seite mitbringt" meldete bei **jeder** Seite aus dem
  Editor "1 Skriptblock(e) mit zusammen 12534 Zeichen" und "parent. - die
  Seite greift nach der Huelle". Gemessen an allen sechs mitgelieferten
  Seiten: dieselbe Zahl, Zeichen fuer Zeichen. Es ist der Block, den
  `edSeiteBauen` in jede Seite legt - Inhaltsverzeichnis, Suche in der
  Seite, PDF-Bausteine -, und die `parent.`-Stellen sind die einzige
  Verbindung, die eine Seite zur Huelle hat.

  Wiedererkannt wird er an einem **Fingerabdruck** in `index.html`
  (`ED_PFLICHTTEIL_KENNUNG`, SHA-256), also Zeichen fuer Zeichen. Weicht er
  ab - eine aeltere Fassung, ein Zeichen mehr, etwas Hineingeschriebenes -,
  sagt die Karte das und der ganze Block zaehlt wieder als Code der Seite.
  Ist der Abdruck nicht lesbar, wird gemeldet wie vorher: keine stille
  Entwarnung.

  Gemessen danach: fuenf der sechs Seiten melden **gar nichts** mehr,
  `git-und-github.html` meldet die **600 Zeichen**, die sie wirklich selbst
  mitbringt - die Information, die vorher unterging.

  `node pflichtteil-nachziehen.mjs --schreiben` haelt den Abdruck auf dem
  Stand, `tests/test_editor.mjs` verlangt es.

- **Ein Entwurf ist kein Fehler mehr** (`N-41`). Eine Datei, die genau dem
  Geruest aus "Eine KI schreiben lassen" folgt - Meta-Block mit `markup`,
  leerer Koerper, kein CSS, kein Skript, so wie der Prompt es woertlich
  verlangt -, bekam beim Einspielen "Nicht uebernehmbar" mit einem Fehler
  und vier Warnungen. Alle vier betrafen Dinge, die der Editor selbst baut.

  Jetzt steht dort **eine** neutrale Karte: "Ein Entwurf - noch keine
  Seite", mit der Zahl der Abschnitte und dem Knopf "In den Editor laden".
  Uebernehmbar ist der Entwurf weiter nicht (eine leere Seite bleibt eine
  leere Flaeche, `N-23`), und echte Fehler - ein ungueltiger `slug` etwa -
  bleiben stehen, unter "Das bleibt auch nach dem Editor stehen".

  Dazu: der Kasten "Eine KI schreiben lassen" sagt jetzt auch, was nach dem
  Einspielen passiert, und aus "Datei auswaehlen" wird ein Rahmenknopf,
  sobald ein Bericht steht.

- **Offen und notiert**, nicht still nebenbei geaendert: `N-42` (jeder
  Seitenaufruf holt sich ein 404 auf `/favicon.ico`) und `N-43` (drei
  Flaechen in `--accent` auf einem Schirm, zwei davon schon vorher).

Kein Datenumzug, keine Schemaaenderung, nichts an den Gruppen.

## Fassung 1.3.3

Aufgeraeumt, eine neue Seite und eine Regeldatei statt drei.

- **Neue Seite: "Prolo bedienen und verstehen"** (`vorlagen/prolo-bedienen.html`).
  Der ganze Stack auf einer Seite, in zehn Abschnitten und sechs Gruppen: was
  die vier Schichten sind, wie der Aufbau auf der Platte aussieht, ein neuer
  Server von null, ein Werkzeug einhaengen, der Alltag mit `prolo`, Sichern,
  eine Sicherung wieder einspielen, den Agenten umziehen, Fehlersuche nach
  Symptom. Erzeugt mit dem Erzeuger der Huelle selbst (`edSeiteBauen`), also
  mit demselben Pflichtteil und denselben Farbtoken wie jede Seite aus dem
  Editor. Im Browser gefahren: Verzeichnis mit allen sechs Gruppen, Strg+F
  findet 31 Stellen zu "Sicherung", 0 Konsolenfehler.

- **Aufgeraeumt** (`N-37`). Zwei Funktionen sind weg, die nur noch ihr
  eigener Test gerufen hat: `fts_ausdruck` im Server (ersetzt von
  `fts_ausdruck_aus_teilen`) und `edPruefbar` in der Huelle (ersetzt von
  `edBefunde`). Die Tests gehen jetzt den Weg, den der Server geht. Die
  Abnahmehilfe fuer die Abschottung liegt als
  `tests/isolierung-probe.html` dort, wo man sie sucht. Und eine
  `.dockerignore` haelt den Baukontext klein: gemessen 50 -> 15 Dateien
  (1149,9 -> 510,9 kB); beim Bordbuch war sie unvollstaendig, jetzt
  41 -> 15 Dateien.

- **Eine Regeldatei** (`N-39`). Das frühere Regelblatt und die
  Betriebsregeln sind in `CLAUDE.md` zusammengezogen; die
  Handgriffe stehen in der neuen Wiki-Seite. Die 148 Verweise quer durch den
  Stack sind auf die neue Nummerierung umgeschrieben, und
  `werkzeuge/regeln-pruefen.sh` haelt fest, dass jeder von ihnen einen
  Abschnitt trifft, den es wirklich gibt.

- **`prolo` holt den neuen Stand selbst** (`N-38`). Beim Aktualisieren wird
  der Quellstand nicht nur geprueft, sondern geholt - und der Lauf mit dem
  geholten Stand neu gestartet. Neuer Befehl `prolo quelle [--holen]`, und
  `prolo status` zeigt den Stand in einer Zeile.

## Fassung 1.3.2

Eine Korrektur zu 1.3.1 - im Browser nachgestellt und gemessen.

- **Eine HTML-Datei anfuegen fuehrt nicht mehr auf eine schwarze Seite**
  (`N-36`). Die Kachel "Ich habe eine HTML-Datei" klappte die Ablage auf und
  scrollte sie ins Bild - mit scrollIntoView. Das scrollt aber JEDEN
  scrollbaren Vorfahren, auch den Koerper. Der hat seit N-34 kein
  overflow, also keine Leiste - vom Programm laesst er sich aber sehr wohl
  schieben. Die Huelle stand danach vollstaendig ausserhalb des Fensters
  (gemessen: Unterkante bei -122 Pixeln), und es gab keinen Weg zurueck.
  Jetzt scrollt die Oberflaeche nur noch die Kaesten, die wirklich scrollen,
  und die Huelle haengt am Fenster statt am Koerper. Das Hinscrollen tut
  weiter, was es soll: die Karte steht im Bild (Flaeche 0 -> 1351), die
  Huelle bleibt stehen.

## Fassung 1.3.1

Zwei Korrekturen aus der Rueckmeldung zu 1.3.0 - beide im Browser
nachgestellt und gemessen, nicht nur ueberlegt.

- **Ein Fehler beim Speichern fuehrt jetzt an seine Stelle** (`N-35`). Die
  Zeile „Eine Sache fehlt noch" war ein Satz ohne Weg: anklickbar aussehend,
  aber nur Text - und markiert wurden drei von elf Faellen. Fehlte etwas
  anderes (ein leerer Abschnitt, ein PDF-Baustein ohne Datei, ein doppelter
  Anker), passierte beim Speichern sichtbar nichts. Jetzt nennt jeder Befund
  seine Stelle: die Standzeile ist ein Knopf, jeder Punkt der Fehlerliste ist
  ein Knopf, und Speichern springt von selbst an den ersten Befund. Die
  Meldung steht am Feld, nicht nur unten in einer Liste; Felder werden
  markiert, Karten bekommen einen warmen Rand, und wer im Feld etwas aendert,
  verliert Marke und Meldung dazu.

- **Der schwarze Balken unter der Oberflaeche ist weg** (`N-34`). Die Huelle
  ist ein Rahmen und scrollt nicht mehr als Ganzes: was innen zu hoch ist,
  scrollt innen. Gab vorher irgendetwas dem Koerper Hoehe - eine
  Browsererweiterung zum Beispiel -, liess sich das ganze Dokument schieben:
  der Kopf verschwand nach oben, unten stand ein Balken in der falschen Farbe.
  Gemessen: 520 Pixel Fremdhoehe genuegten, Huellenunterkante bei 48 % der
  Fensterhoehe. Danach: 100 %, Kopf sichtbar.

## Fassung 1.3.0

- **Strg+S speichert** im Editor, und ein Baustein laesst sich **verdoppeln**.

- **Drei neue Bausteine**: Bild (als Anhang, mit Bildunterschrift), Verweise
  (Knoepfe zu anderen Wiki-Seiten) und Checkliste (Punkte zum Abhaken, mit
  Zaehler - die Haken leben nur im Browser des Lesers).

- **Eine neue Seite faengt mit einer Frage an, nicht mit einem leeren
  Formular.** Sieben Wege: leere Seite, vier Vorlagen (Anleitung, Uebersicht
  und Vergleich, Zum Nachschlagen, Rechnen und Zahlen), HTML-Datei, KI-Prompt.
  Die Vorlagen bringen Abschnitte mit Titel und Gruppe, die passenden
  Bausteine und Platzhalter mit - aber keinen Titel und keinen Pfad.
- **Entwuerfe gehen nicht mehr verloren.** Was im Editor steht, merkt sich der
  Browser und bietet es beim naechsten Mal an. Nach dem Speichern und nach
  einem ausdruecklichen Abbrechen wird er geloescht.
- **Am Handy nimmt die Speicherleiste ein Drittel weniger Platz**: die selten
  gebrauchten Knoepfe stehen hinter "Mehr" (gemessen 206 -> 123 Pixel bei
  einem 640 Pixel hohen Bild).

- **Die Verwaltung ist auf hunderte Seiten ausgelegt.** Vier Bereiche
  (Seiten, Bereiche, Gruppen, Wartung) statt einer einzigen langen Tabelle.
  In der Liste: Suche, Filter nach Bereich, Freigabe und Pruefung, Sortierung
  ueber jede Spalte, Blaettern in Fuenfzigern und Mehrfachauswahl fuer
  Freigabe und Loeschen. Gemessen mit 305 Seiten: 80 ms bis die Liste steht,
  Blaettern und Sortieren ohne merkliche Pause.
- **Index neu bauen hat jetzt einen Knopf** (`N-29`). Die Schnittstelle gab es
  seit N-16, erreichbar war sie nur mit curl.
- **Loeschen sagt die Wahrheit** (`N-30`). Fehlte der Ordner einer Seite auf
  der Platte, kam HTTP 500 - und die Seite war trotzdem weg.

- **Genauer suchen.** Im Suchfeld gelten jetzt fuenf Zeichen: `"zwei worte"`
  fuer genau diese Folge, `-wort` fuer "darf nicht vorkommen",
  `bereich:Technik`, `gruppe:wiki-technik` und `seite:kennung` fuer die
  Einschraenkung. Was als Einschraenkung gelesen wurde, steht ueber der
  Trefferliste und laesst sich dort mit einem Klick aufheben. Steht nur eine
  Einschraenkung und kein Wort da, kommen die Seiten dieses Bereichs.
- **Der Pflichtteil steht nicht mehr im Suchindex** (`N-28`). Vorher fanden
  `dark`, `light`, `prefers`, `section`, `details` und `warn` jeweils alle
  Seiten - sechs Woerter, die auf alles passen.

- **In einer einzelnen Seite suchen.** Strg+F oder der Knopf *Finden* oeffnet
  eine Leiste ueber der Seite: Wort eingeben, "3 von 17" lesen, mit Eingabe
  weiterspringen, mit Esc schliessen. Die Leiste nennt auch den Abschnitt, in
  dem man gerade steht. Steckt eine Fundstelle in einem zugeklappten
  Klapptext, klappt die Seite ihn auf.
  Seiten, die vorher gespeichert wurden, markieren die Stellen, koennen aber
  nicht mitzaehlen - die Leiste sagt das. Ein Durchlauf ueber Bearbeiten und
  Speichern bringt sie auf den Stand.

- **Eine KI kann die Seite schreiben.** Im Editor steht unter *Eine KI
  schreiben lassen* ein Prompt zum Kopieren (rund 5,8 kB). Er verlangt keinen
  fertigen Seitenaufbau, sondern einen Entwurf: Meta-Block mit Abschnitten und
  Markup. Gestaltung, Pflichtteil und Farbtokens baut der Editor daraus selbst
  - die muessen stimmen, und ein Meta-Block ist kurz genug, um richtig zu sein.
  Der Weg: Datei waehlen, *In den Editor laden*, PDF auswaehlen, speichern.
- **Ein Entwurf ist keine Seite mehr** (`N-23`). Ein Meta-Block mit leerem
  Koerper ging vorher fehlerfrei durch und lag danach als auffindbare, leere
  Seite im Wiki. Jetzt ist er ein Fehler - mit dem Weg heraus in derselben
  Meldung.
- **Der Weg in den Editor steht auch bei Fehlern offen.** Er raeumt genau die
  Fehler auf, die eine solche Datei hat.
- **Ein PDF-Knopf ohne PDF** wird nicht mehr gespeichert und sagt in einer
  eingespielten Seite, was fehlt (`N-22`).
- **Dieselbe Gruppe zweimal im Verzeichnis** wird beim Schreiben gemeldet
  (`N-24`).
- **`.ed-gut` hat jetzt einen Stil** (`N-25`).

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

### Neu: eine HTML-Datei in den Editor laden
Wähle eine Datei aus („Ich habe schon eine HTML-Datei"), und im Prüfbericht
steht jetzt neben *Übernehmen* auch **In den Editor laden**: Titel, Kennung,
Pfad, Freigabe, Abschnitte und alle Blöcke landen in den Feldern, vorhandene
Anhänge bleiben bekannt — und du änderst weiter, statt erst einzuspielen und
dann zu bearbeiten.

Der Knopf **„Als HTML-Datei laden"** hieß dabei irreführend: Er *lud herunter*.
Er heißt jetzt **„Als Datei sichern"**.

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

### Neu: die Suche findet auch, was eine Seite beschreibt
Gesucht wird jetzt zusätzlich im **Titel, im Satz darunter, im Pfad, in den
Gruppen des Inhaltsverzeichnisses und in der Adresse** einer Seite. Vorher war
eine Seite nur über ihren Inhalt zu finden — „Haushalt" oder „Grundlagen"
ergaben nichts, obwohl beides oben auf der Seite steht.

Die Trefferliste ist nach Seite gruppiert: Titel und Pfad als Kopf, darunter
die Stellen (Seite, Abschnitte, Text, PDF-Anhänge) mit Marke, woher sie kommen.
Der Fuß sagt, wie viele Seiten und Stellen es sind.

Ein **leeres Suchfeld zeigt alle Seiten**, die du sehen darfst — alphabetisch.
Dieselbe Liste liegt hinter *Alle Seiten* unter jeder Trefferliste. Wer das
Wort nicht weiß, kommt so trotzdem hin.

### Geändert: das Inhaltsverzeichnis hat Gruppen
Jeder Abschnitt kann eine **Gruppe** bekommen („Grundlagen", „Adressierung").
Links stehen dann Seitentitel, der Satz darunter und die Abschnitte unter
ihren Gruppenüberschriften — der Aufbau, den eine gut gemachte Inhaltsseite
selbst benutzt. Ohne Gruppen bleibt es eine einfache Liste.

### Geändert: Seiten anlegen, mit vier Feldern statt elf
Der Editor fragt zuerst nur nach **Titel** und **wohin die Seite gehört**.
Adresse, Freigabe und der Satz darunter liegen unter *Mehr einstellen*;
Gruppe, Stichworte und Anker unter *Mehr zu diesem Abschnitt*. **Speichern**
klebt am unteren Rand und ist immer erreichbar, mit einer Zeile daneben, die
sagt, was fehlt oder dass es bereit ist. Fehlende Pflichtfelder werden am Feld
markiert und angesprungen.

### Behoben: ein Titel ohne Längengrenze
Ein Titel von 376 Zeichen machte den Kopf der Anwendung am Handy 523 Pixel
hoch. Jetzt gilt: Titel und Abschnittstitel höchstens 120 Zeichen, der Satz
300, Pfadebene und Stichwort je 60 — mit klarer Meldung statt stiller
Kürzung. Und die Anzeige hält auch Seiten aus, die vorher schon da waren.

### Behoben: der leere Zustand
Ein frisches Wiki schickte den Nutzer „über die Verwaltung" — einen Knopf, den
ein normaler Nutzer nicht hat, und einen Weg, den es nicht mehr gibt. Jetzt
steht dort **Erste Seite anlegen**.

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
- Suche: 22 Begriffe mit handgeschriebener Erwartung gegen fünf Seiten —
  vorher 16, jetzt 22 Treffer wie erwartet.
- Bedienung: sechs Ansichten × zwei Themen × drei Breiten (360, 768, 1920) =
  36 Messungen ohne Überlauf, ohne Kontrastverletzung; 67 Klicks durch alle
  Ansichten ohne Konsolenfehler; der Weg „neue Seite anlegen" als Nutzer ohne
  Verwalterrechte durchgefahren.
- 83 Editortests und 67 Servertests (`./tests/alle.sh`).

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
- Import prueft die Datei gegen die Regeln aus CLAUDE.md, legt eine
  Vorschau an und schreibt erst nach Bestaetigung
- Eingebettete Base64-Bloecke ueber 200 kB werden zu Anhaengen; PDF-Anhaenge
  werden seitenweise durchsuchbar
- Jede Uebernahme legt die bisherige Fassung ab, Ruecksprung per Klick
