# Die Admin-Seite. Gebaut wird auf dem Server von "prolo einrichten" /
# "prolo update" - Kontext ist das ganze Repository, damit kern/auftrag.py
# hineinkommt (dieselbe Pruefung der Auftraege wie im Agenten).
FROM python:3.13-slim

WORKDIR /app
COPY kern/__init__.py kern/auftrag.py ./kern/
COPY admin/server.py ./admin/
COPY admin/schriften/ ./admin/schriften/

# Das Programmverzeichnis ist schreibgeschuetzt (read_only im Compose).
ENV ADMIN_DATEN=/daten \
    ADMIN_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 10004 steht auch in kern/orte.py (ADMIN_UID): nur dieser Nutzer darf in
# den Eingang des Auftragsbuchs schreiben.
RUN groupadd -r -g 10004 admin \
 && useradd -r -u 10004 -g admin admin \
 && mkdir -p /daten \
 && chown admin:admin /daten
USER admin

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/gesundheit',timeout=4).status==200 else 1)"

CMD ["python3", "admin/server.py"]
