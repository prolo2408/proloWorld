# crowdsec — die Firewall des Stapels

CrowdSec liest, was an der Tür passiert, erkennt darin Angriffe und
entscheidet Sperren. Durchgesetzt werden sie vom **Firewall-Bouncer** auf
dem Server: er holt die Sperren alle paar Sekunden über die lokale API
(`127.0.0.1:8080`) und trägt sie in nftables ein. Eine gesperrte Adresse
erreicht danach **nichts** mehr auf dem Server — keinen Dienst hinter
Traefik und kein SSH.

```
Anfrage ──► Traefik ──► zugriff.log ──► CrowdSec ──► Sperre ──► Bouncer ──► nftables
SSH     ──► sshd    ──► auth.log    ──┘   (Regeln)    (Datenbank)  (Server)   (verwirft)
```

## Was gelesen wird

| Quelle | Datei | Erfassung |
|---|---|---|
| jede Anfrage über Traefik | `traefik/log/zugriff.log` (JSON, B-26) | `erfassung/traefik.yaml` |
| SSH-Anmeldungen | `/var/log/auth.log` des Servers | `erfassung/ssh.yaml` |

Beide werden als **Ordner** eingehängt, nur lesend — logrotate ersetzt die
Dateien jede Nacht (`N-106`). Schreibt Debian nur ins Journal und es gibt
keine `auth.log`: `sudo apt install rsyslog`.

## Die Regeln

**Aus dem Hub** (holt CrowdSec beim Start, `COLLECTIONS` in der
Compose-Datei): SSH-Raten, bekannte Lücken (CVE), Pfad-Scanner, schlechte
Bots und mehr. Gepflegt von CrowdSec, aktuell gehalten bei jedem Start.

**Eigene** in `regeln/` — die „besonderen Regeln" für genau diesen Stapel:

| Datei | was | Sperre |
|---|---|---|
| `zugangslink-raten.yaml` | 10 unbekannte Zugangslinks von `www` in kurzer Folge | 24 h |
| `falle.yaml` | ein einziger Aufruf eines Pfads, den es hier nie gibt (`/wp-login.php`, `/.env`, `/.git/` …) | 24 h |

**Wie lange** gesperrt wird, steht in `profiles.yaml`: eigene Regeln 24
Stunden, alles andere 4 Stunden — und jedes Wiederkommen 4 Stunden mehr.

### Eine eigene Regel bauen

1. Eine Datei in `regeln/` anlegen, am einfachsten eine vorhandene
   kopieren. Die wichtigen Felder:
   - `filter` — welche Zeilen zählen. Zur Hand: `evt.Meta.source_ip`,
     `evt.Meta.http_path`, `evt.Meta.http_status` (als Text, `'404'`),
     `evt.Meta.http_verb`, `evt.Meta.log_type` (`http_access-log` für
     Traefik, `ssh_failed-auth` für SSH).
   - `type: trigger` sperrt beim ersten Treffer; `type: leaky` zählt: ein
     Eimer je Adresse fasst `capacity` Treffer und verliert alle
     `leakspeed` einen — wer ihn zum Überlaufen bringt, ist gesperrt.
   - `name` beginnt mit `prolo/` — dann gilt die Dauer der eigenen Regeln.
2. `sudo prolo neustart crowdsec`.
3. `docker exec crowdsec cscli scenarios list` zeigt sie danach als
   `local`.

Alle Felder beschreibt die Dokumentation von CrowdSec (docs.crowdsec.net)
unter *Scenarios → Format*.

Bevor eine neue Regel scharf geschaltet wird, lässt sie sich **nur
beobachten**: `docker exec crowdsec cscli simulation enable prolo/<name>` —
dann entstehen Meldungen, aber keine Sperren.

## Wo man es sieht

- **Auf dem Server**: `sudo prolo firewall` — aktive Sperren, Meldungen der
  letzten sieben Tage, die Freigabeliste, was gelesen wird, und ob der
  Bouncer abholt. Sperren, aufheben, freigeben:

      sudo prolo firewall sperren 203.0.113.7 12h "raet Zugangslinks"
      sudo prolo firewall aufheben 203.0.113.7
      sudo prolo firewall erlauben 198.51.100.20 "Buero"
      sudo prolo firewall nicht-mehr-erlauben 198.51.100.20
- **Freiwillig, die CrowdSec-Konsole** (<https://app.crowdsec.net>): Karte,
  Verlauf, Blocklisten. Dafür dort einen Schlüssel unter *Security Engines
  → Enroll* holen, in `crowdsec/.env` bei `CROWDSEC_KONSOLE_SCHLUESSEL`
  eintragen, `sudo prolo neustart crowdsec` und die Anmeldung in der
  Konsole bestätigen. Die Konsole sieht Meldungen (Adresse des Angreifers,
  Regel, Zeit) — **nicht** die Protokolle selbst.

## Was CrowdSec nach draußen gibt

Auch ohne Konsole meldet CrowdSec erkannte Angriffe an die Gemeinschaft
(Adresse des Angreifers, Regel, Zeitpunkt) und bekommt dafür die
**Gemeinschafts-Blockliste**: Adressen, die anderswo schon aufgefallen sind,
werden hier gesperrt, bevor sie anklopfen. Wer das nicht will:
`DISABLE_ONLINE_API: "true"` in der Compose-Datei — dann ohne die Liste.

## Ausgesperrt?

Die eigene Adresse in die Freigabeliste, solange man noch drin ist:

    sudo prolo firewall erlauben <adresse> "Zuhause"

Ist es schon passiert: von einem anderen Anschluss (Handy ohne WLAN) per
SSH auf den Server oder über die Web-Konsole des Anbieters, dann

    sudo prolo firewall aufheben <adresse>
    sudo prolo firewall erlauben <adresse> "Zuhause"

## Wem welche Datei gehört

| Datei | von | Inhalt |
|---|---|---|
| `docker-compose.yml` | uns | Abbild, Grenzen, Einhängungen |
| `config.yaml.local` | uns | zeigt CrowdSec die Erfassung |
| `erfassung/` | uns | was gelesen wird |
| `regeln/` | uns | die eigenen Regeln |
| `profiles.yaml` | uns | wie lange gesperrt wird |
| `.env` | Server | Bouncer-Schlüssel, Konsolen-Schlüssel — nie ins Git |
| Volume `crowdsec-konfig` | CrowdSec | was aus dem Hub kam |
| Volume `crowdsec-daten` | CrowdSec | Sperren, Meldungen, Freigabeliste |
