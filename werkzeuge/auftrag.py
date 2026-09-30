#!/usr/bin/env python3
"""werkzeuge/auftrag.py - das Auftragsbuch (A-01)

Die Admin-Seite soll Werkzeuge starten, anhalten, aktualisieren und
anlegen koennen. Der kuerzeste Weg dahin - dem Container schreibenden
Zugriff auf den Docker-Socket geben - ist auch der kuerzeste Weg zur
Uebernahme des ganzen Servers: wer den Socket schreibend hat, hat root.
Eine Webseite ist genau die Stelle, an der man am ehesten hereinkommt.

Darum spricht die Seite nicht mit Docker, sondern schreibt AUFTRAEGE:

    admin/auftraege/eingang/<kennung>.json    schreibt die Admin-Seite
    admin/auftraege/erledigt/<kennung>.json   Lage und Ergebnis
    admin/auftraege/erledigt/<kennung>.log    die Ausgabe von prolo
    admin/auftraege/erledigt/protokoll.jsonl  wer wann was - eine Zeile je Auftrag

Dieses Programm laeuft auf dem SERVER, als root, angestossen von systemd,
sobald in eingang/ etwas liegt (werkzeuge/systemd/). Es fuehrt nur aus,
was hier in ARTEN steht, und zwar ueber "prolo" - also mit allem, was
prolo ohnehin prueft: die Startsperre (offene Ports, Router ohne
Anmeldung), die Sicherung vor dem Aktualisieren, der Rueckweg.

Was in eingang/ liegt, ist FREMDE Eingabe (§11): geschrieben von einem
Container, der uebernommen sein koennte. Darum:
  - nur Dateinamen nach KENNUNG, nichts anderes wird geoeffnet
  - kein Symlink (O_NOFOLLOW), nur eine gewoehnliche Datei, hoechstens
    MAX_AUFTRAG_BYTE gross
  - nur bekannte Arten und Felder, jedes Feld gegen ein Muster
  - kein Shell-Aufruf: die Argumente gehen als Liste an prolo
  - was sich nicht verarbeiten laesst, wandert nach verworfen/ und wird
    protokolliert - liegen bleiben darf nichts, sonst stoesst systemd den
    Dienst in einer Schleife immer wieder an

Aufruf (root):
    auftrag.py abarbeiten     alles in eingang/ der Reihe nach ausfuehren
    auftrag.py einrichten     die Ordner mit den richtigen Besitzern anlegen
                              (--pruefen: nur nachsehen, 1 = es fehlt etwas)
    auftrag.py liste [n]      die letzten n Auftraege (Vorgabe 20)
"""
import datetime
import errno
import fcntl
import ipaddress
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading

HIER = os.path.dirname(os.path.realpath(__file__))
STACK = os.path.dirname(HIER)
BUCH = os.path.join(STACK, "admin", "auftraege")
EINGANG = os.path.join(BUCH, "eingang")
ERLEDIGT = os.path.join(BUCH, "erledigt")
VERWORFEN = os.path.join(BUCH, "verworfen")
PROTOKOLL = os.path.join(ERLEDIGT, "protokoll.jsonl")
PROLO = os.path.join(HIER, "prolo")

# Der Nutzer, unter dem die Admin-Seite im Container laeuft (admin/Dockerfile,
# useradd -u). Nur er darf in eingang/ schreiben. auftrag-pruefen.sh haelt
# die beiden Stellen zusammen.
ADMIN_UID = 10004

KENNUNG = re.compile(r"\d{8}-\d{6}-[0-9a-f]{8}")
WERKZEUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
NETZ = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
MAX_AUFTRAG_BYTE = 640 * 1024      # eine Compose-Datei, als JSON maskiert
MAX_COMPOSE = 256 * 1024
DIENST = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
# Geheimnisse kommen NIE ueber einen Auftrag - die wuerfelt prolo neu selbst.
GEHEIM = re.compile(r"PASS|SECRET|KEY|TOKEN|SALT|CREDENTIAL", re.I)
FREITEXT_MAX = 200
MAX_AUSGABE_BYTE = 1024 * 1024
MAX_WER = 100

# Was von der Seite aus nicht ANGEHALTEN werden darf: ohne diese Dienste
# gibt es keine Seite mehr, von der aus man sie wieder startet. Neu starten
# geht - danach sind sie wieder da. Anhalten geht auf dem Server.
KERN = ("traefik", "authentik", "socket-proxy", "admin")

# Was die Seite ueber die Werkzeuge wissen muss, die gerade NICHT laufen:
# ein angehaltenes Werkzeug hat keinen Container, und die Seite sieht nur
# Container. Ohne den Bestand verschwaende es nach "Anhalten" aus der
# Liste - samt dem Knopf, der es wieder startet.
BESTAND = os.path.join(ERLEDIGT, "bestand.json")
BESTAND_ALTER_S = 240
PLATTFORM = KERN + ("crowdsec",)
# Die Lage der Firewall (F-02), im selben Takt wie der Bestand - die Seite
# spricht nicht mit CrowdSec, sie liest, was prolo firewall hier ablegt.
FIREWALL = os.path.join(ERLEDIGT, "firewall.json")
FIREWALL_MAX_BYTE = 2 * 1024 * 1024
ADRESSE_MAX = 49
DAUER = re.compile(r"[1-9][0-9]{0,3}[mhd]")

MINUTE = 60
ARTEN = {
    # art: (Felder, Zeitgrenze in s, Argumente fuer prolo)
    "start":         (("werkzeug",), 10 * MINUTE, lambda a: ["start", a["werkzeug"]]),
    "neustart":      (("werkzeug",), 10 * MINUTE, lambda a: ["neustart", a["werkzeug"]]),
    "stop":          (("werkzeug",), 10 * MINUTE, lambda a: ["stop", a["werkzeug"]]),
    "pruefen":       (("werkzeug",), 10 * MINUTE, lambda a: ["pruefen", a["werkzeug"]]),
    "aktualisieren": (("werkzeug",), 60 * MINUTE, lambda a: ["aktualisieren", a["werkzeug"]]),
    "sichern":       ((),            60 * MINUTE, lambda a: ["sichern"]),
    "netz_anlegen":  (("netz",),      5 * MINUTE, lambda a: ["netze", "anlegen", a["netz"]]),
    # A-03: eine Compose-Datei ansehen (ohne Nebenwirkung) und daraus ein
    # Werkzeug anlegen. Die Datei selbst geht als Datei an prolo neu, nie
    # als Argument.
    "compose_pruefen": (("name", "compose"), 2 * MINUTE, None),
    "neu": (("name", "compose", "dienst", "port", "netz", "geteilt", "anmeldung", "grund",
             "werte"),
            5 * MINUTE, lambda a: neu_argumente(a)),
    # F-02: die Firewall. Entschieden wird in prolo firewall (werkzeuge/
    # firewall.py) - dort stehen die Regeln, welche Adresse gesperrt werden
    # darf. Hier nur die Form.
    "firewall_sperren": (("adresse", "dauer", "grund"), 2 * MINUTE,
                         lambda a: ["firewall", "sperren", a["adresse"], a["dauer"], a["grund"]]),
    "firewall_aufheben": (("adresse",), 2 * MINUTE,
                          lambda a: ["firewall", "aufheben", a["adresse"]]),
    "firewall_erlauben": (("adresse", "grund"), 2 * MINUTE,
                          lambda a: ["firewall", "erlauben", a["adresse"], a["grund"]]),
    "firewall_nicht_erlauben": (("adresse",), 2 * MINUTE,
                                lambda a: ["firewall", "nicht-mehr-erlauben", a["adresse"]]),
    "firewall_lesen": ((), 2 * MINUTE, lambda a: ["firewall"]),
}


def neu_argumente(a):
    befehl = ["neu", a["name"], "--compose", a["_datei"], "--anmeldung", a["anmeldung"]]
    if a["grund"]:
        befehl += ["--grund", a["grund"]]
    if a["dienst"]:
        befehl += ["--dienst", a["dienst"]]
    if a["port"]:
        befehl += ["--port", a["port"]]
    if a["netz"] and a["netz"] != "netz-" + a["name"]:
        befehl += ["--netz", a["netz"], "--geteilt", a["geteilt"]]
    else:
        befehl += ["--netz-neu"]
    for k in sorted(a["werte"]):
        befehl += ["--wert", "%s=%s" % (k, a["werte"][k])]
    return befehl
IMMER_ERLAUBT = ("art", "wer", "angelegt")

UMGEBUNG = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C.UTF-8",
    "TERM": "dumb",
    "NO_COLOR": "1",
}


class Abgelehnt(Exception):
    """Ein Auftrag, der nicht ausgefuehrt wird - mit dem Grund im Klartext."""


def jetzt():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def schreiben(pfad, text):
    """Erst daneben, dann umbenennen: die Seite liest nie eine halbe Datei."""
    neu = pfad + ".neu"
    with open(neu, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(neu, 0o644)
    os.replace(neu, pfad)


def lage_schreiben(kennung, lage):
    schreiben(os.path.join(ERLEDIGT, kennung + ".json"),
              json.dumps(lage, ensure_ascii=False, indent=1) + "\n")


def protokollieren(eintrag):
    with open(PROTOKOLL, "a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    os.chmod(PROTOKOLL, 0o644)


# ------------------------------------------------------------- Einlesen
def lesen(pfad):
    """Die Auftragsdatei lesen - ohne einem Symlink zu folgen und ohne mehr
    als MAX_AUFTRAG_BYTE anzunehmen."""
    try:
        fd = os.open(pfad, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise Abgelehnt("ist ein Verweis (Symlink), keine Datei")
        raise Abgelehnt("laesst sich nicht oeffnen (%s)" % e.strerror)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Abgelehnt("ist keine gewoehnliche Datei")
        if st.st_size > MAX_AUFTRAG_BYTE:
            raise Abgelehnt("ist zu gross (%d Byte, hoechstens %d)"
                            % (st.st_size, MAX_AUFTRAG_BYTE))
        roh = os.read(fd, MAX_AUFTRAG_BYTE + 1)
    finally:
        os.close(fd)
    if len(roh) > MAX_AUFTRAG_BYTE:
        raise Abgelehnt("ist zu gross")
    try:
        daten = json.loads(roh.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Abgelehnt("ist kein lesbares JSON")
    if not isinstance(daten, dict):
        raise Abgelehnt("ist kein JSON-Objekt")
    return daten


def werte_pruefen(werte):
    """Werte fuer Variablen der Herstellerdatei: keine Geheimnisse, keine
    Zeichen, die eine .env-Zeile zerbrechen."""
    if not isinstance(werte, dict) or len(werte) > 30:
        raise Abgelehnt("das Feld werte ist keine Liste von hoechstens 30 Werten")
    for k, v in werte.items():
        if not VARIABLE.fullmatch(k):
            raise Abgelehnt("%r ist kein Variablenname" % k[:40])
        if GEHEIM.search(k):
            raise Abgelehnt("%s ist ein Geheimnis - das wuerfelt prolo neu selbst" % k)
        if not isinstance(v, str) or len(v) > 500 or not v.isprintable() or "'" in v:
            raise Abgelehnt("der Wert fuer %s ist zu lang, hat Steuerzeichen oder ein '" % k)


def pruefen(daten):
    """Nur bekannte Arten, nur bekannte Felder, jedes gegen sein Muster."""
    art = daten.get("art")
    if not isinstance(art, str) or art not in ARTEN:
        raise Abgelehnt("unbekannte Art %r - moeglich: %s"
                        % (art, ", ".join(sorted(ARTEN))))
    felder, _, _ = ARTEN[art]
    fremd = sorted(set(daten) - set(felder) - set(IMMER_ERLAUBT))
    if fremd:
        raise Abgelehnt("unbekannte Felder: %s" % ", ".join(fremd))
    for feld in felder:
        if feld == "werte":
            werte_pruefen(daten.get(feld))
        elif not isinstance(daten.get(feld), str):
            raise Abgelehnt("das Feld %s fehlt" % feld)

    if "werkzeug" in felder:
        w = daten["werkzeug"]
        if not WERKZEUG.fullmatch(w):
            raise Abgelehnt("%r ist kein Werkzeugname (Kleinbuchstaben, Ziffern, "
                            "Bindestrich)" % w)
        compose = os.path.join(STACK, w, "docker-compose.yml")
        if not os.path.isfile(compose) or os.path.islink(os.path.join(STACK, w)):
            raise Abgelehnt("ein Werkzeug %s gibt es auf diesem Server nicht" % w)
        if art == "stop" and w in KERN:
            raise Abgelehnt(
                "%s haelt den Zugang offen - ohne ihn gibt es keine Seite mehr, "
                "von der aus man ihn wieder startet. Neu starten geht; anhalten "
                "auf dem Server: sudo prolo stop %s" % (w, w))
    if "netz" in felder and daten["netz"] and not NETZ.fullmatch(daten["netz"]):
        raise Abgelehnt("%r ist kein Netzname (Kleinbuchstaben, Ziffern, "
                        "Bindestrich)" % daten["netz"])
    if art == "netz_anlegen" and not daten["netz"]:
        raise Abgelehnt("das Feld netz ist leer")
    if "name" in felder:
        n = daten["name"]
        if not WERKZEUG.fullmatch(n):
            raise Abgelehnt("%r ist kein Werkzeugname (Kleinbuchstaben, Ziffern, "
                            "Bindestrich - er wird die Subdomain)" % n)
        if art == "neu" and os.path.lexists(os.path.join(STACK, n)):
            raise Abgelehnt("ein Werkzeug %s gibt es schon" % n)
    if "compose" in felder:
        if not daten["compose"].strip():
            raise Abgelehnt("die Compose-Datei ist leer")
        if len(daten["compose"].encode("utf-8")) > MAX_COMPOSE:
            raise Abgelehnt("die Compose-Datei ist groesser als %d KiB" % (MAX_COMPOSE // 1024))
    if "adresse" in felder:
        a = daten["adresse"]
        try:
            if len(a) > ADRESSE_MAX:
                raise ValueError
            ipaddress.ip_network(a, strict=False)
        except ValueError:
            raise Abgelehnt("%r ist keine Adresse und kein Netz" % a[:60])
    if "dauer" in felder and not DAUER.fullmatch(daten["dauer"]):
        raise Abgelehnt("%r ist keine Dauer (30m, 12h, 7d)" % daten["dauer"][:20])
    if art in ("firewall_sperren", "firewall_erlauben"):
        g = daten["grund"]
        if not g.strip() or len(g) > FREITEXT_MAX or not g.isprintable():
            raise Abgelehnt("ohne Grund, zu lang oder mit Steuerzeichen - der Grund "
                            "steht spaeter an der Sperre")
    if art == "neu":
        if daten["dienst"] and not DIENST.fullmatch(daten["dienst"]):
            raise Abgelehnt("%r ist kein Dienstname" % daten["dienst"])
        if daten["port"] and not (daten["port"].isdigit() and 0 < int(daten["port"]) < 65536):
            raise Abgelehnt("%r ist kein Port" % daten["port"])
        for feld in ("geteilt", "grund"):
            w = daten[feld]
            if len(w) > FREITEXT_MAX or not w.isprintable():
                raise Abgelehnt("das Feld %s ist zu lang oder hat Steuerzeichen" % feld)
        if daten["anmeldung"] not in ("authentik", "eigene"):
            raise Abgelehnt("anmeldung ist authentik oder eigene - ohne Vorgabe (§17a)")
        if daten["anmeldung"] == "eigene" and not daten["grund"].strip():
            raise Abgelehnt("eigene Anmeldung nur mit Grund (N-59)")
        if daten["netz"] and daten["netz"] != "netz-" + daten["name"] and not daten["geteilt"].strip():
            raise Abgelehnt("ein fremdes Netz nur mit Grund - es hebt die Abschottung auf (N-62)")

    wer = daten.get("wer", "")
    if not isinstance(wer, str) or len(wer) > MAX_WER or not wer.isprintable():
        raise Abgelehnt("das Feld wer ist unbrauchbar")
    return art


# ------------------------------------------------------------ Ausfuehren
def compose_ablegen(daten):
    """Die Compose-Datei in einen Ordner, den nur root lesen kann. Sie geht
    als DATEI an prolo neu bzw. compose_befund.py - nie als Argument."""
    ordner = tempfile.mkdtemp(prefix="prolo-compose-")
    pfad = os.path.join(ordner, "docker-compose.yml")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(daten["compose"])
    return ordner, pfad


def befund_holen(kennung, daten, lage):
    """compose_pruefen: den Befund lesen - nichts anlegen, nichts starten."""
    ordner, pfad = compose_ablegen(daten)
    try:
        r = subprocess.run([sys.executable, os.path.join(HIER, "compose_befund.py"),
                            pfad, daten["name"]], capture_output=True, text=True,
                           timeout=ARTEN["compose_pruefen"][1], env=UMGEBUNG)
    except subprocess.TimeoutExpired:
        return "zeit", None
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
    try:
        befund = json.loads(r.stdout)
    except ValueError:
        befund = {"ok": False, "fehler": (r.stderr.strip().splitlines() or ["kein Befund"])[-1]}
    befund["name_frei"] = not os.path.lexists(os.path.join(STACK, daten["name"]))
    lage["befund"] = befund
    # Die Datei selbst liegt daneben: "Anlegen" nimmt GENAU die, die hier
    # angesehen wurde - nicht eine, die jemand dazwischen geaendert hat.
    schreiben(os.path.join(ERLEDIGT, kennung + ".compose"), daten["compose"])
    with open(os.path.join(ERLEDIGT, kennung + ".log"), "w", encoding="utf-8") as log:
        if befund.get("ok"):
            log.write("Dienste: %s\n" % ", ".join(d["name"] for d in befund["dienste"]))
            log.write("Vorschlag: %s auf Port %s\n" % (befund["vorschlag"]["dienst"] or "-",
                                                     befund["vorschlag"]["port"] or "-"))
            for g in befund["gefahren"]:
                log.write("GEFAHR %s: %s\n" % (g["dienst"], g["was"]))
        else:
            log.write("Nicht zu gebrauchen: %s\n" % befund.get("fehler"))
    os.chmod(os.path.join(ERLEDIGT, kennung + ".log"), 0o644)
    return ("ok" if befund.get("ok") else "fehler"), r.returncode


def ausfuehren(kennung, art, daten):
    """prolo mit den Argumenten aus ARTEN - als Liste, nie ueber eine Shell."""
    _, zeit_s, argumente = ARTEN[art]
    ordner = None
    if art == "neu":
        ordner, pfad = compose_ablegen(daten)
        daten = dict(daten, _datei=pfad)
    try:
        return prolo_ausfuehren(kennung, art, daten, zeit_s, argumente)
    finally:
        if ordner:
            shutil.rmtree(ordner, ignore_errors=True)


def prolo_ausfuehren(kennung, art, daten, zeit_s, argumente):
    befehl = [PROLO] + argumente(daten)
    log_pfad = os.path.join(ERLEDIGT, kennung + ".log")
    umgebung = dict(UMGEBUNG, PROLO_AUFTRAG=kennung)
    if art.startswith("firewall_"):
        # Wer es war, steht an der Sperre (prolo firewall bereinigt den Namen).
        umgebung["PROLO_FIREWALL_WER"] = str(daten.get("wer") or "")[:60]

    with open(log_pfad, "wb") as log:
        os.chmod(log_pfad, 0o644)
        log.write(("$ prolo %s\n\n" % " ".join(befehl[1:])).encode("utf-8"))
        log.flush()
        try:
            p = subprocess.Popen(befehl, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 cwd=STACK, env=umgebung, start_new_session=True)
        except OSError as e:
            log.write(("prolo liess sich nicht starten: %s\n" % e).encode("utf-8"))
            return "fehler", None

        # Die Ausgabe wird mitgeschrieben, waehrend sie entsteht - die Seite
        # zeigt sie an, solange der Auftrag laeuft. Ueber MAX_AUSGABE_BYTE
        # hinaus wird weiter gelesen (sonst blockiert prolo an einer vollen
        # Leitung), aber nicht mehr geschrieben.
        stand = {"byte": 0, "gekuerzt": False}

        def mitschreiben():
            for stueck in iter(lambda: p.stdout.read1(65536), b""):
                rest = MAX_AUSGABE_BYTE - stand["byte"]
                if rest > 0:
                    log.write(stueck[:rest])
                    log.flush()
                    stand["byte"] += min(len(stueck), rest)
                if len(stueck) > max(rest, 0):
                    stand["gekuerzt"] = True

        faden = threading.Thread(target=mitschreiben, daemon=True)
        faden.start()
        try:
            rueckgabe = p.wait(timeout=zeit_s)
            status = "ok" if rueckgabe == 0 else "fehler"
        except subprocess.TimeoutExpired:
            # Die ganze Prozessgruppe: prolo ruft docker, docker compose,
            # Python - ein kill auf prolo allein liesse sie weiterlaufen.
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
            rueckgabe, status = p.returncode, "zeit"
        faden.join(timeout=10)
        if stand["gekuerzt"]:
            log.write(("\n[... die Ausgabe war laenger als %d KiB und ist hier "
                       "abgeschnitten ...]\n" % (MAX_AUSGABE_BYTE // 1024)).encode("utf-8"))
        if status == "zeit":
            log.write(("\n[Abgebrochen nach %d Minuten - laenger darf '%s' nicht "
                       "laufen.]\n" % (zeit_s // 60, art)).encode("utf-8"))
    return status, rueckgabe


def verwerfen(name, grund):
    """Was sich nicht verarbeiten laesst, kommt aus eingang/ heraus -
    sonst stoesst systemd den Dienst immer wieder an."""
    os.makedirs(VERWORFEN, mode=0o700, exist_ok=True)
    sicher = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80] or "_"
    ziel = os.path.join(VERWORFEN, "%s-%s" % (
        datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f"), sicher))
    try:
        os.rename(os.path.join(EINGANG, name), ziel)
    except OSError:
        pass
    protokollieren({"zeit": jetzt(), "kennung": None, "datei": sicher,
                    "status": "verworfen", "grund": grund})


def einer(name):
    kennung = name[:-len(".json")]
    pfad = os.path.join(EINGANG, name)
    if os.path.exists(os.path.join(ERLEDIGT, kennung + ".json")):
        return verwerfen(name, "die Kennung %s gibt es schon" % kennung)
    try:
        daten = lesen(pfad)
    except Abgelehnt as a:
        return verwerfen(name, "die Datei %s" % a)
    # Genommen ist genommen: ab hier liegt der Auftrag nicht mehr im
    # Eingang, auch wenn beim Ausfuehren etwas schiefgeht.
    os.unlink(pfad)

    # Was hier in die Lage kommt, ist noch UNGEPRUEFT - nur kurze
    # Zeichenketten, alles andere faellt weg. Angezeigt wird es trotzdem
    # nur maskiert (admin/server.py).
    lage = {"kennung": kennung, "beginn": jetzt()}
    for feld, grenze in (("art", 40), ("wer", MAX_WER), ("werkzeug", 40),
                         ("netz", 40), ("angelegt", 40), ("name", 40),
                         ("dienst", 64), ("port", 5), ("anmeldung", 12),
                         ("adresse", ADRESSE_MAX), ("dauer", 6)):
        wert = daten.get(feld)
        if isinstance(wert, str) and len(wert) <= grenze and wert.isprintable():
            lage[feld] = wert
    try:
        art = pruefen(daten)
    except Abgelehnt as a:
        lage.update(status="abgelehnt", grund=str(a), ende=jetzt())
        lage_schreiben(kennung, lage)
        protokollieren({"zeit": lage["ende"], **{k: lage[k] for k in
                        ("kennung", "art", "wer", "status", "grund") if k in lage}})
        return

    lage["status"] = "laeuft"
    lage_schreiben(kennung, lage)
    if art == "compose_pruefen":
        status, rueckgabe = befund_holen(kennung, daten, lage)
    else:
        status, rueckgabe = ausfuehren(kennung, art, daten)
    lage.update(status=status, rueckgabe=rueckgabe, ende=jetzt())
    lage_schreiben(kennung, lage)
    protokollieren({"zeit": lage["ende"], **{k: lage[k] for k in
                    ("kennung", "art", "werkzeug", "name", "netz", "adresse", "wer",
                     "status", "rueckgabe") if k in lage}})


HOST = re.compile(r"Host\(`([^`]+)`\)")


def bestand_eines(name):
    """Was die zusammengesetzte Konfiguration ueber ein Werkzeug sagt (§16) -
    ohne Umgebung und ohne Werte: Abbilder, Namen, Netze, Volumes."""
    ordner = os.path.join(STACK, name)
    eintrag = {"name": name,
               "art": ("eigen" if os.path.isfile(os.path.join(ordner, "Dockerfile"))
                       else "plattform" if name in PLATTFORM else "fremd"),
               "sicherung": os.path.isfile(os.path.join(ordner, "sicherung.conf"))}
    try:
        roh = subprocess.run(
            ["docker", "compose", "config", "--no-interpolate", "--format", "json"],
            cwd=ordner, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        eintrag["fehler"] = "docker compose config lief nicht: %s" % e
        return eintrag
    if roh.returncode != 0:
        # Die Ursache im Wortlaut, nicht "unlesbar" (N-64).
        zeilen = [z for z in roh.stderr.strip().splitlines() if z.strip()]
        eintrag["fehler"] = (zeilen[-1] if zeilen else "Rueckgabe %d" % roh.returncode)[:300]
        return eintrag
    try:
        c = json.loads(roh.stdout)
    except ValueError:
        eintrag["fehler"] = "docker compose config gab kein JSON"
        return eintrag
    dienste, hosts, netze = [], set(), set()
    for dname, d in sorted((c.get("services") or {}).items()):
        d = d or {}
        dienste.append({"dienst": dname, "abbild": str(d.get("image") or "")})
        labels = d.get("labels") or {}
        if isinstance(labels, list):
            labels = dict(x.split("=", 1) for x in labels if "=" in x)
        for k, v in labels.items():
            if k.startswith("traefik.http.routers.") and k.endswith(".rule"):
                hosts.update(HOST.findall(str(v)))
        nz = d.get("networks") or {}
        netze.update(nz if isinstance(nz, (dict, list)) else [])
    namen = {k: (v or {}).get("name") or k
             for k, v in (c.get("networks") or {}).items()}
    eintrag.update(dienste=dienste, hosts=sorted(hosts),
                   netze=sorted(namen.get(n, n) for n in netze),
                   volumes=sorted((v or {}).get("name") or k
                                  for k, v in (c.get("volumes") or {}).items()))
    return eintrag


def bestand_schreiben(erzwingen=False):
    """bestand.json neu schreiben - hoechstens alle BESTAND_ALTER_S, ausser
    ein Auftrag hat etwas veraendert. Ein Fehler hier haelt keinen Auftrag
    auf: der Bestand ist eine Anzeige, kein Teil der Arbeit (§12)."""
    try:
        if not erzwingen and os.path.exists(BESTAND) and \
                datetime.datetime.now().timestamp() - os.stat(BESTAND).st_mtime < BESTAND_ALTER_S:
            return
        namen = sorted(n for n in os.listdir(STACK)
                       if WERKZEUG.fullmatch(n)
                       and not os.path.islink(os.path.join(STACK, n))
                       and os.path.isfile(os.path.join(STACK, n, "docker-compose.yml")))
        schreiben(BESTAND, json.dumps(
            {"stand": jetzt(), "werkzeuge": [bestand_eines(n) for n in namen]},
            ensure_ascii=False, indent=1) + "\n")
    except Exception as e:     # noqa: BLE001 - siehe oben
        sys.stderr.write("Bestand nicht geschrieben: %s\n" % e)


def firewall_schreiben(erzwingen=False):
    """firewall.json aus 'prolo firewall --json' - nur, wenn es eine
    Firewall gibt. Wie der Bestand eine Anzeige: ein Fehler haelt nichts auf."""
    try:
        if not os.path.isfile(os.path.join(STACK, "crowdsec", "docker-compose.yml")):
            return
        if not erzwingen and os.path.exists(FIREWALL) and \
                datetime.datetime.now().timestamp() - os.stat(FIREWALL).st_mtime < BESTAND_ALTER_S:
            return
        r = subprocess.run([sys.executable, os.path.join(HIER, "firewall.py"), "--json"],
                           capture_output=True, text=True, timeout=90, env=UMGEBUNG)
        if len(r.stdout) > FIREWALL_MAX_BYTE:
            raise ValueError("die Lage ist groesser als %d KiB" % (FIREWALL_MAX_BYTE // 1024))
        lage = json.loads(r.stdout)
        if not isinstance(lage, dict):
            raise ValueError("die Lage ist kein JSON-Objekt")
        schreiben(FIREWALL, json.dumps(lage, ensure_ascii=False, indent=1) + "\n")
    except Exception as e:     # noqa: BLE001 - siehe oben
        sys.stderr.write("Firewall-Lage nicht geschrieben: %s\n" % e)


def liegengeblieben():
    """Ein Auftrag, der beim letzten Mal "laeuft" war und es jetzt nicht
    mehr sein kann (wir halten die Sperre): der Ausfuehrer ist mittendrin
    beendet worden. Das steht dann auch so da, statt fuer immer "laeuft"."""
    for n in sorted(os.listdir(ERLEDIGT)):
        if not (n.endswith(".json") and KENNUNG.fullmatch(n[:-5])):
            continue
        p = os.path.join(ERLEDIGT, n)
        try:
            with open(p, encoding="utf-8") as f:
                lage = json.load(f)
        except (OSError, ValueError):
            continue
        if lage.get("status") == "laeuft":
            lage.update(status="abgebrochen", ende=jetzt(),
                        grund="Der Ausfuehrer wurde beendet, bevor der Auftrag "
                              "fertig war (Neustart des Servers?). Was bis dahin "
                              "geschah, steht in der Ausgabe.")
            lage_schreiben(n[:-5], lage)
            protokollieren({"zeit": lage["ende"], "kennung": n[:-5],
                            "art": lage.get("art"), "status": "abgebrochen"})


def abarbeiten():
    for d in (EINGANG, ERLEDIGT):
        if not os.path.isdir(d):
            sys.stderr.write("%s fehlt. Einmal: sudo prolo einrichten\n" % d)
            return 1
    with open(os.path.join(BUCH, ".sperre"), "w") as sperre:
        try:
            fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Ein anderer Lauf arbeitet schon - er nimmt sich auch diesen
            # Auftrag, er liest den Eingang, bis darin kein .json mehr liegt.
            return 0
        liegengeblieben()
        bestand_schreiben()
        firewall_schreiben()
        erledigt = set()
        while True:
            offen = False
            for name in sorted(os.listdir(EINGANG)):
                if name in erledigt:
                    # Schon einmal angefasst und immer noch da: weder
                    # Verarbeiten noch Verwerfen hat ihn herausbekommen.
                    # Aufhoeren, statt sich im Kreis zu drehen.
                    sys.stderr.write("%s laesst sich nicht aus dem Eingang "
                                     "nehmen - bitte von Hand ansehen.\n" % name)
                    return 1
                if name.endswith(".json") and KENNUNG.fullmatch(name[:-5]):
                    erledigt.add(name)
                    offen = True
                    einer(name)
                elif name.endswith(".neu") and KENNUNG.fullmatch(name[:-4]):
                    # Die Seite schreibt gerade (erst daneben, dann
                    # umbenennen). Das stoesst systemd nicht an - nur *.json
                    # tut das (werkzeuge/systemd/prolo-auftraege.path).
                    # Bleibt so eine Datei liegen, war die Seite mittendrin
                    # weg; nach ALT_NEU_S kommt sie heraus.
                    if ist_alt(os.path.join(EINGANG, name)):
                        erledigt.add(name)
                        verwerfen(name, "halb geschrieben liegen geblieben")
                else:
                    erledigt.add(name)
                    verwerfen(name, "unbekannter Dateiname")
            if not offen:
                if erledigt:
                    bestand_schreiben(erzwingen=True)
                    firewall_schreiben(erzwingen=True)
                return 0


ALT_NEU_S = 600


def ist_alt(pfad):
    try:
        st = os.lstat(pfad)
    except OSError:
        return False
    return datetime.datetime.now().timestamp() - st.st_mtime > ALT_NEU_S


def einrichten(nur_pruefen=False):
    """Die Ordner anlegen: eingang/ gehoert dem Nutzer der Admin-Seite,
    alles andere root - die Seite liest erledigt/, schreiben kann sie dort
    nicht (dort liegt auch das Protokoll).

    Sieht erst nach und tut nur, was fehlt (N-54). Mit nur_pruefen wird
    nichts angefasst; Rueckgabe 1 heisst dann: es gibt etwas zu tun.
    """
    root = os.geteuid() == 0
    soll = ((BUCH, 0, 0o755), (EINGANG, ADMIN_UID, 0o700),
            (ERLEDIGT, 0, 0o755), (VERWORFEN, 0, 0o700))
    zu_tun = []
    for pfad, uid, modus in soll:
        name = os.path.relpath(pfad, STACK)
        if os.path.islink(pfad):
            # Einem Verweis wird nicht gefolgt - er koennte ueberall hin
            # zeigen, und hier wird gleich chown gemacht.
            print("FEHLER %s ist ein Verweis (Symlink) - bitte von Hand "
                  "ansehen und durch einen Ordner ersetzen" % name)
            return 2
        if not os.path.isdir(pfad):
            zu_tun.append((pfad, uid, modus, "%s anlegen" % name))
            continue
        st = os.stat(pfad)
        if (root and st.st_uid != uid) or stat.S_IMODE(st.st_mode) != modus:
            zu_tun.append((pfad, uid, modus, "%s: Besitzer %d, Rechte %o"
                           % (name, uid, modus)))
    if nur_pruefen:
        for _, _, _, was in zu_tun:
            print(was)
        return 1 if zu_tun else 0
    for pfad, uid, modus, was in zu_tun:
        os.makedirs(pfad, mode=modus, exist_ok=True)
        if root:
            os.chown(pfad, uid, uid)
        os.chmod(pfad, modus)
        print(was)
    return 0


def liste(anzahl):
    try:
        with open(PROTOKOLL, encoding="utf-8") as f:
            zeilen = f.readlines()[-anzahl:]
    except OSError:
        print("Noch kein Auftrag.")
        return 0
    for z in zeilen:
        try:
            a = json.loads(z)
        except ValueError:
            continue
        print("%-25s %-13s %-14s %-10s %s" % (
            a.get("zeit", "?"), a.get("art", "-"),
            a.get("werkzeug") or a.get("netz") or a.get("adresse") or "-",
            a.get("status", "?"), a.get("wer") or a.get("grund") or ""))
    return 0


def main(argv):
    befehl = argv[1] if len(argv) > 1 else ""
    if befehl in ("abarbeiten", "einrichten") and os.geteuid() != 0 \
            and not os.environ.get("PROLO_AUFTRAG_PROBE"):
        sys.stderr.write("Braucht root: sudo %s %s\n" % (argv[0], befehl))
        return 1
    if befehl == "abarbeiten":
        return abarbeiten()
    if befehl == "einrichten":
        return einrichten(nur_pruefen="--pruefen" in argv[2:])
    if befehl == "liste":
        return liste(int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 20)
    sys.stderr.write(__doc__.split("Aufruf (root):")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
