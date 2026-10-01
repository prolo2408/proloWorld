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
