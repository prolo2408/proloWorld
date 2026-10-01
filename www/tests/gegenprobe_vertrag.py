#!/usr/bin/env python3
"""Hat der Vertragstest Zaehne? (CLAUDE.md §13a)

Baut in eine KOPIE dieses Werkzeugs je einen Fehler ein, den
tests/test_vertrag.py finden muss, und verlangt, dass er ihn findet. Die
Kopie liegt im Kratzblock - nie wird im Arbeitsstand mutiert (N-34).

Dieselbe Datei liegt in wiki, bordbuch und www.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ersetze(text, alt, neu):
    if alt not in text:
        return None
    return text.replace(alt, neu, 1)


def gesundheit_weg(text):
    """Die Gesundheit aus der Freiliste nehmen - egal, ob sie als Pfad
    ("/gesundheit") oder in Teilen (["gesundheit"]) dasteht."""
    zeile = re.search(r"^EINLASS_FREI = .*$", text, re.M)
    if not zeile or "gesundheit" not in zeile.group(0):
        return None
    return text.replace(zeile.group(0),
                        zeile.group(0).replace("gesundheit", "gesund-weg"), 1)


MUTATIONEN = [
    ("eine gepruefte Gruppe fehlt im Label", "docker-compose.yml",
     lambda t: ersetze(t, "prolo.gruppen=", "prolo.gruppen-weg=")),
    ("die Marke bricht nicht mehr beim Hochfahren ab", "docker-compose.yml",
     lambda t: ersetze(t, '"${PROLO_EINLASS:?', '"${PROLO_EINLASS:-')),
    ("die Herstellerdatei nennt ein Netz", "docker-compose.yml",
     lambda t: ersetze(t, "\nvolumes:\n", "\nnetworks:\n  x:\n    external: true\nvolumes:\n")),
    ("die Herstellerdatei setzt Speichergrenzen", "docker-compose.yml",
     lambda t: ersetze(t, "    restart: unless-stopped\n",
                       "    restart: unless-stopped\n    mem_limit: 1g\n")),
    ("das Abbild nennt eine andere Fassung", "docker-compose.yml",
     lambda t: ersetze(t, "image: ghcr.io/prolo2408/", "image: ghcr.io/prolo2408/X")),
    ("die Gesundheit liegt hinter der Marke", "server.py", gesundheit_weg),
    ("do_POST fuehrt an der Grenze vorbei", "server.py",
     lambda t: ersetze(t, "def do_POST(self):",
                       "def do_POST(self):\n        return None\n    def _alt_do_POST(self):")),
]


def main():
    gefunden = entwischt = 0
    for name, datei, bauen in MUTATIONEN:
        basis = tempfile.mkdtemp(prefix="vertrag-gegenprobe-")
        try:
            ziel = os.path.join(basis, "w")
            shutil.copytree(WURZEL, ziel, ignore=shutil.ignore_patterns(
                "__pycache__", ".git", "daten", "seiten", "belege"))
            pfad = os.path.join(ziel, datei)
            neu = bauen(open(pfad, encoding="utf-8").read())
            if neu is None:
                print("ABBRUCH   %s (Stelle nicht gefunden)" % name)
                entwischt += 1
                continue
            open(pfad, "w", encoding="utf-8").write(neu)
            lauf = subprocess.run([sys.executable, "-m", "unittest", "tests.test_vertrag"],
                                  cwd=ziel, capture_output=True, text=True)
            if lauf.returncode != 0:
                print("gefunden  %s" % name)
                gefunden += 1
            else:
                print("ENTWISCHT %s  <-- Testluecke" % name)
                entwischt += 1
        finally:
            shutil.rmtree(basis, ignore_errors=True)
    print("gefunden: %d   entwischt: %d" % (gefunden, entwischt))
    return 1 if entwischt else 0


if __name__ == "__main__":
    sys.exit(main())
