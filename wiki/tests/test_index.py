"""Der Suchindex darf an Resten nicht scheitern (N-16).

Der Befund: treffer.id ist ein rowid-Alias und dient gleichzeitig als rowid
in den FTS-Tabellen suche und suche_tri. Beim Loeschen einer Seite raeumte
der Fremdschluessel (ON DELETE CASCADE) die treffer-Zeilen weg - die
FTS-Zeilen blieben liegen. SQLite verwendet freigewordene rowids wieder, und
der naechste Indexaufbau lief in die verwaiste Zeile:

    sqlite3.IntegrityError: constraint failed

Danach baute sich der Index nie wieder auf, auch nicht ueber "Index neu" -
die Suche fand gar nichts mehr.

Erwartungswerte von Hand (Regelblatt 13).

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import sqlite3
import unittest

from hilfe import server


def datenbank():
    """Eine Datenbank mit dem echten Schema des Servers."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(server.SCHEMA)
    con.executescript(server.SCHEMA_FTS)
    con.executescript(server.SCHEMA_TRI)
    return con


def seite(con, slug):
    con.execute("INSERT INTO seite(slug,titel) VALUES(?,?)", (slug, slug.title()))
    return con.execute("SELECT id FROM seite WHERE slug=?", (slug,)).fetchone()["id"]


def treffer(con, seite_id, text):
    """Eine Indexzeile so anlegen, wie index_neu_bauen es tut."""
    cur = con.execute("INSERT INTO treffer(seite_id,abschnittstitel) VALUES(?,?)",
                      (seite_id, text))
    tid = cur.lastrowid
    con.execute("INSERT INTO suche(rowid,titel,stichworte,text) VALUES(?,?,?,?)",
                (tid, text, "", text))
    con.execute("INSERT INTO suche_tri(rowid,inhalt) VALUES(?,?)", (tid, text))
    return tid


def zahlen(con):
    """(treffer, suche, suche_tri, verwaist)"""
    z = lambda f: con.execute("SELECT count(*) FROM " + f).fetchone()[0]
    return (z("treffer"), z("suche"), z("suche_tri"),
            z("suche WHERE rowid NOT IN (SELECT id FROM treffer)"))


class DerFehlerSelbst(unittest.TestCase):
    """Zuerst der Beweis, dass die Lage wirklich so kippt."""

    def test_verwaiste_zeile_bringt_den_aufbau_zu_fall(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "Quellkabel")                   # treffer.id = 1
        # Genau das tat das Loeschen: treffer weg, FTS-Zeile bleibt.
        con.execute("DELETE FROM treffer WHERE seite_id=?", (s1,))
        self.assertEqual(zahlen(con), (0, 1, 1, 1))
        # Die naechste Seite bekommt rowid 1 wieder - und stoesst an.
        s2 = seite(con, "beta")
        with self.assertRaises(sqlite3.IntegrityError):
            treffer(con, s2, "Sternschaltung")

    def test_nach_dem_aufraeumen_geht_es_wieder(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "Quellkabel")
        con.execute("DELETE FROM treffer WHERE seite_id=?", (s1,))
        self.assertEqual(server.verwaiste_indexzeilen_loeschen(con), 2)  # suche + tri
        s2 = seite(con, "beta")
        treffer(con, s2, "Sternschaltung")               # darf jetzt durchgehen
        self.assertEqual(zahlen(con), (1, 1, 1, 0))


class IndexLeeren(unittest.TestCase):
    def test_nimmt_die_fts_zeilen_mit(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "eins")
        treffer(con, s1, "zwei")
        server.index_leeren(con, s1)
        self.assertEqual(zahlen(con), (0, 0, 0, 0))

    def test_laesst_andere_seiten_stehen(self):
        con = datenbank()
        s1, s2 = seite(con, "alpha"), seite(con, "beta")
        treffer(con, s1, "eins")
        treffer(con, s2, "zwei")
        treffer(con, s2, "drei")
        server.index_leeren(con, s1)
        # Von Hand: zwei Zeilen von beta bleiben, keine verwaist.
        self.assertEqual(zahlen(con), (2, 2, 2, 0))
        uebrig = [z["abschnittstitel"] for z in
                  con.execute("SELECT abschnittstitel FROM treffer ORDER BY id")]
        self.assertEqual(uebrig, ["zwei", "drei"])

    def test_auf_einer_seite_ohne_index_ist_es_kein_fehler(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        server.index_leeren(con, s1)
        self.assertEqual(zahlen(con), (0, 0, 0, 0))


class VerwaisteZeilen(unittest.TestCase):
    def test_zaehlt_nur_was_wirklich_verwaist_ist(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "bleibt")
        con.execute("INSERT INTO suche(rowid,titel,stichworte,text) "
                    "VALUES(99,'Rest','','Rest')")
        # Von Hand: eine verwaiste Zeile in suche, keine in suche_tri.
        self.assertEqual(server.verwaiste_indexzeilen_loeschen(con), 1)
        self.assertEqual(zahlen(con), (1, 1, 1, 0))

    def test_saubere_datenbank_bleibt_unberuehrt(self):
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "eins")
        self.assertEqual(server.verwaiste_indexzeilen_loeschen(con), 0)
        self.assertEqual(zahlen(con), (1, 1, 1, 0))

    def test_der_uebrige_inhalt_ist_wirklich_weg(self):
        # Sonst faende die Suche weiter den Text geloeschter Seiten.
        con = datenbank()
        s1 = seite(con, "alpha")
        treffer(con, s1, "Quellkabel")
        con.execute("DELETE FROM treffer WHERE seite_id=?", (s1,))
        server.verwaiste_indexzeilen_loeschen(con)
        gefunden = con.execute("SELECT count(*) FROM suche WHERE suche MATCH ?",
                               ("Quellkabel",)).fetchone()[0]
        self.assertEqual(gefunden, 0)


if __name__ == "__main__":
    unittest.main()
