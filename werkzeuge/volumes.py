#!/usr/bin/env python3
"""werkzeuge/volumes.py

Was legt ein Werkzeug an Daten ab - und steht das auch in seiner
sicherung.conf? (N-76)

Der Anlass: bitwarden lief, und die Sicherung schrieb dazu

    Sichere bitwarden
      Hinweis: /opt/stack/bitwarden/.env gibt es nicht - uebersprungen.

Das sah aus wie "gesichert". Gesichert wurde nichts: "prolo neu" laesst
VOLUMES bei einem Fremdwerkzeug leer, weil es die Herstellerdatei zu dem
Zeitpunkt noch gar nicht gibt - und danach hat nie jemand nachgesehen.
Eine Sicherung, deren Luecke niemandem auffaellt, ist keine (§25).

Gemessen wird die ZUSAMMENGESETZTE Konfiguration, nicht eine einzelne
Datei: bei einem Fremdwerkzeug steht die Haelfte im Overlay (§16). Und
"docker compose config" rechnet den Laufzeitnamen selbst aus
(wiki_daten -> wiki_wiki_daten), sodass nichts geraten werden muss - es
braucht dafuer nicht einmal einen laufenden Docker-Dienst.

Aufruf:   volumes.py <stack> [werkzeug ...]
Ausgabe:  <werkzeug>|<art>|<name>|<lage>[|<grund>]
            art   volume | bind
            lage  gesichert | erklaert | FEHLT | unlesbar
Rueckgabe 1, sobald ein FEHLT dabei ist.
"""
import json
import os
import re
import subprocess
import sys


def conf_lesen(pfad):
    """Die Zuweisungen aus einer sicherung.conf, ohne sie auszufuehren.

    Eine conf-Datei einzulesen, indem man sie SOURCED, waere bequem und
    wuerde bei einem Tippfehler beliebigen Code ausfuehren. Hier wird
    gelesen, nicht gestartet.
    """
    werte = {}
    if not os.path.exists(pfad):
        return werte
    with open(pfad, encoding="utf-8", errors="replace") as f:
        text = f.read()
    for name, wert in re.findall(r'(?m)^([A-Z_]+)="([^"]*)"', text):
        werte[name] = wert
    return werte


def konfig(stack, werkzeug):
    """Die zusammengesetzte Compose-Konfiguration als JSON, oder None."""
    ordner = os.path.join(stack, werkzeug)
    try:
        roh = subprocess.run(
            ["docker", "compose", "config", "--no-interpolate", "--format", "json"],
            cwd=ordner, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if roh.returncode != 0:
        return None
    try:
        return json.loads(roh.stdout)
    except ValueError:
        return None


def erklaert_lesen(wert):
    """VOLUMES_OHNE: je Zeile "name|grund"."""
    aus = {}
    for zeile in (wert or "").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        name, _, grund = zeile.partition("|")
        aus[name.strip()] = grund.strip() or "ohne Begruendung"
    return aus


def pruefen(stack, werkzeuge):
    zeilen, luecke = [], False
    for w in werkzeuge:
        c = konfig(stack, w)
        if c is None:
            zeilen.append("%s|-|-|unlesbar" % w)
            continue
        s = conf_lesen(os.path.join(stack, w, "sicherung.conf"))
        gesichert = set(s.get("VOLUMES", "").split())
        # Das fuehrende "?" heisst "darf fehlen" (backup.sh), nicht "wird
        # nicht gesichert" - es gehoert hier abgezogen. Ohne das meldete
        # der Pruefer authentik/custom-templates als Luecke, obwohl der
        # Eintrag laengst dastand: ein Pruefer, der Falschalarm gibt,
        # wird nach dem zweiten Mal weggeklickt.
        ordner = {o.lstrip("?") for o in s.get("ORDNER", "").split()}
        dateien = {d.lstrip("?") for d in s.get("DATEIEN", "").split()}
        erklaert = erklaert_lesen(s.get("VOLUMES_OHNE", ""))

        # 1. Benannte Volumes. Der Laufzeitname steht im JSON.
        for schluessel, v in sorted((c.get("volumes") or {}).items()):
            name = (v or {}).get("name") or schluessel
            if name in gesichert:
                zeilen.append("%s|volume|%s|gesichert" % (w, name))
            elif name in erklaert:
                zeilen.append("%s|volume|%s|erklaert|%s" % (w, name, erklaert[name]))
            else:
                zeilen.append("%s|volume|%s|FEHLT" % (w, name))
                luecke = True

        # 2. Bind-Mounts aus dem Werkzeugordner. Die sieht man von aussen
        #    gar nicht ("docker volume ls" kennt sie nicht) - genau darum
        #    gehoeren sie mitgezaehlt.
        wurzel = os.path.realpath(os.path.join(stack, w))
        gesehen = set()
        for dienst in sorted((c.get("services") or {}).keys()):
            for m in (c["services"][dienst] or {}).get("volumes") or []:
                if not isinstance(m, dict) or m.get("type") != "bind":
                    continue
                quelle = os.path.realpath(str(m.get("source") or ""))
                if not quelle.startswith(wurzel + os.sep):
                    continue            # zeigt aus dem Werkzeug heraus
                rel = os.path.relpath(quelle, wurzel)
                if rel in gesehen:
                    continue
                gesehen.add(rel)
                if rel in ordner or rel in dateien:
                    zeilen.append("%s|bind|%s|gesichert" % (w, rel))
                elif rel in erklaert:
                    zeilen.append("%s|bind|%s|erklaert|%s" % (w, rel, erklaert[rel]))
                else:
                    zeilen.append("%s|bind|%s|FEHLT" % (w, rel))
                    luecke = True
    return zeilen, luecke


def tools(stack):
    return sorted(n for n in os.listdir(stack)
                  if os.path.exists(os.path.join(stack, n, "docker-compose.yml")))


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Aufruf: volumes.py <stack> [werkzeug ...]\n")
        return 2
    stack = sys.argv[1]
    werkzeuge = sys.argv[2:] or tools(stack)
    zeilen, luecke = pruefen(stack, werkzeuge)
    for z in zeilen:
        print(z)
    return 1 if luecke else 0


if __name__ == "__main__":
    sys.exit(main())
