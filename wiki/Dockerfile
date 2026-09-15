FROM python:3.13-slim-bookworm

# poppler-utils liefert pdftotext. Das ist die einzige Abhaengigkeit
# ausserhalb der Standardbibliothek und der Grund, warum die Suche auch
# Inhalte aus PDF-Anhaengen findet.
#
# Zu B-46 (keine Fassungsangabe beim apt-Paket): bewusst NICHT festgeschrieben.
# Eine feste apt-Fassung wirkt reproduzierbar, ist es aber nicht: Debian nimmt
# alte Paketfassungen aus dem Spiegel, sobald eine Sicherheitsaktualisierung
# nachrueckt, und der Bau schlaegt dann fehl - nicht irgendwann, sondern genau
# dann, wenn man dringend neu bauen muss. Die Reproduzierbarkeit kommt hier
# vom festen Basisabbild (bookworm), das den Paketstand einer
# Debian-Veroeffentlichung festlegt. Vermerkt ist das in CHANGELOG.md, wie der
# Bericht es als zweite Moeglichkeit vorsieht.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py index.html ./
COPY schriften/ ./schriften/

# Keine Geheimnisse per ENV - die kommen aus der .env ueber compose.
#
# PYTHONDONTWRITEBYTECODE (B-29): das Programmverzeichnis kann
# schreibgeschuetzt sein, und Python wuerde sonst bei jedem Start erfolglos
# versuchen, __pycache__ neben server.py anzulegen.
ENV WIKI_DATEN=/daten \
    WIKI_SEITEN=/seiten \
    WIKI_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Eigene Gruppe und chown MIT Gruppe (B-45). Vorher lautete es
# "useradd -r -u 10001 wiki" und "chown wiki /daten /seiten" - ohne
# Gruppenangabe blieb die Gruppe der Ordner die des Erzeugers, und wer sich
# auf Gruppenrechte verlaesst, steht im Dunkeln.
RUN groupadd -r -g 10001 wiki \
 && useradd -r -u 10001 -g wiki wiki \
 && mkdir -p /daten /seiten \
 && chown -R wiki:wiki /daten /seiten
USER wiki

EXPOSE 8080

# Gesundheitspruefung (B-45). Das Bordbuch hatte eine, das Wiki nicht - damit
# merkte Docker nicht, wenn der Dienst zwar laeuft, aber nicht mehr antwortet.
# /gesundheit ist der einzige Pfad ohne Anmeldung und genau dafuer da.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/gesundheit',timeout=4).status==200 else 1)"

CMD ["python3", "server.py"]
