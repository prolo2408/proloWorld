"""Gemeinsamer Zugang zum Server-Modul fuer die Tests.

server.py ist ein Programm, keine Bibliothek: es liest CFG erst in main().
Die Tests brauchen aber die reinen Rechenfunktionen. Darum wird das Modul
hier importiert und CFG mit einem harmlosen Standard belegt.
"""
import os
import sys
import types

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

import server                                          # noqa: E402

if getattr(server, "CFG", None) is None:
    server.CFG = types.SimpleNamespace(
        db=os.path.join(WURZEL, "tests", ".test.db"),
        verbose=False, admin_gruppe="bordbuch-admin",
        abmelde_pfad="", host="127.0.0.1", port=0)
