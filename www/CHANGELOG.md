# Prolo Freigabe — Änderungen

Geschrieben für den Nutzer, nicht für Entwickler. Neueste Fassung oben.

Fassungsnummern: letzte Stelle = Fehlerbehebung, mittlere = neue Funktion,
erste = etwas Bestehendes bricht.

## Fassung 1.1.0

Die nackte Adresse zeigte bisher immer dasselbe Schild: „Hier liegt
nichts offen herum." Das war richtig, solange es hier nur um
Zugangslinks ging — aber es ließ sich nicht ändern, ohne den Text im
Quelltext zu ändern und neu zu bauen.

Jetzt kannst du **eine der abgelegten Seiten zur Startseite machen**.
In der Verwaltung gibt es dafür die Karte „Die Startseite": Seite
auswählen, Übernehmen. Wer die Adresse ohne Link aufruft, sieht ab dann
diese Seite.

Was dabei wichtig ist, und was das Werkzeug dir auch sagt, bevor du es
tust: **eine Startseite ist wirklich öffentlich.** Jeder sieht sie, ohne
Link und ohne Anmeldung, und Suchmaschinen dürfen sie finden. Alles
andere hier bleibt für sie gesperrt — die freigegebenen Seiten unter
`/s/` und die Links unter `/z/` genauso wie vorher.

Rückgängig ist es jederzeit: in derselben Karte „keine" wählen, dann
steht dort wieder das Schild. Die Seite selbst bleibt dabei liegen. Und
löschst du die Seite, die gerade Startseite ist, fällt die Adresse von
allein auf das Schild zurück — der Löschdialog sagt dir vorher, dass es
diese Seite ist.

Nebenbei zwei Dinge, die schon vorher nicht stimmten: die Knöpfe
„Seite löschen", „Zurückziehen" und „Passwort setzen" waren 36 Pixel
hoch statt der 44, die es am Handy braucht, und die Marke oben links
37 — mit dem Daumen traf man daneben. Alle vier sind jetzt 44.

## Fassung 1.0.1

Die Meldung beim Start ohne Einlassmarke schickte in den nächsten
Fehler: sie nannte einen Unterbefehl `compose`, den `prolo` nie
gekannt hat. Sie nennt jetzt `sudo prolo start www`. Ausgerechnet eine
Fehlermeldung liest man, wenn gerade etwas kaputt ist — dort schadet
ein falscher Befehl am meisten (`N-56`).


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
