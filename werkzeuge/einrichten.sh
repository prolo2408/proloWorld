#!/usr/bin/env bash
# werkzeuge/einrichten.sh  -  "prolo einrichten"
#
# Bringt einen Server vom frischen Klon bis zum laufenden Stack. Und einen
# halb eingerichteten von dort, wo er steht, bis zum laufenden Stack -
# das ist derselbe Weg, denn JEDER Schritt sieht erst nach, ob er noetig
# ist (N-54).
#
# Der Anlass: die Einrichtung stand als Befehlsliste in einer Anleitung.
# Wer sie abtippt, laesst eine Zeile aus, tippt sich in einer anderen und
# merkt es erst drei Schritte spaeter an einer Meldung, die nach etwas
# anderem aussieht. Genau das ist zweimal passiert.
#
# Grundsaetze:
#   - Im Skript steht KEIN Toolname. Ein Werkzeug ist ein Ordner mit
#     docker-compose.yml, alles Tool-eigene steht in seinen conf-Dateien.
#   - Nichts wird doppelt getan. Jeder Schritt meldet "ok" (war schon),
#     "getan" oder "FEHLT" mit dem naechsten Handgriff.
#   - Nichts wird ueberschrieben. Eine vorhandene .env bleibt, ein
#     vorhandenes Geheimnis bleibt.
#   - Was ein Mensch entscheiden muss, entscheidet ein Mensch.
#
# Aufruf:
#   sudo prolo einrichten            einrichten, mit Rueckfragen
#   sudo prolo einrichten --trocken  nur nachsehen, nichts anfassen
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"
TROCKEN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --trocken|-n) TROCKEN=1; shift ;;
    *) echo "Unbekannt: $1  (nur --trocken)" >&2; exit 2 ;;
  esac
done

OFFEN=0        # was der Mensch noch tun muss
FEHLER=0       # was schiefging

f_ok()    { printf '  \033[32mok\033[0m      %s\n' "$*"; }
f_tat()   { printf '  \033[34mgetan\033[0m   %s\n' "$*"; }
f_offen() { printf '  \033[33moffen\033[0m   %s\n' "$*"; OFFEN=$((OFFEN+1)); }
f_bad()   { printf '  \033[31mFEHLER\033[0m  %s\n' "$*"; FEHLER=$((FEHLER+1)); }
f_wuerde(){ printf '  \033[34mwuerde\033[0m  %s\n' "$*"; }
schritt() { printf '\n\033[1m%s\033[0m\n' "$*"; }
tun()     { [ "$TROCKEN" -eq 0 ]; }

fragen() {   # fragen "Text" [j]  -> 0 = ja
  local vorgabe="${2:-n}" ja antwort
  [ "$vorgabe" = "j" ] && ja="J/n" || ja="j/N"
  if ! tun; then printf '  frage   %s [%s] -> im Trockenlauf: nein\n' "$1" "$ja"; return 1; fi
  read -r -p "  $1 [$ja] " antwort </dev/tty || return 1
  antwort="${antwort:-$vorgabe}"
  case "${antwort,,}" in j|ja|y|yes) return 0 ;; *) return 1 ;; esac
}

werkzeuge() { local d; for d in "$STACK"/*/docker-compose.yml; do
  [ -e "$d" ] && basename "$(dirname "$d")"; done; }

# ----------------------------------------------------------------- 1
schritt "1. Womit wir arbeiten"
[ "$(id -u)" -eq 0 ] || { echo "  Braucht root:  sudo prolo einrichten"; exit 1; }
f_ok "als root"
for P in docker git python3; do
  if command -v "$P" >/dev/null 2>&1; then f_ok "$P ist da"
  else f_bad "$P fehlt - ohne das geht nichts"; fi
done
if docker compose version >/dev/null 2>&1; then f_ok "docker compose ist da"
else f_bad "das docker-compose-Plugin fehlt"; fi
if command -v age >/dev/null 2>&1; then f_ok "age ist da (verschluesselt Sicherungen)"
else f_bad "age fehlt:  apt install age"; fi
[ "$FEHLER" -eq 0 ] || { echo; echo "Erst das oben, dann noch einmal."; exit 1; }

# ----------------------------------------------------------------- 2
schritt "2. prolo im PATH"
ZIEL=/usr/local/bin/prolo
if [ "$(readlink -f "$ZIEL" 2>/dev/null)" = "$HIER/prolo" ]; then
  f_ok "$ZIEL zeigt hierher"
elif tun; then
  ln -sf "$HIER/prolo" "$ZIEL" && f_tat "$ZIEL angelegt"
else f_wuerde "$ZIEL anlegen"; fi

# ----------------------------------------------------------------- 3
schritt "3. Git-Arbeitsstand"
if git -C "$STACK" rev-parse --git-dir >/dev/null 2>&1; then
  if git -C "$STACK" status --short >/dev/null 2>&1; then
    f_ok "git kann den Stand lesen"
  elif tun; then
    git config --global --add safe.directory "$STACK" \
      && f_tat "safe.directory eingetragen (der Ordner gehoert root)"
  else f_wuerde "safe.directory eintragen"; fi
  HAKEN="$STACK/.git/hooks/pre-commit"
  if [ -L "$HAKEN" ]; then f_ok "pre-commit-Haken haengt"
  elif tun; then
    ln -sf ../../werkzeuge/pre-commit "$HAKEN" && f_tat "pre-commit-Haken gesetzt"
  else f_wuerde "pre-commit-Haken setzen"; fi
else
  f_offen "kein Git-Arbeitsstand - 'prolo quelle' und 'prolo aktualisieren' koennen den Stand nicht holen"
fi

# ----------------------------------------------------------------- 4
schritt "4. Sicherungsschluessel"
SCHL="$STACK/.backup-schluessel.pub"
if [ -s "$SCHL" ]; then
  f_ok "$(basename "$SCHL") liegt da"
else
  f_offen "$SCHL fehlt"
  cat <<'HINWEIS'
          Ohne ihn faengt keine Sicherung an und es entsteht kein
          Merkzettel. Auf deinem ARBEITSRECHNER (nicht hier):

            age-keygen -o ~/.prolo-sicherung.key
            grep 'public key' ~/.prolo-sicherung.key

          Den oeffentlichen Teil hierher, dann noch einmal:
            echo 'age1...' | sudo tee /opt/stack/.backup-schluessel.pub

          Der geheime Teil bleibt auf dem Arbeitsrechner. Liegt er hier,
          kann jeder, der den Server hat, die Sicherungen lesen.
HINWEIS
  # Im Trockenlauf wird NICHT abgebrochen: wer nachsieht, will das ganze
  # Bild sehen und nicht die erste Huerde. Gefragt wird nur, wenn es
  # wirklich losgeht.
  if tun && ! fragen "Trotzdem weitermachen? (Geheimnisse bleiben dann offen)"; then
    echo; echo "Abgebrochen. Nichts wurde angefasst."; exit 1
  fi
fi

# ----------------------------------------------------------------- 5
schritt "5. Netze"
# Gelesen wird, welche externen Netze die Compose-Dateien verlangen -
# keine feste Liste, sonst uebersieht das Skript das naechste Werkzeug.
# Welche EXTERNEN Netze nennt eine Compose-Datei? (ein Name je Zeile)
# Ein Werkzeug ohne Argument heisst: alle Compose-Dateien zusammen.
#
# BEIDE Compose-Dateien je Werkzeug (N-83, dieselbe Falle wie N-70): bei
# einem Fremdwerkzeug steht das Netz nicht in der Datei des Herstellers,
# sondern in unserer docker-compose.override.yml. Wer nur die erste liest,
# legt es auf einem frischen Server nie an - und der Router bleibt tot,
# ohne Fehlermeldung. Die override-Datei gewinnt je Schluessel, wie bei
# "docker compose" selbst.
externe_netze() {
python3 - "$STACK" "${1:-}" <<'PY'
import os, re, sys
stack, nur = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
aus, erzeugt = set(), set()
for d in sorted(os.listdir(stack)):
    if nur and d != nur:
        continue
    if not os.path.isfile(os.path.join(stack, d, "docker-compose.yml")):
        continue
    je_schluessel = {}
    for datei in ("docker-compose.yml", "docker-compose.override.yml"):
        p = os.path.join(stack, d, datei)
        if not os.path.isfile(p):
            continue
        t = open(p, encoding="utf-8", errors="replace").read()
        block = re.search(r"^networks:\s*$(.*)", t, re.S | re.M)
        if not block:
            continue
        for m in re.finditer(r"^  ([A-Za-z0-9_.-]+):\s*$((?:\n    .*)*)",
                             block.group(1), re.M):
            schluessel, rumpf = m.group(1), m.group(2)
            # "name:" gewinnt: socket-proxy nennt sein Netz "socket".
            echt = re.search(r"^\s+name:\s*(\S+)", rumpf, re.M)
            je_schluessel[schluessel] = (
                echt.group(1) if echt else schluessel,
                bool(re.search(r"^\s+external:\s*true", rumpf, re.M)))
    for name, extern in je_schluessel.values():
        (aus if extern else erzeugt).add(name)
# Was ein Compose SELBST anlegt, legt man nicht von Hand an: "socket"
# entsteht mit socket-proxy und ist "internal: true". Von Hand angelegt
# waere es ein gewoehnliches Bridge-Netz - und socket-proxy kaeme nicht
# mehr hoch. Traefik nennt es nur "external", weil es von aussen kommt.
# Beim Blick auf EIN Werkzeug zaehlt nur, was es selbst nicht anlegt.
print("\n".join(sorted(aus - erzeugt)))
PY
}

NETZE=$(externe_netze)
if [ -z "$NETZE" ]; then f_offen "keine externen Netze in den Compose-Dateien gefunden"; fi
for N in $NETZE; do
  if docker network inspect "$N" >/dev/null 2>&1; then f_ok "$N"
  elif tun; then docker network create "$N" >/dev/null && f_tat "$N angelegt" \
                 || f_bad "$N liess sich nicht anlegen"
  else f_wuerde "$N anlegen"; fi
done

# ----------------------------------------------------------------- 6
schritt "6. Geheimnisdateien aus ihren Vorlagen"
for W in $(werkzeuge); do
  CONF="$STACK/$W/geheimnisse.conf"
  [ -f "$CONF" ] || continue
  GESEHEN=""
  while IFS='|' read -r NAME DATEI FORM WECHSEL ERKL; do
    case "$NAME" in ''|\#*) continue ;; esac
    PFAD="$STACK/$W/$DATEI"; VORL="$PFAD.beispiel"
    # Zwei Geheimnisse koennen in DERSELBEN Datei stehen (authentik hat
    # zwei in seiner .env). Die Datei wird trotzdem nur einmal gemeldet
    # und nur einmal angelegt.
    case " $GESEHEN " in
      *" $DATEI "*) SCHON=1 ;;
      *) SCHON=0; GESEHEN="$GESEHEN $DATEI" ;;
    esac
    if [ "$SCHON" -eq 1 ]; then
      :
    elif [ -f "$PFAD" ]; then
      f_ok "$W/$DATEI"
    elif [ -f "$VORL" ]; then
      if tun; then
        mkdir -p "$(dirname "$PFAD")"
        cp "$VORL" "$PFAD" && chmod 600 "$PFAD" \
          && f_tat "$W/$DATEI aus der Vorlage angelegt (Werte noch leer)"
      else f_wuerde "$W/$DATEI aus der Vorlage anlegen"; fi
    else
      f_bad "$W/$DATEI fehlt und es gibt keine Vorlage daneben"
    fi
    # Die Zeile selbst muss drin sein, sonst kann sie niemand fuellen.
    if [ -f "$PFAD" ] && [ "$FORM" = "env" ] \
       && ! grep -q "^$NAME=" "$PFAD"; then
      if tun; then printf '%s=\n' "$NAME" >> "$PFAD" \
                     && f_tat "$W/$DATEI: Zeile $NAME ergaenzt"
      else f_wuerde "$W/$DATEI: Zeile $NAME ergaenzen"; fi
    fi
  done < "$CONF"
done

# ----------------------------------------------------------------- 7
schritt "7. Geheimnisse verteilen"
if tun && [ -s "$SCHL" ]; then
  python3 "$HIER/geheimnisse.py" --verteilen; R=$?
  [ "$R" -eq 0 ] || { f_offen "es blieb etwas offen - siehe oben"; }
elif ! tun; then
  f_wuerde "leere Stellen fuellen (prolo geheimnisse --verteilen)"
  python3 "$HIER/geheimnisse.py" | sed 's/^/          /'
else
  f_offen "ohne Sicherungsschluessel uebersprungen"
fi

# ----------------------------------------------------------------- 8
schritt "8. Eine Sicherung einspielen?"
SICHERUNGEN=$(ls -1d /opt/backups/*/ 2>/dev/null | tail -5)
if [ -z "$SICHERUNGEN" ]; then
  f_ok "keine Sicherung unter /opt/backups - frischer Stack"
else
  echo "  Vorhanden:"; echo "$SICHERUNGEN" | sed 's/^/    /'
  if fragen "Eine davon einspielen?"; then
    f_offen "Einspielen macht dieses Skript NICHT - das ist Handarbeit"
    cat <<'HINWEIS'
          Der Weg steht in der Wiki-Seite "Prolo bedienen und verstehen",
          Abschnitt "Eine Sicherung wieder einspielen": entschluesseln,
          Unversehrtheit pruefen, Dienst anhalten, Volume leeren,
          entpacken, starten. Jeder Schritt einzeln und mit Hinsehen -
          ein Skript, das Produktivdaten ueberschreibt, waere genau das
          Werkzeug, das man nicht haben will.
HINWEIS
  else
    f_ok "nichts eingespielt"
  fi
fi

# ----------------------------------------------------------------- 9
schritt "9. Dienste starten"
# Reihenfolge wie in aktualisieren.sh: socket-proxy legt das Netz an, das
# Traefik braucht; Traefik muss stehen, bevor Authentik seine Zertifikate
# bekommt; erst danach die Werkzeuge.
ZUERST="socket-proxy traefik authentik"
# In welchen Netzen haengen die Container eines Werkzeugs WIRKLICH?
netze_der_container() {
  local T="$1" id
  for id in $(docker compose --project-directory "$STACK/$T" ps -q 2>/dev/null); do
    docker inspect "$id" \
      --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' \
      2>/dev/null
  done | sort -u
}

# Welches erklaerte Netz hat KEINEN einzigen Container? (N-58)
#
# Ein Compose kann mehrere Dienste haben, die in verschiedenen Netzen
# haengen - Authentiks Datenbank etwa nur im internen. Darum reicht es,
# wenn je Netz MINDESTENS EIN Container drin ist. Fehlt eines ganz, ist
# der Container aelter als das Netz.
netze_fehlen() {
  local T="$1" N IST
  IST=$(netze_der_container "$T")
  for N in $(externe_netze "$T"); do
    printf '%s\n' "$IST" | grep -qx "$N" || printf '%s ' "$N"
  done
}

starten() {
  local T="$1"
  [ -f "$STACK/$T/docker-compose.yml" ] || return 0
  local LAUFEN FEHLT
  LAUFEN=$(docker compose --project-directory "$STACK/$T" ps -q 2>/dev/null | grep -c .)
  if [ "${LAUFEN:-0}" -gt 0 ]; then
    # Laeuft - aber haengt er auch in seinen Netzen? Ein Netz, das erst
    # in Schritt 5 entstanden ist, erreicht einen schon laufenden
    # Container NICHT von allein. Genau daran ist Traefik einmal
    # vorbeigelaufen: die Netze waren da, die Werkzeuge hingen drin, und
    # Traefik - der als Einziger in alle gehoert - noch im alten Satz.
    # Von aussen sah das aus wie "Gateway Timeout" (N-58).
    FEHLT=$(netze_fehlen "$T")
    if [ -z "$FEHLT" ]; then f_ok "$T laeuft"; return 0; fi
    if ! tun; then f_wuerde "$T neu verbinden (fehlt: $FEHLT)"; return 0; fi
    if (cd "$STACK/$T" && docker compose up -d >/dev/null 2>&1); then
      FEHLT=$(netze_fehlen "$T")
      if [ -z "$FEHLT" ]; then f_tat "$T neu verbunden"
      else f_bad "$T haengt weiter nicht in: $FEHLT"; fi
    else
      f_bad "$T liess sich nicht neu verbinden:  sudo prolo protokoll $T"
    fi
    return 0
  fi
  if ! tun; then f_wuerde "$T starten"; return 0; fi
  if (cd "$STACK/$T" && docker compose up -d >/dev/null 2>&1); then
    f_tat "$T gestartet"
  else
    f_bad "$T kam nicht hoch:  sudo prolo protokoll $T"
  fi
}
for T in $ZUERST; do starten "$T"; done
for T in $(werkzeuge); do
  case " $ZUERST " in *" $T "*) continue ;; esac
  starten "$T"
done

# ----------------------------------------------------------------- 10
schritt "10. Was nur du tun kannst"
# Auch hier beide Dateien (N-83): der Name eines Fremdwerkzeugs steht in
# unserer override-Datei, nicht in der des Herstellers.
python3 - "$STACK" <<'PY'
import os, re, sys
stack = sys.argv[1]
namen = set()
for d in sorted(os.listdir(stack)):
    if not os.path.isfile(os.path.join(stack, d, "docker-compose.yml")):
        continue
    for datei in ("docker-compose.yml", "docker-compose.override.yml"):
        p = os.path.join(stack, d, datei)
        if not os.path.isfile(p):
            continue
        t = open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"Host\(`([^`]+)`\)", t):
            namen.add(m.group(1))
if namen:
    print("  DNS - je ein A-Record auf die Server-IP, KEIN AAAA:")
    for n in sorted(namen):
        print("    %s" % n)
PY
cat <<'HINWEIS'

  Authentik - fuer jeden Namen oben, der eine Anmeldung braucht:
    1. Anwendung anlegen
    2. Provider "forward-auth-domain" zuweisen
    3. Anwendungen -> Outposts -> authentik Embedded Outpost -> Bearbeiten
       -> die neue Anwendung mit auswaehlen
    Schritt 3 wird am haeufigsten vergessen. Ohne ihn antwortet Authentik
    mit "Not Found", und man sucht den Fehler ueberall, nur nicht dort.

  Gruppen in Authentik anlegen und sich selbst zuweisen:
    wiki-editor, wiki-admin   Wiki: schreiben bzw. verwalten
    stack-admin               Verwaltung auf prolo.me
HINWEIS

# -----------------------------------------------------------------
schritt "Stand"
if [ "$FEHLER" -gt 0 ]; then
  printf '  \033[31m%d Fehler\033[0m - die stehen oben, mit dem naechsten Handgriff.\n' "$FEHLER"
elif [ "$OFFEN" -gt 0 ]; then
  if [ "$OFFEN" -eq 1 ]; then
    printf '  \033[33m1 offener Punkt\033[0m - eingerichtet ist alles andere.\n'
  else
    printf '  \033[33m%d offene Punkte\033[0m - eingerichtet ist alles andere.\n' "$OFFEN"
  fi
else
  printf '  \033[32mAlles eingerichtet.\033[0m\n'
fi
echo
echo "  Nachsehen, ob es wirklich laeuft:   sudo prolo status"
echo "  Wo welches Geheimnis steht:         sudo prolo geheimnisse"
echo "  Dieses Skript noch einmal:          sudo prolo einrichten"
echo "  (es tut nur, was noch fehlt - doppelt passiert nichts)"
echo
exit "$FEHLER"
