"""Einheitstests fuer den Kern: was geprueft, erzeugt und entschieden wird.

Kein Docker noetig. Erwartungswerte von Hand (CLAUDE.md §13) - nie die
Ausgabe des Codes abgeschrieben.

    python3 -m unittest discover -s tests -v
"""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
sys.path.insert(0, REPO)
sys.dont_write_bytecode = True

TMP = tempfile.mkdtemp(prefix="prolo-test-")
for k in ("ETC", "VAR", "TOOLS", "BACKUP"):
    os.environ["PROLO_" + k] = os.path.join(TMP, k.lower())

from kern import agent, auftrag, orte, sicherung, tools  # noqa: E402
from kern.orte import Abbruch  # noqa: E402


def lesen(*pfad):
    with open(os.path.join(REPO, *pfad), encoding="utf-8") as f:
        return f.read()


class AuftragTest(unittest.TestCase):
    def ok(self, art, **felder):
        return auftrag.pruefen({"art": art, "felder": felder})

    def nein(self, art, **felder):
        with self.assertRaises(auftrag.Ungueltig):
            auftrag.pruefen({"art": art, "felder": felder})

    def test_namen(self):
        for gut in ("uptime", "a", "wiki-2", "n8n"):
            self.ok("tool_start", name=gut)
        for schlecht in ("", "Uptime", "-x", "x-", "2fa", "a_b", "a" * 31, "../etc", "a b",
                         "admin", "auth", "traefik", "prolo-x"):
            self.nein("tool_start", name=schlecht)

    def test_unbekanntes_wird_abgelehnt(self):
        self.nein("rm_rf", name="uptime")
        self.nein("tool_start", name="uptime", befehl="reboot")
        with self.assertRaises(auftrag.Ungueltig):
            auftrag.pruefen(["tool_start"])
        with self.assertRaises(auftrag.Ungueltig):
            auftrag.pruefen({"art": "tool_start", "felder": {"name": ["uptime"]}})

    def test_tool_add_quellen(self):
        self.ok("tool_add", name="uptime", quelle="abbild", abbild="louislam/uptime-kuma:1")
        self.ok("tool_add", name="uptime", quelle="abbild",
                abbild="ghcr.io/a/b:1.2@sha256:" + "a" * 64)
        self.nein("tool_add", name="uptime", quelle="abbild", abbild="bild; rm -rf /")
        self.ok("tool_add", name="x", quelle="git", git="https://github.com/a/b.git")
        # Nur https - kein ssh, kein file://, keine Optionen fuer git
        for url in ("git@github.com:a/b.git", "file:///etc", "--upload-pack=x", "http://a/b",
                    "https://a/b c"):
            self.nein("tool_add", name="x", quelle="git", git=url)
        self.ok("tool_add", name="x", quelle="compose", compose="services: {}\n")
        self.nein("tool_add", name="x", quelle="compose", compose="  ")
        self.nein("tool_add", name="x", quelle="compose", compose="x" * (256 * 1024 + 1))
        self.nein("tool_add", name="x", quelle="docker", abbild="a:1")

    def test_port_und_anmeldung(self):
        self.ok("tool_set", name="x", port="65535")
        for p in ("0", "65536", "80a", "-1", "08"):
            self.nein("tool_set", name="x", port=p)
        self.ok("tool_set", name="x", anmeldung="keine")
        self.nein("tool_set", name="x", anmeldung="vielleicht")
        self.nein("tool_set", name="x")

    def test_env_zeilen(self):
        self.assertEqual(auftrag.env_zeilen("A=1\n# x\n\nB = zwei=drei \n"),
                         {"A": "1", "B": "zwei=drei"})
        for kaputt in ("ohne", "1A=x", "A B=x", "=x"):
            with self.assertRaises(auftrag.Ungueltig):
                auftrag.env_zeilen(kaputt)

    def test_argumente_sind_eine_liste(self):
        _, f = self.ok("tool_add", name="x", quelle="compose", compose="services: {}\n",
                       anmeldung="keine", port="80")
        a = auftrag.argumente("tool_add", f, {"compose": "/tmp/c.yml"})
        self.assertEqual(a, ["tool", "add", "x", "--ja", "--von-web", "--compose", "/tmp/c.yml",
                             "--port", "80", "--anmeldung", "keine"])
        _, f = self.ok("tool_restore", name="x", stand="2026-10-01_033000")
        self.assertEqual(auftrag.argumente("tool_restore", f),
                         ["restore", "2026-10-01_033000", "--tool", "x", "--ja"])
        self.nein("tool_restore", name="x", stand="latest")


class EinstellungenTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(orte.ETC, exist_ok=True)

    def test_env_hin_und_zurueck(self):
        p = os.path.join(TMP, "x.env")
        orte.env_schreiben(p, {"A": "1", "B": "mit = gleich"}, "# Kopf")
        self.assertEqual(orte.env_lesen(p), {"A": "1", "B": "mit = gleich"})
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
        with open(p, "w") as f:
            f.write("A='eins'\nB=\"zwei\"\n")
        self.assertEqual(orte.env_lesen(p), {"A": "eins", "B": "zwei"})
        with open(p, "w") as f:
            f.write("kaputt\n")
        with self.assertRaises(Abbruch):
            orte.env_lesen(p)
        with self.assertRaises(Abbruch):
            orte.env_schreiben(p, {"A": "zeile\numbruch"})

    def test_konf_prueft(self):
        def mit(**werte):
            orte.env_schreiben(orte.KONF, werte)
            return orte.konf()
        k = mit(PROLO_DOMAIN="prolo.me", PROLO_EMAIL="a@prolo.me")
        self.assertEqual((k["BACKUP_TAGE"], k["AUTO_UPDATE"], k["ADMIN_GRUPPE"]),
                         ("14", "ja", "authentik Admins"))
        for kaputt in ({"PROLO_EMAIL": "a@b.de"},
                       {"PROLO_DOMAIN": "prolo", "PROLO_EMAIL": "a@b.de"},
                       {"PROLO_DOMAIN": "Prolo.ME", "PROLO_EMAIL": "a@b.de"},
                       {"PROLO_DOMAIN": "prolo.me", "PROLO_EMAIL": "a@b.de", "BACKUP_TAGE": "0"},
                       {"PROLO_DOMAIN": "prolo.me", "PROLO_EMAIL": "a@b.de", "AUTO_UPDATE": "1"}):
            with self.assertRaises(Abbruch):
                mit(**kaputt)

    def test_zufall(self):
        a, b = orte.zufall(), orte.zufall()
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^[A-Za-z0-9]{40}$")


class ComposeTest(unittest.TestCase):
    def test_variablen(self):
        v = tools.variablen("a: ${PFLICHT}\nb: ${MIT:-x}\nc: ${STRENG:?fehlt}\nd: $KURZ\n"
                            "e: ${MIT2-y}\nf: ${PFLICHT}")
        self.assertEqual(v, {"PFLICHT": False, "MIT": True, "STRENG": False, "KURZ": False,
                             "MIT2": True})

    def test_vorschlaege(self):
        self.assertEqual(len(tools.vorschlag_wert("DB_PASSWORD", "h")), 40)
        self.assertEqual(tools.vorschlag_wert("TZ", "h"), "Europe/Berlin")
        self.assertEqual(tools.vorschlag_wert("WEBHOOK_URL", "x.prolo.me"), "https://x.prolo.me")
        self.assertEqual(tools.vorschlag_wert("N8N_HOST", "x.prolo.me"), "x.prolo.me")
        self.assertIsNone(tools.vorschlag_wert("LIZENZ", "h"))

    def test_env_fuellen_raet_nicht(self):
        app = tempfile.mkdtemp(dir=TMP)
        with open(os.path.join(app, "docker-compose.yml"), "w") as f:
            f.write("services:\n  a:\n    image: x:${VERSION:-1}\n    environment:\n"
                    "      P: ${DB_PASS}\n      L: ${LIZENZ}\n")
        with self.assertRaises(Abbruch) as a:
            tools.env_fuellen(app, "a.prolo.me", {})
        self.assertIn("LIZENZ", str(a.exception))
        self.assertFalse(os.path.exists(os.path.join(app, ".env")))
        tools.env_fuellen(app, "a.prolo.me", {"LIZENZ": "abc"})
        env = orte.env_lesen(os.path.join(app, ".env"))
        self.assertEqual(env["LIZENZ"], "abc")
        self.assertRegex(env["DB_PASS"], r"^[A-Za-z0-9]{40}$")
        self.assertNotIn("VERSION", env)
        # Ein zweiter Lauf aendert nichts Vorhandenes
        alt = env["DB_PASS"]
        tools.env_fuellen(app, "a.prolo.me", {})
        self.assertEqual(orte.env_lesen(os.path.join(app, ".env"))["DB_PASS"], alt)

    def test_gefahren(self):
        app = "/opt/tools/x/app"
        cfg = {"services": {
            "harmlos": {"image": "a:1", "volumes": [{"type": "bind", "source": app + "/daten",
                                                     "target": "/d"}]},
            "boese": {"image": "a:1", "privileged": True, "network_mode": "host",
                      "cap_add": ["SYS_ADMIN"], "pid": "host",
                      "volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/s"},
                                  {"type": "bind", "source": "/etc", "target": "/e"},
                                  {"type": "bind", "source": app, "target": "/a"}]}},
               "volumes": {"fremd": {"external": True}}}
        gef, hin, aussen = tools.gefahren(cfg, app)
        text = "\n".join(gef)
        for erwartet in ("privileged", "network_mode: host", "SYS_ADMIN", "pid: host",
                         "Docker-Socket", "/etc vom Server", "ganzen Ordner", "fremdes Volume"):
            self.assertIn(erwartet, text)
        self.assertFalse([g for g in gef if g.startswith("harmlos")])
        self.assertEqual(aussen, ["/etc"])
        self.assertEqual(len(gef), 8)

    def test_dienst_waehlen(self):
        einer = {"services": {"web": {"image": "a:1", "expose": ["3001"]}}}
        self.assertEqual(tools.dienst_waehlen(einer, "x", None, None), ("web", "3001"))
        mit_db = {"services": {"app": {"image": "a:1", "ports": [{"target": 8080}]},
                               "db": {"image": "postgres:16", "ports": [{"target": 5432}]}}}
        self.assertEqual(tools.dienst_waehlen(mit_db, "x", None, None), ("app", "8080"))
        gleichnamig = {"services": {"x": {"image": "a:1", "expose": ["80"]},
                                    "y": {"image": "b:1", "expose": ["81"]}}}
        self.assertEqual(tools.dienst_waehlen(gleichnamig, "x", None, None), ("x", "80"))
        zwei = {"services": {"a": {"image": "a:1", "expose": ["80"]},
                             "b": {"image": "b:1", "expose": ["81"]}}}
        with self.assertRaises(Abbruch):
            tools.dienst_waehlen(zwei, "x", None, None)
        self.assertEqual(tools.dienst_waehlen(zwei, "x", "b", "9000"), ("b", "9000"))
        with self.assertRaises(Abbruch):
            tools.dienst_waehlen(zwei, "x", "c", "80")
        with self.assertRaises(Abbruch):
            tools.dienst_waehlen({"services": {"a": {"image": "a:1", "expose": ["1", "2"]}}},
                                 "x", None, None)


class OverrideTest(unittest.TestCase):
    """prolo.override.yml - hier entscheidet sich, ob ein Tool hinter der
    Anmeldung steht und seine Datenbank noch erreicht."""

    def setUp(self):
        tools.abbild_info = lambda abbild: (set(), {"/vol"} if abbild == "mit-volume:1" else set())
        self.cfg = {"services": {
            "app": {"image": "a:1", "ports": [{"target": 80, "published": "8080"}],
                    "networks": {"default": None}, "labels": {"com.x": "1"}},
            "db": {"image": "mit-volume:1", "restart": "always", "logging": {"driver": "local"},
                   "networks": {"default": None, "intern": None}}}}
        self.c = {"DIENST": "app", "PORT": "80", "ANMELDUNG": "authentik", "HOST": "x.prolo.me"}

    def zeilen(self, text):
        return [z.rstrip() for z in text.splitlines()]

    def test_anmeldung_und_netze(self):
        t = tools.override_text("x", self.cfg, self.c)
        z = self.zeilen(t)
        self.assertIn('      "traefik.http.routers.tool-x.middlewares": "authentik@file"', z)
        self.assertIn('      "traefik.http.routers.tool-x.rule": "Host(`x.prolo.me`)"', z)
        self.assertIn('      "traefik.docker.network": "tool-x"', z)
        self.assertIn('      "traefik.http.services.tool-x.loadbalancer.server.port": "80"', z)
        # Der Hauptdienst bleibt in default (dort ist die Datenbank) UND kommt in prolo.
        app = t.split('  "app":')[1].split('  "db":')[0]
        self.assertIn('      "default": {}', app)
        self.assertIn("      prolo: {}", app)
        # Offene Ports des Herstellers sind weg - beim Dienst, der welche hatte.
        self.assertIn("    ports: !reset []", app)
        self.assertIn('    name: "tool-x"', t)
        self.assertIn("    external: true", t)

    def test_ohne_anmeldung(self):
        t = tools.override_text("x", self.cfg, dict(self.c, ANMELDUNG="keine"))
        self.assertNotIn("authentik@file", t)
        self.assertNotIn("middlewares", t)

    def test_vorhandenes_bleibt(self):
        t = tools.override_text("x", self.cfg, self.c)
        db = t.split('  "db":')[1].split("networks:\n  prolo")[0]
        self.assertNotIn("restart", db)          # hatte schon eins
        self.assertNotIn("logging", db)          # hatte schon eins
        self.assertNotIn("ports", db)            # hatte keine
        # Das VOLUME des Abbilds bekommt einen Namen - sonst findet es keine
        # Wiederherstellung wieder.
        self.assertIn('      - "db-vol:/vol"', db)
        self.assertIn('  "db-vol": {}', t)
        app = t.split('  "app":')[1].split('  "db":')[0]
        self.assertIn("    restart: unless-stopped", app)
        self.assertIn('      "com.x": "1"', app)

    def test_fremde_traefik_labels_werden_ersetzt(self):
        self.cfg["services"]["app"]["labels"] = {"traefik.http.routers.alt.rule": "Host(`a`)",
                                                 "com.x": "1"}
        t = tools.override_text("x", self.cfg, self.c)
        self.assertIn("    labels: !override", t)
        self.assertNotIn("routers.alt", t)
        self.assertIn('"com.x": "1"', t)

    def test_abbild_compose(self):
        tools.abbild_info = lambda abbild: ({"3001"}, {"/app/data"})
        t = tools.abbild_compose("uptime", "louislam/uptime-kuma:1", None)
        self.assertIn('    image: "louislam/uptime-kuma:1"', t)
        self.assertIn('    expose: ["3001"]', t)
        self.assertIn('      - "daten:/app/data"', t)
        self.assertIn("  daten: {}", t)


class AufraeumenTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(orte.BACKUP, exist_ok=True)
        for n in os.listdir(orte.BACKUP):
            import shutil
            shutil.rmtree(os.path.join(orte.BACKUP, n))
        orte.env_schreiben(orte.KONF, {"PROLO_DOMAIN": "prolo.me", "PROLO_EMAIL": "a@prolo.me",
                                       "BACKUP_TAGE": "14"})

    def stand(self, name, fehler=False, manifest=True):
        p = os.path.join(orte.BACKUP, name)
        os.makedirs(p)
        if manifest:
            with open(os.path.join(p, "MANIFEST.json"), "w") as f:
                json.dump({"stand": name[:17], "fehler": ["x"] if fehler else []}, f)

    def test_behaelt_drei_vollstaendige_und_die_juengeren(self):
        heute = datetime.datetime(2026, 10, 20, 12, 0)
        self.stand("2026-10-19_033000")                       # jung
        self.stand("2026-10-01_033000")                       # alt, aber 2. vollstaendige
        self.stand("2026-09-30_033000-unvollstaendig", fehler=True)   # alt, kaputt -> weg
        self.stand("2026-09-20_033000")                       # alt, 3. vollstaendige -> bleibt
        self.stand("2026-09-10_033000")                       # alt, 4. -> weg
        self.stand("2026-10-18_120000-unvollstaendig", fehler=True)   # jung -> bleibt
        self.stand("2026-09-01_033000", manifest=False)       # alt, unbrauchbar -> weg
        sicherung.aufraeumen(heute)
        self.assertEqual(sorted(os.listdir(orte.BACKUP)),
                         ["2026-09-20_033000", "2026-10-01_033000",
                          "2026-10-18_120000-unvollstaendig", "2026-10-19_033000"])

    def test_nie_die_letzten_drei(self):
        heute = datetime.datetime(2027, 6, 1)
        for n in ("2026-01-01_000000", "2026-01-02_000000", "2026-01-03_000000",
                  "2026-01-04_000000"):
            self.stand(n)
        sicherung.aufraeumen(heute)
        self.assertEqual(sorted(os.listdir(orte.BACKUP)),
                         ["2026-01-02_000000", "2026-01-03_000000", "2026-01-04_000000"])


class AgentTest(unittest.TestCase):
    def setUp(self):
        for p in (orte.EINGANG, orte.AUSGANG):
            os.makedirs(p, exist_ok=True)

    def test_lesen_folgt_keinem_verweis(self):
        ziel = os.path.join(TMP, "geheim.json")
        with open(ziel, "w") as f:
            f.write('{"art": "sichern"}')
        verweis = os.path.join(orte.EINGANG, "20261001-120000-abcdef01.json")
        os.symlink(ziel, verweis)
        with self.assertRaises(OSError):
            agent.lesen(verweis)
        os.remove(verweis)

    def test_zu_gross(self):
        p = os.path.join(orte.EINGANG, "20261001-120000-abcdef02.json")
        with open(p, "w") as f:
            f.write(" " * (auftrag.MAX_AUFTRAG + 1))
        with self.assertRaises(auftrag.Ungueltig):
            agent.lesen(p)
        os.remove(p)

    def test_unzulaessiges_wird_abgelehnt_und_nicht_ausgefuehrt(self):
        gerufen = []
        alt = agent.subprocess.Popen
        agent.subprocess.Popen = lambda *a, **k: gerufen.append(a) or alt(["true"])
        try:
            k = "20261001-120000-abcdef03"
            with open(os.path.join(orte.EINGANG, k + ".json"), "w") as f:
                json.dump({"art": "tool_add", "felder": {"name": "x", "quelle": "git",
                                                         "git": "file:///etc"}}, f)
            n = agent.naechster()
            self.assertEqual(n[0], k)
            self.assertFalse(os.path.exists(os.path.join(orte.EINGANG, k + ".json")))
            agent.ausfuehren(*n)
            with open(os.path.join(orte.AUSGANG, k + ".json")) as f:
                lage = json.load(f)
            self.assertEqual(lage["status"], "abgelehnt")
            self.assertEqual(gerufen, [])
        finally:
            agent.subprocess.Popen = alt

    def test_fremde_dateinamen_werden_weggeraeumt(self):
        p = os.path.join(orte.EINGANG, "../../x.json".replace("/", "_"))
        with open(p, "w") as f:
            f.write("{}")
        self.assertIsNone(agent.naechster())
        self.assertFalse(os.path.exists(p))


class UnterbauDateienTest(unittest.TestCase):
    """Die Dateien des Unterbaus: was hier steht, ist die Sicherheit."""

    def test_vertrauensgrenze_deckt_alle_kopfzeilen(self):
        t = lesen("traefik", "dynamic", "prolo.yml")
        antwort = re.search(r"authResponseHeaders:\n((?:\s+- .*\n)+)", t).group(1)
        gesetzt = {z.strip()[2:].lower() for z in antwort.splitlines()}
        grenze = t.split("vertrauensgrenze:")[1].split("sicherheitskopf:")[0]
        geloescht = {m.lower() for m in re.findall(r"(X-authentik-[a-z-]+): \"\"", grenze, re.I)}
        self.assertEqual(len(gesetzt), 12)
        self.assertEqual(gesetzt - geloescht, set())

    def test_eingang_haengt_alle_schutzschichten_an(self):
        c = lesen("docker-compose.yml")
        self.assertIn("--entrypoints.websecure.http.middlewares=ratenbremse@file,gleichzeitig@file,"
                      "vertrauensgrenze@file,sicherheitskopf@file", c)
        self.assertIn("traefik.http.routers.prolo-admin.middlewares=authentik@file", c)
        self.assertIn("--providers.docker.exposedbydefault=false", c)

    def test_jeder_dienst_hat_grenzen(self):
        c = lesen("docker-compose.yml")
        dienste = re.split(r"\n  (?=[a-z-]+:\n)", c.split("\nservices:\n")[1].split("\nvolumes:\n")[0])
        self.assertEqual(len(dienste), 6)
        for d in dienste:
            name = d.split(":")[0].strip()
            for pflicht in ("mem_limit:", "pids_limit:", "no-new-privileges:true", "cap_drop: [ ALL ]",
                            "restart: unless-stopped"):
                self.assertIn(pflicht, d, "%s: %s fehlt" % (name, pflicht))
            self.assertNotRegex(d, r"image: [^\n]*:latest")
            if name != "traefik":
                self.assertNotIn("ports:", d, name)

    def test_blueprint_schuetzt_die_domain(self):
        b = lesen("authentik", "blueprints", "prolowelt.yaml")
        self.assertIn("mode: forward_domain", b)
        self.assertIn("cookie_domain: !Env PROLO_DOMAIN", b)
        self.assertIn("managed: goauthentik.io/outposts/embedded", b)

    def test_admin_uid_stimmt_ueberein(self):
        self.assertIn("useradd -r -u %d " % orte.ADMIN_UID, lesen("admin", "Dockerfile"))


if __name__ == "__main__":
    unittest.main()
