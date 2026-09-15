#!/bin/bash
# Prueft die Testsuite selbst (Regelblatt 13, B-12).
#
# Es werden nacheinander echte Fehler in server.py eingebaut. Jeder MUSS von
# einem Test gefunden werden - sonst ist der Test Beschaeftigung. Am Ende wird
# die Datei wieder hergestellt.
set -u
cd "$(dirname "$0")/.."

SICHER=$(mktemp)
cp server.py "$SICHER"
aufraeumen() { cp "$SICHER" server.py; rm -f "$SICHER"; }
trap aufraeumen EXIT

FEHLER=0

probe() {
  local name="$1"; shift
  cp "$SICHER" server.py
  if ! python3 - "$@" <<'PY'
import sys
p = "server.py"
alt, neu = sys.argv[1], sys.argv[2]
s = open(p).read()
if alt not in s:
    sys.stderr.write("Mutationsstelle nicht gefunden - Gegenprobe anpassen\n")
    sys.exit(2)
open(p, "w").write(s.replace(alt, neu, 1))
PY
  then
    echo "AUFBAU-FEHLER  $name"; FEHLER=1; return
  fi
  if python3 -m unittest discover -s tests -t tests >/dev/null 2>&1; then
    echo "NICHT GEFUNDEN $name  <- die Tests decken diesen Fehler nicht ab"
    FEHLER=1
  else
    echo "gefunden       $name"
  fi
}

echo "=== Gegenprobe: jeder eingebaute Fehler muss gefunden werden ==="

probe "Rundung zur geraden Zahl statt kaufmaennisch" \
  'rounding=decimal.ROUND_HALF_UP))' \
  'rounding=decimal.ROUND_HALF_EVEN))'

probe "stille Null statt None bei unlesbarer Eingabe" \
  '    except (decimal.InvalidOperation, ValueError, TypeError):
        return None' \
  '    except (decimal.InvalidOperation, ValueError, TypeError):
        return 0'

probe "Netto als Fliesskommazahl runden" \
  '    satz = decimal.Decimal(str(satz))
    return int((decimal.Decimal(int(brutto_ct)) / (1 + satz / 100))
               .quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))' \
  '    return int(round(float(brutto_ct) / (1 + float(satz) / 100.0)))'

probe "Mehrwertsteuer unabhaengig rechnen statt als Differenz" \
  '    return int(brutto_ct) - netto_ct(brutto_ct, satz)' \
  '    satz = decimal.Decimal(str(satz))
    return int(decimal.Decimal(int(brutto_ct)) * satz / (100 + satz))'

probe "Plausibilitaetsgrenzen abschalten" \
  '    lo, hi = GRENZEN[grenze]
    if not (lo <= w <= hi):' \
  '    lo, hi = GRENZEN[grenze]
    if False:'

probe "Zukunftspruefung beim Zeitstempel abschalten" \
  '    if d > datetime.date.today() + datetime.timedelta(days=zukunft_tage):
        return ""
    if d.year < FRUEHESTES_JAHR:
        return ""
    return v' \
  '    return v'

probe "Gruppentrennung nur an Komma (der Fehler aus B-30)" \
  'return {g.strip() for g in re.split(r"[|,;]", roh or "") if g.strip()}' \
  'return {g.strip() for g in (roh or "").split(",") if g.strip()}'

# N-02: der Vorgabewert, der den Befund ausgemacht hat - zurueckgebaut.
probe "Pflichttext still durch eine Vorgabe ersetzen (der Fehler aus N-02)" \
  '    if not wert:
        return None, meldung
    return wert, None' \
  '    if not wert:
        return "Auto", None
    return wert, None'

# N-02, zweite Stelle: der Fallstrick mit der Null.
probe "Pflichttext mit or-Kurzschluss (0 faellt als leer durch)" \
  'wert = "" if roh is None else roh if isinstance(roh, str) else str(roh)' \
  'wert = str(roh or "")'

echo
if [ "$FEHLER" -eq 0 ]; then
  echo "Alle eingebauten Fehler wurden gefunden."
else
  echo "GEGENPROBE FEHLGESCHLAGEN - mindestens ein Fehler blieb unentdeckt." >&2
fi
exit "$FEHLER"
