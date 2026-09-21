"""Das Freigabe-Werkzeug als Dienst: echte Anfragen gegen einen echten Prozess.

Geprueft wird der ganze Weg, den ein Link nimmt - anlegen, einloesen,
zurueckziehen, WIEDER freischalten, Passwort dazu und wieder weg, Seite
loeschen. Und die Rechte: wer ohne die Gruppe kommt, sieht nichts.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EINLASS = "probe-einlass-www-3a"
ADMIN = "stack-admin"

SEITE = ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\">"
         "<title>Lebenslauf lang</title></head><body><h1>Artur</h1>"
         "<p>Feuerwehr, Fotografie.</p></body></html>")


def freier_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Dienst(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.mkdtemp(prefix="www-test-")
        cls.port = freier_port()
        umgebung = dict(os.environ,
                        WWW_DATEN=os.path.join(cls.ordner, "daten"),
                        WWW_SEITEN=os.path.join(cls.ordner, "seiten"),
                        WWW_PORT=str(cls.port),
                        WWW_ADMIN_GRUPPE=ADMIN,
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

    # ------------------------------------------------------------------
    def ruf(self, weg, nutzer="artur", gruppen=ADMIN, daten=None,
            methode=None, typ="application/json", einlass=True, keks=None,
            folgen=False, absender=None):
        koerper = None
        if daten is not None:
            koerper = daten if isinstance(daten, bytes) else json.dumps(daten).encode()
        a = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, weg), data=koerper,
            method=methode or ("POST" if koerper is not None else "GET"))
        if nutzer:
            a.add_header("X-Authentik-Username", nutzer)
        if gruppen:
            a.add_header("X-Authentik-Groups", gruppen)
        a.add_header("Sec-Fetch-Site", "same-origin")
        if einlass is True:
            a.add_header("X-Prolo-Einlass", EINLASS)
        elif einlass:
            a.add_header("X-Prolo-Einlass", einlass)
        if koerper is not None:
            a.add_header("Content-Type", typ)
        if keks:
            a.add_header("Cookie", "prolo_einlass=" + keks)
        if absender:
            # So sieht der Server verschiedene Aufrufer. Traefik haengt
            # seinen Eintrag hinten an, darum zaehlt der letzte.
            a.add_header("X-Forwarded-For", "9.9.9.9, " + absender)

        class OhneFolgen(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        oeffner = (urllib.request.build_opener()
                   if folgen else urllib.request.build_opener(OhneFolgen))
        try:
            with oeffner.open(a) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def js(self, *a, **k):
        code, roh, _ = self.ruf(*a, **k)
        try:
            return code, json.loads(roh)
        except ValueError:
            return code, roh

    def seite_ablegen(self, titel="Lebenslauf lang"):
        code, antwort = self.js("/api/hochladen?titel=" + titel.replace(" ", "%20"),
                                daten=SEITE.encode(), typ="text/html")
        self.assertEqual(code, 200, antwort)
        return antwort["kennung"]

    def link_ausgeben(self, kennung, etikett="Bewerbung Probe", tage=90):
        code, antwort = self.js("/api/freigabe",
                                daten={"kennung": kennung, "etikett": etikett,
                                       "tage": tage})
        self.assertEqual(code, 200, antwort)
        return antwort["marke"]

    def keks_holen(self, marke):
        code, _, kopf = self.ruf("/z/" + marke, nutzer="", gruppen="")
        self.assertEqual(code, 302)
        roh = kopf.get("Set-Cookie", "")
        return roh.split("prolo_einlass=")[1].split(";")[0], kopf["Location"]


class DerWegEinesLinks(Dienst):
    """Anlegen, einloesen, zurueckziehen, WIEDER freischalten."""

    def test_der_ganze_weg(self):
        kennung = self.seite_ablegen("Lebenslauf lang")
        self.assertEqual(kennung, "lebenslauf-lang")

        marke = self.link_ausgeben(kennung, "Bewerbung Stadtwerke")
        # 24 Byte urlsafe-base64 sind 32 Zeichen - von Hand gerechnet:
        # ceil(24/3)*4 = 32, ohne Fuellzeichen.
        self.assertEqual(len(marke), 32)

        keks, ziel = self.keks_holen(marke)
        self.assertEqual(ziel, "/s/lebenslauf-lang")

        code, roh, _ = self.ruf("/s/lebenslauf-lang", nutzer="", gruppen="",
                                keks=keks)
        self.assertEqual(code, 200)
        self.assertIn(b"Feuerwehr", roh)

        # Zurueckziehen - der Link gilt nicht mehr, die Seite bleibt.
        nummer = self.freigabe_nummer(kennung)
        code, _ = self.js("/api/zustand", daten={"id": nummer,
                                                 "zustand": "gesperrt"})
        self.assertEqual(code, 200)
        code, _, _ = self.ruf("/z/" + marke, nutzer="", gruppen="")
        self.assertEqual(code, 403)
        # Auch das alte Plaetzchen traegt nicht mehr.
        code, _, _ = self.ruf("/s/lebenslauf-lang", nutzer="", gruppen="",
                              keks=keks)
        self.assertEqual(code, 403)

        # Und wieder freischalten: DERSELBE Link geht wieder.
        code, _ = self.js("/api/zustand", daten={"id": nummer,
                                                 "zustand": "aktiv"})
        self.assertEqual(code, 200)
        keks2, ziel2 = self.keks_holen(marke)
        self.assertEqual(ziel2, "/s/lebenslauf-lang")

    def freigabe_nummer(self, kennung, nr=0):
        _, d = self.js("/api/verwaltung")
        for s in d["seiten"]:
            if s["kennung"] == kennung:
                return s["freigaben"][nr]["id"]
        raise AssertionError("Seite %s nicht in der Verwaltung" % kennung)

    def test_die_marke_steht_nirgends_gespeichert(self):
        kennung = self.seite_ablegen("Nur Abdruck")
        marke = self.link_ausgeben(kennung, "Probe Abdruck")
        _, d = self.js("/api/verwaltung")
        self.assertNotIn(marke, json.dumps(d),
                         "die Marke steht in der Verwaltungsauskunft")
        pfad = os.path.join(self.ordner, "daten", "www.db")
        with open(pfad, "rb") as f:
            roh = f.read()
        self.assertNotIn(marke.encode(), roh,
                         "die Marke steht im Klartext in der Datenbank")

    def test_eine_geratene_marke_fuehrt_nirgendwohin(self):
        code, _, _ = self.ruf("/z/" + "A" * 32, nutzer="", gruppen="")
        self.assertEqual(code, 404)

    def test_ohne_plaetzchen_keine_seite(self):
        kennung = self.seite_ablegen("Ohne Keks")
        self.link_ausgeben(kennung, "Probe")
        code, _, _ = self.ruf("/s/" + kennung, nutzer="", gruppen="")
        self.assertEqual(code, 403)

    def test_ein_gebasteltes_plaetzchen_traegt_nicht(self):
        """Die Signatur ist das Einzige, was zaehlt (§11).

        Das Plaetzchen nennt hier die RICHTIGE Freigabe-Nummer - sonst
        scheitert es schon daran, dass die Nummer zu einer anderen Seite
        gehoert, und die Signaturpruefung waere gar nicht die Stelle, die
        abweist. Genau so war es zuerst: die Probe "Signatur egal" liess
        alle Tests gruen.
        """
        kennung = self.seite_ablegen("Gebastelt")
        self.link_ausgeben(kennung, "Probe")
        nummer = self.freigabe_nummer(kennung)
        weit = int(time.time()) + 99999
        gebastelt = [
            "%d.%d.abc" % (nummer, weit),          # richtige Nummer, falsche Signatur
            "%d.%d." % (nummer, weit),             # gar keine Signatur
            "%d.%d.%s" % (nummer, weit, "A" * 43),  # Signatur in richtiger Laenge
            "quatsch", "",
        ]
        for falsch in gebastelt:
            with self.subTest(keks=falsch):
                code, _, _ = self.ruf("/s/" + kennung, nutzer="", gruppen="",
                                      keks=falsch)
                self.assertEqual(code, 403, "Plaetzchen %r kam durch" % falsch)

    def test_ein_plaetzchen_gilt_nur_fuer_seine_seite(self):
        a = self.seite_ablegen("Seite A")
        b = self.seite_ablegen("Seite B")
        marke_a = self.link_ausgeben(a, "Probe A")
        keks, _ = self.keks_holen(marke_a)
        code, _, _ = self.ruf("/s/" + b, nutzer="", gruppen="", keks=keks)
        self.assertEqual(code, 403)

    def test_der_zaehler_zaehlt(self):
        kennung = self.seite_ablegen("Gezaehlt")
        marke = self.link_ausgeben(kennung, "Probe Zaehler")
        for _ in range(3):
            self.keks_holen(marke)
        _, d = self.js("/api/verwaltung")
        s = [x for x in d["seiten"] if x["kennung"] == kennung][0]
        self.assertEqual(s["freigaben"][0]["aufrufe"], 3)

    def test_ein_abgelaufener_link_traegt_nicht(self):
        kennung = self.seite_ablegen("Abgelaufen")
        code, antwort = self.js("/api/freigabe",
                                daten={"kennung": kennung, "etikett": "X",
                                       "tage": 0})
        self.assertEqual(code, 200, antwort)   # 0 = ohne Ablauf
        self.assertIsNone(antwort["laeuft_ab"])
        code, antwort = self.js("/api/freigabe",
                                daten={"kennung": kennung, "etikett": "Y",
                                       "tage": 4000})
        self.assertEqual(code, 400, "4000 Tage muessen abgewiesen werden")


class Passwort(Dienst):
    """Ein Passwort laesst sich zuschalten und wieder wegnehmen."""

    def nummer(self, kennung):
        _, d = self.js("/api/verwaltung")
        for s in d["seiten"]:
            if s["kennung"] == kennung:
                return s["freigaben"][0]["id"]
        raise AssertionError("Seite fehlt")

    def test_mit_passwort_geht_es_erst_nach_dem_formular(self):
        kennung = self.seite_ablegen("Mit Passwort")
        marke = self.link_ausgeben(kennung, "Probe Passwort")
        nummer = self.nummer(kennung)
        code, _ = self.js("/api/passwort", daten={"id": nummer,
                                                  "passwort": "gutes-passwort"})
        self.assertEqual(code, 200)

        # Der Link allein fuehrt jetzt auf das Formular, nicht zur Seite.
        code, roh, kopf = self.ruf("/z/" + marke, nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertNotIn("Set-Cookie", kopf)
        self.assertIn(b"Passwort", roh)

        # Falsches Passwort: wieder das Formular, mit Hinweis, kein Keks.
        code, roh, kopf = self.ruf("/z/" + marke, nutzer="", gruppen="",
                                   daten=b"passwort=falsch",
                                   typ="application/x-www-form-urlencoded")
        self.assertEqual(code, 200)
        self.assertNotIn("Set-Cookie", kopf)
        self.assertIn("stimmt nicht", roh.decode("utf-8"))

        # Richtiges Passwort: Keks und Umleitung.
        code, _, kopf = self.ruf("/z/" + marke, nutzer="", gruppen="",
                                 daten=b"passwort=gutes-passwort",
                                 typ="application/x-www-form-urlencoded")
        self.assertEqual(code, 302)
        self.assertIn("prolo_einlass=", kopf.get("Set-Cookie", ""))

        # Wieder wegnehmen: der Link fuehrt ohne Umweg zur Seite.
        code, _ = self.js("/api/passwort", daten={"id": nummer, "passwort": ""})
        self.assertEqual(code, 200)
        code, _, kopf = self.ruf("/z/" + marke, nutzer="", gruppen="")
        self.assertEqual(code, 302)

    def test_ein_zu_kurzes_passwort_wird_abgewiesen(self):
        kennung = self.seite_ablegen("Kurzes Passwort")
        self.link_ausgeben(kennung, "Probe")
        code, antwort = self.js("/api/passwort",
                                daten={"id": self.nummer(kennung),
                                       "passwort": "kurz"})
        self.assertEqual(code, 400, antwort)

    def test_das_passwort_steht_nicht_im_klartext(self):
        kennung = self.seite_ablegen("Geheim abgelegt")
        self.link_ausgeben(kennung, "Probe")
        self.js("/api/passwort", daten={"id": self.nummer(kennung),
                                        "passwort": "sehr-geheim-123"})
        with open(os.path.join(self.ordner, "daten", "www.db"), "rb") as f:
            roh = f.read()
        self.assertNotIn(b"sehr-geheim-123", roh)


class Sperre(Dienst):
    """Raten wird nach zehn Fehlversuchen eine Stunde lang sinnlos."""

    def test_nach_zehn_fehlversuchen_ist_ruhe(self):
        codes = []
        for i in range(12):
            code, _, _ = self.ruf("/z/" + ("B" * 31) + str(i % 10),
                                  nutzer="", gruppen="", absender="10.0.0.1")
            codes.append(code)
        # Von Hand: die ersten zehn sind 404 (Marke gibt es nicht), ab dem
        # elften greift die Sperre mit 429.
        self.assertEqual(codes[:10], [404] * 10, codes)
        self.assertEqual(codes[10:], [429, 429], codes)

    def test_die_sperre_trifft_auch_echte_marken(self):
        # Sonst koennte man raten, bis es klappt, und die Sperre waere
        # nur eine Bremse fuer Tippfehler.
        kennung = self.seite_ablegen("Nach der Sperre")
        marke = self.link_ausgeben(kennung, "Probe")
        for i in range(10):
            self.ruf("/z/" + ("C" * 31) + str(i), nutzer="", gruppen="",
                     absender="10.0.0.2")
        code, _, _ = self.ruf("/z/" + marke, nutzer="", gruppen="",
                              absender="10.0.0.2")
        self.assertEqual(code, 429)
        # Und ein anderer Aufrufer ist davon nicht betroffen.
        code, _, _ = self.ruf("/z/" + marke, nutzer="", gruppen="",
                              absender="10.0.0.3")
        self.assertEqual(code, 302)

    def test_eine_vorangestellte_adresse_unterlaeuft_die_sperre_nicht(self):
        """Der Fehler, den der Testlauf gefunden hat.

        Stuende hier der ERSTE Eintrag aus X-Forwarded-For, koennte ein
        Angreifer bei jedem Versuch eine andere Adresse vorne anstellen und
        die Sperre waere wirkungslos. Genau das wird hier versucht.
        """
        import urllib.request as u
        codes = []
        for i in range(12):
            a = u.Request("http://127.0.0.1:%d/z/%s" % (self.port, "D" * 32))
            a.add_header("X-Prolo-Einlass", EINLASS)
            # Bei jedem Versuch eine andere erfundene Adresse VORNE.
            a.add_header("X-Forwarded-For", "1.2.3.%d, 10.0.0.4" % i)
            try:
                with u.urlopen(a) as r:
                    codes.append(r.status)
            except urllib.error.HTTPError as e:
                codes.append(e.code)
        self.assertEqual(codes[10:], [429, 429],
                         "die Sperre liess sich mit einer erfundenen "
                         "Adresse unterlaufen: %s" % codes)


class Rechte(Dienst):
    """Wer ohne die Gruppe kommt, sieht nichts."""

    ROLLEN = {
        "anonym": ("", ""),
        "angemeldet": ("lena", ""),
        "fremd": ("mika", "wiki-admin,bordbuch-admin"),
        "verwalter": ("artur", ADMIN),
    }
    WEGE = [
        ("GET", "/verwaltung", None),
        ("GET", "/api/verwaltung", None),
        ("POST", "/api/freigabe", {"kennung": "x", "etikett": "y"}),
        ("POST", "/api/zustand", {"id": 1, "zustand": "gesperrt"}),
        ("POST", "/api/passwort", {"id": 1, "passwort": "achtzeichen"}),
        ("POST", "/api/loeschen", {"kennung": "x", "bestaetigt": True}),
    ]
    # Von Hand: ohne Anmeldung 401, angemeldet aber ohne Gruppe 403 - auch
    # mit den Verwaltungsgruppen ANDERER Werkzeuge.
    SOLL = {"anonym": 401, "angemeldet": 403, "fremd": 403}

    def test_die_matrix(self):
        for methode, weg, daten in self.WEGE:
            for rolle, (nutzer, gruppen) in self.ROLLEN.items():
                with self.subTest(weg=weg, rolle=rolle):
                    code, _, _ = self.ruf(weg, nutzer=nutzer, gruppen=gruppen,
                                          daten=daten, methode=methode)
                    if rolle == "verwalter":
                        self.assertNotIn(code, (401, 403),
                                         "%s als %s" % (weg, rolle))
                    else:
                        self.assertEqual(code, self.SOLL[rolle],
                                         "%s als %s" % (weg, rolle))

    def test_die_matrix_ist_vollstaendig(self):
        self.assertGreaterEqual(len(self.WEGE) * len(self.ROLLEN), 24)

    def test_das_hochladen_haengt_an_derselben_gruppe(self):
        for rolle, (nutzer, gruppen) in self.ROLLEN.items():
            if rolle == "verwalter":
                continue
            with self.subTest(rolle=rolle):
                code, _, _ = self.ruf("/api/hochladen", nutzer=nutzer,
                                      gruppen=gruppen, daten=SEITE.encode(),
                                      typ="text/html")
                self.assertEqual(code, self.SOLL[rolle])

    def test_eine_fremde_seite_kommt_nicht_durch(self):
        # Sec-Fetch-Site: cross-site ist ein Formular von woanders.
        import urllib.request as u
        a = u.Request("http://127.0.0.1:%d/api/loeschen" % self.port,
                      data=b'{"kennung":"x","bestaetigt":true}', method="POST")
        a.add_header("X-Prolo-Einlass", EINLASS)
        a.add_header("X-Authentik-Username", "artur")
        a.add_header("X-Authentik-Groups", ADMIN)
        a.add_header("Sec-Fetch-Site", "cross-site")
        a.add_header("Content-Type", "application/json")
        try:
            u.urlopen(a)
            self.fail("cross-site wurde nicht abgewiesen")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)


class Vertrauensgrenze(Dienst):
    """N-44 - auch die oeffentlichen Pfade liegen dahinter."""

    def test_ohne_marke_kommt_niemand_durch(self):
        for weg in ("/", "/verwaltung", "/api/verwaltung", "/z/" + "A" * 32,
                    "/s/irgendwas"):
            with self.subTest(weg=weg):
                code, _, _ = self.ruf(weg, nutzer="artur", gruppen=ADMIN,
                                      einlass=False)
                self.assertEqual(code, 401)

    def test_auch_schreibende_aufrufe_brauchen_die_marke(self):
        code, _, _ = self.ruf("/api/freigabe", daten={"kennung": "x",
                                                      "etikett": "y"},
                              einlass=False)
        self.assertEqual(code, 401)

    def test_die_zwei_freien_pfade_bleiben_frei(self):
        for weg in ("/gesundheit", "/api/version"):
            with self.subTest(weg=weg):
                code, _, _ = self.ruf(weg, nutzer="", gruppen="", einlass=False)
                self.assertEqual(code, 200)


class Eingaben(Dienst):
    """Was hochgeladen wird, ist grundsaetzlich falsch (§11)."""

    def test_keine_html_datei(self):
        code, antwort = self.js("/api/hochladen", daten=b"nur text",
                                typ="text/html")
        self.assertEqual(code, 400)
        self.assertIn("HTML", antwort["fehler"])

    def test_leere_datei(self):
        code, antwort = self.js("/api/hochladen", daten=b"   ", typ="text/html")
        self.assertEqual(code, 400)

    def test_kein_utf8(self):
        code, antwort = self.js("/api/hochladen", daten=b"<html>\xff\xfe</html>",
                                typ="text/html")
        self.assertEqual(code, 400)
        self.assertIn("UTF-8", antwort["fehler"])

    def test_eine_freigabe_ohne_etikett_wird_abgewiesen(self):
        kennung = self.seite_ablegen("Ohne Etikett")
        code, antwort = self.js("/api/freigabe",
                                daten={"kennung": kennung, "etikett": "  "})
        self.assertEqual(code, 400)
        self.assertIn("Etikett", antwort["fehler"])

    def test_boeser_titel_bleibt_harmlos(self):
        böse = "</title><script>alert(1)</script>"
        code, antwort = self.js("/api/hochladen", daten=SEITE.encode(),
                                typ="text/html")
        self.assertEqual(code, 200)
        # Der Titel aus der Datei wird gelesen, nicht ausgefuehrt: die
        # Kennung enthaelt nur Kleinbuchstaben, Ziffern und Bindestriche.
        self.assertRegex(antwort["kennung"], r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

    def test_loeschen_ohne_bestaetigung_passiert_nicht(self):
        kennung = self.seite_ablegen("Nicht loeschen")
        code, _ = self.js("/api/loeschen", daten={"kennung": kennung})
        self.assertEqual(code, 400)
        _, d = self.js("/api/verwaltung")
        self.assertIn(kennung, [s["kennung"] for s in d["seiten"]])

    def test_geloeschte_seite_ist_weg_und_ihre_links_tot(self):
        kennung = self.seite_ablegen("Wird geloescht")
        marke = self.link_ausgeben(kennung, "Probe")
        code, _ = self.js("/api/loeschen", daten={"kennung": kennung,
                                                  "bestaetigt": True})
        self.assertEqual(code, 200)
        _, d = self.js("/api/verwaltung")
        self.assertNotIn(kennung, [s["kennung"] for s in d["seiten"]])
        code, _, _ = self.ruf("/z/" + marke, nutzer="", gruppen="")
        self.assertEqual(code, 404)
        # Die Datei liegt noch da (§15): erst markieren, dann irgendwann weg.
        self.assertTrue(os.path.exists(
            os.path.join(self.ordner, "seiten", kennung + ".html")))


class DieStartseite(Dienst):
    """Was unter "/" steht - das Schild, oder eine abgelegte Seite.

    Der heikle Teil ist nicht das Ausliefern, sondern die Grenze drumherum:
    eine Startseite ist oeffentlich, alles andere bleibt es nicht. Darum
    wird hier jedes Mal beides geprueft - dass sie erscheint UND dass die
    Freigaben davon nichts abbekommen.
    """

    START = ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\">"
             "<title>Prolo Startseite</title></head><body>"
             "<h1>Willkommen</h1><p>Kennwort Sonnenblume.</p></body></html>")

    def start_ablegen(self, titel="Prolo Startseite"):
        code, antwort = self.js(
            "/api/hochladen?titel=" + titel.replace(" ", "%20"),
            daten=self.START.encode(), typ="text/html")
        self.assertEqual(code, 200, antwort)
        return antwort["kennung"]

    def aufraeumen(self):
        self.js("/api/startseite", daten={"kennung": ""})

    # ------------------------------------------------------------------
    def test_ohne_markierung_steht_dort_das_schild(self):
        self.aufraeumen()
        code, roh, kopf = self.ruf("/", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertIn("Hier liegt nichts offen herum", roh.decode())
        # Das Schild ist kein oeffentlicher Inhalt: es bleibt draussen.
        self.assertIn("noindex", kopf.get("X-Robots-Tag", ""))

    def test_markierte_seite_steht_unter_der_nackten_adresse(self):
        self.aufraeumen()
        kennung = self.start_ablegen()
        code, antwort = self.js("/api/startseite", daten={"kennung": kennung})
        self.assertEqual(code, 200, antwort)
        self.assertEqual(antwort["startseite"], kennung)

        # OHNE Anmeldung, OHNE Plaetzchen - genau das ist der Punkt.
        code, roh, kopf = self.ruf("/", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertIn(b"Kennwort Sonnenblume", roh)
        self.assertNotIn(b"Hier liegt nichts offen herum", roh)
        # Sie darf gefunden werden - und nur sie.
        self.assertEqual(kopf.get("X-Robots-Tag"), "all")
        # Fremder Code bleibt fremder Code: derselbe Riegel wie bei einer
        # freigegebenen Seite.
        self.assertIn("default-src 'none'", kopf.get("Content-Security-Policy", ""))
        self.assertIn("frame-ancestors 'none'", kopf.get("Content-Security-Policy", ""))
        self.aufraeumen()

    def test_eine_startseite_oeffnet_die_freigaben_nicht(self):
        """Der eigentliche Prueferbeweis.

        Eine oeffentliche Startseite ist genau eine Adresse. Waere sie
        versehentlich ein Generalschluessel, faende man es nur hier.
        """
        start = self.start_ablegen("Oeffentlich")
        geheim = self.seite_ablegen("Streng geheim")
        self.js("/api/startseite", daten={"kennung": start})

        # Die freigegebene Seite bleibt ohne Plaetzchen verschlossen.
        code, _, _ = self.ruf("/s/" + geheim, nutzer="", gruppen="")
        self.assertEqual(code, 403)
        # Auch die Startseite selbst ist unter ihrer eigenen Kennung nicht
        # frei - oeffentlich ist die Wurzel, nicht die Seite.
        code, _, _ = self.ruf("/s/" + start, nutzer="", gruppen="")
        self.assertEqual(code, 403)
        # Und die Verwaltung erst recht nicht.
        code, _, _ = self.ruf("/verwaltung", nutzer="", gruppen="")
        self.assertEqual(code, 401)
        self.aufraeumen()

    def test_robots_erlaubt_genau_die_wurzel(self):
        self.aufraeumen()
        code, roh, _ = self.ruf("/robots.txt", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        # Handgerechnet: ohne Startseite ist alles gesperrt, ohne Ausnahme.
        self.assertEqual(roh.decode(), "User-agent: *\nDisallow: /\n")

        kennung = self.start_ablegen("Robots Probe")
        self.js("/api/startseite", daten={"kennung": kennung})
        code, roh, _ = self.ruf("/robots.txt", nutzer="", gruppen="")
        self.assertEqual(roh.decode(),
                         "User-agent: *\nAllow: /$\nDisallow: /\n")
        self.aufraeumen()

    def test_markierung_wieder_abnehmen(self):
        kennung = self.start_ablegen("Nur kurz")
        self.js("/api/startseite", daten={"kennung": kennung})
        code, antwort = self.js("/api/startseite", daten={"kennung": ""})
        self.assertEqual(code, 200)
        self.assertIsNone(antwort["startseite"])
        code, roh, _ = self.ruf("/", nutzer="", gruppen="")
        self.assertIn("Hier liegt nichts offen herum", roh.decode())
        # Die Seite selbst bleibt liegen - abnehmen ist kein Loeschen.
        _, d = self.js("/api/verwaltung")
        self.assertIn(kennung, [s["kennung"] for s in d["seiten"]])
        self.aufraeumen()

    def test_es_gibt_immer_hoechstens_eine(self):
        self.aufraeumen()
        a = self.start_ablegen("Erste Wahl")
        b = self.start_ablegen("Zweite Wahl")
        self.js("/api/startseite", daten={"kennung": a})
        self.js("/api/startseite", daten={"kennung": b})
        _, d = self.js("/api/verwaltung")
        self.assertEqual(d["startseite"], b)
        self.aufraeumen()

    def test_eine_unbekannte_seite_wird_abgewiesen(self):
        self.aufraeumen()
        code, antwort = self.js("/api/startseite",
                                daten={"kennung": "gibt-es-nicht"})
        self.assertEqual(code, 404)
        self.assertIn("gibt es nicht", antwort["fehler"])

    def test_wer_nicht_darf_kann_es_nicht_setzen(self):
        self.aufraeumen()
        kennung = self.start_ablegen("Fremde Hand")
        code, _ = self.js("/api/startseite", daten={"kennung": kennung},
                          gruppen="irgendwas")
        self.assertEqual(code, 403)
        code, _ = self.js("/api/startseite", daten={"kennung": kennung},
                          nutzer="", gruppen="")
        self.assertEqual(code, 401)
        # Und nichts davon ist angekommen.
        _, d = self.js("/api/verwaltung")
        self.assertIsNone(d["startseite"])

    def test_die_geloeschte_startseite_faellt_auf_das_schild_zurueck(self):
        self.aufraeumen()
        kennung = self.start_ablegen("Wird geloescht")
        self.js("/api/startseite", daten={"kennung": kennung})
        code, antwort = self.js("/api/loeschen",
                                daten={"kennung": kennung, "bestaetigt": True})
        self.assertEqual(code, 200)
        self.assertTrue(antwort["war_startseite"])
        code, roh, kopf = self.ruf("/", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertIn("Hier liegt nichts offen herum", roh.decode())
        self.assertIn("noindex", kopf.get("X-Robots-Tag", ""))
        # Und die Zeile ist wirklich weg, nicht nur wirkungslos.
        _, d = self.js("/api/verwaltung")
        self.assertIsNone(d["startseite"])

    def db(self):
        """Die Datenbank des Dienstes, zum Nachsehen und zum Stellen.

        Zwei Faelle lassen sich ueber die Schnittstelle gar nicht
        beobachten: ob eine Zeile WIRKLICH weg ist (statt nur wirkungslos)
        und was passiert, wenn eine Markierung auf eine geloeschte Seite
        zeigt. Beides deckt im Code je eine eigene Sicherung ab - und die
        eine hat die andere in der Mutationsprobe zugedeckt, bis diese
        beiden Tests dazukamen (N-68: zwei Riegel, eine Pruefzeile, also
        ein blinder Fleck).
        """
        return sqlite3.connect(os.path.join(self.ordner, "daten", "www.db"))

    def test_die_markierung_ist_nach_dem_loeschen_wirklich_weg(self):
        self.aufraeumen()
        kennung = self.start_ablegen("Spurlos")
        self.js("/api/startseite", daten={"kennung": kennung})
        with self.db() as con:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM einstellung WHERE schluessel='startseite'"
            ).fetchone()[0], 1)
        self.js("/api/loeschen", daten={"kennung": kennung, "bestaetigt": True})
        # Nicht "wirkt nicht mehr", sondern "steht nicht mehr da". Eine
        # Zeile, die auf eine geloeschte Seite zeigt, ist eine Zeile ins
        # Leere - und die naechste Sicherung traegt sie mit (§12).
        with self.db() as con:
            self.assertEqual(con.execute(
                "SELECT count(*) FROM einstellung WHERE schluessel='startseite'"
            ).fetchone()[0], 0)

    def test_eine_markierung_auf_eine_geloeschte_seite_wirkt_nicht(self):
        """Der zweite Riegel, fuer sich allein geprueft.

        Der Zustand wird hier von Hand hergestellt - ueber die
        Schnittstelle kann er nicht entstehen, weil das Loeschen die
        Markierung mitnimmt. Genau darum braucht es ihn: was oeffentlich
        ist, haengt nicht an einer einzigen Stelle.
        """
        self.aufraeumen()
        kennung = self.start_ablegen("Heimlich geloescht")
        self.js("/api/startseite", daten={"kennung": kennung})
        with self.db() as con:
            con.execute("UPDATE seite SET geloescht=1 WHERE kennung=?",
                        (kennung,))
            con.commit()
        code, roh, kopf = self.ruf("/", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertIn("Hier liegt nichts offen herum", roh.decode())
        self.assertNotIn(b"Kennwort Sonnenblume", roh)
        # Und die Suchmaschinen bleiben damit auch wieder draussen.
        self.assertIn("noindex", kopf.get("X-Robots-Tag", ""))
        code, roh, _ = self.ruf("/robots.txt", nutzer="", gruppen="")
        self.assertEqual(roh.decode(), "User-agent: *\nDisallow: /\n")
        with self.db() as con:
            con.execute("DELETE FROM einstellung WHERE schluessel='startseite'")
            con.commit()

    def test_eine_datei_die_verschwunden_ist_ergibt_das_schild(self):
        """Nicht 500. Der Besucher kann daran nichts aendern (§12)."""
        kennung = self.start_ablegen("Datei weg")
        self.js("/api/startseite", daten={"kennung": kennung})
        os.remove(os.path.join(self.ordner, "seiten", kennung + ".html"))
        code, roh, _ = self.ruf("/", nutzer="", gruppen="")
        self.assertEqual(code, 200)
        self.assertIn("Hier liegt nichts offen herum", roh.decode())
        self.aufraeumen()
