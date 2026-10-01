# Schriften

Die drei Schriften aus CLAUDE.md §3, als woff2 und ohne fremde Quelle – die
Content-Security-Policy der Admin-Seite lässt nichts von außen zu.

    sora-latin.woff2            sora-latin-ext.woff2
    instrument-latin.woff2      instrument-latin-ext.woff2
    jetbrains-latin.woff2       jetbrains-latin-ext.woff2

Zwei Dateien je Familie, aufgeteilt nach `unicode-range`: `latin` deckt den
Alltag ab, `latin-ext` lädt der Browser nur, wenn ein Zeichen daraus vorkommt.
Zusammen rund 104 kB. Instrument Sans und JetBrains Mono sind variable
Schriften – eine Datei deckt den ganzen Gewichtsbereich ab.

## Lizenz

Alle drei stehen unter der SIL Open Font License 1.1. Die Lizenztexte liegen
als `OFL-sora.txt`, `OFL-instrument.txt` und `OFL-jetbrains.txt` daneben – die
OFL verlangt, dass sie mitgeliefert werden.

## Erneuern

    curl -sS -A "Mozilla/5.0" \
      "https://fonts.googleapis.com/css2?family=Sora:wght@600&display=swap"

Daraus die woff2-Adressen der Subsets `latin` und `latin-ext` nehmen,
herunterladen und hier ersetzen. Die Admin-Seite danach im Browser laden.
