# Regeln für die Arbeit an diesem Stack

Diese Datei gilt für alle künftigen Sitzungen. Sie ergänzt
`prolo-regelblatt.md` (Code und Tests) und `prolo-betriebsregeln.md`
(Betrieb) — die beiden sind die ausführliche Fassung und im Zweifel
maßgeblich.

## Erzeugte HTML-Seiten gehören nach `wiki/vorlagen/`

Jede fertige Wiki-Seite, die hier entsteht — als Beispiel, als Anleitung, als
Vorführung eines Bausteins —, wird unter `wiki/vorlagen/` abgelegt, nicht in
einem Arbeitsordner und nicht nur im Text einer Antwort. Grund: Von dort ist
sie einspielbar, sie wird von `wiki/tests/test_seiten.py` gegen dieselbe
Prüfung gefahren, die beim Einspielen läuft, und sie geht bei der nächsten
Sitzung nicht verloren.

Das gilt auch für Zwischenstände, die vorgezeigt werden. Was nur zum Messen
gebraucht wird, bleibt im Kratzblock.

## Arbeitsweise (Kurzfassung des Regelblatts)

- **Ein Befund, ein Arbeitsschritt, ein Commit.** Die Commit-Nachricht
  beginnt mit der Nummer des Befunds (`N-16: …`).
- **Prüfschritte werden ausgeführt, nicht überlegt** (Regelblatt §14). Im
  Commit steht, was ausgeführt wurde und was dabei herauskam — mit Zahlen.
- **Erwartungswerte von Hand** (§13). Nie die Ausgabe des Codes als
  Erwartung übernehmen.
- **Tests müssen Zähne haben** (§13a): jede neue Prüflinie wird mit einer
  Mutationsprobe belegt. Eine Mutation, die unentdeckt bleibt, ist eine
  Testlücke und wird geschlossen.
- **Nichts still nebenbei ändern.** Ein Problem, das beim Arbeiten auffällt,
  wird ein **neuer Befund** in `NEUE-BEFUNDE.md` und bekommt seinen eigenen
  Schritt.
- **Keine Datenwanderung ohne Sicherungshinweis** (§15).
- Eine Oberfläche ist erst geprüft, wenn sie im **Browser geladen** wurde.
  Zweimal hat ein Fehler auf oberster Skriptebene die ganze Hülle gekostet,
  während alle Tests grün waren (`N-14`, `N-17`).

## Die zwei Werkzeuge

| Ordner | Was | Fassung steht in |
|---|---|---|
| `wiki/` | Wissenssammlung, eigenständige HTML-Seiten in einem abgeschotteten Rahmen | `server.py` (`VERSION`), `docker-compose.yml` (`image:`), `CHANGELOG.md` |
| `bordbuch/` | Fahrtenbuch, Lade- und Tankkosten | ebenso |

Beide: Python-Standardbibliothek, SQLite, kein Fremdpaket. Geld in **ganzen
Cent** (`Decimal`, kaufmännisch gerundet), niemals `float` als Speicherform.

Tests:

```bash
cd wiki      && ./tests/alle.sh
cd bordbuch  && ./tests/alle.sh
```

Liegt `node` nicht im `PATH`, meldet `alle.sh` einen Fehlschlag — Absicht:
ein übersprungener Test ist kein grüner Test.
