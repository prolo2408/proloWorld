"""N-44: Die Identitaet ist nur so viel wert wie die Gewissheit, dass die
Anfrage ueber den Zugang dieses Servers kam.

Das Bordbuch sagt seit jeher den richtigen Satz dazu - "der Kopf ist nur so
viel wert wie die Gewissheit, dass ausschliesslich der Reverse-Proxy den
Server erreicht". Diese Gewissheit gab es nicht: im Docker-Netz erreicht
jeder Container Port 8080 eines anderen direkt. Am Wiki gemessen bekam eine
Anfrage mit "X-Authentik-Groups: wiki-admin" die Verwaltungsdaten.

Hier laeuft server.py als eigener Prozess - die anderen Bordbuch-Tests
rufen Funktionen auf und wuerden die Grenze gar nicht sehen.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EINLASS = "probe-einlass-7c1d"


def freier_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Vertrauensgrenze(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.mkdtemp(prefix="bordbuch-grenze-")
        cls.port = freier_port()
        umgebung = dict(os.environ,
                        BORDBUCH_DB=os.path.join(cls.ordner, "bordbuch.db"),
                        BORDBUCH_BELEGE=os.path.join(cls.ordner, "belege"),
                        LADELOG_HOST="127.0.0.1",
                        LADELOG_PORT=str(cls.port),
                        PROLO_EINLASS=EINLASS)
        cls.prozess = subprocess.Popen(
            [sys.executable, os.path.join(WURZEL, "server.py")],
            env=umgebung, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(200):
            try:
                s = socket.create_connection(("127.0.0.1", cls.port), 0.2)
                s.close()
                break
            except OSError:
                if cls.prozess.poll() is not None:
                    raise AssertionError("Server beendet: %s"
                                         % cls.prozess.stderr.read().decode())
                time.sleep(0.05)
        else:
            raise AssertionError("Server kam nicht hoch")

    @classmethod
    def tearDownClass(cls):
        cls.prozess.terminate()
        try:
            cls.prozess.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.prozess.kill()
        shutil.rmtree(cls.ordner, ignore_errors=True)

    def post(self, weg, einlass=True):
        return self.ruf(weg, einlass=einlass, daten=b"{}")

    def ruf(self, weg, einlass=True, gruppen="bordbuch-admin", daten=None):
        a = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, weg),
                                   data=daten,
                                   method="POST" if daten is not None else "GET")
        if daten is not None:
            a.add_header("Content-Type", "application/json")
        a.add_header("X-Authentik-Username", "probe")
        a.add_header("X-Authentik-Groups", gruppen)
        if einlass is True:
            a.add_header("X-Prolo-Einlass", EINLASS)
        elif einlass:
            a.add_header("X-Prolo-Einlass", einlass)
        try:
            with urllib.request.urlopen(a) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    # ------------------------------------------------------------------
    def test_ohne_marke_kommt_niemand_durch(self):
        # Genau der Angriff: volle Adminrechte behauptet, keine Marke.
        self.assertEqual(self.ruf("/api/admin/export", einlass=False), 401)

    def test_eine_geratene_marke_hilft_nicht(self):
        self.assertEqual(self.ruf("/api/admin/export", einlass="geraten"), 401)

    def test_auch_die_oberflaeche_bleibt_zu(self):
        self.assertEqual(self.ruf("/", einlass=False), 401)

    def test_eine_marke_mit_umlaut_gibt_401_und_keinen_serverfehler(self):
        self.assertEqual(self.ruf("/api/state", einlass="gehäim"), 401)

    def test_die_fassung_bleibt_frei(self):
        # Die Gesundheitspruefung im Dockerfile und PRUEF_URL aus
        # aktualisierung.conf rufen genau diesen Pfad am Zugang vorbei auf.
        self.assertEqual(self.ruf("/api/version", einlass=False), 200)

    def test_auch_schreibende_aufrufe_brauchen_die_marke(self):
        # Dieselbe Luecke wie im Wiki: eine Grenze nur in do_GET faellt
        # keinem lesenden Test auf. Der Pfad muss es gar nicht geben - die
        # Grenze steht vor der Verteilung.
        self.assertEqual(self.post("/api/probe", einlass=False), 401)
        self.assertNotEqual(self.post("/api/probe"), 401)

    def test_mit_marke_entscheidet_weiter_die_gruppe(self):
        # Die zweite Schicht ersetzt die erste nicht.
        self.assertEqual(self.ruf("/api/admin/export", gruppen=""), 403)
        self.assertEqual(self.ruf("/api/admin/export"), 200)


if __name__ == "__main__":
    unittest.main()
