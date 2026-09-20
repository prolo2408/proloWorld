FROM python:3.13-slim-bookworm

WORKDIR /app
COPY server.py ./
COPY schriften/ ./schriften/

# PYTHONDONTWRITEBYTECODE: das Programmverzeichnis ist schreibgeschuetzt
# (read_only im Compose-File), Python wuerde sonst bei jedem Start erfolglos
# versuchen, __pycache__ neben server.py anzulegen.
ENV ADMIN_DATEN=/daten \
    ADMIN_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Eigene Gruppe und chown MIT Gruppe: ohne Gruppenangabe bliebe die Gruppe
# der Ordner die des Erzeugers, und wer sich auf Gruppenrechte verlaesst,
# steht im Dunkeln.
RUN groupadd -r -g 10004 admin \
 && useradd -r -u 10004 -g admin admin \
 && mkdir -p /daten \
 && chown -R admin:admin /daten
USER admin

EXPOSE 8080

# /gesundheit ist einer der beiden Pfade, die die Vertrauensgrenze
# ausdruecklich frei laesst und die nichts preisgeben (§19, N-44).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/gesundheit',timeout=4).status==200 else 1)"

CMD ["python3", "server.py"]
