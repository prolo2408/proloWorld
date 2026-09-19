#!/usr/bin/env python3
"""Nennen die Anleitungen nur Befehle, die es wirklich gibt? (N-51)

Aufgerufen von werkzeuge/prolo-pruefen.sh; laeuft auch allein:

    python3 werkzeuge/prolo-befehle-pruefen.py /opt/stack
    python3 werkzeuge/prolo-befehle-pruefen.py --gegenprobe

Die Liste der Befehle wird aus dem Verteiler in "prolo" gelesen, nicht
gepflegt - eine zweite Liste waere genau die Sorte, die veraltet.
"""
import os, re, sys

# prolo steht an BEFEHLSSTELLE: am Zeilenanfang, hinter sudo, hinter einer
# Eingabeaufforderung oder hinter &&/;/|. Alles andere ist Fliesstext oder
# eine Dateiliste ("-rw------- 1 prolo prolo acme.json").
BEFEHL = re.compile(
    r"(?:^|[\n]|&&\s*|;\s*|\|\s*|\$\s+)[ \t]*(?:sudo\s+)?prolo[ \t]+([a-z][a-z\-]{1,15})\b")

def kennt_prolo(stack):
    t = open(os.path.join(stack, "werkzeuge", "prolo"), encoding="utf-8").read()
    fall = re.search(r"^BEFEHL=.*?^esac", t, re.S | re.M).group(0)
    aus = set()
    for m in re.finditer(r"^\s{2}([a-z|\-]+)\)", fall, re.M):
        aus |= set(m.group(1).split("|"))
    return aus

def stellen(text, html):
    s = []
    if html:
        s += re.findall(r"<code[^>]*>(.*?)</code>", text, re.S)
        s += re.findall(r"<pre[^>]*>(.*?)</pre>", text, re.S)
    s += re.findall(r"```(.*?)```", text, re.S)
    s += re.findall(r"`([^`\n]{1,200})`", text)
    s += re.findall(r"(sudo prolo [a-z][a-z\-]*)", text)
    return s


# Das Narbenbuch ist keine Anleitung. Es ZITIERT falsche Befehle, weil das
# der Befund ist - "sudo prolo compose" steht dort mit Absicht. Wer es
# mitprueft, bekommt eine Meldung ueber den eigenen Eintrag ueber die
# Meldung. Genau in diese Falle ist diese Pruefung bei ihrem ersten Lauf
# getappt (N-51). Ausgenommen wird darum GENAU diese eine Datei, und zwar
# mit Namen: jede weitere Ausnahme waere ein Loch.
NARBENBUCH = "NEUE-BEFUNDE.md"


def pruefen(wurzel):
    kennt = kennt_prolo(wurzel)
    treffer = set()
    for ordner, _, dateien in os.walk(wurzel):
        if any(t in ordner for t in (".git", "node_modules", "__pycache__", "schriften")):
            continue
        for d in dateien:
            if not d.endswith((".md", ".html")) and d != "prolo":
                continue
            if d == NARBENBUCH:
                continue
            p = os.path.join(ordner, d)
            t = open(p, encoding="utf-8", errors="replace").read()
            for st in stellen(t, d.endswith(".html")):
                # In der Wiki-Seite stehen Zeilenumbrueche als \n im JSON.
                for m in BEFEHL.finditer(st.replace("\\n", "\n")):
                    if m.group(1) not in kennt:
                        treffer.add((os.path.relpath(p, wurzel), m.group(1)))
    return treffer, kennt


def melden(wurzel):
    treffer, kennt = pruefen(wurzel)
    if not treffer:
        print("ok     jeder dokumentierte prolo-Befehl gibt es auch "
              "(%d bekannte)" % len(kennt))
        return 0
    for p, w in sorted(treffer):
        print('FEHLER %s nennt "prolo %s" - den Befehl gibt es nicht' % (p, w))
    print("       bekannt sind: %s"
          % " ".join(sorted(k for k in kennt if not k.startswith("-"))))
    return 1


# ------------------------------------------------------------ Gegenprobe

DATEIEN = ["werkzeuge/prolo", "wiki/vorlagen/prolo-bedienen.html",
           "bordbuch/CHANGELOG.md", "CLAUDE.md", NARBENBUCH]


def _tausch(w, rel, alt, neu):
    p = os.path.join(w, rel)
    t = open(p, encoding="utf-8").read()
    if alt not in t:
        raise AssertionError("Textstelle fehlt in %s: %r" % (rel, alt[:60]))
    open(p, "w", encoding="utf-8").write(t.replace(alt, neu, 1))


MUTATIONEN = [
    ("Anleitungsseite nennt prolo compose",
     lambda w: _tausch(w, "wiki/vorlagen/prolo-bedienen.html",
                       "<code>sudo prolo start traefik</code>",
                       "<code>sudo prolo compose traefik up -d</code>")),
    ("Geruest-Kommentar nennt prolo compose",
     lambda w: _tausch(w, "werkzeuge/prolo",
                       "  #   sudo prolo start traefik\n",
                       "  #   sudo prolo compose traefik up -d\n")),
    ("Changelog nennt prolo sicherung",
     lambda w: _tausch(w, "bordbuch/CHANGELOG.md",
                       "`sudo prolo sichern`", "`sudo prolo sicherung`")),
    ("CLAUDE.md nennt einen erfundenen Befehl",
     lambda w: _tausch(w, "CLAUDE.md", "`prolo sichern`", "`prolo backupjetzt`")),
    # Die Ausnahme fuer das Narbenbuch darf nicht auf andere Dateien
    # abfaerben: eine Anleitung mit demselben Fehler muss weiter auffallen.
    ("Anleitung mit demselben Zitat wie im Narbenbuch",
     lambda w: _tausch(w, "CLAUDE.md", "`prolo status` sagt es.",
                       "`prolo compose` sagt es.")),
    # Der Fall, um dessentwillen es die Pruefung gibt: jemand benennt einen
    # Befehl um oder wirft ihn weg, und die Anleitungen nennen ihn weiter.
    ("ein Befehl faellt aus dem Verteiler",
     lambda w: _tausch(w, "werkzeuge/prolo",
                       '  sichern|backup)             root_noetig sichern;',
                       '  sichernXX|backup)           root_noetig sichern;')),
]


def gegenprobe():
    """Findet die Pruefung ueberhaupt etwas? (CLAUDE.md §13a)

    Gearbeitet wird auf Kopien im Kratzblock - nie am Stack selbst: eine
    Probe, die ueber "git checkout" zurueckrollt, nimmt eine noch nicht
    eingecheckte Korrektur mit (N-34).
    """
    import shutil, tempfile
    stack = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    basis = tempfile.mkdtemp(prefix="prolo-befehle-")

    def kopie(ziel):
        for rel in DATEIEN:
            z = os.path.join(ziel, rel)
            os.makedirs(os.path.dirname(z), exist_ok=True)
            shutil.copy(os.path.join(stack, rel), z)

    rein = os.path.join(basis, "rein")
    kopie(rein)
    if pruefen(rein)[0]:
        shutil.rmtree(basis, ignore_errors=True)
        print("Der Grundlauf auf der Kopie ist schon rot - so kann keine")
        print("Mutation etwas zeigen.")
        return 2
    print("Grundlauf auf der Kopie: gruen. %d Mutationen.\n" % len(MUTATIONEN))

    durch = []
    for nr, (name, bauen) in enumerate(MUTATIONEN, 1):
        w = os.path.join(basis, "m%d" % nr)
        kopie(w)
        try:
            bauen(w)
        except AssertionError as e:
            print("%d. %-42s NICHT EINGEBAUT (%s)" % (nr, name, e))
            durch.append(name + " [nicht einbaubar]")
            continue
        treffer = pruefen(w)[0]
        if treffer:
            print("%d. %-42s gefunden: prolo %s"
                  % (nr, name, sorted(treffer)[0][1]))
        else:
            print("%d. %-42s DURCHGERUTSCHT" % (nr, name))
            durch.append(name)
    shutil.rmtree(basis, ignore_errors=True)
    print("")
    if durch:
        print("%d von %d Mutationen blieben unentdeckt: %s"
              % (len(durch), len(MUTATIONEN), ", ".join(durch)))
        return 1
    print("Alle %d Mutationen wurden gefunden." % len(MUTATIONEN))
    return 0


if __name__ == "__main__":
    if "--gegenprobe" in sys.argv:
        sys.exit(gegenprobe())
    sys.exit(melden(sys.argv[1] if len(sys.argv) > 1 else "."))
