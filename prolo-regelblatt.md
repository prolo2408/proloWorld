# Prolo — Regelblatt für Oberflächen und Codequalität

Diese Datei an Claude geben, wenn eine neue Prolo-Anwendung, ein neuer
Screen oder ein Umbau ansteht. Sie ist verbindlich.

Begleitdatei: `regeln-neue-tools.md` regelt Infrastruktur, Anmeldung,
Sicherung und schützenswerte Daten. Diese hier regelt Aussehen, Qualität
und Bedienung.

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
Sidebar 248 px (`--chrome`): Logo-Kachel 28 px + Wortmarke, Navigation mit
44-px-Zeilen und 4-px-Aktivstrich, unten nur „Einstellungen".
Header 76 px: links Titel + Kontextzeile, rechts Kontext-Auswahl (z. B.
Fahrzeug), Zeitraum-Segment, Thema-Umschalter, Primärbutton.
Inhalt: KPI-Reihe (4 Spalten), darunter Raster `1.55fr / 1fr` — links
Diagramm und Tabelle, rechts schmale Karten.

**Handy (390 × 844)**
Statusleiste, Kopf mit Monatslabel + Titel + Kontextchip, Inhalt
(Hero-Kennzahl in `--feature`, Diagramm, Liste), Primärbutton über der
Tabbar, Tabbar mit 4 Einträgen und 3-px-Aktivstrich.

Kontextobjekte (Fahrzeug, Konto, Projekt) gehören in den Header bzw.
Kopfbereich, nicht in die Sidebar-Fußzeile.

**Anmeldung — überall gleich:** Rechts im Header (Desktop) bzw. im
Kopfbereich (Handy) stehen der Anzeigename des angemeldeten Nutzers und
der Abmelden-Knopf. Der Knopf zeigt auf
`/outpost.goauthentik.io/sign_out` — ein lokales Löschen von Cookies
reicht nicht, die Sitzung liegt bei Authentik. Gleiche Position in jedem
Tool, damit man nicht suchen muss.

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

## 14. Was durchprobiert sein muss

Ein Tool gilt erst als fertig, wenn diese Fälle **tatsächlich ausprobiert**
wurden — nicht nur gedanklich:

1. Leerer Zustand: erste Anmeldung, keine Daten. Sieht das gut aus oder
   ist es eine leere Fläche?
2. Ein Datensatz — und mehrere hundert. Wird es langsam?
3. Ganz falsche Eingabe: Text im Zahlenfeld, negative Werte, Datum 1900.
4. Doppelt schnell hintereinander auf „Speichern" geklickt.
5. Seite mitten im Vorgang neu geladen.
6. Abmelden und als anderer Nutzer anmelden — sieht man wirklich nur die
   eigenen Daten?
7. Am Handy im Hochformat, bei 360 px Breite.
8. Mit der Tastatur durch die ganze Seite, ohne Maus.
9. Hell- und Dunkelmodus, beide vollständig durchgesehen.

## 15. Datenverlust ist die einzige echte Katastrophe

- Löschen fragt nach — bei mehreren Datensätzen mit Nennung der Anzahl.
- Wo möglich: erst als gelöscht markieren, später endgültig entfernen.
- Vor Migrationen, die Daten verändern, weist das Tool auf die Sicherung
  hin.
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
- [ ] Nur Token aus Abschnitt 2, kein einziger direkter Farbwert
- [ ] Höchstens eine `--feature`-Fläche, ein Primärbutton pro Screen
- [ ] Sora / Instrument Sans / JetBrains Mono korrekt eingesetzt
- [ ] Karten ohne Schatten, Schatten nur am Fenster
- [ ] Hell- und Dunkelmodus beide vollständig durchgesehen
- [ ] Zahlen deutsch formatiert, Einheiten korrekt
- [ ] Kopfbereich mit Nutzername und Abmelden-Knopf

**Bedienbarkeit**
- [ ] Zustandsblock aus 8.1 vorhanden (Fokus, Bewegungsreduzierung)
- [ ] Alles mit Tastatur erreichbar, Fokusrahmen sichtbar
- [ ] Ab 360 px ohne seitliches Scrollen bedienbar
- [ ] Touchziele mindestens 44 px
- [ ] Kontrast geprüft (4.5:1 / 3:1)
- [ ] Jede Aktion gibt sichtbare Rückmeldung

**Robustheit**
- [ ] Alle Eingaben geprüft, keine stillen Vorgabewerte
- [ ] Zusammengehörende Schreibvorgänge in Transaktionen
- [ ] Fachlogik hat Tests mit handgerechneten Werten
- [ ] Geldbeträge nicht als Fließkommazahl
- [ ] Löschen fragt nach
- [ ] Die neun Fälle aus Abschnitt 14 tatsächlich durchprobiert

**Spaß**
- [ ] Häufigster Arbeitsablauf in möglichst wenigen Schritten
- [ ] Sinnvolle Vorbelegungen
- [ ] Eingaben gehen bei einem Fehler nicht verloren
- [ ] Leere Zustände erklären den nächsten Schritt
