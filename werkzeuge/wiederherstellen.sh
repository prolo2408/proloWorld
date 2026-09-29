#!/bin/bash
# werkzeuge/wiederherstellen.sh
#
# Den Stand eines Werkzeugs aus einer Sicherung zurueckholen (N-77).
#
# §23 sagt: "Die Wiederherstellung wird geuebt - das ist der Schritt, den
# fast alle ueberspringen, und der einzige, der zaehlt." Bis hierher gab es
# gar keinen Befehl dafuer. Eine Sicherung, die nie zurueckgespielt wurde,
# ist eine Vermutung; erst ein Lauf macht daraus eine Tatsache.
#
# NICHT zu verwechseln mit "prolo zurueckholen": das holt ein ENTFERNTES
# Werkzeug aus dem Archiv (nach prolo entfernen). Hier geht es um die
# taegliche Sicherung unter /opt/backups.
#
#   prolo wiederherstellen --probe [...]     uebt, ohne etwas anzufassen
#   prolo wiederherstellen [...]             spielt wirklich zurueck
#
# Der geheime age-Schluessel liegt nach §23 auf dem ARBEITSRECHNER, nicht
# hier. Darum nimmt dieser Befehl beides: ein verschluesseltes Archiv samt
# --schluessel (der Weg zur Datei, die nirgends gespeichert wird), oder ein
# bereits entschluesseltes .tar.gz, das man von dort heraufgeladen hat.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
BACKUPS="${PROLO_BACKUPS:-/opt/backups}"

PROBE=0; STAND=""; SCHLUESSEL=""; JA=0; TOOLS=()

blau()  { printf '\033[1m%s\033[0m\n' "$*"; }
melde() { printf '%s\n' "$*"; }
fehler(){ printf '%s\n' "$*" >&2; }

hilfe() {
  cat <<'H'
prolo wiederherstellen - einen gesicherten Stand zurueckholen

  --probe                 nur ueben: auspacken, alles nachpruefen, nichts
                          anfassen. Genau das gehoert regelmaessig gemacht.
  --stand <datum>         welcher Stand (JJJJ-MM-TT). Ohne das: der neueste
  --schluessel <datei>    der geheime age-Schluessel, wenn das Archiv
                          verschluesselt ist. Wird gelesen, nie gespeichert
  --ja                    nicht nachfragen (fuer Skripte; von Hand lieber nicht)
  <tool> ...              nur diese Werkzeuge. Ohne Angabe: alle im Archiv

Beispiele
  prolo wiederherstellen --probe
  prolo wiederherstellen --probe --stand 2026-09-21 --schluessel ~/prolo.key
  sudo prolo wiederherstellen --schluessel ~/prolo.key bordbuch
H
}

while [ $# -gt 0 ]; do
  case "$1" in
    --probe)      PROBE=1 ;;
    --stand)      STAND="${2:-}"; shift ;;
    --schluessel) SCHLUESSEL="${2:-}"; shift ;;
    --ja)         JA=1 ;;
    -h|--hilfe|--help) hilfe; exit 0 ;;
    -*)           fehler "Unbekannte Angabe: $1"; echo; hilfe; exit 1 ;;
    *)            TOOLS+=("$1") ;;
  esac
  shift
done

# ----------------------------------------------------------------------
# 1. Welches Archiv?
archiv_finden() {
  local kandidat
  if [ -n "$STAND" ]; then
    for kandidat in "$BACKUPS/$STAND.tar.gz.age" "$BACKUPS/$STAND.tar.gz"; do
      [ -f "$kandidat" ] && { printf '%s' "$kandidat"; return 0; }
    done
    # Ein verlangter Stand, den es nicht gibt, ist ein Fehler - nicht
    # still der neueste. Wer ein Datum nennt, meint dieses Datum.
    fehler "Zum Stand $STAND gibt es kein Archiv unter $BACKUPS."
    fehler ""
    fehler "  Vorhanden sind:"
    staende_zeigen >&2
    return 1
  fi
  kandidat=$(ls -1 "$BACKUPS"/*.tar.gz.age "$BACKUPS"/*.tar.gz 2>/dev/null \
             | sort | tail -1)
  [ -n "$kandidat" ] || {
    fehler "Unter $BACKUPS liegt kein Archiv."
    fehler ""
    fehler "  Eine Sicherung anlegen:  sudo prolo sichern"
    return 1
  }
  printf '%s' "$kandidat"
}

staende_zeigen() {
  local f n=0
  for f in $(ls -1 "$BACKUPS"/*.tar.gz.age "$BACKUPS"/*.tar.gz 2>/dev/null | sort); do
    printf '    %-24s %s\n' "$(basename "$f" | sed 's/\.tar\.gz\(\.age\)\?$//')" \
      "$(du -h "$f" 2>/dev/null | cut -f1)"
    n=$((n+1))
  done
  [ "$n" -gt 0 ] || printf '    (keins)\n'
}

# ----------------------------------------------------------------------
# 2. Auspacken. Der Ordner gehoert root und wird beim Verlassen geloescht:
#    darin liegen .env-Dateien und Datenbanken im Klartext (§21).
AUSPACK=""
aufraeumen() { [ -n "$AUSPACK" ] && rm -rf "$AUSPACK"; }
trap aufraeumen EXIT INT TERM

STANDORDNER=""
auspacken() {
  local ARCHIV="$1"
  AUSPACK=$(mktemp -d); chmod 700 "$AUSPACK"
  case "$ARCHIV" in
    *.age)
      if [ -z "$SCHLUESSEL" ]; then
        fehler "$(basename "$ARCHIV") ist verschluesselt - dafuer braucht es"
        fehler "den geheimen Schluessel. Der liegt nach §23 NICHT auf diesem"
        fehler "Server, sondern auf dem Arbeitsrechner."
        fehler ""
        fehler "  Entweder die Schluesseldatei herbringen und angeben:"
        fehler "    prolo wiederherstellen --schluessel /pfad/zur/datei"
        fehler "  oder auf dem Arbeitsrechner entschluesseln und das"
        fehler "  entstandene .tar.gz nach $BACKUPS legen:"
        fehler "    age -d -i /pfad/zur/datei -o $(basename "${ARCHIV%.age}") $(basename "$ARCHIV")"
        return 1
      fi
      [ -f "$SCHLUESSEL" ] || { fehler "Schluesseldatei nicht gefunden: $SCHLUESSEL"; return 1; }
      command -v age >/dev/null 2>&1 || { fehler "'age' ist nicht installiert (apt install age)."; return 1; }
      if ! age -d -i "$SCHLUESSEL" "$ARCHIV" > "$AUSPACK/stand.tar.gz" 2>"$AUSPACK/age.fehler"; then
        fehler "Entschluesseln fehlgeschlagen. age sagt:"
        sed 's/^/  /' "$AUSPACK/age.fehler" >&2
        fehler ""
        fehler "  Passt der Schluessel zu $(basename "$STACK")/.backup-schluessel.pub?"
        fehler "  Gesichert wird gegen den OEFFENTLICHEN Teil; zum Lesen"
        fehler "  braucht es den geheimen desselben Paares."
        return 1
      fi
      ;;
    *) cp "$ARCHIV" "$AUSPACK/stand.tar.gz" ;;
  esac
  if ! tar xzf "$AUSPACK/stand.tar.gz" -C "$AUSPACK" 2>"$AUSPACK/tar.fehler"; then
    fehler "Das Archiv liess sich nicht auspacken. tar sagt:"
    sed 's/^/  /' "$AUSPACK/tar.fehler" >&2
    return 1
  fi
  rm -f "$AUSPACK/stand.tar.gz"
  # Im Archiv liegt genau ein Ordner, der Stand.
  STANDORDNER=$(find "$AUSPACK" -mindepth 1 -maxdepth 1 -type d | head -1)
  [ -n "$STANDORDNER" ] || { fehler "Im Archiv liegt kein Stand-Ordner."; return 1; }
}

# ----------------------------------------------------------------------
# 3. Was soll da sein, und ist es da?
#
# Gelesen wird die sicherung.conf des ARBEITSSTANDES, nicht die aus dem
# Archiv: sie sagt, was heute zu einem Werkzeug gehoert. Weicht das
# Archiv davon ab, ist genau das der Befund - und nicht etwas, das eine
# mitgesicherte Kopie stillschweigend geradebiegen soll.
conf_wert() {  # $1 Datei, $2 Name
  python3 - "$1" "$2" <<'PY'
import re, sys
try:
    t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
except OSError:
    sys.exit(0)
m = re.search(r'(?m)^%s="([^"]*)"' % re.escape(sys.argv[2]), t)
print(m.group(1) if m else "")
PY
}

STUECKE=""   # je Zeile: <tool>|<art>|<datei>|<lage>[|<hinweis>]
plan_bauen() {
  local STANDORDNER="$1"; shift
  local liste=("$@") t conf d
  if [ "${#liste[@]}" -eq 0 ]; then
    liste=()
    for d in "$STANDORDNER"/*/; do [ -d "$d" ] && liste+=("$(basename "$d")"); done
  fi
  STUECKE=""
  NEU_ANLEGEN=""
  for t in "${liste[@]}"; do
    conf="$STACK/$t/sicherung.conf"
    # Das Werkzeug gibt es hier nicht - aber sein Ordner liegt in der
    # Sicherung (N-87). Das ist der Fall nach einem Serververlust fuer
    # alles, was "prolo neu" angelegt hat und nie im Git stand. Gelesen
    # wird seine sicherung.conf aus dem Archiv; angelegt wird der Ordner
    # erst beim Einspielen, nie bei --probe.
    if [ ! -e "$STACK/$t" ] && [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then
      mkdir -p "$AUSPACK/ordner"
      if tar xzf "$STANDORDNER/$t/werkzeug.tar.gz" -C "$AUSPACK/ordner" \
           "$t/sicherung.conf" 2>/dev/null; then
        conf="$AUSPACK/ordner/$t/sicherung.conf"
        NEU_ANLEGEN="$NEU_ANLEGEN $t"
      fi
    fi
    if [ ! -f "$conf" ]; then
      STUECKE="$STUECKE$t|-|-|OHNE-CONF"$'\n'
      continue
    fi
    local V O D2 S DB
    V=$(conf_wert "$conf" VOLUMES)
    O=$(conf_wert "$conf" ORDNER)
    D2=$(conf_wert "$conf" DATEIEN)
    S=$(conf_wert "$conf" SQLITE)
    DB=$(conf_wert "$conf" DB_CONTAINER)
    local x name lage
    for x in $V;  do stueck "$t" volume   "$x.tar.gz"      "$STANDORDNER"; done
    for x in $O;  do stueck "$t" ordner   "${x#\?}.tar.gz" "$STANDORDNER" "${x:0:1}"; done
    for x in $D2; do stueck "$t" datei    "${x#\?}"        "$STANDORDNER" "${x:0:1}"; done
    for x in $S;  do stueck "$t" sqlite   "$(basename "${x#*:}")" "$STANDORDNER"; done
    [ -n "$DB" ] && stueck "$t" datenbank "datenbank.sql.gz" "$STANDORDNER"
    # Der Werkzeugordner (N-87). Aeltere Sicherungen haben ihn nicht -
    # darum darf er fehlen.
    stueck "$t" werkzeug "werkzeug.tar.gz" "$STANDORDNER" "?"
  done
}

stueck() {  # $1 tool $2 art $3 datei $4 standordner $5 erstes Zeichen (? = darf fehlen)
  local t="$1" art="$2" datei="$3" so="$4" frei="${5:-}"
  local p="$so/$t/$datei" lage
  if [ -f "$p" ]; then lage=da
  elif [ "$frei" = "?" ]; then lage="fehlt-erlaubt"
  else lage=FEHLT
  fi
  STUECKE="$STUECKE$t|$art|$datei|$lage"$'\n'
}

# ----------------------------------------------------------------------
# 4. Ist das, was da ist, auch lesbar? Das ist der Kern der Probe: eine
#    Datei, die existiert, ist noch keine Sicherung.
pruefen_lesbar() {
  local STANDORDNER="$1" kaputt=0 zeile t art datei lage p
  while IFS='|' read -r t art datei lage _; do
    [ -n "$t" ] || continue
    [ "$lage" = "da" ] || continue
    p="$STANDORDNER/$t/$datei"
    case "$art" in
      volume|ordner|werkzeug)
        if ! tar tzf "$p" >/dev/null 2>&1; then
          melde "  KAPUTT  $t/$datei - laesst sich nicht lesen"; kaputt=1; fi ;;
      datenbank)
        if ! gzip -t "$p" 2>/dev/null; then
          melde "  KAPUTT  $t/$datei - laesst sich nicht entpacken"; kaputt=1; fi ;;
      sqlite)
        # Nicht nur "ist eine Datei", sondern "ist eine heile Datenbank".
        # Genau dafuer gibt es sqlite3.backup() in backup.sh; ob das
        # geklappt hat, sieht man erst hier.
        if ! python3 - "$p" <<'PY'
import sqlite3, sys
try:
    con = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
except Exception as e:
    sys.stderr.write(str(e) + "\n"); sys.exit(1)
sys.exit(0 if ok == "ok" else 1)
PY
        then melde "  KAPUTT  $t/$datei - keine heile SQLite-Datenbank"; kaputt=1; fi ;;
      datei)
        [ -s "$p" ] || { melde "  LEER    $t/$datei"; kaputt=1; } ;;
    esac
  done <<< "$STUECKE"
  return "$kaputt"
}

# ----------------------------------------------------------------------
bericht() {
  local fehlt=0 t art datei lage
  printf '  %-14s %-10s %-34s %s\n' "WERKZEUG" "ART" "DATEI" "LAGE"
  while IFS='|' read -r t art datei lage _; do
    [ -n "$t" ] || continue
    printf '  %-14s %-10s %-34s %s\n' "$t" "$art" "$datei" "$lage"
    [ "$lage" = "FEHLT" ] || [ "$lage" = "OHNE-CONF" ] && fehlt=1
  done <<< "$STUECKE"
  return "$fehlt"
}

# ----------------------------------------------------------------------
ARCHIV=$(archiv_finden) || exit 1
blau "Sicherung"
melde "  Archiv   $ARCHIV"
melde "  Groesse  $(du -h "$ARCHIV" 2>/dev/null | cut -f1)"
melde "  Stand    $(basename "$ARCHIV" | sed 's/\.tar\.gz\(\.age\)\?$//')"
melde ""

auspacken "$ARCHIV" || exit 1
plan_bauen "$STANDORDNER" ${TOOLS[@]+"${TOOLS[@]}"}

blau "Was im Archiv liegt"
bericht; VOLLSTAENDIG=$?
if [ -n "$NEU_ANLEGEN" ]; then
  melde ""
  melde "  Hier nicht vorhanden, der Ordner liegt aber in der Sicherung und"
  melde "  wird beim Einspielen angelegt:$NEU_ANLEGEN"
fi
# Nichts zu tun heisst hier NICHT "alles in Ordnung". Ein leerer Plan
# bedeutet: im Archiv steht kein Werkzeug, das heute noch eine
# sicherung.conf hat. Das als "vollstaendig und lesbar" zu melden waere
# dieselbe Luege wie "Backup fertig" ueber ein leeres Archiv (N-76).
if [ -z "$(printf '%s\n' "$STUECKE" | awk -F'|' '$1!=""{print}')" ]; then
  melde ""
  fehler "In diesem Archiv steht nichts, was sich zurueckspielen liesse."
  fehler ""
  if [ "${#TOOLS[@]}" -gt 0 ]; then
    fehler "  Verlangt waren: ${TOOLS[*]}"
    fehler "  Im Archiv liegen:"
    for d in "$STANDORDNER"/*/; do [ -d "$d" ] && fehler "    $(basename "$d")"; done
  else
    fehler "  Entweder ist das Archiv leer, oder kein Werkzeug darin hat"
    fehler "  unter $STACK noch eine sicherung.conf."
  fi
  exit 1
fi
melde ""

blau "Ist es lesbar?"
if pruefen_lesbar "$STANDORDNER"; then
  melde "  Alles gelesen, nichts beanstandet."
  LESBAR=0
else
  LESBAR=1
fi
melde ""

if [ "$VOLLSTAENDIG" -ne 0 ] || [ "$LESBAR" -ne 0 ]; then
  fehler "Dieser Stand ist NICHT vollstaendig zurueckspielbar."
  fehler ""
  fehler "  FEHLT     die sicherung.conf verlangt es, im Archiv ist es nicht."
  fehler "            Meist heisst das: es wurde erst nach dieser Sicherung"
  fehler "            eingetragen. Ein neuer Lauf holt es:  sudo prolo sichern"
  fehler "  OHNE-CONF das Werkzeug liegt im Archiv, hat aber heute keine"
  fehler "            sicherung.conf mehr - entfernt oder umbenannt - und"
  fehler "            sein Ordner steht nicht in der Sicherung (die gibt es"
  fehler "            erst seit N-87)."
  fehler "  KAPUTT    die Datei ist da und laesst sich nicht lesen. Das ist"
  fehler "            der Fall, fuer den es diese Probe gibt."
  exit 1
fi

if [ "$PROBE" -eq 1 ]; then
  blau "Probe"
  melde "  Nichts angefasst. Der Stand ist vollstaendig und lesbar."
  melde ""
  melde "  Das ist die Uebung aus §23. Sie beweist, dass das Archiv taugt -"
  melde "  nicht, dass ein Zurueckspielen heute glattgeht. Dafuer braucht es"
  melde "  denselben Lauf ohne --probe."
  exit 0
fi
# ----------------------------------------------------------------------
# 5. Ab hier wird geschrieben.

BETROFFEN=$(printf '%s\n' "$STUECKE" | awk -F'|' '$1!=""{print $1}' | sort -u)
SICHERHEITSKOPIE="$BACKUPS/.vor-wiederherstellung-$(date +%Y-%m-%d-%H%M%S)"

blau "Was jetzt passiert"
melde "  Diese Werkzeuge werden angehalten, ihr jetziger Stand wird zur"
melde "  Seite gelegt, und dann wird der Stand aus dem Archiv eingespielt:"
melde ""
for t in $BETROFFEN; do melde "    $t"; done
melde ""
melde "  Der jetzige Stand kommt nach"
melde "    $SICHERHEITSKOPIE"
melde "  Der Ordner traegt die Uhrzeit und wird nie ueberschrieben (§15):"
melde "  auch ein zweiter, ebenfalls schiefgegangener Lauf nimmt dir den"
melde "  ersten Rueckweg nicht weg."
melde ""

if [ "$JA" -ne 1 ]; then
  if [ ! -t 0 ]; then
    fehler "Das ueberschreibt laufende Daten und will bestaetigt werden."
    fehler "Ohne Terminal geht das nur mit --ja."
    exit 1
  fi
  printf '  Zum Fortfahren die Anzahl der Werkzeuge eintippen (%s): ' \
    "$(printf '%s\n' "$BETROFFEN" | grep -c .)"
  read -r ANTWORT
  if [ "$ANTWORT" != "$(printf '%s\n' "$BETROFFEN" | grep -c .)" ]; then
    melde ""
    melde "  Abgebrochen. Es wurde nichts angefasst."
    exit 1
  fi
  melde ""
fi

mkdir -p "$SICHERHEITSKOPIE"; chmod 700 "$SICHERHEITSKOPIE"

# Wohin gehoert eine SQLite-Datei im Dateisystem? Aus der zusammengesetzten
# Compose-Konfiguration: der Einhaengepunkt sagt, in welchem Volume der Pfad
# liegt und wo darin.
sqlite_ort() {  # $1 tool  $2 behaelter:/pfad   ->  "<volume> <relpfad>"
  python3 - "$STACK/$1" "$2" <<'PY'
import json, os, subprocess, sys
ordner, eintrag = sys.argv[1], sys.argv[2]
behaelter, _, pfad = eintrag.partition(":")
try:
    roh = subprocess.run(["docker", "compose", "config", "--no-interpolate",
                          "--format", "json"], cwd=ordner,
                         capture_output=True, text=True, timeout=60)
    c = json.loads(roh.stdout) if roh.returncode == 0 else {}
except Exception:
    c = {}
treffer = None
for dienst in (c.get("services") or {}).values():
    for m in dienst.get("volumes") or []:
        if not isinstance(m, dict) or m.get("type") != "volume":
            continue
        ziel = str(m.get("target") or "")
        if pfad == ziel or pfad.startswith(ziel.rstrip("/") + "/"):
            # Der laengste passende Einhaengepunkt gewinnt: /daten/unter
            # schlaegt /daten.
            if treffer is None or len(ziel) > len(treffer[0]):
                quelle = str(m.get("source") or "")
                name = ((c.get("volumes") or {}).get(quelle) or {}).get("name") or quelle
                treffer = (ziel, name, os.path.relpath(pfad, ziel))
print("%s %s" % (treffer[1], treffer[2]) if treffer else "")
PY
}

FEHLER=0
for t in $BETROFFEN; do
  blau "$t"
  # Fehlt der Ordner hier, kommt er aus der Sicherung (N-87). Ein
  # VORHANDENER Ordner wird nie ueberschrieben (§15): dort liegt, was
  # jemand nach der Sicherung geaendert hat - und das Git ist fuer die
  # Konfiguration der bessere Rueckweg.
  if [ ! -e "$STACK/$t" ] && [ -f "$STANDORDNER/$t/werkzeug.tar.gz" ]; then
    if tar xzf "$STANDORDNER/$t/werkzeug.tar.gz" -C "$STACK"; then
      melde "  Werkzeugordner aus der Sicherung angelegt: $STACK/$t"
    else
      fehler "  Der Werkzeugordner liess sich nicht auspacken - $t uebersprungen."
      FEHLER=1; continue
    fi
  fi
  conf="$STACK/$t/sicherung.conf"
  V=$(conf_wert "$conf" VOLUMES)
  O=$(conf_wert "$conf" ORDNER)
  D2=$(conf_wert "$conf" DATEIEN)
  S=$(conf_wert "$conf" SQLITE)
  DBC=$(conf_wert "$conf" DB_CONTAINER)
  DBU=$(conf_wert "$conf" DB_USER)
  DBN=$(conf_wert "$conf" DB_NAME)

  melde "  halte an ..."
  # "stop", nicht "down": der Behaelter bleibt liegen. Das ist weniger
  # zerstoererisch, und es geht schneller wieder hoch.
  (cd "$STACK/$t" && docker compose stop >/dev/null 2>&1) || true

  mkdir -p "$SICHERHEITSKOPIE/$t"

  # --- Volumes: erst der jetzige Stand zur Seite, dann ersetzen --------
  for vol in $V; do
    docker run --rm -v "$vol":/daten -v "$SICHERHEITSKOPIE/$t":/ab alpine \
      tar czf "/ab/$vol.tar.gz" -C /daten . >/dev/null 2>&1 \
      || melde "  (kein jetziger Stand von $vol - das Volume gibt es noch nicht)"
    if docker run --rm -v "$vol":/daten -v "$STANDORDNER/$t":/ein alpine \
         sh -c 'rm -rf /daten/..?* /daten/.[!.]* /daten/* 2>/dev/null; \
                tar xzf "/ein/'"$vol"'.tar.gz" -C /daten' >/dev/null 2>&1; then
      melde "  Volume  $vol"
    else
      fehler "  FEHLER  Volume $vol liess sich nicht einspielen"; FEHLER=1
    fi
  done

  # --- Ordner und Dateien im Werkzeugordner ---------------------------
  for o in $O; do
    o="${o#\?}"
    [ -f "$STANDORDNER/$t/$o.tar.gz" ] || continue
    [ -d "$STACK/$t/$o" ] && tar czf "$SICHERHEITSKOPIE/$t/$o.tar.gz" -C "$STACK/$t" "$o" 2>/dev/null
    rm -rf "${STACK:?}/$t/$o"
    if tar xzf "$STANDORDNER/$t/$o.tar.gz" -C "$STACK/$t" 2>/dev/null; then
      melde "  Ordner  $o"
    else
      fehler "  FEHLER  Ordner $o liess sich nicht einspielen"; FEHLER=1
    fi
  done
  for d in $D2; do
    d="${d#\?}"
    [ -f "$STANDORDNER/$t/$d" ] || continue
    [ -f "$STACK/$t/$d" ] && cp -p "$STACK/$t/$d" "$SICHERHEITSKOPIE/$t/$d"
    if cp "$STANDORDNER/$t/$d" "$STACK/$t/$d"; then
      # acme.json und .env sind Geheimnisse - die Rechte gehen mit (§21).
      chmod 600 "$STACK/$t/$d"
      melde "  Datei   $d"
    else
      fehler "  FEHLER  Datei $d liess sich nicht einspielen"; FEHLER=1
    fi
  done

  # --- SQLite ZULETZT -------------------------------------------------
  # Das Volume-Archiv enthaelt die Datenbank auch, aber moeglicherweise
  # mitten in einem Schreibvorgang erwischt (darum gibt es sqlite3.backup()
  # in backup.sh). Die heile Kopie gehoert also OBENDRAUF.
  #
  # Und die alten -wal/-shm muessen weg. Sonst spielt SQLite beim naechsten
  # Oeffnen ein Journal auf eine Datenbank, zu der es nicht gehoert - die
  # Datei sieht heil aus und ist es nicht. Das ist die stillste Art, eine
  # Wiederherstellung zu verlieren.
  for eintrag in $S; do
    name=$(basename "${eintrag#*:}")
    [ -f "$STANDORDNER/$t/$name" ] || continue
    ORT=$(sqlite_ort "$t" "$eintrag")
    if [ -z "$ORT" ]; then
      fehler "  FEHLER  $name: kein Volume gefunden, in dem ${eintrag#*:} liegt."
      fehler "          Steht SQLITE in $t/sicherung.conf richtig?"
      FEHLER=1; continue
    fi
    set -- $ORT
    if docker run --rm -v "$1":/daten -v "$STANDORDNER/$t":/ein alpine \
         sh -c 'cp "/ein/'"$name"'" "/daten/'"$2"'" && \
                rm -f "/daten/'"$2"'-wal" "/daten/'"$2"'-shm"' >/dev/null 2>&1; then
      melde "  SQLite  $name  (nach $1:/$2, -wal und -shm entfernt)"
    else
      fehler "  FEHLER  $name liess sich nicht einspielen"; FEHLER=1
    fi
  done

  # --- PostgreSQL -----------------------------------------------------
  if [ -n "$DBC" ] && [ -f "$STANDORDNER/$t/datenbank.sql.gz" ]; then
    melde "  starte $DBC fuer das Einspielen ..."
    (cd "$STACK/$t" && docker compose up -d "$DBC" >/dev/null 2>&1) || true
    if gzip -dc "$STANDORDNER/$t/datenbank.sql.gz" \
       | docker exec -i "$DBC" psql -U "$DBU" -d "$DBN" >/dev/null 2>&1; then
      melde "  Datenbank $DBN"
    else
      fehler "  FEHLER  Datenbank $DBN liess sich nicht einspielen."
      fehler "          Der Dump liegt noch im Archiv; von Hand:"
      fehler "            gzip -dc datenbank.sql.gz | docker exec -i $DBC psql -U $DBU -d $DBN"
      FEHLER=1
    fi
  fi

  melde "  starte ..."
  (cd "$STACK/$t" && docker compose up -d >/dev/null 2>&1) \
    || { fehler "  FEHLER  $t kam nicht wieder hoch - sudo prolo protokoll $t"; FEHLER=1; }
  melde ""
done

blau "Fertig"
melde "  Der Stand VOR dieser Wiederherstellung liegt unter"
melde "    $SICHERHEITSKOPIE"
melde "  Er ist NICHT verschluesselt. Wenn alles stimmt, gehoert er geloescht;"
melde "  solange er liegt, liegen dort .env-Dateien und Datenbanken offen (§21)."
melde ""
melde "  Nachsehen, ob wirklich alles laeuft:"
melde "    sudo prolo status"
if [ "$FEHLER" -ne 0 ]; then
  melde ""
  fehler "Mindestens ein Stueck ging nicht - siehe oben."
  exit 1
fi
