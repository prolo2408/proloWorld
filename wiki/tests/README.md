# Tests

Ausführen, ohne Fremdpakete — passend dazu, dass der Server bewusst nur die
Standardbibliothek benutzt:

```bash
cd /opt/stack/wiki
python3 -m unittest discover -s tests -t tests -v   # Server und Seiten
node tests/test_editor.mjs                          # Editor
```

Liegt `node` nicht im `PATH` (auf manchen Maschinen steht es unter
`/opt/node22/bin`), dann mit vollem Pfad aufrufen — `alle.sh` meldet sonst
einen Fehlschlag, und das ist richtig so: ein übersprungener Test ist kein
grüner Test.

Oder beides zusammen:

```bash
./tests/alle.sh
```

## Was hier geprüft wird

| Datei | Prüft | Befund |
|---|---|---|
| `test_seiten.py` | Die mitgelieferten Seiten gegen `regeln_pruefen`, Anker gegen `id=`, Pflichtteil vorhanden und korrigiert (auch die Textmeldung), keine externen Verweise | N-06, N-07, N-11 |
| `test_urheber.py` | Wer eine Seite ändern darf, und das Nachtragen der Spalte `urheber` in einer älteren Datenbank | N-13, N-15 |
| `test_index.py` | Dass der Suchindex an Resten gelöschter Seiten nicht scheitert, und dass das Aufräumen nur Verwaistes trifft | N-16 |
| `test_anhaenge.py` | Dass ein markierter Anhang ausgegliedert wird und beim Bearbeiten seine Registrierung behält | N-18 |
| `test_suche.py` | Was die Suche finden muss — mit echtem Indexaufbau gegen eine kleine Datenbank | Suche, N-16 |
| `test_editor.mjs` | Auszeichnung, Suchtext, Kennungen, Bausteine, Rechenwerk und die erzeugte Seite des Editors | Editor, N-14 |

`test_seiten.py` prüft **die eigenen Dateien des Repositorys** mit derselben
Funktion, die beim Einspielen läuft. Ohne das fällt erst beim Einspielen auf,
dass die Vorlage gegen die Regel verstößt, die sie vorführen soll — genau das
war bei N-06 und N-07 der Fall.

## Die zwei Regeln, die hier gelten

**1. Erwartungswerte werden von Hand geschrieben.** Regelblatt §13: Nicht die
Ausgabe des Codes als Erwartung übernehmen — das testet nur, dass sich nichts
geändert hat, nicht dass es richtig ist.

**2. Die Tests müssen Zähne haben.** Regelblatt §13a. Nachgewiesen wird das
mit einer Mutationsprobe: eine Zeile im Editor absichtlich kaputt machen und
zeigen, dass ein Test rot wird. Geprüft wurde so:

| Mutation | Ergebnis |
|---|---|
| `edEscape` schützt `<` und `>` nicht mehr | 4 Tests rot |
| Tabelle ohne `overflow-x`-Rahmen | 1 Test rot |
| Verweis wird ein `href` statt eines Knopfes | 1 Test rot |
| Suchtext behält die Auszeichnung | 2 Tests rot |
| Pflichtteil ohne Herkunftsprüfung | 1 Test rot |
| Pflichtteil setzt das Thema nicht vor dem Anstrich | 1 Test rot |
| Pflichtteil läuft wieder durch Skripttexte | 1 Test rot |
| A-Umlaut nicht mehr ausgeschrieben | 1 Test rot |
| `markup` wird nicht mehr mitgespeichert | 1 Test rot |
| Anker kommt nicht als `id` in die Seite | 2 Tests rot |
| Seite meldet ihren Text nicht mehr (`wiki-text`) | 1 Test rot |
| `urheber_von` ignoriert die eigene Spalte | 3 Tests rot |
| `darf_aendern` fragt wieder `nutzer_id` | 2 Tests rot |
| leere Kennung nicht mehr abgefangen | 1 Test rot |
| leere Fassungskennung zählt wieder mit | 1 Test rot |
| Nachtragen nimmt die letzte statt der ersten Fassung | 1 Test rot |
| Nachtragen läuft auch auf neuen Datenbanken | Fehler |
| `index_leeren` lässt die FTS-Zeilen liegen | 2 Tests rot |
| `index_leeren` lässt die `treffer`-Zeilen liegen | 2 Tests rot |
| Aufräumen tut nichts mehr | 3 Tests rot |
| Aufräumen meldet immer 0 | 2 Tests rot |
| Aufräumen lässt den Trigramm-Index aus | 1 Test rot |
| Blockmodell: Zeilen ohne Trennstrich | 3 Tests rot |
| Blockmodell: unbekannte Bausteinart verschluckt | 1 Test rot |
| Blockmodell: leerer Block landet im Markup | 1 Test rot |
| Vorschau baut selbst statt mit dem Erzeuger | 1 Test rot |
| `eval`-Weg schleicht sich in die Hülle | 1 Test rot |
| PDF-Block ohne Datei wird still verschluckt | 1 Test rot |
| PDF: Seitenzahl geht nicht an den Knopf | 1 Test rot |
| PDF: Anhangsmarke fehlt in der Seite | 1 Test rot |
| PDF: vorhandener Anhang wird nicht mehr genannt | 1 Test rot |
| PDF: Dateiname nicht aus der Marke gelesen | 1 Test rot |
| Anhänge: Marke beim Ausgliedern ignoriert | 1 Test rot |
| Seitenkopf kommt nicht in den Index | 2 Tests rot |
| Pfad fehlt im Kopftreffer | 1 Test rot |
| Satz der Seite fehlt im Kopftreffer | 1 Test rot |
| Gruppe fehlt am Abschnitt | 2 Tests rot |
| Kopfschnipsel zeigt wieder den Suchstoff | 1 Test rot |
| Titel-, Satz-, Pfad- und Stichwortgrenze ausgehebelt | je 1–3 Tests rot |

Was die Tests hier **nicht** leisten, zeigt `N-15`: Die Reihenfolge von
Handlungen am laufenden Server — anlegen, fremd speichern, wieder selbst
ändern — steckt in keinem dieser Tests. Sie wurde von Hand gegen einen
laufenden Server gefahren, und genau dort fiel der Befund auf. Wer am
Rechtemodell arbeitet, fährt diesen Weg noch einmal.

Die Mutationsprobe hat selbst einen Fehler gefunden: Der Kennungstest prüfte
nur U- und O-Umlaut. Ohne die Zeile für den A-Umlaut wäre aus „Zählerstände"
ein `zahlerstande` geworden, und der Test blieb grün. Der Fall steht jetzt
drin.

## Der Durchgang durch die Oberfläche

Regelblatt §14a verlangt, jede Ansicht in beiden Themen bei drei Breiten
anzusehen. Das lief mit Chromium über einen Stellvertreter, der die
Authentik-Kopfzeilen setzt, und ist in den Commits belegt: sechs Ansichten ×
zwei Themen × drei Breiten = 36 Messungen auf Überlauf, waagerechtes Scrollen
und Kontrast, dazu 67 Klicks durch alle Ansichten.

Wichtig dabei: **der Prüfer wurde gegengeprobt.** Ein absichtlich schlecht
lesbarer Text (Kontrast 1,23) und ein absichtlich 3000 px breiter Kasten
wurden gemeldet — ohne diese Gegenprobe hätte „keine Verletzung gefunden"
auch heißen können, dass der Prüfer nichts ansieht.

Lehren aus den Durchgängen für den nächsten:

- Chrome legt den Inhalt eines geschlossenen `<details>` weiter aus
  (`content-visibility` statt `display:none`). `getBoundingClientRect()`
  allein sagt also nicht, ob ein Feld sichtbar ist.
- Ein Überlauf **innerhalb** eines Bereichs mit `overflow-y:auto` erzeugt
  kein waagerechtes Scrollen des Dokuments. Wer nur `scrollWidth` des
  Dokuments prüft, sieht ihn nicht.
- **Hinter einem CSS-Übergang kann dieser Aufbau nichts messen.** Mit
  `--virtual-time-budget` läuft ein `transition` nicht weiter: der berechnete
  Wert bleibt für immer auf dem Anfangswert stehen. Beim Menü am Handy
  (`#seitenleiste`, `transition:transform .18s`) sah das aus wie ein Fehler —
  `data-menue="1"` gesetzt, `aria-expanded="true"`, und die Leiste stand
  weiter bei `translateX(-248px)`. Erst `sl.style.transition='none'` zeigte,
  dass die Regel gewinnt: `transform` wird `none`, die Leiste steht bei 0.
  Wer etwas hinter einem Übergang prüfen will, schaltet ihn vorher ab und
  prüft den Endzustand — sonst meldet der Prüfer einen Fehler, den es nicht
  gibt.

## Die Probe, die von Hand läuft

`isolierung-probe.html` ist keine Testdatei für `alle.sh`, sondern eine
**Abnahmehilfe**: eine Seite, die absichtlich vier Dinge versucht, die eine
eingespielte Seite nicht können darf — die Wiki-Schnittstelle aufrufen, die
Anmeldung lesen, die Hülle manipulieren, im Browser speichern. Wie man sie
benutzt und was dabei herauskommen muss, steht im Kommentar in der Datei
selbst.

Sie lag bis dahin als `wiki/test-isolierung.html` neben dem Programm und war
von nirgendwo aus zu finden (`N-37`). In `vorlagen/` kann sie nicht liegen:
sie enthält mit Absicht zwei Fehler, und `test_seiten.py` würde sie zu Recht
beanstanden.

## Was hier **nicht** geprüft wird

Die Oberfläche im Browser — Ankersprung, Hervorhebung, Themenwechsel, der
Editor von Hand bedient. Das lief mit Chromium über einen Stellvertreter,
der die Authentik-Kopfzeilen setzt, und ist in den Commits belegt. Ein
dauerhafter Browsertest würde ein Fremdpaket brauchen; solange das nicht
eingezogen wird, gilt: wer an Editor oder Pflichtteil arbeitet, klickt es
einmal durch.
