"""prolo agent - der Arm der Admin-Seite auf dem Server.

Die Admin-Seite hat keinen Zugriff auf Docker: wer den hat, hat root, und
eine Webseite ist die Stelle, an der man am ehesten hereinkommt. Sie legt
stattdessen AUFTRAEGE ab:

    /var/lib/prolo/agent/ein/<kennung>.json     schreibt die Admin-Seite
    /var/lib/prolo/agent/aus/<kennung>.json     Stand und Ergebnis
    /var/lib/prolo/agent/aus/<kennung>.log      die Ausgabe von prolo
    /var/lib/prolo/agent/aus/status.json        alle 30 s neu

Dieser Agent laeuft als root (systemd: prolo-agent.service), prueft jeden
Auftrag mit kern/auftrag.py - derselben Datei, die auch die Seite benutzt -
und fuehrt nur aus, was dort erlaubt ist: ueber prolo, als Liste von
Argumenten, nie ueber eine Shell. Einer nach dem anderen.
"""
import datetime
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time

from . import auftrag, orte, status, unterbau

POLL_S = 2
STATUS_S = 30
FETCH_S = 3600
BEHALTEN = 300

_halt = threading.Event()


def jetzt():
    # Mit Doppelpunkt im Versatz (+02:00) - das versteht auch der Browser.
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def aus_schreiben(name, text):
    """Eine Datei in aus/: root schreibt, die Admin-Seite (Gruppe) liest."""
    pfad = os.path.join(orte.AUSGANG, name)
    orte.datei_schreiben(pfad, text, 0o640)
    if orte.ist_root():
        os.chown(pfad, 0, orte.ADMIN_UID)


def lage_schreiben(lage):
    aus_schreiben(lage["kennung"] + ".json", json.dumps(lage, ensure_ascii=False, indent=1))


def lesen(pfad):
    """Die Auftragsdatei lesen - ohne einem Symlink zu folgen, nur eine
    gewoehnliche Datei, nur bis zur Grenze."""
    fd = os.open(pfad, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise auftrag.Ungueltig("keine gewöhnliche Datei")
        if st.st_size > auftrag.MAX_AUFTRAG:
            raise auftrag.Ungueltig("zu groß")
        roh = os.read(fd, auftrag.MAX_AUFTRAG + 1)
    finally:
        os.close(fd)
    try:
        return json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise auftrag.Ungueltig("kein JSON")


def ausfuehren(kennung, daten):
    lage = {"kennung": kennung, "art": str(daten.get("art", ""))[:40] if isinstance(daten, dict) else "",
            "wer": str((daten or {}).get("wer", "") if isinstance(daten, dict) else "")[:100],
            "eingang": str((daten or {}).get("zeit", "") if isinstance(daten, dict) else "")[:40],
            "beginn": jetzt(), "status": "laeuft"}
    try:
        if isinstance(daten, dict) and daten.get("_fehler"):
            raise auftrag.Ungueltig("Auftragsdatei: %s" % daten["_fehler"])
        art, f = auftrag.pruefen(daten)
    except auftrag.Ungueltig as u:
        lage.update(status="abgelehnt", ende=jetzt(), meldung=str(u))
        lage_schreiben(lage)
        return
    lage["titel"] = auftrag.ARTEN[art][2]
    lage["felder"] = {k: v for k, v in f.items() if k not in ("compose", "env") and v}
    lage_schreiben(lage)
    tmp = os.path.join(orte.AGENT, "tmp-" + kennung)
    os.makedirs(tmp, mode=0o700, exist_ok=True)
    datei = {}
    try:
        if f.get("compose"):
            datei["compose"] = os.path.join(tmp, "docker-compose.yml")
            orte.datei_schreiben(datei["compose"], f["compose"], 0o600)
        if f.get("env"):
            datei["env"] = os.path.join(tmp, "variablen.env")
            orte.datei_schreiben(datei["env"], f["env"], 0o600)
        argv = auftrag.argumente(art, f, datei)
        log = os.path.join(orte.AUSGANG, kennung + ".log")
        with open(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640), "wb") as aus:
            if orte.ist_root():
                os.chown(log, 0, orte.ADMIN_UID)
            # Die Hilfsdateien des Agenten nur mit Namen - der Pfad sagt niemandem etwas.
            dateien = set(datei.values())
            aus.write(("$ prolo %s\n\n" % " ".join(os.path.basename(a) if a in dateien else a
                                                  for a in argv)).encode())
            aus.flush()
            env = dict(os.environ, NO_COLOR="1", PYTHONUNBUFFERED="1", PROLO_AGENT="1")
            p = subprocess.Popen([sys.executable, os.path.join(orte.REPO, "prolo"), *argv],
                                 stdout=aus, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env=env, start_new_session=True)
            try:
                rc = p.wait(timeout=auftrag.ARTEN[art][3] * 60)
                lage.update(status="ok" if rc == 0 else "fehler", rc=rc)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(30)
                lage.update(status="fehler", meldung="Zeit abgelaufen (%d Minuten)"
                            % auftrag.ARTEN[art][3])
    except Exception as e:      # der Agent selbst darf nicht fallen
        lage.update(status="fehler", meldung="Agent: %s" % e)
    finally:
        for n in os.listdir(tmp):
            os.remove(os.path.join(tmp, n))
        os.rmdir(tmp)
    # Erst den Stand, dann "fertig": wer auf "Zum Tool" klickt, sobald der
    # Auftrag fertig ist, soll das neue Tool schon finden (gemessen: 404).
    status_schreiben()
    lage["ende"] = jetzt()
    lage_schreiben(lage)


def naechster():
    try:
        namen = sorted(n for n in os.listdir(orte.EINGANG) if n.endswith(".json"))
    except FileNotFoundError:
        return None
    for n in namen:
        pfad = os.path.join(orte.EINGANG, n)
        kennung = n[:-5]
        if not auftrag.KENNUNG.fullmatch(kennung):
            os.remove(pfad)
            continue
        try:
            daten = lesen(pfad)
        except (auftrag.Ungueltig, OSError) as e:
            daten = {"art": "?", "_fehler": str(e)}
        finally:
            # Sofort aus dem Eingang - sonst liefe er nach einem Neustart doppelt.
            try:
                os.remove(pfad)
            except FileNotFoundError:
                pass
        return kennung, daten
    return None


def aufraeumen():
    """Alte Auftraege weg, und was beim letzten Lauf 'laeuft' war, ist es
    nicht mehr."""
    try:
        alle = sorted(n for n in os.listdir(orte.AUSGANG)
                      if auftrag.KENNUNG.fullmatch(n.split(".")[0]) and n.endswith(".json"))
    except FileNotFoundError:
        return
    for n in alle:
        try:
            with open(os.path.join(orte.AUSGANG, n), encoding="utf-8") as f:
                lage = json.load(f)
        except (OSError, ValueError):
            continue
        if lage.get("status") == "laeuft":
            lage.update(status="fehler", ende=jetzt(),
                        meldung="abgebrochen - der Agent wurde neu gestartet")
            lage_schreiben(lage)
    for n in alle[:-BEHALTEN] if len(alle) > BEHALTEN else []:
        for endung in (".json", ".log"):
            try:
                os.remove(os.path.join(orte.AUSGANG, n[:-5] + endung))
            except FileNotFoundError:
                pass


def status_schreiben():
    try:
        s = status.sammeln()
    except Exception as e:
        s = {"zeit": jetzt(), "fehler": "Status: %s" % e, "hinweise": []}
    s["agent"] = {"zeit": jetzt(), "pid": os.getpid()}
    aus_schreiben("status.json", json.dumps(s, ensure_ascii=False))


def laufen():
    orte.root_noetig("agent")
    for p in (orte.EINGANG, orte.AUSGANG):
        if not os.path.isdir(p):
            raise orte.Abbruch("%s fehlt. Erst:  sudo prolo einrichten" % p)
    signal.signal(signal.SIGTERM, lambda *_: _halt.set())
    print("prolo agent läuft (Eingang %s)" % orte.EINGANG, flush=True)
    aufraeumen()
    if os.path.exists(unterbau.NEUSTART_FLAGGE):
        os.remove(unterbau.NEUSTART_FLAGGE)
    arbeit = None
    letzter_status = 0.0
    letzter_fetch = 0.0
    while not _halt.is_set():
        if arbeit is None or not arbeit.is_alive():
            if arbeit is not None:
                arbeit = None
                letzter_status = 0.0          # Ergebnis sofort sichtbar machen
                aufraeumen()
            if os.path.exists(unterbau.NEUSTART_FLAGGE):
                print("Neuer Code - der Agent startet neu.", flush=True)
                os.remove(unterbau.NEUSTART_FLAGGE)
                return 0
            n = naechster()
            if n:
                print("Auftrag %s: %s" % (n[0], n[1].get("art") if isinstance(n[1], dict) else "?"),
                      flush=True)
                arbeit = threading.Thread(target=ausfuehren, args=n, daemon=True)
                arbeit.start()
                letzter_status = 0.0
        if time.time() - letzter_fetch > FETCH_S:
            letzter_fetch = time.time()
            unterbau.git_lage(holen=True)
        if time.time() - letzter_status > STATUS_S:
            letzter_status = time.time()
            status_schreiben()
        _halt.wait(POLL_S)
    return 0
