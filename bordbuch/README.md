# Bordbuch

Fahrtenbuch mit Lade- und Tankkosten, Verbrauch und dem Vergleich Verbrenner gegen Elektro. Geld in ganzen Cent.

Ein Werkzeug des Prolo-Stapels. **Betrieben** wird es von
[`prolo2408/proloWorld`](https://github.com/prolo2408/proloWorld) — dort
stehen Netz, Route, Anmeldung (Authentik), Sicherung und Aktualisierung.
Hier stehen der Code und das Abbild.

Python-Standardbibliothek und SQLite, kein Fremdpaket.

## Arbeiten daran

```bash
./tests/alle.sh          # alle Tests; Rueckgabe 0 nur, wenn alles gruen ist
```

Die Regeln für jede Änderung — Oberfläche, Robustheit, der Vertrag mit dem
Betrieb — stehen in [`CLAUDE.md`](CLAUDE.md). Was schon einmal schiefging:
[`BEFUNDE.md`](BEFUNDE.md).

Lokal starten (ohne Traefik; jede Anfrage braucht dann die Kopfzeilen
`X-Prolo-Einlass` und `X-Authentik-Username`, die sonst der Zugang setzt):

```bash
PROLO_EINLASS=lokal BORDBUCH_DB=/tmp/b/bordbuch.db BORDBUCH_BELEGE=/tmp/b/belege BORDBUCH_HEADER_VERTRAUEN=1 LADELOG_PORT=8080 python3 server.py
curl -H 'X-Prolo-Einlass: lokal' -H 'X-Authentik-Username: ich' http://127.0.0.1:8080/
```

## Veröffentlichen

1. Fassung an drei Stellen erhöhen: `server.py` (`VERSION`),
   `docker-compose.yml` (`image:`), `CHANGELOG.md` (oberste Fassung).
2. `git tag v<fassung> && git push --tags`

Der Arbeitsablauf `.github/workflows/abbild.yml` prüft, baut das Abbild
`ghcr.io/prolo2408/bordbuch:<fassung>` und hängt die Herstellerdatei an die
Veröffentlichung. Eine Fassung, die es schon gibt, wird nicht überschrieben.

Auf dem Server: in `proloWorld` die Fassung in `bordbuch/docker-compose.yml`
hochsetzen, dann `sudo prolo aktualisieren bordbuch` — oder in der
Admin-Oberfläche „Fassung wechseln".

## Weitere Doku

- `ANLEITUNG.md` — die Bedienung im Einzelnen
