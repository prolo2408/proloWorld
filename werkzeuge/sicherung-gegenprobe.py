#!/usr/bin/env python3
"""werkzeuge/sicherung-gegenprobe.py

Mutationsprobe zu werkzeuge/sicherung-pruefen.sh (N-76).

Ein Pruefer, der eine Luecke in der Sicherung finden soll, ist genau so
viel wert wie der Beweis, dass er ueberhaupt etwas finden KANN. Darum
baut dieses Skript absichtlich Fehler in volumes.py ein und verlangt,
dass jeder von einer Pruefzeile gefunden wird.

Die Fehler landen in einer KOPIE im Wegwerfordner des Pruefers, nie im
Arbeitsstand (N-34, N-60).
"""
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PRUEFER = os.path.join(HIER, "sicherung-pruefen.sh")

MUTATIONEN = [
    ("liest nur die Herstellerdatei statt der zusammengesetzten Konfiguration",
     '["docker", "compose", "config", "--no-interpolate", "--format", "json"]',
     '["docker", "compose", "-f", "docker-compose.yml", "config",\n             "--no-interpolate", "--format", "json"]'),

    ("nimmt den Schluessel statt des Laufzeitnamens",
     'name = (v or {}).get("name") or schluessel',
     'name = schluessel'),

    ("uebergeht VOLUMES_OHNE - jede Erklaerung wird zur Beanstandung",
     'erklaert = erklaert_lesen(s.get("VOLUMES_OHNE", ""))',
     'erklaert = {}'),

    ("unterscheidet Ordner und Datei nicht (N-78)",
     'art = "binddatei" if os.path.isfile(quelle) else "bind"',
     'art = "bind"'),

    ("zaehlt Bind-Mounts gar nicht mit",
     'if not isinstance(m, dict) or m.get("type") != "bind":',
     'if True:'),

    ("zaehlt auch Bind-Mounts von ausserhalb des Werkzeugs",
     'if not quelle.startswith(wurzel + os.sep):\n                    continue            # zeigt aus dem Werkzeug heraus',
     'if False:\n                    continue            # zeigt aus dem Werkzeug heraus'),

    ("zieht das ? bei ORDNER nicht ab (Falschalarm)",
     'ordner = {o.lstrip("?") for o in s.get("ORDNER", "").split()}',
     'ordner = set(s.get("ORDNER", "").split())'),

    ("meldet nie einen Fehlschlag",
     'return 1 if luecke else 0',
     'return 0'),

    ("haelt jedes Volume fuer gesichert",
     'if name in gesichert:',
     'if True:'),
]


def main():
    gefunden = entwischt = 0
    for name, alt, neu in MUTATIONEN:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(
                "import io, sys, os\n"
                "p = os.path.join(sys.argv[1], 'volumes.py')\n"
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
