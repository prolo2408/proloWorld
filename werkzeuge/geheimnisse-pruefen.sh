#!/usr/bin/env bash
# werkzeuge/geheimnisse-pruefen.sh
#
# Haelt der Bestand an Geheimnissen zusammen? (N-50)
#
# "prolo geheimnisse" liest, was jedes Werkzeug in seiner geheimnisse.conf
# ueber seine eigenen Geheimnisse sagt. Das ist genau die Sorte Liste, die
# lautlos veraltet: jemand ergaenzt ein Werkzeug um ein Token, traegt es
# nicht ein - und der Bestand zeigt weiter "alles gleich an allen", waehrend
# ein Geheimnis gar nicht mehr vorkommt. Eine Uebersicht, die etwas
# uebersieht, ist schlimmer als keine, weil man ihr glaubt.
#
# Darum zwei Sorten Pruefung:
#
#   Bau      die Listen gegen den Stack: jedes erklaerte Geheimnis hat
#            seine Datei, jede geheimnis-artige Zeile in einer
#            .env.beispiel ist erklaert, in keiner conf steht ein Wert.
#   Verhalten  ein nachgebauter Mini-Stack im Kratzblock, gegen den das
#            Werkzeug wirklich laeuft. Dass es ein "haende"-Geheimnis
#            nicht anfasst, glaubt man erst, wenn man es versucht hat.
#
# Aufruf:
#   ./werkzeuge/geheimnisse-pruefen.sh              gegen diesen Stack
#   ./werkzeuge/geheimnisse-pruefen.sh --stack PFAD gegen einen anderen
#   ./werkzeuge/geheimnisse-pruefen.sh --gegenprobe baut Fehler ein und
#                                                   verlangt, dass jeder
#                                                   auffaellt (§13a)
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
GEGENPROBE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --stack)      STACK="$2"; shift 2 ;;
    --gegenprobe) GEGENPROBE=1; shift ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
done

if [ "$GEGENPROBE" -eq 1 ]; then
  exec python3 "$HIER/geheimnisse-gegenprobe.py" "$STACK" "$HIER/geheimnisse-pruefen.sh"
fi

python3 - "$STACK" <<'PY'
import os, re, shutil, subprocess, sys, tempfile

stack = os.path.abspath(sys.argv[1])
fehler = 0

def sag(ok, text, zusatz=""):
    global fehler
    print(("ok     " if ok else "FEHLER ") + text
          + (("  -> " + zusatz) if zusatz and not ok else ""))
    if not ok:
        fehler += 1

def lies(*teile):
    p = os.path.join(stack, *teile)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()

FORMEN  = ("env", "yaml")
WECHSEL = ("harmlos", "sitzungen", "haende")

# Woran man eine Zeile in einer .env.beispiel als Geheimnis erkennt. Das
# ist eine Heuristik und darf eine sein: sie entscheidet NICHT, was ein
# Geheimnis ist - das sagt die conf - sondern stellt nur die Frage
# "warum steht das nicht drin?". Ein Fehlalarm kostet eine Zeile conf,
# ein uebersehenes Token kostet mehr.
VERDACHT = re.compile(r"(PASS|PASSWORT|SECRET|_KEY$|KEY_|TOKEN|EINLASS|SALT|"
                      r"PEPPER|CREDENTIAL|APIKEY|API_KEY)")

# Ein Wert sieht anders aus als ein Name: lang und gemischt.
BLOB = re.compile(r"[A-Za-z0-9+/=_-]{16,}")

def blobartig(text):
    for t in BLOB.findall(text):
        if (any(c.islower() for c in t) and any(c.isupper() for c in t)
                and any(c.isdigit() for c in t)):
            return t
    return None

# --- 1. Die conf-Dateien selbst ---------------------------------------
werkzeuge = sorted(d for d in os.listdir(stack)
                   if os.path.isfile(os.path.join(stack, d, "docker-compose.yml")))
sag(len(werkzeuge) >= 2, "mindestens zwei Werkzeuge gefunden (%d)" % len(werkzeuge),
    "ohne Werkzeuge prueft dieses Skript nichts und waere trotzdem gruen")

erklaert = {}          # werkzeug -> {name: (datei, form, wechsel)}
for werkzeug in werkzeuge:
    conf = lies(werkzeug, "geheimnisse.conf")
    if conf is None:
        erklaert[werkzeug] = {}
        continue
    erklaert[werkzeug] = {}
    for nr, zeile in enumerate(conf.splitlines(), 1):
        roh, zeile = zeile, zeile.strip()
        if not zeile or zeile.startswith("#"):
            continue
        ort = "%s/geheimnisse.conf:%d" % (werkzeug, nr)
        teile = [t.strip() for t in zeile.split("|")]
        if len(teile) != 5:
            sag(False, "%s hat %d Felder statt 5" % (ort, len(teile)), zeile[:60])
            continue
        name, datei, form, wechsel, erkl = teile
        sag(re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is not None,
            "%s: NAME ist ein Variablenname (%s)" % (ort, name))
        sag(form in FORMEN, "%s: FORM ist env oder yaml (%s)" % (ort, form))
        sag(wechsel in WECHSEL,
            "%s: WECHSEL ist harmlos/sitzungen/haende (%s)" % (ort, wechsel))
        sag(len(erkl) >= 30,
            "%s: die Erklaerung sagt etwas (%d Zeichen)" % (ort, len(erkl)),
            "wer den Bestand liest, soll wissen, was ein Wechsel kostet")
        blob = blobartig(roh)
        sag(blob is None, "%s enthaelt keinen Wert" % ort,
            "das sieht aus wie ein Geheimnis: %s..." % (blob or "")[:8])
        erklaert[werkzeug][name] = (datei, form, wechsel)

# --- 2. Jedes erklaerte Geheimnis hat seine Datei ----------------------
for werkzeug, eintraege in erklaert.items():
    for name, (datei, form, wechsel) in sorted(eintraege.items()):
        # Die echte Datei liegt nie im Git (§21) - die Beispieldatei
        # daneben schon, und sie ist die Vorlage fuer die echte.
        beispiel = lies(werkzeug, datei + ".beispiel")
        echt = lies(werkzeug, datei)
        sag(beispiel is not None or echt is not None,
            "%s/%s: es gibt %s oder %s.beispiel" % (werkzeug, name, datei, datei),
            "erklaert ist ein Geheimnis, das nirgends steht")
        vorlage = beispiel if beispiel is not None else echt
        if vorlage is None:
            continue
        if form == "env":
            treffer = re.search(r"^%s=(.*)$" % re.escape(name), vorlage, re.M)
        else:
            treffer = re.search(r'^\s*\S+:\s*"([^"]*)"\s*$', vorlage, re.M)
        sag(treffer is not None,
            "%s/%s: die Zeile steht in der Vorlage" % (werkzeug, name),
            "ein Tippfehler im Namen faellt sonst erst beim Wechsel auf")
        if treffer is None:
            continue
        wert = treffer.group(1).strip()
        sag(wert == "" or "HIER-EINEN" in wert,
            "%s/%s: die Vorlage steht leer da" % (werkzeug, name),
            "in einer Beispieldatei hat ein echter Wert nichts zu suchen")

# --- 3. Kein Geheimnis ohne Eintrag ------------------------------------
for werkzeug in werkzeuge:
    vorlage = lies(werkzeug, ".env.beispiel")
    if vorlage is None:
        continue
    for zeile in vorlage.splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", zeile.strip())
        if not m or not VERDACHT.search(m.group(1)):
            continue
        sag(m.group(1) in erklaert[werkzeug],
            "%s/.env.beispiel: %s steht in der geheimnisse.conf"
            % (werkzeug, m.group(1)),
            "sonst faellt der Wert aus Bestand und Merkzettel heraus")

# --- 4. Ein Geheimnis an mehreren Stellen ist EIN Geheimnis ------------
ueberall = {}
for werkzeug, eintraege in erklaert.items():
    for name, (datei, form, wechsel) in eintraege.items():
        ueberall.setdefault(name, []).append((werkzeug, wechsel))
for name, stellen in sorted(ueberall.items()):
    arten = {w for _, w in stellen}
    sag(len(arten) == 1,
        "%s: alle %d Stellen sind sich ueber den Wechsel einig"
        % (name, len(stellen)),
        "das Werkzeug nimmt die erste Stelle - die anderen waeren wirkungslos: %s"
        % sorted(arten))

# --- 5. Die Wege drumherum --------------------------------------------
ignore = lies(".gitignore") or ""
sag("merkzettel/" in ignore, ".gitignore faengt merkzettel/",
    "ein Zettel mit ALLEN Geheimnissen des Stacks")
sag(".geheimnis-stand" in ignore, ".gitignore faengt .geheimnis-stand")
prolo = lies("werkzeuge", "prolo") or ""
sag("geheimnisse|secrets)" in prolo, "prolo kennt den Befehl geheimnisse")
sag(re.search(r"geheimnisse\|secrets\)\s*root_noetig", prolo) is not None,
    "prolo geheimnisse verlangt root",
    "ohne root sind die .env-Dateien nicht lesbar - der Bestand"
    " meldete dann 'nicht gesetzt' fuer alles und logo waere alles still")

py = os.path.join(stack, "werkzeuge", "geheimnisse.py")
sag(os.path.isfile(py), "werkzeuge/geheimnisse.py liegt da")

# --- 6. Verhalten: gegen einen nachgebauten Stack ----------------------
# Alles bis hier war Lesen. Dass das Werkzeug ein "haende"-Geheimnis
# wirklich in Ruhe laesst, steht in keiner Datei - das muss man versucht
# haben.
def mini_stack(wurzel):
    """Ein Stack aus zwei Werkzeugen: ein harmloses, ein Haende-Geheimnis."""
    os.makedirs(os.path.join(wurzel, "werkzeuge"))
    shutil.copy(py, os.path.join(wurzel, "werkzeuge", "geheimnisse.py"))
    for name, wechsel, wert in (("eins", "harmlos", "ALTERWERT-EINS"),
                                ("zwei", "harmlos", "ALTERWERT-EINS")):
        d = os.path.join(wurzel, name)
        os.makedirs(d)
        open(os.path.join(d, "docker-compose.yml"), "w").write("services: {}\n")
        open(os.path.join(d, "geheimnisse.conf"), "w").write(
            "GEMEINSAM|.env|env|%s|Steht an zwei Stellen und muss dort gleich lauten.\n"
            % wechsel)
        open(os.path.join(d, ".env"), "w").write(
            "VORHER=bleibt\nGEMEINSAM=%s\nNACHHER=bleibt\n" % wert)
    d = os.path.join(wurzel, "drei")
    os.makedirs(d)
    open(os.path.join(d, "docker-compose.yml"), "w").write("services: {}\n")
    open(os.path.join(d, "geheimnisse.conf"), "w").write(
        "UNBERUEHRBAR|.env|env|haende|Steht auch in der Datenbank - nur von Hand.\n")
    open(os.path.join(d, ".env"), "w").write("UNBERUEHRBAR=FINGER-WEG\n")
    return os.path.join(wurzel, "werkzeuge", "geheimnisse.py")

def lauf(prog, args, eingabe=""):
    p = subprocess.run([sys.executable, prog] + args, input=eingabe,
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr

with tempfile.TemporaryDirectory(prefix="geheimnis-probe-") as tmp:
    prog = mini_stack(tmp)
    env = lambda w: open(os.path.join(tmp, w, ".env")).read()

    rc, aus = lauf(prog, [])
    sag(rc == 0 and "GEMEINSAM" in aus and "UNBERUEHRBAR" in aus,
        "Bestand: beide Geheimnisse stehen in der Uebersicht (rc=%d)" % rc)
    sag("ALTERWERT-EINS" not in aus and "FINGER-WEG" not in aus,
        "Bestand: kein einziger Wert steht auf dem Bildschirm (§22)",
        "genau das ist der Grund, warum es diesen Befehl gibt")
    sag("gleich an allen" in aus,
        "Bestand: zwei gleiche Werte heissen 'gleich an allen'")

    # Ein Wert auseinander -> Warnung und roter Ruecklauf.
    open(os.path.join(tmp, "zwei", ".env"), "w").write(
        "VORHER=bleibt\nGEMEINSAM=ANDERER-WERT\nNACHHER=bleibt\n")
    rc, aus = lauf(prog, [])
    sag(rc == 1 and "UNEINIG" in aus,
        "Bestand: zwei verschiedene Werte fallen auf (rc=%d)" % rc,
        "genau dieser Fall macht Werkzeuge unerreichbar")
    open(os.path.join(tmp, "zwei", ".env"), "w").write(
        "VORHER=bleibt\nGEMEINSAM=ALTERWERT-EINS\nNACHHER=bleibt\n")

    # Ohne Sicherung wird nichts gewechselt.
    vorher = env("eins")
    rc, aus = lauf(prog, ["--neu"], eingabe="n\n")
    sag(rc == 1 and env("eins") == vorher,
        "--neu ohne frische Sicherung aendert nichts (rc=%d)" % rc,
        "ein Wechsel ohne Rueckweg ist keiner")

    # Alles mit "ja" beantworten - und trotzdem bleibt das Haende-Geheimnis.
    rc, aus = lauf(prog, ["--neu"], eingabe="j\n" + "j\n" * 10)
    neu_eins, neu_zwei = env("eins"), env("zwei")
    sag("UNBERUEHRBAR=FINGER-WEG" in env("drei"),
        "--neu laesst ein 'haende'-Geheimnis in Ruhe, auch bei lauter Ja",
        "es steht an einer zweiten Stelle, die das Werkzeug nicht kennt")
    # "NICHT angefasst" allein waere zu wenig: eine Ankuendigung ist kein
    # Beweis (N-38), und eine Warnung ohne Weg ist ein Raetsel (§7). Der
    # Text muss den naechsten Handgriff nennen.
    sag("wechselt das Werkzeug NICHT" in aus and "prolo sichern" in aus
        and "ZWEITEN Stelle" in aus,
        "--neu sagt beim Haende-Geheimnis, was von Hand zu tun ist",
        "sonst steht da nur 'geht nicht' und niemand weiss weiter")
    sag("GEMEINSAM=ALTERWERT-EINS" not in neu_eins,
        "--neu hat das harmlose Geheimnis wirklich gewechselt")
    w1 = re.search(r"^GEMEINSAM=(.*)$", neu_eins, re.M)
    w2 = re.search(r"^GEMEINSAM=(.*)$", neu_zwei, re.M)
    sag(w1 and w2 and w1.group(1) == w2.group(1),
        "--neu schreibt an BEIDE Stellen denselben Wert",
        "zwei verschiedene neue Werte waeren schlimmer als der alte")
    sag(w1 is not None and len(w1.group(1)) >= 40,
        "--neu wuerfelt lang genug (%d Zeichen)"
        % (len(w1.group(1)) if w1 else 0))
    sag(neu_eins.startswith("VORHER=bleibt\n") and neu_eins.endswith("NACHHER=bleibt\n"),
        "--neu ruehrt den Rest der Datei nicht an",
        "eine .env haelt mehr als Geheimnisse")
    sag("ALTERWERT-EINS" not in aus and w1.group(1) not in aus,
        "--neu schreibt auch den neuen Wert nicht auf den Bildschirm")

    # Der Merkzettel ohne oeffentlichen Schluessel: gar nichts.
    rc, aus = lauf(prog, ["--merkzettel"])
    sag(rc != 0 and "backup-schluessel" in aus,
        "--merkzettel ohne Sicherungsschluessel bricht ab (rc=%d)" % rc,
        "eine Klartextdatei mit allen Geheimnissen macht jedes andere egal")
    sag(not os.path.exists(os.path.join(tmp, "merkzettel")),
        "--merkzettel hat bei Abbruch nichts angelegt")

    # Und mit Schluessel: verschluesselt, 600, Wert nicht im Klartext.
    if shutil.which("age") and shutil.which("age-keygen"):
        k = subprocess.run(["age-keygen"], capture_output=True, text=True)
        geheim = os.path.join(tmp, "probe.key")
        open(geheim, "w").write(k.stdout)
        oeff = [z.split(": ")[1].strip() for z in k.stdout.splitlines()
                if z.startswith("# public key:")][0]
        open(os.path.join(tmp, ".backup-schluessel.pub"), "w").write(oeff + "\n")
        rc, aus = lauf(prog, ["--merkzettel"])
        pfad = [w for w in aus.split() if w.endswith(".age")]
        sag(rc == 0 and pfad, "--merkzettel schreibt mit Schluessel (rc=%d)" % rc)
        if pfad:
            roh = open(pfad[0], "rb").read()
            sag(b"FINGER-WEG" not in roh,
                "--merkzettel: der Wert steht nicht im Klartext in der Datei")
            sag(oct(os.stat(pfad[0]).st_mode & 0o777) == "0o600",
                "--merkzettel: die Datei gehoert nur root (%s)"
                % oct(os.stat(pfad[0]).st_mode & 0o777))
            klar = subprocess.run(["age", "-d", "-i", geheim, pfad[0]],
                                  capture_output=True, text=True)
            sag("FINGER-WEG" in klar.stdout,
                "--merkzettel: entschluesselt steht der Wert lesbar da",
                "ein Zettel, den man nicht lesen kann, hilft niemandem")
            sag("UNBERUEHRBAR" in klar.stdout and "eins/.env" in klar.stdout,
                "--merkzettel: Name und Ort stehen dabei")
    else:
        sag(False, "age und age-keygen sind da",
            "ohne sie bleibt die Haelfte dieser Pruefung ungemessen - "
            "ein uebersprungener Test ist kein gruener Test")

print("")
print("Alles gruen." if not fehler else "%d Fehler." % fehler)
sys.exit(1 if fehler else 0)
PY
