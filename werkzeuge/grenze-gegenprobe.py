#!/usr/bin/env python3
"""werkzeuge/grenze-gegenprobe.py

Mutationsprobe zu werkzeuge/grenze-pruefen.sh (N-79).

Der Pruefer, der den Eingang bewacht, hatte selbst nie eine Gegenprobe -
und genau das ist der Fall, vor dem CLAUDE.md §13a warnt: eine Pruefzeile
kann gruen sein, weil sie nichts prueft. Darum baut dieses Skript
absichtlich Fehler in die Konfiguration ein und verlangt, dass JEDER von
einer Pruefzeile gefunden wird.

Gearbeitet wird auf einer Kopie der versionierten Dateien in einem
Wegwerfordner, nie im Arbeitsstand (N-34, N-60). Kopiert wird, was
"git ls-files" nennt - damit kann weder eine .env noch eine Datenbank in
die Kopie geraten (§21).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
STACK = os.path.dirname(HIER)

# (Name, Datei, alt, neu, in welcher Pruefzeile es auffallen MUSS)
MUTATIONEN = [
    ("das Wiki reicht die Marke nicht mehr durch - und faellt aus der Liste (U-02)",
     "wiki/docker-compose.yml",
     '      PROLO_EINLASS: "${PROLO_EINLASS:?PROLO_EINLASS fehlt in wiki/.env - sudo prolo geheimnisse --verteilen}"\n',
     "",
     "wiki: die Compose-Dateien reichen PROLO_EINLASS durch"),

    ("die Admin-Seite nennt ihre Gruppen nicht mehr (N-95)",
     "admin/docker-compose.yml",
     '      - "prolo.gruppen=admin=die Stack-Uebersicht sehen; admin-betrieb=Werkzeuge '
     'starten, anhalten, aktualisieren, Protokolle lesen"\n', "",
     "admin: jede gepruefte Gruppe steht in prolo.gruppen"),

    ("die Admin-Seite nennt ihre Betriebsgruppe nicht (N-104)",
     "admin/docker-compose.yml",
     "; admin-betrieb=Werkzeuge starten, anhalten, aktualisieren, Protokolle lesen", "",
     "admin: jede gepruefte Gruppe steht in prolo.gruppen"),

    ("das Wiki nennt nur eine seiner zwei Gruppen (N-95)",
     "wiki/docker-compose.yml",
     "prolo.gruppen=wiki-editor=Seiten anlegen und die eigenen bearbeiten; wiki-admin=das Wiki verwalten",
     "prolo.gruppen=wiki-admin=das Wiki verwalten",
     "wiki: jede gepruefte Gruppe steht in prolo.gruppen"),

    ("sniStrict steht wieder in einer eigenen Option (N-93)",
     "traefik/dynamic/sicherheit.yml", "    default:\n      minVersion: VersionTLS12",
     "    streng:\n      minVersion: VersionTLS12",
     "sniStrict steht in der TLS-Option 'default'"),

    ("der Vermittler bindet wieder an IPv6 (N-92)",
     "socket-proxy/docker-compose.yml", "      DISABLE_IPV6: 1\n", "",
     "socket-proxy bindet nur IPv4"),

    ("der Vorrat faellt auf den alten Wert zurueck (N-79)",
     "traefik/dynamic/sicherheit.yml", "        burst: 700", "        burst: 150",
     "Vorrat traegt einen ganzen Seitenaufbau"),

    ("gleichzeitige Anfragen wieder bei 40 (N-79)",
     "traefik/dynamic/sicherheit.yml", "        amount: 200", "        amount: 40",
     "gleichzeitige Anfragen eines Browsers passen durch"),

    ("die Bremse trifft auch einen Menschen",
     "traefik/dynamic/sicherheit.yml", "        average: 50", "        average: 5",
     "trifft keinen Menschen"),

    ("die Bremse bremst gar nichts mehr",
     "traefik/dynamic/sicherheit.yml", "        average: 50", "        average: 5000",
     "bremst ueberhaupt"),

    ("die Ratenbremse verlaesst sich auf die Vorgabe",
     "traefik/dynamic/sicherheit.yml",
     "        period: 1s\n        sourceCriterion:\n          ipStrategy:\n            depth: 0",
     "        period: 1s",
     "ratenbremse misst ausdruecklich je Quelladresse"),

    ("die Grenze fuer gleichzeitige Anfragen verlaesst sich auf die Vorgabe",
     "traefik/dynamic/sicherheit.yml",
     "        amount: 200\n        sourceCriterion:\n          ipStrategy:\n            depth: 0",
     "        amount: 200",
     "gleichzeitig misst ausdruecklich je Quelladresse"),

    ("die Ratenbremse haengt nicht mehr am Eingang",
     "traefik/traefik.yml", "        - ratenbremse@file\n", "",
     "Ratenbremse haengt am Eingang"),

    ("die Grenze fuer gleichzeitige Anfragen haengt nicht mehr am Eingang",
     "traefik/traefik.yml", "        - gleichzeitig@file\n", "",
     "gleichzeitige Anfragen haengt am Eingang"),

    ("die Vertrauensgrenze haengt nicht mehr am Eingang (N-44)",
     "traefik/traefik.yml", "        - vertrauensgrenze@file\n", "",
     "vertrauensgrenze haengt am Eingang"),

    ("erst setzen, dann loeschen - die Marke wird wieder weggeputzt",
     "traefik/traefik.yml",
     "        - vertrauensgrenze@file\n        - einlass@file\n",
     "        - einlass@file\n        - vertrauensgrenze@file\n",
     "erst loeschen, dann setzen"),

    ("eine Identitaetskopfzeile wird nicht mehr geleert",
     "traefik/dynamic/sicherheit.yml",
     '          X-Authentik-Groups: ""\n', "",
     "leert alle"),

    ("die eigene Marke wird nicht mehr geleert",
     "traefik/dynamic/sicherheit.yml",
     '          X-Prolo-Einlass: ""\n', "",
     "leert auch X-Prolo-Einlass"),
]


def kopie_bauen(ziel):
    """Nur versionierte Dateien - so kann nichts Schuetzenswertes mitkommen."""
    dateien = subprocess.run(["git", "-C", STACK, "ls-files", "-z"],
                             capture_output=True, text=True, check=True)
    n = 0
    for rel in dateien.stdout.split("\0"):
        if not rel:
            continue
        quelle = os.path.join(STACK, rel)
        if not os.path.isfile(quelle):
            continue
        ablage = os.path.join(ziel, rel)
        os.makedirs(os.path.dirname(ablage), exist_ok=True)
        shutil.copy2(quelle, ablage)
        n += 1
    return n


def main():
    with tempfile.TemporaryDirectory(prefix="grenze-gegenprobe-") as basis:
        rein = os.path.join(basis, "rein")
        anzahl = kopie_bauen(rein)
        pruefer = os.path.join(rein, "werkzeuge", "grenze-pruefen.sh")
        if not os.path.isfile(pruefer):
            print("ABBRUCH: der Pruefer liegt nicht in der Kopie")
            return 1

        # Erst der Beweis, dass die Kopie ueberhaupt gruen ist. Ohne ihn
        # wuerde jede Mutation "gefunden" heissen, auch wenn sie nichts tut.
        vorlauf = subprocess.run(["bash", pruefer], capture_output=True, text=True)
        if vorlauf.returncode != 0:
            print("ABBRUCH: die unveraenderte Kopie ist schon rot (%d Dateien)"
                  % anzahl)
            for z in vorlauf.stdout.splitlines():
                if z.startswith("FEHLER"):
                    print("  " + z)
            return 1
        print("Kopie aus %d versionierten Dateien, unveraendert gruen." % anzahl)
        print("")

        gefunden = entwischt = 0
        for name, datei, alt, neu, erwartet in MUTATIONEN:
            arbeit = os.path.join(basis, "arbeit")
            shutil.rmtree(arbeit, ignore_errors=True)
            shutil.copytree(rein, arbeit)

            pfad = os.path.join(arbeit, datei)
            text = open(pfad, encoding="utf-8").read()
            if text.count(alt) != 1:
                print("ABBRUCH   %s  (Muster %dx in %s)"
                      % (name, text.count(alt), datei))
                entwischt += 1
                continue
            open(pfad, "w", encoding="utf-8").write(text.replace(alt, neu))

            lauf = subprocess.run(
                ["bash", os.path.join(arbeit, "werkzeuge", "grenze-pruefen.sh")],
                capture_output=True, text=True)
            rot = [z for z in lauf.stdout.splitlines() if z.startswith("FEHLER")]
            # Nicht "irgendeine Zeile ist rot" - die RICHTIGE muss rot sein.
            # Sonst deckt eine fremde Pruefzeile die Luecke zu.
            passend = [z for z in rot if erwartet in z]
            if lauf.returncode != 0 and passend:
                print("gefunden  %s" % name)
                print("            " + passend[0].strip())
                gefunden += 1
            elif lauf.returncode != 0:
                print("DANEBEN   %s  <-- rot, aber nicht wegen '%s'"
                      % (name, erwartet))
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
