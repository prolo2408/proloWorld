# Tests

Ausführen, ohne Fremdpakete — passend dazu, dass der Server bewusst nur die
Standardbibliothek benutzt:

```bash
cd /opt/stack/bordbuch
python3 -m unittest discover -s tests -t tests -v     # Server
node tests/test_geld_oberflaeche.mjs                  # Oberfläche
```

Oder beides zusammen:

```bash
./tests/alle.sh
```

## Was hier geprüft wird

| Datei | Prüft | Befund |
|---|---|---|
| `test_geld.py` | Cent-Umrechnung, Mehrwertsteuer, Summen | B-04 |
| `test_eingaben.py` | Zahlen, Plausibilitätsgrenzen, Datumsbereiche, `plus_monate` | B-05 |
| `test_trennung.py` | Mandantentrennung, Freigabemodell, Gruppentrennzeichen | B-12, B-30 |
| `test_geld_oberflaeche.mjs` | Cent-Rechnung der Oberfläche, `sum()` | B-04 |
| `test_antriebsarten.py` | Verbrauchsangaben passend zur Antriebsart | N-08 |
| `test_geld_cent.py` | `ct_lesen` gegen `cent`, Importweg, Sicherung, Betragsprüfung | N-10 |

## Die zwei Regeln, die hier gelten

**1. Erwartungswerte werden von Hand gerechnet.** CLAUDE.md §13: „Nicht die
Ausgabe des Codes als Erwartung übernehmen — das testet nur, dass sich nichts
ändert, nicht dass es stimmt." Jeder Erwartungswert in diesen Dateien steht mit
der Rechnung im Kommentar darüber. Wer einen Wert ändert, rechnet ihn neu —
nicht: lässt sich den neuen vom Code ausgeben.

**2. Pflichtfälle je Berechnung:** ein normaler Fall (handgerechnet), der
Grenzfall (null, negativ, sehr groß), der Fall mit fehlenden Daten.

## Gegenprobe — gehört zur Abnahme

Ein Test, der bei einem echten Fehler nicht anschlägt, ist Beschäftigung.
Darum wird die Testsuite selbst geprüft, indem absichtlich Fehler eingebaut
werden:

```bash
./tests/gegenprobe.sh
```

Das Skript baut nacheinander vier echte Fehler ein und erwartet, dass jeder
gefunden wird:

| Fehler | Muss gefunden werden von |
|---|---|
| Rundung zur geraden Zahl statt kaufmännisch | `test_rundung_halbe_cent_aufwaerts` |
| Stille Null statt `None` bei unlesbarer Eingabe | `test_keine_stille_null` |
| Netto als Fließkommazahl runden | `test_netto_rundet_kaufmaennisch…` |
| Mehrwertsteuer unabhängig rechnen statt als Differenz | `test_netto_plus_mwst_ist_immer_brutto` |

Beim Schreiben der Tests hat genau diese Gegenprobe eine Lücke aufgedeckt:
die erste Fassung hätte den Fließkomma-Fehler nicht gefunden, weil die
geprüften Beträge zufällig übereinstimmten. Erst ein Wert, bei dem
`brutto/1,20` genau auf `,5` endet (3 Cent bei 20 %), trennt die beiden
Rundungsarten.

## Zweite Gegenprobe: die Cent-Rechnung (N-10)

Für `test_geld_cent.py` wurden sieben Mutationen eingebaut, jede hat
mindestens einen Test rot gemacht:

| Mutation | Ergebnis |
|---|---|
| `ct_lesen` rechnet wieder mit 100 | 5 Tests rot |
| Sicherung nimmt wieder `cent()` | 1 Test rot |
| Import nimmt wieder `cent()` | 1 Test rot |
| `ct_lesen` schluckt Unlesbares als Null | 1 Test rot |
| Prüfung findet den Spaltenwiderspruch nicht mehr | 2 Tests rot |
| Unplausibles wird auch ohne Wunsch geändert | 1 Test rot |
| Stückpreis-Grenze auf einen echten Preis gesenkt | 2 Tests rot |

Auch hier hat die Probe eine echte Lücke gezeigt: „Import nimmt wieder
`cent()`" blieb beim ersten Lauf **unentdeckt**, weil die Umrechnung tief in
einem Handler steckte und kein Test sie erreichte. Sie steht jetzt in
`import_zeile_werte()` und ist abgedeckt.

Eine achte Mutation wurde verworfen statt gezählt: Werkstattrechnungen in die
Stückpreis-Prüfung aufzunehmen ändert nichts Beobachtbares, weil dort die
„Menge" der Betrag selbst wäre und das Verhältnis damit immer bei 100 liegt.
Eine Mutation, die nichts ändert, kann kein Test finden — das ist keine Lücke.

## Noch nicht abgedeckt

Der Bericht verlangt in B-12 außerdem `test_wartung.py` (Fälligkeit nach km
**und** Datum) und `test_verbrauch.py` (kWh und l je 100 km). Beide brauchen,
dass die Fachlogik aus `index.html` in prüfbare Funktionen gehoben wird —
Verbrauch und Kosten werden derzeit **im Browser** gerechnet und sind damit
weder prüfbar noch zwischen Geräten verlässlich gleich. Das ist der eigentliche
Aufwand an B-12 und steht noch aus.
