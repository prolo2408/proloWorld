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
    ("kern/kaefig.py", "if SOCKET.search(quelle):", "if False:",
     "Docker-Socket wird nicht als Gefahr erkannt"),
    ("kern/kaefig.py", '        fremd = sorted(set(v) - VOLUME_FREI)\n', '        fremd = []\n',
     "Volume mit driver_opts zeigt auf das Dateisystem des Servers (N-135)"),
    ("kern/kaefig.py", 'if not str(name or "").startswith(self.projekt + "_"):', "if False:",
     "Tool greift ueber den Namen auf das Volume von Authentik zu (N-135)"),
    ("kern/kaefig.py", '                self.g(name, "prolo kennt \'%s\' nicht - darum nur auf der Kommandozeile" % k)',
     "                pass", "unbekannter Schluessel (post_start, provider) geht durch (N-135)"),
    ("kern/kaefig.py", 'if v.get("file") and not _innen(v["file"], self.app):', "if False:",
     "secrets/configs lesen Dateien vom Server (N-135)"),
    ("kern/kaefig.py", "            if quelle not in self.dienste:", "            if False:",
     "volumes_from haengt einen fremden Container ein (N-135)"),
    ("kern/kaefig.py", "        if str(w or \"\") not in NAMENSRAUM[art]:", "        if False:",
     "pid/ipc: container:<fremd> geht durch (N-135)"),
    ("kern/kaefig.py", 'if not re.fullmatch(r"no-new-privileges(?:[:=]true)?", str(s)):', "if False:",
     "security_opt schaltet seccomp/apparmor ab (N-135)"),
    ("kern/kaefig.py", "        fremd = sorted(set(w) - BUILD_FREI)\n", "        fremd = []\n",
     "build reicht ssh-Schluessel des Servers weiter (N-135)"),
    ("kern/orte.py", "        os.unlink(neu)\n    except FileNotFoundError:\n        pass\n    except IsADirectoryError:\n"
     "        raise Abbruch(\"%s ist ein Ordner - dort schreibt prolo nicht hin.\" % neu)\n"
     "    with open(os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, modus)",
     "        pass\n    except FileNotFoundError:\n        pass\n"
     "    with open(os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, modus)",
     "root schreibt durch einen Verweis .env.neu nach draussen (N-136)"),
    ("kern/kaefig.py", "                if not (ziel == app_echt or ziel.startswith(app_echt + os.sep)):",
     "                if False:", ".env als Verweis auf geheim.env geht durch (N-136)"),
    ("kern/kaefig.py", 'if rel.split(os.sep)[0] == ".git":', "if False:",
     "Container haengt .git ein und legt Hooks ab (N-136)"),
    ("kern/kaefig.py", "                if p == q or p.startswith(q + os.sep):", "                if False:",
     "env_file liegt im Einhaengeordner eines Containers (N-136)"),
    ("kern/kaefig.py", "                if q2 != q and q2.startswith(q + os.sep):", "                if False:",
     "Einhaengung in einer Einhaengung - Container tauscht sie gegen einen Verweis (N-136)"),
    ("kern/kaefig.py", "                if os.path.islink(weg):", "                if False:",
     "Einhaengung ueber einen Verweis (N-136)"),
    ("kern/kaefig.py", '                  "--no-env-resolution"]', "                  ]",
     "env_file mit Pfad vom Server ist im Modell nicht zu sehen (N-137)"),
    ("kern/kaefig.py", "        return _umschreiben(cfg, kopie, os.path.normpath(app))", "        return cfg",
     "Pfade im Modell zeigen in die Kopie - Pruefung der Einhaengungen laeuft ins Leere (N-137)"),
    ("kern/kaefig.py", "            r = subprocess.run(befehl, capture_output=True, text=True, timeout=120, env=env,",
     "            r = subprocess.run(befehl, capture_output=True, text=True, timeout=120, env=None,",
     "Umgebung von root fliesst in die Pruefung ein (N-137)"),
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
    ("kern/zugang.py", "GIT_CONFIG_KEY_1=\"credential.helper\", GIT_CONFIG_VALUE_1=helfer)",
     "GIT_CONFIG_KEY_1=\"credential.helper\", GIT_CONFIG_VALUE_1=\"store --file=\" + DATEI)",
     "git nimmt den Speicher-Helfer - der loescht den Zugang nach einer Absage (N-134)"),
    ("kern/zugang.py", "    if gilt is False:\n", "    if False:\n",
     "ein abgelehnter Token ersetzt den gueltigen (N-134)"),
    ("kern/zugang.py", '"ablauf": z.get("ablauf", "")}\n', '"ablauf": z.get("ablauf", ""), "token": z.get("token")}\n',
     "der Token geht mit status.json an die Admin-Seite (N-134)"),
    ("kern/zugang.py", "if tage is None or tage > WARNEN_TAGE:", "if tage is None or tage >= WARNEN_TAGE:",
     "am 14. Tag vor dem Ablauf kommt keine Warnung (N-134)"),
    ("kern/auftrag.py", 'TOKEN = re.compile(r"[A-Za-z0-9_.~+/=-]{8,500}")', 'TOKEN = re.compile(r"\\S{8,500}")',
     "ein Token mit : oder Zeilenumbruch kommt bis in die Antwort an git (N-134)"),
    ("kern/auftrag.py", 'GEHEIM = ("compose", "env", "token")', 'GEHEIM = ("compose", "env")',
     "der Token steht in der Lage des Auftrags auf der Seite (N-134)"),
    ("kern/auftrag.py", '"--token-datei", datei["token"]]', '"--token", f["token"]]',
     "der Token steht als Argument in der Prozessliste und im Protokoll (N-134)"),
    ("admin/server.py", 'if art not in ("zugang_setzen", "zugang_test"):', "if False:",
     "ueber die Einstellungen geht jede Art von Auftrag (N-134)"),
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
