"""Die mitgelieferten Seiten muessen die eigenen Regeln erfuellen.

Das Wiki prueft jede eingespielte Seite (regeln_pruefen, sicherheit_pruefen).
Genau diese Pruefung laeuft hier gegen die Seiten, die im Repository liegen -
test-seite.html und alles unter vorlagen/. Sonst faellt erst beim Einspielen
auf, dass die Vorlage selbst gegen die Regel verstoesst, die sie vorfuehren
soll.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import glob
import json
import os
import re
import unittest

from hilfe import server

WIKI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def seiten():
    p = [os.path.join(WIKI, "test-seite.html")]
    p += sorted(glob.glob(os.path.join(WIKI, "vorlagen", "*.html")))
    return [x for x in p if os.path.exists(x)]


class MitgelieferteSeiten(unittest.TestCase):
    def test_es_gibt_seiten_zu_pruefen(self):
        # Ohne das waere ein leerer Ordner ein gruener Test.
        self.assertGreaterEqual(len(seiten()), 2, "keine Seiten gefunden")

    def test_jede_seite_erfuellt_die_regeln(self):
        for pfad in seiten():
            with self.subTest(seite=os.path.basename(pfad)):
                html = lies(pfad)
                meta, spanne = server.meta_block_lesen(html)
                self.assertIsNotNone(meta, "kein lesbarer Meta-Block")
                fehler, warnungen = server.regeln_pruefen(html, meta)
                self.assertEqual(fehler, [], "Fehler: %s" % fehler)
                self.assertEqual(warnungen, [], "Warnungen: %s" % warnungen)

    def test_jeder_anker_hat_ein_element(self):
        for pfad in seiten():
            with self.subTest(seite=os.path.basename(pfad)):
                html = lies(pfad)
                meta, _ = server.meta_block_lesen(html)
                for a in meta.get("abschnitte", []):
                    self.assertRegex(
                        html, r'id=["\']%s["\']' % re.escape(a["anker"]),
                        "zum Anker %r fehlt das Element" % a["anker"])

    def test_pflichtteil_ist_vorhanden_und_korrigiert(self):
        """N-06 und N-07: die Vorlage darf die Fehler nicht weitertragen."""
        for pfad in seiten():
            with self.subTest(seite=os.path.basename(pfad)):
                html = lies(pfad)
                self.assertIn("wiki-springen", html,
                              "ohne Pflichtteil springt kein Suchtreffer")
                self.assertIn("e.source !== window.parent", html,
                              "die Seite nimmt Nachrichten von jedem an")
                self.assertIn("prefers-color-scheme", html,
                              "N-06: ohne das blitzt die dunkle Fassung auf")
                self.assertIn("FILTER_REJECT", html,
                              "N-07: der Textdurchlauf laeuft durch Skripte")
                self.assertIn("wiki-text", html,
                              "N-11: die Seite meldet nicht, was sie anzeigt - "
                              "dann findet die Suche nur das rohe HTML")

    def test_keine_externen_verweise(self):
        for pfad in seiten():
            with self.subTest(seite=os.path.basename(pfad)):
                html = lies(pfad)
                extern = re.findall(
                    r'(?i)(?:src|href)=["\'](\s*(?:https?:)?//[^"\']+'
                    r'|javascript:[^"\']*)["\']', html)
                self.assertEqual(extern, [], "externer Verweis: %s" % extern)


class EditorSeitenSindRundlauffaehig(unittest.TestCase):
    """Eine Seite aus dem Editor muss sich wieder aufklappen lassen."""

    def test_vorlagen_mit_werkzeugmarke_haben_markup(self):
        for pfad in seiten():
            html = lies(pfad)
            meta, _ = server.meta_block_lesen(html)
            if not meta or meta.get("werkzeug") != "editor-1":
                continue
            with self.subTest(seite=os.path.basename(pfad)):
                for a in meta["abschnitte"]:
                    self.assertIn("markup", a,
                                  "ohne markup ist die Seite nicht editierbar")


class PruefungFaengtDasOffensichtliche(unittest.TestCase):
    """Gegenprobe: die Pruefung selbst muss Zaehne haben."""

    VORLAGE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script type="application/json" id="wiki-meta">%s</script>
<style>:focus-visible{outline:2px solid #000} @media (prefers-reduced-motion:reduce){*{transition:none}}</style>
</head><body><section id="a"><h2>A</h2>
<p>Ein Absatz mit genug Text, damit die Seite eine Seite ist und nicht nur ein
Meta-Block mit leerem Koerper (N-23).</p></section></body></html>"""

    def bauen(self, **aender):
        meta = {"slug": "probe", "titel": "Probe", "pfad": ["Technik"],
                "gruppen": [], "stand": "2026-09-15",
                "abschnitte": [{"anker": "a", "titel": "A", "text": "Text"}]}
        meta.update(aender)
        html = self.VORLAGE % json.dumps(meta)
        return server.regeln_pruefen(html, meta)

    def test_gute_seite_ohne_fehler(self):
        fehler, _ = self.bauen()
        self.assertEqual(fehler, [])

    def test_fehlender_slug_ist_ein_fehler(self):
        fehler, _ = self.bauen(slug="")
        self.assertTrue(fehler)

    def test_ungueltiger_slug_ist_ein_fehler(self):
        fehler, _ = self.bauen(slug="Gross Und Leer")
        self.assertTrue(fehler)

    def test_doppelter_anker_ist_ein_fehler(self):
        fehler, _ = self.bauen(abschnitte=[
            {"anker": "a", "titel": "A", "text": "x"},
            {"anker": "a", "titel": "B", "text": "y"}])
        self.assertTrue(any("mehrfach" in f for f in fehler))

    def test_zu_langer_titel_ist_ein_fehler(self):
        """N-20, CLAUDE.md §11: Text auf sinnvolle Laenge begrenzt.

        Gemessen: ein Titel von 376 Zeichen liess den Kopf der Anwendung am
        Handy auf 523 Pixel wachsen - zwei Drittel des Schirms.
        """
        fehler, _ = self.bauen(titel="Ein " + "wirklich " * 40 + "langer Titel")
        self.assertTrue(any("Zeichen lang" in f for f in fehler), fehler)

    def test_titel_an_der_grenze_geht_durch(self):
        # Genau 120 Zeichen: erlaubt. Die Grenze selbst darf nicht stolpern.
        fehler, _ = self.bauen(titel="T" * 120)
        self.assertEqual(fehler, [])
        fehler, _ = self.bauen(titel="T" * 121)
        self.assertTrue(fehler)

    def test_zu_langer_satz_ist_ein_fehler(self):
        fehler, _ = self.bauen(kurz="Und " + "ein langer Satz, " * 30 + "Ende.")
        self.assertTrue(any("Satz unter dem Titel" in f for f in fehler), fehler)

    def test_zu_lange_pfadebene_ist_ein_fehler(self):
        fehler, _ = self.bauen(pfad=["Technik", "X" * 61])
        self.assertTrue(any("Pfadebene" in f for f in fehler), fehler)

    def test_zu_langer_abschnittstitel_ist_ein_fehler(self):
        fehler, _ = self.bauen(abschnitte=[
            {"anker": "a", "titel": "A" * 121, "text": "x"}])
        self.assertTrue(any("Abschnitt" in f and "Zeichen" in f for f in fehler), fehler)

    def test_zu_langes_stichwort_ist_ein_fehler(self):
        fehler, _ = self.bauen(abschnitte=[
            {"anker": "a", "titel": "A", "text": "x", "stichworte": ["S" * 61]}])
        self.assertTrue(any("Stichwort" in f for f in fehler), fehler)

    def test_anker_ohne_element_ist_eine_warnung(self):
        fehler, warnungen = self.bauen(abschnitte=[
            {"anker": "fehlt-im-html", "titel": "A", "text": "x"}])
        self.assertEqual(fehler, [])
        self.assertTrue(any("fehlt-im-html" in w for w in warnungen))


class EineSeiteMussSichtbarenInhaltHaben(unittest.TestCase):
    """N-23: Ein voller Meta-Block mit leerem <body> ging fehlerfrei durch.

    Die Seite landete im Themenbaum, die Suche fand ihre Abschnitte, und der
    Leser bekam eine weisse Flaeche. Gemessen wurde das an einer Datei mit
    3703 Byte und 0 Zeichen sichtbarem Text.
    """

    META = {"slug": "probe", "titel": "Probe", "pfad": ["Technik"],
            "gruppen": [], "stand": "2026-09-17",
            "abschnitte": [{"anker": "a", "titel": "A", "text": "Text"}]}

    def bauen(self, koerper):
        html = ('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">'
                '<script type="application/json" id="wiki-meta">'
                + json.dumps(self.META) + '</script></head><body>'
                + koerper + '</body></html>')
        return server.regeln_pruefen(html, dict(self.META))

    def test_leerer_koerper_ist_ein_fehler(self):
        fehler, _ = self.bauen("\n")
        self.assertTrue(any("sichtbarer Text" in f for f in fehler), fehler)
        self.assertTrue(any("(0 Zeichen)" in f for f in fehler), fehler)

    def test_der_hinweis_nennt_den_weg_ueber_den_editor(self):
        # Wer eine solche Datei einspielt, hat meist einen Entwurf in der
        # Hand. Die Absage muss sagen, was dann zu tun ist.
        fehler, _ = self.bauen("")
        self.assertTrue(any("in den Editor" in f for f in fehler), fehler)

    def test_neununddreissig_zeichen_sind_zu_wenig(self):
        # Die Grenze steht bei 40. 39 Zeichen liegen darunter - von Hand
        # gezaehlt, indem genau 39 Zeichen gesetzt werden.
        fehler, _ = self.bauen("<p>" + "x" * 39 + "</p>")
        self.assertTrue(any("(39 Zeichen)" in f for f in fehler), fehler)

    def test_vierzig_zeichen_reichen(self):
        fehler, _ = self.bauen("<p>" + "x" * 40 + "</p>")
        self.assertEqual(
            [f for f in fehler if "sichtbarer Text" in f], [],
            "40 Zeichen sind die Grenze und muessen durchgehen")

    def test_marken_und_kommentare_sind_kein_inhalt(self):
        # Ein Koerper voller Auszeichnung ohne ein Wort Text ist leer.
        fehler, _ = self.bauen(
            '<div class="a"><span></span><!-- ein langer Kommentar, der '
            'nach Inhalt aussieht, aber keiner ist --></div>')
        self.assertTrue(any("sichtbarer Text" in f for f in fehler), fehler)

    def test_eine_seite_die_sich_selbst_baut_wird_nicht_beanstandet(self):
        # Seiten, deren Inhalt erst im Browser entsteht, sind erlaubt
        # (N-11). Lieber keine Beanstandung als eine falsche.
        fehler, _ = self.bauen(
            '<div id="ziel"></div><script>'
            'document.getElementById("ziel").textContent = "erst hier";'
            '</script>')
        self.assertEqual([f for f in fehler if "sichtbarer Text" in f], [],
                         "eine Seite mit eigenem Aufbaucode wurde beanstandet")

    def test_der_meta_block_selbst_zaehlt_nicht_als_aufbaucode(self):
        # Sonst wuerde die Ausnahme jede Datei decken - der Meta-Block ist
        # in jeder drin.
        fehler, _ = self.bauen(
            '<script type="application/json" id="noch-einer">{"a":1}</script>')
        self.assertTrue(any("sichtbarer Text" in f for f in fehler), fehler)

    def test_ein_anhang_zaehlt_nicht_als_aufbaucode(self):
        # Ein PDF liegt als <script type="text/plain"> in der Seite. Das ist
        # eine Datei, kein Code.
        fehler, _ = self.bauen(
            '<script type="text/plain" id="anhang-x" data-wiki-anhang="">'
            'JVBERi0xLjQK</script>')
        self.assertTrue(any("sichtbarer Text" in f for f in fehler), fehler)

    def test_ohne_body_wird_die_ganze_datei_angesehen(self):
        # Eine Datei ohne <body> darf nicht durchgewinkt werden, nur weil das
        # Muster nicht greift.
        html = ('<script type="application/json" id="wiki-meta">'
                + json.dumps(self.META) + '</script>')
        fehler, _ = server.regeln_pruefen(html, dict(self.META))
        self.assertTrue(any("sichtbarer Text" in f for f in fehler), fehler)


class PflichtteilWirdErkannt(unittest.TestCase):
    """N-40: Der Pflichtteil ist kein Code, den die Seite mitbringt.

    Vor N-40 meldete die Hinweiskarte bei JEDER Seite aus dem Editor
    "1 Skriptblock mit 12534 Zeichen" und "parent. - die Seite greift nach
    der Huelle" - gemessen an allen sechs mitgelieferten Seiten dieselbe Zahl,
    Zeichen fuer Zeichen. Eine Warnung, die immer angeht, wird nicht gelesen.

    Die Erkennung darf aber nicht zur Entwarnung werden: sie gilt nur bei
    EXAKTER Uebereinstimmung. Darum steht hier zu jedem "erkannt" auch ein
    Fall, in dem etwas nicht stimmt.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = lies(os.path.join(WIKI, "vorlagen", "drucker-einrichten.html"))

    def test_der_fingerabdruck_ist_lesbar(self):
        # Ohne ihn ist jeder weitere Test dieser Klasse gruen aus dem
        # falschen Grund: dann wird eben nichts erkannt.
        self.assertIsNotNone(server.pflichtteil_kennung(),
                             "ED_PFLICHTTEIL_KENNUNG fehlt in index.html")

    def test_eine_seite_aus_dem_editor_meldet_nichts(self):
        self.assertEqual(server.sicherheit_pruefen(self.html), [])

    def test_alle_mitgelieferten_seiten_melden_keinen_pflichtteil(self):
        # "parent." darf in KEINER mitgelieferten Seite mehr auftauchen -
        # sonst ist der Pflichtteil dort nicht nachgezogen.
        for pfad in seiten():
            with self.subTest(seite=os.path.basename(pfad)):
                hinweise = server.sicherheit_pruefen(lies(pfad))
                self.assertFalse([h for h in hinweise if "parent." in h],
                                 "Pflichtteil nicht erkannt: %s" % hinweise)

    def test_ein_einziges_zeichen_mehr_faellt_auf(self):
        # Die Probe mit den Zaehnen (CLAUDE.md §13a): ein Leerzeichen.
        anders = self.html.replace("if(window.parent !== window)",
                                   "if(window.parent !== window) ", 1)
        self.assertNotEqual(anders, self.html, "Mutation griff nicht")
        hinweise = server.sicherheit_pruefen(anders)
        self.assertTrue(any("nicht der dieser Huelle" in h for h in hinweise),
                        hinweise)
        self.assertTrue(any("Skriptblock" in h for h in hinweise), hinweise)

    def test_etwas_im_pflichtteil_versteckt_wird_gemeldet(self):
        # Das Loch, das eine Erkennung nach blossem Kommentar haette: 12 kB
        # fremder Code unter der Marke des Pflichtteils.
        anders = self.html.replace("(function(){",
                                   "(function(){\n  fetch('//fremd.tld/x');", 1)
        self.assertNotEqual(anders, self.html, "Mutation griff nicht")
        hinweise = server.sicherheit_pruefen(anders)
        self.assertTrue(any("nicht der dieser Huelle" in h for h in hinweise),
                        hinweise)
        self.assertTrue(any("fetch(" in h for h in hinweise), hinweise)

    def test_eigener_block_neben_dem_pflichtteil_wird_gemeldet(self):
        anders = self.html.replace(
            "</body>",
            "<script>localStorage.setItem('x',1)</script>\n</body>", 1)
        self.assertNotEqual(anders, self.html, "Mutation griff nicht")
        hinweise = server.sicherheit_pruefen(anders)
        # Von Hand gezaehlt: localStorage.setItem('x',1) sind 27 Zeichen -
        # der Block ist genau sein Inhalt, ohne die Tags.
        self.assertTrue(any("1 Skriptblock(e) mit zusammen 27 Zeichen" in h
                            for h in hinweise), hinweise)
        self.assertTrue(any("localStorage" in h for h in hinweise), hinweise)

    def test_ohne_fingerabdruck_wird_gemeldet_wie_vorher(self):
        # Keine stille Entwarnung (CLAUDE.md §11): ist der Abdruck nicht
        # feststellbar, gilt der Pflichtteil wieder als Code der Seite.
        vorher = list(server._pflichtteil_kennung)
        try:
            server._pflichtteil_kennung[:] = [None]
            hinweise = server.sicherheit_pruefen(self.html)
            self.assertTrue(any("Skriptblock" in h for h in hinweise), hinweise)
            self.assertTrue(any("parent." in h for h in hinweise), hinweise)
        finally:
            server._pflichtteil_kennung[:] = vorher


if __name__ == "__main__":
    unittest.main()
