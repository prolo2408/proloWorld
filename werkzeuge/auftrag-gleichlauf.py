#!/usr/bin/env python3
"""werkzeuge/auftrag-gleichlauf.py  (A-02)

Prueft die Admin-Seite dasselbe wie der Ausfuehrer? Die Seite prueft einen
Auftrag vorher, damit die Meldung sofort kommt; entschieden wird in
werkzeuge/auftrag.py. Laufen die beiden Listen auseinander, bietet die
Seite an, was dort abgelehnt wird - oder lehnt ab, was ginge.

    auftrag-gleichlauf.py <werkzeuge-ordner> <admin-ordner>

Gibt "gleich" aus, sonst die Unterschiede. Aufgerufen von
auftrag-pruefen.sh.
"""
import os
import sys

sys.path[:0] = sys.argv[1:3]
os.environ.setdefault("PROLO_EINLASS", "gleichlauf")
import auftrag  # noqa: E402
import server  # noqa: E402

unterschied = []
if set(auftrag.ARTEN) != set(server.ARTEN):
    unterschied.append("ARTEN %s / %s" % (sorted(auftrag.ARTEN), sorted(server.ARTEN)))
for art in auftrag.ARTEN:
    if art in server.ARTEN and tuple(auftrag.ARTEN[art][0]) != tuple(server.ARTEN[art][0]):
        unterschied.append("Felder von %s" % art)
if tuple(auftrag.KERN) != tuple(server.KERN):
    unterschied.append("KERN %s / %s" % (auftrag.KERN, server.KERN))
if auftrag.WERKZEUG.pattern != server.NAME.pattern:
    unterschied.append("Namensmuster")
if auftrag.KENNUNG.pattern != server.KENNUNG.pattern:
    unterschied.append("Kennungsmuster")
print("; ".join(unterschied) or "gleich")
