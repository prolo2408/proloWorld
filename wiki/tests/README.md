# Tests

Ausführen, ohne Fremdpakete — passend dazu, dass der Server bewusst nur die
Standardbibliothek benutzt:

```bash
cd /opt/stack/wiki
python3 -m unittest discover -s tests -t tests -v   # Server und Seiten
node tests/test_editor.mjs                          # Editor
```

Oder beides zusammen:

```bash
./tests/alle.sh
```

## Was hier geprüft wird

| Datei | Prüft | Befund |
|---|---|---|
| `test_seiten.py` | Die mitgelieferten Seiten gegen `regeln_pruefen`, Anker gegen `id=`, Pflichtteil vorhanden und korrigiert, keine externen Verweise | N-06, N-07 |
| `test_editor.mjs` | Auszeichnung, Suchtext, Kennungen und die erzeugte Seite des Editors | Editor |

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

Die Mutationsprobe hat selbst einen Fehler gefunden: Der Kennungstest prüfte
nur U- und O-Umlaut. Ohne die Zeile für den A-Umlaut wäre aus „Zählerstände"
ein `zahlerstande` geworden, und der Test blieb grün. Der Fall steht jetzt
drin.

## Was hier **nicht** geprüft wird

Die Oberfläche im Browser — Ankersprung, Hervorhebung, Themenwechsel, der
Editor von Hand bedient. Das lief mit Chromium über einen Stellvertreter,
der die Authentik-Kopfzeilen setzt, und ist in den Commits belegt. Ein
dauerhafter Browsertest würde ein Fremdpaket brauchen; solange das nicht
eingezogen wird, gilt: wer an Editor oder Pflichtteil arbeitet, klickt es
einmal durch.
