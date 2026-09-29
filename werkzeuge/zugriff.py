#!/usr/bin/env python3
"""werkzeuge/zugriff.py — was hat der Eingang abgewiesen? (N-80)

Traefik schreibt jede Anfrage nach traefik/log/zugriff.log (B-26). Als
n8n, Vaultwarden und die Anmeldung beim ersten Aufruf schwarz blieben
(N-79), stand die Antwort seit Tagen in dieser Datei - nur lesen konnte
sie niemand: es gab keinen Befehl dafuer, und 14.000 JSON-Zeilen liest
man nicht von Hand.

Aufruf:   prolo abweisungen [--stunden N] [--alle]

WAS HIER NICHT HERAUSKOMMT (§22): In den Pfaden stehen die Zugangslinks
von www (/z/<Marke>, /s/<Marke>) - 192 Bit, die jedem Zugang geben, der
sie hat. Die werden ersetzt, bevor irgendetwas auf den Schirm kommt. Auch
Quelladressen werden nur gezaehlt, nicht genannt: fuer die Frage "wer
wurde abgewiesen und warum" reicht die Anzahl.
"""
import gzip
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

HIER = os.path.dirname(os.path.abspath(__file__))
STACK = os.path.dirname(HIER)
LOGORDNER = os.path.join(STACK, "traefik", "log")
EINSTELLUNG = os.path.join(STACK, "traefik", "dynamic", "sicherheit.yml")


# --- Pfade entschaerfen, bevor sie jemand sieht -------------------------

def pfad_kuerzen(pfad):
    """Aus einem Pfad wird eine Form, die man zeigen kann.

    /z/AbC...192Bit...      -> /z/<Marke>
    /assets/index-9f3a.js   -> /assets/*.js
    /api/v3/flows/xy/       -> unveraendert
    """
    pfad = pfad.split("?", 1)[0]
    teile = pfad.split("/")
    raus = []
    for i, t in enumerate(teile):
        vorher = teile[i - 1] if i else ""
        if vorher in ("z", "s") and t:
            raus.append("<Marke>")          # Zugangslink von www (§22)
        elif len(t) >= 16 and "." not in t:
            raus.append(t[:4] + "…")        # sieht nach Merkmal aus
        else:
            raus.append(t)
    pfad = "/".join(raus)
    # Gleichartige Dateien zu einer Zeile zusammenziehen - sonst sind es
    # 141 Zeilen fuer dieselbe Sache.
    m = re.match(r"^(.*/)[^/]+(\.[A-Za-z0-9]{1,5})$", pfad)
    if m and m.group(1) not in ("/",):
        return m.group(1) + "*" + m.group(2)
    return pfad


# --- Protokolldateien lesen ---------------------------------------------

def dateien():
    """zugriff.log und die gedrehten davor, aeltestes zuerst."""
    if not os.path.isdir(LOGORDNER):
        return []
    gefunden = [os.path.join(LOGORDNER, n) for n in os.listdir(LOGORDNER)
                if n.startswith("zugriff.log")]
    # zugriff.log.14.gz ist aelter als zugriff.log.1, das aelter als
    # zugriff.log. Nach Nummer sortieren, absteigend.
    def rang(p):
        m = re.search(r"\.log\.(\d+)", p)
        return -int(m.group(1)) if m else 0
    return sorted(gefunden, key=rang)


def zeilen(pfad):
    oeffnen = gzip.open if pfad.endswith(".gz") else io.open
    with oeffnen(pfad, "rt", encoding="utf-8", errors="replace") as f:
        for z in f:
            z = z.strip()
            if z.startswith("{"):
                try:
                    yield json.loads(z)
                except ValueError:
                    continue


def zeitpunkt(satz):
    t = satz.get("StartUTC") or satz.get("StartLocal") or ""
    return t[:19]           # 2026-09-29T11:02:03


def kurz(iso):
    if len(iso) < 19:
        return "?"
    return "%s.%s. %s" % (iso[8:10], iso[5:7], iso[11:16])


# --- Die eingestellten Werte, damit die Meldung sie nennen kann ----------

def bremswerte():
    try:
        text = io.open(EINSTELLUNG, encoding="utf-8").read()
    except OSError as e:
        return None, str(e)
    w = dict(re.findall(r"^\s*(average|burst|amount):\s*(\d+)\s*$", text, re.M))
    return w, None


def main(argv):
    stunden = None
    for i, a in enumerate(argv):
        if a == "--stunden" and i + 1 < len(argv):
            try:
                stunden = int(argv[i + 1])
            except ValueError:
                print("--stunden braucht eine Zahl, z.B. --stunden 24")
                return 2

    liste = dateien()
    if not liste:
        print("Kein Zugriffsprotokoll unter %s" % LOGORDNER)
        print("")
        print("  Traefik schreibt es nur, wenn accessLog in traefik.yml")
        print("  steht und der Ordner ihm gehoert:")
        print("    sudo mkdir -p %s && sudo chown -R root:root %s"
              % (LOGORDNER, LOGORDNER))
        print("    sudo prolo start traefik")
        return 1

    grenze = None
    if stunden is not None:
        import datetime
        grenze = (datetime.datetime.now(datetime.timezone.utc)
                  - datetime.timedelta(hours=stunden)).strftime("%Y-%m-%dT%H:%M:%S")

    gesamt = Counter()
    abgewiesen = Counter()
    fehler5xx = Counter()
    quellen = defaultdict(set)
    pfade = defaultdict(Counter)
    erste = letzte = None
    gelesen = 0
    unlesbar = []

    for pfad in liste:
        try:
            for satz in zeilen(pfad):
                t = zeitpunkt(satz)
                if grenze and t < grenze:
                    continue
                gelesen += 1
                if t:
                    erste = t if erste is None or t < erste else erste
                    letzte = t if letzte is None or t > letzte else letzte
                name = satz.get("RequestHost") or "(ohne Namen)"
                code = satz.get("DownstreamStatus") or 0
                gesamt[name] += 1
                if code == 429:
                    abgewiesen[name] += 1
                    quellen[name].add(satz.get("ClientHost") or "?")
                    pfade[name][pfad_kuerzen(satz.get("RequestPath") or "/")] += 1
                elif isinstance(code, int) and 500 <= code < 600:
                    fehler5xx[name] += 1
        except OSError as e:
            # N-64: den Aufruf nennen, der schiefging, nicht "nicht lesbar"
            unlesbar.append("%s: %s" % (pfad, e))

    print("Zugriffsprotokoll: %d Datei(en) unter %s" % (len(liste), LOGORDNER))
    for u in unlesbar:
        print("  nicht gelesen: %s" % u)
    if not gelesen:
        print("")
        print("  %d Zeile(n) im Zeitraum. Es gibt nichts zu zeigen."
              % gelesen)
        if stunden is not None:
            print("  Ohne --stunden %d wird alles gelesen, was da ist."
                  % stunden)
        return 0
    print("  %s Zeilen, %s bis %s" % (f"{gelesen:,}".replace(",", "."),
                                      kurz(erste or ""), kurz(letzte or "")))
    print("")
    print("  %-26s %10s %12s %8s %8s"
          % ("Name", "Anfragen", "abgewiesen", "Fehler", "Quellen"))
    for name, n in sorted(gesamt.items(), key=lambda p: -p[1]):
        print("  %-26s %10d %12d %8d %8d"
              % (name[:26], n, abgewiesen[name], fehler5xx[name],
                 len(quellen[name]) if abgewiesen[name] else 0))

    betroffen = [n for n in abgewiesen if abgewiesen[n]]
    print("")
    if not betroffen:
        print("  Nichts abgewiesen. Bleibt eine Seite trotzdem beim ersten")
        print("  Aufruf leer, liegt es nicht an der Bremse am Eingang.")
        return 0

    # §7: der Satz je Name, die Erklaerung EINMAL je Ursache.
    for name in sorted(betroffen, key=lambda n: -abgewiesen[n]):
        print("  %s hat %d Anfrage(n) abgewiesen, WEIL die Bremse am Eingang"
              % (name, abgewiesen[name]))
        print("  gegriffen hat — verteilt auf %d Quelladresse(n). Am haeufigsten:"
              % len(quellen[name]))
        for p, n in pfade[name].most_common(4):
            print("      %-44s %6d x" % (p[:44], n))
    werte, wieso = bremswerte()
    print("")
    print("  429 setzt Traefik SELBST, am Eingang, bevor das Werkzeug die")
    print("  Anfrage sieht: entweder die Ratenbremse oder die Grenze fuer")
    print("  gleichzeitige Anfragen. Beide stehen in")
    print("    traefik/dynamic/sicherheit.yml")
    if werte:
        print("    average %s je Sekunde · burst %s · gleichzeitig %s"
              % (werte.get("average", "?"), werte.get("burst", "?"),
                 werte.get("amount", "?")))
    else:
        print("    (nicht gelesen — %s)" % wieso)
    print("")
    print("  Faellt dabei ein nachgeladenes Teil weg, baut eine Anwendung")
    print("  ihre Oberflaeche nicht zu Ende: die Seite bleibt schwarz, und")
    print("  erst das Neuladen hilft, weil dann alles aus dem")
    print("  Browserspeicher kommt (N-79). Vier von 300 genuegen dafuer.")
    print("  Nach einer Aenderung:")
    print("    sudo prolo start traefik      (gefahrlos zu wiederholen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
