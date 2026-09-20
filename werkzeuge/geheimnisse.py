#!/usr/bin/env python3
"""prolo geheimnisse - den Bestand zeigen, wechseln, aufschreiben.

Drei Betriebsarten:

  (ohne)          Uebersicht: was es gibt, wo es steht, wie alt, wie riskant
  --neu           fragt je Geheimnis nach und wechselt es
  --merkzettel    schreibt den verschluesselten Zettel fuer den
                  Passwortmanager

Was hier NIE passiert: ein Wert steht auf dem Bildschirm. Die Uebersicht
zeigt Namen, Orte und Daten (CLAUDE.md §22). Wer die Werte braucht, nimmt
den Merkzettel - und der ist verschluesselt.

Welche Werte Geheimnisse sind, sagt jedes Werkzeug selbst in seiner
geheimnisse.conf. Kein Raten an Namensmustern: "WIKI_ADMIN_GRUPPE" sieht
aus wie ein Geheimnis und ist keines.
"""
import argparse
import base64
import datetime
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys

STACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAND = os.path.join(STACK, ".geheimnis-stand")
SCHLUESSEL = os.path.join(STACK, ".backup-schluessel.pub")

# Was ein Wechsel kostet - in der Reihenfolge, in der gefragt wird.
WECHSEL_TEXT = {
    "harmlos": "harmlos",
    "sitzungen": "alle Sitzungen enden",
    "haende": "NUR VON HAND",
}


def rot(s):
    return "\033[31m%s\033[0m" % s if sys.stdout.isatty() else s


def fett(s):
    return "\033[1m%s\033[0m" % s if sys.stdout.isatty() else s


# ------------------------------------------------------------- Bestand

class Geheimnis:
    def __init__(self, werkzeug, name, datei, form, wechsel, erklaerung):
        self.werkzeug, self.name = werkzeug, name
        self.datei, self.form = datei, form
        self.wechsel, self.erklaerung = wechsel, erklaerung

    @property
    def pfad(self):
        return os.path.join(STACK, self.werkzeug, self.datei)

    # Ein Muster fuer alles: Lesen, Schreiben und die Vorabpruefung. Drei
    # eigene Ausdruecke waeren drei Gelegenheiten, dass die Pruefung etwas
    # anderes sucht als das Schreiben spaeter findet (N-52).
    def _muster(self):
        if self.form == "env":
            return re.compile(r"^(%s=)(.*)$" % re.escape(self.name), re.M)
        # Im YAML heisst der Wert nicht wie die Variable, sondern wie die
        # Kopfzeile, die Traefik setzt.
        kopf = re.escape(self.name.replace("PROLO_EINLASS", "Prolo-Einlass"))
        return re.compile(r'^(\s*\S*%s\S*:\s*")([^"]*)("\s*)$' % kopf, re.M)

    def lesen(self):
        """Der abgelegte Wert - oder None. Wird nie ausgegeben."""
        if not os.path.exists(self.pfad):
            return None
        try:
            with open(self.pfad, encoding="utf-8", errors="replace") as f:
                inhalt = f.read()
        except OSError:
            return None
        m = self._muster().search(inhalt)
        wert = m.group(2).strip() if m else None
        if wert in ("", None):
            return None
        # Der Platzhalter aus der Beispieldatei ist kein Wert.
        if "HIER-EINEN" in wert:
            return None
        return wert

    def schreibbar(self):
        """Ginge ein Wechsel hier gut? None heisst ja, sonst der Grund.

        Gefragt wird VOR der ersten Aenderung, fuer JEDE Stelle (N-52).
        Wer Stelle fuer Stelle schreibt und mittendrin abbricht, hinterlaesst
        einen Stack, in dem Traefik eine andere Marke anhaengt als die
        Werkzeuge erwarten - und das heisst 401 auf jede Anfrage.
        """
        if not os.path.exists(self.pfad):
            return ("die Datei fehlt. Anlegen aus %s.beispiel, dann noch "
                    "einmal." % self.datei)
        try:
            with open(self.pfad, encoding="utf-8", errors="replace") as f:
                inhalt = f.read()
        except OSError as e:
            return "nicht lesbar (%s). Mit sudo aufrufen." % e.__class__.__name__
        if not self._muster().search(inhalt):
            vorlage = ("%s=" % self.name if self.form == "env"
                       else '%s: "…"' % self.name.replace("PROLO_EINLASS",
                                                          "Prolo-Einlass"))
            return ("es steht keine Zeile fuer %s darin. Zeile %r "
                    "ergaenzen, dann noch einmal." % (self.name, vorlage))
        if not os.access(self.pfad, os.W_OK):
            return "nicht beschreibbar. Mit sudo aufrufen."
        return None

    def schreiben(self, neu):
        with open(self.pfad, encoding="utf-8") as f:
            inhalt = f.read()
        muster = self._muster()
        if not muster.search(inhalt):
            # Kommt nach schreibbar() nicht mehr vor - bleibt als Netz.
            raise RuntimeError("In %s steht keine Zeile fuer %s."
                               % (self.pfad, self.name))
        ersatz = (lambda m: m.group(1) + neu + (m.group(3) if self.form != "env"
                                                else ""))
        # Erst danebenschreiben, dann umbenennen: ein Abbruch mittendrin
        # hinterlaesst sonst eine halbe Datei (CLAUDE.md §12).
        vorher = os.stat(self.pfad)
        neben = self.pfad + ".neu"
        with open(neben, "w", encoding="utf-8") as f:
            f.write(muster.sub(ersatz, inhalt, count=1))
        os.chmod(neben, vorher.st_mode & 0o7777)
        os.chown(neben, vorher.st_uid, vorher.st_gid)
        os.replace(neben, self.pfad)


def bestand():
    aus = []
    for ordner in sorted(os.listdir(STACK)):
        conf = os.path.join(STACK, ordner, "geheimnisse.conf")
        if not os.path.exists(conf):
            continue
        with open(conf, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#"):
                    continue
                teile = [t.strip() for t in zeile.split("|", 4)]
                if len(teile) != 5:
                    raise SystemExit("Unlesbare Zeile in %s:\n  %s" % (conf, zeile))
                aus.append(Geheimnis(ordner, *teile))
    return aus


def gruppiert(alle):
    """Nach Namen: ein Geheimnis kann an mehreren Stellen stehen."""
    aus = {}
    for g in alle:
        aus.setdefault(g.name, []).append(g)
    return aus


def stand_lesen():
    if not os.path.exists(STAND):
        return {}
    try:
        with open(STAND, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def stand_schreiben(daten):
    with open(STAND, "w", encoding="utf-8") as f:
        json.dump(daten, f, indent=2, sort_keys=True)
    os.chmod(STAND, 0o600)


def alter(datum):
    if not datum:
        return "unbekannt"
    try:
        d = datetime.date.fromisoformat(datum)
    except ValueError:
        return "unbekannt"
    tage = (datetime.date.today() - d).days
    if tage == 0:
        return "heute"
    if tage == 1:
        return "gestern"
    if tage < 60:
        return "vor %d Tagen" % tage
    return "vor %d Monaten" % (tage // 30)


# ----------------------------------------------------------- Uebersicht

def uebersicht():
    alle = bestand()
    if not alle:
        print("Kein Werkzeug hat eine geheimnisse.conf. Nichts zu zeigen.")
        return 0
    st = stand_lesen()
    print(fett("Geheimnisse im Stack") + "\n")
    print("  %-22s %7s  %-14s %-20s %s"
          % ("GEHEIMNIS", "STELLEN", "ZULETZT", "WECHSEL", "STAND"))
    warnung = False
    for name, stellen in sorted(gruppiert(alle).items()):
        werte = [g.lesen() for g in stellen]
        gesetzt = [w for w in werte if w]
        if not gesetzt:
            lage = rot("nicht gesetzt")
        elif len(set(gesetzt)) > 1:
            lage = rot("UNEINIG - %d verschiedene" % len(set(gesetzt)))
            warnung = True
        elif len(gesetzt) < len(stellen):
            lage = rot("fehlt an %d von %d" % (len(stellen) - len(gesetzt),
                                               len(stellen)))
            warnung = True
        else:
            lage = "gleich an allen"
        w = stellen[0].wechsel
        print("  %-22s %7d  %-14s %-20s %s"
              % (name, len(stellen), alter(st.get(name)),
                 rot(WECHSEL_TEXT[w]) if w == "haende" else WECHSEL_TEXT[w],
                 lage))
    print("")
    for name, stellen in sorted(gruppiert(alle).items()):
        print("  %s" % fett(name))
        print("    %s" % stellen[0].erklaerung)
        for g in stellen:
            print("      %s/%s" % (g.werkzeug, g.datei))
        print("")
    if warnung:
        print(rot("  Etwas stimmt nicht. Ein Geheimnis, das an einer Stelle"))
        print(rot("  anders lautet als an der anderen, macht genau die"))
        print(rot("  Werkzeuge unerreichbar, die es pruefen.\n"))
    print("  Werte stehen hier nicht. Fuer den Passwortmanager:")
    print("    sudo prolo geheimnisse --merkzettel")
    return 1 if warnung else 0


# ------------------------------------------------------------- Wechseln

def wuerfeln():
    """44 Zeichen base64 aus 33 Byte - wie die Anleitung es von Hand tut."""
    return base64.b64encode(secrets.token_bytes(33)).decode()


def fragen(text, vorgabe=False):
    ja = "J/n" if vorgabe else "j/N"
    try:
        antwort = input("  %s [%s] " % (text, ja)).strip().lower()
    except EOFError:
        return False
    if not antwort:
        return vorgabe
    return antwort in ("j", "ja", "y", "yes")


def dienste_neu(werkzeuge):
    """Erst Traefik, dann die Werkzeuge.

    Andersherum stehen die Werkzeuge kurz mit dem neuen Wert da, waehrend
    Traefik noch den alten anhaengt - jede Anfrage bekaeme 401. So sind es
    nur die Sekunden, in denen die Werkzeuge nachziehen.
    """
    reihe = (["traefik"] if "traefik" in werkzeuge else []) + \
            [w for w in sorted(werkzeuge) if w != "traefik"]
    if shutil.which("docker") is None:
        print(rot("    Docker ist hier nicht installiert - nichts neu"))
        print(rot("    gestartet. Die Dateien tragen die neuen Werte; die"))
        print(rot("    Dienste laufen noch mit den alten."))
        return False
    for w in reihe:
        print("    %s neu starten ..." % w)
        p = subprocess.run(["docker", "compose", "up", "-d"],
                           cwd=os.path.join(STACK, w),
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(rot("    FEHLGESCHLAGEN: %s" % p.stderr.strip()[:300]))
            return False
    return True


def gesund(werkzeuge, warten=30):
    """Laeuft alles wieder? Gefragt wird Docker, nicht das Netz.

    Ueber das Netz ginge es nur aus einem Container heraus - die
    Pruefadressen zeigen auf Containernamen. Die Gesundheitspruefung im
    Abbild macht dasselbe und ist von hier aus lesbar.
    """
    import time
    if shutil.which("docker") is None:
        return False
    ende = time.time() + warten
    while True:
        offen = []
        for w in sorted(werkzeuge):
            p = subprocess.run(["docker", "compose", "ps", "-q"],
                               cwd=os.path.join(STACK, w),
                               capture_output=True, text=True)
            for kennung in p.stdout.split():
                z = subprocess.run(
                    ["docker", "inspect", kennung, "--format",
                     "{{if .State.Health}}{{.State.Health.Status}}"
                     "{{else}}{{.State.Status}}{{end}}"],
                    capture_output=True, text=True).stdout.strip()
                if z not in ("healthy", "running"):
                    offen.append("%s:%s" % (w, z))
        if not offen:
            return True
        if time.time() > ende:
            print(rot("    Noch nicht gesund: %s" % ", ".join(offen)))
            return False
        time.sleep(2)


def wechseln():
    alle = bestand()
    st = stand_lesen()
    gruppen = gruppiert(alle)

    print(fett("Geheimnisse wechseln") + "\n")
    print("  Gefragt wird je Geheimnis. Nichts passiert ungefragt.\n")

    # Der Merkzettel wird VORHER geprueft, nicht hinterher. Er entsteht am
    # Ende des Laufs; fehlt dann der Schluessel, waeren die Werte schon
    # gewechselt, die Dienste schon neu gestartet - und der einzige Zettel
    # mit dem alten und dem neuen Wert ginge verloren. Ein Hinweis nach der
    # ersten Aenderung ist wertlos (§15, §24a).
    if not os.path.exists(SCHLUESSEL) or shutil.which("age") is None:
        print(rot("  Der Merkzettel liesse sich am Ende nicht schreiben."))
        print("  Es fehlt %s"
              % ("das Programm 'age'" if shutil.which("age") is None
                 else SCHLUESSEL))
        print("  Ohne ihn stuenden die neuen Werte nur in den Dateien, und")
        print("  der alte Wert waere weg. Erst das in Ordnung bringen -")
        print("  denselben Schluessel benutzt auch 'prolo sichern'.\n")
        return 1

    # Vor der ersten Aenderung: eine Sicherung. Danach ist der alte Wert
    # nur noch im Merkzettel - und wenn der schiefgeht, gar nicht mehr.
    if not fragen("Liegt eine frische Sicherung vor (prolo sichern)?"):
        print("\n  Dann zuerst:  sudo prolo sichern")
        print("  Ein Wechsel ohne Rueckweg ist keiner.\n")
        return 1

    heute = datetime.date.today().isoformat()
    zettel, geaendert, gestockt = [], set(), False
    for name, stellen in sorted(gruppen.items()):
        art = stellen[0].wechsel
        print("\n" + fett("  " + name))
        print("    %s" % stellen[0].erklaerung)
        print("    Steht an %d Stelle(n), zuletzt gewechselt: %s"
              % (len(stellen), alter(st.get(name))))

        if art == "haende":
            print(rot("    Dieses Geheimnis wechselt das Werkzeug NICHT."))
            print("    Es steht nicht nur in der Datei, sondern auch an")
            print("    einer zweiten Stelle, die hier niemand kennt. Wer")
            print("    nur die Datei aendert, sperrt den Dienst aus.")
            print("    Von Hand, in dieser Reihenfolge:")
            print("      1. sudo prolo sichern")
            print("      2. Wert an der ZWEITEN Stelle aendern")
            print("         (bei PG_PASS: in PostgreSQL selbst,")
            print("          docker exec ... psql ... ALTER USER ... PASSWORD)")
            print("      3. erst dann die Datei aendern")
            print("      4. Dienst neu starten und anmelden probieren")
            continue

        if art == "sitzungen":
            print(rot("    Nach dem Wechsel muss sich JEDER neu anmelden."))
        if not fragen("Diesen Wert jetzt neu wuerfeln?"):
            print("    uebersprungen.")
            continue

        # ALLE Stellen pruefen, BEVOR eine einzige geschrieben wird (N-52).
        # Vorher lief das Stelle fuer Stelle: eine fehlende Zeile mitten in
        # der Liste liess Traefik mit der neuen Marke stehen und die
        # Werkzeuge mit der alten - also 401 auf jede Anfrage, und der alte
        # Wert war weg, weil der Merkzettel erst am Ende entsteht.
        klemmt = [(g, grund) for g, grund in ((g, g.schreibbar())
                                              for g in stellen) if grund]
        if klemmt:
            print(rot("    NICHT gewechselt - an %d von %d Stellen ginge es "
                      "nicht:" % (len(klemmt), len(stellen))))
            for g, grund in klemmt:
                print(rot("      %s" % g.pfad))
                print("        %s" % grund)
            print("    Ein Wechsel, der nur die Haelfte erreicht, macht die")
            print("    Werkzeuge unerreichbar. Darum bleibt hier alles, wie")
            print("    es war. Erst das oben in Ordnung bringen.")
            gestockt = True
            continue

        alt = next((w for w in (g.lesen() for g in stellen) if w), None)
        neu = wuerfeln()
        # Der alte Wert zuerst auf den Zettel - vor der ersten Aenderung.
        zettel.append((name, alt, neu, [g.werkzeug + "/" + g.datei
                                        for g in stellen]))
        for g in stellen:
            g.schreiben(neu)
            print("    geschrieben: %s/%s" % (g.werkzeug, g.datei))
        st[name] = heute
        geaendert |= {g.werkzeug for g in stellen}

    if not zettel:
        print("\n  Nichts gewechselt.\n")
        return 1 if gestockt else 0

    print("")
    if not dienste_neu(geaendert):
        print(rot("\n  Ein Dienst kam nicht hoch. Die neuen Werte stehen in"))
        print(rot("  den Dateien - der Merkzettel unten enthaelt BEIDE"))
        print(rot("  Werte, den alten und den neuen.\n"))
    elif not gesund(geaendert):
        print(rot("\n  Die Dienste laufen, melden sich aber nicht gesund."))
        print(rot("  Sieh im Protokoll nach:  sudo prolo protokoll <werkzeug>\n"))
    else:
        print("\n  Alles wieder gesund.")

    stand_schreiben(st)
    pfad = merkzettel_schreiben(zettel)
    print("\n  " + fett("Merkzettel: %s" % pfad))
    print("  Er ist verschluesselt und nur auf deinem Arbeitsrechner")
    print("  lesbar. Hol ihn dir dorthin und sortiere die Werte in den")
    print("  Passwortmanager ein:")
    print("    scp <server>:%s ." % pfad)
    print("    age -d -i ~/.prolo-sicherung.key %s"
          % os.path.basename(pfad))
    print("")
    if gestockt:
        print(rot("  Achtung: mindestens ein Geheimnis blieb stehen (siehe"))
        print(rot("  oben). Nach dem Beheben noch einmal aufrufen.\n"))
    return 1 if gestockt else 0


# ----------------------------------------------------------- Merkzettel

def merkzettel_schreiben(eintraege=None):
    """Der Zettel fuer den Passwortmanager - verschluesselt.

    Gegen denselben oeffentlichen Schluessel wie die Sicherung (§23). Ohne
    ihn wird gar nichts geschrieben: eine Klartextdatei mit allen
    Geheimnissen des Stacks waere die eine Datei, die alle anderen
    ueberfluessig macht.
    """
    if not os.path.exists(SCHLUESSEL):
        raise SystemExit(
            "Es fehlt %s.\n\n"
            "Ohne den oeffentlichen Sicherungsschluessel wird kein\n"
            "Merkzettel geschrieben - er stuende sonst im Klartext auf\n"
            "dem Server, und damit waere jedes andere Geheimnis egal.\n\n"
            "Denselben Schluessel benutzt auch 'prolo sichern'.\n" % SCHLUESSEL)
    if shutil.which("age") is None:
        raise SystemExit("Das Programm 'age' fehlt. Es verschluesselt auch "
                         "die Sicherungen.")

    jetzt = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    zeilen = ["Prolo - Geheimnisse, Stand %s" % jetzt, "=" * 46, ""]
    if eintraege:
        zeilen += ["GEWECHSELT IN DIESEM LAUF", "-" * 46, ""]
        for name, alt, neu, orte in eintraege:
            zeilen += ["%s" % name,
                       "  neu : %s" % neu,
                       "  alt : %s" % (alt or "(war nicht gesetzt)"),
                       "  steht in: %s" % ", ".join(orte), ""]
        zeilen += ["", "ALLE GEHEIMNISSE", "-" * 46, ""]
    for name, stellen in sorted(gruppiert(bestand()).items()):
        werte = {w for w in (g.lesen() for g in stellen) if w}
        if not werte:
            zeilen += ["%s\n  (nicht gesetzt)\n" % name]
            continue
        if len(werte) > 1:
            zeilen += ["%s\n  ACHTUNG: an den Stellen stehen verschiedene "
                       "Werte!" % name]
            for g in stellen:
                zeilen += ["  %s/%s : %s" % (g.werkzeug, g.datei,
                                             g.lesen() or "(leer)")]
            zeilen += [""]
            continue
        zeilen += ["%s" % name,
                   "  %s" % werte.pop(),
                   "  steht in: %s" % ", ".join("%s/%s" % (g.werkzeug, g.datei)
                                                for g in stellen),
                   "  Wechsel : %s" % WECHSEL_TEXT[stellen[0].wechsel], ""]
    zeilen += ["", "Diese Datei gehoert in den Passwortmanager und danach",
               "geloescht - auf dem Server UND auf dem Arbeitsrechner.", ""]

    ordner = os.path.join(STACK, "merkzettel")
    os.makedirs(ordner, exist_ok=True)
    os.chmod(ordner, 0o700)
    pfad = os.path.join(ordner, "geheimnisse_%s.txt.age" % jetzt)
    p = subprocess.run(["age", "-R", SCHLUESSEL, "-o", pfad],
                       input="\n".join(zeilen).encode(),
                       capture_output=True)
    if p.returncode != 0:
        raise SystemExit("age hat abgebrochen: %s"
                         % p.stderr.decode(errors="replace")[:300])
    os.chmod(pfad, 0o600)
    return pfad


def main():
    # Ohne das bricht "prolo geheimnisse | head" mit einem Stapelabzug ab,
    # statt einfach aufzuhoeren wie jedes andere Werkzeug. Gemessen: ein
    # BrokenPipeError mitten in der Ausgabe.
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass                      # nicht jede Umgebung kennt SIGPIPE
    p = argparse.ArgumentParser(
        prog="prolo geheimnisse",
        description="Den Bestand an Geheimnissen zeigen, wechseln, aufschreiben.")
    p.add_argument("--neu", action="store_true",
                   help="je Geheimnis nachfragen und es neu wuerfeln")
    p.add_argument("--merkzettel", action="store_true",
                   help="den verschluesselten Zettel schreiben, ohne zu aendern")
    a = p.parse_args()
    if a.neu and a.merkzettel:
        raise SystemExit("Entweder --neu oder --merkzettel, nicht beides. "
                         "--neu schreibt den Zettel ohnehin.")
    if a.neu:
        return wechseln()
    if a.merkzettel:
        pfad = merkzettel_schreiben()
        print("Merkzettel: %s" % pfad)
        print("Verschluesselt, nur auf deinem Arbeitsrechner lesbar.")
        return 0
    return uebersicht()


if __name__ == "__main__":
    sys.exit(main())
