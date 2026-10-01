"""Die Admin-Seite: wer hinein darf, was sie ablegt, was sie zeigt.

Startet den echten Dienst im Testprozess und spricht HTTP mit ihm - so, wie
Traefik es tut (die Anmelde-Kopfzeilen setzt sonst Authentik).
"""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
sys.dont_write_bytecode = True

TMP = tempfile.mkdtemp(prefix="prolo-admin-test-")
os.environ.update(ADMIN_DATEN=os.path.join(TMP, "daten"), ADMIN_AGENT=os.path.join(TMP, "agent"),
                  ADMIN_GRUPPE="authentik Admins", PROLO_DOMAIN="prolo.test",
                  PROLO_VERSION="9.9.9")
sys.path.insert(0, os.path.join(REPO, "admin"))
import server  # noqa: E402

EIN = os.path.join(TMP, "agent", "ein")
AUS = os.path.join(TMP, "agent", "aus")
ADMIN = {"X-Authentik-Username": "akadmin", "X-Authentik-Groups": "andere|authentik Admins",
         "X-Authentik-Name": "Prolo", "Host": "admin.prolo.test"}
GLEICH = dict(ADMIN, Origin="https://admin.prolo.test")


class AdminTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(EIN)
        os.makedirs(AUS)
        server.datenbank_anlegen()
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        for d in (EIN, AUS):
            for n in os.listdir(d):
                os.remove(os.path.join(d, n))

    def frage(self, pfad, kopf=None, daten=None):
        v = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=10)
        koerper = urllib.parse.urlencode(daten).encode() if daten is not None else None
        k = dict(kopf or {})
        if koerper is not None:
            k["Content-Type"] = "application/x-www-form-urlencoded"
        v.request("POST" if koerper is not None else "GET", pfad, body=koerper, headers=k)
        r = v.getresponse()
        text = r.read().decode("utf-8", "replace")
        v.close()
        return r.status, r.getheader("Location"), text

    def status(self, **mehr):
        s = {"zeit": "2026-10-01T03:31:00+02:00", "agent": {"zeit": server.datetime.datetime.now()
                                                            .astimezone().isoformat()},
             "version": "2.0.0", "domain": "prolo.test",
             "unterbau": [{"dienst": "traefik", "zustand": "gesund"}],
             "tools": [{"name": "uptime", "zustand": "gesund", "url": "https://uptime.prolo.test",
                        "host": "uptime.prolo.test", "anmeldung": "authentik",
                        "herkunft": "<script>alert(1)</script>", "dienste": [], "volumes": []}],
             "sicherung": {"staende": []}, "git": {"commit": "abc1234"}, "hinweise": []}
        s.update(mehr)
        with open(os.path.join(AUS, "status.json"), "w") as f:
            json.dump(s, f)

    def eingang(self):
        return sorted(os.listdir(EIN))

    # --- Wer darf hinein
    def test_gesundheit_ohne_anmeldung(self):
        self.assertEqual(self.frage("/gesundheit")[0], 200)

    def test_ohne_anmeldung_abgewiesen(self):
        self.assertEqual(self.frage("/")[0], 401)
        self.assertEqual(self.frage("/tools", {"X-Authentik-Groups": "authentik Admins"})[0], 401)

    def test_ohne_gruppe_abgewiesen(self):
        k = dict(ADMIN, **{"X-Authentik-Groups": "andere|authentik Admins2"})
        st, _, text = self.frage("/", k)
        self.assertEqual(st, 403)
        self.assertIn("authentik Admins", text)

    def test_mit_gruppe_hinein(self):
        self.status()
        st, _, text = self.frage("/", ADMIN)
        self.assertEqual(st, 200)
        self.assertIn("uptime", text)
        self.assertNotIn("Noch kein Stand", text)

    # --- Was gezeigt wird
    def test_ohne_status_ein_hinweis(self):
        st, _, text = self.frage("/", ADMIN)
        self.assertEqual(st, 200)
        self.assertIn("Noch kein Stand vom Server", text)
        self.assertIn("prolo einrichten", text)

    def test_alter_status_wird_gesagt(self):
        self.status(agent={"zeit": "2026-01-01T00:00:00+00:00"})
        self.assertIn("antwortet nicht", self.frage("/", ADMIN)[2])

    def test_werte_werden_maskiert(self):
        self.status()
        st, _, text = self.frage("/tools", ADMIN)
        self.assertEqual(st, 200)
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;", text)

    def test_unbekanntes_tool_404(self):
        self.status()
        self.assertEqual(self.frage("/tool/gibtsnicht", ADMIN)[0], 404)
        self.assertEqual(self.frage("/tool/uptime", ADMIN)[0], 200)

    def test_schriften_nur_schriften(self):
        self.assertEqual(self.frage("/schriften/sora-latin.woff2")[0], 200)
        for p in ("/schriften/../server.py", "/schriften/HINWEIS.md", "/schriften/%2e%2e%2fserver.py"):
            self.assertEqual(self.frage(p)[0], 404, p)

    # --- Was abgelegt wird
    def test_auftrag_wird_abgelegt(self):
        st, ziel, _ = self.frage("/auftrag", GLEICH, {"art": "tool_restart", "name": "uptime",
                                                      "unsinn": "x"})
        self.assertEqual(st, 303)
        [datei] = self.eingang()
        self.assertEqual(ziel, "/auftrag/" + datei[:-5])
        with open(os.path.join(EIN, datei)) as f:
            d = json.load(f)
        self.assertEqual((d["art"], d["felder"], d["wer"]),
                         ("tool_restart", {"name": "uptime"}, "akadmin"))
        # Die Seite des Auftrags zeigt ihn als wartend
        st, _, text = self.frage(ziel, ADMIN)
        self.assertEqual(st, 200)
        self.assertIn("wartet", text)

    def test_fremde_seite_darf_nicht_absenden(self):
        for kopf in (ADMIN, dict(ADMIN, Origin="https://boese.example")):
            st, _, _ = self.frage("/auftrag", kopf, {"art": "sichern"})
            self.assertEqual(st, 403)
        self.assertEqual(self.eingang(), [])
        st, _, _ = self.frage("/auftrag", dict(ADMIN, **{"Sec-Fetch-Site": "same-origin"}),
                              {"art": "sichern"})
        self.assertEqual(st, 303)

    def test_ungueltiges_wird_nicht_abgelegt(self):
        for daten in ({"art": "rm_rf"}, {"art": "tool_rm", "name": "../etc"},
                      {"art": "tool_rm", "name": "admin"}):
            st, _, _ = self.frage("/auftrag", GLEICH, daten)
            self.assertEqual(st, 400, daten)
        self.assertEqual(self.eingang(), [])

    def test_tool_aus_compose(self):
        compose = "services:\n  web:\n    image: nginx:1\n"
        st, _, _ = self.frage("/tools/neu", GLEICH, {"name": "web", "quelle": "compose",
                                                     "compose": compose, "abbild": "egal:1",
                                                     "anmeldung": "authentik", "env": "A=1"})
        self.assertEqual(st, 303)
        [datei] = self.eingang()
        with open(os.path.join(EIN, datei)) as f:
            d = json.load(f)
        self.assertEqual(d["felder"]["compose"], compose)     # Einrueckung erhalten
        self.assertNotIn("abbild", d["felder"])               # nur die gewaehlte Quelle
        self.assertEqual(d["felder"]["env"], "A=1")

    def test_fehler_im_formular_bleibt_stehen(self):
        st, _, text = self.frage("/tools/neu", GLEICH, {"name": "Falsch!", "quelle": "abbild",
                                                        "abbild": "nginx:1"})
        self.assertEqual(st, 400)
        self.assertIn("Kleinbuchstaben", text)
        self.assertIn('value="nginx:1"', text)                 # Eingabe geht nicht verloren
        self.assertEqual(self.eingang(), [])

    def test_darstellung_wird_gespeichert(self):
        st, ziel, _ = self.frage("/einstellungen/thema", GLEICH, {"thema": "hell"})
        self.assertEqual(st, 303)
        _, _, text = self.frage("/einstellungen", ADMIN)
        self.assertIn('var w = "hell"', text)
        self.assertEqual(self.frage("/einstellungen/thema", GLEICH, {"thema": "lila"})[0], 400)

    def test_auftrag_ergebnis(self):
        k = "20261001-120000-abcdef01"
        with open(os.path.join(AUS, k + ".json"), "w") as f:
            json.dump({"kennung": k, "art": "tool_add", "status": "fehler", "titel": "Tool installieren",
                       "felder": {"name": "web"}}, f)
        with open(os.path.join(AUS, k + ".log"), "w") as f:
            f.write("FEHLER  <b>kaputt</b>\n")
        st, _, text = self.frage("/auftrag/" + k, ADMIN)
        self.assertEqual(st, 200)
        self.assertIn("fehlgeschlagen", text)
        self.assertIn("&lt;b&gt;kaputt", text)
        self.assertEqual(self.frage("/auftrag/../../etc/passwd", ADMIN)[0], 404)


if __name__ == "__main__":
    unittest.main()
