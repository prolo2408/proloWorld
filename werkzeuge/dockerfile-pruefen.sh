#!/bin/bash
# Prueft die Dockerfiles auf Formfehler, die beim Bauen teuer sind.
#
# Anlass: beim Einbauen von B-29 habe ich einen Kommentar vor "ENV " gesetzt -
# das Muster traf aber zuerst das Wort "ENV" in einem KOMMENTARTEXT, und
# heraus kam die Zeile "ENV - die kommen aus der .env ueber compose."  Ein
# ungueltiger Variablenname, der den Bau des Wiki-Abbilds zerstoert haette.
# Ohne Docker in dieser Umgebung faellt so etwas erst auf dem Server auf.
#
# Aufruf:  ./werkzeuge/dockerfile-pruefen.sh
set -u
cd "$(dirname "$0")/.."
python3 - "$@" <<'PY'
import re, sys, glob
GUELTIG = {"FROM","RUN","CMD","LABEL","EXPOSE","ENV","ADD","COPY","ENTRYPOINT",
           "VOLUME","USER","WORKDIR","ARG","ONBUILD","STOPSIGNAL","HEALTHCHECK","SHELL"}
fehler = 0
for p in sorted(glob.glob("*/Dockerfile")):
    fort = False
    for i, z in enumerate(open(p).read().split("\n"), 1):
        if fort:
            # Ein Kommentar in einer Fortsetzungszeile ist nicht verlaesslich.
            if z.strip().startswith("#"):
                print("%s:%d  Kommentar in Fortsetzungszeile: %s" % (p, i, z.strip()[:50]))
                fehler = 1
            fort = z.rstrip().endswith("\\")
            continue
        t = z.strip()
        if not t or t.startswith("#"):
            continue
        wort = t.split()[0].upper()
        if wort not in GUELTIG:
            print("%s:%d  unbekannte Anweisung: %s" % (p, i, t[:50])); fehler = 1
        if wort == "ENV" and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t[3:].strip()):
            print("%s:%d  ENV ohne NAME=WERT: %s" % (p, i, t[:50])); fehler = 1
        fort = z.rstrip().endswith("\\")
    print("ok      %s" % p if not fehler else "")
sys.exit(fehler)
PY
