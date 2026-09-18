"""Urheber statt "wer zuletzt gespeichert hat" (N-15).

Der Befund: seite.nutzer_id wird bei jeder Uebernahme neu geschrieben. Als
Schreibrecht gelesen heisst das: sobald ein Verwalter eine fremde Seite
anfasst, steht er selbst drin - und der Urheber kommt an seine eigene Seite
nicht mehr heran (im Versuch: HTTP 403 auf die eigenen Fassungen).

Erwartungswerte von Hand, wie CLAUDE.md §13 es verlangt.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import sqlite3
import unittest

from hilfe import server

urheber_von = server.urheber_von
darf_aendern = server.darf_aendern


class UrheberLesen(unittest.TestCase):
    def test_eigene_spalte_gewinnt(self):
        self.assertEqual(urheber_von({"urheber": "lena", "nutzer_id": "artur"}),
                         "lena")

    def test_leere_spalte_weicht_auf_nutzer_id_aus(self):
        self.assertEqual(urheber_von({"urheber": "", "nutzer_id": "artur"}),
                         "artur")

    def test_zeile_ohne_die_spalte(self):
        # Eine Zeile aus einer Datenbank vor 1.2.0 hat die Spalte nicht.
        self.assertEqual(urheber_von({"nutzer_id": "artur"}), "artur")

    def test_beides_leer(self):
        self.assertEqual(urheber_von({"urheber": "", "nutzer_id": ""}), "")

    def test_echte_datenbankzeile_ohne_spalte(self):
        # sqlite3.Row wirft IndexError, nicht KeyError - das muss beides
        # gefangen sein, sonst faellt der Server bei alten Zeilen um.
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE seite(nutzer_id TEXT)")
        con.execute("INSERT INTO seite VALUES('lena')")
        z = con.execute("SELECT * FROM seite").fetchone()
        self.assertEqual(urheber_von(z), "lena")


def nutzer(kennung, gruppen=("wiki-editor",)):
    """Ein Nutzer wie ihn die Kopfzeilen liefern."""
    return server.Nutzer(kennung, kennung.title(), "", list(gruppen))


class WerAendernDarf(unittest.TestCase):
    ZEILE = {"urheber": "lena", "nutzer_id": "artur"}   # Verwalter war zuletzt dran

    def test_der_urheber_darf(self):
        self.assertTrue(darf_aendern(self.ZEILE, nutzer("lena")))

    def test_wer_zuletzt_speicherte_darf_deswegen_nicht(self):
        # Genau der Fehler: artur darf nur, WEIL er Verwalter ist - nicht,
        # weil er zuletzt gespeichert hat.
        self.assertFalse(darf_aendern(self.ZEILE, nutzer("artur")))

    def test_jeder_verwalter_darf(self):
        self.assertTrue(darf_aendern(self.ZEILE, nutzer("artur", ["wiki-admin"])))
        self.assertTrue(darf_aendern(self.ZEILE, nutzer("max", ["wiki-admin"])))

    def test_ein_fremder_darf_nicht(self):
        self.assertFalse(darf_aendern(self.ZEILE, nutzer("max")))

    def test_ohne_kennung_darf_niemand(self):
        # Sonst wuerde eine leere Kennung auf eine leere Spalte passen.
        self.assertFalse(darf_aendern({"urheber": "", "nutzer_id": ""}, nutzer("")))

    # ---------------------------------------------------- N-21: die Gruppe
    def test_ohne_editorgruppe_darf_auch_der_urheber_nicht(self):
        """Wer die Schreibgruppe verliert, aendert auch die eigene Seite nicht.

        Das ist der Sinn der Gruppe: Sie wird vergeben und wieder entzogen.
        Wuerde die Urheberschaft sie ueberstimmen, waere der Entzug wirkungslos.
        """
        self.assertFalse(darf_aendern(self.ZEILE, nutzer("lena", ["wiki-technik"])))

    def test_leser_ohne_jede_wiki_gruppe(self):
        self.assertFalse(darf_aendern(self.ZEILE, nutzer("lena", [])))

    def test_verwalter_ist_auch_editor(self):
        # Sonst braeuchte man zwei Gruppen, um eine Seite anzulegen.
        self.assertTrue(nutzer("artur", ["wiki-admin"]).ist_editor)


class NurWikiGruppenZaehlen(unittest.TestCase):
    """N-21: In Authentik haengen an einem Nutzer die Gruppen aller Tools."""

    def test_fremde_gruppen_werden_aussortiert(self):
        n = nutzer("lena", ["wiki-technik", "vertrieb", "bordbuch-admin", "wiki-editor"])
        self.assertEqual(n.gruppen, {"wiki-technik", "wiki-editor"})
        self.assertEqual(n.gruppen_andere, ["bordbuch-admin", "vertrieb"])

    def test_wer_nur_fremde_gruppen_hat_darf_lesen(self):
        n = nutzer("max", ["vertrieb"])
        self.assertEqual(n.gruppen, set())
        self.assertFalse(n.ist_editor)
        self.assertFalse(n.ist_admin)

    def test_eine_fremde_gruppe_macht_niemanden_zum_verwalter(self):
        # Der Praefixfilter darf die Rollenpruefung nicht aushebeln, und eine
        # fremde Gruppe darf sie nicht bestehen.
        self.assertFalse(nutzer("max", ["admin", "wiki"]).ist_admin)
        self.assertTrue(nutzer("max", ["wiki-admin"]).ist_admin)


def alte_datenbank():
    """Eine Datenbank im Zustand vor 1.2.0: seite ohne Spalte urheber."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE seite(id INTEGER PRIMARY KEY, slug TEXT,
                   nutzer_id TEXT NOT NULL DEFAULT '')""")
    con.execute("""CREATE TABLE fassung(seite_id INTEGER, nummer INTEGER,
                   nutzer_id TEXT NOT NULL DEFAULT '')""")
    return con


class SpalteNachtragen(unittest.TestCase):
    def test_wird_aus_der_ersten_fassung_gefuellt(self):
        con = alte_datenbank()
        con.execute("INSERT INTO seite VALUES(1,'netzwerke','artur')")
        # Fassung 1 hat lena geschrieben, Fassung 2 max - artur kam zuletzt.
        con.execute("INSERT INTO fassung VALUES(1,2,'max')")
        con.execute("INSERT INTO fassung VALUES(1,1,'lena')")
        self.assertTrue(server.spalte_urheber_nachtragen(con))
        z = con.execute("SELECT urheber FROM seite WHERE id=1").fetchone()
        self.assertEqual(z["urheber"], "lena")

    def test_ohne_fassungen_bleibt_nutzer_id(self):
        con = alte_datenbank()
        con.execute("INSERT INTO seite VALUES(1,'neu','lena')")
        server.spalte_urheber_nachtragen(con)
        z = con.execute("SELECT urheber FROM seite WHERE id=1").fetchone()
        self.assertEqual(z["urheber"], "lena")

    def test_leere_fassungskennung_zaehlt_nicht(self):
        con = alte_datenbank()
        con.execute("INSERT INTO seite VALUES(1,'alt','artur')")
        con.execute("INSERT INTO fassung VALUES(1,1,'')")
        server.spalte_urheber_nachtragen(con)
        z = con.execute("SELECT urheber FROM seite WHERE id=1").fetchone()
        self.assertEqual(z["urheber"], "artur")

    def test_zweiter_aufruf_tut_nichts(self):
        con = alte_datenbank()
        con.execute("INSERT INTO seite VALUES(1,'x','lena')")
        self.assertTrue(server.spalte_urheber_nachtragen(con))
        self.assertFalse(server.spalte_urheber_nachtragen(con))

    def test_nichts_wird_ueberschrieben(self):
        # Zweite Seite mit anderem Urheber - die erste darf davon nichts
        # abbekommen.
        con = alte_datenbank()
        con.execute("INSERT INTO seite VALUES(1,'eins','lena')")
        con.execute("INSERT INTO seite VALUES(2,'zwei','max')")
        con.execute("INSERT INTO fassung VALUES(2,1,'artur')")
        server.spalte_urheber_nachtragen(con)
        werte = {z["slug"]: z["urheber"] for z in
                 con.execute("SELECT slug,urheber FROM seite").fetchall()}
        self.assertEqual(werte, {"eins": "lena", "zwei": "artur"})


if __name__ == "__main__":
    unittest.main()
