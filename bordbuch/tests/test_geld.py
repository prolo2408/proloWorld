"""Geldrechnung in Cent-Ganzzahlen (B-04).

CLAUDE.md §13 verlangt hier ausdruecklich VON HAND GERECHNETE Erwartungswerte.
Keiner der Werte unten ist aus der Ausgabe des Codes uebernommen - jeder ist
im Kommentar nachgerechnet. Pflichtfaelle je Berechnung: ein normaler Fall,
der Grenzfall (null, negativ, sehr gross), der Fall mit fehlenden Daten.
"""
import unittest
from decimal import Decimal

from hilfe import server

cent = server.cent
netto_ct = server.netto_ct
mwst_ct = server.mwst_ct


class SummenSindExakt(unittest.TestCase):
    def test_summe_bleibt_exakt(self):
        # Von Hand: 10 + 10 + 10 + 872 = 902 Cent = 9,02 EUR.
        # Genau dieser Fall ergab als REAL summiert 9.020000000000001.
        self.assertEqual(sum([10, 10, 10, 872]), 902)

    def test_dieselbe_summe_als_fliesskomma_ist_falsch(self):
        # Der Gegenbeweis, damit der Test zeigt WARUM es Cent sein muessen:
        # 0.10 + 0.10 + 0.10 + 8.72 ist in Fliesskomma nicht 9.02.
        self.assertNotEqual(0.10 + 0.10 + 0.10 + 8.72, 9.02)

    def test_viele_kleine_betraege(self):
        # Von Hand: 1000 mal 1 Cent sind genau 1000 Cent = 10,00 EUR.
        # In Fliesskomma driftet dieselbe Summe.
        self.assertEqual(sum([1] * 1000), 1000)


class CentEinlesen(unittest.TestCase):
    def test_normalfall(self):
        # Von Hand: 12,34 EUR = 1234 Cent.
        self.assertEqual(cent("12,34"), 1234)
        self.assertEqual(cent("12.34"), 1234)
        self.assertEqual(cent(12.34), 1234)

    def test_rundung_halbe_cent_aufwaerts(self):
        # Von Hand: 8,995 EUR -> kaufmaennisch 900 Cent, nicht 899.
        # Pythons round() wuerde hier zur geraden Zahl runden und 899 liefern.
        self.assertEqual(cent("8,995"), 900)

    def test_rundung_abwaerts(self):
        # Von Hand: 8,994 EUR -> 899 Cent.
        self.assertEqual(cent("8,994"), 899)

    def test_rundung_von_der_null_weg_nicht_zur_geraden_zahl(self):
        # Wichtig: dieser Fall trennt kaufmaennisches Runden (ROUND_HALF_UP)
        # von Pythons Standard (ROUND_HALF_EVEN, "zur geraden Zahl").
        #
        # 8,995 EUR taugt dafuer NICHT: das sind genau 899,5 Cent, und weil
        # 900 gerade ist, runden beide Verfahren auf 900. Die Gegenprobe hat
        # diese Luecke aufgedeckt.
        #
        # Von Hand: 8,985 EUR = 898,5 Cent.
        #   kaufmaennisch (von der Null weg) -> 899
        #   zur geraden Zahl (898 ist gerade) -> 898
        self.assertEqual(cent("8,985"), 899)
        # Von Hand: 1,005 EUR = 100,5 Cent -> 101, nicht 100.
        self.assertEqual(cent("1,005"), 101)
        # Von Hand: 2,665 EUR = 266,5 Cent -> 267, nicht 266.
        self.assertEqual(cent("2,665"), 267)

    def test_negativ_rundet_von_der_null_weg(self):
        # Von Hand: -8,985 EUR = -898,5 Cent -> -899.
        # Richtung plus unendlich waeren es -898 - dann wichen Server und
        # Oberflaeche bei Gutschriften voneinander ab.
        self.assertEqual(cent("-8,985"), -899)

    def test_null(self):
        # Grenzfall null: eine ausdrueckliche Null ist ein gueltiger Betrag.
        self.assertEqual(cent("0"), 0)
        self.assertEqual(cent(0), 0)

    def test_negativ(self):
        # Grenzfall negativ: -5,00 EUR = -500 Cent. Eine Gutschrift ist
        # fachlich moeglich, darum wird sie nicht hier abgewiesen, sondern
        # erst von den Plausibilitaetsgrenzen (B-05).
        self.assertEqual(cent("-5,00"), -500)

    def test_sehr_gross(self):
        # Von Hand: 1.284.500,55 EUR = 128 450 055 Cent.
        # Ganzzahlen haben in Python keine Obergrenze - kein Genauigkeitsverlust.
        self.assertEqual(cent("1284500.55"), 128450055)

    def test_keine_stille_null(self):
        # CLAUDE.md §11: fehlt ein Wert, wird das gemeldet - nicht durch eine
        # Null ersetzt. cent() liefert darum None, nicht 0.
        self.assertIsNone(cent("abc"))
        self.assertIsNone(cent("12,34,56"))
        self.assertIsNone(cent("NaN"))
        self.assertIsNone(cent("Infinity"))

    def test_fehlender_wert_gibt_vorgabe(self):
        # Ohne Wert kommt die ausdrueckliche Vorgabe zurueck - nur wer eine
        # angibt, bekommt eine.
        self.assertIsNone(cent(None))
        self.assertIsNone(cent(""))
        self.assertIsNone(cent("   "))
        self.assertEqual(cent(None, 0), 0)


class Mehrwertsteuer(unittest.TestCase):
    def test_mwst_19_prozent(self):
        # Von Hand: 4,99 EUR brutto bei 19 %.
        # 499 / 1,19 = 419,3277... -> kaufmaennisch 419 Cent netto.
        # MwSt = 499 - 419 = 80 Cent.
        self.assertEqual(netto_ct(499, Decimal("19")), 419)
        self.assertEqual(mwst_ct(499, Decimal("19")), 80)

    def test_netto_plus_mwst_ist_immer_brutto(self):
        # Der eigentliche Punkt: die Summe stimmt per Konstruktion, weil die
        # MwSt als Differenz entsteht und nicht selbst gerechnet wird.
        for brutto in (1, 2, 3, 99, 100, 499, 1234, 999999):
            for satz in ("19", "7", "0", "16"):
                n = netto_ct(brutto, Decimal(satz))
                m = mwst_ct(brutto, Decimal(satz))
                self.assertEqual(n + m, brutto,
                                 "brutto=%d satz=%s" % (brutto, satz))

    def test_mwst_7_prozent(self):
        # Von Hand: 10,70 EUR brutto bei 7 %.
        # 1070 / 1,07 = 1000 Cent netto genau, MwSt = 70 Cent.
        self.assertEqual(netto_ct(1070, Decimal("7")), 1000)
        self.assertEqual(mwst_ct(1070, Decimal("7")), 70)

    def test_satz_null(self):
        # Grenzfall: ohne Steuer ist netto gleich brutto.
        self.assertEqual(netto_ct(1234, Decimal("0")), 1234)
        self.assertEqual(mwst_ct(1234, Decimal("0")), 0)

    def test_brutto_null(self):
        # Grenzfall null.
        self.assertEqual(netto_ct(0, Decimal("19")), 0)
        self.assertEqual(mwst_ct(0, Decimal("19")), 0)

    def test_ein_cent(self):
        # Grenzfall kleinster Betrag: 1 Cent brutto bei 19 %.
        # 1 / 1,19 = 0,840... -> 1 Cent netto (kaufmaennisch), MwSt 0 Cent.
        self.assertEqual(netto_ct(1, Decimal("19")), 1)
        self.assertEqual(mwst_ct(1, Decimal("19")), 0)

    def test_netto_rundet_kaufmaennisch_nicht_zur_geraden_zahl(self):
        # Der Fall, der Fliesskomma von Decimal unterscheidet.
        # Von Hand: 3 Cent brutto bei 20 % -> 3 / 1,20 = 2,5 genau.
        # Kaufmaennisch (ROUND_HALF_UP) sind das 3 Cent netto.
        # Pythons round(2.5) liefert 2 (Rundung zur geraden Zahl) - damit
        # waere die MwSt 1 Cent statt 0 und der Betrag falsch.
        self.assertEqual(netto_ct(3, Decimal("20")), 3)
        self.assertEqual(mwst_ct(3, Decimal("20")), 0)

    def test_netto_rundet_kaufmaennisch_zweiter_fall(self):
        # Von Hand: 15 Cent brutto bei 20 % -> 15 / 1,20 = 12,5 genau.
        # Kaufmaennisch 13 Cent netto, MwSt 15 - 13 = 2 Cent.
        # Mit Fliesskomma-Rundung waeren es 12 und 3.
        self.assertEqual(netto_ct(15, Decimal("20")), 13)
        self.assertEqual(mwst_ct(15, Decimal("20")), 2)

    def test_jahressumme_aus_vielen_belegen(self):
        # Der Fall aus dem Bericht: eine Jahressumme aus vielen Belegen darf
        # nicht abweichen. Von Hand: 365 mal 4,99 EUR = 365 * 499 Cent
        # = 182 135 Cent = 1821,35 EUR.
        self.assertEqual(sum([499] * 365), 182135)


if __name__ == "__main__":
    unittest.main()
