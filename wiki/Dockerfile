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

# Keine Geheimnisse per ENV - die kommen aus der .env ueber compose.
ENV WIKI_DATEN=/daten \
    WIKI_SEITEN=/seiten \
    WIKI_PORT=8080 \
    PYTHONUNBUFFERED=1

RUN useradd -r -u 10001 wiki && mkdir -p /daten /seiten && chown wiki /daten /seiten
USER wiki

EXPOSE 8080
CMD ["python3", "server.py"]
