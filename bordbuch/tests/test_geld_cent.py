"""Cent bleibt Cent (N-10).

Der Befund: Zwei Wege haben einen Betrag, der schon in Cent vorlag, noch
einmal durch die Euro-nach-Cent-Umrechnung geschickt. Aus 14,21 EUR wurden
1421,00 EUR, aus einer Tankung fuer 74,12 EUR wurden 7412,00 EUR.

- /api/sessions/import: die Oberflaeche schickt costCt (Cent), der Server
  las es mit cent() (Euro erwartet).
- /api/restore: die Sicherung enthaelt cost_ct (Cent), dieselbe Verwechslung.

Erwartungswerte von Hand, wie CLAUDE.md §13 es verlangt.
"""
import sqlite3
import unittest

from hilfe import server

ct_lesen = server.ct_lesen
cent = server.cent
cent_aus_sicherung = server.cent_aus_sicherung


class CentBleibtCent(unittest.TestCase):
    """ct_lesen liest Cent als Cent - der Unterschied zu cent()."""

    def test_ganzzahl_bleibt_gleich(self):
        # Von Hand: 1421 Cent sind 1421 Cent, nicht 142100.
        self.assertEqual(ct_lesen(1421), 1421)
        self.assertEqual(ct_lesen(0), 0)
        self.assertEqual(ct_lesen(7412), 7412)

    def test_cent_dagegen_rechnet_euro_um(self):
        # Der Gegenbeweis: genau dieser Unterschied war der Fehler.
        self.assertEqual(cent(14.21), 1421)
        self.assertEqual(cent(1421), 142100)

    def test_zeichenkette_und_komma(self):
        self.assertEqual(ct_lesen("1421"), 1421)
        self.assertEqual(ct_lesen("1421,0"), 1421)

    def test_bruchteil_wird_kaufmaennisch_gerundet(self):
        # Bruchteile eines Cents gibt es nicht. 1420,5 -> 1421 (nicht 1420).
        self.assertEqual(ct_lesen(1420.5), 1421)
        self.assertEqual(ct_lesen(1421.4), 1421)

    def test_unlesbar_gibt_None_nicht_null(self):
        # CLAUDE.md §11: eine stille Null in der Kostenrechnung ist schlimmer
        # als eine Fehlermeldung. None laesst den Aufrufer ausweichen.
        self.assertIsNone(ct_lesen("keine Zahl"))
        self.assertIsNone(ct_lesen("abc"))
        self.assertIsNone(ct_lesen(float("nan")))
        self.assertIsNone(ct_lesen(float("inf")))

    def test_fehlend_gibt_den_vorgabewert(self):
        self.assertIsNone(ct_lesen(None))
        self.assertEqual(ct_lesen(None, 0), 0)
        self.assertIsNone(ct_lesen("   "))


class SicherungLiestDieCentSpalte(unittest.TestCase):
    def test_cent_spalte_gewinnt_und_bleibt_cent(self):
        satz = {"cost_ct": 7412, "cost": 74.12}
        self.assertEqual(cent_aus_sicherung(satz, "cost_ct", "cost"), 7412)

    def test_alte_sicherung_ohne_cent_spalte(self):
        # Eine Sicherung aus einer aelteren Fassung kennt nur Euro.
        satz = {"cost": 74.12}
        self.assertEqual(cent_aus_sicherung(satz, "cost_ct", "cost"), 7412)

    def test_kaputte_cent_spalte_weicht_auf_euro_aus(self):
        satz = {"cost_ct": "kaputt", "cost": 4.25}
        self.assertEqual(cent_aus_sicherung(satz, "cost_ct", "cost"), 425)

    def test_beides_fehlt_gibt_null(self):
        # Hier ist 0 richtig: die Zeile soll nicht verloren gehen
        # (CLAUDE.md §15), und einen Betrag gibt es nicht.
        self.assertEqual(cent_aus_sicherung({}, "cost_ct", "cost"), 0)


class ImportZeileRechnetRichtig(unittest.TestCase):
    """Genau der Weg, auf dem der Fehler entstanden ist."""

    def werte(self, zeile):
        """Die Werte als Wortschatz {Spalte: Wert}, damit der Test lesbar bleibt."""
        v = server.import_zeile_werte(zeile)
        return dict(zip(server.SESSION_FIELDS, v))

    def test_cent_angabe_der_oberflaeche_bleibt_cent(self):
        # Genau das schickt die Oberflaeche fuer 14,21 EUR.
        w = self.werte({"id": "T-1", "start": "2026-08-01T18:12:00.000Z",
                        "kwh": 38.412, "cost": 14.21, "net": 11.94, "vat": 2.27,
                        "costCt": 1421, "netCt": 1194, "vatCt": 227})
        self.assertEqual(w["cost_ct"], 1421)
        self.assertEqual(w["net_ct"], 1194)
        self.assertEqual(w["vat_ct"], 227)

    def test_alte_datei_nur_mit_euro(self):
        w = self.werte({"id": "ALT", "start": "x", "kwh": 10, "cost": 3.5})
        self.assertEqual(w["cost_ct"], 350)

    def test_kaputte_cent_angabe_weicht_auf_euro_aus(self):
        w = self.werte({"id": "X", "start": "x", "kwh": 10,
                        "cost": 4.25, "costCt": "keine Zahl"})
        self.assertEqual(w["cost_ct"], 425)

    def test_ohne_jeden_betrag_null(self):
        w = self.werte({"id": "X", "start": "x", "kwh": 10})
        self.assertEqual(w["cost_ct"], 0)

    def test_menge_und_text_bleiben_unberuehrt(self):
        w = self.werte({"id": "X", "start": "x", "kwh": 38.4125,
                        "station": "EnBW", "sec": 12480, "odo": 120450})
        self.assertEqual(w["kwh"], 38.4125)
        self.assertEqual(w["station"], "EnBW")
        self.assertEqual(w["sec"], 12480)

    def test_text_wird_gekappt(self):
        w = self.werte({"id": "X", "start": "x", "station": "A" * 500})
        self.assertEqual(len(w["station"]), 200)


def datenbank():
    """Kleine Datenbank mit genau den Spalten, die die Pruefung ansieht."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE sessions(id INTEGER PRIMARY KEY, kwh REAL,
                   cost REAL, cost_ct INTEGER, net REAL, net_ct INTEGER,
                   vat REAL, vat_ct INTEGER, invoice_gross REAL,
                   invoice_gross_ct INTEGER)""")
    con.execute("""CREATE TABLE fuelings(id INTEGER PRIMARY KEY, liters REAL,
                   cost REAL, cost_ct INTEGER)""")
    con.execute("""CREATE TABLE werkstatt(id INTEGER PRIMARY KEY,
                   cost REAL, cost_ct INTEGER)""")
    return con


class HundertfacheFinden(unittest.TestCase):
    """Die sichere Spur: die zwei Geldspalten widersprechen sich."""

    def test_widerspruch_wird_gefunden(self):
        con = datenbank()
        # 14,21 EUR in der Altspalte, 1421,00 EUR in der Cent-Spalte.
        con.execute("INSERT INTO sessions(id,kwh,cost,cost_ct) VALUES(1,38.4,14.21,142100)")
        fund = server.hundertfache_betraege(con)
        namen = {(t, ct) for t, _, ct, _, _ in fund}
        self.assertIn(("sessions", "cost_ct"), namen)

    def test_richtige_zeile_bleibt_unberuehrt(self):
        con = datenbank()
        con.execute("INSERT INTO sessions(id,kwh,cost,cost_ct) VALUES(1,38.4,14.21,1421)")
        self.assertEqual(server.hundertfache_betraege(con), [])

    def test_ehrlicher_grosser_betrag_wird_nicht_angefasst(self):
        con = datenbank()
        # Eine echte Rechnung ueber 1421,00 EUR: beide Spalten sagen dasselbe.
        con.execute("INSERT INTO werkstatt(id,cost,cost_ct) VALUES(1,1421.0,142100)")
        self.assertEqual(server.hundertfache_betraege(con), [])

    def test_null_wird_nicht_gemeldet(self):
        con = datenbank()
        con.execute("INSERT INTO sessions(id,kwh,cost,cost_ct) VALUES(1,10,0,0)")
        self.assertEqual(server.hundertfache_betraege(con), [])

    def test_richten_setzt_den_wert_der_altspalte(self):
        con = datenbank()
        con.execute("""INSERT INTO sessions(id,kwh,cost,cost_ct,net,net_ct,vat,vat_ct)
                       VALUES(1,38.4,14.21,142100,11.94,119400,2.27,22700)""")
        server.betraege_richten(con)
        r = con.execute("SELECT cost_ct,net_ct,vat_ct FROM sessions WHERE id=1").fetchone()
        self.assertEqual((r["cost_ct"], r["net_ct"], r["vat_ct"]), (1421, 1194, 227))
        self.assertEqual(server.hundertfache_betraege(con), [])


class UnplausibleFinden(unittest.TestCase):
    """Die zweite Spur: beim Einspielen wurden beide Spalten verdorben."""

    def test_unmoeglicher_literpreis_wird_verdaechtigt(self):
        con = datenbank()
        # 7412,00 EUR fuer 42,8 Liter sind 173 EUR je Liter.
        con.execute("INSERT INTO fuelings(id,liters,cost,cost_ct) VALUES(1,42.8,7412.0,741200)")
        fund = server.unplausible_betraege(con)
        self.assertEqual([(t, n) for t, _, n, _ in fund], [("fuelings", 1)])

    def test_teure_aber_moegliche_ladung_bleibt_stehen(self):
        con = datenbank()
        # 0,89 EUR/kWh ist teuer, aber es gibt solche Ladesaeulen.
        con.execute("INSERT INTO sessions(id,kwh,cost,cost_ct) VALUES(1,40,35.60,3560)")
        self.assertEqual(server.unplausible_betraege(con), [])

    def test_was_nach_dem_teilen_noch_unmoeglich_ist_bleibt_stehen(self):
        con = datenbank()
        # 90000 EUR fuer 40 kWh: durch 100 geteilt immer noch 22,50 EUR/kWh,
        # also nicht mit Faktor 100 erklaerbar - Finger weg.
        con.execute("INSERT INTO sessions(id,kwh,cost,cost_ct) VALUES(1,40,90000.0,9000000)")
        self.assertEqual(server.unplausible_betraege(con), [])

    def test_richten_nur_auf_wunsch(self):
        con = datenbank()
        con.execute("INSERT INTO fuelings(id,liters,cost,cost_ct) VALUES(1,42.8,7412.0,741200)")
        server.betraege_richten(con)                       # ohne Wunsch
        self.assertEqual(con.execute("SELECT cost_ct FROM fuelings").fetchone()[0], 741200)
        server.betraege_richten(con, auch_unplausible=True)
        r = con.execute("SELECT cost,cost_ct FROM fuelings").fetchone()
        self.assertEqual(r["cost_ct"], 7412)
        self.assertAlmostEqual(r["cost"], 74.12, places=2)
        self.assertEqual(server.unplausible_betraege(con), [])

    def test_werkstatt_hat_keine_menge_und_bleibt_aussen_vor(self):
        con = datenbank()
        con.execute("INSERT INTO werkstatt(id,cost,cost_ct) VALUES(1,7412.0,741200)")
        # Ohne Menge gibt es kein Indiz - lieber stehen lassen als raten.
        self.assertEqual(server.unplausible_betraege(con), [])


if __name__ == "__main__":
    unittest.main()
