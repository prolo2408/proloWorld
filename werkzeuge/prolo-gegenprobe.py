#!/usr/bin/env python3
"""werkzeuge/prolo-gegenprobe.py

Mutationsprobe zu werkzeuge/prolo-pruefen.sh (N-69).

Handgerechnete Erwartungswerte reichen nicht: ein Test kann gruen sein,
weil er nichts prueft (CLAUDE.md §13a). Darum baut dieses Skript
absichtlich Fehler ein und verlangt, dass JEDER von einer Pruefzeile
gefunden wird. Bleibt einer unentdeckt, ist das eine Testluecke und wird
geschlossen - nicht ausgeklammert.

Die Fehler landen in der KOPIE, die prolo-pruefen.sh sich in seinen
Wegwerfordner legt. Der Arbeitsstand wird nie angefasst: eine Probe, die
ueber "git checkout" zurueckrollen muesste, loescht eine noch nicht
eingecheckte Korrektur mit weg (N-34, N-60).
"""
import os
import subprocess
import sys
import tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PRUEFER = os.path.join(HIER, "prolo-pruefen.sh")

# (Name, Datei, alt, neu)
MUTATIONEN = [
    ("die Folgerung zum FREMDen Namen entfaellt ganz",
     "prolo",
     "  if [ -n \"$ZIEL\" ] && { [ \"$ZERT\" = keins ] || [ \"$ZERT\" = notbehelf ]; }; then\n    printf 'dns\\n'",
     "  if [ -n \"\" ] && { [ \"$ZERT\" = keins ] || [ \"$ZERT\" = notbehelf ]; }; then\n    printf 'dns\\n'"),

    ("der A-Eintrag zeigt auf die gefundene statt auf die eigene IP",
     "prolo",
     """    printf '  A-Eintrag fuer %s auf %s setzen.\\n' "$NAME" "$SOLL"
    return 0
  fi

  # Der Name zeigt woanders hin""",
     """    printf '  A-Eintrag fuer %s auf %s setzen.\\n' "$NAME" "$IP"
    return 0
  fi

  # Der Name zeigt woanders hin"""),

    ("ohne bekannte Server-IP bleibt die Stelle einfach leer",
     "prolo",
     'SOLL="${EIGEN:-die IP dieses Servers}"',
     'SOLL="${EIGEN:-}"'),

    ("ein Notzertifikat gilt als gutes Zertifikat",
     "prolo",
     "        zert=notbehelf",
     "        zert=gut"),

    ("auch ein heiler Name bekommt eine Folgerung",
     "prolo",
     "  return 1\n}\n\n# Die Erklaerung zu einer Art von Folgerung",
     "  printf 'dns\\n%s ist vielleicht auch nicht in Ordnung.\\n' \"$NAME\"\n  return 0\n}\n\n# Die Erklaerung zu einer Art von Folgerung"),

    ("status folgert richtig und gibt es nie aus",
     "prolo",
     """    printf '%s' "$folgerungen" | sed 's/^/  /'""",
     """    printf '%s' "" | sed 's/^/  /'"""),

    ("die Erklaerung kommt je Name statt je Art (Tapete)",
     "prolo",
     '      case " $arten " in *" $art "*) ;; *) arten="$arten $art" ;; esac',
     '      arten="$arten $art"'),

    ("ein FREMDer Name wird gar nicht als fremd erkannt",
     "prolo",
     'ipfeld="$ip (FREMD)"; wohin=fremd',
     'ipfeld="$ip (FREMD)"; wohin=hier'),

    ("der DNS-Rat nennt den Befehl nicht mehr",
     "prolo",
     "Minute. Sofort versuchen lassen:\n  sudo prolo start traefik",
     "Minute."),

    ("der DNS-Rat verschweigt, wo der Handgriff zu tun ist",
     "prolo",
     "Zu tun ist es beim DNS-Anbieter, nicht auf dem Server.",
     "Zu tun ist noch etwas."),

    ("prolo dns verschweigt, dass das Zertifikat daran haengt",
     "prolo",
     '    melde "  Daran haengt das Zertifikat: Let\'s Encrypt prueft ueber Port 80"',
     '    melde "  (hier stand mal etwas)"'),

    ("prolo dns nennt die Ziel-IP nicht mehr",
     "prolo",
     '    melde "    A-Eintrag auf ${eigene:-die IP dieses Servers} setzen,"',
     '    melde "    A-Eintrag richtig setzen,"'),

    ("ein abgelaufenes Zertifikat gilt als vorhanden",
     "prolo",
     """        printf '  %-26s %-23s ABGELAUFEN seit %s Tagen\\n' "$name" "$ipfeld" "$(( -tage ))\"""",
     """        printf '  %-26s %-23s ABGELAUFEN seit %s Tagen\\n' "$name" "$ipfeld" "$(( -tage ))"
        zert=gut"""),

    ("die Spalte ZEIGT AUF ist wieder zu schmal fuer '(FREMD)' (N-71)",
     "prolo",
     """      printf '  %-26s %-23s keine Antwort auf 443\\n' "$name" "$ipfeld\"""",
     """      printf '  %-26s %-16s keine Antwort auf 443\\n' "$name" "$ipfeld\""""),

    ("hostnamen liest wieder nur die Herstellerdatei (N-70)",
     "prolo",
     """      "$STACK"/*/docker-compose.yml \\\n      "$STACK"/*/docker-compose.override.yml 2>/dev/null \\""",
     """      "$STACK"/*/docker-compose.yml 2>/dev/null \\"""),

    ("hostnamen liest nur noch die override-Datei",
     "prolo",
     """      "$STACK"/*/docker-compose.yml \\\n      "$STACK"/*/docker-compose.override.yml 2>/dev/null \\""",
     """      "$STACK"/*/docker-compose.override.yml 2>/dev/null \\"""),

    ("ein fremdes Zertifikat wird als unseres ausgegeben",
     "prolo",
     """    printf 'dort antwortet, nicht von diesem hier. Wer %s aufruft,\\n' "$NAME"
    printf 'landet nicht bei uns.\\n'""",
     """    printf 'dort antwortet.\\n'"""),
]


def main():
    gefunden = entwischt = 0
    for name, datei, alt, neu in MUTATIONEN:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(
                "import io, sys, os\n"
                "p = os.path.join(sys.argv[1], %r)\n"
                "s = io.open(p, encoding='utf-8').read()\n"
                "alt, neu = %r, %r\n"
                "if s.count(alt) != 1:\n"
                "    sys.stderr.write('Muster %%dx gefunden: %%r\\n' %% (s.count(alt), alt))\n"
                "    sys.exit(1)\n"
                "io.open(p, 'w', encoding='utf-8').write(s.replace(alt, neu))\n"
                % (datei, alt, neu))
            skript = f.name
        try:
            umg = dict(os.environ, PROLO_MUTATION=skript)
            lauf = subprocess.run(["bash", PRUEFER], env=umg,
                                  capture_output=True, text=True)
        finally:
            os.unlink(skript)

        if lauf.returncode == 3:
            print("ABBRUCH   %s" % name)
            for z in lauf.stderr.strip().splitlines()[-2:]:
                print("            " + z)
            entwischt += 1
        elif lauf.returncode != 0:
            print("gefunden  %s" % name)
            for z in lauf.stdout.splitlines():
                if z.startswith("FEHLER"):
                    print("            " + z)
            gefunden += 1
        else:
            print("ENTWISCHT %s  <-- Testluecke" % name)
            entwischt += 1

    print("")
    print("gefunden: %d   entwischt: %d" % (gefunden, entwischt))
    return 1 if entwischt else 0


if __name__ == "__main__":
    sys.exit(main())
