#!/usr/bin/env python3
"""werkzeuge/crowdsec-probe/probe.py - die Firewall unter echtem CrowdSec (F-01)

    probe.py <stapel>

Startet CrowdSec aus <stapel>/crowdsec/docker-compose.yml - mit allem, was
dort steht (Abbild, Grenzen, Umgebung, Einhaengungen) - und aendert fuer
die Probe nur, was sein muss:

  - eigener Projekt- und Containername, eigene Volumes: ein laufendes
    CrowdSec auf demselben Rechner bleibt unberuehrt
  - keine veroeffentlichten Ports
  - die zwei Protokollordner (/var/log/traefik, /var/log/host) zeigen auf
    Wegwerfordner, in die die Probe schreibt
  - der Einstieg ist crowdsec-probe/start.sh (kein Hub, siehe dort)

Dann gehen Zeilen hinein, deren Ausgang VON HAND festgelegt ist (§13),
und es wird verglichen, was CrowdSec daraus macht. Ausgabe: je Pruefung
eine Zeile "ok ..." oder "FEHLER ...". Rueckgabe 0 nur, wenn alles stimmt.
"""
import datetime
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

HIER = os.path.dirname(os.path.abspath(__file__))
SCHLUESSEL = "probe-" + secrets.token_hex(12)
FEHLER = []


def sag(gut, text, warum=""):
    if gut:
        print("ok     " + text)
    else:
        print("FEHLER " + text + ("  -> " + warum if warum else ""))
        FEHLER.append(text)
    return gut


def lauf(befehl, **kw):
    return subprocess.run(befehl, capture_output=True, text=True, **kw)


def compose_konfig(ordner, umgebung=None):
    r = lauf(["docker", "compose", "config", "--format", "json"], cwd=ordner,
             env=dict(os.environ, **(umgebung or {})))
    if r.returncode != 0:
        return None, r.stderr.strip().splitlines()[-1:] or ["?"]
    return json.loads(r.stdout), None


# ------------------------------------------------ 1. Was ohne Container geht
def traefik_schreibt_wo_crowdsec_liest(stapel, cs):
    """Vier Stellen, eine Kette: traefik.yml schreibt nach X, Traefik haengt
    ./log als /var/log/traefik ein, CrowdSec haengt traefik/log als
    /var/log/traefik ein, die Erfassung liest X. Reisst ein Glied, liest
    CrowdSec eine Datei, in die niemand schreibt - und meldet nie etwas."""
    gruende = []
    t = open(os.path.join(stapel, "traefik", "traefik.yml"), encoding="utf-8").read()
    m = re.search(r"(?m)^accessLog:\s*\n(?:[ \t]+.*\n)*?[ \t]+filePath:\s*(\S+)", t)
    datei = m.group(1).strip("\"'") if m else ""
    if not datei.startswith("/var/log/traefik/"):
        gruende.append("traefik.yml schreibt nach %r" % (datei or "nirgends"))
    if not re.search(r"(?m)^accessLog:\s*\n(?:[ \t]+.*\n)*?[ \t]+format:\s*json", t):
        gruende.append("traefik.yml schreibt nicht als json")
    tk, grund = compose_konfig(os.path.join(stapel, "traefik"))
    log_ordner = os.path.realpath(os.path.join(stapel, "traefik", "log"))
    if tk is None:
        gruende.append("traefik: docker compose config: %s" % grund[0])
    elif not any(v.get("type") == "bind" and v.get("target") == "/var/log/traefik"
                 and os.path.realpath(v.get("source", "")) == log_ordner
                 for d in tk["services"].values() for v in d.get("volumes") or []):
        gruende.append("Traefik haengt traefik/log nicht als /var/log/traefik ein")
    if not any(v.get("type") == "bind" and v.get("target") == "/var/log/traefik"
               and os.path.realpath(v.get("source", "")) == log_ordner and v.get("read_only")
               for v in cs.get("volumes") or []):
        gruende.append("CrowdSec haengt traefik/log nicht lesend als /var/log/traefik ein")
    erf = os.path.join(stapel, "crowdsec", "erfassung")
    gelesen = []
    for n in sorted(os.listdir(erf)) if os.path.isdir(erf) else []:
        gelesen += re.findall(r"(?m)^\s*-\s*(/var/log/traefik/\S+)", open(os.path.join(erf, n)).read())
    if datei and datei not in gelesen:
        gruende.append("die Erfassung liest %s, Traefik schreibt %s" % (", ".join(gelesen) or "nichts", datei))
    sag(not gruende, "Traefik schreibt, wo CrowdSec liest (%s)" % (datei or "?"), "; ".join(gruende))
    return datei


def grenzen(cs):
    g = []
    if "ALL" not in (cs.get("cap_drop") or []):
        g.append("cap_drop: ALL fehlt")
    if cs.get("cap_add"):
        g.append("cap_add: %s" % cs["cap_add"])
    if "no-new-privileges:true" not in (cs.get("security_opt") or []):
        g.append("no-new-privileges fehlt")
    if not cs.get("mem_limit") or not cs.get("pids_limit"):
        g.append("mem_limit/pids_limit fehlt")
    if cs.get("privileged"):
        g.append("privileged")
    if any("docker.sock" in str(v.get("source", "")) for v in cs.get("volumes") or []):
        g.append("haengt den Docker-Socket ein")
    sag(not g, "Grenzen nach §19, kein Socket, keine Faehigkeiten zurueck", "; ".join(g))
    ports = cs.get("ports") or []
    offen = [p for p in ports if str(p.get("host_ip") or "") != "127.0.0.1"]
    labels = cs.get("labels") or {}
    if isinstance(labels, list):
        labels = dict(x.split("=", 1) for x in labels if "=" in x)
    sag(ports and not offen and labels.get("prolo.ports"),
        "die lokale API ist nur auf 127.0.0.1 veroeffentlicht, und das ist erklaert",
        "offen: %s" % ", ".join("%s:%s" % (p.get("host_ip") or "0.0.0.0", p.get("published")) for p in offen)
        if offen else "kein Port oder kein Label prolo.ports")


# ------------------------------------------------------ 2. Der Probelauf
def probe_datei(konfig, name, t):
    """Die Konfiguration aus crowdsec/docker-compose.yml, nur umgelenkt."""
    c = json.loads(json.dumps(konfig))
    c["name"] = name
    d = c["services"]["crowdsec"]
    d["container_name"] = name
    d.pop("ports", None)
    d["entrypoint"] = ["/probe/start.sh"]
    d["restart"] = "no"
    neu = []
    for v in d.get("volumes") or []:
        v = dict(v)
        if v.get("target") == "/var/log/traefik":
            v["source"] = os.path.join(t, "log", "traefik")
        elif v.get("target") == "/var/log/host":
            v["source"] = os.path.join(t, "log", "host")
        neu.append(v)
    neu.append({"type": "bind", "source": HIER, "target": "/probe", "read_only": True})
    d["volumes"] = neu
    # Eigene Volumes - NIE die des echten CrowdSec.
    c["volumes"] = {k: {"name": "%s_%s" % (name, k)} for k in (c.get("volumes") or {})}
    c.pop("networks", None)
    d.pop("networks", None)
    return c


def cscli(name, *args):
    return lauf(["docker", "exec", name, "cscli"] + list(args))


def entscheidungen(name):
    r = cscli(name, "decisions", "list", "-o", "json")
    try:
        daten = json.loads(r.stdout) or []
    except ValueError:
        return {}
    aus = {}
    for a in daten:
        for e in a.get("decisions") or []:
            aus.setdefault(e["value"], []).append((e["scenario"], dauer_h(e["duration"])))
    return aus


def dauer_h(text):
    """'23h59m58.1s' -> 23.99 (Stunden), fuer den Vergleich mit Hand-Werten."""
    h = re.search(r"(\d+)h", text)
    m = re.search(r"(\d+)m", text)
    return (int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0) / 60


def beim_bouncer(name):
    """Was der Bouncer bekaeme: die Adressen aus dem Strom der lokalen API.
    Darauf kommt es an - nicht auf die Liste in cscli."""
    url = "http://127.0.0.1:8080/v1/decisions/stream?startup=true"
    r = lauf(["docker", "exec", name, "wget", "-qO-", "--header", "X-Api-Key: " + SCHLUESSEL, url])
    try:
        return {x["value"] for x in json.loads(r.stdout).get("new") or []}
    except (ValueError, AttributeError):
        return None


def warten(bedingung, sekunden):
    ende = time.time() + sekunden
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(1)
    return bedingung()


def zeilen_schreiben(t, datei):
    jetzt = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def z(ip, pfad, status):
        return json.dumps({"ClientHost": ip, "DownstreamStatus": status, "RequestPath": pfad,
                           "RequestMethod": "GET", "RequestHost": "prolo.me", "time": jetzt,
                           "entryPointName": "websecure", "level": "info", "msg": ""})
    zeilen = []
    zeilen += [z("203.0.113.10", "/z/" + secrets.token_urlsafe(16), 404) for _ in range(10)]
    zeilen += [z("203.0.113.11", "/z/" + secrets.token_urlsafe(16), 404) for _ in range(9)]
    zeilen += [z("203.0.113.12", "/z/" + secrets.token_urlsafe(16), 404) for _ in range(10)]
    zeilen += [z("198.51.100.7", "/wp-login.php", 404)]
    zeilen += [z("198.51.100.8", "/wiki/seite-%d" % i, 200) for i in range(20)]
    zeilen += [z("172.20.0.5", "/wp-login.php", 404)]
    with open(os.path.join(t, "log", "traefik", os.path.basename(datei)), "a") as f:
        f.write("\n".join(zeilen) + "\n")
    s = datetime.datetime.now().strftime("%b %d %H:%M:%S")
    ssh = ["%s prolo sshd[%d]: Failed password for root from %s port %d ssh2" % (s, 1000 + i, ip, 40000 + i)
           for ip in ("192.0.2.50", "192.0.2.60") for i in range(6)]
    with open(os.path.join(t, "log", "host", "auth.log"), "a") as f:
        f.write("\n".join(ssh) + "\n")


def probelauf(stapel, datei):
    ordner = os.path.join(stapel, "crowdsec")
    konfig, grund = compose_konfig(ordner, {"CROWDSEC_BOUNCER_SCHLUESSEL": SCHLUESSEL,
                                            "CROWDSEC_KONSOLE_SCHLUESSEL": ""})
    if not sag(konfig is not None, "crowdsec: docker compose config geht", (grund or [""])[0]):
        return
    cs = konfig["services"]["crowdsec"]
    grenzen(cs)
    datei = traefik_schreibt_wo_crowdsec_liest(stapel, cs) or datei
    sag(cs.get("environment", {}).get("BOUNCER_KEY_firewall") == SCHLUESSEL,
        "der Bouncer-Schluessel kommt aus CROWDSEC_BOUNCER_SCHLUESSEL in .env")

    name = "crowdsec-probe-%d" % os.getpid()
    t = tempfile.mkdtemp(prefix="crowdsec-probe-")
    try:
        for o in ("traefik", "host"):
            os.makedirs(os.path.join(t, "log", o))
        open(os.path.join(t, "log", "traefik", os.path.basename(datei)), "w").close()
        open(os.path.join(t, "log", "host", "auth.log"), "w").close()
        os.chmod(t, 0o755)
        with open(os.path.join(t, "probe.json"), "w") as f:
            json.dump(probe_datei(konfig, name, t), f)
        r = lauf(["docker", "compose", "-p", name, "-f", os.path.join(t, "probe.json"), "up", "-d"])
        if not sag(r.returncode == 0, "der Probelauf startet mit den Grenzen aus der Compose-Datei",
                   (r.stderr.strip().splitlines() or ["?"])[-1]):
            return

        def bereit():
            log = lauf(["docker", "logs", name]).stderr
            return (cscli(name, "lapi", "status").returncode == 0
                    and log.count("Starting tail") >= 2)
        if not sag(warten(bereit, 90), "CrowdSec laeuft und liest beide Protokolle",
                   (lauf(["docker", "logs", "--tail", "5", name]).stderr.strip().splitlines() or ["?"])[-1]):
            return

        r = cscli(name, "scenarios", "list", "-o", "json")
        geladen = {s.get("name") for s in (json.loads(r.stdout or "{}").get("scenarios") or [])} \
            if r.returncode == 0 else set()
        eigene = {"prolo/zugangslink-raten", "prolo/falle"}
        sag(eigene <= geladen, "die eigenen Regeln aus regeln/ sind geladen",
            "fehlt: %s" % ", ".join(sorted(eigene - geladen)))

        # Vor der ersten Zeile: firewall --json nennt beide Quellen - mit 0.
        # Genau dafuer ist die Liste da: eine Quelle, aus der nie etwas
        # kommt, soll auffallen, nicht fehlen.
        leer = firewall_json(stapel, name).get("gelesen") or {}
        sag(leer.get("/var/log/traefik/zugriff.log", {}).get("zeilen") == 0
            and leer.get("/var/log/host/auth.log", {}).get("zeilen") == 0,
            "vor der ersten Zeile nennt firewall --json beide Quellen, mit 0 Zeilen",
            "bekommen: %s" % leer)

        # Vorher: eine Freigabe und eine Handsperre (fuer die Steigerung).
        cscli(name, "allowlists", "create", "prolo", "-d", "Probe")
        cscli(name, "allowlists", "add", "prolo", "203.0.113.12", "-d", "Buero")
        cscli(name, "decisions", "add", "--ip", "192.0.2.60", "--duration", "1h", "--reason", "vorher")

        zeilen_schreiben(t, datei)
        soll = {"203.0.113.10", "198.51.100.7", "192.0.2.50", "192.0.2.60"}
        warten(lambda: soll <= set(entscheidungen(name))
               and any(s[0] != "vorher" for s in entscheidungen(name).get("192.0.2.60", [])), 30)
        time.sleep(3)      # und was danach noch kaeme, soll auch da sein
        e = entscheidungen(name)

        # Die Erwartungen - von Hand, nicht aus dem Lauf (§13).
        def gesperrt(ip, regel, von_h, bis_h, text):
            s = [x for x in e.get(ip, []) if x[0] == regel]
            sag(s and von_h <= s[0][1] <= bis_h, text,
                "bekommen: %s" % ("; ".join("%s, %.2f h" % x for x in e.get(ip, [])) or "keine Sperre"))

        def frei(ip, text):
            sag(ip not in e, text, "gesperrt: %s" % (e.get(ip),))

        gesperrt("203.0.113.10", "prolo/zugangslink-raten", 23.9, 24.0,
                 "10 unbekannte Zugangslinks: gesperrt, 24 Stunden")
        frei("203.0.113.11", "9 unbekannte Zugangslinks: nicht gesperrt (der Eimer fasst 9)")
        gesperrt("198.51.100.7", "prolo/falle", 23.9, 24.0,
                 "ein Aufruf von /wp-login.php: gesperrt, 24 Stunden (Falle)")
        frei("198.51.100.8", "20 gewoehnliche Aufrufe: nicht gesperrt")
        frei("172.20.0.5", "eine private Adresse in der Falle: nicht gesperrt")
        gesperrt("192.0.2.50", "crowdsecurity/ssh-bf", 3.9, 4.0,
                 "6 falsche SSH-Passwoerter: gesperrt, 4 Stunden")
        gesperrt("192.0.2.60", "crowdsecurity/ssh-bf", 7.9, 8.0,
                 "dieselben 6 nach einer frueheren Sperre: 8 Stunden (Wiederholung)")
        log = lauf(["docker", "logs", name]).stderr
        sag("203.0.113.12" not in e and "203.0.113.12 is allowlisted" in log,
            "eine Adresse auf der Freigabeliste laeuft ueber und wird trotzdem nicht gesperrt",
            "gesperrt" if "203.0.113.12" in e else "kein Ueberlauf im Protokoll - dann prueft das nichts")

        # Der Weg des Bouncers: mit Schluessel die Sperren, ohne 403.
        neu = beim_bouncer(name) or set()
        sag(neu == soll, "der Bouncer bekommt mit seinem Schluessel genau die vier Sperren",
            "bekommen: %s" % ", ".join(sorted(neu)))
        url = "http://127.0.0.1:8080/v1/decisions/stream?startup=true"
        r = lauf(["docker", "exec", name, "wget", "-qO-", url])
        sag(r.returncode != 0 and "403" in r.stderr, "ohne Schluessel bekommt niemand etwas (403)",
            r.stderr.strip()[:120])

        firewall_befehle(stapel, name)
    finally:
        lauf(["docker", "compose", "-p", name, "-f", os.path.join(t, "probe.json"), "down", "-v",
              "--timeout", "3"])
        shutil.rmtree(t, ignore_errors=True)


# ------------------------------------------- 3. prolo firewall, am echten
def firewall_json(stapel, name):
    r = lauf([sys.executable, os.path.join(stapel, "werkzeuge", "firewall.py"), "--json"],
             env=dict(os.environ, PROLO_FIREWALL_CONTAINER=name))
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {}


def firewall_befehle(stapel, name):
    """werkzeuge/firewall.py gegen dasselbe CrowdSec. Die Wirkung wird an der
    Sperrliste gemessen, nicht an der Meldung des Befehls (N-38)."""
    fw = os.path.join(stapel, "werkzeuge", "firewall.py")
    umg = dict(os.environ, PROLO_FIREWALL_CONTAINER=name, PROLO_FIREWALL_WER="probe")

    def befehl(*args):
        return lauf([sys.executable, fw] + list(args), env=umg)

    def hat(wert, regel_teil=None):
        return [s for s in entscheidungen(name).get(wert, [])
                if regel_teil is None or regel_teil in s[0]]

    oeffentlich = "93.184.216.34"
    r = befehl("sperren", oeffentlich, "2h", "Probe")
    s = hat(oeffentlich, "von Hand (probe): Probe")
    sag(r.returncode == 0 and s and 1.9 <= s[0][1] <= 2.0,
        "firewall sperren: 2 Stunden, der Grund und wer es war stehen dabei",
        r.stderr.strip() or "Sperren: %s" % hat(oeffentlich))
    for adresse, text in (("10.0.0.5", "eine private Adresse"),
                          ("100.64.1.2", "eine Adresse aus 100.64.0.0/10 (Tailscale)"),
                          ("1.2.3.4; rm -rf /", "etwas, das keine Adresse ist")):
        r = befehl("sperren", adresse, "1h", "x")
        sag(r.returncode == 1 and not hat(adresse.split(";")[0]),
            "firewall sperren lehnt %s ab" % text, r.stdout.strip() or "Rueckgabe %d" % r.returncode)
    r = befehl("sperren", "8.8.0.0/8", "1h", "x")
    sag(r.returncode == 1 and not hat("8.0.0.0/8"), "firewall sperren lehnt ein Netz groesser als /16 ab")
    r1 = befehl("sperren", "93.184.216.0/24", "1h", "Netz")
    da = bool(hat("93.184.216.0/24"))
    r2 = befehl("aufheben", "93.184.216.0/24")
    sag(r1.returncode == 0 and da and r2.returncode == 0 and not hat("93.184.216.0/24"),
        "ein /24 laesst sich sperren und wieder aufheben")

    vorher = oeffentlich in (beim_bouncer(name) or set())
    r = befehl("erlauben", oeffentlich, "Buero")
    nachher = beim_bouncer(name)
    sag(r.returncode == 0 and vorher and nachher is not None and oeffentlich not in nachher,
        "firewall erlauben hebt die bestehende Sperre auf - beim Bouncer gemessen",
        r.stderr.strip() or "vorher beim Bouncer: %s, nachher: %s" % (vorher, nachher))
    r = befehl("sperren", oeffentlich, "1h", "x")
    sag(r.returncode == 1 and not hat(oeffentlich) and "Freigabeliste" in r.stderr,
        "eine freigegebene Adresse laesst sich nicht sperren")
    lage_json = befehl("--json")
    try:
        l = json.loads(lage_json.stdout)
    except ValueError:
        l = {}
    r = befehl("nicht-mehr-erlauben", oeffentlich)
    r2 = befehl("sperren", oeffentlich, "1h", "x")
    sag(r.returncode == 0 and r2.returncode == 0 and hat(oeffentlich),
        "nach nicht-mehr-erlauben geht Sperren wieder")
    befehl("aufheben", oeffentlich)

    r = befehl("sperren", "93.184.216.35", "13d", "lang")
    s = hat("93.184.216.35", "lang")
    sag(r.returncode == 0 and s and 311.9 <= s[0][1] <= 312.0, "13 Tage sind 312 Stunden",
        "bekommen: %s" % s)
    r = befehl("sperren", "93.184.216.36", "400d", "x")
    sag(r.returncode == 1 and not hat("93.184.216.36"), "laenger als ein Jahr wird abgelehnt")
    r = befehl("sperren", "93.184.216.36", "1h", "")
    sag(r.returncode == 1 and not hat("93.184.216.36"), "ohne Grund wird nicht gesperrt")

    # Die Lage, wie die Admin-Seite sie bekommt
    regeln = {x.get("name") for x in l.get("regeln") or []}
    gelesen = l.get("gelesen") or {}
    sag(l.get("crowdsec", {}).get("laeuft")
        and any(x.get("wert") == "198.51.100.7" and x.get("regel") == "prolo/falle"
                for x in l.get("sperren") or [])
        and any(x.get("wert") == oeffentlich for x in l.get("freigaben") or [])
        and {"prolo/zugangslink-raten", "prolo/falle"} <= regeln
        and any(b.get("name") == "firewall" and b.get("still_s") is not None
                for b in l.get("bouncer") or []),
        "firewall --json: CrowdSec, Sperren, Freigaben, eigene Regeln, Bouncer",
        "bekommen: %s" % ", ".join(sorted(l)) if l else lage_json.stderr.strip()[:120])
    sag(gelesen.get("/var/log/traefik/zugriff.log", {}).get("zeilen", 0) >= 50
        and gelesen.get("/var/log/host/auth.log", {}).get("zeilen", 0) >= 12,
        "firewall --json nennt beide Quellen mit dem, was gelesen wurde",
        "bekommen: %s" % gelesen)


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("Aufruf: probe.py <stapel>\n")
        return 2
    if shutil.which("docker") is None:
        sag(False, "docker fehlt", "ohne echtes CrowdSec keine Probe - ein uebersprungener Test ist kein gruener")
        return 1
    probelauf(os.path.realpath(sys.argv[1]), "/var/log/traefik/zugriff.log")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    sys.exit(main())
