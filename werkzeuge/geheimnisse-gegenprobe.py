#!/usr/bin/env python3
"""Gegenprobe zu geheimnisse-pruefen.sh (CLAUDE.md §13a).

Eine gruene Pruefung beweist nichts, solange nicht gezeigt ist, dass sie
ueberhaupt etwas finden kann. Also werden hier Fehler eingebaut - einer
nach dem anderen, jeder fuer sich - und es wird verlangt, dass die
Pruefung bei JEDEM rot wird. Ein Fehler, der durchkommt, ist eine
Testluecke und wird hier gemeldet, nicht weggeredet.

Gearbeitet wird auf einer KOPIE im Kratzblock. Nie am Stack selbst: eine
Probe, die ueber "git checkout" zurueckrollt, nimmt eine noch nicht
eingecheckte Korrektur mit (N-34).

Aufruf (ueber das Pruefskript):
    ./werkzeuge/geheimnisse-pruefen.sh --gegenprobe
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Was die Pruefung liest. Steht hier etwas nicht drin, faellt das sofort
# auf: der Grundlauf auf der Kopie muss gruen sein, bevor eine einzige
# Mutation laeuft.
KOPIEREN = [
    ".gitignore",
    "werkzeuge/prolo",
    "werkzeuge/geheimnisse.py",
    "werkzeuge/geheimnisse-pruefen.sh",
]
JE_WERKZEUG = ["docker-compose.yml", "geheimnisse.conf", ".env.beispiel",
               "dynamic/einlass.yml.beispiel", ".gitignore"]


def kopieren(stack, ziel):
    for rel in KOPIEREN:
        q = os.path.join(stack, rel)
        if not os.path.isfile(q):
            sys.exit("Fehlt im Stack: %s" % rel)
        z = os.path.join(ziel, rel)
        os.makedirs(os.path.dirname(z), exist_ok=True)
        shutil.copy(q, z)
    for d in sorted(os.listdir(stack)):
        if not os.path.isfile(os.path.join(stack, d, "docker-compose.yml")):
            continue
        for rel in JE_WERKZEUG:
            q = os.path.join(stack, d, rel)
            if not os.path.isfile(q):
                continue
            z = os.path.join(ziel, d, rel)
            os.makedirs(os.path.dirname(z), exist_ok=True)
            shutil.copy(q, z)


# ------------------------------------------------------------ Werkzeug

def lies(wurzel, rel):
    with open(os.path.join(wurzel, rel), encoding="utf-8") as f:
        return f.read()


def schreib(wurzel, rel, inhalt):
    with open(os.path.join(wurzel, rel), "w", encoding="utf-8") as f:
        f.write(inhalt)


def tausch(wurzel, rel, alt, neu, anzahl=1):
    """Ersetzt und besteht darauf, dass es etwas zu ersetzen gab.

    Sonst waere die Mutation gar nicht eingebaut - und "die Pruefung hat
    sie nicht gefunden" hiesse dann nur, dass es nichts zu finden gab.
    """
    inhalt = lies(wurzel, rel)
    if inhalt.count(alt) < anzahl:
        raise AssertionError("Textstelle nicht gefunden in %s:\n  %r"
                             % (rel, alt[:90]))
    schreib(wurzel, rel, inhalt.replace(alt, neu, anzahl))


# ------------------------------------------------------------ Mutationen
# Jede bekommt einen Namen, der sagt, WAS kaputtgeht - nicht, welche Zeile
# angefasst wird.

def m_conf_vier_felder(w):
    tausch(w, "wiki/geheimnisse.conf", "PROLO_EINLASS|.env|env|harmlos|",
           "PROLO_EINLASS|.env|env|")


def m_conf_form_erfunden(w):
    tausch(w, "wiki/geheimnisse.conf", "|.env|env|harmlos|",
           "|.env|ini|harmlos|")


def m_conf_wechsel_erfunden(w):
    tausch(w, "wiki/geheimnisse.conf", "|.env|env|harmlos|",
           "|.env|env|egal|")


def m_conf_name_klein(w):
    tausch(w, "wiki/geheimnisse.conf", "\nPROLO_EINLASS|", "\nprolo_einlass|")


def m_conf_erklaerung_leer(w):
    inhalt = lies(w, "wiki/geheimnisse.conf")
    inhalt = re.sub(r"^(PROLO_EINLASS\|[^|]*\|[^|]*\|[^|]*\|).*$",
                    r"\1kurz", inhalt, flags=re.M)
    schreib(w, "wiki/geheimnisse.conf", inhalt)


def m_conf_wert_darin(w):
    tausch(w, "wiki/geheimnisse.conf", "|harmlos|Die Marke",
           "|harmlos|Zur Zeit steht dort ERFUNDENerWert0000nichtEchtXYZ - Die Marke")


def m_conf_datei_erfunden(w):
    tausch(w, "wiki/geheimnisse.conf", "PROLO_EINLASS|.env|",
           "PROLO_EINLASS|.umgebung|")


def m_conf_name_vertippt(w):
    tausch(w, "wiki/geheimnisse.conf", "\nPROLO_EINLASS|", "\nPROLO_EINLAS|")


def m_beispiel_traegt_wert(w):
    tausch(w, "wiki/.env.beispiel", "\nPROLO_EINLASS=\n",
           "\nPROLO_EINLASS=ERFUNDENerWert0000nichtEchtXYZ\n")


def m_neues_geheimnis_unerklaert(w):
    schreib(w, "wiki/.env.beispiel",
            lies(w, "wiki/.env.beispiel")
            + "\n# frisch dazugekommen\nWIKI_API_TOKEN=\n")


def m_stellen_uneinig(w):
    tausch(w, "traefik/geheimnisse.conf", "|yaml|harmlos|", "|yaml|haende|")


def m_gitignore_ohne_merkzettel(w):
    tausch(w, ".gitignore", "merkzettel/\n", "")


def m_gitignore_ohne_stand(w):
    tausch(w, ".gitignore", ".geheimnis-stand\n", "")


def m_prolo_ohne_root(w):
    tausch(w, "werkzeuge/prolo", 'root_noetig geheimnisse "$@"\n', "")


def m_prolo_ohne_befehl(w):
    inhalt = lies(w, "werkzeuge/prolo")
    inhalt = re.sub(r"^ *geheimnisse\|secrets\).*\n( *exec python3.*\n)?",
                    "", inhalt, flags=re.M)
    schreib(w, "werkzeuge/prolo", inhalt)


def m_haende_wird_doch_gewechselt(w):
    """Der gefaehrlichste Fehler: das Werkzeug fasst PG_PASS doch an."""
    tausch(w, "werkzeuge/geheimnisse.py",
           '            print("      4. Dienst neu starten und anmelden probieren")\n'
           "            continue\n",
           '            print("      4. Dienst neu starten und anmelden probieren")\n')


def m_zwei_stellen_zwei_werte(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "            g.schreiben(neu)\n",
           "            g.schreiben(wuerfeln())\n")


def m_uebersicht_zeigt_wert(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           '        for g in stellen:\n            print("      %s/%s" % (g.werkzeug, g.datei))\n',
           '        for g in stellen:\n            print("      %s/%s = %s" % (g.werkzeug, g.datei, g.lesen()))\n')


def m_uebersicht_bleibt_gruen(w):
    tausch(w, "werkzeuge/geheimnisse.py", "    return 1 if warnung else 0\n",
           "    return 0\n")


def m_sicherungsfrage_wirkungslos(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           'if not fragen("Liegt eine frische Sicherung vor (prolo sichern)?"):',
           'if False:')


def m_merkzettel_ohne_schluessel(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "    if not os.path.exists(SCHLUESSEL):\n", "    if False:\n")


def m_merkzettel_fuer_alle_lesbar(w):
    tausch(w, "werkzeuge/geheimnisse.py", "    os.chmod(pfad, 0o600)\n",
           "    os.chmod(pfad, 0o644)\n")


def m_schreiben_zerlegt_die_datei(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "            f.write(muster.sub(ersatz, inhalt, count=1))\n",
           "            f.write(ersatz + chr(10))\n")


def m_wuerfeln_zu_kurz(w):
    tausch(w, "werkzeuge/geheimnisse.py", "secrets.token_bytes(33)",
           "secrets.token_bytes(4)")


def m_merkzettel_ohne_werte(w):
    """Ein Zettel, auf dem nichts steht, faellt beim Lesen nicht auf."""
    tausch(w, "werkzeuge/geheimnisse.py",
           '        zeilen += ["%s" % name,\n                   "  %s" % werte.pop(),',
           '        zeilen += ["%s" % name,\n                   "  (siehe Server)",')


def m_schluesselpruefung_erst_am_ende(w):
    """Die Pruefung auf den Sicherungsschluessel faellt weg - der Wechsel
    laeuft durch und scheitert erst beim Schreiben des Zettels, wenn die
    neuen Werte schon in den Dateien stehen und der alte weg ist."""
    tausch(w, "werkzeuge/geheimnisse.py",
           "    if not os.path.exists(SCHLUESSEL) or shutil.which(\"age\") is None:\n"
           "        print(rot(\"  Der Merkzettel liesse sich am Ende nicht schreiben.\"))\n",
           "    if False:\n"
           "        print(rot(\"  Der Merkzettel liesse sich am Ende nicht schreiben.\"))\n")


def m_zettel_ohne_alten_wert(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           '                       "  alt : %s" % (alt or "(war nicht gesetzt)"),\n',
           "")


def m_stelle_fuer_stelle(w):
    """Der teuerste Fehler: wieder Stelle fuer Stelle schreiben, statt
    vorher alle zu pruefen. Traefik traegt dann die neue Marke und die
    Werkzeuge die alte (N-52)."""
    tausch(w, "werkzeuge/geheimnisse.py",
           "def klemmen(stellen):\n",
           "def klemmen(stellen):\n    return []  # Mutation\n")


def m_halber_wechsel_bleibt_gruen(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "            gestockt = True\n", "            pass\n")


def m_fehlende_datei_faellt_nicht_auf(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "        if not os.path.exists(self.pfad):\n            return (\"die Datei fehlt.",
           "        if False:\n            return (\"die Datei fehlt.")


def m_fehlende_zeile_faellt_nicht_auf(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "        if not self._muster().search(inhalt):\n            vorlage =",
           "        if False:\n            vorlage =")


def m_gitignore_frisst_die_vorlage(w):
    tausch(w, "bordbuch/.gitignore", "!.env.beispiel\n", "")


def m_vorlage_fehlt(w):
    import os as _os
    _os.remove(_os.path.join(w, "bordbuch", ".env.beispiel"))


def m_verteilen_ueberschreibt(w):
    """--verteilen fasst auch die Stellen an, die schon einen Wert haben."""
    tausch(w, "werkzeuge/geheimnisse.py",
           "        leer = [g for g, w in zip(stellen, werte) if not w]\n",
           "        leer = list(stellen)\n")


def m_verteilen_entscheidet_selbst(w):
    """Bei zwei verschiedenen Werten nimmt es einfach einen."""
    tausch(w, "werkzeuge/geheimnisse.py",
           "        if len(verschieden) > 1:\n", "        if False:\n")


def m_verteilen_wuerfelt_je_stelle(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "        for g in leer:\n            g.schreiben(wert)\n",
           "        for g in leer:\n            g.schreiben(wuerfeln())\n")


def m_verteilen_ohne_zettel(w):
    tausch(w, "werkzeuge/geheimnisse.py",
           "    pfad = merkzettel_schreiben(zettel)\n"
           '    print("\\n  " + fett("Merkzettel: %s" % pfad))\n'
           '    print("  Hol ihn auf den Arbeitsrechner und sortiere die Werte in")\n'
           '    print("  den Passwortmanager ein:")\n',
           "    pfad = None\n"
           '    if False:\n'
           '        print("  Hol ihn auf den Arbeitsrechner und sortiere die Werte in")\n'
           '        print("  den Passwortmanager ein:")\n')


MUTATIONEN = [
    ("conf-Zeile hat nur vier Felder",              m_conf_vier_felder),
    ("conf nennt eine erfundene FORM",              m_conf_form_erfunden),
    ("conf nennt eine erfundene WECHSEL-Art",       m_conf_wechsel_erfunden),
    ("conf-NAME ist kleingeschrieben",              m_conf_name_klein),
    ("conf-Erklaerung sagt nichts",                 m_conf_erklaerung_leer),
    ("in der conf steht ein Wert",                  m_conf_wert_darin),
    ("conf zeigt auf eine Datei, die es nicht gibt", m_conf_datei_erfunden),
    ("conf-NAME ist vertippt",                      m_conf_name_vertippt),
    ("die Beispieldatei traegt einen echten Wert",  m_beispiel_traegt_wert),
    ("neues Geheimnis ohne conf-Eintrag",           m_neues_geheimnis_unerklaert),
    ("zwei Stellen, zwei WECHSEL-Arten",            m_stellen_uneinig),
    (".gitignore laesst merkzettel/ durch",         m_gitignore_ohne_merkzettel),
    (".gitignore laesst .geheimnis-stand durch",    m_gitignore_ohne_stand),
    ("prolo geheimnisse laeuft ohne root",          m_prolo_ohne_root),
    ("prolo kennt den Befehl nicht mehr",           m_prolo_ohne_befehl),
    ("ein haende-Geheimnis wird doch gewechselt",   m_haende_wird_doch_gewechselt),
    ("zwei Stellen bekommen zwei verschiedene Werte", m_zwei_stellen_zwei_werte),
    ("die Uebersicht zeigt die Werte",              m_uebersicht_zeigt_wert),
    ("UNEINIG bleibt ohne roten Ruecklauf",         m_uebersicht_bleibt_gruen),
    ("die Frage nach der Sicherung ist wirkungslos", m_sicherungsfrage_wirkungslos),
    ("Merkzettel auch ohne Sicherungsschluessel",   m_merkzettel_ohne_schluessel),
    ("Merkzettel ist fuer alle lesbar",             m_merkzettel_fuer_alle_lesbar),
    ("Schreiben wirft den Rest der Datei weg",      m_schreiben_zerlegt_die_datei),
    ("gewuerfelt wird viel zu kurz",                m_wuerfeln_zu_kurz),
    ("der Merkzettel enthaelt keine Werte",         m_merkzettel_ohne_werte),
    ("der Schluessel wird erst am Ende geprueft",   m_schluesselpruefung_erst_am_ende),
    ("der Zettel nennt den alten Wert nicht mehr",  m_zettel_ohne_alten_wert),
    ("wieder Stelle fuer Stelle geschrieben",       m_stelle_fuer_stelle),
    ("ein halber Wechsel bleibt ohne Fehlschlag",   m_halber_wechsel_bleibt_gruen),
    ("eine fehlende Datei faellt nicht auf",        m_fehlende_datei_faellt_nicht_auf),
    ("eine fehlende Zeile faellt nicht auf",        m_fehlende_zeile_faellt_nicht_auf),
    (".gitignore frisst die eigene Vorlage",        m_gitignore_frisst_die_vorlage),
    ("die Vorlage fehlt ganz",                      m_vorlage_fehlt),
    ("--verteilen ueberschreibt vorhandene Werte",  m_verteilen_ueberschreibt),
    ("--verteilen entscheidet bei Uneinigkeit",     m_verteilen_entscheidet_selbst),
    ("--verteilen wuerfelt je Stelle einzeln",      m_verteilen_wuerfelt_je_stelle),
    ("--verteilen schreibt keinen Zettel",         m_verteilen_ohne_zettel),
]


def pruefen(pruefskript, wurzel):
    p = subprocess.run(["bash", pruefskript, "--stack", wurzel],
                       capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def main():
    stack, pruefskript = sys.argv[1], sys.argv[2]
    basis = tempfile.mkdtemp(prefix="geheimnis-gegenprobe-")
    rein = os.path.join(basis, "rein")
    os.makedirs(rein)
    kopieren(stack, rein)

    # Ohne einen gruenen Grundlauf sagt jedes spaetere "rot" nichts.
    rc, aus = pruefen(pruefskript, rein)
    if rc != 0:
        print("Der Grundlauf auf der Kopie ist schon rot - so kann keine")
        print("Mutation etwas zeigen. Ausgabe:\n")
        print("\n".join(z for z in aus.splitlines() if z.startswith("FEHLER")))
        shutil.rmtree(basis, ignore_errors=True)
        return 2
    print("Grundlauf auf der Kopie: gruen. %d Mutationen.\n" % len(MUTATIONEN))

    durchgerutscht = []
    for nr, (name, bauen) in enumerate(MUTATIONEN, 1):
        w = os.path.join(basis, "m%02d" % nr)
        shutil.copytree(rein, w)
        try:
            bauen(w)
        except AssertionError as e:
            print("%2d. %-48s NICHT EINGEBAUT (%s)" % (nr, name, e))
            durchgerutscht.append(name + " [nicht einbaubar]")
            continue
        rc, aus = pruefen(pruefskript, w)
        gefunden = [z for z in aus.splitlines() if z.startswith("FEHLER")]
        if rc != 0 and gefunden:
            print("%2d. %-48s gefunden: %s" % (nr, name, gefunden[0][7:60].strip()))
        else:
            print("%2d. %-48s DURCHGERUTSCHT" % (nr, name))
            durchgerutscht.append(name)
        shutil.rmtree(w, ignore_errors=True)

    shutil.rmtree(basis, ignore_errors=True)
    print("")
    if durchgerutscht:
        print("%d von %d Mutationen blieben unentdeckt:"
              % (len(durchgerutscht), len(MUTATIONEN)))
        for n in durchgerutscht:
            print("  - %s" % n)
        print("\nDas ist eine Testluecke, keine Meinungsfrage (§13a).")
        return 1
    print("Alle %d Mutationen wurden gefunden." % len(MUTATIONEN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
