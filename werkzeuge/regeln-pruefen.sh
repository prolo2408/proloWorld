#!/usr/bin/env bash
# werkzeuge/regeln-pruefen.sh
#
# Zeigen die Verweise auf die Regeln noch irgendwohin?
#
# Der Anlass: bis N-39 gab es zwei Regeldateien, ein Regelblatt und ein
# Betriebsregelwerk, und quer durch den Stack standen 148 Verweise darauf -
# in Kommentaren, in Tests, in Meldungen. Beim Zusammenziehen nach
# CLAUDE.md haben sich die Abschnittsnummern verschoben. Ein Verweis auf
# einen Abschnitt, den es nicht mehr gibt, faellt beim Lesen nicht auf: er
# sieht aus wie eine Begruendung und ist eine Sackgasse.
#
# Geprueft wird darum mechanisch:
#   1. Jeder Verweis "CLAUDE.md §N" trifft einen Abschnitt, den es gibt.
#   2. Niemand nennt die beiden abgeschafften Dateien mehr.
#   3. CLAUDE.md bringt die Bloecke mit, auf die sich die Werkzeuge berufen.
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

python3 - "$STACK" <<'PY'
import os, re, sys, io
stack = sys.argv[1]
regeln = os.path.join(stack, "CLAUDE.md")
fehler = 0

def sag(ok, text, zusatz=""):
    global fehler
    if ok:
        print("ok     " + text)
    else:
        print("FEHLER " + text + ("\n       " + zusatz if zusatz else ""))
        fehler = 1

if not os.path.exists(regeln):
    print("FEHLER CLAUDE.md fehlt"); sys.exit(1)
quelle = io.open(regeln, encoding="utf-8").read()

# 1. Welche Abschnitte gibt es? Ueberschrift "## 14." oder "### 8.1."
vorhanden = set(re.findall(r"^#{2,3}\s+(\d+[a-z]?(?:\.\d+)?)\.\s", quelle, re.M))
sag(len(vorhanden) >= 25, "CLAUDE.md hat %d nummerierte Abschnitte" % len(vorhanden))

# 2. Alle Verweise einsammeln
zitiert = {}
archiv = {}
for wurzel, ordner, namen in os.walk(stack):
    if ".git" in wurzel or "__pycache__" in wurzel or "/.archiv" in wurzel:
        continue
    for n in namen:
        p = os.path.join(wurzel, n)
        if p.endswith((".png", ".woff2", ".gz", ".age")) or p == regeln:
            continue
        try:
            s = io.open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for m in re.finditer(r"CLAUDE\.md\s+§(\d+[a-z]?(?:\.\d+)?)", s):
            zitiert.setdefault(m.group(1), set()).add(os.path.relpath(p, stack))
        # Die beiden Namen werden zusammengesetzt, nicht ausgeschrieben:
        # sonst faellt DIESE Datei ueber sich selbst. Genau dieselbe Falle
        # wie N-33 und N-36 - beim ersten Lauf hier prompt zugeschnappt.
        #
        # NEUE-BEFUNDE.md ist ausgenommen, und zwar ausdruecklich: es ist das
        # Archiv. Ein Archiv nennt, was es nicht mehr gibt - das ist sein
        # Zweck. Damit die Ausnahme kein Versteck wird, steht unten, wie oft
        # die Namen dort vorkommen.
        for alt in ("prolo-" + "regelblatt.md", "prolo-" + "betriebsregeln.md"):
            if alt not in s:
                continue
            if os.path.basename(p) == "NEUE-BEFUNDE.md":
                archiv[alt] = archiv.get(alt, 0) + s.count(alt)
                continue
            sag(False, "%s nennt noch %s" % (os.path.relpath(p, stack), alt))

# Und die Verweise IN der Datei selbst (N-98). Die erste Fassung las
# jede Datei ausser dieser - und CLAUDE.md verwies in §15 auf einen
# "Dreischritt aus §19a", den es nie gab (gemeint war §24a).
for m in re.finditer(r"§(\d+[a-z]?(?:\.\d+)?)", quelle):
    zitiert.setdefault(m.group(1), set()).add("CLAUDE.md")

fehlend = {k: v for k, v in zitiert.items() if k not in vorhanden}
sag(not fehlend, "jeder der %d zitierten Abschnitte gibt es wirklich" % len(zitiert),
    "; ".join("§%s (in %s)" % (k, ", ".join(sorted(v))) for k, v in sorted(fehlend.items())))

if archiv:
    print("       (im Archiv NEUE-BEFUNDE.md genannt: "
          + ", ".join("%s %dx" % (k, v) for k, v in sorted(archiv.items())) + ")")

# 3. Die Bloecke, auf die sich die Werkzeuge berufen
for was, muster in (("Farbtoken", r"--accent:oklch"),
                    ("Pflichtblock Fokus", r":focus-visible"),
                    ("Pflichtblock hidden", r"\[hidden\]\{display:none!important\}"),
                    ("Checkliste", r"^# TEIL IV — CHECKLISTE")):
    sag(re.search(muster, quelle, re.M) is not None,
        "CLAUDE.md enthaelt den Block: " + was)

print()
print("Alles gruen." if not fehler else "GEGENPROBE FEHLGESCHLAGEN.", file=sys.stderr if fehler else sys.stdout)
sys.exit(fehler)
PY
