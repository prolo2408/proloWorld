# Prolo Freigabe — Änderungen

Geschrieben für den Nutzer, nicht für Entwickler. Neueste Fassung oben.

Fassungsnummern: letzte Stelle = Fehlerbehebung, mittlere = neue Funktion,
erste = etwas Bestehendes bricht.

## Fassung 1.0.0

Das Werkzeug auf `prolo.me`. Es tut drei Dinge:

- **Eine HTML-Datei ablegen.** Sie bleibt liegen, bis du sie löschst. Einen
  Zugang zurückzuziehen löscht nichts.
- **Zugangslinks ausgeben**, so viele du willst — einen je Bewerbung, mit
  Etikett, Zähler, Ablaufdatum. Jederzeit zurückziehbar **und wieder
  freischaltbar**: derselbe Link geht danach wieder.
- **Eine öffentliche Startseite**, die nichts verrät. Kein Name, keine
  Liste, kein Hinweis darauf, dass es etwas zu finden gibt.

Ein Passwort lässt sich je Link zuschalten und wieder wegnehmen.

### Warum Links statt eines Passworts für alle

Ein Link lässt sich **einzeln** zurückziehen, und an seinem Zähler sieht
man, ob er weitergereicht wurde. Ein gemeinsames Passwort kann beides
nicht: es gilt für alle, und wer es weitergibt, hinterlässt keine Spur.

**Was ein Link nicht ist: eine Anmeldung.** Wer ihn hat, kommt hinein. Das
ist der Preis dafür, dass jemand ohne Konto draufkommt — und der Grund für
Ablaufdatum, Zähler und Widerruf.

### Was dabei geschützt ist

| | |
|---|---|
| Die Marke im Link | 192 Bit aus `secrets`, nicht zu erraten |
| Gespeichert | **nur ihr Abdruck** (SHA-256). Eine gestohlene Datenbank ergibt keine funktionierenden Links — und niemand kann einen ausgegebenen Link noch einmal anzeigen, auch der Server nicht |
| Nach dem Einlösen | ein signiertes Plätzchen, dann Umleitung auf eine saubere Adresse. Die Marke steht danach nicht mehr in der Adresszeile, im Verlauf oder auf einem Bildschirmfoto |
| Passwort | `scrypt` mit eigenem Salz, nie im Klartext |
| Raten | nach zehn Fehlversuchen je Aufrufer eine Stunde Ruhe |
| Suchmaschinen | `X-Robots-Tag: noindex, nofollow, noarchive` und `robots.txt` |
| Die abgelegte Seite | eigene CSP ohne Verbindung nach draußen |

Die Marke steht einmal im Traefik-Zugriffsprotokoll — das lässt sich vom
Werkzeug aus nicht verhindern. Die Datei gehört root, und ein Link läuft ab
und ist widerrufbar. Vermerkt im `HINWEIS` der `sicherung.conf`.

### Löschen löscht nicht sofort

Eine gelöschte Seite verschwindet aus der Liste, alle Links darauf gelten
nicht mehr — die **Datei bleibt auf dem Server liegen** (`CLAUDE.md §15`).
Wer sie wirklich los sein will, entfernt sie dort. So ist ein Fehlklick
kein Datenverlust.

### Einrichten

Braucht `PROLO_EINLASS` in der `.env` (derselbe Wert wie in
`traefik/dynamic/einlass.yml`), das Netz `netz-www` und einen Eintrag für
dieses Netz bei Traefik. Ohne den Wert startet das Werkzeug nicht und sagt
im Protokoll, was fehlt.
