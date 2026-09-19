"""Jede Route gegen jede Rolle - die Frage, um die es geht.

„Wenn ich jemandem `wiki-nutzer` gebe, darf dieser in keinem Fall auf die
Verwaltungsseite kommen, auch nicht, wenn er mit JSON versucht, da was
vorzugaukeln."

Die einzelnen Rechteproben stehen verstreut in test_dienst.py und pruefen
je einen Fall. Hier steht die VOLLSTAENDIGE Tabelle an einer Stelle: jede
Route, jede Rolle, ein Erwartungswert. Damit ist die Frage dauerhaft
beantwortbar - und es faellt auf, wenn sich morgen etwas daran aendert.

Die Erwartungswerte sind VON HAND eingetragen (CLAUDE.md §13), abgeleitet
aus den Regeln und nicht aus der Ausgabe des Codes:

  401  nicht angemeldet - oder nicht ueber den Zugang gekommen (N-44)
  403  angemeldet, aber die Gruppe reicht nicht
  DURCH  angemeldet und berechtigt; welcher Erfolgscode genau herauskommt,
         haengt vom Inhalt ab und wird anderswo geprueft. Hier zaehlt nur:
         es scheitert NICHT an der Berechtigung.

Aufruf:  python3 -m unittest discover -s tests -t tests
"""
import unittest

from test_dienst import Dienst, SEITE

DURCH = "DURCH"

# Die Rollen. "fremd" ist der Fall, den man leicht vergisst: jemand mit
# einer Verwaltungsgruppe eines ANDEREN Werkzeugs. Das Wiki beachtet nur
# Gruppen, die mit "wiki" anfangen (§17) - bordbuch-admin ist hier also
# genau so viel wert wie gar keine Gruppe.
ROLLEN = {
    "anonym":   (None,     ""),
    "nutzer":   ("lena",   "wiki-nutzer"),
    "fremd":    ("mika",   "bordbuch-admin,vertrieb"),
    "editor":   ("erik",   "wiki-editor"),
    "admin":    ("artur",  "wiki-admin"),
}

# Die Tabelle. Ein Eintrag je Route.
MATRIX = [
    # --- ohne Anmeldung erreichbar, ausdruecklich (§19) -----------------
    ("GET",  "/api/version",   None, dict(anonym=DURCH, nutzer=DURCH, fremd=DURCH,
                                          editor=DURCH, admin=DURCH)),
    ("GET",  "/gesundheit",    None, dict(anonym=DURCH, nutzer=DURCH, fremd=DURCH,
                                          editor=DURCH, admin=DURCH)),

    # --- lesen: angemeldet genuegt -------------------------------------
    ("GET",  "/api/ich",       None, dict(anonym=401, nutzer=DURCH, fremd=DURCH,
                                          editor=DURCH, admin=DURCH)),
    ("GET",  "/api/baum",      None, dict(anonym=401, nutzer=DURCH, fremd=DURCH,
                                          editor=DURCH, admin=DURCH)),
    ("GET",  "/api/suche?q=probe", None, dict(anonym=401, nutzer=DURCH, fremd=DURCH,
                                              editor=DURCH, admin=DURCH)),

    # --- die Verwaltung: NUR wiki-admin --------------------------------
    ("GET",  "/api/verwaltung", None, dict(anonym=401, nutzer=403, fremd=403,
                                           editor=403, admin=DURCH)),
    ("POST", "/api/rechte",   {"slug": "matrix-seite", "gruppen": []},
                                    dict(anonym=401, nutzer=403, fremd=403,
                                         editor=403, admin=DURCH)),
    ("POST", "/api/zweig",    {"pfad": "Technik", "gruppen": []},
                                    dict(anonym=401, nutzer=403, fremd=403,
                                         editor=403, admin=DURCH)),
    ("POST", "/api/neuindex", {},   dict(anonym=401, nutzer=403, fremd=403,
                                         editor=403, admin=DURCH)),

    # --- schreiben: ab wiki-editor -------------------------------------
    ("POST", "/api/pruefen",  "HTML", dict(anonym=401, nutzer=403, fremd=403,
                                           editor=DURCH, admin=DURCH)),
    ("POST", "/api/import",   "HTML", dict(anonym=401, nutzer=403, fremd=403,
                                           editor=DURCH, admin=DURCH)),

    # --- eigene Einstellungen: jeder Angemeldete fuer sich selbst ------
    ("POST", "/api/einstellungen", {"theme": "dark"},
                                    dict(anonym=401, nutzer=DURCH, fremd=DURCH,
                                         editor=DURCH, admin=DURCH)),
    ("POST", "/api/lesezeichen", {"slug": "matrix-seite", "an": True},
                                    dict(anonym=401, nutzer=DURCH, fremd=DURCH,
                                         editor=DURCH, admin=DURCH)),
]


class Rechtematrix(Dienst):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Eine Seite, die artur gehoert - damit die Routen etwas zum
        # Anfassen haben und ein 404 nicht mit einem 403 verwechselt wird.
        cls().seite_einspielen("matrix-seite", titel="Matrix")

    def erwartet(self, rolle, weg, methode, daten, soll):
        nutzer, gruppen = ROLLEN[rolle]
        inhalt = daten
        typ = "application/json"
        if daten == "HTML":
            inhalt = (SEITE % {"slug": "matrix-neu", "titel": "Neu"}).encode()
            typ = "text/html"
        if nutzer is None:
            # Nicht angemeldet heisst: keine Identitaetskopfzeile. Die Marke
            # der Vertrauensgrenze ist trotzdem da - sonst pruefte dieser
            # Fall N-44 und nicht die Berechtigung.
            code, _ = self.ruf(weg, nutzer="", gruppen="", daten=inhalt,
                               methode=methode, typ=typ)
        else:
            code, _ = self.ruf(weg, nutzer=nutzer, gruppen=gruppen, daten=inhalt,
                               methode=methode, typ=typ)
        if soll == DURCH:
            self.assertNotIn(code, (401, 403),
                             "%s als %s: an der Berechtigung gescheitert (%d)"
                             % (weg, rolle, code))
        else:
            self.assertEqual(code, soll, "%s als %s" % (weg, rolle))

    def test_die_ganze_matrix(self):
        for methode, weg, daten, zeile in MATRIX:
            for rolle, soll in zeile.items():
                with self.subTest(weg=weg, rolle=rolle):
                    self.erwartet(rolle, weg, methode, daten, soll)

    def test_fremde_gruppen_zaehlen_im_wiki_nicht(self):
        """Der Gruppenfilter aus §17, an seiner Wirkung gemessen.

        Die Probe "fremde Gruppen zaehlen mit" liess die Matrix zuerst
        gruen: bordbuch-admin ist auch ohne Filter kein wiki-admin, also
        aendert sich an den Rechten nichts. Der Filter tut etwas anderes -
        er haelt fremde Gruppen aus allem heraus, was das Wiki ueber einen
        Nutzer weiss und was es ihn freigeben laesst. Genau das steht hier.
        """
        code, ich = self.ruf("/api/ich", nutzer="mika",
                             gruppen="bordbuch-admin,vertrieb,wiki-nutzer")
        self.assertEqual(code, 200)
        self.assertEqual(sorted(ich["gruppen"]), ["wiki-nutzer"],
                         "fremde Gruppen stehen in den Wiki-Gruppen")
        self.assertEqual(sorted(ich["gruppen_andere"]),
                         ["bordbuch-admin", "vertrieb"])

    def test_eine_fremde_gruppe_laesst_sich_nicht_freigeben(self):
        # Sonst waere die Seite fuer alle unsichtbar und fuer niemanden
        # sichtbar (N-21) - und ein Verwalter koennte Rechte an Gruppen
        # vergeben, ueber die das Wiki gar nichts weiss.
        code, _ = self.ruf("/api/rechte", nutzer="artur", gruppen="wiki-admin",
                           daten={"slug": "matrix-seite",
                                  "gruppen": ["bordbuch-admin"]})
        self.assertEqual(code, 400)

    def test_die_matrix_ist_vollstaendig(self):
        # Ohne das waere eine leere Tabelle ein gruener Test.
        felder = sum(len(z[3]) for z in MATRIX)
        self.assertGreaterEqual(felder, 60, "die Matrix hat nur %d Felder" % felder)
        for methode, weg, daten, zeile in MATRIX:
            self.assertEqual(set(zeile), set(ROLLEN),
                             "%s laesst eine Rolle aus" % weg)


if __name__ == "__main__":
    unittest.main()
