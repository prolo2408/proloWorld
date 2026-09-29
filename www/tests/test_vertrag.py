"""Der Vertrag mit dem Betrieb (CLAUDE.md, "DER VERTRAG MIT DEM STAPEL").

Diese Pruefungen standen bis zur Aufteilung in proloWorld
(werkzeuge/grenze-pruefen.sh). Dort liegt seitdem nur noch die
Herstellerdatei dieses Werkzeugs, nicht sein Code - was nur am Code
pruefbar ist, wird darum HIER geprueft. Sonst waere es beim Umzug still
verloren gegangen: eine Pruefung, die niemand mehr ausfuehrt, prueft nichts.

Dieselbe Datei liegt in wiki, bordbuch und www; sie liest alles, was sie
braucht, aus den Dateien des Werkzeugs selbst.
"""
import ast
import os
import re
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lies(name):
    with open(os.path.join(WURZEL, name), encoding="utf-8") as f:
        return f.read()


CODE = lies("server.py")
COMPOSE = lies("docker-compose.yml")


def grenze_erreichbar(code, einstieg, tiefe=2):
    """Fuehrt dieser Einstieg an einlass_pruefen vorbei - direkt oder ueber
    einen Helfer? Gelesen wird der Syntaxbaum, nicht der Text."""
    koerper = {k.name: k for k in ast.walk(ast.parse(code))
               if isinstance(k, ast.FunctionDef)}

    def rufe(name):
        aus = set()
        for x in ast.walk(koerper.get(name) or ast.Module(body=[], type_ignores=[])):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
                aus.add(x.func.attr)
            elif isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
                aus.add(x.func.id)
        return aus

    offen, gesehen = {einstieg}, set()
    for _ in range(tiefe + 1):
        if "einlass_pruefen" in offen:
            return True
        naechste = set()
        for n in offen - gesehen:
            gesehen.add(n)
            naechste |= rufe(n)
        offen = naechste
    return "einlass_pruefen" in offen


def freie_pfade(code):
    """Die Freiliste als Pfade - das Wiki schreibt sie in Teilen
    (["api", "version"]), die anderen als ganze Pfade."""
    m = re.search(r"EINLASS_FREI = (\(.*?\))\n", code, re.S)
    if not m:
        return set()
    return {w if isinstance(w, str) else "/" + "/".join(w)
            for w in ast.literal_eval(m.group(1))}


class TestVertrauensgrenze(unittest.TestCase):
    def test_beide_einstiege_fuehren_an_der_grenze_vorbei(self):
        for einstieg in ("do_GET", "do_POST"):
            with self.subTest(einstieg=einstieg):
                self.assertTrue(grenze_erreichbar(CODE, einstieg),
                                "%s erreicht einlass_pruefen nicht - eine "
                                "Haelfte offen ist nicht halb sicher" % einstieg)

    def test_frei_sind_genau_die_pfade_aus_dem_vertrag(self):
        frei = freie_pfade(CODE)
        self.assertIn("/gesundheit", frei)
        self.assertIn("/api/version", frei)
        self.assertNotIn("/", frei, "die Wurzel darf nie frei sein")

    def test_ohne_marke_startet_es_nicht(self):
        # Die Herstellerdatei bricht mit ":?" schon beim Hochfahren ab.
        self.assertRegex(COMPOSE, r'PROLO_EINLASS: "\$\{PROLO_EINLASS:\?')
        self.assertIn("PROLO_EINLASS", lies(".env.beispiel"))


class TestGruppen(unittest.TestCase):
    def test_jede_gepruefte_gruppe_steht_im_label(self):
        """N-95: "prolo einrichten" nennt die Gruppen aus dem Label. Fehlt
        eine, legt sie niemand an - und das Werkzeug sagt 403."""
        gilt = dict(re.findall(
            r'os\.environ\.get\("([A-Z_]*_GRUPPE)",\s*"([^"]+)"\)', CODE))
        self.assertTrue(gilt, "keine Gruppe im Code gefunden - dann prueft "
                              "dieser Test nichts")
        for var in list(gilt):
            u = re.search(r"^\s+%s:\s*\"?(?:\$\{%s:-)?([A-Za-z0-9_.-]+)"
                          % (var, var), COMPOSE, re.M)
            if u:
                gilt[var] = u.group(1)
        genannt = set()
        for m in re.finditer(r"prolo\.gruppen=([^\"\n]+)", COMPOSE):
            genannt |= {t.strip().partition("=")[0].strip()
                        for t in m.group(1).split(";")}
        self.assertEqual(sorted(set(gilt.values()) - genannt), [])


class TestHerstellerdatei(unittest.TestCase):
    def test_das_abbild_traegt_die_fassung_aus_dem_code(self):
        fassung = re.search(r'^VERSION = "([^"]+)"', CODE, re.M).group(1)
        name = re.search(r"^name:\s*(\S+)", COMPOSE, re.M).group(1)
        self.assertRegex(COMPOSE, r"(?m)^\s*image: ghcr\.io/prolo2408/%s:%s\s*(#.*)?$"
                         % (re.escape(name), re.escape(fassung)))

    def test_der_changelog_nennt_die_fassung_zuoberst(self):
        fassung = re.search(r'^VERSION = "([^"]+)"', CODE, re.M).group(1)
        oben = re.search(r"^## (?:Fassung )?(\d+\.\d+\.\d+)", lies("CHANGELOG.md"), re.M)
        self.assertEqual(oben.group(1) if oben else None, fassung)

    def test_was_zum_betrieb_gehoert_steht_nicht_hier(self):
        """Netz, Speichergrenzen und veroeffentlichte Ports sind Sache des
        Betriebs (proloWorld, docker-compose.override.yml)."""
        for verboten in (r"^\s*networks:", r"^\s*mem_limit:", r"^\s*ports:",
                         r"traefik\.docker\.network="):
            with self.subTest(verboten=verboten):
                self.assertNotRegex(COMPOSE, re.compile(verboten, re.M))


if __name__ == "__main__":
    unittest.main()
