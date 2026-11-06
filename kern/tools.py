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

from . import docker, kaefig, orte, zugang
from .auftrag import (ANMELDUNG, DIENST, MAX_COMPOSE, PORT, Ungueltig, env_zeilen,
                      name_pruefen)
from .orte import Abbruch

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)((?::?[-?+])([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")
GEHEIM = re.compile(r"PASS|SECRET|KEY|TOKEN|SALT|CREDENTIAL", re.I)
HILFSDIENST = re.compile(r"(^|/)(postgres|postgis|mysql|mariadb|redis|valkey|mongo|memcached|"
                         r"rabbitmq|elasticsearch|opensearch|clickhouse|minio|typesense|"
                         r"meilisearch)(:|$)", re.I)
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


def config(app, dateien, name, env_datei=None):
    """docker compose config fuer app/ - fehlt eine env_file, die die Datei
    erwartet, wird sie leer angelegt (Hersteller legen sie fast immer bei)."""
    befehl = ["docker", "compose", "-p", name, "--project-directory", app]
    if env_datei:
        befehl += ["--env-file", env_datei]
    for d in dateien:
        befehl += ["-f", d]
    for _ in range(10):
        rc, aus = docker.lauf(befehl + ["config", "--format", "json"], cwd=app,
                              env=docker.tool_env(), zeit_s=120, pruefen=False)
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


def gefahren(cfg, app, projekt):
    """Siehe kern/kaefig.py - die Erlaubnisliste."""
    return kaefig.gefahren(cfg, app, projekt)


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
    dienst = c["DIENST"]
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
            # Unter diesem Namen erreicht Traefik das Tool (tool-<name>.yml).
            # Namen mit prolo... darf kein Tool selbst tragen (kaefig.py).
            teil.append("      prolo: { aliases: [ %s ] }\n" % q(ziel_name(name)))
        if teil:
            zeilen.append("  %s:\n" % q(dname))
            zeilen += teil
    zeilen += ["networks:\n", "  prolo:\n", "    name: %s\n" % q(netzname(name)),
               "    external: true\n"]
    if neue_volumes:
        zeilen.append("volumes:\n")
        zeilen += ["  %s: {}\n" % q(v) for v in neue_volumes]
    return "".join(zeilen)


ROUTE_VORSILBE = "tool-"


def ziel_name(name):
    return "prolo-tool-%s" % name


def route_datei(name):
    return os.path.join(orte.VAR, "traefik", "dynamic", "%s%s.yml" % (ROUTE_VORSILBE, name))


def route_text(name, c):
    """Router und Ziel eines Tools fuer Traefik - als Datei, die prolo
    schreibt. Labels an Containern liest Traefik nicht mehr: sonst haette
    jedes Abbild mit "LABEL traefik.http.routers..." admin.<domain>
    uebernommen (gemessen, N-139)."""
    router = "tool-%s" % name
    zeilen = [KOPF, "http:\n  routers:\n", "    %s:\n" % q(router),
              "      rule: %s\n" % q("Host(`%s`)" % c["HOST"]),
              "      entryPoints: [\"websecure\"]\n", "      service: %s\n" % q(router)]
    if c["ANMELDUNG"] == "authentik":
        zeilen.append("      middlewares: [\"authentik@file\"]\n")
    zeilen += ["  services:\n", "    %s:\n" % q(router), "      loadBalancer:\n",
               "        servers:\n",
               "          - url: %s\n" % q("http://%s:%s" % (ziel_name(name), c["PORT"]))]
    return "".join(zeilen)


def route_schreiben(name, c):
    orte.datei_schreiben(route_datei(name), route_text(name, c), 0o644)


def route_entfernen(name):
    try:
        os.remove(route_datei(name))
    except FileNotFoundError:
        pass


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
def _hat_zugang(url):
    try:
        return zugang.host_von(url) in zugang.lesen()
    except (OSError, Abbruch):
        return False


def klonen(url, ziel):
    """git clone mit dem Git-Zugang (N-134); scheitert es, sagt die Meldung,
    was zu tun ist - privat ohne Zugang, Token abgelaufen, nicht freigegeben."""
    rc, aus = docker.lauf(["git", "clone", "--quiet", "--", url, ziel], zeit_s=600,
                          env=zugang.git_env(), pruefen=False)
    if rc != 0:
        raise Abbruch(zugang.fehler_text(url, zugang.host_von(url), aus, _hat_zugang(url)))


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
                klonen(git, app)
            orte.ok("Quelle liegt in %s/app" % ziel)
            # Vor allem anderen: ein Verweis nach draussen (.env -> /etc/prolo/
            # geheim.env) wuerde schon beim Lesen der Datei folgen (N-136).
            frueh = kaefig.verweise(app)
            if frueh:
                for v in frueh:
                    orte.fehler(v)
                if aus_dem_web(von_web):
                    raise Abbruch("Mit diesen Verweisen legt die Admin-Seite nichts an. Wer das "
                                  "wirklich will, tut es auf dem Server:  sudo prolo tool add ...")
                if not ja and not frage("Trotzdem weiter?"):
                    raise Abbruch("Nichts angelegt.")

            erzeugt = env_fuellen(app, host, env or {})
            if erzeugt:
                orte.getan("in app/.env eingetragen: %s" % ", ".join(erzeugt))
            basis = docker.basis_in(app)
            if basis is None:
                raise Abbruch("Im Repository liegt keine docker-compose.yml (oder compose.yaml).")
            cfg = kaefig.modell(app, name, os.path.basename(basis))
            gef, hin, _ = gefahren(cfg, app, name)
            for h in hin:
                orte.warnung(h)
            gef = [g for g in gef if g not in frueh]       # schon bestaetigt
            if gef:
                for g in gef:
                    orte.fehler(g)
                if aus_dem_web(von_web):
                    raise Abbruch("Mit diesen Gefahren legt die Admin-Seite nichts an. Wer das "
                                  "wirklich will, tut es auf dem Server:  sudo prolo tool add ...")
                if not ja and not frage("Trotzdem anlegen?"):
                    raise Abbruch("Nichts angelegt.")
            if gef or frueh:
                bestaetigen(tmp, gef + frueh)
            # Erst holen und bauen, dann den Port bestimmen: steht er nicht in der
            # Datei, sagt ihn das Abbild - und das muss dafür schon da sein (N-130).
            befehl = ["docker", "compose", "-p", name, "--project-directory", app, "-f", basis]
            rc = 0
            if not abbild:          # ein einzelnes Abbild ist oben schon geholt
                print("  Hole die Abbilder ...", flush=True)
                rc, aus = docker.lauf(befehl + ["pull", "--ignore-buildable"], cwd=app,
                                      env=docker.tool_env(), zeit_s=1800, pruefen=False)
            if rc != 0:
                # Was schon da ist, reicht zum Starten - was fehlt, meldet "up".
                orte.warnung("nicht alle Abbilder ließen sich holen:\n"
                             + docker.kern_der_meldung(aus, 3))
            if any((d or {}).get("build") for d in (cfg.get("services") or {}).values()):
                print("  Baue ...", flush=True)
                docker.lauf(befehl + ["build"], cwd=app, env=docker.tool_env(), zeit_s=3600)
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
            route_schreiben(name, c)
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
                route_entfernen(name)
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
        kaefig_pruefen(name, "ändern")
        override_neu(name, c)
        conf_schreiben(name, c)
        route_schreiben(name, c)
        docker.tool(name, "up", "-d", "--remove-orphans")
    orte.ok("%s: Port %s, Anmeldung %s, %s" % (name, c["PORT"], c["ANMELDUNG"], url(c)))


def env_setzen(text, werte):
    """NAME=wert in einer .env setzen: eine vorhandene Zeile wird ersetzt, eine
    neue angehaengt. Alles andere - Kommentare, andere Werte - bleibt."""
    rest = dict(werte)
    zeilen = []
    for zeile in text.splitlines():
        k, gleich, _ = zeile.partition("=")
        k = k.strip()
        if gleich and not k.startswith("#") and k in werte:
            if k in rest:
                zeilen.append("%s=%s" % (k, rest.pop(k)))
            continue            # derselbe Name ein zweites Mal: weg
        zeilen.append(zeile)
    zeilen += ["%s=%s" % (k, v) for k, v in rest.items()]
    return "".join(z + "\n" for z in zeilen)


def compose_text(name, c):
    """Die Compose-Datei eines Tools zum Bearbeiten - None, wenn sie aus Git
    kommt (dort aendern) oder zu gross ist."""
    if c.get("QUELLE") == "git":
        return None
    basis = docker.basis_in(os.path.join(docker.tool_ordner(name), "app"))
    if basis is None:
        return None
    with open(basis, encoding="utf-8", errors="replace") as f:
        text = f.read(MAX_COMPOSE + 1)
    if len(text.encode("utf-8")) > MAX_COMPOSE:
        return None
    return text[len(KOPF):] if text.startswith(KOPF) else text


BESTAETIGT = "prolo.bestaetigt"


def aus_dem_web(flagge=False):
    """Kommt der Befehl von der Admin-Seite? Der Agent setzt PROLO_AGENT=1 fuer
    jeden Auftrag - auch fuer Starten, Aktualisieren, Zurueckholen."""
    return bool(flagge) or os.environ.get("PROLO_AGENT") == "1"


def bestaetigt(ordner):
    """Gefahren, die ein Mensch auf der Kommandozeile bestaetigt hat."""
    try:
        with open(os.path.join(ordner, BESTAETIGT), encoding="utf-8") as f:
            d = json.load(f)
        return set(d) if isinstance(d, list) else set()
    except (OSError, ValueError):
        return set()


def bestaetigen(ordner, gef):
    orte.datei_schreiben(os.path.join(ordner, BESTAETIGT),
                         json.dumps(sorted(set(gef)), ensure_ascii=False, indent=1) + "\n", 0o600)


def kaefig_pruefen(name, was, ja=False, flagge=False, ordner=None):
    """Vor jedem Start: das Modell der Dateien, wie sie JETZT liegen, durch den
    Kaefig. Ein git pull, eine Wiederherstellung, ein Container, der in einem
    eingehaengten Ordner etwas umbaut - alles kann seit dem Anlegen etwas
    geaendert haben (N-138). Bestaetigtes fragt nicht noch einmal; Neues
    lehnt die Admin-Seite ab, die Kommandozeile fragt."""
    ordner = ordner or docker.tool_ordner(name)
    app = os.path.join(ordner, "app")
    basis = docker.basis_in(app)
    if basis is None:
        raise Abbruch("In %s liegt keine Compose-Datei." % app)
    cfg = kaefig.modell(app, name, os.path.basename(basis), auslassen=eingehaengte_ordner(name))
    gef = gefahren(cfg, app, name)[0]
    neu = [g for g in gef if g not in bestaetigt(ordner)]
    if not neu:
        return cfg
    for g in neu:
        orte.fehler(g)
    if aus_dem_web(flagge):
        raise Abbruch("Mit diesen Gefahren kann die Admin-Seite %s nicht %s. Wer das wirklich "
                      "will, tut es auf dem Server:  sudo prolo tool ..." % (name, was))
    if not ja and not frage("Trotzdem %s?" % was):
        raise Abbruch("Nicht bestätigt: %s" % "; ".join(neu))
    bestaetigen(ordner, gef)
    return cfg


def eingehaengte_ordner(name):
    """Ordner in app/, die die Container des Tools gerade einhaengen - dort
    liegen Daten, keine Dateien fuer prolo."""
    app = os.path.join(docker.tool_ordner(name), "app")
    echt = os.path.realpath(app)
    quellen = set()
    try:
        quellen |= {m["quelle"] for m in docker.mounts(name) if m["art"] == "bind"}
    except Abbruch:
        pass
    # Auch die eines angehaltenen Tools: aus der Datei selbst. Auslassen ist
    # immer gefahrlos - fehlt der Pruefung etwas, scheitert sie (N-138).
    try:
        basis = docker.basis_in(app)
        for d in ((config(app, [basis], name).get("services") or {}).values() if basis else ()):
            quellen |= {str(v.get("source")) for v in (d or {}).get("volumes") or []
                        if isinstance(v, dict) and v.get("type") == "bind"}
    except Abbruch:
        pass
    return {q for q in quellen if os.path.realpath(q).startswith(echt + os.sep)}


def variablen_namen(name):
    """Welche Variablen in app/.env stehen - nur die Namen, nie die Werte."""
    return sorted(orte.env_lesen(os.path.join(docker.tool_ordner(name), "app", ".env")))


def bearbeiten(name, compose=None, env=None, ja=False, von_web=False, sichern=True):
    """Die Compose-Datei ersetzen und/oder Variablen in app/.env setzen.

    Erst geprueft wie beim Anlegen (Gefahren, Dienst, fehlende Werte), dann
    gesichert, dann geaendert. Scheitert etwas - auch erst beim Starten -,
    gilt wieder der Stand davor: Dateien zurueck, Container wie vorher."""
    from . import sicherung
    orte.root_noetig("tool edit")
    c = conf(name)
    env = env or {}
    text = None
    if compose:
        if c.get("QUELLE") == "git":
            raise Abbruch("Die Compose-Datei von %s kommt aus %s - dort ändern, dann:  "
                          "sudo prolo tool update %s" % (name, c.get("GIT"), name))
        try:
            with open(compose, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise Abbruch("%s ist nicht lesbar: %s" % (compose, e))
        if not text.strip():
            raise Abbruch("Die neue Compose-Datei ist leer.")
        if text.startswith(KOPF):
            text = text[len(KOPF):]
    if text is None and not env:
        raise Abbruch("Nichts zu ändern:  --compose <datei>  und/oder  --env NAME=wert")
    ordner = docker.tool_ordner(name)
    app = os.path.join(ordner, "app")
    basis = docker.basis_in(app)
    if basis is None:
        raise Abbruch("In %s liegt keine Compose-Datei." % app)
    env_pfad = os.path.join(app, ".env")
    # Erst pruefen, dann sichern: eine kaputte oder gefaehrliche Datei soll das
    # Tool nicht erst fuer eine Sicherung anhalten. Geprueft wird auf einer
    # Kopie, ohne Rechte (kaefig.modell) - mit der neuen Datei und den neuen
    # Variablen, als lägen sie schon in app/.
    orte.abschnitt("%s: die Änderung prüfen" % name)
    with open(basis, encoding="utf-8") as f:
        text_alt = f.read()
    try:
        with open(env_pfad, encoding="utf-8") as f:
            env_alt = f.read()
    except FileNotFoundError:
        env_alt = ""
    eingehaengt = eingehaengte_ordner(name)
    cfg = kaefig.modell(app, name, os.path.basename(basis),
                        compose_text=text_alt if text is None else text,
                        env_text=env_setzen(env_alt, env), auslassen=eingehaengt)
    if c["DIENST"] not in (cfg.get("services") or {}):
        raise Abbruch("Den Dienst %s mit der Oberfläche gibt es in der neuen Datei nicht - "
                      "nichts geändert. Seinen Namen in der Datei lassen, wie er ist."
                      % c["DIENST"])
    gef, hin, _ = gefahren(cfg, app, name)
    for h in hin:
        orte.warnung(h)
    gef = [g for g in gef if g not in bestaetigt(ordner)]
    if gef:
        for g in gef:
            orte.fehler(g)
        if aus_dem_web(von_web):
            raise Abbruch("Mit diesen Gefahren ändert die Admin-Seite nichts. Wer das "
                          "wirklich will, tut es auf dem Server:  sudo prolo tool edit ...")
        if not ja and not frage("Trotzdem ändern?"):
            raise Abbruch("Nichts geändert.")
    schon = bestaetigt(ordner) | set(gef)
    if not gef:
        schon = bestaetigt(ordner)
    orte.ok("die neue Datei ist in Ordnung")
    if sichern:
        sicherung.sichern(nur=[name], grund="vor dem Bearbeiten von %s" % name)
    with orte.sperre("tool edit " + name):
        orte.abschnitt("%s bearbeiten" % name)
        vorher = {}
        for pfad in (basis, env_pfad, os.path.join(ordner, "prolo.conf"),
                     os.path.join(ordner, "prolo.override.yml"), os.path.join(ordner, BESTAETIGT)):
            try:
                with open(pfad, encoding="utf-8") as f:
                    vorher[pfad] = (f.read(), os.stat(pfad).st_mode & 0o777)
            except FileNotFoundError:
                vorher[pfad] = None
        gestartet = False
        try:
            if text is not None:
                orte.datei_schreiben(basis, text, 0o644)
                orte.getan("Compose-Datei ersetzt")
            if env:
                alt = vorher[env_pfad]
                orte.datei_schreiben(env_pfad, env_setzen(alt[0] if alt else "", env), 0o600)
                orte.getan("in app/.env gesetzt: %s" % ", ".join(sorted(env)))
            erzeugt = env_fuellen(app, c["HOST"], {})
            if erzeugt:
                orte.getan("in app/.env eingetragen: %s" % ", ".join(erzeugt))
            # Mit den gefuellten Werten noch einmal: was jetzt neu gefaehrlich
            # ist, hat niemand bestaetigt.
            cfg = kaefig.modell(app, name, os.path.basename(basis), auslassen=eingehaengt)
            jetzt = gefahren(cfg, app, name)[0]
            neu = set(jetzt) - schon
            if neu:
                raise Abbruch("Mit den eingesetzten Werten neu gefährlich: %s" % "; ".join(sorted(neu)))
            if jetzt:
                bestaetigen(ordner, jetzt)
            if text is not None and c.get("QUELLE") == "image":
                # Wer die Datei eines Abbilds bearbeitet, hat danach eine eigene.
                c.update(QUELLE="compose", ABBILD="")
            override_neu(name, c)           # prueft auch: gibt es den Dienst noch?
            conf_schreiben(name, c)
            route_schreiben(name, c)
            print("  Hole die Abbilder ...", flush=True)
            rc, aus = docker.tool(name, "pull", "--ignore-buildable", zeit_s=1800, pruefen=False)
            if rc != 0:
                orte.warnung("nicht alle Abbilder ließen sich holen:\n"
                             + docker.kern_der_meldung(aus, 3))
            if any((d or {}).get("build") for d in (cfg.get("services") or {}).values()):
                docker.tool(name, "build", zeit_s=3600)
            print("  Starte ...", flush=True)
            gestartet = True
            docker.tool(name, "up", "-d", "--remove-orphans", zeit_s=1800)
            z = warten(name)
            if z in ("aus", "teilweise", "krank"):
                raise Abbruch("%s ist mit der Änderung %s:\n%s" % (name, z, docker.kern_der_meldung(
                    docker.tool(name, "logs", "--tail", "30", "--no-color", pruefen=False)[1], 12)))
        except BaseException:
            for pfad, alt in vorher.items():
                if alt is None:
                    if os.path.exists(pfad):
                        os.remove(pfad)
                else:
                    orte.datei_schreiben(pfad, alt[0], alt[1])
            if gestartet:
                rc, aus = docker.tool(name, "up", "-d", "--remove-orphans", zeit_s=1800,
                                      pruefen=False)
                if rc != 0:
                    orte.fehler("Auch der Stand davor startet nicht:\n%s\n  Zurück auf die "
                                "Sicherung:  sudo prolo restore --tool %s"
                                % (docker.kern_der_meldung(aus), name))
            orte.warnung("Nichts geändert - %s hat wieder den Stand davor." % name)
            raise
    orte.ok("%s ist geändert und %s: %s" % (name, z, url(c)))


def starten(name, ja=False):
    orte.root_noetig("tool start")
    conf(name)
    with orte.sperre("tool start " + name):
        kaefig_pruefen(name, "starten", ja)
        docker.tool(name, "up", "-d", "--remove-orphans")
    orte.ok("%s: %s" % (name, warten(name, 120)))


def anhalten(name):
    orte.root_noetig("tool stop")
    conf(name)
    with orte.sperre("tool stop " + name):
        docker.tool(name, "stop")
    orte.ok("%s angehalten" % name)


def neustarten(name, ja=False):
    orte.root_noetig("tool restart")
    conf(name)
    with orte.sperre("tool restart " + name):
        kaefig_pruefen(name, "neu starten", ja)
        docker.tool(name, "restart")
    orte.ok("%s: %s" % (name, warten(name, 120)))


def protokoll(name, zeilen="100", folgen=False):
    orte.root_noetig("tool logs")
    conf(name)
    args = ["logs", "--tail", str(zeilen), "--no-color"] + (["-f"] if folgen else [])
    return docker.mit_ausgabe(docker.tool_befehl(name, *args), env=docker.tool_env(),
                              cwd=os.path.join(docker.tool_ordner(name), "app"))


def aktualisieren(name, sichern=True, ja=False):
    from . import sicherung
    orte.root_noetig("tool update")
    c = conf(name)
    if sichern:
        sicherung.sichern(nur=[name], grund="vor dem Update von %s" % name)
    with orte.sperre("tool update " + name):
        orte.abschnitt("%s aktualisieren" % name)
        app = os.path.join(docker.tool_ordner(name), "app")
        if c.get("QUELLE") == "git":
            git = ["git", "-C", app, "-c", "safe.directory=" + app]
            _, vorher = docker.lauf(git + ["rev-parse", "HEAD"], zeit_s=60)
            rc, aus = docker.lauf(git + ["pull", "--ff-only"], zeit_s=600, env=zugang.git_env(),
                                  pruefen=False)
            if rc != 0:
                url = c.get("GIT", "")
                raise Abbruch(zugang.fehler_text(url, zugang.host_von(url), aus,
                                                 _hat_zugang(url)))
            orte.ok("git: %s" % (aus.strip().splitlines() or ["?"])[-1])
            # Was aus Git kommt, startet erst nach der Pruefung (N-138) - sonst
            # zurueck auf den Stand davor, damit nichts Halbes liegen bleibt.
            try:
                kaefig_pruefen(name, "aktualisieren", ja)
            except BaseException:
                docker.lauf(git + ["reset", "--hard", "--quiet", vorher.strip()], zeit_s=120)
                orte.warnung("zurück auf den Stand davor (%s)" % vorher.strip()[:7])
                raise
        else:
            kaefig_pruefen(name, "aktualisieren", ja)
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
        route_entfernen(name)
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
