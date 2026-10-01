#!/bin/bash
# werkzeuge/auslagern-pruefen.sh
#
# Probe fuer auslagern.sh und umstellen.sh (U-04), im Wegwerfordner:
#
#   1. Das Wiki wirklich in ein leeres (lokales) Repository auslagern und
#      dort nachsehen: liegt der Code an der Wurzel, ist die Geschichte
#      dabei, fehlen die Betriebsdateien - und laufen die Tests des
#      Werkzeugs ALLEIN, ohne proloWorld drumherum?
#   2. In einer Kopie von proloWorld alle drei Werkzeuge umstellen und dort
#      die Pruefungen des Stapels laufen lassen. Das ist der Beweis, dass
#      der Stapel nach dem Umzug noch prueft, was er vorher prueft.
#
#   ./werkzeuge/auslagern-pruefen.sh
#   ./werkzeuge/auslagern-pruefen.sh --gegenprobe
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUELLE="$(dirname "$HIER")"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
FEHLER=0

pruefe() {
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}
ja() { if eval "$1"; then echo ja; else echo nein; fi; }

# --- Ein Git-Stand wie auf dem Rechner des Entwicklers ------------------
# Der eingecheckte Stand von proloWorld, dazu die Werkzeuge in ihrer
# jetzigen Fassung (auch nicht eingecheckt) - eingecheckt IN DER KOPIE.
S="$T/stack"
git clone -q "$QUELLE" "$S"
git -C "$S" config user.email probe@localhost; git -C "$S" config user.name probe
# Der ganze Ordner, samt Unterordnern (systemd/ seit A-01) - nur die
# obersten Dateien zu nehmen hiess, eine Einheit zu vergessen, die
# einrichten-pruefen.sh dann vermisst.
cp -r "$HIER/." "$S/werkzeuge/"
rm -rf "$S/werkzeuge/__pycache__"
# Einstieg fuer die Mutationsprobe: ein sed-Ausdruck auf die KOPIE (N-34).
if [ -n "${AUSLAGERN_MUTATION:-}" ]; then
  sed -i "${AUSLAGERN_MUTATION#*|}" "$S/werkzeuge/${AUSLAGERN_MUTATION%%|*}"
fi
git -C "$S" add -A && git -C "$S" commit -q -m "Pruefstand" || true

# docker: "manifest inspect" nach Wunsch, alles andere ans echte docker
# ("compose config" braucht keinen Dienst).
mkdir -p "$T/bin"
cat > "$T/bin/docker" <<STUB
#!/bin/bash
if [ "\$1 \$2" = "manifest inspect" ]; then
  [ "\${ABBILD_DA:-1}" = 1 ] && { echo '{}'; exit 0; }
  echo "manifest unknown" >&2; exit 1
fi
exec $(command -v docker) "\$@"
STUB
chmod +x "$T/bin/docker"
export PATH="$T/bin:$PATH"

echo "=== Auslagern ==="
# Wie ein leeres Repository auf GitHub: HEAD zeigt auf main.
ZIEL="$T/ziel/wiki.git"; mkdir -p "$ZIEL"; git init -q --bare -b main "$ZIEL"
A=$(bash "$S/werkzeuge/auslagern.sh" wiki "$ZIEL" 2>&1); R=$?
pruefe "auslagern laeuft durch" "0" "$R"
[ "$R" -eq 0 ] || printf '%s\n' "$A" | tail -8

N=$(git -C "$S" log --oneline -- wiki | wc -l)
git clone -q "$ZIEL" "$T/neu"
pruefe "der Code liegt an der Wurzel" "ja" "$(ja '[ -f "$T/neu/server.py" ] && [ -f "$T/neu/Dockerfile" ]')"
pruefe "die Regeln und der Arbeitsablauf sind dabei" "ja" \
  "$(ja '[ -f "$T/neu/CLAUDE.md" ] && [ -f "$T/neu/.github/workflows/abbild.yml" ]')"
for d in docker-compose.override.yml sicherung.conf aktualisierung.conf geheimnisse.conf vorlagen/prolo-bedienen.html; do
  pruefe "Betriebsdatei $d fehlt im Werkzeug-Repo" "nein" "$(ja '[ -e "$T/neu/$d" ]')"
done
pruefe "die Herstellerdatei ist dabei" "ja" "$(ja '[ -f "$T/neu/docker-compose.yml" ]')"
M=$(git -C "$T/neu" log --oneline | wc -l)
pruefe "die Geschichte ist dabei ($N Commits hier, $M dort)" "ja" "$(ja '[ "$M" -ge "$N" ] && [ "$N" -gt 10 ]')"
# Der aelteste Commit am Wiki muss dort sein. Gelesen wird in eine Variable,
# nicht durch "| grep -q": grep hoert beim ersten Treffer auf, git log
# bekommt SIGPIPE, und mit pipefail ist die Pruefung dann rot, OBWOHL
# der Commit da ist.
ALT=$(git -C "$S" log --format=%s -- wiki | tail -1)
LOG_NEU=$(git -C "$T/neu" log --format=%s)
pruefe "der aelteste Commit am Wiki ist dabei: $ALT" "ja" \
  "$(ja 'grep -qxF "$ALT" <<<"$LOG_NEU"')"
( cd "$T/neu" && bash tests/alle.sh > "$T/neu-tests.txt" 2>&1 ); R=$?
pruefe "die Tests des Werkzeugs laufen im neuen Repository allein" "0" "$R"
[ "$R" -eq 0 ] || tail -12 "$T/neu-tests.txt"
pruefe "in proloWorld hat sich nichts geaendert" "" "$(git -C "$S" status --porcelain -- wiki)"
pruefe "kein Arbeitszweig bleibt liegen" "" "$(git -C "$S" branch --list 'auslagern/*')"

A=$(bash "$S/werkzeuge/auslagern.sh" wiki "$ZIEL" 2>&1); R=$?
pruefe "ein Ziel mit Inhalt wird nicht angefasst" "1" "$R"
pruefe "und es wird gesagt, warum" "ja" "$(ja 'grep -q "nicht leer" <<<"$A"')"

# Ein ECHTES leeres Ziel: gaebe es das nicht, hielte schon "git ls-remote"
# an, und die Pruefung waere aus dem falschen Grund gruen.
LEER="$T/ziel/leer.git"; mkdir -p "$LEER"; git init -q --bare -b main "$LEER"
echo "neu" >> "$S/bordbuch/README.md"
A=$(bash "$S/werkzeuge/auslagern.sh" bordbuch "$LEER" 2>&1); R=$?
pruefe "nicht Eingechecktes haelt das Auslagern an" "1" "$R"
pruefe "und das Ziel bleibt leer" "" "$(git ls-remote "$LEER" 2>&1)"
pruefe "und die Meldung nennt die Datei" "ja" "$(ja 'grep -q "bordbuch/README.md" <<<"$A"')"
git -C "$S" checkout -q -- bordbuch/README.md

echo
echo "=== Umstellen ==="
A=$(ABBILD_DA=0 bash "$S/werkzeuge/umstellen.sh" www 2>&1); R=$?
pruefe "ohne veroeffentlichtes Abbild: nichts wird angefasst" "1" "$R"
pruefe "und nichts ist vorgemerkt" "" "$(git -C "$S" status --porcelain -- www)"
pruefe "die Meldung nennt den Tag, der veroeffentlicht" "ja" \
  "$(ja 'grep -q "git tag v" <<<"$A"')"

for w in wiki bordbuch www; do
  A=$(bash "$S/werkzeuge/umstellen.sh" "$w" 2>&1); R=$?
  pruefe "$w: umstellen laeuft durch" "0" "$R"
  [ "$R" -eq 0 ] || printf '%s\n' "$A" | tail -6
done
git -C "$S" commit -q -m "umgestellt" || true

UEBRIG=$(cd "$S/wiki" && ls -A | tr '\n' ' ')
pruefe "wiki/ enthaelt nur noch Betriebsdateien" \
  ".env.beispiel .gitignore LIESMICH.md aktualisierung.conf docker-compose.override.yml docker-compose.yml geheimnisse.conf sicherung.conf " \
  "$UEBRIG"
pruefe "die Herstellerdatei hat kein build: mehr" "nein" \
  "$(ja 'grep -qE "^\s*build:" "$S/wiki/docker-compose.yml"')"
pruefe "aktualisierung.conf holt statt zu bauen" 'TYP="image"' \
  "$(grep -m1 '^TYP=' "$S/bordbuch/aktualisierung.conf")"
pruefe "das Bedienhandbuch liegt in doku/" "ja" "$(ja '[ -f "$S/doku/prolo-bedienen.html" ]')"
pruefe "CLAUDE.md zeigt dorthin" "0" "$(grep -c 'wiki/vorlagen/prolo-bedienen' "$S/CLAUDE.md")"
V=$(cd "$S/bordbuch" && docker compose config --no-interpolate --format json 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(sorted(v['name'] for v in d['volumes'].values())))")
pruefe "die Volumes heissen wie vorher" "bordbuch_bordbuch_belege bordbuch_bordbuch_daten" "$V"

echo
echo "=== Der Stapel prueft nach dem Umzug weiter ==="
for p in grenze-pruefen.sh schriften-pruefen.sh regeln-pruefen.sh sicherung-pruefen.sh \
         netze-pruefen.sh geheimnisse-pruefen.sh einrichten-pruefen.sh dockerfile-pruefen.sh; do
  ( cd "$S" && bash "werkzeuge/$p" > "$T/nach-$p.txt" 2>&1 ); R=$?
  pruefe "nach dem Umzug gruen: $p" "0" "$R"
  [ "$R" -eq 0 ] || grep -E "^FEHLER" "$T/nach-$p.txt" | head -3
done
( cd "$S" && python3 werkzeuge/prolo-befehle-pruefen.py . > "$T/nach-befehle.txt" 2>&1 ); R=$?
pruefe "nach dem Umzug gruen: prolo-befehle-pruefen.py" "0" "$R"
pruefe "grenze-pruefen sieht weiter alle vier eigenen Werkzeuge" "ja" \
  "$(ja 'grep -q "gefunden (4: admin, bordbuch, wiki, www)" "$T/nach-grenze-pruefen.sh.txt"')"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "PROBE FEHLGESCHLAGEN." >&2; fi

# --- Mutationsprobe (§13a) -------------------------------------------------
if [ "${1:-}" = "--gegenprobe" ] && [ -z "${AUSLAGERN_MUTATION:-}" ]; then
  echo
  echo "=== Mutationsprobe ==="
  DURCH=0; NR=0
  while IFS='|' read -r NAME DATEI AUSDRUCK; do
    [ -n "$NAME" ] || continue
    NR=$((NR + 1))
    cp "$HIER/$DATEI" "$T/probe"; sed -i "$AUSDRUCK" "$T/probe"
    if cmp -s "$HIER/$DATEI" "$T/probe"; then
      printf 'ABBRUCH   %s (liess sich nicht einbauen)\n' "$NAME"; DURCH=$((DURCH + 1)); continue
    fi
    if AUSLAGERN_MUTATION="$DATEI|$AUSDRUCK" bash "$0" >/dev/null 2>&1; then
      printf 'ENTWISCHT %s  <-- Testluecke\n' "$NAME"; DURCH=$((DURCH + 1))
    else
      printf 'gefunden  %s\n' "$NAME"
    fi
  done <<'MUT'
die Betriebsdateien gehen mit ins Werkzeug-Repo|auslagern.sh|s/^BETRIEB="docker-compose.override.yml sicherung.conf aktualisierung.conf geheimnisse.conf LIESMICH.md"$/BETRIEB=""/
ein Ziel mit Inhalt wird trotzdem beschrieben|auslagern.sh|s/^  if \[ -n "\$REFS" \]; then$/  if false; then/
nicht Eingechecktes haelt nicht an|auslagern.sh|s/^if \[ -n "\$(git -C "\$STACK" status --porcelain -- "\$W")" \]; then$/if false; then/
umstellen laesst build: stehen|umstellen.sh|s/^t = re.sub(r"(?m)^\\s\*build:\\s\*\\.\\s\*\\n", "", t)$/pass/
umstellen baut weiter statt zu holen|umstellen.sh|s/^sed -i 's\/\^TYP="build"\/TYP="image"\/'/: sed -i 's\/^TYP="build"\/TYP="image"\/'/
umstellen prueft das Abbild nicht|umstellen.sh|s/^  if ! AUSGABE=\$(docker manifest inspect "\$BILD" 2>&1); then$/  if false; then/
MUT
  echo "gefunden: $((NR - DURCH))   entwischt: $DURCH"
  [ "$DURCH" -eq 0 ] || exit 1
fi
exit "$FEHLER"
