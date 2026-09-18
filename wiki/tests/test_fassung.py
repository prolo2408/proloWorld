"""Die Fassung steht an drei Stellen - und muss ueberall dieselbe sein (B-23).

Der Befund B-23 verlangt die Fassungsnummer an drei Stellen: in `server.py`
(`VERSION`, das zeigt der laufende Dienst an), in `docker-compose.yml` hinter
`image:` (danach benennt Docker das gebaute Abbild) und in `CHANGELOG.md` als
Ueberschrift (dort steht, was drin ist).

Warum das zusammenpassen muss: Das Abbild wird aus dem eigenen Dockerfile
gebaut. Bleibt der Kennsatz beim Veroeffentlichen stehen, ueberschreibt der
Bau das alte Abbild - und der Rueckweg auf die vorige Fassung ist weg, obwohl
`aktualisieren.sh` ihn im Protokoll noch nennt. Und ein Dienst, der sich als
1.2.0 meldet, waehrend das Abbild 1.3.0 heisst, macht jede Fehlersuche am
Server zum Ratespiel.

Geprueft wurde das bisher nur im Kopf. Diese Datei fuehrt es aus.

Erwartungswerte von Hand (CLAUDE.md §13).

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import os
import re
import unittest

from hilfe import server, WURZEL


def gelesen(name):
    with open(os.path.join(WURZEL, name), encoding="utf-8") as datei:
        return datei.read()


class DieDreiStellen(unittest.TestCase):

    def test_die_fassung_sieht_aus_wie_eine_fassung(self):
        # Von Hand: drei Zahlen, durch Punkte getrennt - nichts anderes.
        self.assertRegex(server.VERSION, r"^\d+\.\d+\.\d+$")

    def test_das_abbild_traegt_dieselbe_nummer(self):
        # Die Zeile lautet "    image: wiki:1.2.0" - der Kommentarblock
        # darueber enthaelt weitere image:-Woerter, darum wird der Anfang
        # der Zeile verlangt.
        zeilen = [z.strip() for z in gelesen("docker-compose.yml").splitlines()
                  if re.match(r"^\s*image:", z)]
        self.assertEqual(len(zeilen), 1, "genau eine image:-Zeile erwartet, "
                                         "gefunden: %r" % (zeilen,))
        self.assertEqual(zeilen[0], "image: wiki:%s" % server.VERSION)

    def test_die_aenderungsliste_kennt_die_fassung(self):
        ueberschriften = re.findall(r"^## .*$", gelesen("CHANGELOG.md"),
                                    re.MULTILINE)
        gesucht = "## Fassung %s" % server.VERSION
        self.assertIn(gesucht, ueberschriften,
                      "Ueberschrift %r fehlt. Vorhanden: %r"
                      % (gesucht, ueberschriften))

    def test_die_fassung_steht_ganz_oben(self):
        # Sonst waechst eine neue Fassung unter eine aeltere - dann stimmt die
        # Ueberschrift zwar, aber die Liste liest sich verkehrt herum.
        fassungen = re.findall(r"^## Fassung (\S+)", gelesen("CHANGELOG.md"),
                               re.MULTILINE)
        self.assertTrue(fassungen, "keine einzige Fassungsueberschrift")
        self.assertEqual(fassungen[0], server.VERSION)


if __name__ == "__main__":
    unittest.main()
