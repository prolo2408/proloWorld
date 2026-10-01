# Prolo Freigabe (www) — die Regeln

Diese Datei ist **verbindlich** für jede Sitzung und jeden Agenten, die an
diesem Repository arbeiten.

**Was das ist:** `prolo.me`: HTML-Seiten ablegen und je Empfänger einen widerrufbaren Zugangslink ausgeben. Die Startseite und die Zugangslinks sind mit Absicht öffentlich, nur `/verwaltung` liegt hinter der Anmeldung.

**Wo es läuft:** Dieses Werkzeug ist ein Teil des Prolo-Stapels. Betrieben
wird es von **`prolo2408/proloWorld`** - dort stehen Netz, Route,
Anmeldung, Grenzen, Sicherung und Aktualisierung. Hier steht der Code, und
hier entsteht das Abbild. Das Werkzeug weiß nichts vom Server, und der
Server nichts vom Code: dazwischen steht der **Vertrag** unten.

**Leitsatz:** Funktionierender Code ist der Anfang, nicht das Ziel. Ein
Werkzeug ist fertig, wenn es auch dann noch etwas Vernünftiges tut, wenn
etwas schiefgeht — und wenn man es gerne benutzt.

| Datei | Inhalt |
|---|---|
| **diese hier** | die Regeln: Vertrag, Oberfläche, Robustheit |
| `CHANGELOG.md` | die Bedienung |
| `CHANGELOG.md` | was sich je Fassung geändert hat, für den Nutzer geschrieben |

Die Befundnummern `N-xx` und `B-xx` in Kommentaren und im Changelog
verweisen auf `NEUE-BEFUNDE.md` in `prolo2408/proloWorld` — die Narben
stammen aus der Zeit, als dieses Werkzeug dort lag. Neue Befunde bekommen
hier eine eigene Nummernfolge: `WW-01` aufwärts, in `BEFUNDE.md`.

---

# DER VERTRAG MIT DEM STAPEL

Was `proloWorld` von diesem Werkzeug erwartet. Bricht einer dieser Punkte,
bricht der Betrieb - meist still.

| | |
|---|---|
| **Abbild** | `ghcr.io/prolo2408/www:<fassung>`, gebaut von `.github/workflows/abbild.yml`, sobald ein Tag `v<fassung>` gesetzt wird. Nie `latest`. Eine veröffentlichte Fassung wird nie überschrieben - der Arbeitsablauf bricht ab, wenn es sie schon gibt. |
| **Herstellerdatei** | `docker-compose.yml` hier im Repository. `proloWorld` übernimmt sie **unverändert** (nur ohne `build:`), wie bei jedem Fremdwerkzeug. Darin steht, was das **Werkzeug** braucht: Abbild, Volumes, Umgebung, `read_only`, Rechte. **Nicht** darin: Netz, Traefik-Labels, Speichergrenzen - das ist die Zutat des Betriebs in dessen `docker-compose.override.yml`. |
| **Fassung** | an drei Stellen gleich: `server.py` (`VERSION`), `docker-compose.yml` (`image:`), `CHANGELOG.md` (oberste Überschrift). Mit dem Code zusammen erhöht, nicht danach (§24). |
| **Gesundheit** | `/gesundheit` antwortet `ok`, `/api/version` gibt die Fassung - beide **ohne** Anmeldung und ohne Einlassmarke, und beide geben nichts Schützenswertes aus. `aktualisieren.sh` im Stapel prüft darüber. |
| **Vertrauensgrenze** | Ohne `PROLO_EINLASS` startet das Werkzeug nicht. Jede andere Anfrage ohne passende Kopfzeile `X-Prolo-Einlass` bekommt 401 (§17). In der Herstellerdatei: `PROLO_EINLASS: "${PROLO_EINLASS:?...}"`. |
| **Identität** | nur aus `X-Authentik-*` (§17), nur die **eigenen** Gruppen. Jede Gruppe, die der Code prüft, steht im Label `prolo.gruppen=<gruppe>=<wozu>; ...` der Herstellerdatei - `prolo einrichten` nennt sie daraus, und `grenze-pruefen.sh` im Stapel prüft es. |
| **Daten** | nur in benannten Volumes: `www_daten` (`/daten`, SQLite) und `www_seiten` (`/seiten`). SQLite im WAL-Modus; der Stapel sichert sie mit `sqlite3.backup()` - dafür muss `python3` im Abbild bleiben. |
| **Migrationen** | Hinweis, Kopie, Transaktion (§24a). Das Abbild startet eine neue Fassung auf den alten Daten. |

Was davon ausgeführt geprüft wird, steht in `tests/`. Eine Änderung am
Vertrag ist eine Änderung an **beiden** Repositorys - und gehört in beiden
Changelogs erwähnt.

---

# TEIL 0 — WIE HIER GEARBEITET WIRD

- **Ein Befund, ein Arbeitsschritt, ein Commit.** Die Commit-Nachricht
  beginnt mit der Nummer des Befunds (`WW-01: …`).
- **Prüfschritte werden ausgeführt, nicht überlegt** (§14). Im Commit steht,
  was ausgeführt wurde und was dabei herauskam — **mit Zahlen**.
- **Erwartungswerte von Hand** (§13). Nie die Ausgabe des Codes als
  Erwartung übernehmen.
- **Tests müssen Zähne haben** (§13a): jede neue Prüflinie wird mit einer
  Mutationsprobe belegt. Eine Mutation, die unentdeckt bleibt, ist eine
  Testlücke und wird geschlossen.
- **Der Rückweg einer Probe darf nicht die eigene Arbeit sein.** Mutationen
  werden in einer Kopie im Kratzblock eingebaut, nie über `git checkout`
  zurückgerollt.
- **Nichts still nebenbei ändern.** Ein Problem, das beim Arbeiten auffällt,
  wird ein **neuer Befund** in `BEFUNDE.md` und bekommt seinen eigenen
  Schritt.
- Eine Oberfläche ist erst geprüft, wenn sie im **Browser geladen** wurde.
- **Eine Prüfung wird nicht durch eine Pipe gelesen.** `./tests/alle.sh |
  tail -2 && commit` liefert den Rückgabewert von `tail`.
- **Eine Meldung ist kein Beweis.** Geprüft wird die Wirkung, nicht der
  Text einer Ankündigung.

Python-Standardbibliothek, SQLite, **kein Fremdpaket**.

Tests: `./tests/alle.sh` - Python, mit `tests/gegenprobe.py` fuer §13a.

## Zwei Router auf einem Namen

Dieses Werkzeug ist teils öffentlich. Der Betrieb legt dafür zwei Router an
(in `proloWorld`, `www/docker-compose.override.yml`): den öffentlichen und
`/verwaltung` mit Anmeldung, der mit der **höheren** Priorität. Darum prüft
das Werkzeug die Gruppe **zusätzlich selbst** - eine Kopfzeile allein ist auf
einem Host mit öffentlichem Router kein Nachweis (§19 im Stapel).

---

# TEIL I — OBERFLÄCHE

## 1. Grundhaltung

- Ruhig, sachlich, datennah. Keine Verläufe, keine Emojis, keine dekorativen
  Illustrationen.
- Eine Akzentfarbe (Blau), sonst Graustufen. Farbe bedeutet immer etwas:
  aktiv, positiv, Warnung, Kategorie.
- Viel Weißraum, klare Kanten, flache Flächen. Schatten nur für das Fenster
  selbst, nicht für Karten.
- Dunkelmodus ist der Standard, Hellmodus muss gleichwertig funktionieren.
- Zahlen sind der Inhalt: groß, in Sora, mit Monospace für Rohwerte.

**Lesbarkeit schlägt Palette.** Die Tokens sind der Normalfall, nicht der
Selbstzweck. Ist eine Kombination schlecht lesbar, wird sie geändert — nicht
beibehalten, weil sie „regelkonform" ist. Reines Schwarz auf reinem Weiß ist
hart und ermüdet; deshalb liegen die Tokens bewusst nicht bei 0 und 1. Nie
`#000` oder `#fff` direkt setzen — Text auf `--accent` läuft über
`--on-accent`.

Wer eine neue Farbe braucht: **neues Token mit klarer Bedeutung ergänzen**,
keinen Einzelwert in die Komponente schreiben — und das Token **hier**
nachtragen, sonst weiß das nächste Werkzeug nichts davon.

## 2. Farbtoken

Nie Farbwerte direkt in Komponenten. Definition einmal pro Seite,
Umschaltung über `data-theme` auf `<body>`.

```css
:root{
  --bg:oklch(0.96 0.004 250);        /* Seitenhintergrund             */
  --app:oklch(0.985 0.002 250);      /* Fensterfläche                 */
  --surface:#fff;                    /* Karte, Tabelle, Panel         */
  --chrome:oklch(0.995 0.001 250);   /* Sidebar, Header, Tabbar       */
  --line:oklch(0.92 0.004 250);      /* Rahmen, Trennlinien           */
  --line-soft:oklch(0.96 0.002 250); /* Zeilentrenner in Listen       */
  --hover:oklch(0.96 0.003 250);     /* Hover-Fläche                  */

  --ink:oklch(0.2 0.01 250);         /* Überschriften, Zahlen         */
  --ink-2:oklch(0.3 0.01 250);       /* Fließtext, Tabellenzellen     */
  --ink-3:oklch(0.52 0.01 250);      /* Labels, Sekundärtext          */

  --accent:oklch(0.52 0.17 262);     /* Primäraktion, aktiver Zustand */
  --accent-hover:oklch(0.45 0.17 262);
  --accent-soft:oklch(0.94 0.02 262);/* Badge-, Icon-Hintergrund      */
  --accent-ink:oklch(0.38 0.13 262); /* Text auf accent-soft          */
  --on-accent:oklch(0.99 0.002 250); /* Text AUF --accent             */
  --bar:oklch(0.86 0.03 262);        /* zweite Datenreihe im Chart    */

  --good:oklch(0.45 0.14 158);       /* Ersparnis, günstigster Preis  */
  --good-soft:oklch(0.97 0.01 158);
  --warm-soft:oklch(0.94 0.01 60);   /* Kategorie Verbrenner/Tanken   */
  --warm-ink:oklch(0.45 0.08 60);
  --danger:oklch(0.52 0.18 25);      /* Löschen, Zurücksetzen         */
  --overlay:oklch(0.28 0.02 258);    /* Abdunklung hinter Dialogen    */

  --feature:oklch(0.34 0.12 262);    /* eine farbige Hero-Fläche      */
  --feature-ink:oklch(0.99 0.002 250);
  --feature-ink-2:oklch(0.86 0.03 262);
  --feature-line:oklch(0.46 0.11 262);
  --feature-good:oklch(0.88 0.16 158);

  --track:oklch(0.94 0.004 250);     /* Fortschritts-, Segmentspur    */
  --shadow:0 24px 60px -20px oklch(0.4 0.03 250 / 0.22);
}

body[data-theme="dark"]{
  --bg:oklch(0.16 0.012 258); --app:oklch(0.2 0.012 258);
  --surface:oklch(0.235 0.013 258); --chrome:oklch(0.205 0.012 258);
  --line:oklch(0.31 0.014 258); --line-soft:oklch(0.27 0.012 258); --hover:oklch(0.27 0.013 258);
  --ink:oklch(0.96 0.004 250); --ink-2:oklch(0.87 0.006 250); --ink-3:oklch(0.69 0.01 250);
  --accent:oklch(0.62 0.16 262); --accent-hover:oklch(0.69 0.16 262);
  --accent-soft:oklch(0.33 0.06 262); --accent-ink:oklch(0.85 0.09 262); --bar:oklch(0.38 0.06 262);
  --on-accent:oklch(0.16 0.012 258);
  --good:oklch(0.8 0.14 158); --good-soft:oklch(0.29 0.05 158);
  --warm-soft:oklch(0.33 0.05 60); --warm-ink:oklch(0.86 0.08 60);
  --danger:oklch(0.7 0.16 25); --overlay:oklch(0.2 0.012 258);
  --feature:oklch(0.31 0.07 262); --feature-ink:oklch(0.97 0.004 250); --feature-ink-2:oklch(0.8 0.02 250);
  --feature-line:oklch(0.42 0.05 262); --feature-good:oklch(0.85 0.15 158);
  --track:oklch(0.3 0.014 258);
  --shadow:0 24px 60px -20px oklch(0.05 0 0 / 0.6);
}
```

### Einsatzregeln

| Token | wofür | nicht |
|---|---|---|
| `--accent` | genau **eine** Primäraktion pro Screen, aktiver Navigationspunkt, wichtigste Datenreihe | große Flächen, Fließtext |
| `--accent-soft` | Badges, Icon-Kacheln, aktive Nav-Zeile | Karten |
| `--good` | Ersparnis, günstigster Preis, negative Kostenänderung | „erledigt"-Meldungen |
| `--warm-soft/ink` | Kategorie Verbrenner/Tanken, Hinweise | zerstörende Aktionen |
| `--danger` | Löschen, Zurücksetzen | Warnungen — eine Warnung ist kein Verlust |
| `--feature` | höchstens **eine** farbige Fläche pro Screen (Hero-Kennzahl) | mehrere Panels gleichzeitig |

Nie eine schwarze Karte in eine sonst helle Ansicht setzen. Soll eine Fläche
hervorstechen, ist das `--feature` — und davon gibt es genau eine.

**Farbe darf nie die einzige Information sein.** Rot allein reicht nicht, es
braucht Text oder ein Symbol dazu — sonst ist es für farbfehlsichtige Nutzer
unlesbar.

**Kontrast-Ausnahme:** Erreicht eine Kombination die Mindestwerte aus §8
nicht, wird das nächsthellere bzw. -dunklere Token genommen. Häufig zu
schwach: `--ink-3` auf `--accent-soft`, Monospace-Kleintext auf `--feature`.
Dort `--ink-2` bzw. `--feature-ink`. Gibt es kein passendes Token, wird eines
ergänzt — und oben eingetragen.

## 3. Typografie

- **Sora** 600: Überschriften, Kennzahlen, Beträge, Kartentitel.
- **Instrument Sans** 400/500/600: alles andere.
- **JetBrains Mono** 400/500: Rohwerte, Mengen, Datum, Einheiten,
  Tabellen-Kopfzeilen (10–11 px, `letter-spacing:0.06em`, Versalien).

Größen: Seitentitel 20–22, Kennzahl groß 30–40, Kartentitel 15, Fließtext
13–14, Sekundärtext 12, Label 10–11. Auf Überschriften und Kennzahlen
`letter-spacing:-0.02em`. Handy: nichts unter 12 px, Touchziele ≥ 44 px.

## 4. Form und Abstand

- Radien: Fenster 18, Handyrahmen 42, Karte Desktop 14, Karte Handy 16–20,
  Steuerelement 10, Badge 5.
- Abstände: 4er-Raster. Karteninhalt 18–20, zwischen Karten 14–20, Seitenrand
  Desktop 32, Handy 20.
- Karten: `background:var(--surface); border:1px solid var(--line)` — **kein
  Schatten**. Schatten nur am Gesamtfenster (`--shadow`).
- Gruppen immer mit `display:flex/grid` + `gap`, nie mit Rand-Abständen
  einzelner Elemente.
- Kinder von Raster und Flexkästen brauchen `min-width:0`, sonst wachsen sie
  auf ihre Inhaltsbreite und sprengen die Spalte.

## 5. Bausteine

**Werkzeug-Marke (Pflicht, oben links).** Kachel 30 px, Radius 8, `--accent`
als Fläche, **ein** Großbuchstabe in `--on-accent`. Daneben der Name (Sora
14) und darunter eine kurze Einordnung in Monospace-Versalien. Die Unterzeile
beschreibt **das Werkzeug**, nicht den Zustand: „Fahrtenbuch" ist richtig,
„1 Seite" gehört in den Inhalt. Keine Emojis, keine Icon-Bibliothek. Wer mehr
als einen Buchstaben braucht, braucht ein einfacheres Logo. Ein Klick führt
immer zur Startseite.

**Karte** — `padding:18px; border-radius:14px; background:var(--surface);
border:1px solid var(--line)`; Titel Sora 15 `--ink`, darunter eine
Kontextzeile 12 px `--ink-3`.

**Kennzahl** — Label 12 px `--ink-3`, Wert Sora 30 px `--ink`, Einheit 14 px
`--ink-3` daneben, darunter eine Monospace-Zeile mit Vergleich oder Herkunft.

**Primärbutton** — Höhe 38 (Desktop) / 52 (Handy), Radius 10/16,
`--accent`, Text `--on-accent`, 600, Hover `--accent-hover`. **Einer pro
Screen**, alles andere ist Text oder Rahmenbutton.

**Segment-Umschalter** — Spur `--track`, Radius 10, aktives Segment
`--surface` + feiner Schatten, inaktiv `--ink-3`.

**Badge** — `padding:2px 7px; border-radius:5px`, 11 px, 600.

**Tabelle** — Monospace-Kopfzeile in Versalien, Zeilen 13 px `--ink-2`,
Trenner `--line-soft`, Zahlen rechtsbündig in Monospace, Summen 500, Hover
`--hover`. Auf hunderte Zeilen ausgelegt: eigener Scrollkasten, Kopf bleibt
stehen, Zeilen so hoch wie nötig.

**Liste auf dem Handy** — Icon-Kachel 38 px, Titel 14 px 600, Metazeile 12 px
`--ink-3`, Betrag rechts in Sora 15 px.

**Diagramm** — flache Balken, Radius 5–6, aktueller Zeitraum in `--accent`,
Vergangenheit in `--bar`. Achsen weglassen, Werte direkt über die Balken.
Keine Gitternetzlinien, keine Chart-Bibliothek-Optik.

**Scrollbereiche** — Scrollbalken ausblenden: `scrollbar-width:none` plus
`[data-noscroll]::-webkit-scrollbar{width:0;height:0}`.

**Eine Oberfläche mit fester Hülle** (wie das Wiki) ist ein **Rahmen, kein
Schriftstück**: `html, body { height:100%; overflow:hidden }`, die Hülle
`position:fixed; inset:0`, und gescrollt wird **innen**. Sonst genügt
irgendetwas, das dem Körper Höhe gibt, und die ganze Oberfläche lässt sich
aus dem Fenster schieben (`N-34`). Aus demselben Grund **kein
`scrollIntoView`** in einer solchen Hülle: es scrollt jeden scrollbaren
Vorfahren, auch den Körper (`N-36`).

## 6. Aufbau der Screens

**Desktop (1440 × 900).** Sidebar 248 px (`--chrome`): oben die Marke,
Navigation mit 44-px-Zeilen und 4-px-Aktivstrich, unten nur „Einstellungen".
Header 76 px: links Titel + Kontextzeile, rechts Kontext-Auswahl,
Zeitraum-Segment, Primärbutton, ganz rechts der Anzeigename als Verweis auf
die Einstellungen. Inhalt: KPI-Reihe, darunter Raster `1.55fr / 1fr`.

**Inhaltsbreite begrenzen:** `max-width:1280px; margin:0 auto`. Ohne das zieht
sich auf breiten Schirmen alles auseinander. Die Sidebar bleibt außerhalb.

**Keine halbleeren Reihen.** Hat eine Rasterzeile nur ein oder zwei Elemente,
wird die Spaltenzahl reduziert, statt die Lücke stehen zu lassen.

**Handy (390 × 844).** Kopf mit verkleinerter Marke + Titel + Kontextchip,
Inhalt (Hero-Kennzahl in `--feature`, Diagramm, Liste), Primärbutton über der
Tabbar, Tabbar mit 4 Einträgen und 3-px-Aktivstrich; der letzte Eintrag ist
„Einstellungen". Kontextobjekte (Fahrzeug, Konto) gehören in den Kopf, nicht
in die Sidebar-Fußzeile.

## 6a. Einstellungsseite (Pflicht je Werkzeug)

Unter `/einstellungen`, der einzige Ort für Darstellung, Konto und eigene
Optionen — der Header bleibt dadurch frei für den Inhalt. Immer in dieser
Reihenfolge:

1. **Darstellung** — Segment `System` / `Hell` / `Dunkel`, `System` ist
   Vorgabe und folgt `prefers-color-scheme`. Die Wahl wird **pro Nutzer in
   der Datenbank** gespeichert, nicht nur im Browser — sonst ist sie auf dem
   Handy wieder weg. Umschaltung über `document.body.dataset.theme`, ohne
   Neuladen.
2. **Werkzeug-Einstellungen** — alles Fachliche, als klar beschriftete
   Schalter mit **einer Zeile Erklärung** darunter. Ein Schalter ohne
   Erklärung ist ein Rätsel.
3. **Freigaben** — nur wenn das Werkzeug Daten teilen kann: „Meine
   Freigaben" und „Für mich freigegeben".
4. **Konto** — Anzeigename und E-Mail **nur zur Anzeige**, mit dem Hinweis,
   dass sie zentral verwaltet werden. Knopf **„Abmelden / neu laden"** mit
   der Erklärung darunter, Ziel `/outpost.goauthentik.io/sign_out`. Die
   doppelte Beschriftung ist Absicht: es ist eine Weiterleitung, die Seite
   lädt neu.

Im Header steht nur der Anzeigename, verlinkt hierher. Kein
Theme-Umschalter und kein Abmelden-Knopf in der Kopfzeile.

## 7. Sprache

Deutsch, sachlich, keine Werbesprache. Substantive statt Aufforderungen in
Labels („Vorgang erfassen", „Kosten je Monat").

Zahlen deutsch: Dezimalkomma, Tausenderpunkt, Einheit mit schmalem Abstand
(`8,72 €`, `17,8 kWh/100 km`, `1.284 km`), Datum kurz `09.09.`.

**Fehlermeldungen sagen, was zu tun ist**, nicht nur was kaputt ist. Keine
technischen Brocken: „Speichern hat nicht geklappt — Verbindung zum Server
unterbrochen" statt „HTTP 500". Und sie führen **an die Stelle**: eine Zeile
„eine Sache fehlt noch" ohne Weg dorthin ist keine Meldung, sondern ein
Rätsel (`N-35`).

**Eine Meldung, die einen Weg nennt, nennt auch das Hindernis darauf**
(`N-60`). „3 Commit(s) hinter origin/main" war wahr, und „git pull"
daneben war richtig — zusammen führten sie in eine Mauer, von der das
Werkzeug bereits wusste. Eine Teilwahrheit, die zur Tat auffordert, ist
eine Falle. Und führt der genannte Weg über etwas Zerstörendes (`git
checkout --`, ein Überschreiben), steht die **Kopie davor**, nicht
daneben.

**Und sie verschweigt nicht die Ursache, die sie in der Hand hatte**
(`N-64`). Ein `2>/dev/null` über dem fehlgeschlagenen Aufruf macht aus
„docker sagt: `failed to read bordbuch/.env: key cannot contain a space`"
ein „liefert keine lesbare Konfiguration" — und aus einer Diagnose die
Frage „wo ist das Bordbuch?". Wer zum Nachsehen auffordert, nennt
**genau den Aufruf**, den das Werkzeug gemacht hat, nicht einen
ähnlichen. Und ein Rat, der nur manchmal passt (*„dann mit sudo"*), kommt
nur dann, wenn die Meldung ihn hergibt — sonst ist er nach dem dritten Mal
Tapete.

**Und sie nennt den Befehl, nicht die Aufgabe** (`N-67`). „Anlegen aus
`.env.beispiel`" schickt zum Abtippen, obwohl `prolo einrichten` genau das
idempotent tut. Gibt es einen Befehl, der die Sache erledigt, steht er in
der Meldung — samt der Bemerkung, dass er gefahrlos zu wiederholen ist,
sonst traut ihn sich niemand auf einem laufenden Stack.

**Und sie verbindet, was sie beides gemessen hat** (`N-69`). „zeigt auf
217.160.0.1 (FREMD)" und „keine Antwort auf 443" standen als zwei Zellen
derselben Zeile, jede für sich im Fußtext erklärt — das Wort **weil**
dazwischen fehlte, und damit die ganze Diagnose. Wer Ursache und Wirkung
beide in der Hand hat, sagt auch, dass die eine die andere ist. Und wo
nichts folgt, steht nichts: eine Folgerung, die immer kommt, wird
überlesen, und dieselben zehn Zeilen je Name sind nach dem zweiten Mal
Tapete. Die Erklärung kommt **einmal je Ursache**, der Satz je Name.

## 8. Umsetzungsregeln

- Kein Farbwert ohne Token.
- Themenwechsel über `document.body.dataset.theme`; Standard `dark`.
- **Kontrast: Text mindestens 4.5:1, große Überschriften 3:1.**
- Fluide Layouts, außer bei bewusst festen Formaten.

### 8.1. Inline-Styles: wann ja, wann nein

**Entwürfe und Mockups:** alles inline, keine Klassen. Ausnahme ist der
Tokenblock.

**Echte Anwendungen:** Grundstil inline, aber Zustände und Umgebungsabfragen
gehören in einen CSS-Block — inline lassen sich `:focus-visible`, `:hover`,
`@media` und `prefers-reduced-motion` nicht ausdrücken. Der Pflichtblock:

```css
button:focus-visible, a:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }
```

Und eine Regel, die **vor** allen `display`-Regeln stehen muss, sonst bleibt
ein verstecktes Element sichtbar:

```css
[hidden]{display:none!important}
```

## 9. Bedienbarkeit (nicht verhandelbar)

- Jedes bedienbare Element ist mit der Tastatur erreichbar und zeigt einen
  sichtbaren Fokusrahmen.
- Wer Bewegungsreduzierung eingestellt hat, bekommt keine Animationen.
- **Klickflächen mindestens 44 × 44 px** — die Werkzeuge werden am Handy
  benutzt, mit Daumen und teils mit Handschuhen.
- Beschriftungen gehören zum Feld (`<label for>`), nicht daneben. `label for`
  auf einen `<button>` zählt **nicht** — der braucht `aria-label`.
- Kein reines Icon ohne Text oder `aria-label`.
- Layout funktioniert **ab 360 px** ohne seitliches Scrollen.
- `env(safe-area-inset-bottom)` berücksichtigen.
- Zahlenfelder mit passender Tastatur: `inputmode="decimal"` für Beträge,
  `inputmode="numeric"` für Kilometerstände.
- Ein Knopf, der nichts tut, ist schlimmer als kein Knopf. Was aussieht wie
  ein Knopf, **ist** einer — und was nichts zu tun hat, ist gesperrt.

## 10. Rückmeldung an den Nutzer

- Jede Aktion bestätigt sich sichtbar. Speichern ohne Rückmeldung fühlt sich
  kaputt an, auch wenn es funktioniert hat.
- Kurze Bestätigungen als Einblendung, Fehler bleiben stehen bis man sie
  wegklickt.
- Ladezustände ab etwa 300 ms anzeigen.
- Knöpfe während einer laufenden Aktion sperren, damit nichts doppelt
  abgeschickt wird.

---

---

# TEIL II — ROBUSTHEIT

## 11. Eingaben sind grundsätzlich falsch

Jede Eingabe von außen — Formular, Datei, Schnittstelle — wird geprüft,
bevor sie irgendwo landet: Pflichtfelder vorhanden? Zahlen im plausiblen
Bereich (ein Kilometerstand von 9 Millionen ist ein Tippfehler)? Datum
lesbar und nicht sinnlos in der Zukunft? Text auf sinnvolle Länge begrenzt?

**Aus `X-Forwarded-For` zählt der LETZTE Eintrag, nie der erste.** Ein Proxy
**hängt** seinen Eintrag hinten an; was davor steht, hat der Aufrufer
mitgeschickt und ist frei erfunden. Wer den ersten nimmt, baut eine Sperre,
die sich mit einer erfundenen Adresse je Versuch unterlaufen lässt (`N-48`).

**Keine stillen Vorgabewerte.** Fehlt ein Wert, wird das gemeldet — nicht
durch eine Null ersetzt. Eine Null in der Verbrauchsrechnung ist schlimmer
als eine Fehlermeldung, weil sie falsche Ergebnisse erzeugt, die niemandem
auffallen.

## 12. Fehler dürfen nichts kaputt machen

- Eine fehlgeschlagene Aktion hinterlässt **keinen halben Datensatz**. Bei
  mehreren zusammengehörenden Schreibvorgängen: Transaktion.
- **Mehrere Dateien sind auch eine Transaktion** (`N-52`). Gehört ein Wert an
  vier Stellen, wird **vor der ersten** geprüft, ob alle vier gehen — sonst
  schreibt man drei und bricht bei der vierten ab. „Erst danebenschreiben,
  dann umbenennen" rettet die **einzelne** Datei, nicht die Menge.
- Import von 200 Zeilen, Zeile 137 kaputt: ganz übernehmen oder gar nicht —
  und im Klartext sagen, welche Zeile das Problem war.
- Netzwerkfehler und Zeitüberschreitungen abfangen. Ein hängender Aufruf darf
  die Oberfläche nicht einfrieren.
- **Nach dem Commit wird nicht mehr geworfen.** Was danach schiefgeht
  (Aufräumen, Verschieben), ist ein Hinweis, kein Fehler — sonst meldet der
  Dienst einen Fehlschlag für etwas, das erledigt ist (`N-30`).

## 13. Rechnen

- Geldbeträge niemals als Fließkommazahl.
- Jede Größe mit Einheit im Namen: `menge_l`, `energie_kwh`, `betrag_ct`.
- Keine Steuersätze, Preise oder Wirkungsgrade fest im Code — die gehören in
  Konfiguration mit Gültigkeitsdatum.
- Rechnende Funktionen brauchen Tests mit **von Hand gerechneten**
  Erwartungswerten. Nicht die Ausgabe des Codes als Erwartung übernehmen —
  das testet nur, dass sich nichts ändert, nicht dass es stimmt.

Pflichtfälle je Berechnung: ein normaler Fall (handgerechnet), der Grenzfall
(null, negativ, sehr groß), der Fall mit fehlenden Daten.

### 13a. Die Tests müssen Zähne haben

Handgerechnete Erwartungswerte sind notwendig, aber nicht genug: ein Test
kann grün sein, weil er nichts prüft.

**Darum wird zu jeder Testsuite eine Gegenprobe geschrieben**, die absichtlich
Fehler in den Code einbaut und verlangt, dass **jeder** von einem Test
gefunden wird. Findet ihn keiner, ist der Test Beschäftigung und wird
ergänzt. Vorbilder: `tests/gegenprobe.sh` im Bordbuch, `tests/gegenprobe.py`
in www, die `werkzeuge/*-pruefen.sh` in proloWorld.

**Ein Erwartungswert, der bei zwei verschiedenen Verfahren gleich
herauskommt, prüft das Verfahren nicht.** Die Rundungstests benutzten
`8,995 €` — kaufmännisch gerundet 900 Cent, zur geraden Zahl gerundet
ebenfalls 900. Der Test war grün und hätte beide Arten durchgelassen, also
genau den Fehler nicht gefunden, um dessentwillen er geschrieben wurde.

Zwei weitere Fallen, beide schon zugeschnappt:

- **Ein alter `__pycache__` lässt eine Mutationsprobe still grün bleiben.**
  Vor jeder Probe den Zwischenspeicher leeren.
- **Eine Prüflinie, die ein Wort sucht, fällt über den eigenen Kommentar.**
  Gesucht wird der Aufruf, nicht die Zeichenfolge (`N-36`).

## 14. Was durchprobiert sein muss

Ein Werkzeug gilt erst als fertig, wenn diese Fälle **tatsächlich ausprobiert**
wurden — nicht nur gedanklich. Ein Bildschirmfoto der fertigen Ansicht ist
Teil der Abnahme, nicht die Behauptung, es sehe gut aus.

### 14a. Oberfläche — gründlich durchsehen

Jede Ansicht einzeln, in **beiden Themen**, bei **drei Breiten** (360, 768,
1920):

1. **Löcher im Layout** — bleibt eine große leere Fläche, weil eine
   Rasterzeile nicht gefüllt ist?
2. **Auseinandergezogene Inhalte** — läuft eine Kachel mit wenig Inhalt über
   die volle Breite?
3. **Überlauf** — langer Text, langer Name, große Zahl (`1.284.500,55 €`):
   bricht etwas aus der Karte aus?
4. **Leere Zustände** — jede Liste, Tabelle, jedes Diagramm ohne Daten. Steht
   dort ein hilfreicher Satz oder nur Leere?
5. **Ausrichtung** — Zahlen rechtsbündig und in Monospace? Fluchten
   Kartenkanten?
6. **Kontrast** — jede Text-auf-Fläche-Kombination gegen §8, besonders
   Kleintext auf `--accent-soft` und `--feature`.
7. **Doppelte Scrollbalken**, abgeschnittene Ränder, Elemente unter der
   Gestenleiste.
8. **Beschriftungen** — einheitliche Groß- und Kleinschreibung, keine
   Abkürzung, die nur der Entwickler versteht.
9. **Zoom 200 %** — bleibt alles bedienbar?

**Und der Prüfer wird gegengeprobt.** „Nichts gefunden" heißt nichts,
solange nicht gezeigt ist, dass der Prüfer etwas finden *kann*. Drei
Messwerkzeuge haben schon gelogen: ein Kontrastprüfer, der `oklch` als RGB
las; einer, der Behälter statt Textknoten maß; ein Überlaufprüfer, der Kinder
von Scrollbereichen zählte. Und **hinter einem CSS-Übergang kann ein
kopfloser Browser mit virtueller Zeit nichts messen** — den Übergang vorher
abschalten und den Endzustand prüfen.

### 14b. Verhalten

10. Leerer Zustand: erste Anmeldung, keine Daten.
11. Ein Datensatz — und mehrere hundert. Wird es langsam?
12. Ganz falsche Eingabe: Text im Zahlenfeld, negative Werte, Datum 1900, ein
    Titel aus 400 Zeichen, `</script>` mitten im Text.
13. Doppelt schnell hintereinander auf „Speichern" geklickt.
14. Seite mitten im Vorgang neu geladen.
15. Theme umschalten — bleibt die Wahl nach dem Neuladen erhalten?
16. Abmelden und als anderer Nutzer anmelden — sieht man wirklich nur die
    eigenen Daten?
17. Mit der Tastatur durch die ganze Seite, ohne Maus.

## 15. Datenverlust ist die einzige echte Katastrophe

- Löschen fragt nach — bei mehreren Datensätzen mit Nennung der Anzahl.
- Wo möglich: erst als gelöscht markieren, später endgültig entfernen.
- **Vor Migrationen, die Daten verändern**, gilt der Dreischritt aus §24a:
  Hinweis **vor** der ersten Änderung, Kopie des bisherigen Stands,
  Transaktion. Eine bestehende Kopie wird nicht überschrieben — sonst
  ersetzt ein zweiter, ebenfalls gescheiterter Lauf den einzigen brauchbaren
  Stand.
- Ein Import kann rückgängig gemacht werden: jeder Datensatz bekommt das Feld
  `quelle` mit Importlauf und Zeilennummer.
- **Ein Werkzeug, das eigene Arbeit wegräumen könnte, tut nichts und sagt
  warum.** Vorspulen nur bei sauberem Arbeitsstand, kein Zusammenführen ohne
  Menschen (`N-38`).

---

---

# TEIL III — WAS AUS DEM BETRIEB HIER GILT

Der Betrieb selbst (Ordner, Netze, Sicherung, Aktualisierung, Geheimnisse)
ist Sache von `proloWorld` - dort stehen §16, §19, §23 und §25. Hier gilt,
was der Code einhalten muss.

## 17. Anmeldung: niemals selbst bauen

**Kein Werkzeug mit eigenem Code bringt eine eigene Anmeldung mit.** Kein
Login-Formular, keine Registrierung, keine Passwortspeicherung, kein
Zurücksetzen per Mail. Die Identität kommt als HTTP-Kopf von Traefik:

| Kopf | Inhalt |
|---|---|
| `X-Authentik-Username` | Anmeldename, **der Schlüssel** für eigene Datensätze |
| `X-Authentik-Email` | E-Mail |
| `X-Authentik-Name` | Anzeigename |
| `X-Authentik-Groups` | Gruppen, kommagetrennt |

- Fehlt `X-Authentik-Username`, wird die Anfrage **abgewiesen**. Kein
  Vorgabenutzer, kein Gastzugang, kein stilles Weiterlaufen.
- **Eine Kopfzeile ist nur so viel wert wie die Gewissheit, dass sie von
  Traefik kommt** (`N-44`). Diese Gewissheit gibt es nicht von selbst: im
  Docker-Netz erreicht jeder Container Port 8080 eines anderen direkt, ohne
  Traefik und ohne Anmeldung. Gemessen: eine Anfrage mit
  `X-Authentik-Groups: wiki-admin` bekam die Verwaltungsdaten.

  Darum zwei Schichten, beide Pflicht:

  1. **Traefik löscht am Eingang** jede mitgeschickte `X-Authentik-*` und
     setzt `X-Prolo-Einlass` selbst — am **Eingang**, nicht je Router, sonst
     fällt genau der Router durch, den jemand ohne Anmeldung anlegt.
  2. **Jedes Werkzeug prüft `X-Prolo-Einlass`, bevor es nach der Identität
     fragt.** Fehlt der Wert in seiner `.env`, **startet es nicht** — eine
     Sicherung, deren Ausfall niemandem auffällt, ist keine.

  Frei bleiben nur Pfade ohne Schützenswertes, die absichtlich am Zugang
  vorbei aufgerufen werden: die Gesundheitsprüfung und die Fassung (§19).
  `PRUEF_URL` in der `aktualisierung.conf` muss auf einem davon liegen.
  `werkzeuge/grenze-pruefen.sh` in proloWorld hält die fünf Stellen zusammen.
- Unbekannter Anmeldename legt automatisch einen Nutzer-Datensatz an.
- Wiedererkennung über den **Anmeldenamen**, nicht über die E-Mail — die
  ändert sich.
- Gruppen dürfen für werkzeug-interne Rollen ausgewertet werden. Ein Werkzeug
  wertet nur seine **eigenen** Gruppen aus (das Wiki: alles, was mit `wiki`
  anfängt) und verwirft den Rest an **einer** Stelle, nicht an sieben.

## 18. Datentrennung

Sobald ein Werkzeug Daten pro Person hält:

- Jeder fachliche Datensatz bekommt `nutzer_id`.
- Abfragen filtern standardmäßig auf den angemeldeten Nutzer.
- Freigaben an andere laufen über eine eigene Tabelle im Werkzeug, nicht über
  Authentik.
- Es gibt **keine** Oberfläche, in der ein Nutzer andere Nutzer anlegt,
  löscht oder deren Stammdaten bearbeitet. Das macht Authentik.

## 20. Benennung

- Fachbegriffe deutsch (`tankvorgang`, `ladevorgang`, `fahrzeug`), technische
  Begriffe in der Konvention der jeweiligen Sprache.
- **Keine Umlaute in Bezeichnern:** `blockiergebuehr`, nicht
  `blockiergebühr`.
- Tabellen und Spalten mit fachlicher Bedeutung: **deutsch**.
- **Jede Größe mit Einheit im Namen:** `menge_l`, `energie_kwh`, `betrag_ct`,
  `stand_km`, `dauer_s`.
- Schlüssel einheitlich `<tabelle>_id`.
- **`nutzer_id` bedeutet überall dasselbe:** der Anmeldename als `TEXT`. Das
  Wiki hält es so; im Bordbuch ist es noch ein `INTEGER` auf `users(id)` und
  wird bei der nächsten ohnehin nötigen Migration mitgezogen.
- Die JSON-Schnittstelle folgt dem Schema, keine eigene Schreibweise.

Neue Felder folgen ab sofort der Konvention; bestehende werden bei der
nächsten Migration mitgezogen — nicht in einem Zug.

## 21. Schützenswerte Daten

Was das System nie verlässt: `.env`, Schlüssel, Zertifikate, Datenbanken,
Sicherungen. Die `.gitignore` dieses Repositorys fängt `.env`, `.env.*`
(mit der Ausnahme `!.env.beispiel`), `*.key`, `*.pem`, `*.db*`,
`*.sqlite`, `*.sql`, `*.dump` und die Datenordner. Jede Vorlage, die zum
Aufsetzen gebraucht wird, muss in `git ls-files` auftauchen.

**Vor jedem Push:** `git status` und `git diff --cached` wirklich lesen.

## 22. Protokolle und Weitergabe

- Keine Geheimnisse und keine vollständigen Kopfzeilen ins Protokoll;
  `X-Authentik-Jwt` und `Cookie` weglassen oder kürzen.
- Fehlermeldungen an den Nutzer enthalten keine internen Pfade und keine
  Datenbankfehler im Original.
- **Nichts Schützenswertes in einen Chat** — auch nicht „nur zum Nachsehen".
  Weitergeben darf man den **Namen** einer Variable, den **Ort** einer Datei,
  die **Meldung** ohne den Wert. Für die Fehlersuche reicht das fast immer.

## 24. Fassung und Veröffentlichung

- **Erst die Fassungsnummer, dann der Tag.** Sie gehört **mit dem
  Quellcode zusammen** erhöht, nicht danach: sie ist das Etikett des
  Abbilds, das aus genau diesem Stand gebaut wird.
- Veröffentlicht wird mit `git tag v<fassung> && git push --tags`. Der
  Arbeitsablauf prüft, dass Tag, `server.py`, `docker-compose.yml` und
  `CHANGELOG.md` dieselbe Fassung nennen, baut, prüft und schiebt das
  Abbild nach `ghcr.io`.
- Auf dem Server: in `proloWorld` die Fassung in
  `www/docker-compose.yml` hochsetzen, dann `sudo prolo aktualisieren
  www` - das sichert vorher und rollt bei Fehlschlag zurück.
- **Ein Aufruf, der nur nach der Fassung fragt, migriert nicht.**
  `--version` bleibt ohne Nebenwirkung.

### 24a. Datenbank-Migrationen: Hinweis, Kopie, Transaktion

Pflicht, in dieser Reihenfolge:

1. **Hinweis auf die Sicherung — bevor etwas passiert.** Das Werkzeug
   schreibt beim Start, welche Änderungen anstehen, dass sie nicht umkehrbar
   sind und wie man abbricht. Ein Hinweis nach der ersten Änderung ist
   wertlos.
2. **Kopie der bisherigen Datei** als `<datenbank>.vor-stand-<n>`. Sie bleibt
   liegen und ist das Einzige, was nach einer schiefgegangenen Migration noch
   hilft.
3. **Alle Änderungen in einer Transaktion.** Entweder vollständig alt oder
   vollständig neu — nichts dazwischen.

Zwei Stolpersteine: `executescript()` beendet in Python eine offene
Transaktion (implizites `COMMIT`) — dort gehört nur Idempotentes hinein. Und
Umbenennungen müssen **vor** dem Anlegen von Indizes laufen, die auf den
neuen Spaltennamen stehen.

**Ein Aufruf, der nur nach der Fassung fragt, migriert nicht.** `--version`
bleibt ohne Nebenwirkung; für eine gezielte Migration gibt es `--migrieren`.

---

# CHECKLISTE

**Arbeitsweise**
- [ ] Ein Befund, ein Commit, Nummer in der ersten Zeile
- [ ] Jeder Prüfschritt **ausgeführt**, mit Zahlen im Commit
- [ ] Jede neue Prüflinie mit Mutationsprobe belegt

**Vertrag**
- [ ] Fassung an allen drei Stellen gleich, Tag passt dazu
- [ ] `/gesundheit` und `/api/version` ohne Anmeldung, ohne Schützenswertes
- [ ] Ohne `PROLO_EINLASS` kein Start; ohne Marke 401
- [ ] Jede geprüfte Gruppe im Label `prolo.gruppen`
- [ ] Herstellerdatei ohne Netz, ohne Traefik-Labels, ohne Speichergrenzen

**Oberfläche**
- [ ] Marke oben links nach §5, nur Token aus §2
- [ ] Höchstens eine `--feature`-Fläche, ein Primärbutton pro Screen
- [ ] `/einstellungen` nach §6a, Theme **pro Nutzer in der Datenbank**
- [ ] Pflichtblock aus §8.1, Kontrast geprüft, Touchziele ≥ 44 px
- [ ] Ab 360 px ohne seitliches Scrollen, im **Browser** geladen

**Robustheit**
- [ ] Alle Eingaben geprüft, keine stillen Vorgabewerte
- [ ] Zusammengehörende Schreibvorgänge in Transaktionen
- [ ] Fachlogik hat Tests mit handgerechneten Werten, Gegenprobe vollständig
- [ ] Löschen fragt nach; Migrationen nach §24a
