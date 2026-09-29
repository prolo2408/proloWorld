#!/usr/bin/env python3
"""werkzeuge/zugriff-gegenprobe.py

Mutationsprobe zu werkzeuge/zugriff-pruefen.sh (N-80).

Baut absichtlich Fehler in zugriff.py ein und verlangt, dass jeder von
einer Pruefzeile gefunden wird - und zwar von der RICHTIGEN. Die
wichtigste davon ist die erste: wer die Maskierung der Zugangslinks
herausnimmt, muss auffliegen, sonst steht eines Tages eine 192-Bit-Marke
im naechsten Chat (§22).

Die Fehler landen in einer KOPIE im Wegwerfordner des Pruefers, nie im
Arbeitsstand (N-34, N-60).
"""
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PRUEFER = os.path.join(HIER, "zugriff-pruefen.sh")

# (Name, alt, neu, in welcher Pruefzeile es auffallen MUSS)
MUTATIONEN = [
    ("kennt /z/ und /s/ nicht mehr (§22)",
     '        if vorher in ("z", "s") and t:\n            raus.append("<Marke>")',
     '        if False:\n            raus.append("<Marke>")',
     "stattdessen steht dort der Platzhalter"),

    ("kuerzt lange Merkmale nicht mehr (§22)",
     '        elif len(t) >= 16 and "." not in t:',
     '        elif False:',
     "langes Merkmal ausserhalb von /z/ wird gekuerzt"),

    ("nimmt BEIDE Schutzregeln heraus - die Marke steht im Klartext (§22)",
     '        if vorher in ("z", "s") and t:\n            raus.append("<Marke>")'
     '          # Zugangslink von www (§22)\n'
     '        elif len(t) >= 16 and "." not in t:',
     '        if False:\n            raus.append("<Marke>")'
     '          # Zugangslink von www (§22)\n'
     '        elif False:',
     "Marke aus dem Zugangslink steht NICHT"),

    ("zaehlt abgewiesene Anfragen gar nicht",
     "                if code == 429:",
     "                if False:",
     "n8n: 10 Anfragen"),

    ("haelt jede Anfrage fuer abgewiesen",
     "                if code == 429:",
     "                if True:",
     "wiki: 4 Anfragen"),

    ("zaehlt 5xx nicht",
     "                elif isinstance(code, int) and 500 <= code < 600:",
     "                elif False:",
     "n8n: 10 Anfragen"),

    ("zaehlt die Quellen als eine",
     'quellen[name].add(satz.get("ClientHost") or "?")',
     'quellen[name].add("eine")',
     "n8n: 10 Anfragen"),

    ("zieht gleichartige Dateien nicht zusammen",
     '    m = re.match(r"^(.*/)[^/]+(\\.[A-Za-z0-9]{1,5})$", pfad)',
     '    m = None',
     "als eine Zeile"),

    ("laesst das WEIL weg (§7, N-69)",
     '        print("  %s hat %d Anfrage(n) abgewiesen, WEIL die Bremse am Eingang"',
     '        print("  %s hat %d Anfrage(n) abgewiesen. Die Bremse am Eingang"',
     "der Satz je Name nennt das WEIL"),

    ("wiederholt die Erklaerung je Name statt einmal (§7)",
     '    werte, wieso = bremswerte()',
     '    for _ in betroffen:\n        print("  429 setzt Traefik SELBST, ...")\n    werte, wieso = bremswerte()',
     "Erklaerung kommt genau EINMAL"),

    ("nennt die Werte nicht mehr, nur die Datei (N-64)",
     '    if werte:',
     '    if False:',
     "sie nennt die eingestellten Werte"),

    ("nennt den Befehl nicht, nur die Aufgabe (N-67)",
     '    print("    sudo prolo start traefik      (gefahrlos zu wiederholen)")',
     '    print("    Traefik neu starten")',
     "sie nennt den Befehl"),

    ("liest die gedrehten Dateien nicht mit",
     '                if n.startswith("zugriff.log")]',
     '                if n == "zugriff.log"]',
     "gedrehte Datei zaehlt mit"),

    ("sagt beim sauberen Lauf gar nichts mehr",
     "    if not betroffen:",
     "    if False:",
     "sagt es, was das bedeutet"),

    ("meldet ein fehlendes Protokoll als Erfolg",
     '        print("    sudo prolo start traefik")\n        return 1',
     '        print("    sudo prolo start traefik")\n        return 0',
     "ein Fehlschlag, kein stilles Nichts"),
]


def main():
    gefunden = entwischt = 0
    for name, alt, neu, erwartet in MUTATIONEN:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(
                "import io, sys, os\n"
                "p = os.path.join(sys.argv[1], 'zugriff.py')\n"
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

        rot = [z for z in lauf.stdout.splitlines() if z.startswith("FEHLER")]
        passend = [z for z in rot if erwartet in z]
        if lauf.returncode == 3:
            print("ABBRUCH   %s" % name)
            entwischt += 1
        elif lauf.returncode != 0 and passend:
            print("gefunden  %s" % name)
            print("            " + passend[0].strip())
            gefunden += 1
        elif lauf.returncode != 0:
            print("DANEBEN   %s  <-- rot, aber nicht wegen '%s'" % (name, erwartet))
            for z in rot[:2]:
                print("            " + z.strip())
            entwischt += 1
        else:
            print("ENTWISCHT %s  <-- Testluecke" % name)
            entwischt += 1

    print("")
    print("gefunden: %d   entwischt: %d" % (gefunden, entwischt))
    return 1 if entwischt else 0


if __name__ == "__main__":
    sys.exit(main())
