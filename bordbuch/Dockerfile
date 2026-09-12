FROM python:3.13-slim

WORKDIR /app

# Nur was der Dienst zur Laufzeit braucht.
COPY server.py index.html ./

# Daten liegen ausserhalb des Abbilds, damit ein Update sie nicht anfasst.
RUN mkdir -p /app/daten /app/receipts

ENV BORDBUCH_DB=/app/daten/bordbuch.db \
    LADELOG_HOST=0.0.0.0 \
    LADELOG_PORT=8080

EXPOSE 8080

CMD ["python3", "server.py", "--header-vertrauen"]
