"""Anhaenge ueberleben das Bearbeiten (N-18).

Der Befund: uebernehmen() loeschte alle anhang-Zeilen einer Seite und legte
nur die neu mitgeschickten wieder an. Der Editor schickt eine bestehende
Datei aber nicht noch einmal mit - sie liegt schon auf dem Server, die neue
Fassung nennt sie nur (Marke data-wiki-anhang). Folge: Zeile weg, Abruf
lieferte application/octet-stream statt application/pdf, die Seite meldete
keine Anhaenge mehr, und der PDF-Text fiel aus der Suche.

Die Entscheidung "nennt die Seite den Anhang noch?" trifft
genannte_anhaenge(). Erwartungswerte von Hand (Regelblatt 13).
"""
import unittest

from hilfe import server

genannt = server.genannte_anhaenge


class WelcheAnhaengeNenntDieSeite(unittest.TestCase):
    def test_die_marke_des_ausgliederns(self):
        html = ('<script type="text/plain" id="k" '
                'data-wiki-anhang="kompendium.pdf"></script>')
        self.assertEqual(genannt(html), {"kompendium.pdf"})

    def test_einfache_anfuehrungszeichen(self):
        self.assertEqual(genannt("<script data-wiki-anhang='bild.png'></script>"),
                         {"bild.png"})

    def test_verweis_im_text(self):
        self.assertEqual(genannt('<img src="anhaenge/plan-2.png" alt="">'),
                         {"plan-2.png"})

    def test_mehrere_und_doppelte(self):
        html = ('<script data-wiki-anhang="a.pdf"></script>'
                '<img src="anhaenge/b.png"><a href="anhaenge/a.pdf">noch mal</a>')
        self.assertEqual(genannt(html), {"a.pdf", "b.png"})

    def test_seite_ohne_anhang(self):
        self.assertEqual(genannt("<p>Nur Text.</p>"), set())

    def test_leere_marke_zaehlt_nicht(self):
        # So sieht die Seite VOR dem Ausgliedern aus: die Marke ist noch leer.
        self.assertEqual(genannt('<script data-wiki-anhang="">DATEN</script>'), set())

    def test_kein_ausbruch_aus_dem_ordner(self):
        # Ein Name mit Pfad darf nicht durchkommen - sonst entscheidet der
        # Inhalt der Seite darueber, welche Datei gemeint ist.
        html = ('<script data-wiki-anhang="../../etc/passwd"></script>'
                '<img src="anhaenge/../../etc/passwd">')
        self.assertEqual(genannt(html), set())

    def test_nur_erlaubte_zeichen(self):
        self.assertEqual(genannt('<img src="anhaenge/mit leerzeichen.png">'),
                         {"mit"})   # bis zum Leerzeichen, und das ist ein
                                    # anderer Name - also kein Treffer auf die
                                    # echte Datei


if __name__ == "__main__":
    unittest.main()
