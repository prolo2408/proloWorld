#!/bin/bash
# werkzeuge/crowdsec-probe/start.sh - NUR FUER DIE PROBE (F-01)
#
# Das Startskript des Abbilds holt beim Start den Hub (Parser, Regeln).
# Auf einem Pruefrechner ohne Hub bricht es daran ab. Dieses hier tut, was
# es sonst tut, aus dem, was das Abbild schon mitbringt - und legt die
# zwei Stellvertreter-Parser dazu. Geprueft wird damit UNSER Teil:
# Erfassung, eigene Regeln, Dauer der Sperren, Freigaben, Bouncer-Zugang.
set -e
if [ ! -e /etc/crowdsec/config.yaml ]; then
  rsync -a --ignore-existing /staging/etc/crowdsec/ /etc/crowdsec/
fi
for t in /staging/var/lib/crowdsec/data/*; do
  f=$(basename "$t"); case "$f" in crowdsec.db*) continue ;; esac
  [ -e "/var/lib/crowdsec/data/$f" ] || ln -s "$t" "/var/lib/crowdsec/data/$f"
done
cp /probe/stellvertreter-nicht-syslog.yaml /etc/crowdsec/parsers/s00-raw/
cp /probe/stellvertreter-traefik.yaml /etc/crowdsec/parsers/s01-parse/
cscli machines add localhost --auto --force -f /etc/crowdsec/local_api_credentials.yaml >/dev/null
# Wie im Startskript des Abbilds: BOUNCER_KEY_<name> meldet einen Bouncer an.
cscli bouncers add firewall -k "$BOUNCER_KEY_firewall" >/dev/null
exec crowdsec -c /etc/crowdsec/config.yaml
