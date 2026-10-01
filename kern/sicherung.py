"""Sicherung und Wiederherstellung.

Ein Stand ist ein Ordner /opt/backup/<JJJJ-MM-TT_hhmmss>/ mit:

    MANIFEST.json                       was drin ist, Pruefsummen, Ergebnis
    unterbau-dateien.tar.gz.age         /etc/prolo und die Zertifikate
    unterbau-vol-<volume>.tar.gz.age    Authentik (Datenbank, Medien), Admin
    tool-<name>.tar.gz.age              der Ordner /opt/tools/<name>
    tool-<name>-vol-<volume>.tar.gz.age je Volume des Tools

So geht es, fuer jedes Tool und den Unterbau gleich:

  1. anhalten, was Daten schreibt - eine Datenbank, die laeuft, laesst
     sich nicht verlaesslich kopieren
  2. packen und mit age verschluesseln (oeffentlicher Schluessel)
  3. wieder starten, was vorher lief
  4. JEDES Stueck wieder entschluesseln und vollstaendig lesen - erst
     dann gilt es als gesichert. Eine Sicherung, die sich nicht lesen
     laesst, ist keine.

Der Stand entsteht als .laufend-<stand> und wird erst am Ende umbenannt:
ein abgebrochener Lauf sieht nie aus wie eine Sicherung.
"""
import datetime
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

from . import docker, orte, tools
from .orte import Abbruch

FORMAT = 1
# Was vom Unterbau als Datei gesichert wird - alles andere entsteht neu.
UNTERBAU_DIENSTE = ("authentik-server", "authentik-worker", "authentik-db", "admin")
MIN_FREI = 1024 ** 3
BEHALTEN_MINDESTENS = 3


def jetzt():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def stand_name():
    return time.strftime("%Y-%m-%d_%H%M%S")


# ------------------------------------------------------- Schluessel
def schluessel_anlegen(vorhanden=None):
    """Den Schluessel fuer die Sicherung: geheimer Teil in /etc/prolo/backup.key
    (nur root), oeffentlicher in backup.pub. Mit 'vorhanden' wird ein
    mitgebrachter Schluessel uebernommen - nach einem Umzug bleibt es dann
    bei EINEM Schluessel fuer alte und neue Staende."""
    if os.path.isfile(orte.SCHLUESSEL) and os.path.isfile(orte.SCHLUESSEL_PUB):
        if vorhanden:
            alt = pub_von(vorhanden)
            with open(orte.SCHLUESSEL_PUB, encoding="utf-8") as f:
                if f.read().strip() != alt:
                    raise Abbruch("Auf diesem Server liegt schon ein anderer Schlüssel (%s). "
                                  "Der mitgebrachte wird nicht über ihn geschrieben - mit "
                                  "'prolo restore --schluessel %s' lässt er sich trotzdem "
                                  "zum Entschlüsseln nutzen." % (orte.SCHLUESSEL, vorhanden))
        return False
    os.makedirs(orte.ETC, mode=0o700, exist_ok=True)
    if vorhanden:
        pub = pub_von(vorhanden)
        with open(vorhanden, encoding="utf-8") as f:
            orte.datei_schreiben(orte.SCHLUESSEL, f.read(), 0o600)
    else:
        neu = orte.SCHLUESSEL + ".neu"
        if os.path.exists(neu):
            os.remove(neu)
        docker.lauf(["age-keygen", "-o", neu], zeit_s=30)
        os.chmod(neu, 0o600)
        os.replace(neu, orte.SCHLUESSEL)
        pub = pub_von(orte.SCHLUESSEL)
    orte.datei_schreiben(orte.SCHLUESSEL_PUB, pub + "\n", 0o644)
    return True


def pub_von(schluessel):
    _, aus = docker.lauf(["age-keygen", "-y", schluessel], zeit_s=30)
    pub = aus.strip().splitlines()[-1] if aus.strip() else ""
    if not pub.startswith("age1"):
        raise Abbruch("%s ist kein age-Schluessel (age-keygen -y lieferte nichts)." % schluessel)
    return pub


# ----------------------------------------------------- Packen/Pruefen
def _pruefsumme(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def packen(quelle, ziel):
    """quelle (Befehl, der ein tar.gz nach stdout schreibt) -> age -> ziel.
    Gibt (sha256, bytes) zurueck oder wirft Abbruch mit der Meldung."""
    with tempfile.TemporaryFile() as fehl1, open(ziel + ".neu", "wb") as aus:
        p1 = subprocess.Popen(quelle, stdout=subprocess.PIPE, stderr=fehl1)
        p2 = subprocess.Popen(["age", "-R", orte.SCHLUESSEL_PUB], stdin=p1.stdout, stdout=aus,
                              stderr=subprocess.PIPE)
        p1.stdout.close()
        _, fehl2 = p2.communicate()
        rc1 = p1.wait()
        fehl1.seek(0)
        meldung = fehl1.read().decode("utf-8", "replace").strip()
    if rc1 != 0 or p2.returncode != 0:
        os.remove(ziel + ".neu")
        raise Abbruch("Packen ging nicht: %s" % (meldung or fehl2.decode("utf-8", "replace")
                                                  or "Rückgabe %d" % rc1)[-400:])
    os.chmod(ziel + ".neu", 0o600)
    os.replace(ziel + ".neu", ziel)
    return _pruefsumme(ziel), os.path.getsize(ziel)


def lesen_pruefen(datei, schluessel):
    """Entschluesseln und das ganze Archiv lesen. Gibt '' oder den Fehler."""
    p1 = subprocess.Popen(["age", "-d", "-i", schluessel, datei], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    p2 = subprocess.Popen(["tar", "-tzf", "-"], stdin=p1.stdout, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
    p1.stdout.close()
    _, f2 = p2.communicate()
    f1 = p1.stderr.read()
    p1.wait()
    if p1.returncode != 0:
        return "entschlüsseln: %s" % f1.decode("utf-8", "replace").strip()[-200:]
    if p2.returncode != 0:
        return "lesen: %s" % f2.decode("utf-8", "replace").strip()[-200:]
    return ""


def volume_befehl(name):
    return ["docker", "run", "--rm", "--network", "none", "-v", "%s:/v:ro" % name,
            orte.HILFSABBILD, "tar", "-czf", "-", "-C", "/v", "."]


# ----------------------------------------------------------- Sichern
class Lauf:
    def __init__(self, verz):
        self.verz = verz
        self.teile = []
        self.fehler = []
        self.nicht_gesichert = []

    def teil(self, datei, quelle, **angaben):
        print("    %s ..." % datei, end="", flush=True)
        t0 = time.time()
        try:
            summe, groesse = packen(quelle, os.path.join(self.verz, datei))
        except Abbruch as a:
            print(" FEHLER", flush=True)
            self.fehler.append("%s: %s" % (datei, a))
            return
        print(" %s (%.0f s)" % (groesse_text(groesse), time.time() - t0), flush=True)
        self.teile.append(dict(datei=datei, sha256=summe, bytes=groesse, **angaben))


def groesse_text(n):
    for einheit in ("B", "KB", "MB", "GB"):
        if n < 1024 or einheit == "GB":
            return ("%d %s" % (n, einheit)) if einheit == "B" else ("%.1f %s" % (n, einheit))
        n /= 1024.0
    return "%d" % n


def unterbau_sichern(lauf):
    orte.abschnitt("Unterbau")
    pfade = [os.path.relpath(orte.ETC, "/")]
    acme = os.path.join(orte.VAR, "traefik", "acme")
    if os.path.isdir(acme):
        pfade.append(os.path.relpath(acme, "/"))
    lauf.teil("unterbau-dateien.tar.gz.age",
              ["tar", "-czf", "-", "-C", "/",
               "--exclude=" + os.path.relpath(orte.SCHLUESSEL, "/"),
               "--exclude=*.neu", *pfade],
              art="dateien", bereich="unterbau", pfade=pfade)
    alle = docker.container(docker.UNTERBAU)
    vols = [m for m in docker.mounts(docker.UNTERBAU) if m["art"] == "volume"]
    laufend = [c["dienst"] for c in alle if c["zustand"] == "running"
               and c["dienst"] in UNTERBAU_DIENSTE]
    if laufend:
        print("  Halte an: %s" % ", ".join(laufend), flush=True)
        docker.unterbau("stop", "-t", "60", *laufend, zeit_s=300)
    try:
        for m in vols:
            lauf.teil("unterbau-vol-%s.tar.gz.age" % m["name"], volume_befehl(m["name"]),
                      art="volume", bereich="unterbau", volume=m["name"],
                      labels=docker.volume_labels(m["name"]) or {})
    finally:
        if laufend:
            print("  Starte wieder: %s" % ", ".join(laufend), flush=True)
            rc, aus = docker.unterbau("start", *laufend, zeit_s=600, pruefen=False)
            if rc != 0:
                lauf.fehler.append("Unterbau startete nicht wieder:\n" + docker.kern_der_meldung(aus))


def tool_sichern(lauf, name):
    orte.abschnitt("Tool %s" % name)
    alle = docker.container(name)
    ms = docker.mounts(name)
    ordner = os.path.realpath(docker.tool_ordner(name))
    for m in ms:
        if m["art"] == "bind" and not os.path.realpath(m["quelle"]).startswith(ordner + os.sep):
            lauf.nicht_gesichert.append({"tool": name, "pfad": m["quelle"]})
            orte.warnung("%s hängt %s ein - das liegt außerhalb von %s und wird NICHT "
                         "gesichert" % (name, m["quelle"], ordner))
    laufend = [c["id"] for c in alle if c["zustand"] == "running"]
    if laufend:
        print("  Halte an ...", flush=True)
        docker.tool(name, "stop", "-t", "60", zeit_s=300)
    try:
        lauf.teil("tool-%s.tar.gz.age" % name,
                  ["tar", "-czf", "-", "-C", orte.TOOLS, name],
                  art="ordner", bereich=name)
        for m in ms:
            if m["art"] == "volume":
                lauf.teil("tool-%s-vol-%s.tar.gz.age" % (name, m["name"]),
                          volume_befehl(m["name"]), art="volume", bereich=name,
                          volume=m["name"], labels=docker.volume_labels(m["name"]) or {})
    finally:
        if laufend:
            print("  Starte wieder ...", flush=True)
            rc, aus = docker.lauf(["docker", "start", *laufend], zeit_s=600, pruefen=False)
            if rc != 0:
                lauf.fehler.append("%s startete nicht wieder: %s" % (name, aus.strip()[-300:]))


def sichern(nur=None, grund="von Hand", unterbau=None):
    """Sichert den Unterbau und alle Tools (oder nur die genannten Tools).
    Gibt den Namen des Stands zurueck; wirft Abbruch, wenn etwas fehlt."""
    orte.root_noetig("backup")
    if not os.path.isfile(orte.SCHLUESSEL_PUB):
        raise Abbruch("Kein Sicherungsschlüssel (%s). Anlegen mit:  sudo prolo einrichten"
                      % orte.SCHLUESSEL_PUB)
    if nur:
        # Nur nachsehen, ob es das Tool gibt - nicht seine prolo.conf lesen:
        # auch ein Tool mit kaputter Einstellung muss sich sichern lassen.
        for n in nur:
            if n not in tools.namen():
                raise Abbruch("Ein Tool '%s' gibt es nicht. Installiert: %s"
                              % (n, ", ".join(tools.namen()) or "keine"))
    if unterbau is None:
        unterbau = nur is None
    with orte.sperre("backup"):
        os.makedirs(orte.BACKUP, mode=0o700, exist_ok=True)
        os.chmod(orte.BACKUP, 0o700)
        frei = shutil.disk_usage(orte.BACKUP).free
        if frei < MIN_FREI:
            raise Abbruch("Unter %s ist nur noch %s frei. Erst Platz schaffen (alte Stände: "
                          "prolo backup list)." % (orte.BACKUP, groesse_text(frei)))
        stand = stand_name()
        while os.path.exists(os.path.join(orte.BACKUP, stand)):
            time.sleep(1)
            stand = stand_name()
        verz = os.path.join(orte.BACKUP, ".laufend-" + stand)
        os.makedirs(verz, mode=0o700)
        lauf = Lauf(verz)
        welche = tools.namen() if nur is None else list(nur)
        print("Sichere nach %s/%s (%s)" % (orte.BACKUP, stand, grund), flush=True)
        try:
            if unterbau:
                unterbau_sichern(lauf)
            for n in welche:
                tool_sichern(lauf, n)
            orte.abschnitt("Prüfen: jedes Stück entschlüsseln und lesen")
            geprueft = pruefen_verz(verz, lauf.teile, lauf.fehler)
        except BaseException:
            shutil.rmtree(verz, ignore_errors=True)
            raise
        manifest = {"format": FORMAT, "stand": stand, "zeit": jetzt(), "grund": grund,
                    "version": orte.version(), "rechner": socket.gethostname(),
                    "domain": orte.env_lesen(orte.KONF).get("PROLO_DOMAIN", ""),
                    "unterbau": unterbau, "tools": welche, "teile": lauf.teile,
                    "nicht_gesichert": lauf.nicht_gesichert, "fehler": lauf.fehler,
                    "geprueft": geprueft,
                    "bytes": sum(t["bytes"] for t in lauf.teile)}
        orte.datei_schreiben(os.path.join(verz, "MANIFEST.json"),
                             json.dumps(manifest, ensure_ascii=False, indent=1), 0o600)
        ziel = os.path.join(orte.BACKUP, stand + ("" if not lauf.fehler else "-unvollstaendig"))
        os.rename(verz, ziel)
        status_merken(manifest, ziel)
        aufraeumen()
    if lauf.fehler:
        orte.abschnitt("Sicherung UNVOLLSTAENDIG")
        for f in lauf.fehler:
            orte.fehler(f)
        raise Abbruch("Die Sicherung %s ist unvollständig - Gründe oben." % os.path.basename(ziel))
    orte.abschnitt("Gesichert: %s" % stand)
    print("  %s, %d Teile, %s" % (groesse_text(manifest["bytes"]), len(lauf.teile),
                                   "jedes Stück entschlüsselt und gelesen" if geprueft == "ok"
                                   else "nur Prüfsummen (kein geheimer Schlüssel auf dem Server)"))
    return stand


def pruefen_verz(verz, teile, fehler, schluessel=None):
    """Prueft jedes Teil. Gibt 'ok', 'pruefsumme' oder 'fehler'."""
    schluessel = schluessel or (orte.SCHLUESSEL if os.path.isfile(orte.SCHLUESSEL) else None)
    ergebnis = "ok" if schluessel else "pruefsumme"
    for t in teile:
        pfad = os.path.join(verz, t["datei"])
        if not os.path.isfile(pfad):
            fehler.append("%s fehlt" % t["datei"])
            ergebnis = "fehler"
            continue
        if _pruefsumme(pfad) != t["sha256"]:
            fehler.append("%s: Prüfsumme stimmt nicht - die Datei wurde verändert" % t["datei"])
            ergebnis = "fehler"
            continue
        if schluessel:
            f = lesen_pruefen(pfad, schluessel)
            if f:
                fehler.append("%s: %s" % (t["datei"], f))
                ergebnis = "fehler"
                continue
        orte.ok(t["datei"])
    return ergebnis


def status_merken(manifest, ziel):
    try:
        with open(orte.SICHERUNG_JSON, encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    kurz = {k: manifest[k] for k in ("stand", "zeit", "grund", "bytes", "geprueft", "tools",
                                     "unterbau", "fehler", "nicht_gesichert")}
    kurz["ordner"] = os.path.basename(ziel)
    st["letzte"] = kurz
    if not manifest["fehler"] and manifest["unterbau"]:
        st["letzte_vollstaendige"] = kurz
    orte.datei_schreiben(orte.SICHERUNG_JSON, json.dumps(st, ensure_ascii=False, indent=1), 0o644)


# ----------------------------------------------------------- Bestand
def staende():
    """Alle Staende, neueste zuerst: [(ordnername, manifest|None)]."""
    try:
        namen = os.listdir(orte.BACKUP)
    except FileNotFoundError:
        return []
    liste = []
    for n in sorted(namen, reverse=True):
        p = os.path.join(orte.BACKUP, n)
        if n.startswith(".") or not os.path.isdir(p):
            continue
        try:
            with open(os.path.join(p, "MANIFEST.json"), encoding="utf-8") as f:
                liste.append((n, json.load(f)))
        except (OSError, ValueError):
            liste.append((n, None))
    return liste


def aufraeumen(heute=None):
    """Behaelt alles juenger als BACKUP_TAGE - und immer die drei neuesten
    vollstaendigen. Halbe Laeufe (.laufend-*) aelter als ein Tag gehen weg."""
    tage = int(orte.konf()["BACKUP_TAGE"])
    heute = heute or datetime.datetime.now()
    vollstaendig = 0
    for n, m in staende():
        try:
            datum = datetime.datetime.strptime(n[:17], "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue
        gut = m is not None and not m.get("fehler") and n == m.get("stand")
        if gut:
            vollstaendig += 1
            if vollstaendig <= BEHALTEN_MINDESTENS:
                continue
        if (heute - datum).days >= tage:
            shutil.rmtree(os.path.join(orte.BACKUP, n), ignore_errors=True)
            print("  alter Stand entfernt: %s" % n)
    for n in os.listdir(orte.BACKUP):
        p = os.path.join(orte.BACKUP, n)
        if n.startswith(".laufend-") and time.time() - os.path.getmtime(p) > 86400:
            shutil.rmtree(p, ignore_errors=True)


def liste():
    alle = staende()
    if not alle:
        print("Noch keine Sicherung unter %s. Jetzt sichern:  sudo prolo backup" % orte.BACKUP)
        return
    print("%-28s %-9s %-11s %s" % ("STAND", "GROESSE", "GEPRUEFT", "INHALT"))
    for n, m in alle:
        if m is None:
            print("%-28s %s" % (n, "(ohne MANIFEST.json - unbrauchbar)"))
            continue
        inhalt = (["Unterbau"] if m.get("unterbau") else []) + list(m.get("tools") or [])
        print("%-28s %-9s %-11s %s%s" % (n, groesse_text(m.get("bytes", 0)), m.get("geprueft", "?"),
                                         ", ".join(inhalt) or "-",
                                         "  [%s]" % m["grund"] if m.get("grund") else ""))


def stand_finden(stand=None, tool=None):
    """Der Ordner eines Stands - ohne Angabe der neueste, der passt."""
    for n, m in staende():
        if m is None or m.get("fehler"):
            if stand and n == stand:
                raise Abbruch("Der Stand %s ist unvollständig oder ohne MANIFEST.json." % n)
            continue
        if stand and n != stand:
            continue
        if tool and tool not in (m.get("tools") or []):
            if stand:
                raise Abbruch("Im Stand %s ist das Tool %s nicht enthalten. Darin: %s"
                              % (n, tool, ", ".join(m.get("tools") or []) or "keine Tools"))
            continue
        return os.path.join(orte.BACKUP, n), m
    raise Abbruch("Keinen passenden Stand gefunden%s. Vorhanden:  prolo backup list"
                  % ((" für " + tool) if tool else ""))


def pruefen(stand=None, schluessel=None):
    verz, m = stand_finden(stand)
    fehler = []
    orte.abschnitt("Prüfe %s" % os.path.basename(verz))
    ergebnis = pruefen_verz(verz, m["teile"], fehler, schluessel)
    for f in fehler:
        orte.fehler(f)
    if fehler:
        raise Abbruch("Der Stand ist beschädigt.")
    print("  %s" % ("Alles lesbar." if ergebnis == "ok" else
                    "Prüfsummen stimmen. Zum Entschlüsseln fehlt der geheime Schlüssel: "
                    "--schluessel <datei>"))


# ------------------------------------------------------ Zurueckholen
def entpacken_nach(datei, schluessel, befehl):
    """age -d datei | befehl (liest tar.gz von stdin)."""
    p1 = subprocess.Popen(["age", "-d", "-i", schluessel, datei], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    p2 = subprocess.Popen(befehl, stdin=p1.stdout, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    p1.stdout.close()
    aus, _ = p2.communicate()
    f1 = p1.stderr.read()
    p1.wait()
    if p1.returncode != 0 or p2.returncode != 0:
        raise Abbruch("Entpacken von %s ging nicht: %s"
                      % (os.path.basename(datei), (f1 + (aus or b"")).decode("utf-8", "replace")[-300:]))


def volume_zurueck(teil, verz, schluessel):
    name = teil["volume"]
    docker.lauf(["docker", "volume", "rm", "-f", name], zeit_s=120, pruefen=False)
    befehl = ["docker", "volume", "create"]
    for k, v in (teil.get("labels") or {}).items():
        befehl += ["--label", "%s=%s" % (k, v)]
    docker.lauf(befehl + [name], zeit_s=60)
    entpacken_nach(os.path.join(verz, teil["datei"]), schluessel,
                   ["docker", "run", "--rm", "-i", "--network", "none", "-v", "%s:/v" % name,
                    orte.HILFSABBILD, "tar", "-xzf", "-", "-C", "/v"])
    orte.ok("Volume %s" % name)


def tool_zurueck(name, verz, m, schluessel):
    orte.abschnitt("Tool %s zurückholen" % name)
    teile = [t for t in m["teile"] if t["bereich"] == name]
    ordner = next((t for t in teile if t["art"] == "ordner"), None)
    if ordner is None:
        raise Abbruch("Im Stand fehlt der Ordner von %s." % name)
    ziel = docker.tool_ordner(name)
    alt = None
    if os.path.isdir(ziel):
        docker.tool(name, "down", "--remove-orphans", zeit_s=600, pruefen=False)
        alt = os.path.join(orte.TOOLS, ".alt-%s-%s" % (name, stand_name()))
        os.rename(ziel, alt)
    try:
        os.makedirs(orte.TOOLS, exist_ok=True)
        entpacken_nach(os.path.join(verz, ordner["datei"]), schluessel,
                       ["tar", "-xzf", "-", "-C", orte.TOOLS])
        orte.ok("Ordner %s" % ziel)
        # Ein Volume laesst sich nur ersetzen, wenn kein Container es haelt.
        docker.tool(name, "down", "--remove-orphans", zeit_s=600, pruefen=False)
        for t in teile:
            if t["art"] == "volume":
                volume_zurueck(t, verz, schluessel)
        docker.netz_anlegen(tools.netzname(name))
        tools.netze_schreiben()
        tools.traefik_verbinden(name)
        docker.tool(name, "up", "-d", "--remove-orphans", zeit_s=1800)
        z = tools.warten(name)
    except BaseException:
        if alt and not os.path.exists(ziel):
            os.rename(alt, ziel)
            alt = None
        raise
    if alt:
        shutil.rmtree(alt, ignore_errors=True)
    orte.ok("%s läuft wieder (%s)" % (name, z))


def unterbau_zurueck(verz, m, schluessel):
    from . import unterbau
    orte.abschnitt("Unterbau zurückholen")
    teile = [t for t in m["teile"] if t["bereich"] == "unterbau"]
    dateien = next((t for t in teile if t["art"] == "dateien"), None)
    if dateien is None:
        raise Abbruch("Im Stand fehlen die Dateien des Unterbaus.")
    with tempfile.TemporaryDirectory(dir=orte.VAR) as tmp:
        entpacken_nach(os.path.join(verz, dateien["datei"]), schluessel,
                       ["tar", "-xzf", "-", "-C", tmp])
        etc_alt = os.path.join(tmp, dateien["pfade"][0])
        for n in ("prolo.conf", "geheim.env"):
            if os.path.isfile(os.path.join(etc_alt, n)):
                with open(os.path.join(etc_alt, n), encoding="utf-8") as f:
                    orte.datei_schreiben(os.path.join(orte.ETC, n), f.read(), 0o600)
                orte.ok(os.path.join(orte.ETC, n))
        if len(dateien["pfade"]) > 1:
            acme_alt = os.path.join(tmp, dateien["pfade"][1])
            acme = os.path.join(orte.VAR, "traefik", "acme")
            if os.path.isdir(acme_alt):
                shutil.rmtree(acme, ignore_errors=True)
                shutil.copytree(acme_alt, acme)
                os.chmod(acme, 0o700)
                orte.ok("Zertifikate")
    # Erst alle Container weg, die die Volumes halten - dann ersetzen.
    docker.unterbau("rm", "-s", "-f", *UNTERBAU_DIENSTE, zeit_s=600, pruefen=False)
    for t in teile:
        if t["art"] == "volume":
            volume_zurueck(t, verz, schluessel)
    unterbau.hochfahren()


def zurueckholen(stand=None, tool=None, nur_unterbau=False, schluessel=None, ja=False,
                 sichern_vorher=True):
    orte.root_noetig("restore")
    schluessel = schluessel or orte.SCHLUESSEL
    if not os.path.isfile(schluessel):
        raise Abbruch("Zum Entschlüsseln fehlt der geheime Schlüssel. Mitgeben:  "
                      "--schluessel <datei>")
    verz, m = stand_finden(stand, tool)
    stand = os.path.basename(verz)
    if tool:
        bereiche = [tool]
    elif nur_unterbau:
        bereiche = ["unterbau"]
    else:
        bereiche = (["unterbau"] if m.get("unterbau") else []) + list(m.get("tools") or [])
    if "unterbau" in bereiche and not m.get("unterbau"):
        raise Abbruch("Der Stand %s enthält den Unterbau nicht (nur Tools)." % stand)
    orte.abschnitt("Zurückholen aus %s (%s)" % (stand, m.get("grund", "")))
    print("  Ersetzt wird: %s" % ", ".join(bereiche))
    print("  Was jetzt dort liegt, wird vorher gesichert." if sichern_vorher else
          "  Ohne Sicherung vorher - was jetzt dort liegt, ist danach weg.")
    if not ja and not tools.frage("Weiter?"):
        raise Abbruch("Nichts verändert.")
    with orte.sperre("restore"):
        fehler = []
        orte.abschnitt("Erst pruefen, dann anfassen")
        pruefen_verz(verz, [t for t in m["teile"] if t["bereich"] in bereiche], fehler, schluessel)
        if fehler:
            for f in fehler:
                orte.fehler(f)
            raise Abbruch("Der Stand ist beschädigt - es wurde nichts angefasst.")
        if sichern_vorher:
            vorhanden = [b for b in bereiche if b != "unterbau" and b in tools.namen()]
            if "unterbau" in bereiche or vorhanden:
                try:
                    sichern(nur=vorhanden, grund="vor dem Zurückholen von %s" % stand,
                            unterbau="unterbau" in bereiche)
                except Abbruch as a:
                    raise Abbruch("Den jetzigen Stand konnte ich nicht sichern - darum wurde "
                                  "nichts angefasst.\n  %s\n  Wenn der jetzige Stand ohnehin "
                                  "verloren ist, ohne Sicherung vorher:\n    sudo prolo restore "
                                  "%s%s --ohne-sicherung" % (a, stand, (" --tool " + tool) if tool
                                                             else " --unterbau" if nur_unterbau
                                                             else ""))
        if "unterbau" in bereiche:
            unterbau_zurueck(verz, m, schluessel)
        for b in bereiche:
            if b != "unterbau":
                tool_zurueck(b, verz, m, schluessel)
    orte.abschnitt("Zurückgeholt: %s" % ", ".join(bereiche))
