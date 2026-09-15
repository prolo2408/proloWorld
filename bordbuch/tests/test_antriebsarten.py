"""Verbrauchsangaben passend zur Antriebsart (N-08).

Der Befund: Der Einrichtungs-Assistent konnte drei von vier Antriebsarten
nicht anlegen. Die Oberflaeche schickt fuer die Groesse, die es bei dieser
Art nicht gibt, eine 0 - und die 0 fiel in die Plausibilitaetspruefung
(0,5 bis 60 l/100 km, 1 bis 100 kWh/100 km). Ein neuer Benutzer sass damit
im Assistenten fest, weil ohne Auto kein Weg daran vorbeifuehrt.

Erwartungswerte von Hand, wie Regelblatt 13 es verlangt: 18,0 kWh/100 km und
7,0 l/100 km sind die Vorgaben des Programms, 0 steht fuer "gibt es hier
nicht".
"""
import unittest

from hilfe import server

verbrauchswerte = server.verbrauchswerte


class ArtBestimmtWasGeprueftWird(unittest.TestCase):
    """Genau die Aufrufe, die der Assistent macht - vier Arten, vier Male."""

    def test_elektro_ohne_liter(self):
        # Assistent: kwhPer100 aus dem Feld, lPer100 zwangsweise 0.
        kwh, lit, fehler = verbrauchswerte("bev", {"kwhPer100": 18, "lPer100": 0})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 18.0)
        self.assertEqual(lit, 0.0)

    def test_benziner_ohne_kilowattstunden(self):
        kwh, lit, fehler = verbrauchswerte("petrol", {"kwhPer100": 0, "lPer100": 7})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 0.0)
        self.assertEqual(lit, 7.0)

    def test_diesel_ohne_kilowattstunden(self):
        kwh, lit, fehler = verbrauchswerte("diesel", {"kwhPer100": 0, "lPer100": 5.5})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 0.0)
        self.assertEqual(lit, 5.5)

    def test_hybrid_hat_beides(self):
        kwh, lit, fehler = verbrauchswerte("phev", {"kwhPer100": 20, "lPer100": 6})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 20.0)
        self.assertEqual(lit, 6.0)


class TippfehlerFallenWeiterAuf(unittest.TestCase):
    """Die Gegenprobe: die Pruefung darf nicht einfach abgeschaltet sein."""

    def test_unmoeglicher_stromverbrauch(self):
        kwh, lit, fehler = verbrauchswerte("bev", {"kwhPer100": 999, "lPer100": 0})
        self.assertIsNotNone(fehler)
        self.assertIn("999", fehler)
        self.assertIsNone(kwh)

    def test_unmoeglicher_spritverbrauch(self):
        kwh, lit, fehler = verbrauchswerte("petrol", {"kwhPer100": 0, "lPer100": 999})
        self.assertIsNotNone(fehler)
        self.assertIn("999", fehler)

    def test_keine_zahl(self):
        kwh, lit, fehler = verbrauchswerte("bev", {"kwhPer100": "abc"})
        self.assertIsNotNone(fehler)
        self.assertIn("keine Zahl", fehler)

    def test_null_bei_der_eigenen_groesse_bleibt_ein_fehler(self):
        # Ein Elektroauto mit 0 kWh/100 km ist ein Tippfehler - die 0 wird
        # nur bei der Groesse durchgelassen, die es bei der Art nicht gibt.
        kwh, lit, fehler = verbrauchswerte("bev", {"kwhPer100": 0, "lPer100": 0})
        self.assertIsNotNone(fehler)
        self.assertIn("kWh/100 km", fehler)

    def test_benziner_mit_null_litern_bleibt_ein_fehler(self):
        kwh, lit, fehler = verbrauchswerte("petrol", {"kwhPer100": 0, "lPer100": 0})
        self.assertIsNotNone(fehler)
        self.assertIn("l/100 km", fehler)


class FehlendeAngabeBekommtDieVorgabe(unittest.TestCase):
    """Fehlt das Feld ganz, gilt die Vorgabe - aber nur fuer die eigene Art."""

    def test_elektro_ohne_angabe(self):
        kwh, lit, fehler = verbrauchswerte("bev", {})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 18.0)   # Vorgabe des Programms
        self.assertEqual(lit, 0.0)    # gibt es bei Elektro nicht

    def test_benziner_ohne_angabe(self):
        kwh, lit, fehler = verbrauchswerte("petrol", {})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 0.0)
        self.assertEqual(lit, 7.0)

    def test_leerer_text_gilt_als_fehlend(self):
        kwh, lit, fehler = verbrauchswerte("bev", {"kwhPer100": "  "})
        self.assertIsNone(fehler)
        self.assertEqual(kwh, 18.0)


class MengenPassenZuDenKinds(unittest.TestCase):
    """LAEDT und TANKT muessen zu KINDS in index.html passen."""

    def test_vier_arten_vollstaendig(self):
        alle = {"bev", "phev", "petrol", "diesel"}
        self.assertEqual(server.LAEDT | server.TANKT, alle)
        self.assertEqual(server.LAEDT, {"bev", "phev"})
        self.assertEqual(server.TANKT, {"phev", "petrol", "diesel"})

    def test_jede_art_hat_mindestens_eine_groesse(self):
        for art in ("bev", "phev", "petrol", "diesel"):
            with self.subTest(art=art):
                self.assertTrue(art in server.LAEDT or art in server.TANKT)


if __name__ == "__main__":
    unittest.main()
