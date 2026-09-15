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
</head><body><section id="a"><h2>A</h2><p>Text</p></section></body></html>"""

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

    def test_anker_ohne_element_ist_eine_warnung(self):
        fehler, warnungen = self.bauen(abschnitte=[
            {"anker": "fehlt-im-html", "titel": "A", "text": "x"}])
        self.assertEqual(fehler, [])
        self.assertTrue(any("fehlt-im-html" in w for w in warnungen))


if __name__ == "__main__":
    unittest.main()
