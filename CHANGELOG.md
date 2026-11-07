# 2.3.0

Sicherheit – aus einem Angriff von allen Seiten (N-135 bis N-145, Einzelheiten
in `BEFUNDE.md`). **Vor dem Mergen auf einem Testserver
`sudo python3 tests/durchlauf.py` fahren** – das nächtliche Update spielt es
sonst ungeprüft ein.

- **Compose-Dateien: Erlaubnisliste statt Sperrliste** (`kern/kaefig.py`).
  Was prolo nicht kennt, ist eine Gefahr. Geschlossen u. a.: Volumes mit
  `driver_opts` (Dateisystem des Servers), fremde Volume- und Netznamen
  (Datenbank von Authentik), `secrets`/`configs`/`env_file`/`build` mit Pfaden
  vom Server, `volumes_from`/`pid`/`ipc` fremder Container, `post_start`
  privilegiert, `provider`, `use_api_socket` (N-135).
- **Der Ordner eines Tools ist fremd:** kein Schreiben durch Verweise
  (`.env.neu` → `authorized_keys`), keine Verweise nach draußen, keine
  Einhängung von `.git`, von Dateien, die root liest, oder ineinander (N-136).
- **Prüfung als Nutzer `prolo-pruefer`, ohne Rechte und ohne Netz**, auf einer
  Kopie: `include`/`extends` können keine fremden Dateien und nichts aus Git
  oder einer Registry mehr einschleusen (N-137, N-145).
- **Geprüft wird vor jedem Start** – auch Aktualisieren (eine gefährliche
  neue Fassung aus Git wird zurückgesetzt), Starten, Neustarten, Zurückholen.
  Auf der Kommandozeile Bestätigtes merkt sich prolo (N-138).
- **Traefik sieht Docker nicht mehr:** kein Docker-Provider, kein
  `socket-proxy`. Router als Dateien (`unterbau.yml`, `tool-<name>.yml`) –
  Labels eines Abbilds können `admin.`/`auth.` nicht mehr übernehmen (N-139).
- **Eigenes Anmelde-Cookie für die Admin-Seite**, nur für die Admin-Gruppe –
  das Cookie der Tools gilt dort nicht (N-140).
- **`ADMIN_NETZE`** in `prolo.conf`: Admin-Seite auf Wunsch nur aus deinen
  Netzen (N-141, N-143).
- `tool set --host` prüft wie `tool add` (N-144); der Agent übersteht einen
  Ordner im Eingang (N-142).

Beim Update legt `prolo einrichten` jedes Tool einmal neu an (neuer Name für
Traefik), nach der Prüfung. Findet die neue Prüfung bei einem Tool etwas, das
früher auf der Kommandozeile durchging, bleibt es stehen und „Was zu tun ist“
sagt: `sudo prolo einrichten` und bestätigen.

# 2.2.0

- **Private Git-Repositories:** Git-Zugänge, einer je Anbieter, unter
  Einstellungen → Git-Zugänge oder mit `prolo git-zugang`. prolo prüft den
  Token, liest das Ablaufdatum und warnt 14 Tage vorher; *Zugang testen*
  zeigt, ob ein Repository lesbar ist. Scheitert ein Klonen oder Update,
  sagt die Meldung, was fehlt (N-134).

# 2.1.0

- **Bearbeiten** auf der Seite eines Tools (und `prolo tool edit`): die
  Compose-Datei ändern und Variablen setzen. Vorher wird gesichert, geprüft
  wie beim Anlegen; kommt das Tool danach nicht hoch, gilt wieder der Stand
  davor (N-131).
- Eine Compose-Datei ohne Port wird auch auf einem frischen Server
  angenommen – prolo holt das Abbild, bevor es nach dem Port fragt (N-130).

# 2.0.0

ProloWelt ist nur noch der Unterbau (U-05). Neu aufsetzen statt
aktualisieren – siehe `README.md`, „Installieren“.

- `install.sh` richtet einen frischen Debian/Ubuntu-Server ein: Docker,
  Firewall (ufw: SSH, 80, 443), nächtliche Sicherheitsupdates des Systems,
  dann `prolo einrichten`.
- Der Unterbau ist ein Compose-Projekt: Traefik v3.6, Authentik 2026.8 mit
  Postgres 16, Docker-Vermittler, Admin-Seite. Einstellungen und
  Geheimnisse in `/etc/prolo`, nicht im Repository.
- Authentik schützt alle Subdomains über einen Blueprint – ein neues Tool
  braucht in Authentik nichts.
- Tools unter `/opt/tools/<name>/`, aus Abbild, Compose-Datei oder Git;
  eigenes Netz, keine offenen Ports, Anmeldung als Vorgabe.
- `prolo backup` / `prolo restore`: anhalten, packen, verschlüsseln, jedes
  Stück wieder lesen; Tool, entferntes Tool oder Unterbau zurückholen.
  Jede Nacht um 03:30, danach `prolo update`.
- Admin-Seite neu: Übersicht, Tools installieren und verwalten, Sicherungen,
  Aufträge – ohne Zugriff auf Docker, über den Agenten auf dem Server.
- Entfallen: Wiki, Bordbuch, www, n8n (jetzt eigene Tools), CrowdSec,
  `X-Prolo-Einlass`, die `*.conf`-Dateien je Tool und ihre Prüfskripte.
