# Bordbuch - Fahrzeug-Bordbuch fuer den Stack hinter Traefik und Authentik.
#
# Feste Fassung statt "latest" (Regel 5): eine Hauptversion weiter koennte
# Verhalten aendern, und die Datenbank wandert nur vorwaerts.
FROM python:3.13-slim

# Bordbuch braucht ausdruecklich KEINE Fremdpakete - nur die
# Standardbibliothek. Darum kein pip, kein requirements.txt, kein Bauschritt.
WORKDIR /app
COPY server.py index.html ./

# Datenbank unter /daten, Belege unter /belege - zwei benannte Volumes,
# beide in sicherung.conf eingetragen.
ENV BORDBUCH_DB=/daten/bordbuch.db \
    BORDBUCH_BELEGE=/belege \
    LADELOG_HOST=0.0.0.0 \
    LADELOG_PORT=8080 \
    BORDBUCH_ADMIN_GRUPPE=bordbuch-admin \
    BORDBUCH_ABMELDEN=/outpost.goauthentik.io/sign_out \
    BORDBUCH_HEADER_VERTRAUEN=1 \
    PYTHONUNBUFFERED=1

# Nicht als root laufen. Die Kennung ist fest, damit die Rechte im Volume
# nach einem Neubau des Abbilds dieselben bleiben.
# Rechte ausdruecklich setzen: COPY uebernimmt die Rechte der Quelldatei, und
# eine versehentlich mit 600 gepackte Datei waere fuer den unprivilegierten
# Nutzer unlesbar - der Container startete dann in einer Schleife.
RUN chmod 0644 /app/server.py /app/index.html \
    && useradd --system --uid 10001 --home-dir /daten bordbuch \
    && mkdir -p /daten /belege && chown -R bordbuch:bordbuch /daten /belege
USER bordbuch
VOLUME ["/daten", "/belege"]

# Keine ports-Zeile im Compose-File - erreichbar ist der Dienst nur ueber
# Traefik. EXPOSE dient allein der Dokumentation im Docker-Netz.
EXPOSE 8080

# /api/version antwortet ohne Anmeldung und ohne Datenbankzugriff.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/version',timeout=4).status==200 else 1)"

CMD ["python3", "server.py"]
