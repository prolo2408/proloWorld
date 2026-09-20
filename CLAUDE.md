# Prolo — die Regeln

Diese Datei ist **verbindlich** für jede Sitzung und jeden Agenten, die an
diesem Stack arbeiten. Sie ist die einzige Regeldatei: sie ersetzt die
früheren `prolo-regelblatt.md` und `prolo-betriebsregeln.md`.

**Leitsatz:** Funktionierender Code ist der Anfang, nicht das Ziel. Ein
Werkzeug ist fertig, wenn es auch dann noch etwas Vernünftiges tut, wenn
etwas schiefgeht — und wenn man es gerne benutzt.

Wo was steht:

| Datei | Inhalt |
|---|---|
| **diese hier** | die Regeln: Oberfläche, Robustheit, Betrieb |
| `NEUE-BEFUNDE.md` | was schon einmal schiefging und warum. Fast jede Regel hier hat dort eine Narbe |
| `wiki/vorlagen/prolo-bedienen.html` | die **Bedienung**: neuer Server, Alltag, Sichern, Wiederherstellen, Fehlersuche |
| `wiki/EINRICHTUNG.md` | der Seitenaufbau des Wikis im Einzelnen |
| `bordbuch/ANLEITUNG.md` | die Bedienung des Bordbuchs im Einzelnen |

---

# TEIL 0 — WIE HIER GEARBEITET WIRD

- **Ein Befund, ein Arbeitsschritt, ein Commit.** Die Commit-Nachricht
  beginnt mit der Nummer des Befunds (`N-16: …`).
- **Prüfschritte werden ausgeführt, nicht überlegt** (§14). Im Commit steht,
  was ausgeführt wurde und was dabei herauskam — **mit Zahlen**.
- **Erwartungswerte von Hand** (§13). Nie die Ausgabe des Codes als
  Erwartung übernehmen.
- **Tests müssen Zähne haben** (§13a): jede neue Prüflinie wird mit einer
  Mutationsprobe belegt. Eine Mutation, die unentdeckt bleibt, ist eine
  Testlücke und wird geschlossen.
- **Der Rückweg einer Probe darf nicht die eigene Arbeit sein.** Eine
  Mutationsprobe, die über `git checkout` zurückrollt, löscht eine noch
  nicht eingecheckte Korrektur mit weg (`N-34`). Kopie im Kratzblock — und
  zwar von allem, was die Probe **schreiben kann**, nicht nur von dem, was
  man von Hand ändert. Ruft die Probe einen Erzeuger auf, gehören seine
  **Ausgaben** gesichert, nicht seine Eingaben (`N-40`).
- **Nichts still nebenbei ändern.** Ein Problem, das beim Arbeiten auffällt,
  wird ein **neuer Befund** in `NEUE-BEFUNDE.md` und bekommt seinen eigenen
  Schritt.
- **Keine Datenwanderung ohne Sicherungshinweis** (§15).
- Eine Oberfläche ist erst geprüft, wenn sie im **Browser geladen** wurde.
  Zweimal hat ein Fehler auf oberster Skriptebene die ganze Hülle gekostet,
  während alle Tests grün waren (`N-14`, `N-17`), und einmal hat ein
  Kommentar sie abgeschaltet (`N-33`).
- **Eine Prüfung wird nicht durch eine Pipe gelesen.** `bash pruefen.sh |
  tail -2 && commit` liefert den Rückgabewert von `tail`, nicht den der
  Prüfung — der Commit läuft dann auch bei rotem Lauf durch (`N-39`).
- **Eine Meldung ist kein Beweis.** Eine Prüflinie, die den Text einer
  Ankündigung sucht, bleibt grün, wenn die Tat entfällt (`N-38`). Geprüft
  wird die Wirkung.

## Die drei Werkzeuge mit eigenem Code

| Ordner | Was | Fassung steht in |
|---|---|---|
| `wiki/` | Wissenssammlung, eigenständige HTML-Seiten in einem abgeschotteten Rahmen | `server.py` (`VERSION`), `docker-compose.yml` (`image:`), `CHANGELOG.md` |
| `bordbuch/` | Fahrtenbuch, Lade- und Tankkosten | ebenso |
| `www/` | `prolo.me`: HTML-Seiten ablegen und je Empfänger einen widerrufbaren Zugangslink ausgeben | ebenso |

Alle drei: Python-Standardbibliothek, SQLite, **kein Fremdpaket**. Geld in
**ganzen Cent** (`Decimal`, kaufmännisch gerundet), niemals `float` als
Speicherform.

```bash
cd wiki      && ./tests/alle.sh
cd bordbuch  && ./tests/alle.sh
cd www       && ./tests/alle.sh
```

Liegt `node` nicht im `PATH`, meldet `alle.sh` einen Fehlschlag — Absicht:
ein übersprungener Test ist kein grüner Test.

## Erzeugte HTML-Seiten gehören nach `wiki/vorlagen/`

Jede fertige Wiki-Seite, die hier entsteht — als Beispiel, als Anleitung, als
Vorführung eines Bausteins —, wird unter `wiki/vorlagen/` abgelegt, nicht in
einem Arbeitsordner und nicht nur im Text einer Antwort. Von dort ist sie
einspielbar, sie wird von `wiki/tests/test_seiten.py` gegen dieselbe Prüfung
gefahren, die beim Einspielen läuft, und sie geht bei der nächsten Sitzung
nicht verloren.

Was nur zum Messen gebraucht wird, bleibt im Kratzblock. Eine Probeseite, die
**mit Absicht** Fehler enthält, gehört nach `wiki/tests/` — in `vorlagen/`
würde sie zu Recht beanstandet.

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
ergänzt. Vorbilder: `bordbuch/tests/gegenprobe.sh`,
`werkzeuge/aktualisieren-pruefen.sh`, `werkzeuge/prolo-pruefen.sh`.

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
- **Vor Migrationen, die Daten verändern**, gilt der Dreischritt aus §19a:
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

# TEIL III — BETRIEB

Die **Handgriffe** stehen in der Wiki-Seite „Prolo bedienen und verstehen"
(`wiki/vorlagen/prolo-bedienen.html`). Hier stehen nur die Regeln.

## 16. Ein Ordner je Werkzeug

Alles unter `/opt/stack/`. Ein Werkzeug ist ein Ordner mit einer
`docker-compose.yml` — daran erkennt `prolo` es.

```
/opt/stack/<werkzeug>/
├── docker-compose.yml      Pflicht
├── sicherung.conf          Pflicht — was gesichert wird
├── aktualisierung.conf     Pflicht — wie aktualisiert wird
├── geheimnisse.conf        nur wenn das Werkzeug Geheimnisse hat
├── Dockerfile              nur bei eigenem Code
├── .dockerignore           nur bei eigenem Code — hält den Baukontext klein
├── CHANGELOG.md            nur bei eigenem Code
├── .gitignore              je Werkzeug, zusätzlich zur Wurzeldatei
├── .env                    nur wenn Geheimnisse nötig, NIE in Git
└── <quellcode>
```

Der Ordnername ist kleingeschrieben, ohne Leerzeichen und Umlaute, und
**identisch mit der Subdomain**: Ordner `bordbuch` → `bordbuch.prolo.me`.

Daneben liegt, was **allen** gemeinsam ist — und das ist kein Werkzeug, also
ohne `sicherung.conf` und `aktualisierung.conf`: `backup.sh`, `werkzeuge/`
(`prolo`, `aktualisieren.sh`, `quellstand.sh`, `geheimnisse.py`,
`pre-commit` und die Gegenproben), diese Datei und `NEUE-BEFUNDE.md`.

**Die Fassungsnummer steht an drei Stellen** und muss überall dieselbe sein:
`server.py` (`VERSION`), `docker-compose.yml` (`image:`), `CHANGELOG.md` (als
oberste Überschrift). Bleibt sie beim Veröffentlichen stehen, überschreibt
der nächste Bau das alte Abbild — und der Rückweg ist weg, obwohl
`aktualisieren.sh` ihn im Protokoll noch nennt. Im Wiki hält
`tests/test_fassung.py` die drei Stellen zusammen.

## 17. Anmeldung: niemals selbst bauen

**Kein Werkzeug bringt eine eigene Anmeldung mit.** Kein Login-Formular,
keine Registrierung, keine Passwortspeicherung, kein Zurücksetzen per Mail.
Die Identität kommt als HTTP-Kopf von Traefik:

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
  `werkzeuge/grenze-pruefen.sh` hält die fünf Stellen zusammen.
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

## 19. Container-Regeln

Verbindlich in jeder `docker-compose.yml`:

- **Keine `ports:`-Zeile.** Das ist der eigentliche Schutz: der Dienst ist nur
  über Traefik erreichbar. Eine `ports:`-Zeile hebelt Firewall und Anmeldung
  gleichzeitig aus.
- **Ein eigenes Netz je Werkzeug** (`netz-<werkzeug>`, extern), zusätzlich
  `internal` für Datenbanken. Datenbanken und Hilfsdienste hängen **nur** in
  `internal`.

  **Nur Traefik hängt in allen Werkzeugnetzen** (`N-45`). In einem
  gemeinsamen Netz erreicht jeder Container jeden anderen direkt — ohne
  Traefik, ohne Anmeldung. Vorher lagen Wiki, Bordbuch, n8n und Authentik in
  einem einzigen `proxy`, und damit stand der Weg von n8n (führt angeklickte
  Abläufe mit einem HTTP-Baustein aus, hat Webhook-Pfade ohne Anmeldung) zum
  Wiki offen.

  Jedes Werkzeug nennt sein Netz **selbst** im Label
  `traefik.docker.network` — seit `N-45` gibt es keine Vorgabe mehr, auf die
  Traefik zurückfallen könnte. Beim Anlegen eines Werkzeugs gehört sein Netz
  in **drei** Dateien: seine eigene, die von Traefik (Dienst **und** Block
  unten) — und einmal `docker network create netz-<werkzeug>` auf dem
  Server. `werkzeuge/netze-pruefen.sh` hält das zusammen.
- `restart: unless-stopped`
- **Grenzen sind Pflicht:**

  ```yaml
      mem_limit: 512m          # bordbuch, wiki: 512m · n8n: 2g · authentik: 1g
      pids_limit: 256
      security_opt: [ no-new-privileges:true ]
      cap_drop: [ ALL ]
  ```

  Ohne sie bringt ein Speicherleck in einem Werkzeug den **ganzen** Server in
  den OOM-Killer, die Container laufen mit dem vollen Satz an
  Linux-Fähigkeiten, und eine Datei mit setuid-Bit im Abbild ermöglicht eine
  Rechteausweitung.

  Zwei Dienste brauchen einzelne Fähigkeiten zurück, und nur diese: **Traefik**
  `NET_BIND_SERVICE` (80/443 sind privilegierte Ports), **PostgreSQL**
  `CHOWN`, `SETUID`, `SETGID`, `FOWNER`, `DAC_OVERRIDE`.

  `read_only: true` zusätzlich, wo das Programmverzeichnis nicht beschrieben
  wird — beim Bordbuch möglich, beim Wiki nicht (`pdftotext` legt
  Zwischendateien ab, `/seiten/.vorschau` wird zur Laufzeit gefüllt). Dann
  `tmpfs` für `/tmp` und `PYTHONDONTWRITEBYTECODE=1` im Dockerfile.
- **Feste Fassungsnummer beim Abbild, niemals `latest`.**
  Datenbankmigrationen bei Hauptversionen sind nicht umkehrbar.
- Persistente Daten in **benannten Volumes**, nicht im Container.
- **Pfade ohne Anmeldung** darf ein Werkzeug selbst bereitstellen
  (`/gesundheit`, `/api/version`) oder als zweiter Router ohne Middleware.
  Beides erlaubt; welche Variante gilt, gehört in den `HINWEIS` der
  `sicherung.conf`. Ein solcher Pfad gibt **nichts Schützenswertes** aus:
  „ok" und eine Fassungsnummer, mehr nicht.
- **Ausnahme Webhooks:** ein zweiter Router **ohne** `authentik@file` und mit
  höherer `priority` — und ein Vermerk unter `HINWEIS=`.
- **Zwei Router auf demselben Namen** sind erlaubt, wenn ein Teil öffentlich
  sein muss (`www/`: die Startseite und die Zugangslinks). Dann gilt: der
  geschützte Router bekommt die **höhere** `priority`, sonst gewinnt der
  breitere und die Verwaltung steht offen. Und das Werkzeug prüft die Gruppe
  **zusätzlich selbst** — eine Kopfzeile allein ist auf einem Host mit
  öffentlichem Router kein Nachweis.
- **Eine Ratenbremse am Eingang** (`N-46`), vor allem anderen: wer zu schnell
  oder zu oft gleichzeitig anklopft, kommt gar nicht erst bis zur Anmeldung.
  Gemessen je Quelladresse. Der Wert muss **beides** können — einen Menschen
  durchlassen (ein Seitenaufruf des Wikis sind rund 15 Anfragen; bei 24/s
  null Abweisungen) und ein Skript bremsen (bei 302/s wurden 558 von 800
  abgewiesen). Sie hilft **nicht** gegen verteiltes Raten von vielen
  Adressen; dagegen hilft nur, dass es nichts zu raten gibt.

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

Was das System nie verlässt: `.env`, `acme.json`, Schlüssel, Zertifikate,
Datenbanken, Sicherungen, Archive entfernter Werkzeuge.

`/opt/stack/.gitignore` enthält mindestens `**/.env`, `**/.env.*` mit der
Ausnahme `!**/.env.beispiel`, `**/acme.json`, `**/*.key`, `**/*.pem`,
`**/*.db*`, `**/*.sqlite`, `**/*.sql`, `**/*.dump`, `**/daten/`,
`**/seiten/`, `**/backups/`, `**/.vorschau/`, `**/*.vor-stand-*`,
`.archiv/`, `authentik/data/`, `authentik/certs/`, `merkzettel/`,
`*.txt.age`, `.geheimnis-stand`.

**Zusätzlich eine `.gitignore` je Werkzeug.** Die Wurzeldatei allein trägt
nicht: sie ist leicht zu übersehen, und ein Werkzeug bringt seine Regel dort
mit, wo die Daten entstehen. Wer ein Werkzeug anlegt, das eine **neue Art von
Daten** ablegt, ergänzt die Regel im **selben** Arbeitsschritt.

**Und sie trägt die Ausnahmen mit** (`N-53`). Für Dateien im Werkzeugordner
gewinnt die tool-eigene `.gitignore` gegen die Wurzeldatei. Wer dort
`.env.*` schreibt, ohne `!.env.beispiel` daneben, fängt seine **eigene
Vorlage** mit — auf der Platte ist alles da, im Repository nichts, und
auffallen tut es erst beim nächsten frischen Klon. Jede Vorlage, die ein
Werkzeug zum Aufsetzen braucht, muss in `git ls-files` auftauchen; der Text
der Regeln ist kein Beweis.

**Vor jedem Push:** `git status` und `git diff --cached` wirklich **lesen**.
Taucht dort etwas Schützenswertes auf: nicht committen, erst die `.gitignore`
korrigieren. Dazu der versionierte Vorab-Test:

```bash
ln -sf ../../werkzeuge/pre-commit .git/hooks/pre-commit
```

Das muss **nach jedem frischen Klon** neu gesetzt werden — `.git/hooks` wird
nicht mitversioniert. Der Haken ist ein Netz, kein Ersatz fürs Hinschauen.

## 22. Protokolle und Weitergabe

- Keine Geheimnisse und keine vollständigen Kopfzeilen ins Protokoll;
  `X-Authentik-Jwt` und `Cookie` weglassen oder kürzen.
- Fehlermeldungen an den Nutzer enthalten keine internen Pfade und keine
  Datenbankfehler im Original.
- **Nichts Schützenswertes in einen Chat** — auch nicht „nur zum Nachsehen".
  Weitergeben darf man den **Namen** einer Variable, den **Ort** einer Datei,
  die **Meldung** ohne den Wert. Für die Fehlersuche reicht das fast immer.

## 23. Sicherung

**Eine Sicherung auf demselben Server ist keine Sicherung.** Es braucht immer
eine Kopie außer Haus.

| Was | Wohin |
|---|---|
| Konfiguration | Git, privates Repository |
| Geheimnisse | Passwortmanager **und** verschlüsselte Sicherung — `prolo geheimnisse --merkzettel` schreibt den Zettel dafür |
| Daten | `prolo sichern`, danach weg vom Server |

Jedes Werkzeug bringt seine `sicherung.conf` mit (`VOLUMES`, `DB_CONTAINER`,
`DATEIEN`, `ORDNER`, `SQLITE`, `HINWEIS`); das zentrale Skript liest sie ein,
also ist beim Anlegen eines Werkzeugs an der Sicherung **nichts** zu ändern.

**SQLite braucht ein eigenes Feld.** Eine Datei aus dem laufenden Volume zu
kopieren kann einen Stand mitten in einer Schreibaktion erwischen — die Kopie
sieht heil aus und ist kaputt. Darum über `sqlite3.backup()`.

Verschlüsselt wird mit `age` gegen den **öffentlichen** Schlüssel in
`/opt/stack/.backup-schluessel.pub`; der geheime Teil liegt auf dem
Arbeitsrechner. Ohne diese Datei fängt die Sicherung nicht an: eine
unverschlüsselte Sicherung mit `.env` darin wäre schlimmer als keine.

### 23a. Die Geheimnisse selbst

Was ein Werkzeug an Geheimnissen hält, sagt es in seiner `geheimnisse.conf`
— wie bei der Sicherung ist zentral nichts zu ändern, wenn ein Werkzeug
dazukommt. Eine Zeile je Wert: `NAME|DATEI|FORM|WECHSEL|Erklaerung`, und
**nie ein Wert darin**. `prolo geheimnisse` liest sie und zeigt Namen, Orte
und Alter — Werte stehen dort nicht, auch nicht „nur zum Nachsehen" (§22).

`WECHSEL` sagt, was ein neuer Wert kostet, und ist die einzige Bremse des
Werkzeugs:

| Wert | Bedeutung |
|---|---|
| `harmlos` | darf neu gewürfelt werden, niemand merkt etwas |
| `sitzungen` | darf auch, aber alle müssen sich neu anmelden |
| `haende` | **nur von Hand** — das Werkzeug zeigt ihn und rührt ihn nicht an |

**Steht ein Wert auch außerhalb seiner Datei, ist er `haende`.** `PG_PASS`
steht zusätzlich in PostgreSQL selbst: wer nur die Datei ändert, sperrt
Authentik aus seiner eigenen Datenbank aus — und damit den ganzen Stack aus
der Anmeldung. Ein Werkzeug, das das nicht weiß, macht aus einem gepflegten
Wechsel einen Ausfall.

Gewechselt wird **erst Traefik, dann die Werkzeuge**: andersherum stünden die
Werkzeuge mit dem neuen Wert da, während Traefik noch den alten anhängt, und
jede Anfrage bekäme 401. Der Merkzettel enthält **alten und neuen** Wert und
ist mit demselben `age`-Schlüssel verschlüsselt wie die Sicherung.

**Die Wiederherstellung wird geübt**, solange nur Testdaten drin sind. Das
ist der Schritt, den fast alle überspringen, und der einzige, der zählt.

## 24. Aktualisierung

- **Erst die Fassungsnummer, dann der Lauf.** Bei eigenem Code gehört sie
  **mit dem Quellcode zusammen** erhöht, nicht danach: sie ist das Etikett des
  Abbilds, das aus genau diesem Stand gebaut wird.
- Nie mehrere Hauptversionen auf einmal überspringen.
- `prolo aktualisieren` holt den neuen Quellstand selbst, sichert, baut,
  wartet auf „gesund" und rollt bei Fehlschlag auf den Stand des letzten
  **erfolgreichen** Laufs zurück. Der Rückweg ist die Kopie der
  `docker-compose.yml`, nicht ein `sed` auf die `image:`-Zeile — bei mehreren
  Diensten würde das alle auf dasselbe Abbild setzen.
- **Ein Skript, das sich selbst ersetzt haben kann, startet neu.** Bash liest
  ein Skript häppchenweise von der Platte; nach einem Pull weiterzulaufen
  hieße, halb die alte und halb die neue Fassung auszuführen (`N-38`).
- `PRUEF_WARTEN` ist eine **Obergrenze**, keine feste Wartezeit.

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

## 25. Monatliche Pflege

Betriebssystem aktualisieren, Platz freigeben (`docker image prune -a`),
Fassungsnummern gegen die Releases-Seiten abgleichen —
**Sicherheitsaktualisierungen bei Authentik und Traefik haben Vorrang**, die
stehen an der Tür.

**Und: lebt die Sicherung noch?** `prolo status` sagt es. Ist der Vermerk
älter als zwei Tage oder fehlt er, ist zuerst das zu klären und nichts zu
aktualisieren. Eine Sicherung, deren Scheitern niemand merkt, ist keine
Sicherung.

---

# TEIL IV — CHECKLISTE

**Arbeitsweise**
- [ ] Ein Befund, ein Commit, Nummer in der ersten Zeile
- [ ] Jeder Prüfschritt **ausgeführt**, mit Zahlen im Commit
- [ ] Jede neue Prüflinie mit Mutationsprobe belegt
- [ ] Neue Probleme als neuer Befund, nicht still nebenbei

**Oberfläche**
- [ ] Marke oben links nach §5
- [ ] Nur Token aus §2, Text auf `--accent` über `--on-accent`
- [ ] Höchstens eine `--feature`-Fläche, ein Primärbutton pro Screen
- [ ] Sora / Instrument Sans / JetBrains Mono richtig eingesetzt
- [ ] Karten ohne Schatten, Schatten nur am Fenster
- [ ] Inhalt auf `max-width:1280px` begrenzt und zentriert
- [ ] Keine halbleeren Rasterzeilen, `min-width:0` an Rasterkindern
- [ ] Zahlen deutsch formatiert, Einheiten korrekt

**Einstellungsseite**
- [ ] `/einstellungen` vorhanden und aus der Navigation erreichbar
- [ ] Theme System / Hell / Dunkel, **pro Nutzer in der Datenbank**
- [ ] Optionen mit je einer Zeile Erklärung
- [ ] „Abmelden / neu laden" mit Erklärung, Ziel `sign_out`
- [ ] Im Header nur der Anzeigename als Verweis hierher

**Bedienbarkeit**
- [ ] Pflichtblock aus §8.1 vorhanden (`[hidden]`, Fokus, Bewegungsreduzierung)
- [ ] Alles mit Tastatur erreichbar, Fokusrahmen sichtbar
- [ ] Ab 360 px ohne seitliches Scrollen
- [ ] Touchziele ≥ 44 px
- [ ] Kontrast geprüft (4.5:1 / 3:1), auch auf `--feature`
- [ ] Jede Aktion gibt sichtbare Rückmeldung
- [ ] Kein Knopf, der nichts tut

**Robustheit**
- [ ] Alle Eingaben geprüft, keine stillen Vorgabewerte
- [ ] Zusammengehörende Schreibvorgänge in Transaktionen
- [ ] Fachlogik hat Tests mit handgerechneten Werten
- [ ] Gegenprobe vorhanden und **alle** eingebauten Fehler werden gefunden
- [ ] Kein Erwartungswert, der bei zwei Verfahren gleich herauskommt
- [ ] Geldbeträge nicht als Fließkommazahl
- [ ] Löschen fragt nach
- [ ] Die neun Punkte aus §14a **einzeln durchgesehen**, zwei Themen, drei Breiten
- [ ] Die acht Punkte aus §14b tatsächlich ausprobiert
- [ ] Im **Browser** geladen, nicht nur getestet

**Betrieb**
- [ ] Keine `ports:`-Zeile, Grenzen gesetzt, feste Abbildfassung
- [ ] `sicherung.conf` und `aktualisierung.conf` vorhanden und gefüllt
- [ ] `geheimnisse.conf`, falls das Werkzeug Geheimnisse hat — ohne Werte
- [ ] `.gitignore` je Werkzeug ergänzt, `pre-commit` verlinkt
- [ ] Fassungsnummer an allen drei Stellen gleich
- [ ] Sicherung und Aktualisierung je einmal durchgelaufen

**Spaß**
- [ ] Häufigster Arbeitsablauf in möglichst wenigen Schritten
- [ ] Sinnvolle Vorbelegungen — nichts abfragen, was schon bekannt ist
- [ ] Eingaben gehen bei einem Fehler nicht verloren
- [ ] Zahlen kommentieren sich selbst („7,4 l/100 km — 0,3 unter dem Schnitt")
- [ ] Leere Zustände erklären den nächsten Schritt
- [ ] Keine Überraschungen: gleiche Geste, gleiche Wirkung, in jedem Werkzeug
