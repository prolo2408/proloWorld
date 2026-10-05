#!/usr/bin/env python3
"""Der echte Durchlauf: Unterbau, Tools, Sicherung, Wiederherstellung - mit
Docker, Traefik und Authentik, so wie auf dem Server.

Braucht root und Docker, dauert einige Minuten. Laeuft in eigenen Ordnern
(PROLO_ETC, PROLO_VAR, ...) und raeumt danach alles weg, was er angelegt hat.

    sudo python3 tests/durchlauf.py

Weigert sich, wenn auf dieser Maschine schon ein Unterbau laeuft - er wuerde
dessen Container uebernehmen.
"""
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
PROLO = os.path.join(REPO, "prolo")
DOMAIN = "prolo.test"
TMP = tempfile.mkdtemp(prefix="prolo-durchlauf-")
ENV = dict(os.environ, PROLO_ETC=TMP + "/etc", PROLO_VAR=TMP + "/var", PROLO_TOOLS=TMP + "/tools",
           PROLO_BACKUP=TMP + "/backup", PROLO_OHNE_SYSTEMD="1", NO_COLOR="1",
           PYTHONDONTWRITEBYTECODE="1")
PROJEKTE = ("prolo", "notizen", "zwei", "boese", "drei")
ERGEBNIS = []

TESTBILD = """FROM python:3.13-slim
RUN mkdir -p /daten && echo "hallo" > /daten/index.html
VOLUME /daten
EXPOSE 8000
STOPSIGNAL SIGINT
HEALTHCHECK --interval=5s --timeout=3s CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/')"
CMD ["python3", "-m", "http.server", "8000", "--directory", "/daten"]
"""
ZWEI = """services:
  app:
    image: prolotest/web:1
    ports: ["8080:8000"]
    depends_on: [db]
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - dbdaten:/var/lib/postgresql/data
volumes:
  dbdaten:
"""
# Kein Port in der Datei - den sagt erst das Abbild, und das ist noch nicht da.
DREI = """services:
  web:
    image: traefik/whoami:v1.10
"""
BOESE = """services:
  app:
    image: prolotest/web:1
    privileged: true
    volumes: ["/:/host"]
"""


def sh(*befehl, eingabe=None, pruefen=True, zeit_s=1200):
    r = subprocess.run(befehl, input=eingabe, capture_output=True, text=True, env=ENV,
                       timeout=zeit_s, cwd=REPO)
    if pruefen and r.returncode != 0:
        raise AssertionError("%s -> %d\n%s%s" % (" ".join(befehl), r.returncode, r.stdout[-3000:],
                                                 r.stderr[-2000:]))
    return r


def prolo(*args, pruefen=True):
    return sh(PROLO, *args, pruefen=pruefen)


def stimmt(was, bedingung, mehr=""):
    ERGEBNIS.append((bool(bedingung), was))
    print("  %s  %s%s" % ("ok    " if bedingung else "FALSCH", was, (" - " + mehr) if mehr and not bedingung else ""),
          flush=True)
    if not bedingung:
        raise AssertionError(was)


def https(host, pfad="/", kopf=None):
    """Eine Anfrage an Traefik mit diesem Namen (SNI), ohne DNS."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    v = http.client.HTTPConnection("127.0.0.1", 443, timeout=20)
    v.sock = ctx.wrap_socket(socket.create_connection(("127.0.0.1", 443), 20), server_hostname=host)
    v.request("GET", pfad, headers=dict({"Host": host}, **(kopf or {})))
    r = v.getresponse()
    r.read()
    v.close()
    return r.status, r.getheader("Location") or ""


def im_container(container, code):
    return sh("docker", "exec", container, "python3", "-c", code, pruefen=False).stdout.strip()


def authentik(code):
    r = sh("docker", "exec", "prolo-authentik-worker-1", "ak", "shell", "-c", code, pruefen=False)
    return r.stdout


def neuester_stand():
    return sorted(n for n in os.listdir(ENV["PROLO_BACKUP"]) if not n.startswith("."))[-1]


def schritt(text):
    print("\n== %s" % text, flush=True)


def ablauf():
    schritt("Einrichten")
    prolo("einrichten", "--domain", DOMAIN, "--email", "admin@" + DOMAIN)
    stimmt("Unterbau laeuft, Blueprint wirkt", True)
    # Ein Zertifikat fuer *.prolo.test - Let's Encrypt kennt den Namen nicht.
    dyn = os.path.join(ENV["PROLO_VAR"], "traefik", "dynamic")
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", dyn + "/test.key",
       "-out", dyn + "/test.crt", "-days", "2", "-subj", "/CN=" + DOMAIN,
       "-addext", "subjectAltName=DNS:%s,DNS:*.%s" % (DOMAIN, DOMAIN))
    with open(dyn + "/lokal-test.yml", "w") as f:
        f.write("tls:\n  certificates:\n    - certFile: /etc/traefik/dynamic/test.crt\n"
                "      keyFile: /etc/traefik/dynamic/test.key\n")
    time.sleep(5)

    schritt("Der Eingang")
    st, ziel = https("admin." + DOMAIN)
    stimmt("Admin-Seite ohne Anmeldung -> Authentik", st == 302 and ziel.startswith(
        "https://auth.%s/" % DOMAIN), "%s %s" % (st, ziel))
    st, ziel = https("admin." + DOMAIN, kopf={"X-authentik-username": "akadmin",
                                              "X-authentik-groups": "authentik Admins"})
    stimmt("gefaelschte Anmelde-Kopfzeilen helfen nicht", st == 302 and "auth." in ziel)
    try:
        https("fremd.example")
        fremd = False
    except (ssl.SSLError, ConnectionError, OSError):
        fremd = True
    stimmt("fremder Name bekommt keinen TLS-Handschlag (sniStrict)", fremd)

    schritt("Tools anlegen")
    sh("docker", "build", "-q", "-t", "prolotest/web:1", "-", eingabe=TESTBILD)
    prolo("tool", "add", "notizen", "--image", "prolotest/web:1")
    st, ziel = https("notizen." + DOMAIN)
    stimmt("notizen laeuft hinter der Anmeldung", st == 302 and "auth." in ziel, "%s" % st)
    with open(TMP + "/zwei.yml", "w") as f:
        f.write(ZWEI)
    prolo("tool", "add", "zwei", "--compose", TMP + "/zwei.yml")
    stimmt("App erreicht ihre Datenbank", "ja" in im_container(
        "zwei-app-1", "import socket; socket.create_connection(('db',5432),5); print('ja')"))
    stimmt("App erreicht das andere Tool NICHT", "nein" in im_container(
        "zwei-app-1", "import socket\ntry: socket.create_connection(('notizen',8000),5); print('ja')\n"
                      "except Exception: print('nein')"))
    stimmt("offener Port des Herstellers ist weg",
           sh("docker", "port", "zwei-app-1").stdout.strip() == "")
    with open(TMP + "/boese.yml", "w") as f:
        f.write(BOESE)
    r = prolo("tool", "add", "boese", "--compose", TMP + "/boese.yml", "--ja", "--von-web",
              pruefen=False)
    stimmt("gefaehrliche Compose-Datei wird von der Seite abgelehnt", r.returncode != 0
           and "privileged" in r.stdout)
    stimmt("... und hinterlaesst nichts", not os.path.exists(ENV["PROLO_TOOLS"] + "/boese") and
           sh("docker", "network", "inspect", "tool-boese", pruefen=False).returncode != 0)

    schritt("Sichern")
    sh("docker", "exec", "notizen-notizen-1", "sh", "-c", "echo wichtig > /daten/notiz.txt")
    sh("docker", "exec", "zwei-db-1", "psql", "-U", "postgres", "-c",
       "create table merkmal(x text); insert into merkmal values ('ueberlebt')")
    authentik("from authentik.core.models import Group; Group.objects.get_or_create(name='vorher')")
    prolo("backup")
    stand = neuester_stand()
    with open(os.path.join(ENV["PROLO_BACKUP"], stand, "MANIFEST.json")) as f:
        m = json.load(f)
    stimmt("Sicherung vollstaendig und jedes Stueck gelesen", m["geprueft"] == "ok" and not m["fehler"]
           and m["unterbau"] and m["tools"] == ["notizen", "zwei"])
    teile = {t["datei"] for t in m["teile"]}
    stimmt("alle Volumes dabei", {"unterbau-vol-prolo_authentik-db.tar.gz.age",
                                  "tool-zwei-vol-zwei_dbdaten.tar.gz.age",
                                  "tool-notizen-vol-notizen_daten.tar.gz.age"} <= teile, str(teile))
    stimmt("nur root kann die Sicherung lesen", all(
        os.stat(os.path.join(ENV["PROLO_BACKUP"], stand, d)).st_mode & 0o077 == 0 for d in teile))
    # Die Pruefung muss eine beschaedigte Sicherung erkennen.
    kaputt = os.path.join(ENV["PROLO_BACKUP"], "2000-01-01_000000")
    shutil.copytree(os.path.join(ENV["PROLO_BACKUP"], stand), kaputt)
    with open(os.path.join(kaputt, "MANIFEST.json")) as f:
        km = json.load(f)
    km["stand"] = "2000-01-01_000000"
    with open(os.path.join(kaputt, "MANIFEST.json"), "w") as f:
        json.dump(km, f)
    with open(os.path.join(kaputt, "tool-notizen.tar.gz.age"), "r+b") as f:
        f.seek(200)
        b = f.read(1)
        f.seek(200)
        f.write(bytes([b[0] ^ 0xFF]))
    r = prolo("backup", "pruefen", "2000-01-01_000000", pruefen=False)
    stimmt("beschaedigte Sicherung wird erkannt", r.returncode != 0 and "Prüfsumme" in r.stdout)
    shutil.rmtree(kaputt)

    schritt("Zurueckholen: ein Tool")
    sh("docker", "exec", "notizen-notizen-1", "sh", "-c", "echo WEG > /daten/notiz.txt")
    with open(ENV["PROLO_TOOLS"] + "/notizen/prolo.conf", "a") as f:
        f.write("kaputt\n")
    prolo("restore", stand, "--tool", "notizen", "--ja")
    stimmt("Daten von notizen sind zurueck", sh("docker", "exec", "notizen-notizen-1", "cat",
                                                "/daten/notiz.txt").stdout.strip() == "wichtig")

    schritt("Entfernen und zurueckholen")
    prolo("tool", "rm", "zwei", "--ja")
    weg = (not os.path.exists(ENV["PROLO_TOOLS"] + "/zwei")
           and "zwei_dbdaten" not in sh("docker", "volume", "ls", "-q").stdout
           and sh("docker", "network", "inspect", "tool-zwei", pruefen=False).returncode != 0)
    stimmt("zwei ist weg: Ordner, Volumes, Netz", weg)
    prolo("restore", "--tool", "zwei", "--ja")
    stimmt("zwei ist mit seiner Datenbank zurueck", sh(
        "docker", "exec", "zwei-db-1", "psql", "-U", "postgres", "-tAc",
        "select x from merkmal").stdout.strip() == "ueberlebt")

    schritt("Zurueckholen: der Unterbau")
    authentik("from authentik.core.models import Group; Group.objects.get_or_create(name='nachher')")
    prolo("restore", stand, "--unterbau", "--ja")
    gruppen = authentik("from authentik.core.models import Group; "
                        "print('GRUPPEN', sorted(g.name for g in Group.objects.all()))")
    stimmt("Authentik ist auf dem gesicherten Stand", "'vorher'" in gruppen and "'nachher'" not in gruppen,
           gruppen[-300:])

    schritt("Admin-Seite und Agent")
    agent = subprocess.Popen([PROLO, "agent"], env=ENV, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    try:
        anfrage = ("import urllib.request\n"
                   "r = urllib.request.Request('http://127.0.0.1:8080/auftrag', data=b'art=tool_restart&name=notizen',"
                   " headers={'X-Authentik-Username': 'akadmin', 'X-Authentik-Groups': 'authentik Admins',"
                   " 'Host': 'admin.prolo.test', 'Origin': 'https://admin.prolo.test'})\n"
                   "class K(urllib.request.HTTPRedirectHandler):\n"
                   "    def redirect_request(self, *a, **k): return None\n"
                   "try: urllib.request.build_opener(K).open(r)\n"
                   "except urllib.error.HTTPError as e: print(e.headers.get('Location'))\n")
        ziel = sh("docker", "exec", "-i", "prolo-admin-1", "python3", "-", eingabe=anfrage).stdout.strip()
        kennung = ziel.rsplit("/", 1)[-1]
        stimmt("Admin-Seite legt den Auftrag ab", ziel.startswith("/auftrag/"), ziel)
        lage = {}
        for _ in range(60):
            try:
                with open(os.path.join(ENV["PROLO_VAR"], "agent", "aus", kennung + ".json")) as f:
                    lage = json.load(f)
            except (OSError, ValueError):
                pass
            if lage.get("status") in ("ok", "fehler", "abgelehnt"):
                break
            time.sleep(2)
        stimmt("der Agent fuehrt ihn aus", lage.get("status") == "ok", str(lage))
        stimmt("der Agent schreibt den Status", os.path.isfile(
            os.path.join(ENV["PROLO_VAR"], "agent", "aus", "status.json")))
    finally:
        agent.terminate()
        agent.wait(30)

    schritt("Port aus dem Abbild (N-130)")
    sh("docker", "image", "rm", "traefik/whoami:v1.10", pruefen=False)
    with open(TMP + "/drei.yml", "w") as f:
        f.write(DREI)
    prolo("tool", "add", "drei", "--compose", TMP + "/drei.yml")
    with open(ENV["PROLO_TOOLS"] + "/drei/prolo.conf") as f:
        stimmt("Port aus einem Abbild, das erst geholt wird", "PORT=80\n" in f.read())

    schritt("Stand")
    s = json.loads(prolo("status", "--json").stdout)
    stimmt("Unterbau gesund", all(u["zustand"] in ("gesund", "laeuft") for u in s["unterbau"]),
           str(s["unterbau"]))
    stimmt("Tools gesund", sorted((t["name"], t["zustand"]) for t in s["tools"]) ==
           [("drei", "laeuft"), ("notizen", "gesund"), ("zwei", "gesund")], str([(t["name"], t["zustand"]) for t in s["tools"]]))


def aufraeumen():
    schritt("Aufraeumen")
    for p in PROJEKTE:
        sh("docker", "compose", "-p", p, "down", "-v", "--remove-orphans", pruefen=False)
    for n in ("tool-notizen", "tool-zwei", "tool-boese", "tool-drei", "prolo-socket", "prolo-auth",
              "prolo-authentik", "prolo-admin"):
        sh("docker", "network", "rm", n, pruefen=False)
    sh("docker", "image", "rm", "prolotest/web:1", "traefik/whoami:v1.10", pruefen=False)
    shutil.rmtree(TMP, ignore_errors=True)


def main():
    if os.geteuid() != 0:
        print("Braucht root:  sudo python3 tests/durchlauf.py")
        return 2
    if sh("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=prolo").stdout.strip():
        print("Auf dieser Maschine laeuft schon ein Unterbau (Projekt 'prolo') - der Durchlauf "
              "wuerde ihn uebernehmen. Abgebrochen, nichts angefasst.")
        return 2
    t0 = time.time()
    try:
        ablauf()
    except AssertionError as a:
        print("\nFEHLGESCHLAGEN: %s" % a)
        return 1
    finally:
        aufraeumen()
        gut = sum(1 for g, _ in ERGEBNIS if g)
        print("\n%d von %d Pruefungen bestanden (%.0f s)." % (gut, len(ERGEBNIS), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
