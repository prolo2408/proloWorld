FROM python:3.13-slim-bookworm

WORKDIR /app
COPY server.py ./
COPY schriften/ ./schriften/

# Keine Geheimnisse per ENV - die kommen aus der .env ueber compose.
#
# PYTHONDONTWRITEBYTECODE: das Programmverzeichnis ist schreibgeschuetzt
# (read_only im Compose-File), Python wuerde sonst bei jedem Start erfolglos
# versuchen, __pycache__ neben server.py anzulegen.
ENV WWW_DATEN=/daten \
    WWW_SEITEN=/seiten \
    WWW_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Eigene Gruppe und chown MIT Gruppe: ohne Gruppenangabe bliebe die Gruppe
# der Ordner die des Erzeugers, und wer sich auf Gruppenrechte verlaesst,
# steht im Dunkeln.
RUN groupadd -r -g 10003 www \
 && useradd -r -u 10003 -g www www \
 && mkdir -p /daten /seiten \
 && chown -R www:www /daten /seiten
USER www

EXPOSE 8080

# /gesundheit ist der einzige Pfad, den die Vertrauensgrenze ausdruecklich
# frei laesst und der nichts preisgibt (CLAUDE.md §19, N-44).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/gesundheit',timeout=4).status==200 else 1)"

CMD ["python3", "server.py"]
