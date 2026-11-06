"""Einheitstests fuer den Kern: was geprueft, erzeugt und entschieden wird.

Kein Docker-Dienst noetig - nur fuer KaefigModellTest das Programm docker
compose (config laeuft ohne Dienst). Erwartungswerte von Hand (CLAUDE.md §13) - nie die
Ausgabe des Codes abgeschrieben.

    python3 -m unittest discover -s tests -v
"""
import datetime
import json
import os
import re
import shutil
import subprocess
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

from kern import agent, auftrag, kaefig, orte, sicherung, tools, zugang  # noqa: E402
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

    def test_tool_edit(self):
        _, f = self.ok("tool_edit", name="x", compose="services:\n  a:\n    image: b:1\n")
        self.assertEqual(auftrag.argumente("tool_edit", f, {"compose": "/tmp/c.yml"}),
                         ["tool", "edit", "x", "--ja", "--von-web", "--compose", "/tmp/c.yml"])
        _, f = self.ok("tool_edit", name="x", env="ADMIN_TOKEN='$argon2id$v=19$x'")
        self.assertEqual(auftrag.argumente("tool_edit", f, {"env": "/tmp/v.env"}),
                         ["tool", "edit", "x", "--ja", "--von-web", "--env-datei", "/tmp/v.env"])
        self.nein("tool_edit", name="x")
        self.nein("tool_edit", name="x", compose=" \n ")      # leer ist nichts zu aendern
        self.nein("tool_edit", name="x", compose="x" * (256 * 1024 + 1))
        self.nein("tool_edit", name="x", env="kein gleich")
        self.nein("tool_edit", name="x", env="A=1\n" * 3000)
        self.nein("tool_edit", name="x", env="A=1", port="80")   # nur Datei und Variablen


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
        gef, hin, aussen = tools.gefahren(cfg, app, "x")
        text = "\n".join(gef)
        for erwartet in ("privileged", "network_mode: host", "SYS_ADMIN", "pid: host",
                         "Docker-Socket", "/etc vom Server", "ganzen Ordner", "fremdes Volume"):
            self.assertIn(erwartet, text)
        self.assertFalse([g for g in gef if g.startswith("harmlos")])
        self.assertEqual(aussen, ["/etc"])
        self.assertEqual(len(gef), 8)

    def test_erlaubnisliste(self):
        """N-135: je ein Weg, an dem die Sperrliste vorbeiliess - jeder einzeln."""
        app = "/opt/tools/x/app"

        def gef(dienst=None, **oben):
            cfg = {"services": {"app": dict({"image": "a:1"}, **(dienst or {}))}}
            cfg.update(oben)
            return "\n".join(tools.gefahren(cfg, app, "x")[0])

        self.assertEqual(gef(), "")
        faelle = [
            ({}, {"volumes": {"w": {"name": "x_w", "driver": "local", "driver_opts": {
                "type": "none", "o": "bind", "device": "/"}}}}, "driver_opts"),
            ({}, {"volumes": {"w": {"name": "prolo_authentik-db"}}}, "prolo_authentik-db"),
            ({}, {"volumes": {"w": {"name": "vault_daten"}}}, "vault_daten"),
            ({}, {"networks": {"n": {"name": "prolo-authentik"}}}, "prolo-authentik"),
            ({}, {"networks": {"n": {"name": "x_n", "ipam": {"config": [{}]}}}}, "ipam"),
            ({}, {"secrets": {"s": {"file": "/etc/prolo/backup.key"}}}, "backup.key"),
            ({}, {"secrets": {"s": {"environment": "HOME"}}}, "environment"),
            ({}, {"configs": {"c": {"file": "/etc/prolo/geheim.env"}}}, "geheim.env"),
            ({}, {"include": []}, "'include'"),
            ({"volumes_from": ["container:prolo-authentik-db-1"]}, {}, "fremden Containers"),
            ({"pid": "container:prolo-authentik-server-1"}, {}, "pid:"),
            ({"ipc": "container:x"}, {}, "ipc:"),
            ({"post_start": [{"command": ["id"], "privileged": True}]}, {}, "'post_start'"),
            ({"provider": {"type": "x"}}, {}, "'provider'"),
            ({"use_api_socket": True}, {}, "'use_api_socket'"),
            ({"gpus": "all"}, {}, "'gpus'"),
            ({"security_opt": ["seccomp=unconfined"]}, {}, "seccomp=unconfined"),
            ({"security_opt": ["apparmor=unconfined"]}, {}, "apparmor=unconfined"),
            ({"logging": {"driver": "syslog"}}, {}, "syslog"),
            ({"oom_score_adj": -900}, {}, "oom_score_adj"),
            ({"deploy": {"resources": {"reservations": {"devices": [{}]}}}}, {}, "Geräte"),
            ({"labels": {"com.docker.compose.project": "vault"}}, {}, "com.docker.compose.project"),
            ({"container_name": "prolo-authentik-server-1"}, {}, "Containernamen"),
            ({"networks": {"default": {"aliases": ["prolo-tool-vault"]}}},
             {"networks": {"default": {"name": "x_default"}}}, "Netz-Aliasse"),
            ({"networks": {"default": {"ipv4_address": "172.18.0.2"}}},
             {"networks": {"default": {"name": "x_default"}}}, "ipv4_address"),
            ({"volumes": [{"type": "bind", "source": app + "/d", "target": "/d",
                           "bind": {"propagation": "rshared"}}]}, {}, "rshared"),
            ({"volumes": [{"type": "volume", "source": "nirgends", "target": "/d"}]}, {},
             "nicht anlegt"),
            ({"build": {"context": "/etc"}}, {}, "build.context"),
            ({"build": {"context": app, "dockerfile": "../../../../etc/shadow"}}, {}, "Dockerfile"),
            ({"build": {"context": app, "ssh": ["default"]}}, {}, "ssh"),
            ({"build": {"context": app, "network": "host"}}, {}, "build.network"),
            ({"build": {"context": app, "additional_contexts": {"x": "/root"}}}, {},
             "additional_contexts"),
            ({"build": {"context": app, "cache_from": ["type=local,src=/root"]}}, {}, "cache_from"),
        ]
        for dienst, oben, erwartet in faelle:
            with self.subTest(erwartet=erwartet):
                self.assertIn(erwartet, gef(dienst, **oben))

    def test_erlaubnisliste_laesst_uebliches_durch(self):
        """Was Hersteller-Dateien gewoehnlich haben, ist keine Gefahr."""
        app = "/opt/tools/x/app"
        cfg = {"name": "x", "services": {
            "app": {"image": "a:1", "command": None, "entrypoint": None, "restart": "always",
                    "environment": {"A": "1"}, "depends_on": {"db": {"condition": "service_started"}},
                    "volumes": [{"type": "volume", "source": "daten", "target": "/d", "volume": {}},
                                {"type": "bind", "source": app + "/export", "target": "/e"},
                                {"type": "tmpfs", "target": "/t"}],
                    "networks": {"default": None}, "healthcheck": {"test": ["CMD", "true"]},
                    "security_opt": ["no-new-privileges:true"], "cap_drop": ["ALL"],
                    "logging": {"driver": "json-file"}, "read_only": True, "shm_size": "128mb",
                    "deploy": {"resources": {"limits": {"memory": "1"}}}, "ports": [{"target": 80}],
                    "labels": {"traefik.enable": "true"}, "x-eigen": 1,
                    "build": {"context": app, "dockerfile": "Dockerfile", "args": {"A": "1"}}},
            "db": {"image": "postgres:16", "volumes_from": ["app:ro"]}},
            "volumes": {"daten": {"name": "x_daten"}},
            "networks": {"default": {"name": "x_default"}},
            "secrets": {"s": {"file": app + "/geheim.txt"}}}
        gef, hin, _ = tools.gefahren(cfg, app, "x")
        self.assertEqual(gef, [])
        self.assertTrue(any("Traefik" in h for h in hin))

    def test_ordner_eines_tools_ist_fremd(self):
        """N-136: was ein Container einhaengt, kann er veraendern - und ein
        Git-Repository bringt Verweise mit."""
        tmp = tempfile.mkdtemp()
        app = os.path.join(tmp, "app")
        for d in ("daten/innen", "export", ".git/hooks", "conf"):
            os.makedirs(os.path.join(app, d))
        os.symlink("/etc/prolo/geheim.env", os.path.join(app, ".env"))
        os.symlink("conf", os.path.join(app, "nach-innen"))
        os.symlink(tmp, os.path.join(app, "export", "weg"))       # im Einhaengeordner: egal

        def bind(q):
            return {"type": "bind", "source": os.path.join(app, q), "target": "/x"}

        cfg = {"services": {"app": {"image": "a:1", "volumes": [
            bind("daten"), bind("daten/innen"), bind(".git"), bind("export"), bind("nach-innen")],
            "env_file": [{"path": os.path.join(app, "daten", "app.env")}]}}}
        gef = "\n".join(tools.gefahren(cfg, app, "x")[0])
        self.assertIn(".env zeigt nach /etc/prolo/geheim.env", gef)
        self.assertIn("Git-Hooks", gef)
        self.assertIn("darin wird daten/innen eingehängt", gef)
        self.assertIn("darin liegt daten/app.env", gef)
        self.assertIn("über einen Verweis ein (nach-innen)", gef)
        self.assertNotIn("weg zeigt", gef)          # gehoert dem Container
        self.assertNotIn("nach-innen zeigt", gef)   # zeigt nach innen

    def test_schreiben_folgt_keinem_verweis(self):
        """N-136: ein mitgebrachter Verweis .env.neu -> Datei ausserhalb."""
        tmp = tempfile.mkdtemp()
        opfer = os.path.join(tmp, "authorized_keys")
        with open(opfer, "w") as f:
            f.write("unberuehrt\n")
        app = os.path.join(tmp, "app")
        os.makedirs(app)
        os.symlink(opfer, os.path.join(app, ".env.neu"))
        orte.datei_schreiben(os.path.join(app, ".env"), "A=1\n", 0o600)
        with open(opfer) as f:
            self.assertEqual(f.read(), "unberuehrt\n")
        with open(os.path.join(app, ".env")) as f:
            self.assertEqual(f.read(), "A=1\n")
        self.assertFalse(os.path.islink(os.path.join(app, ".env")))

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


@unittest.skipUnless(shutil.which("docker"), "docker compose fehlt")
class KaefigModellTest(unittest.TestCase):
    """N-137: das Modell entsteht ohne Rechte auf einer Kopie."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = os.path.join(self.tmp, "x", "app")
        os.makedirs(self.app)

    def schreiben(self, name, text, ordner=None):
        p = os.path.join(ordner or self.app, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_include_einer_fremden_datei(self):
        fremd = self.schreiben("compose.yml", "services:\n  vault:\n    image: a:1\n"
                                              "    environment: { T: ${T} }\n",
                               os.path.join(self.tmp, "vault"))
        self.schreiben(".env", "T=geheim\n", os.path.join(self.tmp, "vault"))
        os.chmod(os.path.dirname(fremd), 0)
        self.addCleanup(os.chmod, os.path.dirname(fremd), 0o700)
        self.schreiben("docker-compose.yml", "include: [ %s ]\nservices:\n  app: { image: a:1 }\n"
                       % fremd)
        with self.assertRaises(Abbruch) as a:
            kaefig.modell(self.app, "x", "docker-compose.yml")
        self.assertIn("außerhalb des Tools", str(a.exception))
        self.assertNotIn(self.tmp, str(a.exception).replace(fremd, ""))

    def test_include_im_tool_geht_und_pfade_zeigen_nach_app(self):
        self.schreiben("db/compose.yml", "services:\n  db: { image: postgres:16 }\n")
        self.schreiben("docker-compose.yml", "include: [ ./db/compose.yml ]\nservices:\n  app:\n"
                       "    image: a:1\n    env_file: [ /etc/hostname ]\n"
                       "    volumes: [ ./daten:/d ]\n")
        cfg = kaefig.modell(self.app, "x", "docker-compose.yml")
        self.assertEqual(sorted(cfg["services"]), ["app", "db"])
        self.assertEqual(cfg["services"]["app"]["volumes"][0]["source"],
                         os.path.join(self.app, "daten"))
        gef = "\n".join(tools.gefahren(cfg, self.app, "x")[0])
        self.assertIn("/etc/hostname (env_file)", gef)
        self.assertNotIn("daten", gef)

    def test_aenderung_wird_auf_der_kopie_geprueft(self):
        self.schreiben("docker-compose.yml", "services:\n  app: { image: a:1 }\n")
        self.schreiben(".env", "A=alt\n")
        cfg = kaefig.modell(self.app, "x", "docker-compose.yml",
                            compose_text="services:\n  app:\n    image: a:${A}\n",
                            env_text="A=neu\n")
        self.assertEqual(cfg["services"]["app"]["image"], "a:neu")
        with open(os.path.join(self.app, ".env")) as f:
            self.assertEqual(f.read(), "A=alt\n")          # das Original bleibt

    def test_umgebung_von_root_kommt_nicht_hinein(self):
        self.schreiben("docker-compose.yml", "services:\n  app:\n    image: a:1\n"
                       "    environment: { W: \"${PROLO_TEST_GEHEIM:-leer}\" }\n")
        os.environ["PROLO_TEST_GEHEIM"] = "von-root"
        self.addCleanup(os.environ.pop, "PROLO_TEST_GEHEIM")
        cfg = kaefig.modell(self.app, "x", "docker-compose.yml")
        self.assertEqual(cfg["services"]["app"]["environment"]["W"], "leer")
        self.assertNotIn("PROLO_TEST_GEHEIM", __import__("kern").docker.tool_env())


@unittest.skipUnless(shutil.which("docker"), "docker compose fehlt")
class NachpruefenTest(unittest.TestCase):
    """N-138: jeder Weg zum Start prueft die Dateien, wie sie jetzt liegen."""

    def setUp(self):
        self.ordner = os.path.join(orte.TOOLS, "nach")
        os.makedirs(os.path.join(self.ordner, "app"), exist_ok=True)
        self.datei("services:\n  app: { image: a:1, expose: [\"80\"] }\n")
        orte.env_schreiben(os.path.join(self.ordner, "prolo.conf"), {
            "QUELLE": "compose", "DIENST": "app", "PORT": "80", "HOST": "nach.prolo.test",
            "ANMELDUNG": "authentik"})
        self.gestartet = []
        echt = (tools.docker.tool, tools.override_neu, orte.root_noetig, sicherung.sichern,
                tools.warten)
        tools.docker.tool = lambda *a, **k: self.gestartet.append(a) or (0, "")
        tools.override_neu = lambda *a, **k: None
        tools.warten = lambda *a, **k: "laeuft"
        orte.root_noetig = lambda *a: None
        os.environ["PROLO_AGENT"] = "1"

        def zurueck():
            (tools.docker.tool, tools.override_neu, orte.root_noetig, sicherung.sichern,
             tools.warten) = echt
            os.environ.pop("PROLO_AGENT", None)
            shutil.rmtree(self.ordner, ignore_errors=True)
        self.addCleanup(zurueck)

    def datei(self, text):
        with open(os.path.join(self.ordner, "app", "docker-compose.yml"), "w") as f:
            f.write(text)

    def test_von_der_seite_startet_nichts_gefaehrliches(self):
        self.datei("services:\n  app: { image: a:1, privileged: true }\n")
        for wie in (lambda: tools.starten("nach"), lambda: tools.neustarten("nach"),
                    lambda: tools.aendern("nach", port="81"),
                    lambda: tools.aktualisieren("nach", sichern=False)):
            with self.assertRaises(Abbruch) as a:
                wie()
            self.assertIn("Admin-Seite", str(a.exception))
        self.assertEqual(self.gestartet, [])

    def test_bestaetigtes_fragt_nicht_noch_einmal_neues_schon(self):
        self.datei("services:\n  app: { image: a:1, privileged: true }\n")
        os.environ.pop("PROLO_AGENT")
        tools.kaefig_pruefen("nach", "starten", ja=True)          # Mensch, Kommandozeile
        os.environ["PROLO_AGENT"] = "1"
        tools.kaefig_pruefen("nach", "starten")                   # jetzt auch von der Seite
        self.datei("services:\n  app: { image: a:1, privileged: true, pid: host }\n")
        with self.assertRaises(Abbruch):
            tools.kaefig_pruefen("nach", "starten")

    def test_harmloses_startet(self):
        tools.starten("nach")
        self.assertTrue(self.gestartet)


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

    def test_env_setzen(self):
        alt = "# Kopf\nA=1\nB=2\n# B=kommentar\nB=doppelt\n"
        self.assertEqual(tools.env_setzen(alt, {"B": "neu", "C": "'$x$y'"}),
                         "# Kopf\nA=1\nB=neu\n# B=kommentar\nC='$x$y'\n")
        self.assertEqual(tools.env_setzen("", {"A": "1"}), "A=1\n")

    def test_bearbeiten_einer_git_datei(self):
        ordner = os.path.join(orte.TOOLS, "ausgit")
        os.makedirs(os.path.join(ordner, "app"), exist_ok=True)
        with open(os.path.join(ordner, "prolo.conf"), "w") as f:
            f.write("QUELLE=git\nGIT=https://example.org/a/b.git\nDIENST=a\nPORT=80\n"
                    "HOST=ausgit.prolo.test\nANMELDUNG=authentik\n")
        with open(os.path.join(ordner, "app", "docker-compose.yml"), "w") as f:
            f.write("services: {}\n")
        c = tools.conf("ausgit")
        # Die Datei gehoert dem Repository: weder zeigen noch ersetzen.
        self.assertIsNone(tools.compose_text("ausgit", c))
        alt_root = orte.root_noetig
        orte.root_noetig = lambda *_: None
        try:
            with self.assertRaises(Abbruch) as a:
                tools.bearbeiten("ausgit", compose="/gibt/es/nicht.yml")
        finally:
            orte.root_noetig = alt_root
        self.assertIn("example.org/a/b.git", str(a.exception))

    def test_compose_text_und_variablen(self):
        ordner = os.path.join(orte.TOOLS, "ausbild")
        os.makedirs(os.path.join(ordner, "app"), exist_ok=True)
        with open(os.path.join(ordner, "app", "docker-compose.yml"), "w") as f:
            f.write(tools.KOPF + "services:\n  a: {image: b:1}\n")
        with open(os.path.join(ordner, "app", ".env"), "w") as f:
            f.write("GEHEIM_PASS=sehr-geheim\nTZ=Europe/Berlin\n")
        self.assertEqual(tools.compose_text("ausbild", {"QUELLE": "image"}),
                         "services:\n  a: {image: b:1}\n")
        self.assertEqual(tools.variablen_namen("ausbild"), ["GEHEIM_PASS", "TZ"])

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


TOKEN = "github_pat_11ABCDEFG0123456789_abcdefXYZ"


class ZugangTest(unittest.TestCase):
    """Git-Zugaenge (N-134): der Token kommt in git an - und nirgends sonst hin."""

    def setUp(self):
        self.root = orte.ist_root
        orte.ist_root = lambda: True
        self.fragen = zugang.ablauf_fragen
        if os.path.exists(zugang.DATEI):
            os.remove(zugang.DATEI)

    def tearDown(self):
        orte.ist_root = self.root
        zugang.ablauf_fragen = self.fragen

    def ok(self, art, **felder):
        return auftrag.pruefen({"art": art, "felder": felder})

    def nein(self, art, **felder):
        with self.assertRaises(auftrag.Ungueltig):
            auftrag.pruefen({"art": art, "felder": felder})

    def test_auftrag_prueft_anbieter_benutzer_token(self):
        self.ok("zugang_setzen", host="github.com", benutzer="prolo2408", token=TOKEN)
        self.ok("zugang_setzen", host="git.example.de", benutzer="a.b-c", token="glpat-12345678")
        for host in ("https://github.com", "github.com/prolo2408", "GitHub.com", "localhost",
                     "github.com\nhost=x", ""):
            self.nein("zugang_setzen", host=host, benutzer="prolo2408", token=TOKEN)
        for benutzer in ("prolo@2408", "a b", "-x", "a\nb", "a=b"):
            self.nein("zugang_setzen", host="github.com", benutzer=benutzer, token=TOKEN)
        for token in ("kurz", "mit leer zeichen1", "a:b1234567", "abc\npassword=x", "x" * 501):
            self.nein("zugang_setzen", host="github.com", benutzer="prolo2408", token=token)
        self.ok("zugang_test", git="https://github.com/prolo2408/galaxy-golf-bot")
        self.nein("zugang_test", git="file:///etc/prolo")

    def test_token_nie_als_argument(self):
        _, f = self.ok("zugang_setzen", host="github.com", benutzer="prolo2408", token=TOKEN)
        a = auftrag.argumente("zugang_setzen", f, {"token": "/tmp/x/token"})
        self.assertEqual(a, ["git-zugang", "setzen", "github.com", "--benutzer", "prolo2408",
                             "--token-datei", "/tmp/x/token"])

    def test_agent_zeigt_token_nirgends(self):
        orte.ist_root = self.root           # der Agent im Test: kein chown
        for p in (orte.EINGANG, orte.AUSGANG):
            os.makedirs(p, exist_ok=True)
        gerufen = []
        alt = agent.subprocess.Popen

        def popen(argv, **k):
            with open(argv[argv.index("--token-datei") + 1]) as f:
                gerufen.append(f.read())
            return alt(["true"], **{x: k[x] for x in ("stdout", "stderr")})
        agent.subprocess.Popen = popen
        try:
            k = "20261105-120000-abcdef09"
            with open(os.path.join(orte.EINGANG, k + ".json"), "w") as f:
                json.dump({"art": "zugang_setzen", "felder": {
                    "host": "github.com", "benutzer": "prolo2408", "token": TOKEN}}, f)
            agent.ausfuehren(*agent.naechster())
        finally:
            agent.subprocess.Popen = alt
        self.assertEqual(gerufen, [TOKEN])                  # prolo bekam ihn als Datei
        for endung in (".json", ".log"):
            with open(os.path.join(orte.AUSGANG, k + endung)) as f:
                self.assertNotIn(TOKEN, f.read())
        self.assertFalse(os.path.exists(os.path.join(orte.AGENT, "tmp-" + k)))
        with open(os.path.join(orte.AUSGANG, k + ".json")) as f:
            self.assertEqual(json.load(f)["felder"], {"host": "github.com", "benutzer": "prolo2408"})

    def test_git_bekommt_den_token_und_loescht_ihn_nicht(self):
        zugang.ablauf_fragen = lambda h, t: (True, "2027-11-05")
        zugang.setzen("github.com", "prolo2408", token=TOKEN)
        self.assertEqual(os.stat(zugang.DATEI).st_mode & 0o777, 0o600)
        env = dict(zugang.git_env(), PROLO_ETC=orte.ETC)
        frage = "protocol=https\nhost=github.com\n\n"
        r = subprocess.run(["git", "credential", "fill"], input=frage, capture_output=True,
                           text=True, env=env, timeout=30)
        self.assertEqual(r.stdout, "protocol=https\nhost=github.com\nusername=prolo2408\n"
                                   "password=%s\n" % TOKEN)
        r = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=gitlab.com\n\n",
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertNotEqual(r.returncode, 0)                 # anderer Anbieter: nichts
        # Eine Absage (401) laesst git "erase" rufen - der Zugang muss bleiben.
        subprocess.run(["git", "credential", "reject"], input=frage + "username=prolo2408\n"
                       "password=%s\n\n" % TOKEN, text=True, env=env, timeout=30)
        self.assertIn("github.com", zugang.lesen())

    def test_abgelehnter_token_wird_nicht_gespeichert(self):
        zugang.ablauf_fragen = lambda h, t: (True, "")
        zugang.setzen("github.com", "prolo2408", token=TOKEN)
        zugang.ablauf_fragen = lambda h, t: (False, "")
        with self.assertRaises(Abbruch):
            zugang.setzen("github.com", "anderer", token="github_pat_neu12345")
        self.assertEqual(zugang.lesen()["github.com"]["token"], TOKEN)   # der alte bleibt

    def test_uebersicht_ohne_token(self):
        zugang.ablauf_fragen = lambda h, t: (True, "2027-11-05")
        zugang.setzen("github.com", "prolo2408", token=TOKEN)
        u = zugang.uebersicht()
        self.assertEqual(u, [{"host": "github.com", "benutzer": "prolo2408",
                              "gesetzt": datetime.date.today().isoformat(), "ablauf": "2027-11-05"}])
        self.assertNotIn(TOKEN, json.dumps(u))

    def test_entfernen(self):
        zugang.ablauf_fragen = lambda h, t: (None, "")
        zugang.setzen("github.com", "prolo2408", token=TOKEN)
        with self.assertRaises(Abbruch):
            zugang.entfernen("gitlab.com")
        zugang.entfernen("github.com")
        self.assertEqual(zugang.lesen(), {})

    def test_ablaufdatum_aus_der_kopfzeile(self):
        class Antwort:
            headers = {"github-authentication-token-expiration": "2027-11-05 12:00:00 +0100"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        alt = zugang.urllib.request.urlopen
        zugang.urllib.request.urlopen = lambda *a, **k: Antwort()
        try:
            self.assertEqual(zugang.ablauf_fragen("github.com", TOKEN), (True, "2027-11-05"))
            Antwort.headers = {}
            self.assertEqual(zugang.ablauf_fragen("github.com", TOKEN), (True, ""))
            self.assertEqual(zugang.ablauf_fragen("gitlab.com", TOKEN), (None, ""))
        finally:
            zugang.urllib.request.urlopen = alt

    def test_hinweise_vor_dem_ablauf(self):
        ab = datetime.date(2027, 11, 1)
        alle = [{"host": "a.de", "benutzer": "x", "ablauf": "2027-11-16"},   # 15 Tage: still
                {"host": "b.de", "benutzer": "x", "ablauf": "2027-11-15"},   # 14 Tage: warn
                {"host": "c.de", "benutzer": "x", "ablauf": "2027-11-01"},   # heute
                {"host": "d.de", "benutzer": "x", "ablauf": "2027-10-31"},   # gestern: Fehler
                {"host": "e.de", "benutzer": "x", "ablauf": ""}]
        h = zugang.hinweise(alle, ab)
        self.assertEqual([(x[0], x[1]) for x in h], [
            ("warn", "Der Git-Zugang für b.de läuft am 15.11.2027 ab (in 14 Tagen)."),
            ("warn", "Der Git-Zugang für c.de läuft am 01.11.2027 ab (heute)."),
            ("fehler", "Der Git-Zugang für d.de ist am 31.10.2027 abgelaufen - private "
                       "Repositories dort lassen sich nicht mehr aktualisieren.")])
        self.assertIn("sudo prolo git-zugang setzen d.de --benutzer x", h[2][2])

    def test_meldungen_von_git_sagen_was_zu_tun_ist(self):
        url = "https://github.com/prolo2408/galaxy-golf-bot"
        privat = "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
        t = zugang.fehler_text(url, "github.com", privat, False)
        self.assertIn("privat", t)
        self.assertIn("sudo prolo git-zugang setzen github.com --benutzer <name>", t)
        self.assertIn("abgelaufen oder widerrufen", zugang.fehler_text(url, "github.com", privat, True))
        weg = ("remote: Repository not found.\nfatal: repository "
               "'https://github.com/prolo2408/galaxy-golf-bot/' not found")
        self.assertIn("Repository access", zugang.fehler_text(url, "github.com", weg, True))
        self.assertEqual(zugang.host_von("https://Git.Example.de:8443/a/b"), "git.example.de")


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
