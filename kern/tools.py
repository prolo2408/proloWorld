"""Tools: anlegen, aendern, starten, aktualisieren, entfernen.

Ein Tool ist ein Ordner unter /opt/tools/<name>/:

    app/                  das Tool selbst - die Compose-Datei des Herstellers,
                          ein git clone, oder eine von prolo erzeugte Datei.
                          Daneben seine .env.
    prolo.conf            was prolo ueber das Tool weiss (Quelle, Port, ...)
    prolo.override.yml    was prolo dazutut: eigenes Netz, Router bei
                          Traefik, Anmeldung, keine offenen Ports

Die Datei des Herstellers bleibt unangetastet - bei einer neuen Fassung
ersetzt man nur sie. docker compose liest beide Dateien zusammen.

Jedes Tool haengt in seinem EIGENEN Netz tool-<name>, in dem sonst nur
Traefik haengt. Tools erreichen einander also nicht direkt - nur ueber
Traefik und damit ueber die Anmeldung.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import docker, orte
from .auftrag import ANMELDUNG, DIENST, PORT, Ungueltig, env_zeilen, name_pruefen
from .orte import Abbruch

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)((?::?[-?+])([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")
GEHEIM = re.compile(r"PASS|SECRET|KEY|TOKEN|SALT|CREDENTIAL", re.I)
HILFSDIENST = re.compile(r"(^|/)(postgres|postgis|mysql|mariadb|redis|valkey|mongo|memcached|"
                         r"rabbitmq|elasticsearch|opensearch|clickhouse|minio|typesense|"
                         r"meilisearch)(:|$)", re.I)
SOCKET = re.compile(r"(^|/)docker\.sock$")
KAEFIG = {
    "privileged": "läuft mit allen Rechten des Servers (privileged)",
    "pid": "sieht alle Prozesse des Servers (pid: host)",
    "ipc": "teilt den Speicher mit dem Server (ipc: host)",
    "uts": "teilt den Rechnernamen mit dem Server (uts: host)",
    "userns_mode": "verlässt den Nutzer-Namensraum (userns_mode: host)",
    "cgroup": "teilt die cgroups mit dem Server (cgroup: host)",
}
KOPF = "# Von prolo geschrieben - wird bei jeder Änderung neu erzeugt. Nicht von Hand ändern.\n"


# ------------------------------------------------------------ Bestand
def namen():
    """Alle installierten Tools, sortiert."""
    try:
        eintraege = sorted(os.listdir(orte.TOOLS))
    except FileNotFoundError:
        return []
    return [n for n in eintraege
            if not n.startswith(".") and os.path.isfile(os.path.join(orte.TOOLS, n, "prolo.conf"))]


def conf(name):
    pfad = os.path.join(docker.tool_ordner(name), "prolo.conf")
    if not os.path.isfile(pfad):
        raise Abbruch("Ein Tool '%s' gibt es nicht. Installiert: %s"
                      % (name, ", ".join(namen()) or "keine"))
    return orte.env_lesen(pfad)


def netzname(name):
    return "tool-%s" % name


def url(c):
    return "https://%s" % c.get("HOST", "")


# ------------------------------------------------------ Compose lesen
def variablen(text):
    """Welche ${VAR} erwartet eine Compose-Datei? {name: hat_vorgabe}"""
    gefunden = {}
    for m in VARIABLE.finditer(text):
        n = m.group(1) or m.group(4)
        op = m.group(2) or ""
        vorgabe = bool(op) and "?" not in op
        gefunden[n] = gefunden.get(n, False) or vorgabe
    return gefunden


def vorschlag_wert(var, host):
    """Ein naheliegender Wert fuer eine Variable - oder None."""
    v = var.upper()
    if GEHEIM.search(v):
        return orte.zufall(40)
    if v in ("TZ", "TIMEZONE", "GENERIC_TIMEZONE"):
        return "Europe/Berlin"
    if v in ("PUID", "PGID", "UID", "GID"):
        return "1000"
    if v.endswith("URL"):
        return "https://%s" % host
    if v.endswith("HOST") or v.endswith("DOMAIN") or v.endswith("HOSTNAME"):
        return host
    return None


def env_fuellen(app, host, gegeben):
    """Legt app/.env an bzw. ergaenzt sie: gegebene Werte, gewuerfelte
    Geheimnisse, naheliegende Vorgaben. Was danach fehlt, wird genannt -
    geraten wird nichts (keine stillen Vorgabewerte)."""
    text = ""
    for n in os.listdir(app):
        if re.fullmatch(r"(docker-)?compose(\.override)?\.ya?ml", n):
            with open(os.path.join(app, n), encoding="utf-8", errors="replace") as f:
                text += f.read() + "\n"
    pfad = os.path.join(app, ".env")
    vorhanden = orte.env_lesen(pfad) if os.path.isfile(pfad) else {}
    neu, fehlt, erzeugt = {}, [], []
    for var, hat_vorgabe in sorted(variablen(text).items()):
        if var in vorhanden:
            continue
        if var in gegeben:
            neu[var] = gegeben[var]
        elif hat_vorgabe:
            continue
        else:
            w = vorschlag_wert(var, host)
            if w is None:
                fehlt.append(var)
            else:
                neu[var] = w
                erzeugt.append(var)
    for var, w in gegeben.items():
        if var not in vorhanden and var not in neu:
            neu[var] = w
    if fehlt:
        raise Abbruch("Die Compose-Datei braucht Werte, die prolo nicht kennt: %s\n"
                      "  Mitgeben mit  --env NAME=wert  (in der Admin-Seite: Feld 'Variablen')."
                      % ", ".join(fehlt))
    if neu:
        alt = ""
        if os.path.isfile(pfad):
            with open(pfad, encoding="utf-8") as f:
                alt = f.read()
            if alt and not alt.endswith("\n"):
                alt += "\n"
        zeilen = "".join("%s=%s\n" % (k, v) for k, v in neu.items())
        orte.datei_schreiben(pfad, alt + "# von prolo ergänzt\n" + zeilen, 0o600)
    return erzeugt


def config(app, dateien, name):
    """docker compose config fuer app/ - fehlt eine env_file, die die Datei
    erwartet, wird sie leer angelegt (Hersteller legen sie fast immer bei)."""
    befehl = ["docker", "compose", "-p", name, "--project-directory", app]
    for d in dateien:
        befehl += ["-f", d]
    for _ in range(10):
        rc, aus = docker.lauf(befehl + ["config", "--format", "json"], cwd=app,
                              zeit_s=120, pruefen=False)
        if rc == 0:
            return json.loads(aus[aus.index("{"):])
        m = re.search(r"env file (\S+) not found", aus)
        if m and os.path.realpath(m.group(1)).startswith(os.path.realpath(app) + os.sep):
            os.makedirs(os.path.dirname(m.group(1)), exist_ok=True)
            os.close(os.open(m.group(1), os.O_WRONLY | os.O_CREAT, 0o600))
            continue
        raise Abbruch("docker compose versteht die Datei nicht:\n%s"
                      % docker.kern_der_meldung(aus.replace(app, "app")))
    raise Abbruch("Zu viele fehlende env_file-Dateien.")


def gefahren(cfg, app):
    """Alles, womit ein Container aus seinem Kaefig auf den Server greift.
    Gibt (gefahren, hinweise, binds_aussen) zurueck."""
    gef, hin, aussen = [], [], []
    app_echt = os.path.realpath(app)
    for dname, d in sorted((cfg.get("services") or {}).items()):
        d = d or {}

        def g(text):
            gef.append("%s: %s" % (dname, text))

        for k, warum in KAEFIG.items():
            w = d.get(k)
            if (k == "privileged" and w is True) or (k != "privileged" and str(w or "") == "host"):
                g(warum)
        nm = str(d.get("network_mode") or "")
        if nm == "host":
            g("hängt direkt im Netz des Servers (network_mode: host) - an Traefik und "
              "Anmeldung vorbei")
        elif nm:
            g("teilt das Netz eines anderen Containers (network_mode: %s)" % nm)
        if d.get("cap_add"):
            g("holt Linux-Fähigkeiten zurück: %s" % ", ".join(sorted(map(str, d["cap_add"]))))
        if d.get("devices"):
            g("greift auf Geräte des Servers zu (devices)")
        for s in d.get("security_opt") or []:
            if re.search(r"unconfined|label[:=]disable", str(s)):
                g("schaltet einen Schutz ab (security_opt: %s)" % s)
        for v in d.get("volumes") or []:
            if not isinstance(v, dict) or v.get("type") != "bind":
                continue
            quelle = os.path.realpath(str(v.get("source") or ""))
            if SOCKET.search(quelle):
                g("hängt den Docker-Socket ein - das ist root auf dem Server")
            elif quelle == app_echt:
                g("hängt seinen ganzen Ordner ein (samt .env)")
            elif not quelle.startswith(app_echt + os.sep):
                g("hängt %s vom Server ein - das liegt außerhalb des Tools und wird "
                  "NICHT gesichert" % quelle)
                aussen.append(quelle)
        bild = str(d.get("image") or "")
        if bild and not d.get("build") and (bild.endswith(":latest") or
                                            ":" not in bild.rsplit("/", 1)[-1]):
            hin.append("%s: Abbild %s ohne feste Fassung - ein Update kann einen großen "
                       "Sprung machen" % (dname, bild))
        if d.get("container_name"):
            hin.append("%s: fester Containername %s" % (dname, d["container_name"]))
        labels = d.get("labels") or {}
        if any(str(k).startswith("traefik.") for k in labels):
            hin.append("%s: bringt eigene Traefik-Einstellungen mit - prolo ersetzt sie" % dname)
    for k, v in (cfg.get("volumes") or {}).items():
        if (v or {}).get("external"):
            gef.append("erwartet ein fremdes Volume %s (external)" % ((v or {}).get("name") or k))
    return gef, hin, aussen


def ports_von(d):
    ziele = set()
    for p in d.get("ports") or []:
        if isinstance(p, dict) and p.get("target"):
            ziele.add(str(p["target"]))
    for x in d.get("expose") or []:
        ziele.add(str(x).split("/")[0])
    return ziele


def abbild_info(abbild):
    """(ExposedPorts, Volumes) eines vorhandenen Abbilds."""
    rc, aus = docker.lauf(["docker", "image", "inspect", abbild, "--format",
                           "{{json .Config.ExposedPorts}}|{{json .Config.Volumes}}"],
                          pruefen=False, zeit_s=60)
    if rc != 0:
        return set(), set()
    teil = aus.strip().split("|", 1)
    try:
        ports = {k.split("/")[0] for k in (json.loads(teil[0]) or {})}
        vols = set(json.loads(teil[1]) or {})
    except (ValueError, IndexError):
        return set(), set()
    return ports, vols


def dienst_waehlen(cfg, name, dienst, port):
    dienste = cfg.get("services") or {}
    if dienst:
        if dienst not in dienste:
            raise Abbruch("Einen Dienst '%s' gibt es in der Compose-Datei nicht. Vorhanden: %s"
                          % (dienst, ", ".join(sorted(dienste))))
    else:
        kandidaten = ([name] if name in dienste else
                      list(dienste) if len(dienste) == 1 else
                      [n for n, d in dienste.items()
                       if ports_von(d or {}) and not HILFSDIENST.search(str((d or {}).get("image", "")))])
        if len(kandidaten) != 1:
            raise Abbruch("Welcher Dienst ist die Oberfläche? In Frage kommen: %s\n"
                          "  Angeben mit  --dienst <name>."
                          % ", ".join(sorted(kandidaten or dienste)))
        dienst = kandidaten[0]
    d = dienste[dienst] or {}
    if not port:
        ziele = ports_von(d) or abbild_info(str(d.get("image") or ""))[0]
        if len(ziele) != 1:
            raise Abbruch("Auf welchem Port antwortet %s? %s\n  Angeben mit  --port <zahl>."
                          % (dienst, ("In Frage kommen: " + ", ".join(sorted(ziele)))
                             if ziele else "Die Datei sagt es nicht."))
        port = ziele.pop()
    if not PORT.fullmatch(str(port)) or int(port) > 65535:
        raise Abbruch("Port: eine Zahl von 1 bis 65535.")
    if d.get("network_mode"):
        raise Abbruch("%s nutzt network_mode und lässt sich darum nicht an Traefik hängen."
                      % dienst)
    return dienst, str(port)


# --------------------------------------------------------- Erzeugen
def q(text):
    """Ein YAML-Text in doppelten Anfuehrungszeichen (JSON ist gueltiges YAML)."""
    return json.dumps(str(text), ensure_ascii=False)


def abbild_compose(name, abbild, port):
    """Eine Compose-Datei fuer ein einzelnes Abbild - mit einem benannten
    Volume je VOLUME des Abbilds, damit die Sicherung sie findet."""
    ports, vols = abbild_info(abbild)
    zeilen = [KOPF, "services:\n", "  %s:\n" % name, "    image: %s\n" % q(abbild),
              "    restart: unless-stopped\n"]
    if port or ports:
        zeilen.append("    expose: [%s]\n" % ", ".join(q(p) for p in sorted({port} if port else ports)))
    namen = []
    if vols:
        zeilen.append("    volumes:\n")
        for i, pfad in enumerate(sorted(vols), 1):
            vname = "daten" if len(vols) == 1 else "daten-%d" % i
            namen.append(vname)
            zeilen.append("      - %s\n" % q("%s:%s" % (vname, pfad)))
    if namen:
        zeilen.append("volumes:\n")
        zeilen += ["  %s: {}\n" % v for v in namen]
    return "".join(zeilen)


def override_text(name, cfg, c):
    """prolo.override.yml aus der zusammengesetzten Konfiguration der
    Herstellerdatei (cfg) und prolo.conf (c)."""
    dienst, port, anm = c["DIENST"], c["PORT"], c["ANMELDUNG"]
    router = "tool-%s" % name
    zeilen = [KOPF, "services:\n"]
    neue_volumes = []
    for dname, d in sorted((cfg.get("services") or {}).items()):
        d = d or {}
        teil = []
        if d.get("ports"):
            teil.append("    ports: !reset []\n")
        if not d.get("restart"):
            teil.append("    restart: unless-stopped\n")
        if not d.get("logging"):
            teil.append("    logging:\n      driver: json-file\n"
                        "      options: {max-size: \"10m\", max-file: \"3\"}\n")
        # Was das Abbild als VOLUME erklaert, die Datei aber nicht nennt,
        # wuerde ein anonymes Volume - und das findet keine Wiederherstellung
        # wieder. Darum bekommt es hier einen Namen.
        ziele = {str(v.get("target")) for v in d.get("volumes") or [] if isinstance(v, dict)}
        fehlend = sorted(abbild_info(str(d.get("image") or ""))[1] - ziele) if d.get("image") else []
        if fehlend:
            teil.append("    volumes:\n")
            for pfad in fehlend:
                vname = ("%s-%s" % (dname, re.sub(r"[^a-z0-9]+", "-", pfad.lower()).strip("-")))[:60]
                neue_volumes.append(vname)
                teil.append("      - %s\n" % q("%s:%s" % (vname, pfad)))
        if dname == dienst:
            # Alle bisherigen Netze ausdruecklich nennen: ein Dienst ohne
            # networks-Zeile haengt im unsichtbaren "default" - und waere
            # sonst nur noch in "prolo" und faende seine Datenbank nicht mehr.
            teil.append("    networks:\n")
            for netz in sorted(d.get("networks") or {"default": None}):
                teil.append("      %s: {}\n" % q(netz))
            teil.append("      prolo: {}\n")
            labels = {k: v for k, v in (d.get("labels") or {}).items()
                      if not str(k).startswith("traefik.")}
            fremd = len(labels) != len(d.get("labels") or {})
            labels.update({
                "traefik.enable": "true",
                "traefik.docker.network": netzname(name),
                "traefik.http.routers.%s.rule" % router: "Host(`%s`)" % c["HOST"],
                "traefik.http.routers.%s.entrypoints" % router: "websecure",
                "traefik.http.services.%s.loadbalancer.server.port" % router: port,
            })
            if anm == "authentik":
                labels["traefik.http.routers.%s.middlewares" % router] = "authentik@file"
            teil.append("    labels:%s\n" % (" !override" if fremd else ""))
            teil += ["      %s: %s\n" % (q(k), q(v)) for k, v in labels.items()]
        if teil:
            zeilen.append("  %s:\n" % q(dname))
            zeilen += teil
    zeilen += ["networks:\n", "  prolo:\n", "    name: %s\n" % q(netzname(name)),
               "    external: true\n"]
    if neue_volumes:
        zeilen.append("volumes:\n")
        zeilen += ["  %s: {}\n" % q(v) for v in neue_volumes]
    return "".join(zeilen)


def netze_schreiben():
    """/var/lib/prolo/unterbau-netze.yml: Traefik haengt in jedem Tool-Netz."""
    alle = namen()
    if not alle:
        if os.path.exists(orte.NETZE_YML):
            os.remove(orte.NETZE_YML)
        return
    zeilen = [KOPF, "# Traefik hängt in den Netzen aller Tools - und als Einziger.\n",
              "services:\n  traefik:\n    networks:\n"]
    zeilen += ["      %s: {}\n" % q(netzname(n)) for n in alle]
    zeilen.append("networks:\n")
    for n in alle:
        zeilen += ["  %s:\n" % q(netzname(n)), "    name: %s\n" % q(netzname(n)),
                   "    external: true\n"]
    orte.datei_schreiben(orte.NETZE_YML, "".join(zeilen), 0o644)


def traefik_verbinden(name, an=True):
    """Traefik sofort ins Netz haengen (oder heraus) - ohne Neustart. Beim
    naechsten Neuanlegen kommt es aus unterbau-netze.yml."""
    _, aus = docker.unterbau("ps", "-q", "traefik", pruefen=False, zeit_s=60)
    cid = aus.strip().splitlines()[-1] if aus.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{12,64}", cid):
        return
    befehl = ["docker", "network", "connect" if an else "disconnect", netzname(name), cid]
    rc, aus = docker.lauf(befehl, pruefen=False, zeit_s=60)
    if rc != 0 and "already exists" not in aus and "is not connected" not in aus:
        orte.warnung("Traefik ließ sich nicht %s %s hängen: %s"
                     % ("in" if an else "aus", netzname(name), aus.strip()[:200]))


def warten(name, zeit_s=180):
    """Bis alle Container laufen und keiner mehr startet. Gibt den Zustand."""
    ende = time.time() + zeit_s
    z = "aus"
    while time.time() < ende:
        z = docker.zustand(docker.container(name))
        if z in ("gesund", "laeuft", "krank"):
            return z
        time.sleep(3)
    return z


def conf_schreiben(name, c, ordner=None):
    reihenfolge = ("QUELLE", "ABBILD", "GIT", "DIENST", "PORT", "HOST", "ANMELDUNG", "ANGELEGT")
    werte = {k: c[k] for k in reihenfolge if c.get(k)}
    orte.env_schreiben(os.path.join(ordner or docker.tool_ordner(name), "prolo.conf"), werte,
                       "# Was prolo über dieses Tool weiß. Ändern mit: prolo tool set %s ..."
                       % name, 0o644)


def override_neu(name, c, ordner=None):
    """prolo.override.yml aus der Herstellerdatei neu schreiben."""
    ordner = ordner or docker.tool_ordner(name)
    app = os.path.join(ordner, "app")
    basis = docker.basis_in(app)
    if basis is None:
        raise Abbruch("In %s liegt keine Compose-Datei (docker-compose.yml)." % app)
    cfg = config(app, [basis], name)
    if c["DIENST"] not in (cfg.get("services") or {}):
        raise Abbruch("Den Dienst %s gibt es in der Compose-Datei nicht mehr. Neu wählen:  "
                      "prolo tool set %s --dienst <name>" % (c["DIENST"], name))
    zusatz = os.path.join(ordner, "prolo.override.yml")
    orte.datei_schreiben(zusatz, override_text(name, cfg, c), 0o644)
    # Gegenprobe: versteht compose beide Dateien zusammen?
    config(app, [basis, zusatz], name)
    return cfg


# ----------------------------------------------------------- Befehle
def anlegen(name, abbild=None, compose=None, git=None, dienst=None, port=None,
            anmeldung="authentik", host=None, env=None, ja=False, von_web=False):
    orte.root_noetig("tool add")
    try:
        name_pruefen(name)
    except Ungueltig as u:
        raise Abbruch(str(u))
    if sum(bool(x) for x in (abbild, compose, git)) != 1:
        raise Abbruch("Genau eine Quelle angeben:  --image <abbild>  |  --compose <datei>  |  "
                      "--git <url>")
    if anmeldung not in ANMELDUNG:
        raise Abbruch("--anmeldung ist authentik oder keine.")
    if dienst and not DIENST.fullmatch(dienst):
        raise Abbruch("--dienst: so heißt kein Dienst.")
    k = orte.konf()
    host = (host or "%s.%s" % (name, k["PROLO_DOMAIN"])).lower()
    if not orte.DOMAIN.fullmatch(host):
        raise Abbruch("--host %s ist kein gültiger Name." % host)
    if anmeldung == "authentik" and not (host == k["PROLO_DOMAIN"] or
                                         host.endswith("." + k["PROLO_DOMAIN"])):
        raise Abbruch("Die Anmeldung über Authentik gilt für %s und seine Subdomains - "
                      "%s liegt nicht darunter." % (k["PROLO_DOMAIN"], host))
    if host in ("admin." + k["PROLO_DOMAIN"], "auth." + k["PROLO_DOMAIN"]):
        raise Abbruch("%s gehört dem Unterbau." % host)
    for n in namen():
        if n == name:
            raise Abbruch("Ein Tool '%s' gibt es schon:  prolo tool update %s" % (name, name))
        if conf(n).get("HOST") == host:
            raise Abbruch("%s ist schon vergeben - an das Tool %s." % (host, n))

    ziel = docker.tool_ordner(name)
    tmp = os.path.join(orte.TOOLS, ".neu-" + name)
    with orte.sperre("tool add " + name):
        if os.path.exists(ziel):
            raise Abbruch("%s gibt es schon, aber ohne prolo.conf. Erst ansehen, dann von "
                          "Hand wegräumen." % ziel)
        shutil.rmtree(tmp, ignore_errors=True)
        app = os.path.join(tmp, "app")
        os.makedirs(app, mode=0o700)
        os.chmod(tmp, 0o700)
        angelegt = False
        try:
            orte.abschnitt("Tool %s anlegen" % name)
            if abbild:
                print("  Hole %s ..." % abbild, flush=True)
                rc, aus = docker.lauf(["docker", "pull", abbild], zeit_s=1800, pruefen=False)
                if rc != 0:
                    if docker.lauf(["docker", "image", "inspect", abbild], pruefen=False)[0] != 0:
                        raise Abbruch("%s ließ sich nicht holen:\n%s"
                                      % (abbild, docker.kern_der_meldung(aus)))
                    orte.warnung("%s ließ sich nicht holen - es geht mit dem vorhandenen weiter"
                                 % abbild)
                orte.datei_schreiben(os.path.join(app, "docker-compose.yml"),
                                     abbild_compose(name, abbild, port), 0o644)
                dienst = dienst or name
            elif compose:
                try:
                    with open(compose, encoding="utf-8") as f:
                        text = f.read()
                except (OSError, UnicodeDecodeError) as e:
                    raise Abbruch("%s ist nicht lesbar: %s" % (compose, e))
                orte.datei_schreiben(os.path.join(app, "docker-compose.yml"), text, 0o644)
            else:
                print("  Klone %s ..." % git, flush=True)
                os.rmdir(app)
                docker.lauf(["git", "clone", "--quiet", "--", git, app], zeit_s=600,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            orte.ok("Quelle liegt in %s/app" % ziel)

            erzeugt = env_fuellen(app, host, env or {})
            if erzeugt:
                orte.getan("in app/.env eingetragen: %s" % ", ".join(erzeugt))
            basis = docker.basis_in(app)
            if basis is None:
                raise Abbruch("Im Repository liegt keine docker-compose.yml (oder compose.yaml).")
            cfg = config(app, [basis], name)
            gef, hin, _ = gefahren(cfg, app)
            for h in hin:
                orte.warnung(h)
            if gef:
                for g in gef:
                    orte.fehler(g)
                if von_web:
                    raise Abbruch("Mit diesen Gefahren legt die Admin-Seite nichts an. Wer das "
                                  "wirklich will, tut es auf dem Server:  sudo prolo tool add ...")
                if not ja and not frage("Trotzdem anlegen?"):
                    raise Abbruch("Nichts angelegt.")
            # Erst holen und bauen, dann den Port bestimmen: steht er nicht in der
            # Datei, sagt ihn das Abbild - und das muss dafür schon da sein (N-130).
            befehl = ["docker", "compose", "-p", name, "--project-directory", app, "-f", basis]
            rc = 0
            if not abbild:          # ein einzelnes Abbild ist oben schon geholt
                print("  Hole die Abbilder ...", flush=True)
                rc, aus = docker.lauf(befehl + ["pull", "--ignore-buildable"], cwd=app,
                                      zeit_s=1800, pruefen=False)
            if rc != 0:
                # Was schon da ist, reicht zum Starten - was fehlt, meldet "up".
                orte.warnung("nicht alle Abbilder ließen sich holen:\n"
                             + docker.kern_der_meldung(aus, 3))
            if any((d or {}).get("build") for d in (cfg.get("services") or {}).values()):
                print("  Baue ...", flush=True)
                docker.lauf(befehl + ["build"], cwd=app, zeit_s=3600)
            dienst, port = dienst_waehlen(cfg, name, dienst, port)
            orte.ok("Oberfläche: Dienst %s, Port %s" % (dienst, port))

            c = {"QUELLE": "image" if abbild else "compose" if compose else "git",
                 "ABBILD": abbild or "", "GIT": git or "", "DIENST": dienst, "PORT": port,
                 "HOST": host, "ANMELDUNG": anmeldung,
                 "ANGELEGT": time.strftime("%Y-%m-%dT%H:%M:%S")}
            conf_schreiben(name, c, tmp)
            override_neu(name, c, tmp)

            if docker.netz_anlegen(netzname(name)):
                orte.getan("Netz %s angelegt" % netzname(name))
            os.rename(tmp, ziel)
            angelegt = True
            netze_schreiben()
            traefik_verbinden(name)
            print("  Starte ...", flush=True)
            docker.tool(name, "up", "-d", "--remove-orphans", zeit_s=1800)
            z = warten(name)
            if z == "krank":
                orte.warnung("%s läuft, meldet sich aber krank:  prolo tool logs %s" % (name, name))
            elif z in ("aus", "teilweise"):
                raise Abbruch("%s kam nicht hoch:\n%s" % (name, docker.kern_der_meldung(
                    docker.tool(name, "logs", "--tail", "30", "--no-color", pruefen=False)[1], 12)))
            orte.ok("%s läuft: %s  (%s)" % (name, url(c), "Anmeldung über Authentik"
                                              if anmeldung == "authentik" else "OHNE Anmeldung"))
        except BaseException:
            # Kein halbes Tool liegen lassen (§12): was schon steht, wieder weg.
            if angelegt:
                docker.tool(name, "down", "-v", "--remove-orphans", pruefen=False)
                traefik_verbinden(name, an=False)
                shutil.rmtree(ziel, ignore_errors=True)
                netze_schreiben()
            docker.netz_entfernen(netzname(name))
            shutil.rmtree(tmp, ignore_errors=True)
            raise


def frage(text):
    if not sys.stdin.isatty():
        return False
    try:
        return input("  %s [j/N] " % text).strip().lower() in ("j", "ja", "y", "yes")
    except EOFError:
        return False


def aendern(name, port=None, anmeldung=None, dienst=None, host=None):
    orte.root_noetig("tool set")
    c = conf(name)
    if port:
        if not PORT.fullmatch(port) or int(port) > 65535:
            raise Abbruch("--port: eine Zahl von 1 bis 65535.")
        c["PORT"] = port
    if anmeldung:
        if anmeldung not in ANMELDUNG:
            raise Abbruch("--anmeldung ist authentik oder keine.")
        c["ANMELDUNG"] = anmeldung
    if dienst:
        c["DIENST"] = dienst
    if host:
        if not orte.DOMAIN.fullmatch(host):
            raise Abbruch("--host %s ist kein gültiger Name." % host)
        c["HOST"] = host
    with orte.sperre("tool set " + name):
        override_neu(name, c)
        conf_schreiben(name, c)
        docker.tool(name, "up", "-d", "--remove-orphans")
    orte.ok("%s: Port %s, Anmeldung %s, %s" % (name, c["PORT"], c["ANMELDUNG"], url(c)))


def starten(name):
    orte.root_noetig("tool start")
    conf(name)
    with orte.sperre("tool start " + name):
        docker.tool(name, "up", "-d", "--remove-orphans")
    orte.ok("%s: %s" % (name, warten(name, 120)))


def anhalten(name):
    orte.root_noetig("tool stop")
    conf(name)
    with orte.sperre("tool stop " + name):
        docker.tool(name, "stop")
    orte.ok("%s angehalten" % name)


def neustarten(name):
    orte.root_noetig("tool restart")
    conf(name)
    with orte.sperre("tool restart " + name):
        docker.tool(name, "restart")
    orte.ok("%s: %s" % (name, warten(name, 120)))


def protokoll(name, zeilen="100", folgen=False):
    orte.root_noetig("tool logs")
    conf(name)
    args = ["logs", "--tail", str(zeilen), "--no-color"] + (["-f"] if folgen else [])
    return docker.mit_ausgabe(docker.tool_befehl(name, *args),
                              cwd=os.path.join(docker.tool_ordner(name), "app"))


def aktualisieren(name, sichern=True):
    from . import sicherung
    orte.root_noetig("tool update")
    c = conf(name)
    if sichern:
        sicherung.sichern(nur=[name], grund="vor dem Update von %s" % name)
    with orte.sperre("tool update " + name):
        orte.abschnitt("%s aktualisieren" % name)
        app = os.path.join(docker.tool_ordner(name), "app")
        if c.get("QUELLE") == "git":
            _, aus = docker.lauf(["git", "-C", app, "-c", "safe.directory=" + app, "pull",
                                  "--ff-only"], zeit_s=600,
                                 env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            orte.ok("git: %s" % (aus.strip().splitlines() or ["?"])[-1])
        override_neu(name, c)
        rc, aus = docker.tool(name, "pull", "--ignore-buildable", zeit_s=1800, pruefen=False)
        if rc != 0:
            orte.warnung("nicht alle Abbilder ließen sich holen:\n" + docker.kern_der_meldung(aus, 3))
        docker.tool(name, "build", "--pull", zeit_s=3600, pruefen=False)
        docker.tool(name, "up", "-d", "--remove-orphans", zeit_s=1800)
        z = warten(name)
    if z in ("aus", "teilweise", "krank"):
        raise Abbruch("%s ist nach dem Update %s. Protokoll:  prolo tool logs %s\n"
                      "  Zurück auf den Stand davor:  prolo restore --tool %s"
                      % (name, z, name, name))
    orte.ok("%s ist aktuell und %s" % (name, z))


def entfernen(name, ja=False, sichern=True):
    from . import sicherung
    orte.root_noetig("tool rm")
    conf(name)
    if not ja and not frage("%s mit allen Daten entfernen? (vorher wird es gesichert)" % name):
        raise Abbruch("Nichts entfernt.")
    stand = None
    if sichern:
        stand = sicherung.sichern(nur=[name], grund="vor dem Entfernen von %s" % name)
    with orte.sperre("tool rm " + name):
        docker.tool(name, "down", "-v", "--remove-orphans", zeit_s=600)
        traefik_verbinden(name, an=False)
        shutil.rmtree(docker.tool_ordner(name))
        netze_schreiben()
        docker.netz_entfernen(netzname(name))
    orte.ok("%s ist entfernt." % name)
    if stand:
        print("  Zurückholen geht, solange die Sicherung liegt:  sudo prolo restore %s --tool %s"
              % (stand, name))


def liste():
    alle = namen()
    if not alle:
        print("Noch keine Tools. Eines installieren:  sudo prolo tool add <name> --image <abbild>")
        return
    cs = docker.container()
    print("%-16s %-10s %-11s %s" % ("TOOL", "ZUSTAND", "ANMELDUNG", "ADRESSE"))
    for n in alle:
        c = conf(n)
        print("%-16s %-10s %-11s %s" % (n, docker.zustand([x for x in cs if x["projekt"] == n]),
                                        c.get("ANMELDUNG", "?"), url(c)))
