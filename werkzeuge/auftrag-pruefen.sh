#!/usr/bin/env bash
# werkzeuge/auftrag-pruefen.sh
#
# Fuehrt werkzeuge/auftrag.py nur aus, was es darf - und nichts, was ein
# uebernommener Admin-Container ihm unterschieben will? (A-01)
#
# Der Eingang des Auftragsbuchs wird von einem Container beschrieben, der
# im Internet haengt. Alles, was dort liegt, ist fremde Eingabe (§11) - und
# der Ausfuehrer laeuft als root. Diese Probe legt Auftraege ab, wie ein
# Angreifer sie ablegen wuerde, und misst, was danach WIRKLICH aufgerufen
# wurde: prolo ist eine Attrappe, die jeden Aufruf mitschreibt.
#
# Gearbeitet wird in einem Wegwerfstapel. auftrag.py wird hineinkopiert -
# es findet seinen Stapel ueber seinen eigenen Ort.
#
#   ./werkzeuge/auftrag-pruefen.sh
#   ./werkzeuge/auftrag-pruefen.sh --gegenprobe
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
T=$(mktemp -d); trap 'pkill -f "$T/" 2>/dev/null; rm -rf "$T"' EXIT
FEHLER=0

pruefe() {   # pruefe "Was" erwartet ist
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}

# --- Der Wegwerfstapel ----------------------------------------------------
aufbauen() {   # aufbauen <wurzel> [datei-mit-auftrag.py]
  local S="$1"
  rm -rf "$S"; mkdir -p "$S/werkzeuge"
  cp "${2:-$HIER/auftrag.py}" "$S/werkzeuge/auftrag.py"
  local w
  for w in traefik admin; do
    mkdir -p "$S/$w"; printf 'services: {}\n' > "$S/$w/docker-compose.yml"
  done
  # wiki fuer den Bestand (A-02): eigener Code, ein Router, ein Netz - und
  # ein Wert in der Umgebung, der im Bestand NIE auftauchen darf.
  mkdir -p "$S/wiki"; : > "$S/wiki/Dockerfile"
  cat > "$S/wiki/docker-compose.yml" <<'YML'
services:
  wiki:
    image: ghcr.io/prolo2408/wiki:1.4.1
    environment:
      GEHEIMER_WERT: nie-im-bestand
    networks: [netz-wiki]
    labels:
      - "traefik.http.routers.wiki.rule=Host(`wiki.prolo.me`)"
networks:
  netz-wiki:
    external: true
YML
  mkdir -p "$S/kaputt"; printf 'services:\n  x: [kaputt\n' > "$S/kaputt/docker-compose.yml"
  mkdir -p "$T/draussen-werkzeug"; printf 'services: {}\n' > "$T/draussen-werkzeug/docker-compose.yml"
  ln -sfn "$T/draussen-werkzeug" "$S/verweis"
  # prolo-Attrappe: schreibt die Argumente und die Umgebung mit. Wie sie
  # sich verhaelt, steht in einer Datei - die Umgebung reicht auftrag.py
  # mit Absicht nicht durch.
  cat > "$S/werkzeuge/prolo" <<'STUB'
#!/bin/bash
D="$(dirname "$0")"
printf '%s\n' "$*" >> "$D/.aufrufe"
env | grep -E '^(GEHEIM|PROLO_AUFTRAG)=' | sort >> "$D/.umgebung"
echo "prolo-attrappe: $*"
case "$(cat "$D/.verhalten" 2>/dev/null)" in
  fehler)   echo "etwas ging schief" >&2; exit 3 ;;
  schlafen) sleep 60 & echo $! > "$D/.kind"; wait ;;
  viel)     head -c 2500000 /dev/zero | tr '\0' 'x'; echo ;;
esac
exit 0
STUB
  chmod +x "$S/werkzeuge/prolo"
  PROLO_AUFTRAG_PROBE=1 python3 "$S/werkzeuge/auftrag.py" einrichten > /dev/null
}

# Gezaehlt wird in einer Datei: kennung() laeuft meist in $(...), und
# eine Variable, die in einer Subshell hochgezaehlt wird, ist danach so
# alt wie vorher - jeder Auftrag bekaeme dieselbe Kennung.
kennung() {
  local n; n=$(( $(cat "$T/zaehler" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "$T/zaehler"; printf '20260930-120000-%08x' "$n"
}

auftrag() {   # auftrag <wurzel> <json> -> Kennung
  local k; k=$(kennung)
  printf '%s' "$2" > "$1/admin/auftraege/eingang/$k.json"
  printf '%s' "$k"
}

# Laeuft mit GEHEIM in der Umgebung: die darf bei prolo nicht ankommen.
# Die Zeitgrenze fuer "pruefen" wird fuer die Probe auf 2 s gesetzt - im
# Betrieb sind es 10 Minuten.
abarbeiten() {   # abarbeiten <wurzel>
  GEHEIM=verraten PROLO_AUFTRAG_PROBE=1 python3 - "$1/werkzeuge" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import auftrag
f, _, a = auftrag.ARTEN["pruefen"]
auftrag.ARTEN["pruefen"] = (f, 2, a)
sys.exit(auftrag.main(["auftrag.py", "abarbeiten"]))
PY
}

lage() {   # lage <wurzel> <kennung> <feld>
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' \
    "$1/admin/auftraege/erledigt/$2.json" "$3" 2>/dev/null || echo "(keine Lage)"
}
aufrufe() { cat "$1/werkzeuge/.aufrufe" 2>/dev/null; }
eingang() { ls -A "$1/admin/auftraege/eingang" | tr '\n' ' '; }

pruefen_alles() {
  local S="$1" A K K2 K3 R START DAUER

  # --- Der Normalfall -------------------------------------------------
  K=$(auftrag "$S" '{"art":"start","werkzeug":"wiki","wer":"artur","angelegt":"2026-09-30T12:00:00+02:00"}')
  abarbeiten "$S"; R=$?
  pruefe "abarbeiten endet mit 0" "0" "$R"
  pruefe "prolo bekommt genau 'start wiki'" "start wiki" "$(aufrufe "$S")"
  pruefe "Lage: ok" "ok" "$(lage "$S" "$K" status)"
  pruefe "Lage: Rueckgabe 0" "0" "$(lage "$S" "$K" rueckgabe)"
  pruefe "Lage: wer" "artur" "$(lage "$S" "$K" wer)"
  pruefe "die Ausgabe steht im Protokoll des Auftrags" "ja" \
    "$(grep -q 'prolo-attrappe: start wiki' "$S/admin/auftraege/erledigt/$K.log" && echo ja || echo nein)"
  pruefe "der Eingang ist danach leer" "" "$(eingang "$S")"
  pruefe "PROLO_AUFTRAG traegt die Kennung, GEHEIM kommt nicht an" "PROLO_AUFTRAG=$K" \
    "$(cat "$S/werkzeuge/.umgebung")"
  pruefe "das Protokoll hat eine Zeile" "1" "$(wc -l < "$S/admin/auftraege/erledigt/protokoll.jsonl")"
  pruefe "und die sagt, wer was womit" "start wiki artur ok" \
    "$(python3 -c 'import json,sys; a=json.loads(open(sys.argv[1]).readline()); print(a["art"], a["werkzeug"], a["wer"], a["status"])' \
       "$S/admin/auftraege/erledigt/protokoll.jsonl")"
  pruefe "die Lage ist fuer die Seite lesbar (0644)" "644" \
    "$(stat -c %a "$S/admin/auftraege/erledigt/$K.json")"

  # --- Der Bestand (A-02): jeder Ordner, auch ohne Container -----------
  local BST="$S/admin/auftraege/erledigt/bestand.json"
  pruefe "der Bestand nennt jeden Werkzeugordner, keinen Verweis" "admin kaputt traefik wiki" \
    "$(python3 -c 'import json,sys; print(" ".join(w["name"] for w in json.load(open(sys.argv[1]))["werkzeuge"]))' "$BST" 2>&1)"
  pruefe "mit Art, Namen, Netz und Abbild (von Hand)" \
    "admin:plattform traefik:plattform wiki:eigen wiki.prolo.me netz-wiki ghcr.io/prolo2408/wiki:1.4.1" \
    "$(python3 -c '
import json,sys
w={x["name"]:x for x in json.load(open(sys.argv[1]))["werkzeuge"]}
print(" ".join("%s:%s" % (n, w[n]["art"]) for n in ("admin","traefik","wiki")),
      " ".join(w["wiki"]["hosts"]), " ".join(w["wiki"]["netze"]), w["wiki"]["dienste"][0]["abbild"])' "$BST" 2>&1)"
  pruefe "ein Wert aus der Umgebung steht nie im Bestand" "nein" \
    "$(grep -q 'nie-im-bestand\|GEHEIMER_WERT' "$BST" && echo ja || echo nein)"
  pruefe "ein kaputtes Werkzeug: die Ursache im Wortlaut von docker (N-64)" "ja" \
    "$(python3 -c 'import json,sys; w={x["name"]:x for x in json.load(open(sys.argv[1]))["werkzeuge"]}; print("ja" if "did not find expected" in w["kaputt"].get("fehler","") else "nein: " + w["kaputt"].get("fehler","(kein Fehler)"))' "$BST")"
  local ALT_B; ALT_B=$(stat -c %Y "$BST"); sleep 1.1
  abarbeiten "$S"
  pruefe "ohne Auftrag: der Bestand wird nicht jedes Mal neu geschrieben" "$ALT_B" "$(stat -c %Y "$BST")"
  K=$(auftrag "$S" '{"art":"pruefen","werkzeug":"wiki"}'); abarbeiten "$S"
  pruefe "nach einem Auftrag wird er neu geschrieben" "ja" \
    "$([ "$(stat -c %Y "$BST")" != "$ALT_B" ] && echo ja || echo nein)"
  : > "$S/werkzeuge/.aufrufe"; : > "$S/werkzeuge/.umgebung"

  echo fehler > "$S/werkzeuge/.verhalten"
  K=$(auftrag "$S" '{"art":"neustart","werkzeug":"wiki","wer":"artur"}')
  abarbeiten "$S"
  pruefe "ein Fehlschlag von prolo heisst 'fehler'" "fehler" "$(lage "$S" "$K" status)"
  pruefe "mit seiner Rueckgabe" "3" "$(lage "$S" "$K" rueckgabe)"
  pruefe "und seiner Meldung" "ja" \
    "$(grep -q 'etwas ging schief' "$S/admin/auftraege/erledigt/$K.log" && echo ja || echo nein)"
  rm -f "$S/werkzeuge/.verhalten"

  K=$(auftrag "$S" '{"art":"netz_anlegen","netz":"netz-probe"}')
  abarbeiten "$S"
  pruefe "netz_anlegen ruft 'netze anlegen <netz>'" "netze anlegen netz-probe" \
    "$(aufrufe "$S" | tail -1)"

  K=$(auftrag "$S" '{"art":"neustart","werkzeug":"traefik"}')
  abarbeiten "$S"
  pruefe "neu starten darf man auch den Zugang" "neustart traefik" "$(aufrufe "$S" | tail -1)"

  # --- Was abgelehnt wird: prolo wird NICHT gerufen --------------------
  : > "$S/werkzeuge/.aufrufe"
  local art json
  while IFS='|' read -r was json; do
    [ -n "$was" ] || continue
    K=$(auftrag "$S" "$json")
    abarbeiten "$S"
    pruefe "abgelehnt: $was" "abgelehnt" "$(lage "$S" "$K" status)"
  done <<'FAELLE'
unbekannte Art|{"art":"loeschen","werkzeug":"wiki"}
Pfad aus dem Stapel heraus|{"art":"start","werkzeug":"../traefik"}
Pfad, der ueber einen Umweg wieder hereinfuehrt|{"art":"start","werkzeug":"./wiki"}
Werkzeug, das es nicht gibt|{"art":"start","werkzeug":"gibtsnicht"}
Werkzeugordner, der ein Verweis ist|{"art":"start","werkzeug":"verweis"}
Grossbuchstaben im Namen|{"art":"start","werkzeug":"Wiki"}
Anhalten des Zugangs|{"art":"stop","werkzeug":"traefik"}
Anhalten der Admin-Seite selbst|{"art":"stop","werkzeug":"admin"}
ein Feld zu viel|{"art":"start","werkzeug":"wiki","befehl":"rm -rf /"}
Werkzeug als Liste|{"art":"start","werkzeug":["wiki"]}
Werkzeug fehlt|{"art":"start"}
Netzname mit Semikolon|{"art":"netz_anlegen","netz":"netz;reboot"}
wer mit Zeilenumbruch|{"art":"start","werkzeug":"wiki","wer":"a\nb"}
FAELLE
  pruefe "keiner davon hat prolo erreicht" "" "$(aufrufe "$S")"
  K=$(auftrag "$S" '{"art":"stop","werkzeug":"traefik"}')
  abarbeiten "$S"
  pruefe "die Ablehnung sagt, wie es auf dem Server geht" "ja" \
    "$(lage "$S" "$K" grund | grep -q 'sudo prolo stop traefik' && echo ja || echo nein)"

  # --- Was verworfen wird: die Datei selbst taugt nicht ---------------
  printf '{"art":"start","werkzeug":"wiki"}' > "$T/draussen.json"
  K=$(kennung); ln -s "$T/draussen.json" "$S/admin/auftraege/eingang/$K.json"
  K2=$(kennung); { printf '{"art":"start","werkzeug":"wiki"}'; head -c 300000 /dev/zero | tr '\0' ' '; } \
    > "$S/admin/auftraege/eingang/$K2.json"
  printf '{"art":"start","werkzeug":"wiki"}' > "$S/admin/auftraege/eingang/hallo.json"
  printf 'kein json' > "$S/admin/auftraege/eingang/$(kennung).json"
  printf '[1,2]' > "$S/admin/auftraege/eingang/$(kennung).json"
  mkdir "$S/admin/auftraege/eingang/$(kennung).json"
  abarbeiten "$S"; R=$?
  pruefe "ein Verweis (Symlink) wird nicht verfolgt" "" "$(aufrufe "$S")"
  pruefe "... und nichts davon bleibt im Eingang" "" "$(eingang "$S")"
  pruefe "... alles steht im Protokoll als verworfen" "6" \
    "$(grep -c '"status": "verworfen"' "$S/admin/auftraege/erledigt/protokoll.jsonl")"
  pruefe "... und das Ziel des Verweises ist unberuehrt" '{"art":"start","werkzeug":"wiki"}' \
    "$(cat "$T/draussen.json")"
  pruefe "abarbeiten endet trotzdem mit 0" "0" "$R"

  # Eine Kennung, die es schon gibt: die alte Lage bleibt.
  K=$(auftrag "$S" '{"art":"start","werkzeug":"wiki"}'); abarbeiten "$S"
  local VORHER; VORHER=$(md5sum < "$S/admin/auftraege/erledigt/$K.json")
  : > "$S/werkzeuge/.aufrufe"
  printf '{"art":"stop","werkzeug":"wiki"}' > "$S/admin/auftraege/eingang/$K.json"
  abarbeiten "$S"
  pruefe "eine doppelte Kennung ueberschreibt die alte Lage nicht" "$VORHER" \
    "$(md5sum < "$S/admin/auftraege/erledigt/$K.json")"
  pruefe "... und fuehrt nichts aus" "" "$(aufrufe "$S")"

  # Halb geschrieben: frisch bleibt liegen, alt kommt heraus.
  K=$(kennung); printf '{"art"' > "$S/admin/auftraege/eingang/$K.neu"
  K2=$(kennung); printf '{"art"' > "$S/admin/auftraege/eingang/$K2.neu"
  touch -d '-20 min' "$S/admin/auftraege/eingang/$K2.neu"
  abarbeiten "$S"
  pruefe "eine frische halbe Datei bleibt liegen, eine alte nicht" "$K.neu " "$(eingang "$S")"
  rm -f "$S/admin/auftraege/eingang/$K.neu"

  # --- Grenzen ----------------------------------------------------------
  echo schlafen > "$S/werkzeuge/.verhalten"
  K=$(auftrag "$S" '{"art":"pruefen","werkzeug":"wiki"}')
  START=$(date +%s); abarbeiten "$S"; DAUER=$(( $(date +%s) - START ))
  pruefe "ueber der Zeitgrenze: 'zeit'" "zeit" "$(lage "$S" "$K" status)"
  pruefe "und zwar bald (unter 20 s bei 2 s Grenze)" "ja" "$([ "$DAUER" -lt 20 ] && echo ja || echo "nein ($DAUER s)")"
  sleep 1
  # "Lebt" heisst: da und kein Zombie. Ein beendetes Kind, dessen Eltern
  # schon weg sind, bleibt als Zombie stehen, bis PID 1 es abraeumt - und
  # nicht jeder Container hat ein PID 1, das das tut. kill -0 hielte es
  # fuer lebendig.
  pruefe "... und auch das Kind von prolo ist weg (ganze Prozessgruppe)" "nein" \
    "$(Z=$(ps -o stat= -p "$(cat "$S/werkzeuge/.kind")" 2>/dev/null | tr -d ' ')
       case "$Z" in ''|Z*) echo nein ;; *) echo "ja ($Z)" ;; esac)"

  echo viel > "$S/werkzeuge/.verhalten"
  K=$(auftrag "$S" '{"art":"start","werkzeug":"wiki"}')
  abarbeiten "$S"
  local GROESSE; GROESSE=$(stat -c %s "$S/admin/auftraege/erledigt/$K.log")
  pruefe "die Ausgabe wird bei 1 MiB abgeschnitten" "ja" \
    "$([ "$GROESSE" -lt 1100000 ] && [ "$GROESSE" -gt 1000000 ] && echo ja || echo "nein ($GROESSE Byte)")"
  pruefe "... und es steht dabei" "ja" \
    "$(grep -q 'abgeschnitten' "$S/admin/auftraege/erledigt/$K.log" && echo ja || echo nein)"
  pruefe "... und der Auftrag ist trotzdem ok" "ok" "$(lage "$S" "$K" status)"
  rm -f "$S/werkzeuge/.verhalten"

  # --- Liegengebliebenes und die Sperre ---------------------------------
  K=$(kennung)
  printf '{"kennung":"%s","art":"start","status":"laeuft"}' "$K" \
    > "$S/admin/auftraege/erledigt/$K.json"
  abarbeiten "$S"
  pruefe "was bei einem Absturz 'laeuft' blieb, heisst danach 'abgebrochen'" "abgebrochen" \
    "$(lage "$S" "$K" status)"

  : > "$S/werkzeuge/.aufrufe"
  python3 -c 'import fcntl,sys,time; f=open(sys.argv[1],"w"); fcntl.flock(f,fcntl.LOCK_EX); time.sleep(4)' \
    "$S/admin/auftraege/.sperre" &
  local HALTER=$!
  sleep 1
  K=$(auftrag "$S" '{"art":"start","werkzeug":"wiki"}')
  abarbeiten "$S"; R=$?
  pruefe "haelt ein anderer Lauf die Sperre, geht dieser leise" "0" "$R"
  pruefe "... und fasst den Auftrag nicht an" "$K.json " "$(eingang "$S")"
  wait "$HALTER"
  abarbeiten "$S"
  pruefe "danach wird er ausgefuehrt" "start wiki" "$(aufrufe "$S")"

  # --- Die Tuer: ohne root nur in der Probe -----------------------------
  if [ "$(id -u)" -ne 0 ]; then
    A=$(python3 "$S/werkzeuge/auftrag.py" abarbeiten 2>&1); R=$?
    pruefe "ohne root und ohne Probe: Abbruch" "1" "$R"
  fi
}

aufbauen "$T/s"
pruefen_alles "$T/s"

# Der Nutzer im Container der Admin-Seite muss der sein, dem eingang/
# gehoert - sonst kann die Seite keinen Auftrag ablegen.
UID_DOCKERFILE=$(sed -n 's/.*useradd .*-u \([0-9]*\).*/\1/p' "$STACK/admin/Dockerfile")
UID_AUFTRAG=$(sed -n 's/^ADMIN_UID = \([0-9]*\).*/\1/p' "$HIER/auftrag.py")
pruefe "ADMIN_UID in auftrag.py = Nutzer in admin/Dockerfile" "$UID_DOCKERFILE" "$UID_AUFTRAG"

# Die Seite prueft vorher dasselbe wie der Ausfuehrer (A-02) - laufen die
# Listen auseinander, bietet die Seite an, was hier abgelehnt wird, oder
# lehnt ab, was ginge.
pruefe "Arten, Kern, Namens- und Kennungsmuster gleich in Seite und Ausfuehrer" "gleich" \
  "$(PROLO_EINLASS=x python3 "$HIER/auftrag-gleichlauf.py" "$HIER" "$STACK/admin" 2>&1)"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "AUFTRAGSPRUEFUNG FEHLGESCHLAGEN." >&2; fi

# --- Mutationsprobe (§13a) ---------------------------------------------------
if [ "${1:-}" = "--gegenprobe" ]; then
  [ "$FEHLER" -eq 0 ] || exit 1
  echo
  echo "=== Mutationsprobe ==="
  DURCH=0; NR=0
  while IFS='|' read -r NAME AUSDRUCK; do
    [ -n "$NAME" ] || continue
    NR=$((NR + 1))
    cp "$HIER/auftrag.py" "$T/mutant.py"; sed -i "$AUSDRUCK" "$T/mutant.py"
    if cmp -s "$HIER/auftrag.py" "$T/mutant.py"; then
      printf 'ABBRUCH   %s (liess sich nicht einbauen)\n' "$NAME"; DURCH=$((DURCH + 1)); continue
    fi
    FEHLER=0
    aufbauen "$T/m" "$T/mutant.py"
    pruefen_alles "$T/m" > "$T/mutant.log" 2>&1
    if [ "$FEHLER" -eq 0 ]; then
      printf 'ENTWISCHT %s  <-- Testluecke\n' "$NAME"; DURCH=$((DURCH + 1))
    else
      printf 'gefunden  %s\n' "$NAME"
    fi
  done <<'MUT'
einem Verweis wird gefolgt|s/os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK/os.O_RDONLY | os.O_NONBLOCK/
der Zugang darf angehalten werden|s/if art == "stop" and w in KERN:/if False:/
jeder Werkzeugname geht|s/^WERKZEUG = re.compile(.*/WERKZEUG = re.compile(r".+")/
fremde Felder werden geduldet|s/^    fremd = sorted(.*/    fremd = []/
nur prolo selbst wird beendet|s/os.killpg(p.pid, signal.SIGTERM)/p.terminate()/
die Ausgabe wird nicht begrenzt|s/^MAX_AUSGABE_BYTE = .*/MAX_AUSGABE_BYTE = 10 ** 9/
Liegengebliebenes bleibt "laeuft"|s/^        liegengeblieben()$/        pass/
Verworfenes bleibt im Eingang|s/^        os.rename(os.path.join(EINGANG, name), ziel)$/        pass/
keine Groessengrenze|s/^        if st.st_size > MAX_AUFTRAG_BYTE:$/        if False:/;s/^    if len(roh) > MAX_AUFTRAG_BYTE:$/    if False:/;s/os.read(fd, MAX_AUFTRAG_BYTE + 1)/os.read(fd, 10 ** 7)/
die Umgebung wird durchgereicht|s/cwd=STACK, env=umgebung,/cwd=STACK, env=dict(os.environ, **umgebung),/
keine Sperre|s/fcntl.flock(sperre, fcntl.LOCK_EX | fcntl.LOCK_NB)/pass/
eine doppelte Kennung wird ueberschrieben|s/^    if os.path.exists(os.path.join(ERLEDIGT, kennung + ".json")):$/    if False:/
der Bestand nimmt den ganzen Dienst mit|s/dienste.append({"dienst": dname, "abbild": str(d.get("image") or "")})/dienste.append(dict(d, dienst=dname, abbild=str(d.get("image") or "")))/
der Bestand wird jedes Mal geschrieben|s/^        if not erzwingen and os.path.exists(BESTAND) and \\$/        if False and \\/
der Bestand bleibt nach einem Auftrag alt|s/^                    bestand_schreiben(erzwingen=True)$/                    pass/
ein Verweis als Werkzeugordner wird angenommen|s/ or os.path.islink(os.path.join(STACK, w)):/:/
die Ursache wird zu "unlesbar"|s/(zeilen\[-1\] if zeilen else "Rueckgabe %d" % roh.returncode)\[:300\]/"unlesbar"/
MUT
  echo "gefunden: $((NR - DURCH))   entwischt: $DURCH"
  [ "$DURCH" -eq 0 ] || exit 1
  exit 0
fi
exit "$FEHLER"
