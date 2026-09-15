# Prolo — Regelblatt für Oberflächen und Codequalität

Diese Datei an Claude geben, wenn eine neue Prolo-Anwendung, ein neuer
Screen oder ein Umbau ansteht. Sie ist verbindlich.

Begleitdatei: `prolo-betriebsregeln.md` regelt Infrastruktur, Anmeldung,
Sicherung, Aktualisierung und schützenswerte Daten. Diese hier regelt
Aussehen, Qualität und Bedienung.

Leitsatz: Funktionierender Code ist der Anfang, nicht das Ziel. Ein Tool
ist fertig, wenn es auch dann noch etwas Vernünftiges tut, wenn etwas
schiefgeht — und wenn man es gerne benutzt.

---

# TEIL I — DESIGNSYSTEM

## 1. Grundhaltung

- Ruhig, sachlich, datennah. Keine Verläufe, keine Emojis, keine
  dekorativen Illustrationen.
- Eine Akzentfarbe (Blau), sonst Graustufen. Farbe bedeutet immer etwas:
  aktiv, positiv, Warnung, Kategorie.
- Viel Weißraum, klare Kanten, flache Flächen. Schatten nur für das
  Fenster selbst, nicht für Karten.
- Dunkelmodus ist der Standard, Hellmodus muss gleichwertig funktionieren.
- Zahlen sind der Inhalt: groß, in Sora, mit Monospace für Rohwerte.

**Lesbarkeit schlägt Palette.** Die Tokens sind der Normalfall, nicht der
Selbstzweck. Wenn eine Kombination schlecht lesbar ist, wird sie geändert
— nicht beibehalten, weil sie „regelkonform" ist. Reines Schwarz auf
reinem Weiß (und umgekehrt) ist hart und ermüdet; deshalb liegen die
Tokens bewusst nicht bei 0 und 1. Nie `#000` oder `#fff` direkt setzen,
außer als Text auf `--accent`.

Wer eine neue Farbe braucht: **neues Token mit klarer Bedeutung
ergänzen**, keinen Einzelwert in die Komponente schreiben.

## 2. Farbtoken

Nie Farbwerte direkt in Komponenten schreiben. Immer diese Variablen
benutzen. Definition einmal pro Seite, Umschaltung über `data-theme` auf
`<body>`.

```css
:root{
  --bg:oklch(0.96 0.004 250);        /* Seitenhintergrund             */
  --app:oklch(0.985 0.002 250);      /* Fensterfläche                 */
  --surface:#fff;                     /* Karte, Tabelle, Panel         */
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
  --bar:oklch(0.86 0.03 262);        /* zweite Datenreihe im Chart    */

  --good:oklch(0.45 0.14 158);       /* Ersparnis, günstigster Preis  */
  --good-soft:oklch(0.97 0.01 158);
  --warm-soft:oklch(0.94 0.01 60);   /* Kategorie Verbrenner/Tanken   */
  --warm-ink:oklch(0.45 0.08 60);

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
  --good:oklch(0.8 0.14 158); --good-soft:oklch(0.29 0.05 158);
  --warm-soft:oklch(0.33 0.05 60); --warm-ink:oklch(0.86 0.08 60);
  --feature:oklch(0.31 0.07 262); --feature-ink:oklch(0.97 0.004 250); --feature-ink-2:oklch(0.8 0.02 250);
  --feature-line:oklch(0.42 0.05 262); --feature-good:oklch(0.85 0.15 158);
  --track:oklch(0.3 0.014 258);
  --shadow:0 24px 60px -20px oklch(0.05 0 0 / 0.6);
}
```

### Einsatzregeln

| Token | wofür | nicht |
|---|---|---|
| `--accent` | genau eine Primäraktion pro Screen, aktiver Navigationspunkt, wichtigste Datenreihe | große Flächen, Fließtext |
| `--accent-soft` | Badges, Icon-Kacheln, aktive Nav-Zeile | Karten |
| `--good` | Ersparnis, günstigster Preis, negative Kostenänderung | „erledigt"-Meldungen |
| `--warm-soft/ink` | Kategorie Verbrenner/Tanken | Warnungen |
| `--feature` | höchstens **eine** farbige Fläche pro Screen (Hero-Kennzahl) | mehrere Panels gleichzeitig |

Nie eine schwarze Karte in eine sonst helle Ansicht setzen. Wenn eine
Fläche hervorstechen soll, ist das `--feature` — und davon gibt es genau
eine.

**Zusatzregel:** Farbe darf nie die einzige Information sein. Rot allein
reicht nicht, es braucht Text oder ein Symbol dazu — sonst ist es für
farbfehlsichtige Nutzer unlesbar.

**Kontrast-Ausnahme:** Erreicht eine Token-Kombination die Mindestwerte
aus Abschnitt 8 nicht, wird das nächsthellere bzw. -dunklere Token
genommen. Beispiele, die häufig zu schwach sind: `--ink-3` auf
`--accent-soft`, Monospace-Kleintext auf `--feature`. Dort `--ink-2` bzw.
`--feature-ink` verwenden. Gibt es kein passendes Token, wird eines
ergänzt.

### Nachträglich aufgenommen

Drei Token, die das Bordbuch sinnvoll ergänzt hatte, die aber im Regelwerk
fehlten — aus der Prüfung vom 14.09.2026. Der letzte Satz oben sagt
ausdrücklich „Gibt es kein passendes Token, wird eines ergänzt"; ergänzt
werden muss es dann aber **hier**, sonst weiß das nächste Tool nichts davon:

| Token | Wofür | Warum es nötig ist |
|---|---|---|
| `--danger` | Zerstörende Aktionen: Löschen, Zurücksetzen | `--warn` ist eine Warnung, kein Verlust. Wer beides mit derselben Farbe zeigt, nimmt dem Löschen sein Gewicht. |
| `--on-accent` | Text **auf** `--accent` | Abschnitt 1 erlaubt dort `#fff` ausdrücklich. Als Token ist es nachvollziehbar und lässt sich an einer Stelle ändern, falls `--accent` einmal heller wird. |
| `--overlay` | Abdunklung hinter Dialogen und Blättern | Sonst schreibt jedes Tool sein eigenes `rgba(0,0,0,.5)` — und sie sehen verschieden aus. |

## 3. Typografie

- **Sora** 600: Überschriften, Kennzahlen, Beträge, Kartentitel.
- **Instrument Sans** 400/500/600: alles andere.
- **JetBrains Mono** 400/500: Rohwerte, Mengen, Datum, Einheiten,
  Tabellen-Kopfzeilen (10–11 px, `letter-spacing:0.06em`,
  `text-transform:uppercase`).

Größen: Seitentitel 20–22, Kennzahl groß 30–40, Kartentitel 15, Fließtext
13–14, Sekundärtext 12, Label 10–11.

Auf Überschriften und Kennzahlen `letter-spacing:-0.02em`. Handy: nichts
unter 12 px, Touchziele mindestens 44 px.

## 4. Form und Abstand

- Radien: Fenster 18, Handyrahmen 42, Karte Desktop 14, Karte Handy 16–20,
  Steuerelement 10, Badge 5.
- Abstände: 4er-Raster. Karteninhalt 18–20, Abstand zwischen Karten 14–20,
  Seitenrand Desktop 32, Handy 20.
- Karten: `background:var(--surface); border:1px solid var(--line)` — kein
  Schatten. Schatten nur am Gesamtfenster (`--shadow`).
- Gruppen immer mit `display:flex/grid` + `gap`, nie mit Rand-Abständen
  einzelner Elemente.

## 5. Bausteine

**Tool-Logo (Pflicht, oben links)**

Jedes Tool hat eine Marke oben links — schlicht, nicht illustrativ. Immer
derselbe Aufbau, damit die Tools als Familie erkennbar sind:

```html
<div style="display:flex; align-items:center; gap:10px">
  <div style="width:30px; height:30px; border-radius:8px; flex:0 0 30px;
              background:var(--accent); color:#fff;
              display:flex; align-items:center; justify-content:center;
              font-family:'Sora',sans-serif; font-size:15px; font-weight:600">B</div>
  <div style="min-width:0">
    <div style="font-family:'Sora',sans-serif; font-size:14px; font-weight:600;
                color:var(--ink); line-height:1.2">Bordbuch</div>
    <div style="font-family:'JetBrains Mono',monospace; font-size:10px;
                letter-spacing:0.06em; text-transform:uppercase;
                color:var(--ink-3); line-height:1.4">Fahrtenbuch</div>
  </div>
</div>
```

Regeln dazu:

- Kachel 30 px, Radius 8, `--accent` als Fläche, ein Großbuchstabe in
  `#fff`. Ein Buchstabe, keine Wortmarke in der Kachel.
- Daneben der Toolname (Sora 14) und darunter eine kurze Einordnung in
  Monospace-Versalien.
- Die Unterzeile beschreibt **das Tool**, nicht den Zustand. „Fahrtenbuch"
  ist richtig, „1 Seite" gehört in den Inhalt, nicht unter das Logo.
- Keine Emojis, keine Icon-Bibliothek, keine Illustration. Wer mehr als
  einen Buchstaben braucht, braucht ein einfacheres Logo.
- Ein Klick auf das Logo führt immer zur Startseite des Tools.

**Karte**
```html
<div style="padding:18px; border-radius:14px; background:var(--surface); border:1px solid var(--line)">
  <div style="font-family:'Sora',sans-serif; font-size:15px; font-weight:600; color:var(--ink)">Titel</div>
  <div style="margin-top:2px; font-size:12px; color:var(--ink-3)">Kontextzeile</div>
</div>
```

**Kennzahl** — Label 12 px `--ink-3`, Wert Sora 30 px `--ink`, Einheit
14 px `--ink-3` daneben, darunter eine Monospace-Zeile mit Vergleich oder
Herkunft.

**Primärbutton** — Höhe 38 (Desktop) bzw. 52 (Handy), Radius 10/16,
`background:var(--accent)`, Text `#fff`, 600, Hover `--accent-hover`. Ein
Primärbutton pro Screen, alles andere ist Text oder Rahmenbutton.

**Segment-Umschalter** — Spur `--track`, Radius 10, aktives Segment
`--surface` + feiner Schatten, inaktiv `--ink-3`.

**Badge** — `padding:2px 7px; border-radius:5px`, 11 px, 600; Strom
`--accent-soft/--accent-ink`, Sprit `--warm-soft/--warm-ink`.

**Tabelle** — Monospace-Kopfzeile in Versalien, Zeilen 13 px `--ink-2`,
Trenner `--line-soft`, Zahlen rechtsbündig in Monospace, Summen 500. Hover
`--hover`.

**Liste auf dem Handy** — Zeile = Icon-Kachel 38 px (`--accent-soft` /
`--warm-soft`), Titel 14 px 600, Metazeile 12 px `--ink-3`, Betrag rechts
in Sora 15 px.

**Diagramm** — flache Balken, Radius 5–6, aktueller Monat in `--accent`,
Vergangenheit in `--bar`. Achsen weglassen, Werte direkt über die Balken
schreiben. Keine Chart-Bibliothek-Optik, keine Gitternetzlinien.

**Scrollbereiche** — Scrollbalken ausblenden: `scrollbar-width:none` plus
`[data-noscroll]::-webkit-scrollbar{width:0;height:0}`.

## 6. Aufbau der Screens

**Desktop (1440 × 900)**
Sidebar 248 px (`--chrome`): oben das Tool-Logo aus Abschnitt 5,
Navigation mit 44-px-Zeilen und 4-px-Aktivstrich, unten nur
„Einstellungen".
Header 76 px: links Titel + Kontextzeile, rechts Kontext-Auswahl (z. B.
Fahrzeug), Zeitraum-Segment, Primärbutton, ganz rechts der Anzeigename
als Verweis auf die Einstellungen.
Inhalt: KPI-Reihe (4 Spalten), darunter Raster `1.55fr / 1fr` — links
Diagramm und Tabelle, rechts schmale Karten.

**Inhaltsbreite begrenzen.** Der Inhaltsbereich bekommt
`max-width:1280px; margin:0 auto`. Ohne das zieht sich auf breiten
Bildschirmen alles auseinander: Hero-Kacheln stehen fast leer da, Karten
reißen Löcher, und der Blick muss quer über den Schirm wandern. Die
Sidebar bleibt außerhalb dieser Begrenzung.

**Keine halbleeren Reihen.** Wenn eine Rasterzeile nur ein oder zwei
Elemente hat, wird die Spaltenzahl reduziert, statt die Lücke stehen zu
lassen. Eine Kachel mit einer einzigen Zahl darf nicht über die volle
Breite laufen.

**Handy (390 × 844)**
Statusleiste, Kopf mit Tool-Logo (verkleinert) + Titel + Kontextchip,
Inhalt (Hero-Kennzahl in `--feature`, Diagramm, Liste), Primärbutton über
der Tabbar, Tabbar mit 4 Einträgen und 3-px-Aktivstrich. Der letzte
Tabbar-Eintrag ist „Einstellungen".

Kontextobjekte (Fahrzeug, Konto, Projekt) gehören in den Header bzw.
Kopfbereich, nicht in die Sidebar-Fußzeile.

## 6a. Einstellungsseite (Pflicht je Tool)

Jedes Tool hat eine eigene Einstellungsseite unter `/einstellungen`. Sie
ist der einzige Ort für Darstellung, Konto und tool-eigene Optionen — der
Header bleibt dadurch frei für den eigentlichen Inhalt.

Aufbau, immer in dieser Reihenfolge:

**1. Darstellung**
- Segment-Umschalter mit drei Zuständen: `System` / `Hell` / `Dunkel`.
  `System` ist die Voreinstellung und folgt
  `prefers-color-scheme`.
- Die Wahl wird **pro Nutzer in der Datenbank des Tools** gespeichert,
  nicht nur im Browser — sonst ist sie auf dem Handy wieder weg.
- Umschaltung über `document.body.dataset.theme`, ohne Neuladen.

**2. Tool-Einstellungen**
- Alles Fachliche: Standardfahrzeug, Einheiten, Zusatzfunktionen,
  Ansichtsoptionen.
- Zusatzfunktionen als klar beschriftete Schalter, mit einer Zeile
  Erklärung darunter. Ein Schalter ohne Erklärung ist ein Rätsel.

**3. Freigaben** (nur wenn das Tool Daten teilen kann)
- „Meine Freigaben" und „Für mich freigegeben", siehe Betriebsregeln.

**4. Konto**
- Anzeigename und E-Mail **nur zur Anzeige**, mit dem Hinweis, dass sie
  zentral verwaltet werden.
- Knopf **„Abmelden / neu laden"** mit der Erklärung darunter:
  *„Beendet die Anmeldung und lädt die Seite neu. Danach kann ein anderes
  Konto verwendet werden."*
  Ziel ist `/outpost.goauthentik.io/sign_out`. Die doppelte Beschriftung
  ist Absicht — es ist eine Weiterleitung, keine reine Abmeldung im Tool,
  und der Nutzer soll nicht überrascht sein, wenn die Seite neu lädt.

Im Header steht nur noch der Anzeigename, verlinkt auf diese Seite. Kein
Theme-Umschalter und kein Abmelden-Knopf direkt in der Kopfzeile.

## 7. Sprache

Deutsch, sachlich, keine Werbesprache. Substantive statt Aufforderungen in
Labels („Vorgang erfassen", „Kosten je Monat", „Günstig in der Nähe").

Zahlen deutsch formatieren: Dezimalkomma, Tausenderpunkt, Einheit mit
schmalem Abstand (`8,72 €`, `17,8 kWh/100 km`, `1.284 km`). Datum kurz
`09.09.`.

Fehlermeldungen sagen, **was zu tun ist**, nicht nur was kaputt ist.
Keine technischen Brocken für den Nutzer: „Speichern hat nicht geklappt —
Verbindung zum Server unterbrochen" statt „HTTP 500".

## 8. Umsetzungsregeln

- Kein Farbwert ohne Token. Neue Bedeutung heißt neues Token, nicht neue
  Einzelfarbe.
- Themenwechsel über `document.body.dataset.theme`; Standard `dark`.
- Kontrast: Text mindestens 4.5:1, große Überschriften 3:1.
- Fluide Layouts, außer bei bewusst festen Formaten (Gerätemockup,
  Präsentation, Druck).

### 8.1 Inline-Styles: wann ja, wann nein

**Entwürfe, Mockups, Präsentationsbilder:** alles inline stylen, keine
CSS-Klassen. Ausnahme ist der Tokenblock aus Abschnitt 2.

**Echte Anwendungen:** Grundstil weiterhin inline, aber Zustände und
Umgebungsabfragen gehören in einen kleinen CSS-Block. Inline-Styles
können `:focus-visible`, `:hover`, `@media` und `prefers-reduced-motion`
technisch nicht ausdrücken — ohne sie gibt es keinen Fokusrahmen für
Tastaturbedienung und keine mobile Anpassung. Der Pflichtblock:

```css
button:focus-visible, a:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }
@media (max-width:432px){ /* Layoutanpassungen */ }
```

## 9. Bedienbarkeit (nicht verhandelbar)

- Jedes bedienbare Element ist mit der Tastatur erreichbar und zeigt einen
  sichtbaren Fokusrahmen.
- Wer Bewegungsreduzierung eingestellt hat, bekommt keine Animationen.
- Klickflächen mindestens 44 × 44 px — die Tools werden am Handy benutzt,
  mit Daumen und teilweise mit Handschuhen.
- Beschriftungen gehören zum Eingabefeld (`<label for>`), nicht daneben
  geschrieben.
- Kein reines Icon ohne Text oder `aria-label`.
- Layout funktioniert ab 360 px Breite ohne seitliches Scrollen.
- `env(safe-area-inset-bottom)` berücksichtigen, damit nichts unter der
  Gestenleiste klebt.
- Zahlenfelder mit passender Tastatur: `inputmode="decimal"` für Beträge,
  `inputmode="numeric"` für Kilometerstände.

## 10. Rückmeldung an den Nutzer

- Jede Aktion bestätigt sich sichtbar. Speichern ohne Rückmeldung fühlt
  sich kaputt an, auch wenn es funktioniert hat.
- Kurze Bestätigungen als Einblendung, Fehler bleiben stehen bis man sie
  wegklickt.
- Ladezustände anzeigen, sobald etwas länger als etwa 300 ms dauert.
- Knöpfe während einer laufenden Aktion sperren, damit nichts doppelt
  abgeschickt wird.

---

# TEIL II — ROBUSTHEIT

## 11. Eingaben sind grundsätzlich falsch

Jede Eingabe von außen — Formular, Datei, Schnittstelle — wird geprüft,
bevor sie irgendwo landet:

- Pflichtfelder wirklich vorhanden?
- Zahlen im plausiblen Bereich? (Ein Kilometerstand von 9 Millionen ist
  ein Tippfehler, kein Datensatz.)
- Datum lesbar und nicht in der Zukunft, wo das keinen Sinn ergibt?
- Text auf sinnvolle Länge begrenzt?

**Keine stillen Vorgabewerte.** Fehlt ein Wert, wird das gemeldet — nicht
durch eine Null ersetzt. Eine Null in der Verbrauchsrechnung ist
schlimmer als eine Fehlermeldung, weil sie falsche Ergebnisse erzeugt,
die niemandem auffallen.

## 12. Fehler dürfen nichts kaputt machen

- Eine fehlgeschlagene Aktion hinterlässt **keinen halben Datensatz**. Bei
  mehreren zusammengehörenden Schreibvorgängen: Transaktion nutzen.
- Import von 200 Zeilen, Zeile 137 ist kaputt: Die Datei wird entweder
  ganz übernommen oder gar nicht — und es steht im Klartext da, welche
  Zeile das Problem war.
- Netzwerkfehler und Zeitüberschreitungen abfangen. Ein hängender Aufruf
  darf die Oberfläche nicht einfrieren.

## 13. Rechnen

- Geldbeträge niemals als Fließkommazahl.
- Jede Größe mit Einheit im Namen: `menge_l`, `energie_kwh`.
- Keine Steuersätze, Preise oder Wirkungsgrade fest im Code — die gehören
  in Konfiguration mit Gültigkeitsdatum.
- Rechnende Funktionen brauchen Tests mit **von Hand gerechneten**
  Erwartungswerten. Nicht die Ausgabe des Codes als Erwartung übernehmen
  — das testet nur, dass sich nichts ändert, nicht dass es stimmt.

Pflichtfälle je Berechnung: ein normaler Fall (handgerechnet), der
Grenzfall (null, negativ, sehr groß), der Fall mit fehlenden Daten.

### 13a. Die Tests müssen Zähne haben

Aus der Prüfung vom 14.09.2026. Handgerechnete Erwartungswerte sind
notwendig, aber nicht genug: ein Test kann grün sein, weil er nichts prüft.

**Darum wird zu jeder Testsuite eine Gegenprobe geschrieben**, die
absichtlich Fehler in den Code einbaut und verlangt, dass **jeder** von einem
Test gefunden wird. Findet ihn keiner, ist der Test Beschäftigung und wird
ergänzt. Vorbild: `bordbuch/tests/gegenprobe.sh`.

Warum das nicht theoretisch ist — ein Fall aus dieser Prüfung: die
Rundungstests benutzten `8,995 €`. Kaufmännisch gerundet ergibt das 900
Cent, zur geraden Zahl gerundet ebenfalls 900 — weil 900 gerade ist. Der
Test war grün und hätte **beide** Rundungsarten durchgelassen, also genau
den Fehler nicht gefunden, um dessentwillen er geschrieben wurde. Aufgefallen
ist das erst, als die Gegenprobe „Rundung zur geraden Zahl" einbaute und
kein Test anschlug. Ergänzt wurden `8,985`, `1,005`, `2,665` und `-8,985` —
Werte, bei denen sich die beiden Arten unterscheiden.

Ein Erwartungswert, der bei zwei verschiedenen Verfahren gleich herauskommt,
prüft das Verfahren nicht.

## 14. Was durchprobiert sein muss

Ein Tool gilt erst als fertig, wenn diese Fälle **tatsächlich ausprobiert**
wurden — nicht nur gedanklich. Ein Screenshot der fertigen Ansicht ist
Teil der Abnahme, nicht die Behauptung, es sehe gut aus.

### 14a. Oberfläche — gründlich durchsehen

Jede Ansicht wird einzeln angeschaut, in **beiden Themen**, bei
**drei Breiten** (360 px, 768 px, 1920 px):

1. **Löcher im Layout.** Bleibt irgendwo eine große leere Fläche, weil
   eine Rasterzeile nicht gefüllt ist? Dann Spaltenzahl anpassen.
2. **Auseinandergezogene Inhalte.** Läuft eine Kachel mit wenig Inhalt
   über die volle Breite? `max-width` prüfen (Abschnitt 6).
3. **Überlauf.** Langer Text, langer Name, große Zahl (`1.284.500,55 €`)
   — bricht etwas aus der Karte aus oder wird abgeschnitten?
4. **Leere Zustände.** Jede Liste, jede Tabelle, jedes Diagramm ohne
   Daten. Steht dort ein hilfreicher Satz oder nur Leere?
5. **Ausrichtung.** Sind Zahlen in Spalten wirklich rechtsbündig und in
   Monospace? Fluchten Kartenkanten untereinander?
6. **Kontrast.** Jede Text-auf-Fläche-Kombination gegen die Werte aus
   Abschnitt 8 prüfen, besonders Kleintext auf `--accent-soft` und
   `--feature`.
7. **Doppelte Scrollbalken**, abgeschnittene Ränder, Elemente unter der
   Gestenleiste.
8. **Beschriftungen.** Einheitliche Groß- und Kleinschreibung bei Badges
   und Labels. Keine Abkürzung, die nur der Entwickler versteht.
9. **Zoom 200 %** im Browser — bleibt alles bedienbar?

### 14b. Verhalten

10. Leerer Zustand: erste Anmeldung, keine Daten.
11. Ein Datensatz — und mehrere hundert. Wird es langsam?
12. Ganz falsche Eingabe: Text im Zahlenfeld, negative Werte, Datum 1900.
13. Doppelt schnell hintereinander auf „Speichern" geklickt.
14. Seite mitten im Vorgang neu geladen.
15. Theme umschalten — bleibt die Wahl nach dem Neuladen erhalten?
16. Abmelden und als anderer Nutzer anmelden — sieht man wirklich nur die
    eigenen Daten?
17. Mit der Tastatur durch die ganze Seite, ohne Maus. Ist die
    Reihenfolge sinnvoll?

## 15. Datenverlust ist die einzige echte Katastrophe

- Löschen fragt nach — bei mehreren Datensätzen mit Nennung der Anzahl.
- Wo möglich: erst als gelöscht markieren, später endgültig entfernen.
- Vor Migrationen, die Daten verändern, weist das Tool auf die Sicherung
  hin — und zwar **vor** der ersten Änderung, danach wäre der Hinweis
  wertlos. Dazu gehören zwei weitere Schritte, die in
  `prolo-betriebsregeln.md` Abschnitt 19a ausgeführt sind: eine **Kopie** des
  bisherigen Stands als Rückweg, und alle Änderungen in einer
  **Transaktion**. Eine bestehende Kopie wird dabei nicht überschrieben —
  sonst ersetzt ein zweiter, ebenfalls gescheiterter Lauf den einzigen
  brauchbaren Stand.
- Ein Import kann rückgängig gemacht werden. Dafür bekommt jeder
  Datensatz das Feld `quelle` mit Importlauf und Zeilennummer.

---

# TEIL III — DAMIT ES SPASS MACHT

Die Punkte, die den Unterschied zwischen „funktioniert" und „benutze ich
gern" ausmachen:

- **Der häufigste Fall ist am schnellsten.** Tanken eintragen passiert
  hundertmal — das darf nicht vier Klicks tief liegen.
- **Mitdenken statt abfragen.** Datum auf heute vorbelegen, Fahrzeug auf
  das zuletzt benutzte, Kilometerstand mit dem letzten bekannten Wert als
  Hinweis.
- **Nichts verlangen, was schon bekannt ist.** Wenn Preis pro Liter und
  Menge dastehen, wird der Betrag gerechnet, nicht abgefragt.
- **Eingaben überleben Fehler.** Wer ein langes Formular ausfüllt und
  einen Fehler macht, darf nicht von vorn anfangen.
- **Zahlen kommentieren sich selbst.** „7,4 l/100 km" ist eine Zahl.
  „7,4 l/100 km — 0,3 weniger als im Schnitt" ist eine Information.
- **Leere Zustände erklären, was zu tun ist**, statt nur leer zu sein.
- **Keine Überraschungen.** Gleiche Geste, gleiche Wirkung — in jedem
  Tool.

---

# TEIL IV — CHECKLISTE

**Design**
- [ ] Tool-Logo oben links nach dem Muster aus Abschnitt 5
- [ ] Nur Token aus Abschnitt 2. Text auf `--accent` läuft über
      `--on-accent`, nicht über ein hartes `#fff` — erlaubt bleibt es, aber
      als Token ist es an einer Stelle änderbar
- [ ] Höchstens eine `--feature`-Fläche, ein Primärbutton pro Screen
- [ ] Sora / Instrument Sans / JetBrains Mono korrekt eingesetzt
- [ ] Karten ohne Schatten, Schatten nur am Fenster
- [ ] Inhaltsbereich auf `max-width:1280px` begrenzt und zentriert
- [ ] Keine halbleeren Rasterzeilen
- [ ] Zahlen deutsch formatiert, Einheiten korrekt

**Einstellungsseite**
- [ ] Seite `/einstellungen` vorhanden, aus Navigation erreichbar
- [ ] Theme-Umschalter System / Hell / Dunkel, pro Nutzer gespeichert
- [ ] Tool-Optionen mit je einer Zeile Erklärung
- [ ] Knopf „Abmelden / neu laden" mit Erklärung, Ziel `sign_out`
- [ ] Im Header nur der Anzeigename als Verweis auf die Einstellungen

**Bedienbarkeit**
- [ ] Zustandsblock aus 8.1 vorhanden (Fokus, Bewegungsreduzierung)
- [ ] Alles mit Tastatur erreichbar, Fokusrahmen sichtbar
- [ ] Ab 360 px ohne seitliches Scrollen bedienbar
- [ ] Touchziele mindestens 44 px
- [ ] Kontrast geprüft (4.5:1 / 3:1), auch auf `--feature`
- [ ] Jede Aktion gibt sichtbare Rückmeldung

**Robustheit**
- [ ] Alle Eingaben geprüft, keine stillen Vorgabewerte
- [ ] Zusammengehörende Schreibvorgänge in Transaktionen
- [ ] Fachlogik hat Tests mit handgerechneten Werten
- [ ] Gegenprobe vorhanden (13a) und **alle** eingebauten Fehler werden
      gefunden
- [ ] Kein Erwartungswert, der bei zwei Verfahren gleich herauskommt
- [ ] Geldbeträge nicht als Fließkommazahl
- [ ] Löschen fragt nach
- [ ] Die neun Punkte aus 14a **einzeln durchgesehen**, in beiden Themen
      und bei drei Breiten
- [ ] Die acht Punkte aus 14b tatsächlich ausprobiert

**Spaß**
- [ ] Häufigster Arbeitsablauf in möglichst wenigen Schritten
- [ ] Sinnvolle Vorbelegungen
- [ ] Eingaben gehen bei einem Fehler nicht verloren
- [ ] Leere Zustände erklären den nächsten Schritt
