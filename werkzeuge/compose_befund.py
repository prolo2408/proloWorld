#!/usr/bin/env python3
"""werkzeuge/compose_befund.py - was steht in einer Compose-Datei? (A-03)

Eine Compose-Datei, die jemand in die Admin-Seite wirft oder "prolo neu
--compose" gibt, ist die Datei eines Herstellers - und fremde Eingabe
(§11). Bevor daraus ein Werkzeug wird, sagt dieser Befund:

  - welche Dienste es gibt, mit Abbild, Ports, expose
  - welcher Dienst vermutlich der ist, zu dem Traefik fuehren soll, und
    auf welchem Port (ein VORSCHLAG - bestaetigt wird er von einem Menschen)
  - welche Volumes und Bind-Mounts entstehen (-> sicherung.conf)
  - welche Variablen ${...} die Datei erwartet (-> .env)
  - welche GEFAHREN darin stehen: alles, womit ein Container aus seinem
    Kaefig heraus auf den Server greift

Gelesen wird ueber "docker compose config", nicht mit einem eigenen
YAML-Leser: was Compose selbst versteht, ist die Wahrheit (§16). Das
braucht keinen laufenden Docker-Dienst.

    compose_befund.py <compose-datei> <werkzeugname>

Ausgabe: JSON auf stdout. Rueckgabe 0, wenn die Datei lesbar war (auch mit
Gefahren darin), 1 sonst - der Grund steht dann unter "fehler".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MAX_BYTE = 256 * 1024
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)((?::?[-?+])([^}]*))?\}")
GEHEIM = re.compile(r"PASS|SECRET|KEY|TOKEN|SALT|CREDENTIAL", re.I)
SOCKET = ("/var/run/docker.sock", "/run/docker.sock")
# Hilfsdienste, zu denen Traefik nie fuehrt - fuer den Vorschlag, welcher
# Dienst der ist, den man im Browser oeffnet.
HILFSDIENST = re.compile(r"(^|/)(postgres|postgis|mysql|mariadb|redis|valkey|mongo|"
                         r"memcached|rabbitmq|elasticsearch|opensearch|clickhouse|"
                         r"minio|typesense|meilisearch)(:|$)", re.I)
# Was an Faehigkeiten und Einstellungen einen Container aus seinem Kaefig
# laesst. Jede davon kann gewollt sein - aber nicht aus einem Webformular.
KAEFIG = {
    "privileged": "laeuft mit ALLEN Rechten des Servers (privileged)",
    "pid": "sieht alle Prozesse des Servers (pid: host)",
    "ipc": "teilt den Speicher mit dem Server (ipc: host)",
    "uts": "teilt den Rechnernamen mit dem Server (uts: host)",
    "userns_mode": "verlaesst den Nutzer-Namensraum (userns_mode: host)",
    "cgroup": "teilt die cgroups mit dem Server (cgroup: host)",
}


def fehler(text):
    print(json.dumps({"ok": False, "fehler": text}, ensure_ascii=False))
    return 1


def konfig(ordner, name):
    """docker compose config - und wenn eine env_file fehlt, wird sie
    leer angelegt und neu gelesen. Hersteller legen ihre .env fast immer
    daneben; die gibt es hier (noch) nicht, und ohne sie laesst Compose
    die ganze Datei nicht gelten."""
    angelegt = []
    for _ in range(10):
        r = subprocess.run(["docker", "compose", "-p", name, "config",
                            "--no-interpolate", "--format", "json"],
                           cwd=ordner, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return json.loads(r.stdout), angelegt, ""
        m = re.search(r"env file (\S+) not found", r.stderr)
        if m and m.group(1).startswith(ordner + os.sep) and m.group(1) not in angelegt:
            os.makedirs(os.path.dirname(m.group(1)), exist_ok=True)
            open(m.group(1), "w").close()
            angelegt.append(m.group(1))
            continue
        zeilen = [z.strip() for z in r.stderr.strip().splitlines() if z.strip()]
        return None, angelegt, (zeilen[-1] if zeilen else "Rueckgabe %d" % r.returncode)
    return None, angelegt, "zu viele fehlende env_file"


def befund(pfad, name):
    if not NAME.fullmatch(name or ""):
        return None, "Werkzeugname: nur Kleinbuchstaben, Ziffern und Bindestrich."
    try:
        if os.path.getsize(pfad) > MAX_BYTE:
            return None, "Die Datei ist groesser als %d KiB." % (MAX_BYTE // 1024)
        with open(pfad, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return None, "Die Datei ist nicht lesbar: %s" % e
    ordner = tempfile.mkdtemp(prefix="compose-befund-")
    try:
        with open(os.path.join(ordner, "docker-compose.yml"), "w", encoding="utf-8") as f:
            f.write(text)
        try:
            c, env_dateien, grund = konfig(ordner, name)
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            return None, "docker compose config lief nicht: %s" % e
        if c is None:
            # Im Wortlaut von docker, aber ohne den Wegwerfpfad (N-64, §22).
            return None, "docker compose sagt: %s" % grund.replace(ordner + os.sep, "").replace(ordner, ".")
        return auswerten(c, text, name, ordner, env_dateien), ""
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


def auswerten(c, text, name, ordner, env_dateien):
    dienste, gefahren, binds = [], [], []
    for dname, d in sorted((c.get("services") or {}).items()):
        d = d or {}
        ports = []
        for p in d.get("ports") or []:
            if isinstance(p, dict):
                ports.append({"ziel": str(p.get("target", "")),
                              "veroeffentlicht": str(p.get("published") or ""),
                              "adresse": str(p.get("host_ip") or "")})
        expose = sorted({str(x).split("/")[0] for x in d.get("expose") or []})
        bild = str(d.get("image") or "")
        dienste.append({"name": dname, "abbild": bild, "ports": ports, "expose": expose,
                        "baut": bool(d.get("build")),
                        "hilfsdienst": bool(HILFSDIENST.search(bild))})
        # env_file: Compose laesst eine fehlende Datei beim Lesen durchgehen,
        # beim Starten nicht. Sie gehoert also angelegt - leer, 0600.
        for ef in d.get("env_file") or []:
            ep = ef.get("path") if isinstance(ef, dict) else ef
            if ep and str(ep).startswith(ordner + os.sep):
                env_dateien.append(str(ep))

        def gefahr(was):
            gefahren.append({"dienst": dname, "was": was})

        if d.get("build"):
            gefahr("baut aus Quellcode (build:) - ein eigenes Werkzeug gehoert in "
                   "sein eigenes Repository und kommt als fertiges Abbild (U-04)")
        elif not bild:
            gefahr("hat kein Abbild")
        elif ":" not in bild.rsplit("/", 1)[-1] and "@" not in bild:
            gefahr("Abbild %s ohne feste Fassung (§19: nie latest)" % bild)
        elif bild.endswith(":latest"):
            gefahr("Abbild %s mit latest (§19: nie latest)" % bild)
        for schluessel, warum in KAEFIG.items():
            wert = d.get(schluessel)
            if (schluessel == "privileged" and wert is True) or \
               (schluessel != "privileged" and str(wert or "") == "host"):
                gefahr(warum)
        nm = str(d.get("network_mode") or "")
        if nm == "host":
            gefahr("haengt direkt im Netz des Servers (network_mode: host) - an "
                   "Traefik, Anmeldung und Firewall vorbei")
        elif nm.startswith("container:"):
            gefahr("haengt im Netz eines FREMDEN Containers (%s)" % nm)
        if d.get("cap_add"):
            gefahr("holt Linux-Faehigkeiten zurueck: %s" % ", ".join(sorted(map(str, d["cap_add"]))))
        if d.get("devices"):
            gefahr("greift auf Geraete des Servers zu (devices)")
        for s in d.get("security_opt") or []:
            if re.search(r"unconfined|label[:=]disable", str(s)):
                gefahr("schaltet einen Schutz ab (security_opt: %s)" % s)
        for v in d.get("volumes") or []:
            if not isinstance(v, dict) or v.get("type") != "bind":
                continue
            quelle = str(v.get("source") or "")
            if quelle in SOCKET or quelle.endswith("/docker.sock"):
                gefahr("haengt den Docker-Socket ein - das ist root auf dem Server")
            elif quelle == ordner or quelle.startswith(ordner + os.sep):
                rel = os.path.relpath(quelle, ordner)
                if rel == ".":
                    gefahr("haengt den ganzen Werkzeugordner ein (samt .env)")
                else:
                    binds.append({"dienst": dname, "pfad": rel, "ziel": str(v.get("target", ""))})
            else:
                gefahr("haengt %s vom Server ein" % quelle)

    volumes = sorted((v or {}).get("name") or "%s_%s" % (name, k)
                     for k, v in (c.get("volumes") or {}).items()
                     if not (v or {}).get("external"))
    extern = sorted((v or {}).get("name") or k for k, v in (c.get("volumes") or {}).items()
                    if (v or {}).get("external"))
    for v in extern:
        gefahren.append({"dienst": "-", "was": "erwartet ein fremdes Volume %s (external)" % v})

    variablen = {}
    for m in VARIABLE.finditer(text):
        n = m.group(1)
        op = m.group(2) or ""
        pflicht = not op or "?" in op
        alt = variablen.get(n, {})
        variablen[n] = {"name": n, "geheim": bool(GEHEIM.search(n)),
                        "pflicht": alt.get("pflicht", False) or pflicht,
                        # ${TZ:-Europe/Berlin}: die Vorgabe des Herstellers.
                        "vorgabe": alt.get("vorgabe") or (m.group(3) or "" if "-" in op else "")}

    return {
        "ok": True,
        "dienste": dienste,
        "vorschlag": vorschlag(dienste, name),
        "volumes": volumes,
        "binds": binds,
        "env_dateien": sorted({os.path.relpath(p, ordner) for p in env_dateien}),
        "variablen": [variablen[k] for k in sorted(variablen)],
        "gefahren": gefahren,
    }


def vorschlag(dienste, name):
    """Zu welchem Dienst fuehrt Traefik, auf welchem Port? Nur ein
    Vorschlag, wenn er eindeutig ist - sonst leer, und ein Mensch waehlt.
    Geraten wird nicht (§11)."""
    kandidaten = [d for d in dienste if d["name"] == name] or \
                 (dienste if len(dienste) == 1 else
                  [d for d in dienste if (d["ports"] or d["expose"]) and not d["hilfsdienst"]])
    if len(kandidaten) != 1:
        return {"dienst": "", "port": ""}
    d = kandidaten[0]
    ziele = sorted({p["ziel"] for p in d["ports"] if p["ziel"]} | set(d["expose"]))
    return {"dienst": d["name"], "port": ziele[0] if len(ziele) == 1 else ""}


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("Aufruf: compose_befund.py <compose-datei> <werkzeugname>\n")
        return 2
    b, grund = befund(argv[1], argv[2])
    if b is None:
        return fehler(grund)
    print(json.dumps(b, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
