# Wiki einhängen

Ablauf nach Betriebsregeln Abschnitt 7. Dauert etwa zwanzig Minuten.

## 1. DNS

Bei IONOS einen A-Record `wiki` auf die Server-IP. **Keinen AAAA-Record**,
oder auf die IPv6 des Servers zeigen lassen — sonst scheitert die
Zertifikatsausstellung.

## 2. Dateien ablegen

```bash
sudo mkdir -p /opt/stack/wiki
cd /opt/stack/wiki
sudo tar xzf /tmp/wiki.tar.gz
sudo cp .env.beispiel .env
sudo nano .env          # WIKI_ADMIN_NUTZER auf deinen Anmeldenamen setzen
```

Der Eintrag `WIKI_ADMIN_NUTZER` ist nur der Notnagel für den ersten Start.
Sobald die Gruppe in Authentik steht, wird er geleert.

## 3. `.gitignore` ergänzen

Betriebsregeln Abschnitt 10 verlangt das **im selben Arbeitsschritt**. Das
Wiki legt eine neue Art von Daten ab:

```
wiki/schriften/*.woff2
```

Die Seiten selbst liegen im Volume, nicht im Ordner — da ist nichts zu
ergänzen. Die Schriften sind nur lizenzrechtlich besser außen vor.

## 4. Starten

```bash
sudo docker compose up -d --build
sudo docker compose logs -f       # "Prolo Wiki laeuft auf Port 8080"
```

## 5. Authentik

1. **Anwendungen → Anwendungen → Erstellen**
   Name `Wiki`, Slug `wiki`, Provider `forward-auth-domain`.
2. **Anwendungen → Outposts → authentik Embedded Outpost → Bearbeiten**
   → Wiki mit auswählen.
   *Der Schritt, der am häufigsten vergessen wird. Äußert sich als
   „Not Found" von Authentik.*
3. **Verzeichnis → Gruppen → Erstellen**: `wiki-admin`. Dich selbst
   hineinlegen. Wer in dieser Gruppe ist, darf Seiten einspielen.
4. Weitere Gruppen nach Bedarf, benannt nach Thema statt nach Person:
   `wiki-technik`, `wiki-arbeit`.

Danach in `.env` `WIKI_ADMIN_NUTZER` leeren und
`sudo docker compose up -d` — ab jetzt hängen die Rechte nur noch an
Authentik.

## 6. Prüfen

```bash
# Von außen: Anmelde-Weiterleitung muss kommen
curl -sI https://wiki.prolo.me | head -3

# Intern: Lebendpruefung ohne Anmeldung
sudo docker run --rm --network proxy curlimages/curl:latest \
  -sf http://wiki:8080/gesundheit && echo OK
```

Dann `https://wiki.prolo.me` im Browser öffnen, `test-seite.html` in die
Verwaltung ziehen, übernehmen, suchen.

## 7. Sicherung und Aktualisierung einmal durchlaufen lassen

```bash
sudo /opt/stack/backup.sh
ls -la /opt/backups/$(date +%F)/wiki/

sudo /opt/stack/aktualisieren.sh wiki
```

Und den Rückweg testen, bevor echte Inhalte drin sind — der letzte Punkt
der Checkliste, und der einzige, der zählt:

```bash
cd /opt/stack/wiki
sudo docker compose down
sudo docker volume rm wiki_wiki_seiten wiki_wiki_daten
sudo docker compose up -d
# leeres Wiki -> Sicherung einspielen:
sudo docker run --rm -v wiki_wiki_seiten:/daten \
  -v /opt/backups/<datum>/wiki:/backup alpine \
  sh -c "rm -rf /daten/* && tar xzf /backup/wiki_wiki_seiten.tar.gz -C /daten"
sudo docker run --rm -v wiki_wiki_daten:/daten \
  -v /opt/backups/<datum>/wiki:/backup alpine \
  sh -c "rm -rf /daten/* && tar xzf /backup/wiki_wiki_daten.tar.gz -C /daten"
sudo docker compose up -d
```

Geht beim Index etwas schief, ist das nicht schlimm: In der Verwaltung
baut *Index neu* ihn aus den Seiten wieder auf. Die Seiten selbst sind
das, was nicht verloren gehen darf.

---

# Wie eine Seite aussehen muss

Jede Seite ist eine eigenständige HTML-Datei mit drei Pflichtteilen.
`test-seite.html` zeigt alle drei im Zusammenhang.

## 1. Der Meta-Block

Steht im `<head>` und ist das, woraus Wiki Baum, Suche und Freigabe baut:

```html
<script type="application/json" id="wiki-meta">
{
  "slug": "subnetze",
  "titel": "Subnetze",
  "kurz": "Netzmaske, Präfix und wie man Adressbereiche teilt.",
  "pfad": ["Technik", "Netzwerke"],
  "gruppen": [],
  "stand": "2026-09-14",
  "abschnitte": [
    { "anker": "maske",
      "titel": "Subnetzmaske und Präfix",
      "stichworte": ["Netzmaske", "CIDR", "Präfixlänge"],
      "text": "Die Subnetzmaske trennt die Adresse in Netzanteil und ..." }
  ]
}
</script>
```

| Feld | Bedeutung |
|---|---|
| `slug` | Kennung und Adresse. Kleinbuchstaben, Ziffern, Bindestriche |
| `pfad` | Ort im Themenbaum. Der Baum entsteht daraus von selbst |
| `gruppen` | Leer = alle Angemeldeten. Sonst Authentik-Gruppennamen |
| `abschnitte[].anker` | Muss als `id=` im HTML existieren — dorthin springt die Suche |
| `abschnitte[].text` | Der Suchstoff. Auch Inhalte, die im JS stecken |

Der letzte Punkt ist der wichtige: Bei deiner Netzwerk-Seite stehen
Glossar, Portverzeichnis und TCP-Schritte in JavaScript. Ein Indexer, der
nur den sichtbaren Text liest, findet davon nichts. Was im `text` steht,
ist auffindbar — unabhängig davon, wo es auf der Seite herkommt.

## 2. Der Empfänger für Suchsprünge

Die Shell schickt der Seite nach dem Laden, wohin gesprungen werden soll
und was zu markieren ist. Ohne diesen Block landet ein Suchtreffer oben
auf der Seite statt an der Fundstelle. Der fertige Block steht in
`test-seite.html` und kann unverändert übernommen werden.

```js
window.addEventListener('message', function(e){
  /* Die Seite laeuft in einem opaken Origin - location.origin ist "null"
     und taugt nicht als Vergleich. Geprueft wird das Elternfenster. */
  if(e.source !== window.parent || !e.data) return;
  if(e.data.typ === 'wiki-springen') springen(e.data.anker, e.data.begriff);
  if(e.data.thema) document.body.dataset.theme = e.data.thema;
});
window.parent.postMessage({typ:'wiki-bereit'}, '*');
```

Zwei Dinge daran sind leicht zu übersehen und stecken darum fertig in
`test-seite.html` (Befunde N-06 und N-07):

- **Das Thema gilt ab der ersten Zeile.** Die Nachricht der Hülle kommt
  erst nach dem ersten Anstrich — gemessen 10 ms danach. Wer nur
  `<body data-theme="dark">` schreibt, lässt bei hellem Wiki jedes Mal
  kurz die dunkle Fassung aufblitzen. Darum setzt der Block das Thema
  zuerst selbst aus `prefers-color-scheme`.
- **Der Textdurchlauf lässt `script` und `style` aus.** Ein `TreeWalker`
  mit `SHOW_TEXT` läuft auch durch Skriptkommentare. Eine Marke darin hat
  kein Layout, `scrollIntoView` tut dann nichts, und der Suchtreffer landet
  oben auf der Seite statt an der Fundstelle. Der `acceptNode` im Block
  verhindert das.

Seiten mit umgeschalteten Bereichen — so wie deine Netzwerk-Seite, wo
alle Abschnitte `display:none` sind — müssen in `springen()` zusätzlich
den richtigen Bereich öffnen, bevor sie scrollen.

## 3. Tokens und Zustandsblock

Farben nur über die Tokens aus Regelblatt Abschnitt 2, dazu der
Pflichtblock aus 8.1 (`focus-visible`, `prefers-reduced-motion`). Der
Import prüft beides und meldet, was fehlt.

---

# Was die Hülle beim Lesen anbietet

- **Merken** im Kopf legt die Seite auf die Übersicht. Nochmal drücken nimmt
  sie wieder weg.
- **Auf dieser Seite** — in der Seitenleiste über dem Themenbaum — springt zu
  einem Abschnitt, ohne die Seite neu zu laden. Erscheint ab zwei
  Abschnitten; die Anker kommen aus dem Meta-Block, der offene Abschnitt ist
  markiert.
- **Bearbeiten** öffnet den Editor. Sichtbar für den Urheber der Seite und
  für Verwalter.

## Ein PDF anhängen

Im Editor der Baustein **PDF**:

1. *Datei auswählen* — das PDF wird beim Speichern ein **Anhang** dieser Seite.
2. **Sprungziele** eintragen: Beschriftung und Seitenzahl, eine Zeile je Ziel.
   Bei einem Handbuch mit 200 Seiten ist das der eigentliche Nutzen.
3. Speichern. Die Knöpfe öffnen das PDF rechts neben dem Text, auf der
   genannten Seite.

Wichtig zum Verständnis, falls du eigene Seiten von Hand schreibst: **Die
Seite selbst darf kein PDF anzeigen.** Sie läuft in einem abgeschotteten
Rahmen, dessen Regeln `frame-src 'none'` und `object-src 'none'` setzen — das
ist die Grenze, die eine eingespielte Seite vom Rest des Wikis trennt. Statt es
selbst zu versuchen, bittet die Seite die Hülle:

```html
<button data-wiki-pdf="anhang-handbuch" data-wiki-seite="10">Kapitel 1</button>
```

`data-wiki-pdf` ist die Kennung des Skriptblocks, in dem das PDF eingebettet
war; der Pflichtteil liest daraus den echten Anhangsnamen und schickt die
Nachricht `wiki-pdf` an die Hülle. Der Anhang selbst liegt unter
`/seite/<kennung>/anhaenge/<datei>`, und die Hülle hängt `#page=N` an.

Ein PDF-Anhang wird außerdem **seitenweise durchsuchbar** (dafür braucht der
Container `pdftotext`, das Abbild bringt es mit). Ein Suchtreffer aus dem PDF
öffnet die Seite und das PDF auf der Fundstelle.

## Gruppen im Inhaltsverzeichnis

Jeder Abschnitt kann eine **Gruppe** tragen. Abschnitte mit derselben Gruppe
stehen links unter einer gemeinsamen Überschrift:

```
Netzwerk-Grundlagen          ← Titel der Seite
Schichten, Adressen, Ports   ← der Satz darunter

GRUNDLAGEN
  Schichten und Kapselung
  Latenz und Durchsatz
ADRESSIERUNG
  IP-Adressen und Subnetze
  Namen und DNS
```

Im Editor steht das Feld unter *Mehr zu diesem Abschnitt*. Die Reihenfolge der
Gruppen ist die Reihenfolge der Abschnitte — nicht alphabetisch, denn die
Reihenfolge ist eine Aussage des Autors. Im Meta-Block ist es ein Feld je
Abschnitt:

```json
{ "anker": "adressen", "titel": "IP-Adressen und Subnetze",
  "gruppe": "Adressierung", "text": "…" }
```

Eine Gruppe ist außerdem **durchsuchbar**: „Adressierung" findet die Seite und
springt an den Abschnitt.

## Was die Suche findet

Der Index hat fünf Quellen, und die Reihenfolge ist Absicht:

| Quelle | Woher |
|---|---|
| Seitenkopf | Titel, der Satz darunter, der Pfad, die Gruppen des Verzeichnisses, die Adresse, alle Abschnittstitel |
| Abschnitte | `abschnitte[].text`, `stichworte` und `gruppe` aus dem Meta-Block |
| Seitentext | der sichtbare Text im HTML |
| gemeldeter Text | was die Seite nach dem Laden selbst meldet — genau das, was der Leser sieht |
| Skripttext | Zeichenketten aus den Skriptblöcken, wenn die Seite nichts gemeldet hat |

Der **Seitenkopf** ist die Quelle für alles, was eine Seite *beschreibt*.
Ohne ihn ist sie nur über ihren Inhalt zu finden: „Haushalt" (steht nur im
Pfad), „Grundlagen" (nur eine Gruppe) oder der erste Satz der Seite ergaben
nichts. Gezeigt wird als Schnipsel trotzdem der Satz der Seite — gefunden
wird mit allem, gelesen wird, was ein Mensch lesen will.

Ein **leeres Suchfeld** listet alle Seiten, die du sehen darfst. Das ist der
Weg, wenn man das Wort nicht kennt.

Die dritte Quelle ist der Grund, warum eine Seite, die ihre Tabellen erst im
Browser aufbaut, überhaupt durchsuchbar ist: **der Server kann kein
JavaScript.** Dafür trägt der Pflichtteil drei Zeilen, die nach dem Laden
`document.body.innerText` an die Hülle schicken; gleicher Text löst keinen
Indexlauf aus.

Für Seiten ohne den aktuellen Pflichtteil springt die vierte Quelle ein: die
Zeichenketten der Skripte, gefiltert um alles, was nach Code aussieht. Grob,
aber sofort da — nach einem **Index neu** in der Verwaltung findet die Suche
auch dort.

---

# Seiten im Wiki selbst schreiben

Für alles, was keine eigene Gestaltung braucht, gibt es den **Editor** —
kein HTML, keine Datei, kein Editor auf dem Rechner:

**Neue Seite** in der Seitenleiste, oder bei einer offenen Seite
**Bearbeiten** im Kopf. Beides gibt es nur für Verwalter, weil Speichern
dieselbe Berechtigung braucht wie Einspielen.

Eingetragen werden Titel, Kennung, Ort im Themenbaum und die Abschnitte.
Kennung und Anker schlägt der Editor aus dem Titel vor, solange man sie
nicht selbst anfasst.

## Wer darf was

| Wer | Darf | Gruppe |
|---|---|---|
| jeder Angemeldete | lesen, was für ihn freigegeben ist; suchen; Merkzettel setzen | — |
| **Editor** | Seiten anlegen; eigene Seiten ändern, zurücksetzen, löschen; Freigabe setzen, aber nur auf **eigene** Gruppen | `wiki-editor` |
| **Verwalter** | alle Seiten sehen und ändern; Freigabe je Seite setzen; Themenzweige freigeben; Index neu bauen | `wiki-admin` |

Ein Verwalter ist immer auch Editor. Die Gruppennamen sind einstellbar:

```yaml
environment:
  WIKI_EDITOR_GRUPPE: wiki-editor     # Vorgabe
  WIKI_ADMIN_GRUPPE: wiki-admin       # Vorgabe
  WIKI_GRUPPEN_PRAEFIX: wiki          # Vorgabe
```

**Das Wiki beachtet nur Gruppen, die mit `wiki` anfangen.** In Authentik hängen
an einem Nutzer die Gruppen aller Werkzeuge; `vertrieb` oder `bordbuch-admin`
entscheiden hier nichts. Eine Freigabe auf eine Gruppe ohne dieses Präfix wird
abgewiesen — sie würde die Seite allen wegnehmen und niemandem geben. In den
Einstellungen steht, wie viele Gruppen aussortiert wurden.

„Eigene Seite" heißt: die, die man **angelegt** hat — nicht die, die man
zuletzt gespeichert hat. Der Unterschied ist wichtig: Wenn du als Verwalter
eine fremde Seite aufräumst, bleibt sie die Seite ihres Urhebers, und er kann
sie weiter ändern. Die Verwaltung zeigt in der Spalte *Von* den Urheber; wer
zuletzt gespeichert hat, steht als Hinweis am Namen.

Wer eine fremde Seite überschreiben will, bekommt eine klare Absage mit dem
Namen des Urhebers — und den Vorschlag, eine eigene Kennung zu nehmen.

Die Freigabe einer Seite ändert der Verwalter in der Verwaltung mit einem
Klick auf die Freigabe-Spalte. Geschrieben wird beides: die Datenbank, die
über die Sichtbarkeit entscheidet, und der Meta-Block der Datei — sonst
dreht das nächste Bearbeiten durch den Urheber die Freigabe zurück.

## Die Auszeichnung

Absichtlich klein — die Liste im Editor unter *Wie schreibe ich hier?* ist
vollständig:

| Eingabe | Ergebnis |
|---|---|
| Leerzeile | neuer Absatz |
| `## Titel` | Zwischentitel |
| `- Punkt` | Aufzählung |
| `1. Punkt` | nummerierte Liste |
| `**fett**` | hervorgehoben |
| `` `Befehl` `` | Code im Text |
| ` ``` ` … ` ``` ` | Codeblock |
| `> Text` | blauer Merkkasten |
| `!> Text` | gelber Warnkasten |
| `?> Text` | grüner Kasten |
| `\| A \| B \|` | Tabelle, zweite Zeile `\|---\|---\|` |
| `[[kennung]]` | Verweis auf eine andere Wiki-Seite |

Getippter Text wird immer zuerst geschützt: Wer `<script>` schreibt, sieht
`<script>` auf der Seite stehen. Ein Verweis wird ein Knopf, der die Hülle
bittet, die Seite zu öffnen — kein `href`, weil eine Seite im Rahmen nicht
selbst navigieren darf.

## Bausteine

Unter jedem Textfeld steht ein Kasten mit Bausteinen. Ein Klick setzt die
Vorlage an der Schreibmarke ein; danach füllt man sie wie normalen Text aus.
Der Aufbau ist immer gleich:

```
:::art Titel
Zeile
Zeile
:::
```

| Baustein | Was daraus wird | Zeilenform |
|---|---|---|
| `:::rechner` | Felder, Formel, Ergebnis — rechnet im Browser | `Name = Startwert`, dann `= Formel`, dazu `Einheit: €` |
| `:::schritte` | nummerierte Abfolge | `Titel \| Erklärung` |
| `:::kennzahlen` | Werte groß nebeneinander | `Name \| Wert \| Zusatz` |
| `:::gegenueber` | zwei bis vier Seiten nebeneinander | `Titel \| Inhalt` |
| `:::begriffe` | Wort und Erklärung als Tabelle | `Wort \| Erklärung` |
| `:::klapp` | Überschrift, die man aufklappt | normaler Text |

Der **Rechner** nimmt die Feldnamen aus dem ersten Wort jeder Feldzeile. Aus

```
:::rechner Stromkosten je 100 km
Verbrauch in kWh/100 km = 18
Preis je kWh in Euro = 0,32
= Verbrauch * Preis
Einheit: €
:::
```

wird ein Kasten mit zwei Eingabefeldern und einem Ergebnis, das sich beim
Tippen mitrechnet. Gerechnet wird von einem eigenen kleinen Rechenwerk —
**kein `eval`**: es kennt Zahlen, Feldnamen und `+ - * / ( )`, und alles
andere ergibt „keine Zahl". Ein Feld mit Text wird markiert, Teilen durch
Null ergibt „—".

Ein unbekannter Baustein wird nicht verschluckt, sondern als Warnkasten mit
seinem Inhalt gezeigt.

## Was der Editor erzeugt

Eine gewöhnliche Wiki-Seite. Sie geht durch dieselbe Prüfung wie eine
eingespielte Datei (*Prüfen und ansehen* legt die Vorschau an, *Speichern*
übernimmt), bekommt Fassungen und Rücksprung, und lässt sich über
*Als HTML-Datei laden* auch herausnehmen und woanders einspielen.

Die getippte Quelle steht im Meta-Block je Abschnitt unter `markup`. Nur
deshalb lässt sich eine Seite später wieder aufklappen und weiterschreiben.
Unter `text` steht wie gehabt der Suchstoff — dort ohne Auszeichnung.

Eine Seite, die **nicht** aus dem Editor kommt, lässt sich trotzdem öffnen.
Der Editor sagt dann deutlich, dass Speichern die eigene Gestaltung durch
die Standardgestaltung ersetzt; Text und Abschnitte bleiben, eigenes HTML
und eigene Skripte nicht. Die alte Fassung bleibt über *Fassungen*
erreichbar.

---

# Einspielen

Verwaltung → Datei hineinziehen. Was dann passiert:

1. **Geprüft.** Fehler verhindern die Übernahme und stehen im Klartext da:
   fehlender Meta-Block, doppelte Anker, externe Verweise, ein Titel über 120
   Zeichen — und seit `N-23` auch ein `<body>` ohne sichtbaren Text. Hinweise
   verhindern nichts, werden aber an der Seite vermerkt.
   Ist der Meta-Block lesbar, steht neben den Fehlern **In den Editor laden**:
   Der Editor baut Gestaltung, Pflichtteil und Farben selbst neu und räumt
   damit genau diese Fehler auf.
2. **Anhänge ausgelagert.** Base64-Blöcke über 200 kB werden Dateien. Bei
   PDFs wird zusätzlich der Text seitenweise indexiert — ein Suchtreffer
   nennt dann die Seitenzahl im Dokument.
3. **Vorschau.** Ansehen, bevor es zählt.
4. **Übernehmen.** Die bisherige Fassung wandert ins Archiv, Rücksprung
   per Klick.

Gleiche `slug` noch einmal einspielen heißt: Seite ersetzen. Neue `slug`
heißt: neue Seite. Mehr Regeln gibt es nicht.

## Eine Seite von einer KI schreiben lassen

Im Editor unter **Eine KI schreiben lassen** steht ein Prompt zum Kopieren.
Thema eintippen, *Prompt kopieren*, in die KI einfügen — sie antwortet mit
einer HTML-Datei.

Der Prompt verlangt **keine fertige Seite**, sondern einen Entwurf: Meta-Block
mit Titel, Pfad, Abschnitten und deren Markup, und ein leerer Körper. Das ist
Absicht:

- Gestaltung, Pflichtteil, Farbtokens und CSP-Regeln macht der **Editor**. Sie
  müssen stimmen, und eine KI, die 300 Zeilen CSS nachbaut, trifft sie
  irgendwann nicht mehr.
- Ein Meta-Block ist kurz genug, um richtig zu sein. Der Prompt ist deshalb
  rund 5,8 kB statt 40.

Der Weg danach, vier Klicks:

1. Editor → **Ich habe schon eine HTML-Datei** → Datei wählen.
2. Die Prüfung sagt *Nicht übernehmbar* — richtig, der Entwurf ist noch keine
   Seite (`N-23`). Darunter steht **In den Editor laden**.
3. Der Editor ist gefüllt: Titel, Pfad, Kennung, Satz, alle Abschnitte mit
   Gruppen und Stichworten, das Markup als Blöcke mit lebender Vorschau.
4. **Speichern.** Erst jetzt entsteht die richtige Seite.

Ein PDF kann die KI nicht mitschicken. Der Prompt lässt sie deshalb nur den
Baustein mit den Sprungzielen schreiben:

```
:::pdf Handbuch des Herstellers
datei: handbuch
Einrichtung | 12
Fehlersuche | 88
:::
```

Die Datei wählst du danach im PDF-Baustein mit einem Klick aus. Ohne Datei
lässt der Editor nicht speichern (`N-22`) — ein PDF-Knopf ohne PDF wäre ein
Klick ins Leere.

Zwei Regeln, die der Prompt mitgibt und die auch für Seiten von Hand gelten:

- `werkzeug` muss genau `editor-1` sein. Steht dort etwas anderes, hält der
  Editor die Datei für eine fremde Seite und wirft ihr Markup weg.
- Abschnitte derselben Gruppe müssen **direkt aufeinander folgen**, sonst
  steht die Überschrift links zweimal (`N-24`).

## Fertige Seiten im Repository

Unter `wiki/vorlagen/` liegen fertige Seiten, die nur noch eingespielt werden
müssen:

| Datei | Slug | Ort im Baum | Inhalt |
|---|---|---|---|
| `git-und-github.html` | `git-und-github` | Technik › Werkzeuge | Git von vorn: die vier Orte, die fünf Befehle des Alltags, Zweige und Pull Requests, der Weg vom Zweig auf den Server, die häufigen Fehler, Kurzreferenz |

Einspielen wie jede andere Datei: Verwaltung → Datei hineinziehen. Auf dem
Arbeitsrechner liegt sie unter `wiki/vorlagen/`, auf dem Server unter
`/opt/stack/wiki/vorlagen/` — von dort herunterladen oder direkt aus dem
Repository nehmen.

## Was noch fehlt

- Ein Skill, der ganze Seitenreihen auf einmal erzeugt. Fuer eine einzelne
  Seite gibt es jetzt den Prompt im Editor (siehe oben).
- Weitere Bausteine: Bild mit Beschriftung, Ablaufdiagramm, Zeitleiste,
  Tabelle mit Summenzeile. Der Aufbau (`:::art`) trägt beliebig viele; jeder
  neue Baustein ist eine Funktion in `edBaustein()` plus ein Eintrag in
  `ED_BAUSTEINE`.
- Anhänge (Bilder, PDFs) kann der Editor noch nicht aufnehmen. Wer sie
  braucht, spielt eine Datei ein.
- Die Netzwerk-Seite selbst: Tokens, Zustandsblock und das Nachladen des
  Kompendiums über `data-wiki-anhang` statt aus dem eingebetteten Block.
