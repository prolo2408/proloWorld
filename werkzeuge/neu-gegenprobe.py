#!/usr/bin/env python3
"""werkzeuge/neu-gegenprobe.py

Mutationsprobe zu werkzeuge/neu-pruefen.sh (N-61, N-62).

Handgerechnete Erwartungswerte reichen nicht: ein Test kann gruen sein,
weil er nichts prueft (CLAUDE.md §13a). Darum baut dieses Skript
absichtlich Fehler ein und verlangt, dass JEDER von einer Pruefzeile
gefunden wird. Bleibt einer unentdeckt, ist das eine Testluecke und wird
geschlossen - nicht ausgeklammert.

Die Fehler landen in den KOPIEN, die neu-pruefen.sh sich in seinen
Wegwerfordner legt. Der Arbeitsstand wird nie angefasst: eine Probe, die
ueber "git checkout" zurueckrollen muesste, loescht eine noch nicht
eingecheckte Korrektur mit weg (N-34).
"""
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PRUEFER = os.path.join(HIER, "neu-pruefen.sh")

# (Name, Datei, alt, neu)
MUTATIONEN = [
    ("prolo neu legt gar keine override-Datei an",
     "neu.sh",
     '  } > "$STACK/$NAME/docker-compose.override.yml"',
     '  } > "$STACK/$NAME/.weggeworfen"'),

    ("prolo neu laesst die eigene Anmeldung unerklaert",
     "neu.sh",
     '''    printf '%s- "prolo.anmeldung=eigene"\\n' "$E"''',
     '''    printf '%s# hier stand mal etwas\\n' "$E"'''),

    ("prolo neu laesst latest als Fassung durch",
     "neu.sh",
     """grep -q ':latest$'""",
     """grep -q ':niemals-so-heisst-keine-fassung$'"""),

    ("prolo neu schreibt die .gitignore ohne die Ausnahme (N-53)",
     "neu.sh",
     '''  printf '%s\\n' ".env" ".env.*" "!.env.beispiel" "daten/"''',
     '''  printf '%s\\n' ".env" ".env.*" "daten/"'''),

    ("prolo neu legt den Ordner an, bevor das Netz steht",
     "neu.sh",
     'if [ "$OHNE_NETZ" -eq 0 ]; then\n  titel "Netz"',
     'mkdir -p "$STACK/$NAME"\nif [ "$OHNE_NETZ" -eq 0 ]; then\n  titel "Netz"'),

    ("prolo neu laesst eigenen Code eine eigene Anmeldung behaupten (§17)",
     "neu.sh",
     '''|| { fehler "Eigener Code laeuft immer hinter Authentik (§17)."; exit 1; }
  ANMELDUNG=authentik''',
     '''|| true
  ANMELDUNG="${ANMELDUNG:-authentik}"'''),

    ("netze anlegen traegt nur beim Dienst ein, nicht im Block unten",
     "netze.sh",
     '    if not hat_unten:',
     '    if False:'),

    ("netze schliessen fragt nicht, wer das Netz noch braucht",
     "netze.sh",
     '''  if [ -n "$WER" ]; then
    fehler "  NICHT geschlossen: $N wird noch erklaert von: $WER"''',
     '''  if [ -n "" ]; then
    fehler "  NICHT geschlossen: $N wird noch erklaert von: $WER"'''),

    ("netze umziehen nimmt bei einem Fehlschlag nichts zurueck",
     "netze.sh",
     '''  if ! traefik_netze | grep -qx "$NEU"; then''',
     '''  if false; then'''),

    ("prolo start sieht ueber offene Ports hinweg",
     "prolo",
     '''    if [ -n "$PORTS" ] && [ -z "$GRUND" ]; then''',
     '''    if false; then'''),

    ("prolo start laesst einen Router ohne Anmeldung los",
     "prolo",
     '''    if [ "$SCHUTZ" = OFFEN ]; then''',
     '''    if false; then'''),

    ("prolo neu legt ueber ein Werkzeug, das im Git steht (N-66)",
     "neu.sh",
     '''if command -v git >/dev/null 2>&1 \\
   && git -C "$STACK" ls-files --error-unmatch "$NAME" >/dev/null 2>&1; then''',
     '''if false; then'''),

    ("die Git-Bremse greift auch bei einem ganz neuen Namen",
     "neu.sh",
     '''   && git -C "$STACK" ls-files --error-unmatch "$NAME" >/dev/null 2>&1; then''',
     '''   && git -C "$STACK" rev-parse --git-dir >/dev/null 2>&1; then'''),

    ("die Meldung zum Abbild nennt kein Beispiel mehr",
     "neu.sh",
     '''       fehler "  docker.n8n.io/n8nio/n8n:1.121.0, nicht n8n."''',
     '''       fehler "  anders."'''),

    ("netze wirft die Meldung von docker wieder weg (N-64)",
     "netze.sh",
     """   && docker compose config --no-interpolate --format json 2>"$TMP_FEHLER")""",
     """   && docker compose config --no-interpolate --format json 2>/dev/null)"""),

    ("netze nennt einen anderen Aufruf, als es selbst gemacht hat",
     "netze.sh",
     """konfig_befehl() { printf 'cd %s/%s && docker compose config --no-interpolate' "$STACK" "$1"; }""",
     """konfig_befehl() { printf 'cd %s/%s && docker compose config' "$STACK" "$1"; }"""),

    ("netze raet auch bei einem YAML-Fehler zu sudo",
     "netze.sh",
     """    if printf '%s' "$KM" | grep -qi "permission denied\\|not permitted\\|kein Zugriff"; then""",
     """    if true; then"""),

    ("netze zaehlt auch erklaerte Ports als Beanstandung",
     "netze.sh",
     '''    if [ -n "$PORTS" ] && [ -z "$GRUND" ]; then
      HINWEISE="$HINWEISE''',
     '''    if [ -n "$PORTS" ]; then
      HINWEISE="$HINWEISE'''),
]


def main():
    gefunden = entwischt = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(
                "import io, sys, os\n"
                "p = os.path.join(sys.argv[1], %r)\n"
                "s = io.open(p, encoding='utf-8').read()\n"
                "alt, neu = %r, %r\n"
                "if s.count(alt) != 1:\n"
                "    sys.stderr.write('Muster %%dx gefunden: %%r\\n' %% (s.count(alt), alt))\n"
                "    sys.exit(1)\n"
                "io.open(p, 'w', encoding='utf-8').write(s.replace(alt, neu))\n"
                % (datei, alt, neu))
            skript = f.name
        try:
            umg = dict(os.environ, PROLO_MUTATION=skript)
            lauf = subprocess.run(["bash", PRUEFER], env=umg,
                                  capture_output=True, text=True)
        finally:
            os.unlink(skript)

        if lauf.returncode == 3:
            print("ABBRUCH   %s" % name)
            print("          %s" % lauf.stderr.strip().splitlines()[-1:])
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
