#!/usr/bin/env python3
"""www/tests/gegenprobe.py

Mutationsprobe zu den Tests des Freigabe-Werkzeugs (N-72).

Handgerechnete Erwartungswerte reichen nicht: ein Test kann gruen sein,
weil er nichts prueft (CLAUDE.md §13a). Darum baut dieses Skript
absichtlich Fehler ein und verlangt, dass JEDER von einem Test gefunden
wird. Bleibt einer unentdeckt, ist das eine Testluecke und wird
geschlossen - nicht ausgeklammert.

Die Fehler landen in einer KOPIE des ganzen Werkzeugordners in einem
Wegwerfverzeichnis. Der Arbeitsstand wird nie angefasst: eine Probe, die
ueber "git checkout" zurueckrollen muesste, loescht eine noch nicht
eingecheckte Korrektur mit weg (N-34, N-60).

Aufruf:  python3 tests/gegenprobe.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)

# (Name, alt, neu)
MUTATIONEN = [
    ("die nackte Adresse zeigt immer das Schild",
     '''        z = startseite_finden()
        if z is None:
            return self.senden(200, seite_start())''',
     '''        z = None
        if z is None:
            return self.senden(200, seite_start())'''),

    ("die Startseite kommt ohne den Riegel gegen fremden Code",
     '''                "Content-Security-Policy": CSP_SEITE,
                # Kein Zwischenspeicher''',
     '''                "X-Prolo-Nichts": "hier stand mal die CSP",
                # Kein Zwischenspeicher'''),

    ("auch die oeffentliche Startseite bleibt auf noindex",
     '''                "X-Robots-Tag": "all",''',
     '''                "X-Robots-Tag": "noindex",'''),

    ("eine geloeschte Seite bleibt oeffentlich stehen",
     '''        "WHERE e.schluessel = 'startseite' AND s.geloescht = 0").fetchone()''',
     '''        "WHERE e.schluessel = 'startseite'").fetchone()'''),

    ("robots.txt gibt die Wurzel auch ohne Startseite frei",
     '''            if startseite_finden() is None:
                regeln = "User-agent: *\\nDisallow: /\\n"''',
     '''            if False:
                regeln = "User-agent: *\\nDisallow: /\\n"'''),

    ("robots.txt sperrt auch die eingerichtete Startseite aus",
     '''                regeln = "User-agent: *\\nAllow: /$\\nDisallow: /\\n"''',
     '''                regeln = "User-agent: *\\nDisallow: /\\n"'''),

    ("eine unbekannte Kennung wird als Startseite angenommen",
     '''        if s is None:
            raise Antwort(404, "Diese Seite gibt es nicht.")
        db().execute(
            "INSERT INTO einstellung(schluessel,wert,geaendert,nutzer_id) "''',
     '''        if s is None:
            pass
        db().execute(
            "INSERT INTO einstellung(schluessel,wert,geaendert,nutzer_id) "'''),

    ("die zweite Wahl ersetzt die erste nicht",
     '''            "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert, "
            "geaendert=excluded.geaendert, nutzer_id=excluded.nutzer_id",''',
     '''            "ON CONFLICT(schluessel) DO NOTHING",'''),

    ("die Markierung laesst sich nicht wieder abnehmen",
     '''            db().execute("DELETE FROM einstellung WHERE schluessel='startseite'")
            db().commit()
            return self.json_senden({"ok": True, "startseite": None})''',
     '''            db().commit()
            return self.json_senden({"ok": True, "startseite": None})'''),

    ("das Loeschen laesst die Markierung stehen",
     '''        if war_start:
            db().execute("DELETE FROM einstellung WHERE schluessel='startseite'")''',
     '''        if False:
            db().execute("DELETE FROM einstellung WHERE schluessel='startseite'")'''),

    ("eine verschwundene Datei wird zum Serverfehler",
     '''        p = os.path.join(SEITEN, z["datei"])
        if not os.path.exists(p):''',
     '''        p = os.path.join(SEITEN, z["datei"])
        if False:'''),

    ("wer nicht in der Gruppe ist, darf die Startseite setzen",
     '''        if ADMIN_GRUPPE not in gruppen:
            raise Antwort(403, "Dafuer braucht es die Gruppe '%s'." % ADMIN_GRUPPE)''',
     '''        if False:
            raise Antwort(403, "Dafuer braucht es die Gruppe '%s'." % ADMIN_GRUPPE)'''),

    ("die Verwaltung verschweigt, welche Seite oeffentlich ist",
     '''    return {"nutzer": nutzer, "seiten": seiten, "version": VERSION,
            "startseite": z["kennung"] if z else None}''',
     '''    return {"nutzer": nutzer, "seiten": seiten, "version": VERSION,
            "startseite": None}'''),
]


def main():
    gefunden = entwischt = 0
    for name, alt, neu in MUTATIONEN:
        ordner = tempfile.mkdtemp(prefix="www-gegenprobe-")
        try:
            ziel = os.path.join(ordner, "www")
            shutil.copytree(WURZEL, ziel,
                            ignore=shutil.ignore_patterns("__pycache__",
                                                          "daten", "seiten"))
            quelle = os.path.join(ziel, "server.py")
            with open(quelle, encoding="utf-8") as f:
                text = f.read()
            if text.count(alt) != 1:
                print("ABBRUCH   %s" % name)
                print("            Muster %dx gefunden" % text.count(alt))
                entwischt += 1
                continue
            with open(quelle, "w", encoding="utf-8") as f:
                f.write(text.replace(alt, neu))
            lauf = subprocess.run(
                [sys.executable, "-m", "unittest", "discover",
                 "-s", "tests", "-t", "tests"],
                cwd=ziel, capture_output=True, text=True)
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

        if lauf.returncode != 0:
            print("gefunden  %s" % name)
            for z in lauf.stderr.splitlines():
                if z.startswith(("FAIL:", "ERROR:")):
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
