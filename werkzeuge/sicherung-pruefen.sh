#!/bin/bash
# werkzeuge/sicherung-pruefen.sh
#
# Gegenprobe zu werkzeuge/volumes.py (N-76).
#
# Baut einen Wegwerfstack und fragt zu jedem Fall: sieht der Pruefer, was
# dort entsteht? Der wichtigste Fall ist "fremd" - ein Werkzeug, dessen
# Volume in der HERSTELLERDATEI steht und dessen sicherung.conf leer ist.
# Genau so lief bitwarden: der Container lief, die Sicherung meldete
# Erfolg, und gesichert war nichts.
set -uo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
FEHLER=0
S="$T/stack"

# Einstieg fuer die Mutationsprobe. Sie baut ihre Fehler in eine KOPIE im
# Wegwerfordner ein, nie in die Datei im Arbeitsstand (N-34, N-60).
PRUEFLING="$HIER/volumes.py"
if [ -n "${PROLO_MUTATION:-}" ]; then
  cp "$HIER/volumes.py" "$T/volumes.py"
  python3 "$PROLO_MUTATION" "$T" || {
    echo "FEHLER Mutation liess sich nicht einbauen" >&2; exit 3; }
  PRUEFLING="$T/volumes.py"
fi

pruefe() {
  if [ "$3" = "$2" ]; then printf 'ok     %s\n' "$1"
  else printf 'FEHLER %s\n       erwartet: %s\n       ist:      %s\n' "$1" "$2" "$3"; FEHLER=1; fi
}

werkzeug() {  # $1 Name
  mkdir -p "$S/$1"
}

# --- 1. heil: das Volume steht in der sicherung.conf -----------------
werkzeug heil
cat > "$S/heil/docker-compose.yml" <<'Y'
services:
  heil:
    image: heil:1
    volumes:
      - daten:/daten
volumes:
  daten:
Y
printf 'VOLUMES="heil_daten"\nORDNER=""\nDATEIEN=""\n' > "$S/heil/sicherung.conf"

# --- 2. luecke: das Volume steht NIRGENDS ----------------------------
werkzeug luecke
cat > "$S/luecke/docker-compose.yml" <<'Y'
services:
  luecke:
    image: luecke:1
    volumes:
      - daten:/daten
volumes:
  daten:
Y
printf 'VOLUMES=""\nORDNER=""\nDATEIEN=""\n' > "$S/luecke/sicherung.conf"

# --- 3. erklaert: es braucht keine Sicherung, und das steht da -------
werkzeug erklaert
cat > "$S/erklaert/docker-compose.yml" <<'Y'
services:
  erklaert:
    image: erklaert:1
    volumes:
      - zwischenspeicher:/cache
volumes:
  zwischenspeicher:
Y
printf 'VOLUMES=""\nORDNER=""\nDATEIEN=""\nVOLUMES_OHNE="erklaert_zwischenspeicher|nur Zwischenspeicher"\n' \
  > "$S/erklaert/sicherung.conf"

# --- 4. fremd: das Volume steht in der Herstellerdatei (der Fall) ----
werkzeug fremd
cat > "$S/fremd/docker-compose.yml" <<'Y'
services:
  fremd:
    image: hersteller/fremd:1.2.3
    volumes:
      - fremd_data:/data
volumes:
  fremd_data:
Y
# Und ein Volume, das ERST im Overlay dazukommt - unsere Zutat neben der
# Herstellerdatei (§16). Ohne diesen Fall bliebe die Mutation "lies nur
# die Herstellerdatei" unentdeckt: gruen aus Mangel an Gelegenheit (N-68).
cat > "$S/fremd/docker-compose.override.yml" <<'Y'
services:
  fremd:
    networks: [ netz-fremd ]
    volumes:
      - unseres:/unseres
networks:
  netz-fremd:
    external: true
volumes:
  unseres:
Y
printf 'VOLUMES=""\nORDNER=""\nDATEIEN="?.env"\n' > "$S/fremd/sicherung.conf"

# --- 5. bind: ein Bind-Mount aus dem Werkzeugordner ------------------
werkzeug bind
mkdir -p "$S/bind/daten" "$S/bind/egal"
printf 'geheim\n' > "$S/bind/eine.conf"
cat > "$S/bind/docker-compose.yml" <<'Y'
services:
  bind:
    image: bind:1
    volumes:
      - ./daten:/daten
      - ./egal:/egal
      - ./eine.conf:/etc/eine.conf:ro
      - /etc/localtime:/etc/localtime:ro
Y
printf 'VOLUMES=""\nORDNER="?egal"\nDATEIEN=""\n' > "$S/bind/sicherung.conf"

# ---------------------------------------------------------------------
echo "=== Gegenprobe Sicherung ==="
A=$(python3 "$PRUEFLING" "$S" 2>&1); R=$?

lage() { printf '%s\n' "$A" | awk -F'|' -v t="$1" -v n="$3" -v a="$2" \
  '$1==t && $2==a && $3==n {print $4}'; }

pruefe "ein eingetragenes Volume gilt als gesichert" "gesichert" "$(lage heil volume heil_daten)"
pruefe "ein Volume, das nirgends steht, ist eine Luecke" "FEHLT" "$(lage luecke volume luecke_daten)"
pruefe "ein erklaertes Volume ist keine Luecke" "erklaert" "$(lage erklaert volume erklaert_zwischenspeicher)"

# Der Kern: die Herstellerdatei wird mitgelesen. Ohne das saehe der
# Pruefer bei einem Fremdwerkzeug NICHTS - und genau dort ist die Luecke.
# Der Laufzeitname ist <ordner>_<schluessel>, nicht der Schluessel. Genau
# daran vertippt man sich beim Eintragen von Hand - darum nennt die
# Meldung ihn ausgeschrieben, statt "trag dein Volume ein" zu sagen.
pruefe "das Volume aus der Herstellerdatei wird gesehen" "FEHLT" \
  "$(lage fremd volume fremd_fremd_data)"
pruefe "und zwar unter seinem LAUFZEITnamen" "ja" \
  "$(printf '%s\n' "$A" | grep -q 'fremd|volume|fremd_fremd_data|' && echo ja || echo nein)"
# Die andere Haelfte: was NUR im Overlay steht, zaehlt genauso. Ein
# Pruefer, der eine der beiden Dateien nicht liest, sieht bei einem
# Fremdwerkzeug die Haelfte (§16).
pruefe "ein Volume, das erst im Overlay dazukommt, wird gesehen" "FEHLT" \
  "$(lage fremd volume fremd_unseres)"

pruefe "ein Bind-Mount ohne Eintrag ist eine Luecke" "FEHLT" "$(lage bind bind daten)"
pruefe "ein Bind-Mount mit ?-Eintrag gilt als gesichert" "gesichert" "$(lage bind bind egal)"
# Ordner und Datei gehoeren in VERSCHIEDENE Zeilen der sicherung.conf
# (ORDNER bzw. DATEIEN). Wer das nicht unterscheidet, nennt in der
# Meldung die falsche - genau das ist bei bitwarden passiert (N-78).
pruefe "eine gebundene DATEI wird als solche gemeldet" "FEHLT" \
  "$(lage bind binddatei eine.conf)"
printf '%s\n' "$A" | grep -q 'bind|bind|eine.conf' && E=ja || E=nein
pruefe "und nicht als Ordner" "nein" "$E"
printf '%s\n' "$A" | grep -q 'localtime' && E=ja || E=nein
pruefe "ein Bind-Mount von ausserhalb des Werkzeugs zaehlt nicht" "nein" "$E"

pruefe "bei einer Luecke ist der Rueckgabewert 1" "1" "$R"

# --- Und ohne Luecke muss er 0 sein ----------------------------------
# Sonst waere der Pruefer nur ein Dauerwarner, den man nach dem dritten
# Mal wegklickt.
printf 'VOLUMES="luecke_daten"\nORDNER=""\nDATEIEN=""\n' > "$S/luecke/sicherung.conf"
printf 'VOLUMES="fremd_fremd_data fremd_unseres"\nORDNER=""\nDATEIEN="?.env"\n' > "$S/fremd/sicherung.conf"
printf 'VOLUMES=""\nORDNER="daten ?egal"\nDATEIEN="eine.conf"\n' > "$S/bind/sicherung.conf"
python3 "$PRUEFLING" "$S" >/dev/null 2>&1; R=$?
pruefe "ohne Luecke ist der Rueckgabewert 0" "0" "$R"

# --- Der Arbeitsstand selbst -----------------------------------------
python3 "$PRUEFLING" "$(dirname "$HIER")" >/dev/null 2>&1; R=$?
pruefe "im Arbeitsstand steht jedes Werkzeug vollstaendig da" "0" "$R"

echo
if [ "$FEHLER" -eq 0 ]; then echo "Alles gruen."; else echo "GEGENPROBE FEHLGESCHLAGEN." >&2; fi
exit "$FEHLER"
