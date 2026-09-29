# Prolo Freigabe (www)

`prolo.me`: HTML-Seiten ablegen und je Empfänger einen widerrufbaren Zugangslink ausgeben. Startseite und Zugangslinks sind öffentlich, `/verwaltung` liegt hinter der Anmeldung.

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
PROLO_EINLASS=lokal WWW_DATEN=/tmp/x/daten WWW_SEITEN=/tmp/x/seiten WWW_PORT=8080 python3 server.py
curl -H 'X-Prolo-Einlass: lokal' -H 'X-Authentik-Username: ich' http://127.0.0.1:8080/
```

## Veröffentlichen

1. Fassung an drei Stellen erhöhen: `server.py` (`VERSION`),
   `docker-compose.yml` (`image:`), `CHANGELOG.md` (oberste Fassung).
2. `git tag v<fassung> && git push --tags`

Der Arbeitsablauf `.github/workflows/abbild.yml` prüft, baut das Abbild
`ghcr.io/prolo2408/www:<fassung>` und hängt die Herstellerdatei an die
Veröffentlichung. Eine Fassung, die es schon gibt, wird nicht überschrieben.

Auf dem Server: in `proloWorld` die Fassung in `www/docker-compose.yml`
hochsetzen, dann `sudo prolo aktualisieren www` — oder in der
Admin-Oberfläche „Fassung wechseln".

