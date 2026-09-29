"""Tests fuer die Admin-Uebersicht.

Erwartungswerte von Hand (CLAUDE.md §13): jede Lage hier ist ausgedacht
und das Ergebnis dazu abgezaehlt, nicht aus dem Code uebernommen.

Der Schwerpunkt liegt auf den beiden Dingen, bei denen ein Fehler teuer
waere: wer hereindarf, und ob die Seite einen ungeschuetzten Router als
solchen erkennt. Eine Uebersicht, die "alles in Ordnung" sagt, obwohl ein
Dienst offen steht, ist schlimmer als gar keine.
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EINLASS = "probe-einlass-wert"
os.environ["PROLO_EINLASS"] = EINLASS
os.environ["ADMIN_DATEN"] = tempfile.mkdtemp()

import server  # noqa: E402


# ------------------------------------------------------- Ausgedachte Lage
def behaelter(name, projekt, dienst, labels=None, netze=("netz-x",),
              zustand="running", ports=()):
    l = {"com.docker.compose.project": projekt,
         "com.docker.compose.service": dienst}
    l.update(labels or {})
    return {
        "Names": ["/" + name], "Image": "abbild:1.0", "State": zustand,
        "Status": "Up 2 days", "Labels": l,
        "NetworkSettings": {"Networks": {n: {} for n in netze}},
        "Ports": [{"PublicPort": p, "PrivatePort": p, "Type": "tcp"} for p in ports],
    }


AUTH = {"traefik.enable": "true",
        "traefik.http.routers.a.rule": "Host(`a.prolo.me`)",
        "traefik.http.routers.a.middlewares": "authentik@file"}


class TestSchutz(unittest.TestCase):
    """Womit ist ein Dienst geschuetzt? Gelesen, nicht geraten."""

    def test_authentik(self):
        self.assertEqual(server.schutz_lesen(AUTH), ("authentik", ""))

    def test_eigene_anmeldung_ist_erklaert(self):
        self.assertEqual(
            server.schutz_lesen({"traefik.enable": "true",
                                 "prolo.anmeldung": "eigene",
                                 "prolo.anmeldung.grund": "API direkt"}),
            ("eigene", "API direkt"))

    def test_oeffentlich_ist_erklaert(self):
        self.assertEqual(
            server.schutz_lesen({"traefik.enable": "true",
                                 "prolo.oeffentlich": "www"}),
            ("oeffentlich", "www"))

    def test_ohne_alles_ist_OFFEN(self):
        # Das ist der Fall, um dessentwillen es diese Seite gibt: ein
        # fehlendes middlewares= sieht aus wie ein vergessenes (N-59).
        self.assertEqual(
            server.schutz_lesen({"traefik.enable": "true",
                                 "traefik.http.routers.a.rule": "Host(`a`)"}),
            ("OFFEN", ""))

    def test_kein_router_ist_kein_mangel(self):
        # Eine Datenbank hat keinen Router. Sie ist nicht "offen", sie ist
        # gar nicht erreichbar - das darf nicht als Mangel gemeldet werden.
        self.assertEqual(server.schutz_lesen({"irgendwas": "1"}), ("", ""))

    def test_authentik_schlaegt_eine_erklaerung(self):
        # Steht beides da, gilt die Middleware. Sonst koennte ein Label
        # eine Anmeldung wegerklaeren, die tatsaechlich davorsteht.
        self.assertEqual(
            server.schutz_lesen(dict(AUTH, **{"prolo.anmeldung": "eigene"})),
            ("authentik", ""))

    def test_traefik_aus_zaehlt_nicht(self):
        self.assertEqual(
            server.schutz_lesen({"traefik.enable": "false",
                                 "traefik.http.routers.a.rule": "Host(`a`)"}),
            ("", ""))


class TestLage(unittest.TestCase):
    """Aus zwei Listen wird ein Bild."""

    def bauen(self, container, netze=None):
        def ersatz(pfad):
            if pfad == "/containers/json?all=1":
                return container
            if pfad == "/networks":
                return netze if netze is not None else []
            raise AssertionError("unerwarteter Pfad " + pfad)
        alt = server.docker_lesen
        server.docker_lesen = ersatz
        try:
            return server.lage()
        finally:
            server.docker_lesen = alt

    def test_container_werden_nach_projekt_gebuendelt(self):
        l = self.bauen([
            behaelter("wiki", "wiki", "wiki", AUTH, ("netz-wiki",)),
            behaelter("ak-server", "authentik", "server", {}, ("netz-authentik",)),
            behaelter("ak-db", "authentik", "postgresql", {}, ("authentik_internal",)),
        ])
        # Von Hand: zwei Projekte, authentik hat zwei Dienste.
        self.assertEqual([w["name"] for w in l["werkzeuge"]], ["authentik", "wiki"])
        self.assertEqual(len(l["werkzeuge"][0]["dienste"]), 2)
        self.assertEqual([d["dienst"] for d in l["werkzeuge"][0]["dienste"]],
                         ["postgresql", "server"])

    def test_netze_entstehen_auch_aus_den_containern(self):
        # Ein Netz, das die Netzliste nicht nennt, aber ein Container
        # benutzt, darf nicht verschwinden.
        l = self.bauen([behaelter("a", "p", "a", AUTH, ("netz-a", "socket"))],
                       netze=[{"Name": "netz-a", "Driver": "bridge"}])
        self.assertEqual(sorted(n["name"] for n in l["netze"]), ["netz-a", "socket"])
        nach = {n["name"]: n["container"] for n in l["netze"]}
        self.assertEqual(nach["netz-a"], ["a"])
        self.assertEqual(nach["socket"], ["a"])

    def test_hostnamen_werden_aus_der_regel_gelesen(self):
        l = self.bauen([behaelter("a", "p", "a", {
            "traefik.enable": "true",
            "traefik.http.routers.a.rule": "Host(`a.prolo.me`) || Host(`b.prolo.me`)",
            "traefik.http.routers.a.middlewares": "authentik@file"})])
        self.assertEqual(l["werkzeuge"][0]["dienste"][0]["hosts"],
                         ["a.prolo.me", "b.prolo.me"])

    def test_ohne_compose_labels_gibt_es_trotzdem_eine_zeile(self):
        # Ein von Hand gestarteter Container gehoert keinem Projekt. Er
        # darf trotzdem nicht unter den Tisch fallen - gerade der.
        l = self.bauen([{"Names": ["/fremd"], "Image": "x:1", "State": "running",
                         "Status": "Up", "Labels": {}, "NetworkSettings": {},
                         "Ports": []}])
        self.assertEqual(l["werkzeuge"][0]["name"], "(ohne Projekt)")


class TestBeanstandungen(unittest.TestCase):
    """Was jemand sehen muss, ohne danach zu suchen."""

    def lage_mit(self, *dienste):
        return {"werkzeuge": [{"name": "p", "dienste": list(dienste)}], "netze": []}

    def d(self, **kw):
        g = {"dienst": "a", "container": "a", "abbild": "x:1", "zustand": "running",
             "lage": "Up", "netze": ["netz-a"], "netz_label": "netz-a", "hosts": [],
             "schutz": "authentik", "schutz_grund": "", "ports": [], "ports_grund": ""}
        g.update(kw)
        return g

    def test_sauber_gibt_nichts(self):
        self.assertEqual(server.beanstandungen(self.lage_mit(self.d())), [])

    def test_offener_router(self):
        b = server.beanstandungen(self.lage_mit(self.d(schutz="OFFEN")))
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0][0], "ungeschuetzt")

    def test_offener_port_ohne_grund(self):
        b = server.beanstandungen(self.lage_mit(self.d(ports=["8081"])))
        self.assertEqual([z[0] for z in b], ["offener Port"])
        self.assertIn("8081", b[0][2])

    def test_offener_port_mit_grund_ist_keiner(self):
        # Traefik MUSS 80 und 443 veroeffentlichen. Ein erklaerter Port ist
        # eine Entscheidung und kein Fund - sonst meldet diese Seite jeden
        # Tag denselben Fehlalarm, und beim echten sieht niemand mehr hin.
        b = server.beanstandungen(self.lage_mit(
            self.d(ports=["80", "443"], ports_grund="Eingang des Stacks")))
        self.assertEqual(b, [])

    def test_label_und_netz_laufen_auseinander(self):
        # N-58: ein neues Netz erreicht einen laufenden Container nicht.
        b = server.beanstandungen(self.lage_mit(
            self.d(netze=["netz-alt"], netz_label="netz-neu")))
        self.assertEqual([z[0] for z in b], ["falsches Netz"])
        self.assertIn("N-58", b[0][2])

    def test_container_haelt_nicht(self):
        b = server.beanstandungen(self.lage_mit(
            self.d(zustand="exited", lage="Exited (1) vor 2 Minuten")))
        self.assertEqual([z[0] for z in b], ["haelt nicht"])

    def test_mehrere_auf_einmal(self):
        # Von Hand abgezaehlt: offener Router + offener Port = 2.
        b = server.beanstandungen(self.lage_mit(
            self.d(schutz="OFFEN", ports=["9000"])))
        self.assertEqual(len(b), 2)


class TestDockerPfade(unittest.TestCase):
    def test_nur_die_zwei_erlaubten_pfade(self):
        # Eine Uebersicht, die eine Adresse aus der Anfrage zusammenbaut,
        # ist ein offener Tuersteher fuer das interne Netz.
        with self.assertRaises(server.Antwort) as f:
            server.docker_lesen("/containers/abc/json")
        self.assertEqual(f.exception.kode, 500)


# ------------------------------------------------------------ Der Dienst
class TestDienst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.DB = os.path.join(tempfile.mkdtemp(), "admin.db")
        server.DATEN = os.path.dirname(server.DB)
        server.datenbank_anlegen()
        cls.lage_roh = [
            behaelter("wiki", "wiki", "wiki", AUTH, ("netz-wiki",)),
            behaelter("boese", "boese", "boese", {
                "traefik.enable": "true",
                "traefik.http.routers.b.rule": "Host(`<script>alert(1)</script>`)",
            }, ("netz-b",)),
        ]

        def ersatz(pfad):
            if pfad == "/containers/json?all=1":
                return cls.lage_roh
            return [{"Name": "netz-wiki", "Driver": "bridge"}]
        # Merken und in tearDownClass zurueckgeben: ohne das laeuft der
        # naechste Test gegen die Attrappe weiter und prueft etwas
        # anderes, als er zu pruefen glaubt.
        cls.echtes_docker_lesen = server.docker_lesen
        server.docker_lesen = ersatz

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.srv.daemon_threads = True
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        server.docker_lesen = cls.echtes_docker_lesen

    # urllib folgt einer 303 von selbst. Dann misst der Test die Seite
    # DANACH und nie die Weiterleitung - und eine kaputte Weiterleitung
    # faellt nicht auf.
    class OhneFolgen(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def hol(self, pfad, kopf=None, daten=None):
        a = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, pfad),
                                   data=daten, method="POST" if daten else "GET")
        for k, v in (kopf or {}).items():
            a.add_header(k, v)
        oeffner = urllib.request.build_opener(self.OhneFolgen())
        try:
            with oeffner.open(a) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers

    ANGEMELDET = {"X-Prolo-Einlass": EINLASS, "X-Authentik-Username": "arthur",
                  "X-Authentik-Groups": "admin,wiki-editor",
                  "X-Authentik-Name": "Arthur", "X-Authentik-Email": "a@b.c"}

    def test_gesundheit_braucht_keine_marke(self):
        kode, text, _ = self.hol("/gesundheit")
        self.assertEqual((kode, text), (200, "ok"))

    def test_version_braucht_keine_marke(self):
        kode, text, _ = self.hol("/api/version")
        self.assertEqual(kode, 200)
        self.assertEqual(json.loads(text)["version"], server.VERSION)

    def test_ohne_marke_keine_uebersicht(self):
        # N-44: im Docker-Netz erreicht jeder Container Port 8080 eines
        # anderen direkt. Ohne die Marke von Traefik antwortet nichts.
        kode, _, _ = self.hol("/", {"X-Authentik-Username": "arthur",
                                    "X-Authentik-Groups": "admin"})
        self.assertEqual(kode, 401)

    def test_mit_marke_aber_ohne_anmeldung(self):
        kode, _, _ = self.hol("/", {"X-Prolo-Einlass": EINLASS})
        self.assertEqual(kode, 401)

    def test_falsche_marke(self):
        # Absichtlich der ANFANG des richtigen Werts. Ein Vergleich, der
        # nur den Anfang prueft (startswith statt compare_digest), waere
        # sonst gruen - und wer den Anfang raet, kaeme herein.
        kode, _, _ = self.hol("/", dict(self.ANGEMELDET,
                                        **{"X-Prolo-Einlass": EINLASS[:-1]}))
        self.assertEqual(kode, 401)
        kode, _, _ = self.hol("/", dict(self.ANGEMELDET,
                                        **{"X-Prolo-Einlass": EINLASS + "x"}))
        self.assertEqual(kode, 401)

    def test_angemeldet_ohne_gruppe(self):
        kode, text, _ = self.hol("/", dict(self.ANGEMELDET,
                                           **{"X-Authentik-Groups": "wiki-editor"}))
        self.assertEqual(kode, 403)
        self.assertIn("admin", text)

    def test_fremde_gruppe_mit_aehnlichem_namen_zaehlt_nicht(self):
        # "wiki-admin" faengt nicht mit "admin" an und ist auch nicht
        # "admin". Ein Werkzeug wertet nur SEINE Gruppen aus (§17).
        kode, _, _ = self.hol("/", dict(self.ANGEMELDET,
                                        **{"X-Authentik-Groups": "wiki-admin"}))
        self.assertEqual(kode, 403)

    def test_admin_darf(self):
        kode, text, _ = self.hol("/", self.ANGEMELDET)
        self.assertEqual(kode, 200)
        self.assertIn("Zu klaeren", text)

    def test_der_offene_router_steht_auf_der_uebersicht(self):
        _, text, _ = self.hol("/", self.ANGEMELDET)
        self.assertIn("ungeschuetzt", text)
        self.assertIn("boese/boese", text)

    def test_ein_boeses_label_wird_nicht_ausgefuehrt(self):
        # Die Labels kommen aus fremden Abbildern. Wer sie ungefiltert
        # ausgibt, baut sich eine Seite, die der Container bestimmt.
        _, text, _ = self.hol("/werkzeuge", self.ANGEMELDET)
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_netze_und_werkzeuge_gehen_auf(self):
        for p in ("/werkzeuge", "/netze", "/einstellungen"):
            kode, _, _ = self.hol(p, self.ANGEMELDET)
            self.assertEqual(kode, 200, p)

    def test_unbekannter_weg(self):
        kode, text, _ = self.hol("/gibtsnicht", self.ANGEMELDET)
        self.assertEqual(kode, 404)
        self.assertIn("Uebersicht", text)   # Die Meldung fuehrt zurueck (§7)

    def test_thema_speichern(self):
        kode, _, kopf = self.hol(
            "/einstellungen/thema",
            dict(self.ANGEMELDET, **{"Content-Type": "application/x-www-form-urlencoded",
                                     "Origin": "http://127.0.0.1:%d" % self.port}),
            b"thema=hell")
        self.assertEqual(kode, 303)
        with server.verbindung() as k:
            z = k.execute("SELECT thema FROM nutzer WHERE nutzer_id='arthur'").fetchone()
        self.assertEqual(z["thema"], "hell")
        _, text, _ = self.hol("/einstellungen", self.ANGEMELDET)
        self.assertIn('value="hell" aria-pressed="true"', text)

    def test_thema_von_fremder_seite_abgesendet(self):
        kode, _, _ = self.hol(
            "/einstellungen/thema",
            dict(self.ANGEMELDET, **{"Content-Type": "application/x-www-form-urlencoded",
                                     "Origin": "https://woanders.example"}),
            b"thema=dunkel")
        self.assertEqual(kode, 403)

    def test_unbekanntes_thema(self):
        kode, text, _ = self.hol(
            "/einstellungen/thema",
            dict(self.ANGEMELDET, **{"Content-Type": "application/x-www-form-urlencoded",
                                     "Origin": "http://127.0.0.1:%d" % self.port}),
            b"thema=lila")
        self.assertEqual(kode, 400)
        self.assertIn("system", text)   # sagt, was moeglich waere (§7)

    def test_kopfzeilen_gegen_einbetten(self):
        _, _, kopf = self.hol("/", self.ANGEMELDET)
        self.assertIn("frame-ancestors 'none'", kopf.get("Content-Security-Policy"))
        self.assertEqual(kopf.get("X-Content-Type-Options"), "nosniff")

    def test_schriften_nur_aus_dem_ordner(self):
        kode, _, _ = self.hol("/schriften/../server.py", self.ANGEMELDET)
        self.assertIn(kode, (400, 404))


class TestAbgebrocheneVerbindung(unittest.TestCase):
    """Ein Browser, der mitten in der Antwort geht, darf den Dienst nicht
    beenden (N-82).

    Gemessen wird am ECHTEN Prozess, nicht am Handler im Testfaden: der
    Fehler sass in main(), und ein Signal trifft den ganzen Prozess. Im
    selben Prozess wie die Tests liefe die Probe gar nicht erst durch -
    sie wuerde den Testlauf selbst beenden.
    """

    def starten(self):
        import socket
        import subprocess
        import time
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        daten = tempfile.mkdtemp()
        umgebung = dict(os.environ, PROLO_EINLASS=EINLASS, ADMIN_DATEN=daten,
                        ADMIN_PORT=str(port),
                        ADMIN_DOCKER_API="http://127.0.0.1:1")
        prozess = subprocess.Popen(
            [sys.executable, os.path.join(os.path.dirname(server.__file__),
                                          "server.py")],
            env=umgebung, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(prozess.kill)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        return prozess, port

    def test_sigpipe_bleibt_ignoriert(self):
        # Die Ursache selbst, nicht nur ihre Wirkung: ist SIGPIPE im
        # laufenden Dienst ignoriert? Bit 13 in SigIgn (Zaehlung ab 1).
        # Das haengt nicht davon ab, ob ein Schreibversuch zufaellig vor
        # oder nach dem RST kommt.
        prozess, _ = self.starten()
        with open("/proc/%d/status" % prozess.pid) as f:
            zeile = [z for z in f if z.startswith("SigIgn:")][0]
        maske = int(zeile.split()[1], 16)
        self.assertTrue(maske & (1 << (13 - 1)),
                        "SIGPIPE ist im Dienst nicht ignoriert (SigIgn %s)"
                        % zeile.split()[1])

    def test_dienst_ueberlebt_abgebrochene_verbindungen(self):
        import socket
        import struct
        import time
        prozess, port = self.starten()
        # Zehnmal: Anfrage auf eine Schriftdatei (die Antwort ist grosser
        # als eine leere Seite), dann sofort RST statt eines geordneten
        # Schliessens. Das ist, was ein Browser beim Wegklicken tut.
        for _ in range(10):
            c = socket.create_connection(("127.0.0.1", port))
            c.sendall(b"GET /schriften/sora-latin.woff2 HTTP/1.1\r\n"
                      b"Host: x\r\nX-Prolo-Einlass: " + EINLASS.encode()
                      + b"\r\n\r\n")
            c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                         struct.pack("ii", 1, 0))
            c.close()
            time.sleep(0.05)
        self.assertIsNone(prozess.poll(),
                          "der Dienst hat sich beendet (Rueckgabe %s)"
                          % prozess.returncode)
        with urllib.request.urlopen("http://127.0.0.1:%d/gesundheit" % port,
                                    timeout=5) as r:
            self.assertEqual(r.read(), b"ok")


if __name__ == "__main__":
    unittest.main()
