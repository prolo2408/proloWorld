#!/usr/bin/env python3
"""werkzeuge/wiederherstellen-gegenprobe.py

Mutationsprobe zu werkzeuge/wiederherstellen-pruefen.sh (N-77).

Ein Wiederherstellungslauf, der gruen meldet und nichts tut, ist die
teuerste Art zu scheitern - man merkt es erst, wenn man ihn braucht.
Genau das ist hier beim Bauen passiert: der erste Lauf meldete
"vollstaendig und lesbar" ueber einen leeren Plan. Darum baut dieses
Skript absichtlich Fehler ein und verlangt, dass jeder gefunden wird.

Die Fehler landen in der KOPIE im Wegwerfordner des Pruefers, nie im
Arbeitsstand (N-34, N-60).
"""
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PRUEFER = os.path.join(HIER, "wiederherstellen-pruefen.sh")

MUTATIONEN = [
    # N-87: ein Werkzeug, dessen Ordner hier fehlt, kommt aus der Sicherung.
    ("ein fehlender Werkzeugordner wird nicht aus der Sicherung gelesen (N-87)",
     '    if [ ! -e "$STACK/$t" ] && [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then\n      mkdir -p "$AUSPACK/ordner"',
     '    if false; then\n      mkdir -p "$AUSPACK/ordner"'),

    ("der fehlende Werkzeugordner wird beim Einspielen nicht angelegt (N-87)",
     '  if [ ! -e "$STACK/$t" ] && [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then\n    if tar xzf',
     '  if false; then\n    if tar xzf'),

    ("ein vorhandener Werkzeugordner wird ueberschrieben (N-87)",
     '  if [ ! -e "$STACK/$t" ] && [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then\n    if tar xzf',
     '  if [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then\n    if tar xzf'),

    ("die Probe legt den fehlenden Ordner schon an (N-87)",
     '        conf="$AUSPACK/ordner/$t/sicherung.conf"',
     '        conf="$AUSPACK/ordner/$t/sicherung.conf"; tar xzf "$STANDORDNER/$t/werkzeug.tar.gz" -C "$STACK"'),

    ("der SQLite-Schritt entfaellt - der Stand aus dem Volume gewinnt",
     '  for eintrag in $S; do\n    name=$(basename "${eintrag#*:}")',
     '  for eintrag in ""; do\n    name=$(basename "${eintrag#*:}")'),

    # Der ganze sh -c-Aufruf, damit die Ersetzung keine Anfuehrungszeichen
    # zerreisst: die vorige Fassung traf einen Ausschnitt und liess ein
    # ' stehen - das Ergebnis lief weiter und aenderte nichts.
    ("das fremde -wal bleibt liegen",
     """         sh -c 'cp "/ein/'"$name"'" "/daten/'"$2"'" && \\
                rm -f "/daten/'"$2"'-wal" "/daten/'"$2"'-shm"' >/dev/null 2>&1; then""",
     """         sh -c 'cp "/ein/'"$name"'" "/daten/'"$2"'"' >/dev/null 2>&1; then"""),

    ("das Volume wird ergaenzt statt ersetzt",
     "sh -c 'rm -rf /daten/..?* /daten/.[!.]* /daten/* 2>/dev/null; \\\n                tar xzf",
     "sh -c 'true; \\\n                tar xzf"),

    ("der jetzige Stand wird nicht weggelegt",
     'tar czf "/ab/$vol.tar.gz" -C /daten . >/dev/null 2>&1 \\',
     'true >/dev/null 2>&1 \\'),

    # Beide Riegel auf einmal: einzeln faengt der jeweils andere die
    # Mutation ab, und das ist richtig so (N-72). Gebrochen ist die
    # Eigenschaft erst, wenn keiner mehr steht.
    ("ohne Bestaetigung wird trotzdem geschrieben",
     'if [ "$JA" -ne 1 ]; then',
     'if false; then'),

    ("ein kaputtes Stueck haelt den Lauf nicht auf",
     'if [ "$VOLLSTAENDIG" -ne 0 ] || [ "$LESBAR" -ne 0 ]; then',
     'if false; then'),

    ("die Lesbarkeit wird gar nicht geprueft",
     'if pruefen_lesbar "$STANDORDNER"; then',
     'if true; then'),

    ("eine kaputte SQLite-Datei gilt als heil",
     'sys.exit(0 if ok == "ok" else 1)',
     'sys.exit(0)'),

    ("ein leerer Plan gilt als vollstaendig",
     '''if [ -z "$(printf '%s\\n' "$STUECKE" | awk -F'|' '$1!=""{print}')" ]; then''',
     '''if false; then'''),

    ("ein unbekannter Stand nimmt still den neuesten",
     'if [ -n "$STAND" ]; then\n    for kandidat in',
     'if false; then\n    for kandidat in'),

    ("ein verschluesseltes Archiv wird ohne Schluessel angenommen",
     '''      if [ -z "$SCHLUESSEL" ]; then''',
     '''      if false; then'''),

    ("die Datei wird eingespielt, aber ohne enge Rechte",
     'chmod 600 "$STACK/$t/$d"',
     'true'),
]


def main():
    gefunden = entwischt = 0
    for eintrag in MUTATIONEN:
        name, alt, neu = eintrag
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(
                "import io, sys, os\n"
                "p = os.path.join(sys.argv[1], 'wiederherstellen.sh')\n"
                "s = io.open(p, encoding='utf-8').read()\n"
                "alt, neu = %r, %r\n"
                "if s.count(alt) != 1:\n"
                "    sys.stderr.write('Muster %%dx gefunden\\n' %% s.count(alt))\n"
                "    sys.exit(1)\n"
                "io.open(p, 'w', encoding='utf-8').write(s.replace(alt, neu))\n"
                % (alt, neu))
            skript = f.name
        try:
            lauf = subprocess.run(["bash", PRUEFER],
                                  env=dict(os.environ, PROLO_MUTATION=skript),
                                  capture_output=True, text=True)
        finally:
            os.unlink(skript)

        if lauf.returncode == 3:
            print("ABBRUCH   %s" % name)
            print("            " + (lauf.stderr.strip().splitlines() or [""])[-1])
            entwischt += 1
        elif lauf.returncode != 0:
            print("gefunden  %s" % name)
            for z in lauf.stdout.splitlines():
                if z.startswith("FEHLER"):
                    print("            " + z)
            gefunden += 1
        else:
            print("ENTWISCHT %s  <-- Testluecke" % name)
            entwischt += 1

    print("")
    print("gefunden: %d   entwischt: %d" % (gefunden, entwischt))
    return 1 if entwischt else 0


if __name__ == "__main__":
    sys.exit(main())
