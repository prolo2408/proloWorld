# Schriften

Die drei Schriften aus CLAUDE.md §3 liegen hier als woff2 — **seit B-19
tatsaechlich**, vorher standen hier nur diese Zeilen und die `@font-face`-Regeln
zeigten auf Dateien, die es nie gab.

    sora-latin.woff2            sora-latin-ext.woff2
    instrument-latin.woff2      instrument-latin-ext.woff2
    jetbrains-latin.woff2       jetbrains-latin-ext.woff2

Zwei Dateien je Familie, aufgeteilt nach `unicode-range`: `latin` deckt den
Alltag ab, `latin-ext` laedt der Browser nur nachtraeglich, wenn ein Zeichen
daraus vorkommt. Zusammen rund 104 kB.

Instrument Sans und JetBrains Mono sind **variable** Schriften — eine Datei
deckt den ganzen Gewichtsbereich ab. Darum steht in der `@font-face`-Regel eine
Spanne (`font-weight:400 600`) und keine einzelne Zahl, und darum sind es sechs
Dateien statt der acht, die hier vorher erwartet wurden.

Bewusst keine externe Quelle: die CSP der Seiten sperrt fremde Herkuenfte, und
eine Wissenssammlung soll auch dann lesbar sein, wenn ein Anbieter
verschwindet.

## Lizenz

Alle drei stehen unter der SIL Open Font License 1.1. Die Lizenztexte liegen
als `OFL-sora.txt`, `OFL-instrument.txt` und `OFL-jetbrains.txt` daneben — die
OFL verlangt, dass sie mitgeliefert werden.

## Gleichstand mit dem Bordbuch

`bordbuch/schriften/` enthaelt dieselben Dateien. Dass sie byteweise gleich
bleiben, prueft:

    ./werkzeuge/schriften-pruefen.sh

Das ist Absicht und keine Nachlaessigkeit: CLAUDE.md §5 will, dass die Tools
als Familie erkennbar sind, und verschiedene Schriftfassungen faellt niemandem
auf, bis zwei Fenster nebeneinander stehen. Der Bericht schlug einen gemeinsamen
Ordner `/opt/stack/schriften/` vor; das haette den Docker-Baukontext beider
Tools auf das Wurzelverzeichnis umstellen muessen. Die Pruefung erreicht
dasselbe Ziel, ohne am Bauvorgang zu ruehren.

## Erneuern

    # Fassung bei Google Fonts holen, nur latin und latin-ext
    curl -sS -A "Mozilla/5.0" \
      "https://fonts.googleapis.com/css2?family=Sora:wght@600&display=swap"

Daraus die woff2-Adressen der Subsets `latin` und `latin-ext` nehmen,
herunterladen, in **beide** Ordner legen und `schriften-pruefen.sh` laufen
lassen.
