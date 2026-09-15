"""Gemeinsamer Zugang zum Server-Modul fuer die Tests.

server.py ist ein Programm, keine Bibliothek: DATEN und SEITEN kommen aus der
Umgebung, und beim Import wird noch nichts geoeffnet. Die Tests brauchen nur
die reinen Pruef- und Rechenfunktionen - darum wird das Modul hier importiert
und auf harmlose Ordner gezeigt.
"""
import os
import sys
import tempfile

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

_tmp = os.path.join(tempfile.gettempdir(), "wiki-tests")
os.makedirs(os.path.join(_tmp, "daten"), exist_ok=True)
os.makedirs(os.path.join(_tmp, "seiten"), exist_ok=True)
os.environ.setdefault("WIKI_DATEN", os.path.join(_tmp, "daten"))
os.environ.setdefault("WIKI_SEITEN", os.path.join(_tmp, "seiten"))

import server                                          # noqa: E402
