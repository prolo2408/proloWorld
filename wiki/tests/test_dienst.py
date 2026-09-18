"""Der Server als Dienst: echte Anfragen gegen einen echten Prozess.

Alle anderen Tests rufen Funktionen auf. Die Handhabung der Anfragen selbst -
Rechte, Rueckgabewerte, was nach einem Fehler in der Datenbank steht - war
damit nicht abgedeckt. Genau dort sass `N-30`: Loeschen gab HTTP 500 zurueck,
obwohl die Seite weg war.

Hier laeuft server.py als eigener Prozess auf einem freien Port, und die
Tests sprechen ihn ueber HTTP an - mit denselben Kopfzeilen, die der
Anmelde-Stellvertreter im Betrieb setzt.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import json
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


def freier_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Dienst(unittest.TestCase):
    """Ein laufender Server je Testklasse."""

    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.mkdtemp(prefix="wiki-dienst-")
        cls.daten = os.path.join(cls.ordner, "daten")
        cls.seiten = os.path.join(cls.ordner, "seiten")
        os.makedirs(cls.daten)
        os.makedirs(cls.seiten)
        cls.port = freier_port()
        umgebung = dict(os.environ,
                        WIKI_DATEN=cls.daten, WIKI_SEITEN=cls.seiten,
                        WIKI_PORT=str(cls.port))
        cls.prozess = subprocess.Popen(
            [sys.executable, os.path.join(WURZEL, "server.py")],
            env=umgebung, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Auf den Port warten, nicht auf eine Frist: ein schlafender Test ist
        # entweder zu langsam oder zu kurz.
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

    # ------------------------------------------------------------------
    def ruf(self, weg, nutzer="artur", gruppen="wiki-admin",
            daten=None, methode=None, typ="application/json"):
        """Eine Anfrage wie vom Anmelde-Stellvertreter. Gibt (code, inhalt)."""
        koerper = None
        if daten is not None:
            koerper = (daten if isinstance(daten, bytes)
                       else json.dumps(daten).encode())
        a = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, weg), data=koerper,
            method=methode or ("POST" if koerper is not None else "GET"))
        a.add_header("X-Authentik-Username", nutzer)
        a.add_header("X-Authentik-Name", nutzer.title())
        a.add_header("X-Authentik-Groups", gruppen)
        a.add_header("Sec-Fetch-Site", "same-origin")
        if koerper is not None:
            a.add_header("Content-Type", typ)
        try:
            with urllib.request.urlopen(a) as r:
                roh = r.read()
                code = r.status
        except urllib.error.HTTPError as e:
            roh, code = e.read(), e.code
        try:
            return code, json.loads(roh)
        except ValueError:
            return code, roh

    def seite_einspielen(self, slug, titel="Probe", nutzer="artur",
                         gruppen="wiki-admin"):
        html = SEITE % {"slug": slug, "titel": titel}
        code, antwort = self.ruf("/api/import", nutzer=nutzer, gruppen=gruppen,
                                 daten=html.encode(), typ="text/html")
        self.assertEqual(code, 200, antwort)
        return antwort


SEITE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script type="application/json" id="wiki-meta">
{"slug": "%(slug)s", "titel": "%(titel)s", "kurz": "Eine Seite fuer den Test.",
 "pfad": ["Technik"], "gruppen": [], "stand": "2026-09-18",
 "abschnitte": [{"anker": "a", "titel": "Abschnitt", "text": "Inhalt",
                 "stichworte": ["probe"]}]}
</script>
<style>:focus-visible{outline:2px solid #000}
@media (prefers-reduced-motion:reduce){*{transition:none}}</style>
</head><body><section id="a"><h2>Abschnitt</h2>
<p>Ein Absatz mit genug sichtbarem Text, damit die Seite eine Seite ist.</p>
</section></body></html>"""


class LoeschenSagtDieWahrheit(Dienst):
    """N-30: Die Seite war weg, die Antwort sagte "schiefgegangen"."""

    def test_ohne_bestaetigung_passiert_nichts(self):
        self.seite_einspielen("ohne-bestaetigung")
        code, antwort = self.ruf("/api/loeschen",
                                 daten={"slug": "ohne-bestaetigung"})
        self.assertEqual(code, 400, antwort)
        code, verw = self.ruf("/api/verwaltung")
        self.assertIn("ohne-bestaetigung", [s["slug"] for s in verw["seiten"]])

    def test_loeschen_legt_den_ordner_beiseite(self):
        self.seite_einspielen("mit-ordner")
        code, antwort = self.ruf("/api/loeschen",
                                 daten={"slug": "mit-ordner", "bestaetigt": True})
        self.assertEqual(code, 200, antwort)
        self.assertEqual(antwort.get("hinweis"), "",
                         "mit Ordner gibt es nichts zu melden")
        self.assertFalse(os.path.isdir(os.path.join(self.seiten, "mit-ordner")))
        beiseite = [n for n in os.listdir(self.seiten)
                    if n.startswith(".geloescht-mit-ordner-")]
        self.assertEqual(len(beiseite), 1, os.listdir(self.seiten))

    def test_fehlender_ordner_ist_kein_serverfehler(self):
        # Genau der gemessene Fall: HTTP 500 mit "Auf dem Server ist etwas
        # schiefgegangen (FileNotFoundError)" - und die Seite war weg.
        self.seite_einspielen("ohne-ordner")
        shutil.rmtree(os.path.join(self.seiten, "ohne-ordner"))
        code, antwort = self.ruf("/api/loeschen",
                                 daten={"slug": "ohne-ordner", "bestaetigt": True})
        self.assertEqual(code, 200, antwort)
        self.assertTrue(antwort.get("ok"))
        # Auf den Wortlaut geprueft, nicht nur auf "irgendein Hinweis":
        # sonst reicht auch die allgemeine Meldung fuer einen ganz anderen
        # Ordnerfehler, und der Unterschied zwischen "war nicht mehr da" und
        # "liess sich nicht verschieben" geht verloren.
        self.assertIn("hatte sie nicht mehr", antwort.get("hinweis", ""),
                      "die Antwort sagt nicht, dass es keinen Ordner gab")
        code, verw = self.ruf("/api/verwaltung")
        self.assertNotIn("ohne-ordner", [s["slug"] for s in verw["seiten"]])

    def test_eine_geloeschte_seite_ist_kein_zweites_mal_da(self):
        self.seite_einspielen("nur-einmal")
        self.ruf("/api/loeschen", daten={"slug": "nur-einmal", "bestaetigt": True})
        code, antwort = self.ruf("/api/loeschen",
                                 daten={"slug": "nur-einmal", "bestaetigt": True})
        self.assertEqual(code, 404, antwort)


class RechteAmDienst(Dienst):
    """Was die Kopfzeilen wirklich bewirken - nicht, was sie sollten."""

    def test_ohne_editorgruppe_kein_schreiben(self):
        code, antwort = self.ruf("/api/import", nutzer="leser", gruppen="wiki-lesen",
                                 daten=(SEITE % {"slug": "verboten",
                                                 "titel": "Verboten"}).encode(),
                                 typ="text/html")
        self.assertEqual(code, 403, antwort)
        self.assertIn("wiki-editor", str(antwort))

    def test_verwaltung_ist_verwaltersache(self):
        code, _ = self.ruf("/api/verwaltung", nutzer="lena", gruppen="wiki-editor")
        self.assertEqual(code, 403)
        code, _ = self.ruf("/api/verwaltung")
        self.assertEqual(code, 200)

    def test_neuindex_ist_verwaltersache(self):
        # Der Knopf dazu fehlte lange ganz (N-29) - die Sperre nicht.
        code, _ = self.ruf("/api/neuindex", nutzer="lena", gruppen="wiki-editor",
                           daten={})
        self.assertEqual(code, 403)
        code, antwort = self.ruf("/api/neuindex", daten={})
        self.assertEqual(code, 200, antwort)
        self.assertIn("verwaiste", antwort)

    def test_ein_editor_aendert_die_seite_eines_anderen_nicht(self):
        self.seite_einspielen("gehoert-artur")
        code, antwort = self.ruf(
            "/api/import", nutzer="lena", gruppen="wiki-editor",
            daten=(SEITE % {"slug": "gehoert-artur", "titel": "Geklaut"}).encode(),
            typ="text/html")
        self.assertEqual(code, 403, antwort)

    def test_eine_anfrage_von_fremder_seite_wird_abgewiesen(self):
        a = urllib.request.Request(
            "http://127.0.0.1:%d/api/loeschen" % self.port,
            data=b'{"slug":"x","bestaetigt":true}', method="POST")
        a.add_header("X-Authentik-Username", "artur")
        a.add_header("X-Authentik-Groups", "wiki-admin")
        a.add_header("Sec-Fetch-Site", "cross-site")
        a.add_header("Content-Type", "application/json")
        try:
            urllib.request.urlopen(a)
            self.fail("cross-site wurde nicht abgewiesen")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)


if __name__ == "__main__":
    unittest.main()
