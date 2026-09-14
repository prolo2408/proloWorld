"""Mandantentrennung (B-12).

Der Bericht hat sie serverseitig angegriffen und fuer haltend befunden. Sie
ist damit ungeschuetzt richtig - der naechste Umbau merkt es nicht. Diese
Tests halten sie fest.

Gearbeitet wird direkt auf der Datenbank und ueber die Abfragen, die der
Server benutzt; kein HTTP, damit die Tests ohne laufenden Server gehen.
"""
import os
import sqlite3
import tempfile
import types
import unittest

from hilfe import server


class TrennungBasis(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        db = os.path.join(self.ordner, "t.db")
        server.CFG = types.SimpleNamespace(db=db, verbose=False,
                                           admin_gruppe="bordbuch-admin")
        server.RECEIPT_DIR = os.path.join(self.ordner, "belege")
        server.init_db()
        with server.db() as con:
            self.alice = con.execute(
                "INSERT INTO users(name,authentik_user) VALUES('alice','alice')").lastrowid
            self.mallory = con.execute(
                "INSERT INTO users(name,authentik_user) VALUES('mallory','mallory')").lastrowid
            self.auto_alice = con.execute(
                "INSERT INTO cars(nutzer_id,name) VALUES(?,'Golf')", (self.alice,)).lastrowid
            con.execute("INSERT INTO fuelings(nutzer_id,car_id,ts,liters,cost,cost_ct)"
                        " VALUES(?,?,'2026-01-01T10:00',40,80.0,8000)",
                        (self.alice, self.auto_alice))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)


class FremdeDatenLesen(TrennungBasis):
    def test_fremdes_auto_ist_nicht_sichtbar(self):
        # Die Abfrage, die own_car() benutzt.
        with server.db() as con:
            treffer = con.execute("SELECT 1 FROM cars WHERE id=? AND nutzer_id=?",
                                  (self.auto_alice, self.mallory)).fetchone()
        self.assertIsNone(treffer)

    def test_eigenes_auto_ist_sichtbar(self):
        with server.db() as con:
            treffer = con.execute("SELECT 1 FROM cars WHERE id=? AND nutzer_id=?",
                                  (self.auto_alice, self.alice)).fetchone()
        self.assertIsNotNone(treffer)

    def test_fremde_tankung_nicht_in_der_eigenen_liste(self):
        with server.db() as con:
            n = con.execute("SELECT COUNT(*) FROM fuelings WHERE nutzer_id=?",
                            (self.mallory,)).fetchone()[0]
        self.assertEqual(n, 0)


class FremdeDatenSchreiben(TrennungBasis):
    def test_fremde_tankung_loeschen_trifft_nichts(self):
        # Genau der Fall aus B-09: die Trennung haelt, aber der rowcount ist 0
        # und muss darum als Fehler gemeldet werden.
        with server.db() as con:
            cur = con.execute("DELETE FROM fuelings WHERE id=1 AND nutzer_id=?",
                              (self.mallory,))
            self.assertEqual(cur.rowcount, 0)
            # und die Zeile steht noch
            self.assertEqual(con.execute("SELECT COUNT(*) FROM fuelings").fetchone()[0], 1)

    def test_fremde_tankung_aendern_trifft_nichts(self):
        with server.db() as con:
            cur = con.execute("UPDATE fuelings SET cost_ct=1 WHERE id=1 AND nutzer_id=?",
                              (self.mallory,))
            self.assertEqual(cur.rowcount, 0)
            self.assertEqual(con.execute(
                "SELECT cost_ct FROM fuelings WHERE id=1").fetchone()[0], 8000)


class Freigaben(TrennungBasis):
    def test_ohne_freigabe_kein_zugriff(self):
        with server.db() as con:
            fr = con.execute(
                "SELECT rechte FROM freigaben WHERE eigentuemer_id=? AND empfaenger_id=?"
                " AND ziel_typ='profil'", (self.alice, self.mallory)).fetchone()
        self.assertIsNone(fr)

    def test_lesefreigabe_gibt_nur_lesen(self):
        with server.db() as con:
            con.execute("INSERT INTO freigaben(eigentuemer_id,empfaenger_id,ziel_typ,ziel_id,rechte)"
                        " VALUES(?,?,'profil',0,'lesen')", (self.alice, self.mallory))
            fr = con.execute(
                "SELECT rechte FROM freigaben WHERE eigentuemer_id=? AND empfaenger_id=?"
                " AND ziel_typ='profil'", (self.alice, self.mallory)).fetchone()
        self.assertEqual(fr["rechte"], "lesen")
        # darf_schreiben leitet sich daraus ab
        self.assertFalse(fr["rechte"] == "schreiben")

    def test_schreibfreigabe_ist_keine_profiluebernahme(self):
        # Der Kern des Freigabemodells, den der Bericht ausdruecklich lobt:
        # "Eine Freigabe heisst mitschreiben duerfen, nicht das Profil
        # uebernehmen." Diese Wege bleiben beim Eigentuemer.
        for weg in ("/api/settings", "/api/restore", "/api/users/reset",
                    "/api/freigabe/save", "/api/freigabe/delete",
                    "/api/cars/save", "/api/cars/delete", "/api/admin/import"):
            self.assertIn(weg, server.NUR_EIGENTUEMER,
                          "%s muss beim Eigentuemer bleiben" % weg)

    def test_freigabe_ist_nicht_gegenseitig(self):
        # Alice gibt mallory frei - das heisst nicht, dass alice in mallorys
        # Profil darf.
        with server.db() as con:
            con.execute("INSERT INTO freigaben(eigentuemer_id,empfaenger_id,ziel_typ,ziel_id,rechte)"
                        " VALUES(?,?,'profil',0,'schreiben')", (self.alice, self.mallory))
            rueck = con.execute(
                "SELECT 1 FROM freigaben WHERE eigentuemer_id=? AND empfaenger_id=?"
                " AND ziel_typ='profil'", (self.mallory, self.alice)).fetchone()
        self.assertIsNone(rueck)


class Gruppen(unittest.TestCase):
    """Gruppentrennzeichen (B-30) - ein echter Fehler mit Wirkung.

    Authentik trennt mit Pipe. Das Bordbuch trennte nur an Komma, womit
    "a|bordbuch-admin|c" EINE Gruppe war und ist_admin() fehlschlug - die
    Gesamtsicherung waere fuer niemanden erreichbar gewesen.
    """

    def test_pipe(self):
        self.assertEqual(server.gruppen_aus_kopf("a|bordbuch-admin|c"),
                         {"a", "bordbuch-admin", "c"})

    def test_komma(self):
        self.assertEqual(server.gruppen_aus_kopf("a,bordbuch-admin,c"),
                         {"a", "bordbuch-admin", "c"})

    def test_semikolon(self):
        self.assertEqual(server.gruppen_aus_kopf("a;bordbuch-admin;c"),
                         {"a", "bordbuch-admin", "c"})

    def test_gemischt_und_mit_leerzeichen(self):
        # Grenzfall: verschiedene Trennzeichen in einem Kopf, dazu Leerraum.
        self.assertEqual(server.gruppen_aus_kopf(" a | b , c ; d "),
                         {"a", "b", "c", "d"})

    def test_eine_gruppe(self):
        self.assertEqual(server.gruppen_aus_kopf("bordbuch-admin"),
                         {"bordbuch-admin"})

    def test_keine_gruppen(self):
        # Fall mit fehlenden Daten.
        self.assertEqual(server.gruppen_aus_kopf(""), set())
        self.assertEqual(server.gruppen_aus_kopf(None), set())
        self.assertEqual(server.gruppen_aus_kopf("|||"), set())
        self.assertEqual(server.gruppen_aus_kopf("  "), set())


if __name__ == "__main__":
    unittest.main()
