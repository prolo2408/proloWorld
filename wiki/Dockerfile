FROM python:3.13-slim-bookworm

# poppler-utils liefert pdftotext. Das ist die einzige Abhaengigkeit
# ausserhalb der Standardbibliothek und der Grund, warum die Suche auch
# Inhalte aus PDF-Anhaengen findet.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py index.html ./
COPY schriften/ ./schriften/

# Keine Geheimnisse per # PYTHONDONTWRITEBYTECODE (B-29): mit read_only: true ist das
# Programmverzeichnis nicht beschreibbar, und Python wuerde bei jedem Start
# erfolglos versuchen, __pycache__ neben server.py zu schreiben. Ein
# Kommentar gehoert NICHT in eine Fortsetzungszeile mit Backslash - darum
# steht er hier.
ENV - die kommen aus der .env ueber compose.
ENV WIKI_DATEN=/daten \
    WIKI_SEITEN=/seiten \
    WIKI_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd -r -u 10001 wiki && mkdir -p /daten /seiten && chown wiki /daten /seiten
USER wiki

EXPOSE 8080
CMD ["python3", "server.py"]
