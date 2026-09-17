"""Was die Suche finden muss (Seitenkopf im Index).

Der Befund aus der Messung: Eine Seite war nur ueber ihren INHALT zu finden,
nicht ueber das, was sie beschreibt. Sechs von 22 Begriffen fehlten - "Haushalt"
und "Energie" (nur im Pfad), "hingeht" (nur im Satz der Seite), "Grundlagen"
und "Adressierung" (nur als Gruppe im Inhaltsverzeichnis). Genau die Woerter,
mit denen ein Mensch anfaengt, wenn er den Titel nicht mehr weiss.

Hier laeuft der echte Indexaufbau gegen eine kleine Datenbank, und danach die
echte Suche. Erwartungen von Hand (Regelblatt 13).
"""
import json
import os
import shutil
import tempfile
import unittest

from hilfe import server


class SucheMitSeitenkopf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Eine eigene Datenbank je Testlauf - sonst sehen sich die Tests."""
        cls.ordner = tempfile.mkdtemp(prefix="wiki-suche-")
        server.DATEN = os.path.join(cls.ordner, "daten")
        server.SEITEN = os.path.join(cls.ordner, "seiten")
        server.DB_DATEI = os.path.join(server.DATEN, "wiki.db")
        os.makedirs(server.DATEN, exist_ok=True)
        os.makedirs(server.SEITEN, exist_ok=True)
        server.db_freigeben()
        server.datenbank_anlegen()

        cls.nutzer = server.Nutzer("artur", "Artur", "", ["wiki-admin"])
        cls.seite_anlegen(
            "stromkosten-verstehen", "Stromkosten verstehen",
            "Was eine Kilowattstunde ist, was sie kostet, und wo sie hingeht.",
            ["Haushalt", "Energie"],
            [("kwh", "Was eine Kilowattstunde ist", "Grundlagen", "kWh, Watt",
              "Eine Kilowattstunde ist 1000 Watt fuer eine Stunde."),
             ("rechnen", "Selbst nachrechnen", "Rechnen", "Jahreskosten",
              "Ein Geraet mit 80 Watt sechs Stunden am Tag.")])
        cls.seite_anlegen(
            "netzwerk-grundlagen", "Netzwerk-Grundlagen",
            "Schichten, Adressen, Ports.", ["Technik", "Netzwerke"],
            [("schichten", "Schichten und Kapselung", "Grundlagen", "OSI",
              "Jede Schicht loest eine Aufgabe."),
             ("adressen", "IP-Adressen und Subnetze", "Adressierung", "CIDR",
              "Die Subnetzmaske trennt Netzanteil und Hostanteil.")])

    @classmethod
    def tearDownClass(cls):
        server.db_freigeben()
        shutil.rmtree(cls.ordner, ignore_errors=True)

    @classmethod
    def seite_anlegen(cls, slug, titel, kurz, pfad, abschnitte):
        v = server.db()
        v.execute("INSERT INTO seite(slug,titel,kurz,pfad_json,gruppen_json,stand,"
                  "fassung,nutzer_id,urheber) VALUES(?,?,?,?,'[]','2026-09-17',1,"
                  "'artur','artur')",
                  (slug, titel, kurz, json.dumps(pfad, ensure_ascii=False)))
        sid = v.execute("SELECT id FROM seite WHERE slug=?", (slug,)).fetchone()["id"]
        for i, (anker, atitel, gruppe, stich, text) in enumerate(abschnitte):
            v.execute("INSERT INTO abschnitt(seite_id,anker,titel,ebene,stichworte,"
                      "text,gruppe,reihenfolge) VALUES(?,?,?,1,?,?,?,?)",
                      (sid, anker, atitel, stich, text, gruppe, i))
        v.commit()
        server.index_neu_bauen(sid, "<html><body><p>%s</p></body></html>" % kurz)

    def seiten(self, begriff):
        """Die Kennungen der Seiten, in der Reihenfolge der Treffer."""
        aus = []
        for t in server.suchen(self.nutzer, begriff):
            if t["slug"] not in aus:
                aus.append(t["slug"])
        return aus

    # ---------------------------------------------------- was vorher fehlte
    def test_wort_nur_im_satz_der_seite(self):
        # "hingeht" steht ausschliesslich in kurz.
        self.assertEqual(self.seiten("hingeht"), ["stromkosten-verstehen"])

    def test_wort_nur_im_pfad(self):
        self.assertEqual(self.seiten("Haushalt"), ["stromkosten-verstehen"])
        self.assertEqual(self.seiten("Energie"), ["stromkosten-verstehen"])

    def test_wort_nur_als_gruppe(self):
        """Die Gruppe muss an ZWEI Stellen im Index stehen.

        Die Mutationsprobe hat gezeigt, dass die Seite allein nichts beweist:
        Sie wird schon gefunden, wenn nur eine der beiden Quellen die Gruppe
        kennt. Gebraucht werden beide - der Kopftreffer fuehrt zur Seite, der
        Abschnittstreffer springt an die Stelle.
        """
        treffer = server.suchen(self.nutzer, "Adressierung")
        self.assertEqual(sorted({t["slug"] for t in treffer}), ["netzwerk-grundlagen"])
        arten = {t["art"] for t in treffer}
        self.assertIn("kopf", arten, "der Kopftreffer fehlt")
        self.assertIn("abschnitt", arten, "der Abschnittstreffer fehlt")
        anker = {t["anker"] for t in treffer if t["art"] == "abschnitt"}
        self.assertEqual(anker, {"adressen"},
                         "der Treffer springt nicht an den richtigen Abschnitt")

    def test_gruppe_auf_zwei_seiten(self):
        # "Grundlagen" ist auf beiden Seiten eine Gruppe - und zwar jeweils
        # als Kopf- UND als Abschnittstreffer.
        treffer = server.suchen(self.nutzer, "Grundlagen")
        self.assertEqual(sorted({t["slug"] for t in treffer}),
                         ["netzwerk-grundlagen", "stromkosten-verstehen"])
        paare = {(t["slug"], t["art"]) for t in treffer}
        for slug in ("netzwerk-grundlagen", "stromkosten-verstehen"):
            self.assertIn((slug, "kopf"), paare, slug + ": kein Kopftreffer")
            self.assertIn((slug, "abschnitt"), paare, slug + ": kein Abschnitt")

    def test_die_kennung_selbst_findet_die_seite(self):
        # Die Kennung steht nur im Kopftreffer - wer eine Adresse aus dem
        # Verlauf oder einem Verweis kennt, soll damit hinkommen.
        treffer = server.suchen(self.nutzer, "stromkosten-verstehen")
        self.assertEqual(sorted({t["slug"] for t in treffer}),
                         ["stromkosten-verstehen"])
        self.assertIn("kopf", {t["art"] for t in treffer})

    # ---------------------------------------------------- was vorher schon ging
    def test_titel(self):
        self.assertEqual(self.seiten("Stromkosten"), ["stromkosten-verstehen"])

    def test_abschnittstitel(self):
        self.assertEqual(self.seiten("Kapselung"), ["netzwerk-grundlagen"])

    def test_stichwort(self):
        self.assertEqual(self.seiten("Jahreskosten"), ["stromkosten-verstehen"])

    def test_text(self):
        self.assertEqual(self.seiten("Subnetzmaske"), ["netzwerk-grundlagen"])

    def test_wortanfang_genuegt(self):
        # "netz" muss "Netzwerk-Grundlagen" finden - sonst muss man das Wort
        # schon kennen, um es zu finden.
        self.assertIn("netzwerk-grundlagen", self.seiten("netz"))

    # ---------------------------------------------------- Gegenproben
    def test_was_nicht_vorkommt_wird_nicht_gefunden(self):
        self.assertEqual(self.seiten("Kernfusion"), [])

    def test_ein_buchstabe_gibt_nichts(self):
        # Sonst kaeme bei jedem Tastendruck die halbe Sammlung.
        self.assertEqual(server.suchen(self.nutzer, "a"), [])

    def test_der_kopftreffer_traegt_den_satz_als_schnipsel(self):
        treffer = [t for t in server.suchen(self.nutzer, "hingeht")
                   if t["art"] == "kopf"]
        self.assertTrue(treffer, "kein Kopftreffer")
        self.assertIn("hingeht", treffer[0]["schnipsel"])
        self.assertEqual(treffer[0]["titel"], "Stromkosten verstehen")

    def test_der_kopftreffer_zeigt_nicht_seinen_suchstoff(self):
        """Im Index stehen am Kopf auch Pfad, Gruppen und Abschnittstitel.

        Gefunden werden soll damit - gezeigt wird der Satz der Seite. Sonst
        liest der erste Treffer einer Seite wie eine Titelkette
        ("...und Kapselung Latenz und Durchsatz IP-Adressen und Subnetze"),
        und genau so sah es im Browser aus.
        """
        for begriff in ("Haushalt", "Grundlagen", "Stromkosten"):
            treffer = [t for t in server.suchen(self.nutzer, begriff)
                       if t["art"] == "kopf" and t["slug"] == "stromkosten-verstehen"]
            self.assertTrue(treffer, begriff + ": kein Kopftreffer")
            schnipsel = treffer[0]["schnipsel"]
            self.assertIn("Kilowattstunde", schnipsel,
                          begriff + ": der Satz der Seite fehlt")
            self.assertNotIn("Selbst nachrechnen", schnipsel,
                             begriff + ": da steht ein Abschnittstitel")
            self.assertNotIn("Haushalt Energie", schnipsel,
                             begriff + ": da steht der Pfad")

    def test_wer_die_gruppe_nicht_hat_findet_nichts(self):
        # Die Freigabe gilt auch fuer die Suche.
        v = server.db()
        v.execute("UPDATE seite SET gruppen_json='[\"wiki-chefs\"]' "
                  "WHERE slug='stromkosten-verstehen'")
        v.commit()
        try:
            fremd = server.Nutzer("lena", "Lena", "", ["wiki-technik"])
            self.assertEqual([t["slug"] for t in server.suchen(fremd, "hingeht")], [])
            self.assertEqual(self.seiten("hingeht"), ["stromkosten-verstehen"])
        finally:
            v.execute("UPDATE seite SET gruppen_json='[]' "
                      "WHERE slug='stromkosten-verstehen'")
            v.commit()


class PflichtteilGehoertNichtInDenIndex(unittest.TestCase):
    """N-28: Der Pflichtteil steht in jeder Seite - und stand im Index.

    Gemessen an fuenf eingespielten Seiten: "dark", "light", "prefers",
    "section", "details" und "warn" fanden jeweils ALLE fuenf. Sechs
    Woerter, die auf alles passen, sind das Gegenteil einer Suche.
    """

    PFLICHT = (
        "<script>\n"
        "/* Pflichtteil jeder Wiki-Seite: auf die Huelle hoeren. */\n"
        "(function(){\n"
        "  var a = '(prefers-color-scheme: dark)';\n"
        "  var b = 'warn bk-pdf-fehlt';\n"
        "  var c = 'Zu diesem Knopf liegt kein PDF bei';\n"
        "})();\n"
        "</script>")

    def test_der_pflichtteil_kommt_nicht_in_den_suchstoff(self):
        stoff = server.text_aus_skripten(
            "<html><body>" + self.PFLICHT + "</body></html>")
        self.assertEqual(stoff.strip(), "",
                         "aus dem Pflichtteil wurde Suchstoff: %r" % stoff)

    def test_ein_eigenes_skript_der_seite_kommt_weiter_hinein(self):
        # N-11: Seiten, die ihren Inhalt erst im Browser bauen, muessen
        # findbar bleiben. Sonst waere die Heilung schlimmer als das Leiden.
        stoff = server.text_aus_skripten(
            "<html><body>" + self.PFLICHT +
            "<script>var t = 'TCP verliert keine Daten, aber Zeit';</script>"
            "</body></html>")
        self.assertIn("TCP verliert keine Daten", stoff)
        self.assertNotIn("prefers", stoff)

    def test_ein_als_technik_markiertes_skript_wird_uebersprungen(self):
        stoff = server.text_aus_skripten(
            "<html><body><script data-wiki-technik>"
            "var a = 'prefers-color-scheme dark light';</script>"
            "<script>var b = 'Das gehoert zum Inhalt';</script></body></html>")
        self.assertIn("Das gehoert zum Inhalt", stoff)
        self.assertNotIn("dark light", stoff)

    def test_die_mitgelieferten_seiten_bringen_keinen_technikstoff_mit(self):
        # Die starke Probe: der ECHTE Pflichtteil, in den echten Seiten.
        import glob
        pfade = sorted(glob.glob(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "vorlagen", "*.html")))
        self.assertGreaterEqual(len(pfade), 3, "keine Seiten gefunden")
        for pfad in pfade:
            with self.subTest(seite=os.path.basename(pfad)):
                with open(pfad, encoding="utf-8") as f:
                    stoff = server.text_aus_skripten(f.read())
                for wort in ("prefers-color-scheme", "bk-pdf-fehlt",
                             "wiki-springen", "section[id]"):
                    self.assertNotIn(wort, stoff,
                                     "%s steht im Suchstoff" % wort)


if __name__ == "__main__":
    unittest.main()
