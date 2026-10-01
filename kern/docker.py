"""Alles, was mit Docker spricht.

Befehle gehen immer als Liste an subprocess, nie durch eine Shell - ein
Toolname oder eine Adresse kann so nie zu einem zweiten Befehl werden.
"""
import json
import os
import re
import subprocess

from . import orte
from .orte import Abbruch

UNTERBAU = "prolo"


def lauf(befehl, eingabe=None, zeit_s=600, env=None, cwd=None, pruefen=True):
    """Fuehrt aus und gibt (rueckgabe, ausgabe) zurueck. Mit pruefen=True wird
    ein Fehlschlag zu einem Abbruch - mit dem, was das Programm gesagt hat."""
    try:
        r = subprocess.run(befehl, input=eingabe, capture_output=True, text=True,
                           timeout=zeit_s, env=env, cwd=cwd)
    except FileNotFoundError:
        raise Abbruch("%s ist nicht installiert." % befehl[0])
    except subprocess.TimeoutExpired:
        raise Abbruch("%s lief länger als %d s und wurde abgebrochen."
                      % (" ".join(befehl[:3]), zeit_s))
    ausgabe = (r.stdout or "") + (r.stderr or "")
    if pruefen and r.returncode != 0:
        raise Abbruch("%s ging nicht:\n%s" % (" ".join(befehl[:4]), kern_der_meldung(ausgabe)))
    return r.returncode, ausgabe


def mit_ausgabe(befehl, env=None, cwd=None):
    """Fuehrt aus und laesst die Ausgabe durchlaufen (lange Vorgaenge)."""
    r = subprocess.run(befehl, env=env, cwd=cwd)
    return r.returncode


RAUSCHEN = re.compile(r"Pulling|Pulled|Download|Extracting|Waiting|Verifying|Pull complete|"
                      r"Already exists|fs layer|Building|Built|Creating|Created|Starting|"
                      r"Started|Running|Recreate|Stopping|Stopped|Removing|Removed|^\s*#\d|^\s*$")


def kern_der_meldung(ausgabe, zeilen=6):
    """Die letzten Zeilen, die etwas sagen - ohne den Fortschritt von docker."""
    wichtig = [z for z in ausgabe.splitlines() if not RAUSCHEN.search(z)]
    return "\n".join(("    " + z) for z in (wichtig or ["(keine Meldung)"])[-zeilen:])


def da():
    """Laeuft Docker, und ist compose neu genug?"""
    lauf(["docker", "info", "--format", "{{.ServerVersion}}"], zeit_s=30)
    _, v = lauf(["docker", "compose", "version", "--short"], zeit_s=30)
    v = v.strip().lstrip("v")
    teile = [int(x) for x in re.findall(r"\d+", v)[:3]] + [0, 0, 0]
    if teile[:3] < [2, 24, 4]:
        raise Abbruch("docker compose %s ist zu alt - gebraucht wird 2.24.4 oder neuer "
                      "(fuer '!reset').  apt install docker-compose-plugin" % v)
    return v


# ---------------------------------------------------------- Unterbau
def unterbau_env():
    """Die Werte fuer docker-compose.yml des Unterbaus."""
    k = orte.konf()
    g = orte.geheimnisse()
    env = dict(os.environ)
    env.update(k)
    env.update(g)
    env["PROLO_VERSION"] = orte.version()
    env["PROLO_VAR"] = orte.VAR
    env["PROLO_DOMAIN_RE"] = re.escape(k["PROLO_DOMAIN"])
    return env


def unterbau_befehl(*args):
    dateien = ["-f", os.path.join(orte.REPO, "docker-compose.yml")]
    if os.path.isfile(orte.NETZE_YML):
        dateien += ["-f", orte.NETZE_YML]
    return ["docker", "compose", "-p", UNTERBAU, "--project-directory", orte.REPO,
            *dateien, *args]


def unterbau(*args, zeit_s=900, pruefen=True):
    return lauf(unterbau_befehl(*args), env=unterbau_env(), zeit_s=zeit_s, pruefen=pruefen)


# ------------------------------------------------------------- Tools
def tool_ordner(name):
    return os.path.join(orte.TOOLS, name)


def basis_in(app):
    """Die Compose-Datei in einem Ordner - in der Reihenfolge, in der auch
    docker compose sucht. None, wenn es keine gibt."""
    for n in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"):
        if os.path.isfile(os.path.join(app, n)):
            return os.path.join(app, n)
    return None


def tool_basisdatei(name):
    """Die Compose-Datei des Tools selbst (vom Hersteller, aus Git oder von
    prolo erzeugt) - sie liegt immer in app/."""
    app = os.path.join(tool_ordner(name), "app")
    basis = basis_in(app)
    if basis is None:
        raise Abbruch("In %s liegt keine Compose-Datei." % app)
    return basis


def tool_befehl(name, *args):
    app = os.path.join(tool_ordner(name), "app")
    dateien = ["-f", tool_basisdatei(name)]
    zusatz = os.path.join(tool_ordner(name), "prolo.override.yml")
    if os.path.isfile(zusatz):
        dateien += ["-f", zusatz]
    return ["docker", "compose", "-p", name, "--project-directory", app, *dateien, *args]


def tool(name, *args, zeit_s=900, pruefen=True):
    return lauf(tool_befehl(name, *args), cwd=os.path.join(tool_ordner(name), "app"),
                zeit_s=zeit_s, pruefen=pruefen)


def konfig_json(befehl, cwd=None, env=None):
    """docker compose config als JSON - was Compose selbst versteht, ist die
    Wahrheit ueber ein Projekt, nicht eine einzelne Datei."""
    _, aus = lauf(befehl + ["config", "--format", "json"], cwd=cwd, env=env, zeit_s=120)
    try:
        return json.loads(aus[aus.index("{"):])
    except ValueError:
        raise Abbruch("docker compose config lieferte kein JSON:\n" + kern_der_meldung(aus))


# -------------------------------------------------------- Container
def container(projekt=None):
    """Alle Container (auch angehaltene) als Liste von dicts:
    projekt, dienst, name, zustand (running/exited/...), gesundheit, abbild."""
    # Nur die Felder, die gebraucht werden. Mit "{{json .}}" berechnet Docker
    # fuer jeden Container die Groesse (Feld Size) - langsam, und es scheitert
    # an einem Container, der gerade entsteht: "snapshotter.Usage failed".
    # Gemessen beim Anlegen eines Tools ueber die Admin-Seite.
    format_ = "\t".join(("{{.ID}}", "{{.Names}}", "{{.State}}", "{{.Status}}", "{{.Image}}",
                         '{{.Label "com.docker.compose.project"}}',
                         '{{.Label "com.docker.compose.service"}}'))
    _, aus = lauf(["docker", "ps", "-a", "--no-trunc", "--format", format_], zeit_s=60)
    liste = []
    for zeile in aus.splitlines():
        teile = zeile.split("\t")
        if len(teile) != 7:
            continue
        cid, name, zust, status, abbild, projekt_, dienst = teile
        gesundheit = ("krank" if "(unhealthy)" in status else
                      "startet" if "health: starting" in status else
                      "gesund" if "(healthy)" in status else "")
        eintrag = {"projekt": projekt_, "dienst": dienst, "name": name, "id": cid,
                   "zustand": zust, "status": status, "gesundheit": gesundheit, "abbild": abbild}
        if projekt is None or eintrag["projekt"] == projekt:
            liste.append(eintrag)
    return liste


def zustand(liste):
    """Ein Wort fuer eine Gruppe von Containern."""
    if not liste:
        return "aus"
    laufen = [c for c in liste if c["zustand"] == "running"]
    if not laufen:
        return "aus"
    if len(laufen) < len(liste):
        return "teilweise"
    if any(c["gesundheit"] == "krank" for c in laufen):
        return "krank"
    if any(c["gesundheit"] == "startet" for c in laufen):
        return "startet"
    return "gesund" if any(c["gesundheit"] == "gesund" for c in laufen) else "laeuft"


def mounts(projekt):
    """Was die Container eines Projekts einhaengen: benannte Volumes und
    Bind-Mounts, je einmal. [{art: volume|bind, name|quelle, ziel, dienst}]"""
    ids = [c["id"] for c in container(projekt)]
    if not ids:
        return []
    _, aus = lauf(["docker", "inspect", *ids], zeit_s=60)
    gesehen, liste = set(), []
    for c in json.loads(aus):
        dienst = (c.get("Config", {}).get("Labels") or {}).get("com.docker.compose.service", "")
        for m in c.get("Mounts") or []:
            if m.get("Type") == "volume":
                schluessel = ("volume", m.get("Name"))
                eintrag = {"art": "volume", "name": m.get("Name"), "ziel": m.get("Destination"),
                           "dienst": dienst}
            elif m.get("Type") == "bind":
                schluessel = ("bind", m.get("Source"))
                eintrag = {"art": "bind", "quelle": m.get("Source"), "ziel": m.get("Destination"),
                           "dienst": dienst}
            else:
                continue
            if schluessel not in gesehen:
                gesehen.add(schluessel)
                liste.append(eintrag)
    return liste


def volume_labels(name):
    rc, aus = lauf(["docker", "volume", "inspect", name, "--format", "{{json .Labels}}"],
                   pruefen=False, zeit_s=30)
    if rc != 0:
        return None
    try:
        return json.loads(aus) or {}
    except ValueError:
        return {}


def netz_anlegen(name):
    rc, _ = lauf(["docker", "network", "inspect", name], pruefen=False, zeit_s=30)
    if rc == 0:
        return False
    lauf(["docker", "network", "create", "--label", "prolo.netz=tool", name], zeit_s=60)
    return True


def netz_entfernen(name):
    rc, _ = lauf(["docker", "network", "inspect", name], pruefen=False, zeit_s=30)
    if rc == 0:
        lauf(["docker", "network", "rm", name], zeit_s=60, pruefen=False)
