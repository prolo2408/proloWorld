#!/usr/bin/env python3
"""Gegenprobe (CLAUDE.md §13a): haben die Tests Zaehne?

Baut nacheinander je einen Fehler ein - in eine KOPIE des Repositorys, nie
in den Arbeitsstand - und verlangt, dass die Tests ihn finden. Ein Fehler,
den kein Test findet, ist eine Testluecke und wird geschlossen.

    python3 tests/gegenprobe.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)

# (Datei, alt, neu, was damit kaputt waere)
FEHLER = [
    ("kern/tools.py", 'sorted(d.get("networks") or {"default": None})', "[]",
     "Hauptdienst verliert sein default-Netz - App findet die Datenbank nicht"),
    ("kern/tools.py", 'if anm == "authentik":', 'if anm == "keine":',
     "Tool steht ohne Anmeldung offen"),
    ("kern/tools.py", 'teil.append("    ports: !reset []\\n")', "pass",
     "Ports des Herstellers bleiben offen - an Traefik vorbei"),
    ("kern/tools.py", "if SOCKET.search(quelle):", "if False:",
     "Docker-Socket wird nicht als Gefahr erkannt"),
    ("kern/tools.py", "                fehlt.append(var)", "                neu[var] = \"\"",
     "fehlender Wert wird still leer gesetzt"),
    ("kern/tools.py", 'if not d.get("restart"):', "if True:",
     "Neustart-Regel des Herstellers wird ueberschrieben"),
    ("kern/tools.py", "volumes:\\n\")\n            for pfad in fehlend:", "volumes:\\n\")\n            for pfad in []:",
     "VOLUME des Abbilds bleibt anonym - Wiederherstellung findet es nicht"),
    ("kern/tools.py", 'if c.get("QUELLE") == "git":\n            raise Abbruch("Die Compose-Datei von',
     'if False:\n            raise Abbruch("Die Compose-Datei von',
     "Bearbeiten ersetzt die Datei eines Git-Repositorys - das naechste Update scheitert"),
    ("kern/tools.py", 'if c.get("QUELLE") == "git":\n        return None', 'if False:\n        return None',
     "die Seite bietet die Datei eines Git-Repositorys zum Bearbeiten an"),
    ("kern/tools.py", "            continue            # derselbe Name ein zweites Mal: weg",
     "            zeilen.append(zeile)", "alter Wert bleibt neben dem neuen in der .env stehen"),
    ("kern/tools.py", 'return sorted(orte.env_lesen(os.path.join(docker.tool_ordner(name), "app", ".env")))',
     'return sorted(orte.env_lesen(os.path.join(docker.tool_ordner(name), "app", ".env")).items())',
     "Werte der Variablen (Passwoerter) gehen an die Admin-Seite"),
    ("kern/auftrag.py", 'if not (f["compose"] or f["env"]):', "if False:",
     "Bearbeiten ohne Aenderung sichert und startet das Tool fuer nichts neu"),
    ("kern/auftrag.py", "if name in RESERVIERT or", "if False and",
     "ein Tool darf 'admin' heissen und den Unterbau verdecken"),
    ("kern/auftrag.py", 'GIT_URL = re.compile(r"https://', 'GIT_URL = re.compile(r"(?:https|file|http)://',
     "Git-Quelle aus dem Dateisystem des Servers"),
    ("kern/auftrag.py", "    fremd = set(felder) - set(pflicht) - set(frei)", "    fremd = set()",
     "unbekannte Felder werden durchgereicht"),
    ("kern/orte.py", 'if not DOMAIN.fullmatch(werte["PROLO_DOMAIN"]):', "if False:",
     "Domain wird nicht geprueft"),
    ("kern/sicherung.py", "BEHALTEN_MINDESTENS = 3", "BEHALTEN_MINDESTENS = 0",
     "Aufraeumen loescht auch die letzten Sicherungen"),
    ("kern/sicherung.py", "        if (heute - datum).days >= tage:", "        if True:",
     "Aufraeumen loescht junge Sicherungen"),
    ("kern/agent.py", "os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK", "os.O_RDONLY | os.O_NONBLOCK",
     "Agent folgt einem Verweis aus dem Eingang"),
    ("kern/agent.py", "        art, f = auftrag.pruefen(daten)",
     '        art, f = daten["art"], dict(daten["felder"], env="", compose="")',
     "Agent fuehrt ungepruefte Auftraege aus"),
    ("traefik/dynamic/prolo.yml", '          X-authentik-groups: ""\n', "",
     "Aufrufer kann seine Gruppen selbst mitschicken"),
    ("docker-compose.yml", "      - traefik.http.routers.prolo-admin.middlewares=authentik@file\n", "",
     "Admin-Seite ohne Anmeldung"),
    ("docker-compose.yml", "    read_only: true\n    tmpfs: [ \"/tmp:size=8m\" ]\n    mem_limit: 128m",
     "    read_only: true\n    tmpfs: [ \"/tmp:size=8m\" ]",
     "Admin-Seite ohne Speichergrenze"),
    ("admin/server.py", "        if GRUPPE not in gruppen:", "        if False:",
     "Admin-Seite fragt nicht nach der Gruppe"),
    ("admin/server.py", '        if not kennung:\n            raise Antwort(401',
     '        if False:\n            raise Antwort(401', "Admin-Seite ohne Anmeldung"),
    ("admin/server.py", "        self.gleicher_ursprung()\n        if pfad == \"/einstellungen/thema\"",
     "        if pfad == \"/einstellungen/thema\"", "fremde Seite kann Auftraege absenden"),
    ("admin/server.py", "        auftrag.pruefen(daten)\n    except", "        pass\n    except",
     "Admin-Seite legt ungepruefte Auftraege ab"),
    ("admin/server.py", 'if t.get("compose") is None or compose == t["compose"]:',
     'if t.get("compose") is None:', "unveraenderte Datei wird trotzdem ersetzt"),
    ("admin/server.py", 'if t.get("compose") is None or compose == t["compose"]:',
     'if compose == t.get("compose"):', "die Seite schickt eine Datei fuer ein Git-Tool mit"),
    ("admin/server.py", 'if not re.fullmatch(r"[a-z0-9-]+\\.woff2", name)', "if False",
     "Schriftpfad laesst andere Dateien heraus"),
    ("admin/server.py", "return html.escape(str(s if s is not None else \"\"), quote=True)",
     "return str(s if s is not None else \"\")", "Werte landen ungeschuetzt im HTML"),
]


def tests_laufen(ordner):
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ordner, capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return r.returncode == 0


def main():
    kopie = tempfile.mkdtemp(prefix="prolo-gegenprobe-")
    try:
        ziel = os.path.join(kopie, "repo")
        shutil.copytree(REPO, ziel, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        if not tests_laufen(ziel):
            print("Die Tests sind schon OHNE eingebauten Fehler rot - erst das klaeren.")
            return 1
        unentdeckt = []
        for datei, alt, neu, was in FEHLER:
            pfad = os.path.join(ziel, datei)
            with open(pfad, encoding="utf-8") as f:
                original = f.read()
            if original.count(alt) != 1:
                print("  ?? %s: Stelle nicht eindeutig gefunden (%dx) - Gegenprobe veraltet"
                      % (datei, original.count(alt)))
                unentdeckt.append(was)
                continue
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(original.replace(alt, neu))
            gefunden = not tests_laufen(ziel)
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(original)
            print("  %s  %s" % ("gefunden " if gefunden else "UNENTDECKT", was))
            if not gefunden:
                unentdeckt.append(was)
        print("\n%d von %d eingebauten Fehlern gefunden." % (len(FEHLER) - len(unentdeckt),
                                                            len(FEHLER)))
        return 1 if unentdeckt else 0
    finally:
        shutil.rmtree(kopie, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
