"""Tests fuer das Bedienen ueber das Auftragsbuch (A-02).

Erwartungswerte von Hand (§13): die Rahmen des Docker-Protokolls sind Byte
fuer Byte hingeschrieben, die Kennungen abgezaehlt.

Der Schwerpunkt: wer darf einen Auftrag ablegen, was landet wirklich im
Eingang - und was die Seite aus fremder Hand (Protokolle, Ausgaben,
Labels) anzeigt, wird nie ausgefuehrt.
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
os.environ.setdefault("ADMIN_DATEN", tempfile.mkdtemp())

import server  # noqa: E402

ID_WIKI = "a" * 64
ID_TRAEFIK = "b" * 64


def rahmen(strom, daten):
    """Ein Rahmen des Docker-Protokolls, von Hand: Strom, drei Nullen,
    Laenge in 4 Byte gross-endian, dann die Daten."""
    return bytes([strom, 0, 0, 0]) + len(daten).to_bytes(4, "big") + daten


def buch():
    """Ein frisches Auftragsbuch im Kratzblock, in server eingetragen."""
    wurzel = tempfile.mkdtemp()
    server.EINGANG = os.path.join(wurzel, "eingang")
    server.ERLEDIGT = os.path.join(wurzel, "erledigt")
    os.makedirs(server.EINGANG)
    os.makedirs(server.ERLEDIGT)
    return wurzel


def erledigt(kennung, **lage):
    lage.setdefault("kennung", kennung)
    with open(os.path.join(server.ERLEDIGT, kennung + ".json"), "w") as f:
        json.dump(lage, f)


class TestEntmischen(unittest.TestCase):
    def test_zwei_rahmen_werden_zu_einem_text(self):
        roh = rahmen(1, b"hallo\n") + rahmen(2, b"fehler\n")
        # Von Hand: Kopf 8 Byte + 6, dann 8 + 7 = 29 Byte insgesamt.
        self.assertEqual(len(roh), 29)
        self.assertEqual(server.entmischen(roh), "hallo\nfehler\n")

    def test_mit_tty_kommt_es_roh_und_ohne_farben(self):
        self.assertEqual(server.entmischen(b"\x1b[32mgruen\x1b[0m\r\nweiter\n"),
                         "gruen\nweiter\n")

    def test_gewoehnlicher_text_bleibt(self):
        self.assertEqual(server.entmischen(b"abc\n"), "abc\n")

    def test_abgeschnittener_letzter_rahmen(self):
        # Die Lesegrenze kann mitten in einem Rahmen liegen: der Anfang
        # wird gezeigt, nichts stuerzt ab.
        roh = rahmen(1, b"eins\n") + rahmen(1, b"zwei\n")[:10]
        self.assertEqual(server.entmischen(roh), "eins\nzw")


class TestPfadeZumVermittler(unittest.TestCase):
    """Die Protokolle kommen ueber denselben Vermittler - aber nur genau
    dieser eine Pfad je bekannter Kennung. Nicht /json (dort stehen die
    Umgebungsvariablen, also Geheimnisse), nicht follow (haengt)."""

    def setUp(self):
        self.alt = server.DOCKER_API
        server.DOCKER_API = "http://127.0.0.1:1"   # da antwortet niemand

    def tearDown(self):
        server.DOCKER_API = self.alt

    def kode(self, pfad):
        with self.assertRaises(server.Antwort) as f:
            server.docker_roh(pfad)
        return f.exception.kode

    def test_protokoll_mit_kennung_kommt_durch_die_schranke(self):
        # 503 heisst: die Schranke liess durch, erst die Verbindung scheiterte.
        self.assertEqual(self.kode("/containers/%s/logs?stdout=1&stderr=1&tail=200" % ID_WIKI), 503)

    def test_was_nicht_erlaubt_ist(self):
        for pfad in ("/containers/%s/json" % ID_WIKI,
                     "/containers/%s/logs?stdout=1&stderr=1&tail=200&follow=1" % ID_WIKI,
                     "/containers/%s/logs?stdout=1&stderr=1&tail=200" % ID_WIKI[:12],
                     "/containers/../info",
                     "/info", "/containers/create"):
            with self.subTest(pfad=pfad):
                self.assertEqual(self.kode(pfad), 500)

    def test_protokoll_einer_unbekannten_kennung(self):
        with self.assertRaises(server.Antwort) as f:
            server.protokoll_lesen("../../info")
        self.assertEqual(f.exception.kode, 404)


class TestAuftragPruefen(unittest.TestCase):
    def kode(self, art, **felder):
        with self.assertRaises(server.Antwort) as f:
            server.auftrag_pruefen(art, felder)
        return f.exception

    def test_gueltig(self):
        self.assertEqual(server.auftrag_pruefen("neustart", {"werkzeug": "wiki"}),
                         {"werkzeug": "wiki"})
        self.assertEqual(server.auftrag_pruefen("sichern", {"werkzeug": "egal"}), {})
        self.assertEqual(server.auftrag_pruefen("netz_anlegen", {"netz": "netz-x"}),
                         {"netz": "netz-x"})

    def test_ungueltig(self):
        for art, felder in (("loeschen", {"werkzeug": "wiki"}),
                            ("start", {"werkzeug": "../traefik"}),
                            ("start", {"werkzeug": "Wiki"}),
                            ("start", {"werkzeug": ""}),
                            ("start", {"werkzeug": "a" * 41}),
                            ("netz_anlegen", {"netz": "netz;reboot"})):
            with self.subTest(art=art, felder=felder):
                self.assertEqual(self.kode(art, **felder).kode, 400)

    def test_den_zugang_haelt_man_nicht_von_hier_an(self):
        for w in ("traefik", "authentik", "socket-proxy", "admin"):
            with self.subTest(w=w):
                a = self.kode("stop", werkzeug=w)
                self.assertEqual(a.kode, 400)
                self.assertIn("sudo prolo stop %s" % w, a.text)
        # Neu starten geht.
        self.assertEqual(server.auftrag_pruefen("neustart", {"werkzeug": "traefik"}),
                         {"werkzeug": "traefik"})


class TestAuftragsbuch(unittest.TestCase):
    def setUp(self):
        self.alt = (server.EINGANG, server.ERLEDIGT)
        buch()

    def tearDown(self):
        server.EINGANG, server.ERLEDIGT = self.alt

    def eingang(self):
        return sorted(os.listdir(server.EINGANG))

    def test_ablegen_schreibt_genau_das(self):
        k, neu = server.auftrag_ablegen("neustart", {"werkzeug": "wiki", "netz": "x"}, "arthur")
        self.assertTrue(neu)
        self.assertRegex(k, r"^\d{8}-\d{6}-[0-9a-f]{8}$")
        self.assertEqual(self.eingang(), [k + ".json"])        # kein .neu uebrig
        with open(os.path.join(server.EINGANG, k + ".json")) as f:
            d = json.load(f)
        # Nur die Felder der Art - "netz" gehoert nicht zu neustart.
        self.assertEqual(sorted(d), ["angelegt", "art", "wer", "werkzeug"])
        self.assertEqual((d["art"], d["werkzeug"], d["wer"]), ("neustart", "wiki", "arthur"))

    def test_doppelt_gibt_es_nicht(self):
        k1, _ = server.auftrag_ablegen("neustart", {"werkzeug": "wiki"}, "a")
        k2, neu = server.auftrag_ablegen("neustart", {"werkzeug": "wiki"}, "b")
        self.assertEqual((k2, neu), (k1, False))
        self.assertEqual(len(self.eingang()), 1)
        # Anderes Ziel: ein eigener Auftrag.
        k3, neu = server.auftrag_ablegen("neustart", {"werkzeug": "n8n"}, "a")
        self.assertTrue(neu)
        self.assertNotEqual(k3, k1)

    def test_laeuft_er_schon_gibt_es_auch_keinen_zweiten(self):
        erledigt("20260930-110000-0000000a", art="aktualisieren", werkzeug="wiki",
                 status="laeuft")
        k, neu = server.auftrag_ablegen("aktualisieren", {"werkzeug": "wiki"}, "a")
        self.assertEqual((k, neu), ("20260930-110000-0000000a", False))

    def test_ist_er_fertig_gibt_es_einen_neuen(self):
        erledigt("20260930-110000-0000000a", art="aktualisieren", werkzeug="wiki",
                 status="ok")
        k, neu = server.auftrag_ablegen("aktualisieren", {"werkzeug": "wiki"}, "a")
        self.assertTrue(neu)

    def test_ohne_eingang_sagt_es_den_befehl(self):
        server.EINGANG = os.path.join(server.EINGANG, "gibtsnicht")
        with self.assertRaises(server.Antwort) as f:
            server.auftrag_ablegen("start", {"werkzeug": "wiki"}, "a")
        self.assertEqual(f.exception.kode, 503)
        self.assertIn("sudo prolo einrichten", f.exception.text)

    def test_liste_neueste_zuerst_mit_wartenden(self):
        # Die Kennung beginnt mit der Zeit: die beiden erledigten liegen im
        # Januar, der neue ist von jetzt - also der neueste.
        erledigt("20260101-100000-00000001", art="start", werkzeug="wiki", status="ok")
        erledigt("20260101-100500-00000002", art="stop", werkzeug="wiki", status="fehler")
        k, _ = server.auftrag_ablegen("pruefen", {"werkzeug": "wiki"}, "a")
        # Muell daneben wird nicht angezeigt.
        with open(os.path.join(server.ERLEDIGT, "kaputt.json"), "w") as f:
            f.write("{")
        with open(os.path.join(server.ERLEDIGT, "20260101-100600-00000003.json"), "w") as f:
            f.write("{kein json")
        liste = server.auftraege_lesen()
        self.assertEqual([(a["kennung"], a["status"]) for a in liste],
                         [(k, "wartet"),
                          ("20260101-100500-00000002", "fehler"),
                          ("20260101-100000-00000001", "ok")])

    def test_ausgabe_ohne_farben(self):
        erledigt("20260930-100000-00000001", art="start", status="ok")
        with open(os.path.join(server.ERLEDIGT, "20260930-100000-00000001.log"), "wb") as f:
            f.write(b"\x1b[1mTitel\x1b[0m\nweiter\n")
        lage, ausgabe = server.auftrag_lesen("20260930-100000-00000001")
        self.assertEqual(ausgabe, "Titel\nweiter\n")
        self.assertEqual(lage["status"], "ok")

    def test_eine_kennung_ist_kein_pfad(self):
        # "geheim" gibt es als Datei - nur das Muster haelt es fern. Ohne
        # eine vorhandene Datei waere die Probe auch ohne Muster gruen.
        with open(os.path.join(server.ERLEDIGT, "geheim.json"), "w") as f:
            json.dump({"art": "start", "status": "ok"}, f)
        for k in ("geheim", "../erledigt/geheim", "20260930-100000-0000000", "x"):
            with self.subTest(k=k):
                with self.assertRaises(server.Antwort) as f:
                    server.auftrag_lesen(k)
                self.assertEqual(f.exception.kode, 404)


class TestSicht(unittest.TestCase):
    L = {"werkzeuge": [
        {"name": "wiki", "dienste": [{"dienst": "wiki", "zustand": "running", "hosts": ["wiki.x"]}]},
        {"name": "(ohne Projekt)", "dienste": [{"dienst": "fremd", "zustand": "running", "hosts": []}]},
    ], "netze": []}

    def test_bestand_und_docker_zusammen(self):
        b = {"werkzeuge": [{"name": "wiki", "art": "eigen"},
                           {"name": "n8n", "art": "fremd", "hosts": ["n8n.x"]}]}
        s = {x["name"]: x for x in server.werkzeuge_sicht(self.L, b)}
        self.assertEqual(sorted(s), ["(ohne Projekt)", "n8n", "wiki"])
        self.assertEqual((s["wiki"]["zustand"], s["wiki"]["bedienbar"]), ("laeuft", True))
        self.assertEqual((s["n8n"]["zustand"], s["n8n"]["bedienbar"], s["n8n"]["hosts"]),
                         ("angehalten", True, ["n8n.x"]))
        # Ohne Ordner und ohne gueltigen Namen: sehen ja, bedienen nein.
        self.assertFalse(s["(ohne Projekt)"]["bedienbar"])

    def test_ohne_bestand_entscheidet_der_ausfuehrer(self):
        s = {x["name"]: x for x in server.werkzeuge_sicht(self.L, None)}
        self.assertTrue(s["wiki"]["bedienbar"])


# ------------------------------------------------------------ Der Dienst
def behaelter(name, projekt, cid, labels=None, zustand="running"):
    l = {"com.docker.compose.project": projekt, "com.docker.compose.service": name}
    l.update(labels or {})
    return {"Id": cid, "Names": ["/" + name], "Image": "abbild:1.0", "State": zustand,
            "Status": "Up 2 days", "Labels": l,
            "NetworkSettings": {"Networks": {"netz-" + projekt: {}}}, "Ports": []}


class TestBedienen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.DB = os.path.join(tempfile.mkdtemp(), "admin.db")
        server.datenbank_anlegen()
        cls.alt = (server.EINGANG, server.ERLEDIGT, server.docker_lesen, server.docker_roh)
        buch()
        with open(os.path.join(server.ERLEDIGT, "bestand.json"), "w") as f:
            json.dump({"stand": "x", "werkzeuge": [
                {"name": "wiki", "art": "eigen", "sicherung": True},
                {"name": "traefik", "art": "plattform", "sicherung": True},
                {"name": "n8n", "art": "fremd", "sicherung": True,
                 "dienste": [{"dienst": "n8n", "abbild": "n8nio/n8n:1.0"}]},
                {"name": "../boese", "art": "fremd"}]}, f)
        roh = [behaelter("wiki", "wiki", ID_WIKI),
               behaelter("traefik", "traefik", ID_TRAEFIK)]

        def lesen(pfad):
            return roh if pfad.startswith("/containers") else []

        def roh_lesen(pfad, grenze=0):
            # Ein Protokoll mit einem Skript darin: kommt aus dem Container,
            # also aus fremder Hand.
            return rahmen(1, b"gestartet\n<script>alert(2)</script>\n")
        server.docker_lesen = lesen
        server.docker_roh = roh_lesen
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.srv.daemon_threads = True
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        server.EINGANG, server.ERLEDIGT, server.docker_lesen, server.docker_roh = cls.alt

    class OhneFolgen(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    SEHEN = {"X-Prolo-Einlass": EINLASS, "X-Authentik-Username": "leser",
             "X-Authentik-Groups": "admin"}
    BEDIENEN = {"X-Prolo-Einlass": EINLASS, "X-Authentik-Username": "arthur",
                "X-Authentik-Groups": "admin,admin-betrieb"}

    def hol(self, pfad, kopf, daten=None, ursprung=True):
        kopf = dict(kopf)
        if daten is not None:
            kopf["Content-Type"] = "application/x-www-form-urlencoded"
            if ursprung is True:
                kopf["Origin"] = "http://127.0.0.1:%d" % self.port
            elif ursprung:
                kopf["Origin"] = ursprung
        a = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, pfad),
                                   data=daten, method="POST" if daten is not None else "GET")
        for k, v in kopf.items():
            a.add_header(k, v)
        try:
            with urllib.request.build_opener(self.OhneFolgen()).open(a) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers

    def setUp(self):
        for n in os.listdir(server.EINGANG):
            os.unlink(os.path.join(server.EINGANG, n))

    def eingang(self):
        return sorted(os.listdir(server.EINGANG))

    def test_bedienen_legt_einen_auftrag_ab(self):
        kode, _, kopf = self.hol("/auftrag", self.BEDIENEN, b"art=neustart&werkzeug=wiki")
        self.assertEqual(kode, 303)
        k = kopf["Location"][len("/auftrag/"):]
        self.assertEqual(self.eingang(), [k + ".json"])
        with open(os.path.join(server.EINGANG, k + ".json")) as f:
            d = json.load(f)
        self.assertEqual((d["art"], d["werkzeug"], d["wer"]), ("neustart", "wiki", "arthur"))

    def test_sehen_ist_nicht_bedienen(self):
        kode, text, _ = self.hol("/auftrag", self.SEHEN, b"art=neustart&werkzeug=wiki")
        self.assertEqual(kode, 403)
        self.assertIn("admin-betrieb", text)
        self.assertEqual(self.eingang(), [])

    def test_von_fremder_seite_abgesendet(self):
        kode, _, _ = self.hol("/auftrag", self.BEDIENEN, b"art=neustart&werkzeug=wiki",
                              ursprung="https://woanders.example")
        self.assertEqual(kode, 403)
        kode, _, _ = self.hol("/auftrag", self.BEDIENEN, b"art=neustart&werkzeug=wiki",
                              ursprung=False)
        self.assertEqual(kode, 403)
        self.assertEqual(self.eingang(), [])

    def test_den_zugang_anhalten_geht_nicht(self):
        kode, text, _ = self.hol("/auftrag", self.BEDIENEN, b"art=stop&werkzeug=traefik")
        self.assertEqual(kode, 400)
        self.assertIn("sudo prolo stop traefik", text)
        self.assertEqual(self.eingang(), [])

    def test_doppelklick_gibt_einen_auftrag(self):
        _, _, k1 = self.hol("/auftrag", self.BEDIENEN, b"art=pruefen&werkzeug=wiki")
        _, _, k2 = self.hol("/auftrag", self.BEDIENEN, b"art=pruefen&werkzeug=wiki")
        self.assertEqual(k1["Location"], k2["Location"])
        self.assertEqual(len(self.eingang()), 1)

    def test_auftragsseite_laedt_nach_solange_er_wartet(self):
        _, _, kopf = self.hol("/auftrag", self.BEDIENEN, b"art=start&werkzeug=n8n")
        kode, text, _ = self.hol(kopf["Location"], self.SEHEN)
        self.assertEqual(kode, 200)
        self.assertIn(">wartet<", text)
        self.assertIn("/api/auftrag/", text)
        kode, text, _ = self.hol("/api" + kopf["Location"], self.SEHEN)
        d = json.loads(text)
        self.assertEqual((d["status"], d["offen"]), ("wartet", True))

    def test_die_seite_darf_ihren_stand_nachholen(self):
        # Die Richtlinie der Seite muss den fetch auf /api/auftrag/
        # erlauben - und nur zur eigenen Adresse. Ohne connect-src greift
        # default-src 'none', und die Seite bleibt auf "wartet" stehen.
        _, _, kopf = self.hol("/auftraege", self.SEHEN)
        csp = [x.strip() for x in kopf["Content-Security-Policy"].split(";")]
        self.assertIn("connect-src 'self'", csp)
        self.assertIn("default-src 'none'", csp)

    def test_eine_fertige_auftragsseite_laedt_nicht_nach(self):
        erledigt("20260930-090000-000000ff", art="start", werkzeug="wiki", status="ok",
                 rueckgabe=0)
        with open(os.path.join(server.ERLEDIGT, "20260930-090000-000000ff.log"), "w") as f:
            f.write("fertig </pre><script>alert(3)</script>\n")
        kode, text, _ = self.hol("/auftrag/20260930-090000-000000ff", self.SEHEN)
        self.assertEqual(kode, 200)
        self.assertNotIn("/api/auftrag/", text)
        self.assertIn(">erledigt<", text)
        # Die Ausgabe kommt vom Server, aber aus Werkzeugen - maskiert.
        self.assertNotIn("<script>alert(3)", text)
        self.assertIn("&lt;/pre&gt;&lt;script&gt;alert(3)", text)

    def test_werkzeugseite_zum_bedienen(self):
        kode, text, _ = self.hol("/werkzeug/wiki", self.BEDIENEN)
        self.assertEqual(kode, 200)
        for w in ("neustart", "aktualisieren", "pruefen", "stop"):
            self.assertIn('name="art" value="%s"' % w, text)
        self.assertIn('data-frage="wiki anhalten?', text)
        # Das Protokoll ist da - und maskiert.
        self.assertIn("gestartet", text)
        self.assertNotIn("<script>alert(2)", text)
        self.assertIn("&lt;script&gt;alert(2)", text)

    def test_werkzeugseite_zum_sehen(self):
        kode, text, _ = self.hol("/werkzeug/wiki", self.SEHEN)
        self.assertEqual(kode, 200)
        self.assertNotIn('action="/auftrag"', text)
        self.assertNotIn("gestartet", text)          # kein Protokoll
        self.assertIn("admin-betrieb", text)

    def test_den_zugang_zeigt_die_seite_gesperrt(self):
        _, text, _ = self.hol("/werkzeug/traefik", self.BEDIENEN)
        self.assertNotIn('name="art" value="stop"', text)
        self.assertIn("disabled>Anhalten</button>", text)
        self.assertIn("sudo prolo stop traefik", text)
        self.assertIn('name="art" value="neustart"', text)

    def test_ein_angehaltenes_werkzeug_laesst_sich_starten(self):
        kode, text, _ = self.hol("/werkzeug/n8n", self.BEDIENEN)
        self.assertEqual(kode, 200)
        self.assertIn('name="art" value="start"', text)
        self.assertNotIn('name="art" value="stop"', text)
        self.assertIn("n8nio/n8n:1.0", text)
        _, text, _ = self.hol("/werkzeuge", self.SEHEN)
        self.assertIn('href="/werkzeug/n8n"', text)
        self.assertIn("angehalten", text)
        # Ohne Container keine Labels: nicht "kein Router" raten.
        zeile = text[text.index('href="/werkzeug/n8n"'):].split("</tr>")[0]
        self.assertNotIn("kein Router", zeile)
        self.assertIn("erst nach dem Start lesbar", zeile)

    def test_unbekanntes_werkzeug(self):
        for pfad in ("/werkzeug/gibtsnicht", "/werkzeug/../boese", "/werkzeug/%2e%2e%2fboese"):
            with self.subTest(pfad=pfad):
                kode, _, _ = self.hol(pfad, self.BEDIENEN)
                self.assertEqual(kode, 404)

    def test_seiten_gehen_auf(self):
        for p in ("/", "/werkzeuge", "/netze", "/auftraege", "/einstellungen"):
            with self.subTest(p=p):
                kode, _, _ = self.hol(p, self.BEDIENEN)
                self.assertEqual(kode, 200)

    def test_netz_anlegen_nur_fuer_betrieb(self):
        _, text, _ = self.hol("/netze", self.SEHEN)
        self.assertNotIn('value="netz_anlegen"', text)
        _, text, _ = self.hol("/netze", self.BEDIENEN)
        self.assertIn('value="netz_anlegen"', text)
        kode, _, kopf = self.hol("/auftrag", self.BEDIENEN, b"art=netz_anlegen&netz=netz-neu")
        self.assertEqual(kode, 303)


if __name__ == "__main__":
    unittest.main()
