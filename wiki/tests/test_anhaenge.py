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


class MarkierteAnhaengeWerdenAusgegliedert(unittest.TestCase):
    """Ein PDF aus dem Editor ist ein Anhang, auch wenn es klein ist.

    Die Groessenschwelle ist fuer Bloecke da, die ZUFAELLIG gross sind.
    Traegt der Block die Marke data-wiki-anhang, ist er ausdruecklich als
    Anhang gemeint - dann muss er ausgegliedert werden, sonst laesst sich
    das PDF nicht anzeigen und nicht seitenweise durchsuchen.
    """

    # Ein winziges, gueltiges PDF - base64, weit unter der Schwelle.
    PDF = ("JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4K"
           "ZW5kb2JqCnRyYWlsZXIKPDwgL1Jvb3QgMSAwIFIgPj4KJSVFT0YK")

    def test_mit_marke_wird_ausgegliedert(self):
        html = ('<script type="text/plain" id="anhang-probe" '
                'data-wiki-anhang="">%s</script>' % self.PDF)
        neu, gefunden = server.anhaenge_ausgliedern(html, "probe")
        self.assertEqual(len(gefunden), 1)
        self.assertEqual(gefunden[0]["name"], "anhang-probe.pdf")
        self.assertEqual(gefunden[0]["typ"], "application/pdf")
        # Die Daten sind aus der Seite heraus - sonst stuenden sie zweimal da.
        self.assertNotIn(self.PDF, neu)
        self.assertIn('data-wiki-anhang="anhang-probe.pdf"', neu)

    def test_ohne_marke_bleibt_kleines_stehen(self):
        # Die Schwelle gilt weiter: ein kleiner Base64-Block ohne Marke ist
        # kein Anhang, sondern irgendein Inhalt der Seite.
        html = '<script type="text/plain" id="anhang-probe">%s</script>' % self.PDF
        neu, gefunden = server.anhaenge_ausgliedern(html, "probe")
        self.assertEqual(gefunden, [])
        self.assertIn(self.PDF, neu)

    def test_marke_macht_aus_text_keinen_anhang(self):
        # Nur Base64 kommt in Frage - sonst wuerde ein Skript mit der Marke
        # zur Datei erklaert.
        html = ('<script id="x" data-wiki-anhang="">'
                'alert(1); // kein base64</script>')
        neu, gefunden = server.anhaenge_ausgliedern(html, "probe")
        self.assertEqual(gefunden, [])
        self.assertIn("alert(1)", neu)

    def test_leerer_block_mit_marke_ist_nur_ein_verweis(self):
        html = ('<script type="text/plain" id="anhang-probe" '
                'data-wiki-anhang="anhang-probe.pdf"></script>')
        neu, gefunden = server.anhaenge_ausgliedern(html, "probe")
        self.assertEqual(gefunden, [])
        self.assertEqual(server.genannte_anhaenge(neu), {"anhang-probe.pdf"})


class EingebetteteBilderBleibenSichtbar(unittest.TestCase):
    """N-31: Aus einem grossen Bild wurde eine kaputte Adresse.

    Das Ausgliedern ersetzte nur den DATENTEIL einer data:-Adresse. Heraus
    kam src="data:image/png;base64,anhaenge/eingebettet.png" - der Browser
    liest das als Base64, bekommt Unsinn und zeigt nichts. Die Pruefung
    meldete dabei "eingespielt" und legte die Datei sauber ab.
    """

    def bauen(self, zeichen):
        # Ein Datenteil aus lauter 'A' ist gueltiges Base64 und laesst sich
        # in der Laenge genau einstellen - darum steht die Schwelle hier
        # nicht zur Debatte.
        daten = "A" * zeichen
        return ('<html><body><p><img alt="x" '
                'src="data:image/png;base64,%s"></p></body></html>' % daten)

    def test_die_adresse_zeigt_auf_die_datei_und_sonst_nichts(self):
        html, anhaenge = server.anhaenge_ausgliedern(
            self.bauen(2000), "probe", schwelle=1000)
        self.assertEqual(len(anhaenge), 1, anhaenge)
        self.assertIn('src="anhaenge/%s"' % anhaenge[0]["name"], html)
        self.assertNotIn("data:image", html,
                         "die alte Adresse steht noch davor")

    def test_unter_der_schwelle_bleibt_alles_stehen(self):
        # Gegenprobe: ein kleines Bild bleibt eingebettet, sonst waere jede
        # Seite mit einem Symbol ploetzlich ein Ordner voller Dateien.
        #
        # Die Schwelle steht hier ueber 1000, weil das Muster selbst erst ab
        # 1000 Zeichen greift: mit 500 Zeichen wuerde der Test nur zeigen,
        # dass das Muster nicht passt, und die Schwelle nie beruehren.
        html, anhaenge = server.anhaenge_ausgliedern(
            self.bauen(2000), "probe", schwelle=3000)
        self.assertEqual(anhaenge, [])
        self.assertIn("data:image/png;base64,", html)

    def test_die_endung_kommt_aus_dem_inhalt(self):
        # "AAAA..." ist kein PNG - die Endung darf nicht aus dem Rufnamen
        # der Adresse geraten werden, sondern muss aus den Daten kommen.
        _, anhaenge = server.anhaenge_ausgliedern(
            self.bauen(2000), "probe", schwelle=1000)
        self.assertTrue(anhaenge[0]["name"].endswith(".bin"),
                        anhaenge[0]["name"])

    def test_die_datei_traegt_den_inhalt(self):
        html, anhaenge = server.anhaenge_ausgliedern(
            self.bauen(2000), "probe", schwelle=1000)
        import base64
        self.assertEqual(anhaenge[0]["daten"], base64.b64decode("A" * 2000))

    def test_zwei_bilder_werden_zwei_dateien(self):
        roh = self.bauen(2000).replace("</body>",
                                       '<img src="data:image/png;base64,%s">'
                                       "</body>" % ("A" * 2400))
        html, anhaenge = server.anhaenge_ausgliedern(roh, "probe", schwelle=1000)
        self.assertEqual(len(anhaenge), 2, anhaenge)
        self.assertEqual(len({a["name"] for a in anhaenge}), 2,
                         "beide Bilder heissen gleich")
        for a in anhaenge:
            self.assertIn('src="anhaenge/%s"' % a["name"], html)


if __name__ == "__main__":
    unittest.main()
