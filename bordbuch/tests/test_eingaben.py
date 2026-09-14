"""Eingabepruefung ohne stille Vorgabewerte (B-05).

Regelblatt 11, woertlich: "Keine stillen Vorgabewerte. Fehlt ein Wert, wird das
gemeldet - nicht durch eine Null ersetzt. Eine Null in der Verbrauchsrechnung
ist schlimmer als eine Fehlermeldung, weil sie falsche Ergebnisse erzeugt, die
niemandem auffallen."

Erwartungswerte von Hand, wie Regelblatt 13 es verlangt.
"""
import datetime
import unittest

from hilfe import server

zahl = server.zahl
FEHLT = server.FEHLT
pflicht_zahl = server.pflicht_zahl
pflicht_cent = server.pflicht_cent
valid_ts = server.valid_ts
valid_dat = server.valid_dat
valid_dat_vergangen = server.valid_dat_vergangen
valid_dat_zukunft = server.valid_dat_zukunft
plus_monate = server.plus_monate


class ZahlOhneVorgabe(unittest.TestCase):
    def test_normalfall(self):
        self.assertEqual(zahl("40"), 40.0)
        self.assertEqual(zahl("40,5"), 40.5)
        self.assertEqual(zahl(40), 40.0)

    def test_unlesbar_gibt_fehlt_nicht_null(self):
        # Der Kern des Befunds: "abc" wurde zu 0.0 und als Erfolg gemeldet.
        self.assertIs(zahl("abc"), FEHLT)
        self.assertIs(zahl("neunmillionen"), FEHLT)
        self.assertIs(zahl(None), FEHLT)
        self.assertIs(zahl(""), FEHLT)

    def test_nan_und_unendlich(self):
        # Grenzfall: beides ist "eine Zahl" fuer float(), aber kein Wert.
        self.assertIs(zahl("NaN"), FEHLT)
        self.assertIs(zahl("inf"), FEHLT)
        self.assertIs(zahl("-inf"), FEHLT)

    def test_null_ist_ein_gueltiger_wert(self):
        # Grenzfall null: eine ausdrueckliche Null ist keine fehlende Angabe.
        self.assertEqual(zahl("0"), 0.0)
        self.assertEqual(zahl(0), 0.0)


class Grenzen(unittest.TestCase):
    def test_kilometerstand_neun_millionen(self):
        # Das Beispiel aus dem Regelblatt selbst: "Ein Kilometerstand von 9
        # Millionen ist ein Tippfehler, kein Datensatz."
        w, fehler = pflicht_zahl({"odo": 9000000}, "odo", "odo_km")
        self.assertIsNone(w)
        self.assertIn("Tippfehler", fehler)

    def test_kilometerstand_plausibel(self):
        # Von Hand: 123456 km liegt zwischen 0 und 2 000 000.
        w, fehler = pflicht_zahl({"odo": 123456}, "odo", "odo_km")
        self.assertEqual(w, 123456)
        self.assertIsNone(fehler)

    def test_grenze_genau_erreicht_ist_erlaubt(self):
        # Grenzfall: die Grenze selbst gehoert noch dazu.
        self.assertEqual(pflicht_zahl({"odo": 2000000}, "odo", "odo_km")[0], 2000000)
        self.assertEqual(pflicht_zahl({"odo": 0}, "odo", "odo_km")[0], 0)

    def test_grenze_knapp_ueberschritten(self):
        self.assertIsNone(pflicht_zahl({"odo": 2000001}, "odo", "odo_km")[0])
        self.assertIsNone(pflicht_zahl({"odo": -1}, "odo", "odo_km")[0])

    def test_optional_darf_fehlen_aber_nicht_unsinn_sein(self):
        # Die Unterscheidung, an der ich beim Bauen selbst gestolpert bin:
        # pflicht=False heisst "darf fehlen", nicht "darf Unsinn sein".
        w, fehler = pflicht_zahl({}, "odo", "odo_km", pflicht=False)
        self.assertIsNone(w)
        self.assertIsNone(fehler)                   # fehlen ist in Ordnung
        w, fehler = pflicht_zahl({"odo": ""}, "odo", "odo_km", pflicht=False)
        self.assertIsNone(w)
        self.assertIsNone(fehler)                   # leer ist in Ordnung
        w, fehler = pflicht_zahl({"odo": "abc"}, "odo", "odo_km", pflicht=False)
        self.assertIsNone(w)
        self.assertIsNotNone(fehler)                # Unsinn ist es NICHT
        self.assertIn("keine Zahl", fehler)

    def test_pflichtfeld_fehlt(self):
        w, fehler = pflicht_zahl({}, "liters", "liters_l")
        self.assertIsNone(w)
        self.assertIn("fehlt", fehler)

    def test_meldung_sagt_was_zu_tun_ist(self):
        # Regelblatt 7: die Meldung sagt, was zu tun ist - nicht nur, was
        # kaputt ist. "ungueltiger Wert" waere zu wenig.
        _, fehler = pflicht_zahl({"odo": 9000000}, "odo", "odo_km")
        self.assertIn("Bitte", fehler)
        self.assertIn("Kilometerstand", fehler)     # Klartextname, nicht "odo"


class Betraege(unittest.TestCase):
    def test_betrag_unlesbar(self):
        w, fehler = pflicht_cent({"cost": "abc"}, "cost")
        self.assertIsNone(w)
        self.assertIn("keine Zahl", fehler)

    def test_betrag_normal(self):
        # Von Hand: 80,50 EUR = 8050 Cent.
        self.assertEqual(pflicht_cent({"cost": "80,50"}, "cost")[0], 8050)

    def test_betrag_unplausibel(self):
        # Von Hand: 99999 EUR je Einzelvorgang ist ein Tippfehler.
        w, fehler = pflicht_cent({"cost": 99999}, "cost")
        self.assertIsNone(w)
        self.assertIn("Tippfehler", fehler)

    def test_betrag_optional_darf_fehlen(self):
        self.assertEqual(pflicht_cent({}, "cost", pflicht=False), (None, None))

    def test_betrag_optional_aber_unsinn_wird_gemeldet(self):
        w, fehler = pflicht_cent({"cost": "abc"}, "cost", pflicht=False)
        self.assertIsNone(w)
        self.assertIsNotNone(fehler)


class Datum(unittest.TestCase):
    def test_form_wird_geprueft(self):
        self.assertEqual(valid_dat("2027-03-15"), "2027-03-15")
        # Nur Monat angegeben: der Erste wird ergaenzt (HU-Faelligkeit).
        self.assertEqual(valid_dat("2027-03"), "2027-03-01")
        self.assertEqual(valid_dat("Unsinn"), "")

    def test_unmoegliches_datum_trotz_passender_form(self):
        # 2026-02-31 passt auf das Muster, gibt es aber nicht.
        self.assertEqual(valid_dat("2026-02-31"), "")
        self.assertEqual(valid_dat("2026-13-01"), "")

    def test_zeitstempel_2099_wird_abgelehnt(self):
        # Der belegte Fall: valid_ts prueft jetzt auch den Bereich.
        self.assertEqual(valid_ts("2099-12-31T10:00"), "")

    def test_zeitstempel_heute_geht(self):
        heute = datetime.date.today().isoformat()
        self.assertEqual(valid_ts(heute + "T10:00"), heute + "T10:00")

    def test_zeitstempel_morgen_geht_noch(self):
        # Ein Tag Zukunft ist erlaubt: Zeitzonen und falsch gestellte Uhren
        # sollen keine Eingabe verhindern.
        morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(valid_ts(morgen + "T10:00"), morgen + "T10:00")

    def test_zeitstempel_uebermorgen_nicht_mehr(self):
        weit = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        self.assertEqual(valid_ts(weit + "T10:00"), "")

    def test_zeitstempel_vor_1990(self):
        self.assertEqual(valid_ts("1989-12-31T10:00"), "")

    def test_ereignis_darf_nicht_in_der_zukunft_liegen(self):
        self.assertEqual(valid_dat_vergangen("2099-01-01"), "")
        self.assertEqual(valid_dat_vergangen("2026-01-15"), "2026-01-15")

    def test_faelligkeit_darf_in_der_zukunft_liegen(self):
        # Der Sonderfall, den der Bericht ausdruecklich nennt: die HU im
        # Maerz 2029 ist voellig richtig und darf nicht abgelehnt werden.
        self.assertEqual(valid_dat_zukunft("2029-03"), "2029-03-01")

    def test_faelligkeit_aber_nicht_im_jahr_2400(self):
        self.assertEqual(valid_dat_zukunft("2400-01-01"), "")


class PlusMonate(unittest.TestCase):
    def test_schaltjahr_2000(self):
        # Von Hand: 2000 ist durch 400 teilbar, also Schaltjahr - der Februar
        # hat 29 Tage. 29.01.2000 plus 1 Monat = 29.02.2000.
        self.assertEqual(plus_monate("2000-01-29", 1), "2000-02-29")

    def test_kein_schaltjahr_1900(self):
        # Von Hand: 1900 ist durch 100, aber nicht durch 400 teilbar, also
        # KEIN Schaltjahr - der Februar hat 28 Tage.
        self.assertEqual(plus_monate("1900-01-29", 1), "1900-02-28")

    def test_monatsende_31_auf_30(self):
        # Von Hand: 31.01. plus 3 Monate = 30.04. (April hat 30 Tage).
        self.assertEqual(plus_monate("2026-01-31", 3), "2026-04-30")

    def test_jahreswechsel(self):
        # Von Hand: 15.11.2026 plus 24 Monate = 15.11.2028.
        self.assertEqual(plus_monate("2026-11-15", 24), "2028-11-15")

    def test_null_monate(self):
        # Grenzfall null: das Datum bleibt.
        self.assertEqual(plus_monate("2026-05-10", 0), "2026-05-10")

    def test_unsinniges_datum(self):
        # Fall mit fehlenden Daten.
        self.assertEqual(plus_monate("Unsinn", 3), "")


if __name__ == "__main__":
    unittest.main()
