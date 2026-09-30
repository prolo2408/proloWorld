#!/bin/bash
# admin/tests/gegenprobe.sh
#
# Die Tests muessen Zaehne haben (CLAUDE.md §13a). Handgerechnete
# Erwartungswerte sind notwendig, aber nicht genug: ein Test kann gruen
# sein, weil er nichts prueft.
#
# Darum baut dieses Skript absichtlich Fehler ein und verlangt, dass JEDER
# von einem Test gefunden wird. Gearbeitet wird auf einer KOPIE in einem
# Wegwerfordner - eine Probe, die ueber "git checkout" zurueckrollt,
# loescht eine noch nicht eingecheckte Korrektur mit weg (N-34).
set -uo pipefail
cd "$(dirname "$0")/.."
QUELLE="$(pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
GEFUNDEN=0; ENTWISCHT=0

# Die Schriften gehoeren dazu: die Probe zu N-82 holt eine davon, und ohne
# sie antwortet die Kopie mit einer kleinen 404 statt mit der Datei.
cp -a "$QUELLE/server.py" "$QUELLE/tests" "$QUELLE/schriften" "$T/"
rm -rf "$T/tests/__pycache__"

probe() {
  local name="$1" alt="$2" neu="$3"
  cp "$QUELLE/server.py" "$T/server.py"
  # Ein alter __pycache__ laesst eine Mutationsprobe still gruen bleiben.
  rm -rf "$T/tests/__pycache__" "$T/__pycache__"
  if ! python3 - "$T/server.py" "$alt" "$neu" <<'PY'
import io, sys
p, alt, neu = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(p, encoding="utf-8").read()
if s.count(alt) != 1:
    sys.stderr.write("Muster %dx gefunden: %r\n" % (s.count(alt), alt))
    sys.exit(1)
io.open(p, "w", encoding="utf-8").write(s.replace(alt, neu))
PY
  then
    printf 'ABBRUCH   %s (Mutation liess sich nicht einbauen)\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1)); return
  fi
  if (cd "$T" && python3 -m unittest discover -s tests -t tests >"$T/lauf.txt" 2>&1); then
    printf 'ENTWISCHT %s  <-- Testluecke\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1))
  else
    printf 'gefunden  %s\n' "$name"
    grep -E '^(FAIL|ERROR):' "$T/lauf.txt" | sed 's/^/            /' | head -4
    GEFUNDEN=$((GEFUNDEN + 1))
  fi
}

# Zwei Stellen auf einmal - fuer einen Fehler, der erst aus beiden entsteht.
probe2() {
  local name="$1"
  cp "$QUELLE/server.py" "$T/server.py"
  rm -rf "$T/tests/__pycache__" "$T/__pycache__"
  if ! python3 - "$T/server.py" "$2" "$3" "$4" "$5" <<'PY'
import io, sys
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
for alt, neu in ((sys.argv[2], sys.argv[3]), (sys.argv[4], sys.argv[5])):
    if s.count(alt) != 1:
        sys.stderr.write("Muster %dx gefunden: %r\n" % (s.count(alt), alt))
        sys.exit(1)
    s = s.replace(alt, neu)
io.open(p, "w", encoding="utf-8").write(s)
PY
  then
    printf 'ABBRUCH   %s (Mutation liess sich nicht einbauen)\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1)); return
  fi
  if (cd "$T" && python3 -m unittest discover -s tests -t tests >"$T/lauf.txt" 2>&1); then
    printf 'ENTWISCHT %s  <-- Testluecke\n' "$name"
    ENTWISCHT=$((ENTWISCHT + 1))
  else
    printf 'gefunden  %s\n' "$name"
    grep -E '^(FAIL|ERROR):' "$T/lauf.txt" | sed 's/^/            /' | head -4
    GEFUNDEN=$((GEFUNDEN + 1))
  fi
}

probe "ein Router ohne Anmeldung gilt als geschuetzt" \
  '        return ("OFFEN", ", ".join(ungeschuetzt))' \
  '        return ("authentik", "")'

probe "die Marke von Traefik wird nicht mehr geprueft (N-44)" \
  '        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")' \
  '        return
        mit = (self.headers.get(EINLASS_KOPF) or "").encode("utf-8", "replace")'

probe "die Marke wird nur am Anfang verglichen" \
  '        if hmac.compare_digest(mit, EINLASS_B):' \
  '        if mit and EINLASS_B.startswith(mit):'

probe "jede Gruppe darf herein" \
  '        if GRUPPE_LESEN not in meine:' \
  '        if not gruppen:'

probe "eine fremde Gruppe mit aehnlichem Namen zaehlt mit" \
  '        meine = {g for g in gruppen if g.startswith(GRUPPE_PRAEFIX)}' \
  '        meine = {g.split("-")[-1] for g in gruppen}'

probe "Labels werden ungefiltert ausgegeben" \
  '    return html.escape(str(s), quote=True)' \
  '    return str(s)'

probe "ein offener Port faellt nicht auf" \
  '            if d["ports"] and not d["ports_grund"]:' \
  '            if False:'

probe "auch ein erklaerter Port wird beanstandet" \
  '            if d["ports"] and not d["ports_grund"]:' \
  '            if d["ports"]:'

probe "Label und tatsaechliches Netz werden nicht verglichen (N-58)" \
  '            if d["netz_label"] and d["netz_label"] not in d["netze"]:' \
  '            if False:'

probe "ein angehaltener Container faellt nicht auf" \
  '            if d["zustand"] not in ("running", ""):' \
  '            if False:'

probe "eine Absendung von einer fremden Seite wird angenommen" \
  '        if urlparse(quelle).netloc != ziel:' \
  '        if False:'

probe "jeder Pfad zum Docker-Vermittler ist erlaubt" \
  '    if not erlaubt:' \
  '    if False:'

probe "ein unbekanntes Thema wird gespeichert" \
  '    if thema not in THEMEN:' \
  '    if False:'

probe "ein Dienst ohne Router gilt als offen" \
  '''    if labels.get("traefik.enable") != "true":
        return ("", "")''' \
  '''    if False:
        return ("", "")'''

# N-84: ein authentik@file an irgendeinem Router schuetzt den ganzen Dienst.
probe "ein zweiter Router ohne Anmeldung faellt nicht auf (N-84)" \
  '        and "authentik@file" not in labels.get("traefik.http.routers.%s.middlewares" % r, "")]' \
  '        and "authentik@file" not in " ".join(w for k, w in labels.items() if k.endswith(".middlewares"))]'

probe "ein als oeffentlich erklaerter Router gilt trotzdem als offen (N-84)" \
  '        if r not in oeffentlich' \
  '        if True'

# N-82: SIGPIPE auf die Voreinstellung - ein Browser, der wegklickt,
# beendet dann den ganzen Dienst.
probe "SIGPIPE steht wieder auf der Voreinstellung (N-82)" \
  '    datenbank_anlegen()
    srv = ThreadingHTTPServer' \
  '    import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    datenbank_anlegen()
    srv = ThreadingHTTPServer'

# Und der alte Stand im Ganzen: Voreinstellung UND jeder Schreibfehler
# fuehrt zu einer Fehlerseite, also zu einem zweiten Schreibversuch in
# dieselbe geschlossene Leitung. Genau so ist der Dienst gestorben.
# --- A-02: Bedienen ueber das Auftragsbuch
probe "wer nur sehen darf, darf auch bedienen (A-02)" \
  '        if not nutzer["betrieb"]:' \
  '        if False:'
probe "ein Auftrag von einer fremden Seite wird angenommen (A-02)" \
  '        if pfad == "/auftrag":
            self.gleicher_ursprung()' \
  '        if pfad == "/auftrag":'
probe "den Zugang kann man von hier anhalten (A-02)" \
  '    if art == "stop" and aus.get("werkzeug") in KERN:' \
  '    if False:'
probe "ein Doppelklick legt zwei Auftraege ab (A-02)" \
  '    for a in auftraege_lesen(grenze=30):' \
  '    for a in []:'
probe "fremde Felder landen im Auftrag (A-02)" \
  '    daten = dict(aus, art=art,' \
  '    daten = dict(felder, art=art,'
probe "das Protokoll eines Containers wird ungefiltert gezeigt (A-02)" \
  'e(text) or "(leer)"' \
  'text or "(leer)"'
probe "die Ausgabe eines Auftrags wird ungefiltert gezeigt (A-02)" \
  'e(ausgabe) or ("(noch keine)"' \
  'ausgabe or ("(noch keine)"'
probe "die Rahmenkoepfe landen im Protokoll (A-02)" \
  '            teile.append(roh[i + 8:i + 8 + laenge])' \
  '            teile.append(roh[i:i + 8 + laenge])'
probe "eine Kennung darf ein Pfad sein (A-02)" \
  '    if not KENNUNG.fullmatch(kennung or ""):' \
  '    if False:'
probe "die Auftragsseite darf ihren Stand nicht nachholen (A-02)" \
  "\"connect-src 'self'; \"" \
  '""'
# --- A-03: Compose einwerfen
probe "eine Compose-Datei mit Gefahren laesst sich anlegen (A-03)" \
  '    if befund.get("gefahren"):' \
  '    if False:'
probe "angelegt wird die Datei aus dem Formular statt der gepruefen (A-03)" \
  '    return {"name": str(stand.get("name") or ""), "compose": compose,' \
  '    return {"name": str(stand.get("name") or ""), "compose": w("compose") or compose,'
probe "wer nur sehen darf, wirft Compose-Dateien ein (A-03)" \
  '        if pfad == "/neu/pruefen":
            self.gleicher_ursprung()
            self.betrieb_noetig(nutzer)' \
  '        if pfad == "/neu/pruefen":
            self.gleicher_ursprung()'
probe "eigene Anmeldung ohne Grund geht durch (A-03)" \
  '        if aus["anmeldung"] == "eigene" and not aus["grund"]:' \
  '        if False:'
probe "eine Gefahr aus der Datei wird ungefiltert gezeigt (A-03)" \
  '% (e(g["dienst"]), e(g["was"]))' \
  '% (e(g["dienst"]), g["was"])'
probe "die Anmeldung hat doch eine Vorgabe (A-03)" \
  'name="anmeldung" value="authentik" required>' \
  'name="anmeldung" value="authentik" required checked>'

probe "wer nur sehen darf, liest die Protokolle (A-02)" \
  '            if betrieb and laufend:' \
  '            if laufend:'

probe2 "eine abgebrochene Verbindung beendet den Dienst (N-82)" \
  '    datenbank_anlegen()
    srv = ThreadingHTTPServer' \
  '    import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    datenbank_anlegen()
    srv = ThreadingHTTPServer' \
  '        except (BrokenPipeError, ConnectionResetError):' \
  '        except ZeroDivisionError:'

echo
echo "gefunden: $GEFUNDEN   entwischt: $ENTWISCHT"
[ "$ENTWISCHT" -eq 0 ] || exit 1
