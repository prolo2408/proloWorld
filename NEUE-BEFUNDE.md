# Neue Befunde aus der Abarbeitung des Prüfberichts

**Stand:** 15.09.2026
**Anlass:** Regel 4 des Prüfberichts — „Wenn beim Bearbeiten eines Befunds ein
weiteres Problem auffällt, wird es als neuer Befund notiert und getrennt
bearbeitet."

Diese Punkte sind beim Abarbeiten von `B-01` bis `B-49` aufgefallen und stehen
**nicht** im ursprünglichen Bericht. Sie sind bewusst **nicht** stillschweigend
mitbehoben worden. Nummerierung `N-01` aufwärts, damit es keine Verwechslung
mit den `B`-Nummern gibt.

---

## N-01 — Das Wiki kennt `--danger`, `--on-accent` und `--overlay` nicht

**Stufe:** niedrig
**Datei:** `wiki/index.html`, Tokenblock
**Gefunden bei:** B-30 Teil 2

Mit B-30 sind die drei Token in die Regeldatei aufgenommen worden, weil das
Bordbuch sie sinnvoll ergänzt hatte. Das Wiki definiert sie nicht — geprüft:
alle drei fehlen im Tokenblock.

Das ist kein rein theoretischer Punkt:

- Das Wiki hat **zerstörende Aktionen** (Seite löschen, Fassung
  zurücksetzen). Ohne `--danger` sehen sie aus wie gewöhnliche Knöpfe oder
  wie eine Warnung — CLAUDE.md §2 unterscheidet beides bewusst.
- Es stehen **vier hartkodierte `#fff`** in der Datei. CLAUDE.md §1 erlaubt
  `#fff` ausdrücklich nur als Text auf `--accent`. Ob alle vier dort stehen,
  ist nachzusehen; wenn ja, gehören sie auf `--on-accent`.

**Zu tun:** Die drei Token im Wiki ergänzen, die vier `#fff` prüfen und, wo
sie auf `--accent` stehen, durch `--on-accent` ersetzen. Die Löschknöpfe auf
`--danger` umstellen.

**Prüfen:** Bordbuch und Wiki nebeneinander, beide Themen. Ein Löschknopf muss
in beiden Tools gleich aussehen.

**Behoben.** Die drei Token stehen jetzt in beiden Themen des Wikis, wertgleich
zum Bordbuch (nachgemessen, alle sechs Werte identisch). Die beiden harten
`#fff` standen tatsächlich beide auf `--accent` und laufen jetzt über
`--on-accent`; übrig bleibt `--surface:#fff`, und das ist die Definition aus
der Regeldatei selbst. Löschen und Zurücksetzen tragen `gefahr` und färben sich
im Hover auf `--danger` — dieselbe Kette wie `.danger` im Bordbuch.

Eine Abweichung von der ursprünglichen Notiz: `--overlay` hat im Wiki **keine
Fundstelle**. Es gibt dort keinen eigenen Dialog, gefragt wird über `confirm()`.
Das Token ist trotzdem definiert, weil genau das sein in der Regeldatei genannter
Zweck ist — damit der nächste Dialog nicht sein eigenes `rgba(0,0,0,.5)`
erfindet. `--danger-soft` und `--on-overlay` sind **nicht** übernommen worden:
die sind Ergänzungen des Bordbuchs, stehen nicht in der Regeldatei und hätten hier
keine Verwendung.

---

## N-02 — Leerer Rumpf legt ein Auto mit dem Namen „Auto" an

**Stufe:** niedrig
**Datei:** `bordbuch/server.py`, `car_save()`
**Gefunden bei:** B-37/B-38

Ein `POST /api/cars/save` mit `Content-Length: 0` — also ganz ohne Inhalt —
antwortet mit `200` und legt ein Auto an, das „Auto" heißt. Nachgeprüft am
laufenden Server.

Der Grund ist die Vorbelegung in `car_save()`:
`name = (data.get("name") or "").strip()[:60] or "Auto"`. Für das Anlegen aus
dem Formular heraus ist diese Vorbelegung sinnvoll; für eine Anfrage ganz ohne
Inhalt ist sie eine stille Vorgabe im Sinne von CLAUDE.md §11 — nur an einer
Stelle, die B-05 nicht erfasst hat, weil dort Zahlen geprüft wurden und nicht
Text.

**Zu tun:** Entscheiden, ob ein Auto ohne Namen entstehen darf. Wenn nicht:
`name` als Pflichtfeld behandeln und `400` mit einer Meldung nach §7 liefern.
Wenn doch, bleibt es wie es ist — dann gehört ein Satz in den Code, warum.

**Prüfen:** `curl -X POST … -H "Content-Length: 0" …/api/cars/save` — die
Antwort muss zu der getroffenen Entscheidung passen.

**Behoben.** Entschieden wurde: **der Name ist Pflicht.** Ausschlaggebend war,
dass die Oberfläche ihn ohnehin schon selbst verlangt (`wizSpeichern` bricht mit
„Bitte gib dem Auto einen Namen." ab, bevor überhaupt gesendet wird). Der
Vorgabewert war also gar nicht aus dem Formular erreichbar, sondern nur über
einen direkten API-Aufruf — er hat nichts abgefangen und nur stille Daten
erzeugt.

Die Prüfung steckt jetzt in `pflicht_text()`, dem Gegenstück zu `pflicht_zahl`
und `pflicht_cent` aus B-05. Dass es die Funktion gibt, ist kein Selbstzweck:
so ist die Regel testbar, ohne einen HTTP-Server hochzufahren.

**Zweite Fundstelle, bewusst anders entschieden:** in `einspielen()`
(Wiederherstellung aus einer Sicherung) bleibt `or "Auto"` stehen. Dort werden
vorhandene Daten zurückgeholt; eine alte Sicherung mit einem namenlosen Auto
darf nicht dazu führen, dass die ganze Wiederherstellung abbricht. Ein Auto
namens „Auto" ist besser als die Tankungen, die daran hängen. Der Grund steht
jetzt als Satz im Code, wie es dieser Befund verlangt hat.

**Beim Schreiben aufgefallen:** ein erster Entwurf benutzte `data.get(feld) or ""`.
Damit wäre die Zahl `0` als *fehlender* Name durchgefallen, `911` dagegen nicht.
Behoben und als eigener Testfall festgehalten.

Geprüft: vier Fälle am laufenden Server (ohne Inhalt, nur Leerzeichen, mit
Namen, Ändern), Wiederherstellung mit namenlosem Auto geht weiter durch,
82 Tests grün, und die Gegenprobe findet beide eingebauten Rückbauten.

---

## N-03 — Der Vorab-Test im Bericht selbst funktioniert nicht

**Stufe:** mittel (betrifft das Regelwerk, nicht den Stack)
**Datei:** Prüfbericht, B-49, und `CLAUDE.md` §21
**Gefunden bei:** B-49 — **bereits behoben**, hier nur zur Kenntnis

Der im Bericht vorgeschlagene `pre-commit`-Haken benutzt `grep -PE`. Diese
Kombination gibt es nicht: grep meldet `conflicting matchers specified` und
tut daraufhin **gar nichts** — der Haken lässt jede Datei durch und meldet
Erfolg. Beim Einrichten ist mir das nur aufgefallen, weil ich ihn danach
tatsächlich ausprobiert habe; der erzeugte Fehl-Commit mit `wiki/wiki.db`
musste zurückgenommen werden.

Behoben in B-49 (`grep -P`, dazu `--diff-filter=ACM`, damit eine *gelöschte*
`.env` den Commit nicht blockiert). Steht hier, weil dieselbe Zeile in einem
anderen Zusammenhang wieder auftauchen könnte.

---

## N-04 — Eine `.pyc`-Datei liegt seit B-03 im Git

**Stufe:** niedrig
**Datei:** `wiki/__pycache__/server.cpython-311.pyc`
**Gefunden bei:** Abschlussvalidierung

`git status` war nach dem letzten Commit nicht sauber: eine übersetzte
Python-Datei meldete sich als geändert. Nachgesehen — sie ist **verfolgt**:

```
$ git log --oneline --diff-filter=A -- wiki/__pycache__/server.cpython-311.pyc
2343d81 B-03: Fremdherkunft verschaerft und Content-Type erzwungen
```

Sie ist mir in meinem eigenen B-03-Commit hineingerutscht, weil `wiki/.gitignore`
damals noch nicht existierte — die kam erst mit B-49. Seither ist sie in fünf
weiteren Commits stillschweigend mitgelaufen, weil sie sich bei jedem Serverlauf
ändert.

Der entscheidende Punkt: `__pycache__/` steht inzwischen in **allen drei**
`.gitignore`-Dateien. Das hat nichts geholfen — **`.gitignore` wirkt nicht auf
bereits verfolgte Dateien.** Eine vollständige Pflichtliste nach CLAUDE.md
§10 ist also keine Garantie für das, was schon im Git liegt.

Der Vorab-Test aus B-49 greift hier ebenfalls nicht: er prüft Namensmuster für
Geheimnisse und Datenbanken, nicht auf Bauartefakte.

**Behoben:** `git rm --cached` für die Datei; der Inhalt bleibt auf der Platte,
nur die Verfolgung endet.

**Prüfen:** `git ls-files | grep -E '__pycache__|\.pyc$'` gibt nichts mehr aus,
und `git status` bleibt nach einem Serverlauf sauber.

---

## N-05 — `cap_drop: ALL` nahm Traefik den Zugriff auf `acme.json`

**Stufe:** hoch (Ausfall nach außen)
**Datei:** `traefik/docker-compose.yml`
**Gefunden bei:** dem ersten echten Ausrollen auf dem Server, 15.09.2026
**Verursacht durch:** B-29 (Speicher-, Prozess- und Rechtegrenzen)

### Befund

Nach dem Ausrollen meldete der Browser bei `wiki.prolo.me` **„Nicht sicher"**
und zeigte als Zertifikat `CN=TRAEFIK DEFAULT CERT`. Im Protokoll:

```
ERR The ACME resolve is skipped from the resolvers list
    error="unable to get ACME account: open /letsencrypt/acme.json: permission denied"
WRN Unable to create access logger
    error="... /var/log/traefik/zugriff.log: permission denied"
```

Die Rechte auf dem Server:

```
-rw------- 1 prolo prolo 65868 acme.json
drwxrwxr-x 2 prolo prolo       log
```

Traefik läuft im Container als root. Normalerweise umgeht root jede
Dateirechteprüfung — über `CAP_DAC_OVERRIDE`. Genau die nimmt ihm aber das
mit B-29 eingeführte `cap_drop: ALL`. Ohne sie gelten für root die normalen
Rechtebits, und `acme.json` gehört `prolo` mit `600`.

**Was daran wichtig ist:** Es gab keinen Absturz und keine rote Meldung. Der
Container lief, das Aktualisierungsskript meldete `FERTIG. traefik laeuft.` —
richtig, denn es prüft den Containerzustand, und der war einwandfrei. Nur
lieferte Traefik ab diesem Moment sein selbst ausgestelltes Notzertifikat
aus, für **alle** Subdomains. Aufgefallen ist es erst, weil jemand die Seite
im Browser aufgerufen hat.

Auch die Einschätzung „die bestehenden Zertifikate laufen weiter, nur die
Erneuerung ist kaputt" war falsch: der Resolver wurde beim Start
**übersprungen**, Traefik kam also gar nicht erst an die gespeicherten
Zertifikate.

### Zu tun — erledigt

Eigentümerschaft geradeziehen, nicht die Fähigkeit zurückgeben:

```bash
sudo chown root:root /opt/stack/traefik/acme.json
sudo chmod 600      /opt/stack/traefik/acme.json
sudo chown -R root:root /opt/stack/traefik/log
cd /opt/stack/traefik && sudo docker compose restart
```

`cap_add: DAC_OVERRIDE` wäre der bequemere Weg und würde die Härtung aus
B-29 wieder aufweichen. Die Datei gehört dem Dienst, der sie braucht — das
ist die richtige Ebene.

In `traefik/docker-compose.yml` steht der Zusammenhang jetzt als Kommentar
direkt über der Zeile, samt der Protokollmeldung, an der man ihn
wiedererkennt.

### Was daraus folgt

Die Prüfung im Aktualisierungsskript sagt „der Container läuft" — nicht „der
Dienst tut, was er soll". Bei Traefik ist das derselbe Unterschied wie
zwischen einem laufenden Motor und einem Auto, das fährt. Ein Tool ohne
`PRUEF_URL` (Traefik hat keine, siehe `traefik/aktualisierung.conf`) ist
damit nur oberflächlich geprüft. Offen und in Abschnitt 20 der
CLAUDE.md als Grenze benannt.

---

## N-06 — Jede Wiki-Seite blitzt beim Öffnen dunkel auf

**Stufe:** niedrig
**Datei:** `wiki/test-seite.html`, `wiki/EINRICHTUNG.md` (Pflichtteil 2)
**Gefunden bei:** Anlegen der Seite `git-und-github`

Die Vorlage setzt `<body data-theme="dark">` fest. Das Thema kommt erst per
Nachricht von der Hülle — und die trifft **nach** dem ersten Anstrich ein. Im
Browser gemessen (Sonde im iframe, Zeitmessung ab Parse-Ende):

```
beim Parsen: dark | erster Anstrich: {"thema":"dark","ms":10} | Nachricht nach 10 ms
```

Bei einem hell eingestellten Wiki sieht man also jedes Mal kurz die dunkle
Fassung. Auf dem Handy ist das Fenster größer: dort fiel der Anstrich im
Bildschirmfoto noch dunkel aus, während der Kopf der Hülle schon hell war.

**In der neuen Seite behoben** — drei Zeilen direkt hinter `<body>`, die bis
zur Nachricht die Einstellung des Geräts übernehmen:

```js
document.body.dataset.theme =
  (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
    ? 'dark' : 'light';
```

Danach: `beim Parsen: light | erster Anstrich: {"thema":"light","ms":10}`.

**Behoben, auch in der Vorlage.** `test-seite.html` und der Block in
`EINRICHTUNG.md` haben die Zeilen jetzt ebenfalls, samt Begründung. Der
Editor erzeugt sie in jede neue Seite. `wiki/tests/test_seiten.py` prüft für
jede mitgelieferte Seite, dass `prefers-color-scheme` darin vorkommt.

**Prüfen:** Seite im iframe laden und im Elternfenster mitschreiben, welches
Thema beim ersten `requestAnimationFrame` gilt.

---

## N-07 — Die Suchhervorhebung markiert auch Skriptkommentare

**Stufe:** niedrig
**Datei:** `wiki/test-seite.html`, `wiki/EINRICHTUNG.md` (Pflichtteil 2)
**Gefunden bei:** Anlegen der Seite `git-und-github`

`springen()` läuft mit einem `TreeWalker` über `document.body` und filtert nur
auf `NodeFilter.SHOW_TEXT`. Ein `<script>` im Body ist aber ebenfalls ein
Element mit Textknoten — also werden Treffer in **Kommentaren und Code**
markiert. Gemessen an der neuen Seite und an der Vorlage selbst:

```
Wort "Nachricht":  11 Marken, davon 7 im Skript, erste Marke im Skript
Wort "Huelle":      6 Marken, davon 6 im Skript
test-seite.html, Wort "Pflichtteil": 3 Marken, davon 3 im Skript
```

Die Folge ist nicht kosmetisch: Für einen Treffer **ohne** Anker springt
`springen()` zur ersten Marke. Liegt die in einem Skript, hat sie kein
Layout — `scrollIntoView` tut nichts, gemessen `window.scrollY: 0`. Der
Nutzer landet oben auf der Seite statt an der echten Fundstelle, obwohl es
sie gibt.

**Behoben.** Der `TreeWalker` bekommt ein `acceptNode`, das `SCRIPT` und
`STYLE` zurückweist:

```js
var lauf = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
  acceptNode: function(k){
    var e = k.parentElement;
    while(e){
      if(e.tagName === 'SCRIPT' || e.tagName === 'STYLE')
        return NodeFilter.FILTER_REJECT;
      e = e.parentElement;
    }
    return NodeFilter.FILTER_ACCEPT;
  }});
```

Geändert in `test-seite.html`, in `wiki/vorlagen/git-und-github.html` und im
Vorlagenblock von `EINRICHTUNG.md`; der Editor erzeugt die korrigierte
Fassung. Im Browser nachgemessen, vorher und nachher, mit demselben Wort:

```
vorher   "Nachricht":  11 Marken, davon 7 im Skript, erste im Skript, scrollY 0
nachher  "Nachricht":   4 Marken, davon 0 im Skript, scrollY 1885
vorher   test-seite.html "Pflichtteil": 3 Marken, alle im Skript
nachher  test-seite.html "Pflichtteil": 0 Marken
```

Gegenprobe, damit die Korrektur nicht einfach die Hervorhebung abschaltet:
Ein Wort aus dem sichtbaren Text wird weiter markiert und angesprungen
(`Subnetzmaske`: 2 Marken; `gitignore`: 2 Marken, scrollY 4603).

**Prüfen:** Der Seite `{typ:'wiki-springen', anker:'', begriff:'Nachricht'}`
schicken und `document.querySelectorAll('mark.wiki-fund')` daraufhin
durchzählen, wie viele in einem `script` stecken.

---

## N-08 — Der Einrichtungs-Assistent konnte drei von vier Antriebsarten nicht anlegen

**Stufe:** hoch — ein neuer Benutzer kam nicht in das Tool hinein
**Datei:** `bordbuch/server.py` (`car_save`), `bordbuch/index.html` (Assistent)
**Gefunden bei:** Nachstellen der gemeldeten „Einrichtungsschleife"

Im Browser nachgefahren, mit frischer Datenbank und neuem Anmeldenamen: Name
eingegeben, Antriebsart Elektro, durch alle vier Schritte, „Auto anlegen" —
und dann nichts. Der Assistent blieb stehen, mit diesem Hinweis, der nach
3,8 Sekunden verschwand:

```
Der Verbrauch in l/100 km 0 wirkt wie ein Tippfehler -
plausibel ist 0.5 bis 60. Bitte pruefen.
```

Ein Feld für l/100 km zeigt der Assistent bei einem Elektroauto überhaupt
nicht. Es war also eine Meldung über einen Wert, den niemand eingeben oder
korrigieren konnte — und weil ohne Auto kein Weg am Assistenten vorbeiführt
(`wizNoetig()`), war das eine Sackgasse.

Die Ursache liegt im Zusammenspiel zweier für sich richtiger Regeln:

- Die Oberfläche schickt für die Größe, die zur Art nicht gehört, eine `0`
  (`lPer100:K.fuel?…:0`).
- `pflicht_zahl(..., pflicht=False)` lässt ein Feld **fehlen**, aber eine
  eingetragene `0` prüft es gegen die Plausibilitätsgrenze — und die liegt
  bei 0,5 bzw. 1.

Am API nachgemessen, genau die vier Aufrufe, die der Assistent macht:

```
bev     -> FEHLER 400: Der Verbrauch in l/100 km 0 wirkt wie ein Tippfehler
phev    -> OK id=1
petrol  -> FEHLER 400: Der Verbrauch in kWh/100 km 0 wirkt wie ein Tippfehler
diesel  -> FEHLER 400: Der Verbrauch in kWh/100 km 0 wirkt wie ein Tippfehler
```

Nur der Plug-in-Hybrid ging durch — der ist die einzige Art, die beide
Größen wirklich hat.

### Behoben

1. **Server:** `car_save` prüft nur, was zur Antriebsart gehört (`LAEDT`,
   `TANKT` neben den Grenzen). Was es bei dieser Art nicht gibt, wird nicht
   geprüft und als `0` gespeichert — das ist die Aussage „gibt es hier
   nicht" und keine stille Vorgabe.
2. **Oberfläche:** Scheitert das Anlegen, steht die Meldung jetzt **im
   Assistenten** (`.wiz .fehler`), zusammen mit dem Hinweis, dass die
   Eingaben erhalten sind. Vorher gab es nur den verschwindenden Hinweis.
3. **`saveSettings(streng)`:** Im Assistenten wird ein Fehlschlag beim
   Speichern der Einstellungen weitergegeben. Vorher verpuffte er in einem
   Hinweis — und weil `onboarded` damit nur lokal stand, kam der Assistent
   nach dem nächsten Laden stumm wieder. Das war der zweite Weg in dieselbe
   Schleife.
4. **`wizNoetig()`:** Kein erzwungener Assistent in einem fremden Profil und
   keiner ohne Schreibrecht. Ein freigegebenes Profil ohne Auto legte sonst
   einen Assistenten über den Bildschirm, dessen Speichern der Server zu
   Recht mit 403 abweist — und der erzwungene Assistent hat keinen
   Abbrechen-Knopf.

**Prüfen (ausgeführt):** Alle vier Antriebsarten im Browser durch den
Assistenten, je mit frischem Anmeldenamen:

```
Art bev     | Assistent offen: False | Autos: ['Test-bev/bev']       | onboarded: True
Art phev    | Assistent offen: False | Autos: ['Test-phev/phev']     | onboarded: True
Art petrol  | Assistent offen: False | Autos: ['Test-petrol/petrol'] | onboarded: True
Art diesel  | Assistent offen: False | Autos: ['Test-diesel/diesel'] | onboarded: True
```

**Gegenprobe:** Mit absichtlich unmöglichem Verbrauch (999 kWh/100 km) bleibt
der Assistent stehen — jetzt aber mit stehender Meldung, „Zurück" und „Auto
anlegen":

```
Assistent offen: True | Fehlerkasten: True | Autos: []
Kasten: Das Anlegen hat nicht geklappt / Der Verbrauch in kWh/100 km 999
        wirkt wie ein Tippfehler - plausibel ist 1 bis 100.
```

Tippfehler fallen also weiter auf; nur die Größe, die es bei dieser Art nicht
gibt, wird nicht mehr geprüft.

---

## N-09 — „Zuhause" war kein Heim-Ladepunkt, und der Vergleich rechnete mit Vorzeichen

**Stufe:** mittel
**Datei:** `bordbuch/index.html`
**Gefunden bei:** erster echter Durchlauf nach N-08

Nach dem Assistenten zwei Ladungen von Hand erfasst, beide mit dem Ort
`Zuhause` — das ist der Wert, den das Ladeformular selbst vorschlägt. Die
Übersicht schrieb danach:

```
Unterwegs 24,66 € 2× · 80,3 kWh · 0,307 €/kWh
Unterwegs hat dich -1,04 € mehr gekostet, als die 80 kWh
zuhause gekostet hätten (0,320 €/kWh).
```

Zwei Fehler in einem Satz:

1. **Der Ort „Zuhause" war nicht als Heim-Ladepunkt eingeordnet.**
   `placeOf()` kennt nur `settings.stationKind`, und das war leer. Also
   galten Heimladungen als „unterwegs" und wurden mit dem Anbieterpreis
   gerechnet. Der Assistent fragt den Heimstrompreis ab — wer ihn angibt,
   hat einen Heim-Ladepunkt. Der wird jetzt beim Abschluss eingetragen
   (`stationKind['Zuhause']='home'`), änderbar unter Einstellungen ›
   Ladepunkte. Im Assistenten steht dazu jetzt ein Satz, damit es keine
   stille Magie ist.
2. **„-1,04 € mehr gekostet"** ist keine Aussage. Das Vorzeichen gehört in
   die Worte: mehr / weniger, und unter einem halben Cent Unterschied
   „genauso teuer".

**Prüfen (ausgeführt):** Derselbe Durchlauf danach:

```
Zuhause 25,70 € 2× · 80,3 kWh · 0,320 €/kWh
```

Der Vergleichssatz erscheint gar nicht mehr, weil es keine Ladung unterwegs
gibt — und mit einer Ladung unterwegs stimmt die Richtung.

### Was dabei offen bleibt

Eine Heimladung mit **eingetragenem** Betrag wird mit dem Heimstrompreis
gerechnet, nicht mit dem Betrag: 42,3 kWh für eingetippte 12,50 € stehen in
der Übersicht als 13,54 € (42,3 × 0,320). Das ist Absicht
(`settings.useHomePrice`, die Stromrechnung kommt vom Versorger und nicht je
Ladung), aber an der Stelle, an der es passiert, steht es nicht — der Betrag
verschwindet ohne Hinweis. Nicht mitgeändert, weil es eine
Verhaltensentscheidung ist: entweder der Betrag gewinnt, oder die Liste sagt
je Zeile, dass gerechnet wurde.

---

## N-10 — Eingelesene und eingespielte Beträge standen hundertfach in der Datenbank

**Stufe:** hoch — falsche Zahlen, die niemandem auffallen müssen
**Datei:** `bordbuch/server.py` (`sessions_import`, `cent_aus_sicherung`)
**Gefunden bei:** Durchtesten des Datei-Imports

Eine Ladeliste als CSV eingelesen, wie ein Anbieter sie ausgibt — Semikolon,
deutsche Zahlen. Die Prüfansicht stimmte:

```
Gefundene Ladungen prüfen
Neu 3 · Energie 102,3 kWh · Kosten 24,05 €
```

Nach dem Übernehmen stand in der Übersicht:

```
Ausgaben 2.418,36 €   Ø Preis 23,646 €/kWh   Kosten je 100 km 425,63 €
```

Am API nachgemessen, gegen die Werte aus der Datei:

```
Ort                    kWh      Kosten    erwartet  Faktor
EnBW Siegen Ost        38.412   1421.0    14.21     100
Aldi Netto Park        22.1     984.0     9.84      100
```

**Der zweite, schlimmere Weg:** dasselbe beim Einspielen einer Sicherung. Eine
von Hand erfasste Tankung für 74,12 € kam als **7.412,00 €** zurück:

```
vor der Sicherung:  Tankung 42,8 l -> 74,12 EUR (costCt 7412)
nach dem Einspielen: Tankung 42,8 l -> 7412,00 EUR (costCt 741200)
```

Eine Sicherung spielt man genau dann ein, wenn man sich auf sie verlassen
muss.

### Die Ursache

Zwei Funktionen, die fast dasselbe tun:

- `cent(v)` bekommt **Euro** und multipliziert mit 100. `cent(14.21) = 1421`.
- Die Oberfläche schickt beim Import `costCt` — das ist **schon Cent**
  (`ct(14.21) = 1421`), und die Sicherung enthält `cost_ct` ebenso.

An beiden Stellen wurde die Cent-Angabe durch `cent()` geschickt:
`cent(1421) = 142100`. Der Kommentar im Code sagte sogar „bevorzugt die
Cent-Angabe" — genommen wurde sie auch, nur eben noch einmal umgerechnet.

Von Hand erfasste Vorgänge waren nie betroffen: die gehen über
`pflicht_cent(data, "cost")` und bekommen tatsächlich Euro.

### Behoben

`ct_lesen(v)` liest eine Cent-Angabe als Cent — mit derselben kaufmännischen
Rundung wie `cent()`, und ohne stillen Vorgabewert, damit der Aufrufer auf die
Euro-Spalte ausweichen kann. Beide Stellen benutzen sie. Die Umrechnung einer
Importzeile steckt jetzt in `import_zeile_werte()`, damit genau dieser Weg
einzeln prüfbar ist.

**Prüfen (ausgeführt):** Import und Sicherungsdurchlauf am laufenden Server:

```
Ladung  EnBW            14,21 EUR  erwartet 14.21  ok
Ladung  Alt ohne Cent    3,50 EUR  erwartet 3.50   ok   (Datei ohne Cent-Spalte)
Tankung Shell           74,12 EUR  erwartet 74.12  ok   (nach Sicherung + Einspielen)
```

### Was mit bestehenden Daten passiert

Der Fehler ist behoben, aber gespeicherte Zeilen bleiben falsch. Dafür gibt es
zwei Schalter:

```bash
python3 server.py --db <datei> --betraege-pruefen    # nur nachsehen
python3 server.py --db <datei> --betraege-richten    # berichtigen
```

Erkannt wird auf zwei Wegen, und die beiden sind unterschiedlich stark:

| Spur | Merkmal | Wird berichtigt |
|---|---|---|
| **sicher** | die zwei Geldspalten widersprechen sich um genau Faktor 100 | mit `--betraege-richten` |
| **verdächtig** | nur der Stückpreis verrät es: 7.412,00 € für 42,8 l = 173 €/l | nur mit `--auch-unplausible` |

Die zweite Spur ist nötig, weil beim Einspielen einer Sicherung **beide**
Spalten verdorben wurden (die Euro-Altspalte wurde aus der falschen Cent-Zahl
abgeleitet) — der Widerspruch fehlt dort. Sie ist ein Indiz, kein Beweis,
darum getrennt und nur auf Wunsch. Werkstattrechnungen bleiben außen vor: ohne
Menge gibt es keinen Stückpreis, und eine Rechnung über 7.412 € ist möglich.

`--betraege-pruefen` ändert nichts und nennt jede Zeile mit altem und neuem
Betrag. An einer wirklich verdorbenen Datenbank ausgeführt: 11 sichere Zeilen
über vier Spalten, 4 verdächtige; nach `--betraege-richten --auch-unplausible`
standen alle Preise wieder im plausiblen Bereich (0,296–0,445 €/kWh,
1,73–1,77 €/l) und die Nachprüfung meldete nichts Offenes.

**Vor dem Berichtigen sichern** (CLAUDE.md §15) — der Schalter sagt es selbst
und nennt den Weg.

### Was daraus folgt

Zwei Funktionen mit demselben Namensteil und verschiedener Einheit sind eine
Falle, die sich nicht durch Aufmerksamkeit entschärfen lässt. Aufgefallen ist
es nur, weil jemand nach dem Import auf die Übersicht geschaut und die Zahlen
mit der Datei verglichen hat — die Prüfansicht **vor** dem Übernehmen zeigte
die richtigen Beträge, weil sie aus der Datei stammen und nicht aus der
Datenbank. Eine Prüfung, die nur „Import erfolgreich" sagt, hätte hier nichts
gemerkt.

---

## N-11 — Die Suche fand nicht, was auf der Seite steht

**Stufe:** hoch — eine Wissenssammlung, in der man nichts findet, ist keine
**Datei:** `wiki/server.py` (`index_neu_bauen`)
**Gefunden bei:** Rückmeldung nach dem Einspielen von Fassung 1.1.0

Gemeldet: „tcp" ergibt null Treffer, obwohl TCP auf der Netzwerkseite in der
Tabelle der Transportprotokolle steht. Nachgestellt mit einer Seite, die wie
die echte gebaut ist — Abschnitte im Meta-Block, die Tabelle erst im Skript:

```
tcp        -> 0 Treffer | NICHTS GEFUNDEN
UDP        -> 0 Treffer | NICHTS GEFUNDEN
Transport  -> 0 Treffer | NICHTS GEFUNDEN
Schichten  -> 2 Treffer | Netzwerke / Schichten und Kapselung
```

Was im Meta-Block steht, wird gefunden. Was der Leser **sieht**, nicht.

Der Grund steht seit Anfang an in `EINRICHTUNG.md`: „Bei deiner
Netzwerk-Seite stehen Glossar, Portverzeichnis und TCP-Schritte in
JavaScript. Ein Indexer, der nur den sichtbaren Text liest, findet davon
nichts." Der Hinweis war richtig — nur hilft er niemandem, der die Seite
nicht selbst umbaut. `text_aus_html()` schneidet `<script>` heraus, und damit
war der halbe Inhalt unsichtbar.

### Behoben mit zwei zusätzlichen Quellen

| Quelle | Woher | Genauigkeit | Braucht |
|---|---|---|---|
| `ansicht` | Die Seite meldet nach dem Laden ihren sichtbaren Text an `/api/ansichtstext` | genau das, was der Leser sieht | den aktuellen Pflichtteil in der Seite |
| `skript` | Zeichenketten aus den Skriptblöcken, Kennungen und Code herausgefiltert | grob, aber sofort | nichts |

Die zweite Quelle war die wichtigere Entscheidung: sie hilft **bestehenden**
Seiten, ohne dass jemand sie anfasst. Gefiltert wird konservativ — kein
`<`, `{`, `;`, `=`, keine Adressen, keine Kennungen mit Bindestrich oder
Punkt, keine Techniknamen wie `none` oder `click`. Von der Netzwerk-Probe
bleibt genau der Inhalt:

```
Anwendung · Daten · HTTP, DNS, SMTP, SSH · Transport · Segment ·
TCP, UDP, QUIC, SCTP · Vermittlung · Paket · IP, ICMP, Routing · …
```

Hat eine Seite ihren Text gemeldet, entfällt die Skriptquelle für sie — sonst
stünde derselbe Inhalt zweimal im Index und jede Seite doppelt in der
Trefferliste.

**Prüfen (ausgeführt):** Nach `Index neu` findet die Suche `tcp`, `UDP`,
`Transport`, `Ethernet`, `ICMP` — ohne jede Änderung an der Seite. Mit
Pflichtteil in der Seite kommt der Treffer aus `ansicht` und der Schnipsel
liest sich wie der Text auf der Seite.

**Für den Server heißt das:** Einmal **Verwaltung › Index neu** drücken. Die
alten Seiten sind danach durchsuchbar.

---

## N-12 — „Server Fehler" beim Einspielen, obwohl die Seite gespeichert war

**Stufe:** mittel — die Meldung widersprach der Wirklichkeit
**Datei:** `wiki/server.py` (`uebernehmen`)
**Gefunden bei:** derselben Rückmeldung

Gemeldet: „wenn ich eine HTML einfüge kommt eine Nachricht mit Server Fehler,
aber wenn ich die Seite neu Lade ist die neue Seite da."

Der Ablauf erklärt genau das:

```python
v.commit()                       # Seite ist gespeichert
index_neu_bauen(seite_id, html)  # ungeschuetzt
```

Der Index wird **nach** dem Festschreiben gebaut. Geht dort etwas schief — ein
PDF-Anhang, den `pdftotext` nicht mochte, eine Eigenheit der Volltextsuche —,
dann wirft die Anfrage einen 500er, obwohl die Seite steht.

**Behoben.** Der Indexaufbau läuft in einem `try`, der Fehler wird
protokolliert und in der Antwort als **Hinweis** mitgegeben:

> Die Seite ist gespeichert, aber der Suchindex wurde nicht gebaut
> (RuntimeError: …). Sie ist erreichbar und wird gefunden, sobald in der
> Verwaltung „Index neu" gelaufen ist.

Die Begründung ist einfach: der Index ist abgeleitet und jederzeit neu baubar,
die Seite ist es nicht.

**Prüfen (ausgeführt):** Mit einer Kopie des Servers, in der
`index_neu_bauen()` absichtlich wirft: HTTP 200, `ok: true`, Seite im Baum,
Hinweis in der Antwort, Grund im Protokoll (`FEHLER beim Indexaufbau fuer
Seite subnetze: RuntimeError: Probe`).

---

## N-13 — Seiten schreiben war Verwaltersache

**Stufe:** mittel — eine Wissenssammlung, in die nur einer schreiben darf
**Datei:** `wiki/server.py`, `wiki/index.html`
**Gefunden bei:** Wunsch aus der Rückmeldung

`/api/pruefen` und `/api/import` verlangten Verwalterrecht, „Neue Seite" und
die Verwaltung waren nur für Verwalter sichtbar. Gefordert war: jeder darf
Seiten anlegen, der Verwalter sieht alle und steuert die Rechte, und wer eine
Gruppe vergibt, muss selbst darin sein.

### Behoben

| Wer | Darf |
|---|---|
| jeder Angemeldete | Seiten anlegen, eigene Seiten ändern, löschen, zurücksetzen |
| jeder Angemeldete | Freigabe **nur** auf eigene Gruppen setzen |
| Verwalter | alle Seiten sehen und ändern, Freigabe je Seite setzen, Themenzweige freigeben, Index neu bauen |

Zwei Helfer an einer Stelle: `darf_schreiben(z, n)` (Urheber oder Verwalter)
und `gruppen_pruefen(meta, n)` (nur eigene Gruppen). Dazu `/api/rechte`, mit
dem der Verwalter die Freigabe ändert, ohne die Seite neu einzuspielen —
geschrieben wird in die Datenbank **und** in den Meta-Block der Datei, sonst
dreht das nächste Bearbeiten durch den Urheber die Freigabe zurück.

**Prüfen (ausgeführt), vier Fälle am laufenden Server:**

```
max überschreibt lenas Seite   -> 403 "… hat lena angelegt. Aendern kann sie
                                   ihr Urheber oder ein Verwalter."
lena vergibt fremde Gruppe     -> 403 "Diese Gruppen hast du selbst nicht:
                                   geschaeftsfuehrung … deine sind: wiki-technik."
Verwalter setzt wiki-buero     -> ok; Datei und Datenbank tragen wiki-buero
Sichtbarkeit danach            -> max: 1 Seite, lena: 0, Verwalter: 1
```

---

## N-14 — Eine `const` vor ihrer Deklaration, und das ganze Wiki war weiß

**Stufe:** hoch, aber nur in meinem eigenen Zwischenstand
**Datei:** `wiki/index.html`
**Gefunden bei:** Browserprobe der Bausteine

Beim Einbau der Bausteine habe ich `ED_STIL_BAUSTEINE` und `ED_RECHENWERK`
hinter die Blöcke gesetzt, die sie benutzen. `const` wird nicht hochgezogen:

```
Uncaught ReferenceError: Cannot access 'ED_STIL_BAUSTEINE' before initialization
```

Das ist kein Teilausfall — das Skript der Hülle stirbt beim Laden, und das
Wiki zeigt **nichts** mehr. Die 54 Editortests waren grün, weil sie die
Stücke einzeln ausschneiden und in eigener Reihenfolge zusammensetzen. Gemerkt
hat es erst der Browser.

**Behoben:** beide Blöcke stehen jetzt vor ihrer Verwendung, mit Begründung
im Kommentar. Dazu ein Test, der genau diese Reihenfolge in der Datei prüft —
denn ein Test, der Funktionen einzeln ausschneidet, kann diese Art Fehler
grundsätzlich nicht finden.

**Was daraus folgt:** Für eine Oberfläche ist „die Tests sind grün" keine
Aussage über das Laden der Seite. Es braucht den Aufruf im Browser, und zwar
einen, der einen Abbruch auch sichtbar macht — mein Fahrskript hat die
Meldung anfangs verschluckt und nur „KEINE MESSUNG" geliefert.

---

## N-15 — Nach der Korrektur des Verwalters kam der Urheber nicht mehr an seine eigene Seite

**Stufe:** mittel — kein Datenverlust, aber es sperrt Leute aus ihrer eigenen
Arbeit aus, und zwar unsichtbar
**Datei:** `wiki/server.py` (`seite.nutzer_id`, `darf_schreiben`)
**Gefunden bei:** dem ausgeführten Rechtedurchgang zu `N-13` — die
fünfzehnte von fünfzehn Prüfungen

`N-13` gibt das Schreibrecht an „den Urheber und jeden Verwalter". Gelesen
wurde dafür `seite.nutzer_id`. Diese Spalte wird aber bei **jeder** Übernahme
neu geschrieben; sie bedeutet „wer zuletzt gespeichert hat", nicht „wer die
Seite angelegt hat".

Folge: Sobald ein Verwalter eine fremde Seite anfasst — einen Tippfehler
richtet, eine Freigabe nachzieht —, steht er selbst als Urheber drin, und der
eigentliche Urheber wird ausgesperrt. Im Durchgang:

```
lena legt lenas-seite an                       HTTP 200
der Verwalter ändert lenas Seite               HTTP 200, Fassung 3
lena sieht ihre eigenen Fassungen              HTTP 403   <-- falsch
```

Das ist besonders unangenehm, weil es genau bei der Person passiert, die am
meisten korrigiert: Wer das Wiki verwaltet, nimmt beim Aufräumen jeder Seite,
die er anfasst, ihrem Urheber das Schreibrecht.

**Behoben:** `seite` hat jetzt eine eigene Spalte `urheber`. Sie wird beim
Anlegen gesetzt und bei einer Änderung **nicht** angefasst; `nutzer_id`
behält seine Bedeutung („zuletzt gespeichert von") und steht in der
Verwaltung als Kurzhinweis am Namen. Das Schreibrecht entscheidet
`darf_aendern()` — eine Funktion auf Modulebene, damit sie ohne Anfrage
geprüft werden kann.

Bestehende Datenbanken bekommen die Spalte beim Start nachgetragen und aus
der Fassungsgeschichte gefüllt: Die erste archivierte Fassung trägt die
Kennung dessen, der sie geschrieben hat. Es wird nur hinzugefügt, nichts
überschrieben, und das Protokoll sagt es (CLAUDE.md §15).

**Was daraus folgt:** Ein Rechtemodell ist erst geprüft, wenn die *Reihenfolge*
der Handlungen mitgeprüft wird. Jede einzelne Prüfung war richtig — anlegen,
fremd überschreiben, Gruppen vergeben. Der Fehler saß im Zustand, den eine
erlaubte Handlung hinterlässt. Der Durchgang hat ihn nur gefunden, weil er
nach der Verwalteränderung noch einmal den Urheber gefragt hat.

---

## N-16 — Eine gelöschte Seite legte den Suchindex für immer still

**Stufe:** hoch — die Suche fand danach **nichts** mehr, in einem Werkzeug,
dessen Zweck das Finden ist
**Datei:** `wiki/server.py` (`index_neu_bauen`, `/api/loeschen`)
**Gefunden bei:** der Rückmeldung „die Suche geht nicht" — mit dem
Fehlertext, den `N-12` überhaupt erst sichtbar gemacht hat

Im Screenshot stand:

```
Die Seite ist gespeichert, aber der Suchindex wurde nicht gebaut
(IntegrityError: constraint failed).
```

`constraint failed` ohne Spaltennamen ist in SQLite die Meldung für eine
**doppelte rowid in einer FTS5-Tabelle**. Nachgemessen, nicht geraten:

```python
con.execute("INSERT INTO suche(rowid,...) VALUES(1,...)")   # geht
con.execute("INSERT INTO suche(rowid,...) VALUES(1,...)")   # IntegrityError: constraint failed
```

Die Ursache ist eine Kopplung, die man leicht übersieht: `treffer.id` ist ein
`rowid`-Alias und dient **gleichzeitig** als `rowid` in `suche` und
`suche_tri`. Beim Löschen einer Seite räumte der Fremdschlüssel
(`ON DELETE CASCADE`) die `treffer`-Zeilen weg — die FTS-Zeilen blieben
liegen, weil kein Trigger sie mitnimmt. SQLite verwendet freigewordene
`rowid`s wieder. Die nächste eingespielte Seite bekam also eine `id`, unter
der in `suche` noch eine Leiche lag, und der Indexaufbau brach ab.

Und zwar **dauerhaft**: Auch „Index neu" in der Verwaltung lief in denselben
Fehler — ausgeführt, HTTP 500. Genau der Knopf, mit dem man es reparieren
würde, war selbst blockiert. Wer einmal eine Seite gelöscht hatte, hatte
danach eine Wissenssammlung ohne Suche, ohne Weg zurück.

**Behoben:**

- `index_leeren(v, seite_id)` räumt erst die FTS-Zeilen, dann `treffer` —
  und wird beim Löschen einer Seite **vor** dem Löschen aufgerufen.
- `verwaiste_indexzeilen_loeschen(v)` räumt Reste weg. Läuft beim Start
  (mit Hinweis im Protokoll, wie viele es waren) **und** als erster Schritt
  von „Index neu" — der Reparaturknopf muss sich selbst reparieren können.
- `eintragen()` räumt die `rowid` vorher frei. Gürtel und Hosenträger: ein
  Indexaufbau darf an Resten grundsätzlich nicht scheitern.

**Was daraus folgt:** Zwei Sachen.

Erstens: `N-12` war kein Nebenbefund. Ohne den Hinweis statt des
Serverfehlers hätte diese Meldung niemand gesehen — die Rückmeldung wäre
„die Suche geht halt nicht" geblieben, und die Ursache lag drei Schichten
tiefer. Eine Fehlermeldung, die den Grund nennt, ist ein Werkzeug.

Zweitens: Ich habe in `N-11` zwei neue Indexquellen gebaut und mit
`tcp -> 1 Treffer` belegt — auf einem **frischen** Wiki. Der Fehler brauchte
eine Datenbank mit Geschichte: eine gelöschte Seite. Eine Prüfung auf
leerem Stand prüft die halbe Welt.

---

## N-17 — `new Function` in der Hülle: die eigene CSP hat es verboten, zu Recht

**Stufe:** hoch, aber nur in meinem eigenen Zwischenstand
**Datei:** `wiki/index.html`
**Gefunden bei:** Browserprobe des Blockeditors

Die lebende Vorschau im Editor soll einen Rechner-Baustein wirklich rechnen
lassen. Das Rechenwerk lag als Liste von Zeichenketten vor (es wird in die
erzeugte Seite geschrieben), und der naheliegende Griff war:

```js
const BK = new Function(ED_RECHENWERK + 'return {bkRechnen, bkZahl};')();
```

Der Browser hat das sofort abgelehnt:

```
Uncaught EvalError: Refused to evaluate a string as JavaScript because
'unsafe-eval' is not an allowed source of script in the following Content
Security Policy directive: "script-src 'self' 'unsafe-inline'"
```

Das ist die CSP, die die Hülle aus der Prüfung vom 14.09.2026 mitbekommen
hat — sie ist keine Formsache. Und die Folge war dieselbe wie bei `N-14`:
Der Fehler steht auf oberster Ebene, das ganze Skript stirbt beim Laden, das
Wiki zeigt **nichts**. Danach kam nur noch ein Folgefehler
(`Cannot access 'ED_FORM' before initialization`), der nichts erklärte.

Die naheliegende Reparatur wäre `'unsafe-eval'` in die CSP gewesen — für eine
Vorschau. Das ist die falsche Richtung: Die Hülle darf die Wiki-API im eigenen
Origin benutzen; sie ist genau der Ort, an dem `eval` nichts zu suchen hat.

**Behoben, und dabei besser geworden:** Das Rechenwerk steht jetzt **einmal**
als echte Funktion in der Hülle. Die Hülle ruft sie direkt auf, und die
erzeugte Seite bekommt ihren Quelltext über `toString()`. Damit rechnet die
Vorschau nicht nur genauso wie die Seite — es ist derselbe Code, und das lässt
sich prüfen (ein Test wertet `ED_RECHENWERK` aus und vergleicht das Ergebnis
mit dem der Funktion in der Hülle).

Dazu eine Prüflinie auf die Datei selbst: In `wiki/index.html` darf
`new Function(` oder `eval(` **nicht** vorkommen. Kommentare zählen nicht mit,
sonst wäre dieser Absatz sein eigener Fehler.

**Was daraus folgt:** Zweimal in dieser Reihe (`N-14`, `N-17`) hat ein Fehler
auf oberster Skriptebene die ganze Oberfläche gekostet, und zweimal war das
Ergebnis der Tests grün. Eine Oberfläche ist erst geprüft, wenn sie im Browser
**geladen** wurde. Und: Eine Regel, die im Weg steht, ist erst einmal ein
Hinweis — nicht ein Hindernis, das man wegräumt.

---

## N-18 — Beim Bearbeiten verlor eine Seite ihre Anhänge

**Stufe:** mittel bis hoch — kein Dateiverlust, aber der Anhang ist danach
nicht mehr *als Anhang* bekannt: er wird heruntergeladen statt angezeigt und
fällt aus der Suche
**Datei:** `wiki/server.py` (`uebernehmen`)
**Gefunden bei:** der Vorarbeit zum PDF-Baustein

`uebernehmen()` löschte alle `anhang`-Zeilen einer Seite und legte danach nur
die wieder an, die **mitgeschickt** wurden. Die Dateien selbst blieben liegen
(der Kommentar sagte das auch), die Registrierung nicht.

Genau das passiert, sobald eine Seite mit Anhang neu gespeichert wird: Die
Datei liegt schon auf dem Server, die neue Fassung nennt sie nur noch (die
Marke `data-wiki-anhang`, die das Ausgliedern hinterlässt). Also kommt nichts
Neues an — und die Zeile ist weg.

Ausgeführt, an einer Seite mit einem 196 KB großen PDF:

```
nach dem Einspielen    anhang: 1 Zeile (kompendium.pdf, application/pdf)
                       Abruf: 200, application/pdf
                       die Seite meldet 1 Anhang
nach dem Neuspeichern  anhang: 0 Zeilen
                       Abruf: 200, application/octet-stream
                       die Seite meldet 0 Anhänge
```

`application/octet-stream` heißt: Der Browser lädt die Datei herunter,
statt sie anzuzeigen. Dazu kommt, dass der seitenweise Text des PDFs aus dem
Suchindex fällt — die Suche findet in PDF-Anhängen dann nichts mehr.

**Behoben:** `uebernehmen()` behält die Zeilen der Anhänge, die die neue
Fassung noch nennt und deren Datei noch da ist. Die Entscheidung trifft
`genannte_anhaenge(html)` — sie liest die Marke und Verweise auf
`anhaenge/<name>`, und lässt nur Namen durch, die das Dateinamenmuster
erfüllen (sonst entschiede der Inhalt einer eingespielten Seite, welche Datei
gemeint ist).

**Gegenprobe ausgeführt:** Wird der Anhang aus der Seite entfernt, ist die
Zeile danach auch weg — behalten heißt nicht festhalten.

**Was daraus folgt:** Der Fehler stand im Weg, bevor das Feature begann, das
ihn gebraucht hätte. Eine Funktion, die es ohne Anhänge im Editor nie gab
(„Seite mit Anhang neu speichern"), war mit dem Editor plötzlich der
Normalfall — und kein Test deckte sie ab, weil sie vorher niemand ausführen
konnte.

---

## N-19 — Der Knopf hieß „laden" und lud herunter

**Stufe:** niedrig in der Technik, hoch in der Wirkung — er hat genau das
Gegenteil dessen getan, was sein Name sagt
**Datei:** `wiki/index.html` (Editor)
**Gefunden bei:** der Rückmeldung — „wenn ich unten auf *als HTML-Datei
laden* klicke, kommt da ein Fehler, weil ich keine Seite geladen habe"

Der Knopf hieß **„Als HTML-Datei laden"** und erzeugte einen Download der
Seite, die gerade im Editor steht. Auf Deutsch heißt „laden" aber
*hereinholen*, nicht *hinausgeben* — und weil er zuerst prüft, ob die Seite
vollständig ist, bekam man bei einem leeren Editor die Liste „Das fehlt noch".
Der Fehler war fachlich richtig und die Antwort auf eine Frage, die niemand
gestellt hatte.

**Behoben, zweifach:**

- Der Knopf heißt jetzt **„Als Datei sichern"**. Das ist, was er tut.
- Das, was der Name versprach, gibt es jetzt wirklich: Im Prüfbericht einer
  ausgewählten HTML-Datei steht neben *Übernehmen* der Knopf **„In den Editor
  laden"**. Er holt Titel, Kennung, Pfad, Freigabe, Abschnitte und alle Blöcke
  in die Felder — samt der Namen vorhandener Anhänge — und man ändert weiter,
  statt erst einzuspielen und dann zu bearbeiten.

Beide Wege gehen durch dieselbe Übersetzung (`edAusHtml`) wie *Bearbeiten* an
einer gespeicherten Seite. Ein zweiter Leser wäre eine zweite Wahrheit.

**Was daraus folgt:** Ein Wort kann eine Funktion unbenutzbar machen. Der Knopf
funktionierte tadellos und war trotzdem kaputt. Das ist nicht mit Tests zu
finden — nur damit, dass jemand es benutzt und sagt, was er erwartet hat.

---

## N-20 — Ein Titel ohne Längengrenze machte den Kopf 523 Pixel hoch

**Stufe:** mittel — kein Datenverlust, aber die Oberfläche wird am Handy
unbenutzbar, und es lässt sich von außen auslösen
**Datei:** `wiki/server.py` (`regeln_pruefen`), `wiki/index.html`
**Gefunden bei:** dem Bedienungsdurchgang, Punkt 12 aus CLAUDE.md §14b
(„ganz falsche Eingabe")

CLAUDE.md §11 fragt ausdrücklich: *„Text auf sinnvolle Länge begrenzt?"* Für
den Titel einer Seite war die Antwort nein. Geprüft wurde nur, **ob** er da
ist. Eine Seite mit einem Titel von 376 Zeichen und einem „Satz" von 669
Zeichen ging ohne eine einzige Warnung durch.

Gemessen, was das anrichtet:

| | Desktop 1440 px | Handy 390 px |
|---|---|---|
| Titelkasten | 120 px hoch in einem 76-px-Kopf | — |
| Kopf der Anwendung | 76 px (der Titel läuft heraus) | **523 px** |
| Eintrag im Themenbaum | 326 px hoch | 326 px hoch |

523 Pixel sind bei 844 Pixel Schirmhöhe zwei Drittel des Geräts — für eine
Zeile.

**Behoben, an beiden Enden:**

- Der Server weist es ab, mit Zahl und Begründung: „Der Titel ist 376 Zeichen
  lang, erlaubt sind 120. Er steht im Kopf, im Themenbaum und in jedem
  Suchtreffer." Grenzen: Titel und Abschnittstitel 120, Satz 300, Pfadebene
  und Stichwort je 60 Zeichen. Der Editor hat dieselben Grenzen als
  `maxlength` und sagt es selbst, bevor der Server es tut.
- Die Oberfläche hält auch Seiten aus, die vorher schon da waren: Kopftitel,
  Baumeinträge, Verzeichnis und Suchtreffer sind auf zwei bis vier Zeilen
  begrenzt. Nach der Änderung: Titelkasten 48 px statt 120, Kopf am Handy
  235 px statt 523 (eine normale Seite braucht dort 163 px).

**Was daraus folgt:** Die Grenze im Server allein hätte nicht gereicht — die
Seiten, die es schon gibt, verschwinden davon nicht. Eine Oberfläche, die an
ihren eigenen Altdaten zerbricht, ist nicht fertig. Und gefunden hat es nicht
der Blick in den Code, sondern Punkt 12 einer Liste, die genau dafür da ist.

---

## N-21 — Entscheidung: Schreiben braucht eine Gruppe, und nur `wiki`-Gruppen zählen

**Kein Befund, sondern eine Korrektur meiner Annahme.** In `N-13` habe ich
„jeder Angemeldete darf Seiten anlegen" umgesetzt — das war die Antwort auf
„es ist wichtig, dass jeder Seiten erstellen kann". Gemeint war: nicht nur der
Verwalter. Nicht: jeder im Haus.

**Jetzt drei Stufen:**

| Wer | Darf | Gruppe |
|---|---|---|
| jeder Angemeldete | lesen, was für ihn freigegeben ist; suchen; Merkzettel | — |
| Editor | Seiten anlegen, eigene ändern, zurücksetzen, löschen | `wiki-editor` |
| Verwalter | alle Seiten, alle Freigaben, Verwaltung, Index | `wiki-admin` |

Ein Verwalter ist immer auch Editor — sonst bräuchte man zwei Gruppen, um eine
Seite anzulegen. Beide Namen stehen in Umgebungsvariablen
(`WIKI_EDITOR_GRUPPE`, `WIKI_ADMIN_GRUPPE`).

**Und: Das Wiki sieht nur Gruppen an, die mit `wiki` anfangen.** In Authentik
hängen an einem Nutzer die Gruppen aller Werkzeuge. `vertrieb` oder
`bordbuch-admin` haben hier nichts zu entscheiden — und eine **Freigabe** auf
so eine Gruppe war vorher ein stiller Fehler: Sie nimmt die Seite allen weg
und gibt sie niemandem. Das wird jetzt abgewiesen, mit Begründung. Das Präfix
steht in `WIKI_GRUPPEN_PRAEFIX`.

Wichtig dabei: Der Filter darf die Rollenprüfung nicht aushebeln. Eine Gruppe
`admin` (ohne Präfix) macht niemanden zum Verwalter, eine Gruppe `wiki` auch
nicht — geprüft wird auf den ganzen Namen. Dafür gibt es einen Test.

**Was der Knopf nicht tut:** Wer nicht schreiben darf, sieht *Neue Seite* und
*Bearbeiten* nicht. Ein Knopf, der in ein 403 führt, ist schlimmer als kein
Knopf — und in den Einstellungen steht, welche Gruppe fehlt und wer sie
vergibt.

---

## N-22 — Ein PDF-Knopf ohne PDF tat gar nichts

### Befund

Der PDF-Baustein baut Knöpfe, die die Hülle bitten, ein Anhang-PDF zu öffnen.
Welche Datei gemeint ist, steht nicht im Knopf, sondern in der Marke
`data-wiki-anhang` an dem Anhangsblock, auf den der Knopf zeigt — genau so
soll es sein (siehe `N-18`: nur so übersteht der Knopf eine Umbenennung).

Fehlt dieser Anhangsblock, war die Zeile im Pflichtteil jeder Seite:

```js
if(!name || window.parent === window) return;
```

Der Leser klickt, und **nichts** passiert. Keine Meldung, kein Hinweis, kein
Eintrag in der Leiste. Das kommt auf zwei Wegen zustande:

1. Im Editor einen PDF-Baustein anlegen, Sprungziele eintragen, aber keine
   Datei auswählen und speichern. Der Editor hat das erlaubt.
2. Eine von Hand oder von einer KI geschriebene Seite mit `datei: handbuch`
   im Baustein einspielen, ohne den Anhang mitzuschicken.

### Ausgeführt, nicht überlegt

`scratchpad/n22/probe.mjs` baut mit `edSeiteBauen` genau so eine Seite und
liest das Ergebnis:

```
Knopf mit data-wiki-pdf="handbuch" im HTML: true
Skriptblock id="handbuch" im HTML:         false
=> Der Knopf zeigt auf einen Block, den es nicht gibt: true
Pflichtteil bricht bei fehlendem Namen still ab: true
```

### Behoben an beiden Enden

**Im Editor:** `edPruefbar` beanstandet jetzt jeden PDF-Baustein ohne Datei —
mit Abschnitt und Nummer: *„Im PDF-Baustein 1 in „Netzwerke" ist keine Datei
ausgewählt — seine Knöpfe würden ins Leere führen."* Damit kommt Weg 1 gar
nicht mehr bis zum Speichern.

**In der Seite:** Weg 2 kann der Editor nicht verhindern — eine eingespielte
Seite bringt ihr HTML selbst mit. Darum sagt der Pflichtteil beim Klick, was
fehlt, statt zu schweigen: ein Warnkasten unter den Knöpfen nennt die
gesuchte Kennung.

Drei Tests in `wiki/tests/test_editor.mjs`, jeder mit einer Mutationsprobe
belegt: Prüfung entfernt → Test 1 rot, `||` zu `&&` → Test 2 rot, alte stille
Zeile zurück → Test 3 rot.

### Was daraus folgt

Der Baustein war für sich richtig, die Marke war richtig, `N-18` war richtig.
Falsch war nur die Annahme, dass die beiden immer zusammen in einer Seite
ankommen. Ein `return` ohne Meldung ist im Zweifel die schlechteste von drei
Möglichkeiten — schlechter als eine Absage und schlechter als ein Absturz,
weil niemand ihn melden kann.

---

## N-23 — Ein voller Meta-Block mit leerem `<body>` galt als fehlerfreie Seite

### Befund

Gefunden beim Bau des KI-Prompts: Ich habe eine Datei geschrieben, wie sie
eine KI liefern würde — Meta-Block mit Titel, vier Abschnitten, Markup,
Stichworten, und ein leerer `<body>`. Die Prüfung sagte:

```
fehler: []
warnungen: [6 Hinweise]
```

Und `/api/import` sagte `"ok": true`. Danach:

| Was | Ergebnis |
|---|---|
| Datei auf dem Server | 3703 Byte |
| Sichtbarer Text im Körper | **0 Zeichen** |
| Im Themenbaum | ja, unter Technik / Geräte |
| Suche nach „Buchse" | ein Treffer, mit Schnipsel |
| Was der Leser sieht | eine weiße Fläche |

Das ist der schlechteste Zustand von allen: Die Seite ist **auffindbar und
leer**. Wer den Treffer anklickt, denkt, das Wiki sei kaputt.

Die Ursache ist eine Lücke in `regeln_pruefen`: Sie prüft den Meta-Block sehr
genau (Slug, Titellänge, Anker, Stichwortlängen, Farben, externe Verweise) —
aber nie, ob im Körper überhaupt etwas steht. Die Prüfung nimmt den Meta-Block
für die Seite.

### Behoben

**Der Körper muss etwas hergeben.** Weniger als 40 Zeichen sichtbarer Text
(ohne Skripte, Stile, Kommentare und Marken) ist jetzt ein Fehler, nicht eine
Warnung — mit der Zahl in der Meldung und dem Weg heraus: *„Wenn die Datei nur
als Entwurf gedacht war, lade sie in den Editor — er baut die Seite aus dem
Meta-Block."*

**Eine Ausnahme, bewusst:** Seiten, die ihren Inhalt erst im Browser bauen,
sind ausdrücklich erlaubt — genau darum ging `N-11`. Trägt die Datei einen
ausführbaren Skriptblock, wird nichts beanstandet. Der Meta-Block
(`application/json`) und ein Anhang (`text/plain`) zählen dabei **nicht** als
Code, sonst würde die Ausnahme jede Datei decken: der Meta-Block ist in jeder
drin. Lieber keine Beanstandung als eine falsche.

**Und der Weg heraus wurde erst gebaut.** Vorher bot der Bericht *In den
Editor laden* nur an, wenn die Prüfung **keine** Fehler fand. Das ist genau
verkehrt: Der Editor baut Gestaltung, Pflichtteil und Farben selbst neu — er
räumt diese Fehler auf. Jetzt steht der Knopf da, sobald der Meta-Block
lesbar ist, mit der Erklärung, warum die Fehler danach weg sind.

### Ausgeführt

Der ganze Weg im Browser, nicht im Kopf: Entwurf hochgeladen → *Nicht
übernehmbar* mit dem neuen Fehler, kein *Übernehmen*-Knopf → *In den Editor
laden* → 4 Abschnitte, 7 Blöcke (Text, Schritte, Kennzahlen, Rechner, Text,
PDF, Text), Titel, Pfad, Kennung und Satz gefüllt → PDF ausgewählt →
gespeichert → das Verzeichnis links zeigt die Abschnitte → der PDF-Knopf in
der Seite öffnet `anhang-kompendium.pdf#page=12`. Der Rechnerblock zeigte in
der lebenden Vorschau **20** — 500 × 0,04 = 20, von Hand nachgerechnet.

Neun Tests in `wiki/tests/test_seiten.py`, vier Mutationsproben: Prüfung aus
→ 7 rot, Grenze um eins verschoben → der Grenzfall rot, Ausnahme für
Aufbaucode entfernt → die JS-Seite rot, jede Skriptart als Aufbaucode → 7 rot.

### Was daraus folgt

Die Prüfung war gründlich in allem, was im Meta-Block steht — und blind für
die Frage, ob die Seite eine Seite ist. Dasselbe Muster wie `N-05`, `N-06`,
`N-08` und `N-10`: Jede einzelne Prüfung war richtig, keine hat gefragt, was
am Ende beim Menschen ankommt. Gefunden hat es nicht die Prüfung, sondern der
Versuch, den neuen Weg wirklich zu gehen.

---

## N-24 — Dieselbe Gruppe stand zweimal im Verzeichnis

### Befund

Gefunden an der Seite, die ich nach meinem eigenen KI-Prompt gebaut habe.
Ihre vier Abschnitte tragen die Gruppen:

```
Grundlagen · Anleitung · Grundlagen · Wenn es klemmt
```

Das Verzeichnis links zeigte daraufhin gemessen:

```
Grundlagen → Was du vorher brauchst
Anleitung  → Drucker anmelden
Grundlagen → Aufwand und Kosten      ← dieselbe Überschrift zum zweiten Mal
Wenn es klemmt → Wenn es klemmt
```

Das ist kein Fehler der Anzeige. `abschnittsleiste` fasst bewusst nur
**aufeinanderfolgende** Abschnitte unter eine Überschrift, weil die
Reihenfolge der Abschnitte die Aussage des Autors ist — sie umzusortieren
wäre schlimmer. Der Aufbau ist also so gemeint, wie er dasteht. Nur hat ihn
niemand so gemeint.

### Behoben, wo es hingehört: beim Schreiben

Der Editor sagt es jetzt beim Anlegen, an dem Abschnitt, der die Überschrift
ein zweites Mal aufmacht:

> „Grundlagen" kommt weiter oben schon vor, und dazwischen steht eine andere
> Gruppe. Im Verzeichnis erscheint die Überschrift dann zweimal. Verschiebe
> die Abschnitte nebeneinander — mit ↑ und ↓ oben.

Warm, nicht rot, und **ohne Sperre**: Der Aufbau ist erlaubt, nur selten
gewollt. Der Hinweis steht nur an der Wiederholung, nicht am ersten
Abschnitt der Gruppe — dort wäre der Satz „kommt weiter oben schon vor"
schlicht falsch. Dieselbe Regel steht auch im KI-Prompt, damit sie gar nicht
erst entsteht.

Ein Abschnitt **ohne** Gruppe zählt dabei als Trennung: Im Verzeichnis steht
dort eine Lücke, und danach fängt die Überschrift wieder an. „A, ohne, A"
zeigt „A" also genauso zweimal wie „A, B, A". Der erste Entwurf der Funktion
hatte die leeren Gruppen weggefiltert und diesen Fall verschluckt — aufgefallen
ist es an einem Test, den ich vorher von Hand berechnet hatte.

Fünf Tests in `wiki/tests/test_editor.mjs`, drei Mutationsproben: falsche
Nummer gemeldet → 3 rot, leere Gruppen wieder wegfiltern → 1 rot,
Nachbarschaft ignorieren → 1 rot. Im Browser nachgesehen: genau ein Hinweis,
an „Abschnitt 3 · Aufwand und Kosten".

---

## N-25 — Eine Klasse wurde benutzt, hatte aber keine Regel

### Befund

Die Erfolgsmeldung im PDF-Baustein — *„kompendium.pdf ausgewählt, wird beim
Speichern angehängt"* — steht in `<span class="ed-gut">`. Zu dieser Klasse gab
es im ganzen Stilblock keine Regel. Gemessen im Browser:

| | Farbe | Größe | Fett |
|---|---|---|---|
| `.ed-gut` | `oklch(0.3 0.01 250)` | 14 px | 400 |
| `body` | `oklch(0.3 0.01 250)` | 14 px | 400 |
| `.ed-merke` (der Hinweis daneben) | `oklch(0.52 0.01 250)` | 11,5 px | 400 |

Zeichen für Zeichen dasselbe wie gewöhnlicher Fließtext — und **größer und
dunkler** als die Hinweise ringsherum. Die eine Zeile, die den Erfolg bestätigt,
sah damit aus wie ein Satz, der vergessen wurde, und drängte sich optisch vor
die Erklärungen. Eine Prüfung im Browser hätte sie auch gefunden; gesucht habe
ich sie erst, weil im Quelltext eine Klasse ohne Regel stand.

### Behoben

`.ed-gut{font-size:12px;color:var(--good);font-weight:500}` — grün, etwas
kleiner als Fließtext, halbfett. Nachgemessen: `oklch(0.45 0.14 158)`, 12 px,
500. Damit liest sich die Zeile als Bestätigung, nicht als Absatz.

Geprüft wurde beides mit derselben Messung, vor und nach der Änderung, und
zusätzlich, ob überhaupt eine Regel für den Selektor existiert
(`regelVorhanden`: vorher `false`, nachher `true`).

---

## N-26 — Die Suchhervorhebung übersprang Fundstellen, weil das Muster mitzählte

### Befund

Im Pflichtteil jeder Seite stand, um die Textknoten mit einem Treffer zu
sammeln:

```js
var re = new RegExp('(' + worte.join('|') + ')', 'gi');
while((n = lauf.nextNode())) if(re.test(n.nodeValue)) knoten.push(n);
```

Ein Muster mit `/g` **merkt sich seine Position**. `test()` sucht beim nächsten
Aufruf erst hinter dem letzten Treffer weiter — auch wenn der nächste Aufruf
eine völlig andere Zeichenkette prüft. Nachgemessen in Node:

```
mit /g, so wie im Pflichtteil:   gefunden in Knoten [ 0, 2 ]
mit lastIndex=0 vor jedem Test:  gefunden in Knoten [ 0, 1, 2 ]
Erwartet (von Hand): alle drei Knoten enthalten tcp -> [ 0, 1, 2 ]
```

### Die Falle an diesem Befund

Auf `netzwerk-grundlagen.html` war **nichts** zu sehen: vier Vorkommen von
„TCP", vier Marken. Ich hatte drei vorhergesagt und lag falsch — zwischen zwei
Absätzen steht im HTML ein Textknoten aus Zeilenumbruch und Einrückung, der
nicht trifft, und ein **fehlgeschlagener** `test()` setzt `lastIndex` wieder
auf 0. Der Leerraum hat den Fehler verdeckt.

Er bricht erst, wenn zwei treffende Textknoten **direkt** benachbart sind.
Dafür habe ich eine Seite gebaut, deren Körper von Hand so aussieht:

```html
<p><b>Ein Absatz, der lang genug ist, damit die Fundstelle weit hinten liegt: tcp</b>tcp</p>
```

Gemessen im Browser, an der eingespielten Seite:

| | Vorkommen im Text | gesetzte Marken |
|---|---|---|
| vorher | 2 | **1** |
| nachher | 2 | 2 |

Das ist genau die Lage, die `edInline` erzeugt: `**fett**` wird ein `<b>`, und
unmittelbar danach geht der Text weiter — ohne Leerraum dazwischen.

### Behoben, mit einer zweiten Sache gleich dazu

- `re.lastIndex = 0` vor jedem `test()`.
- Die Marken kommen jetzt über ein `DocumentFragment` **ohne zusätzliches
  `<span>`** in den Text. Vorher wurde jeder treffende Textknoten durch ein
  `<span>` ersetzt, und das blieb nach dem Aufräumen stehen. Nach einigen
  Suchläufen war der Text dauerhaft zerschnitten, und ein Wort über eine alte
  Schnittstelle hinweg war nicht mehr zu finden.
- Beim Entfernen der Marken wird `normalize()` auf dem Elternknoten gerufen,
  damit die Textknoten wieder zusammenwachsen.

### Und der Grund, warum das allein nicht reicht

Jede Seite trägt ihren Pflichtteil **selbst** — das ist der Kern der
Architektur und soll so bleiben. Der Preis: Eine Korrektur am Pflichtteil
erreicht bestehende Seiten nicht. Eine gespeicherte Seite behält den Code, mit
dem sie gebaut wurde.

Für die Seiten im Repository macht das jetzt `wiki/pflichtteil-nachziehen.mjs`
— es ersetzt **nur** den Pflichtteil und lässt Inhalt, Meta-Block und Stil in
Ruhe. Darum geht es auch bei `git-und-github.html`, die von Hand gebaut ist und
kein `markup` im Meta-Block hat; ein Rundlauf durch den Editor hätte ihre
Struktur verloren. Sechs Seiten nachgezogen, danach im Browser gegengeprüft:
2/2, 4/4 und 0/0 Marken, keine Fehler auf der Konsole.

Ein Test in `wiki/tests/test_editor.mjs` vergleicht den Pflichtteil jeder
mitgelieferten Seite mit dem der Hülle und wird rot, sobald einer
zurückfällt. Vier Mutationsproben, alle vier erkannt.

**Für Seiten, die schon im Betrieb liegen,** gilt das nicht automatisch. Sie
bekommen den korrigierten Pflichtteil beim nächsten Speichern über den Editor.
Das ist kein Datenverlust und keine Wanderung — nur eine Korrektur, die
langsam durchsickert.

---

## N-27 — *(zurückgezogen)* Meine „Korrektur" der Korrekturzeile war der Fehler

Beim Umbau der Suche hielt ich diese Zeile für vertauscht:

```js
Nichts zu <span class="mono">${statt}</span> — Treffer für <strong>${q}</strong>
```

Der Aufruf lautet `trefferZeichnen(d.statt || q, ms, d.statt ? q : null)` —
also steht im Parameter `q` das **wirksame** Wort und in `statt` das
**getippte**. Genau umgekehrt, als die Namen vermuten lassen. Die Zeile war
richtig; ich habe sie gedreht und damit falsch gemacht.

Aufgefallen ist es, weil ich die Ausgabe danach im Browser nachgelesen habe
statt im Quelltext:

```
Nichts zu Netzwek — Treffer für netzwerk
```

Das ist die richtige Aussage — mit der zurückgedrehten Zeile. Die Namen im
Funktionskopf heißen jetzt `gesucht` und `getippt`, damit die Verwechslung
nicht noch einmal passiert.

**Was daraus folgt:** CLAUDE.md §14 („tatsächlich ausprobiert, nicht nur
gedanklich") gilt auch für das Lesen von Code, nicht nur für das Prüfen von
Funktionen. Zwei Variablennamen, die das Gegenteil von dem bedeuten, was sie
sagen, haben mich in eine Änderung geführt, die alle Tests bestanden hätte —
weil es für diese Zeile keinen Test gab.

---

## N-28 — Der Pflichtteil jeder Seite stand im Suchindex

### Befund

Der Suchindex hat ein drittes Netz für Inhalte, die erst im Browser
entstehen (`N-11`): Zeichenketten aus den Skriptblöcken der Seite. Der
Pflichtteil ist aber auch ein Skriptblock — und er steht **in jeder Seite**,
mit demselben Inhalt. Gemessen an fünf eingespielten Seiten:

| Suchbegriff | Treffer | von |
|---|---|---|
| `dark` | 5 Seiten | 5 |
| `light` | 5 Seiten | 5 |
| `prefers` | 5 Seiten | 5 |
| `section` | 5 Seiten | 5 |
| `details` | 5 Seiten | 5 |
| `warn` | 5 Seiten | 5 |

Sechs Wörter, die auf alles passen. Das ist das Gegenteil einer Suche. Im
Index stand zum Beispiel:

```
(prefers-color-scheme: dark) · dark · light · gi · SCRIPT · start ·
section[id] · h1,h2,h3 · details:not([open]) · warn bk-pdf-fehlt
```

`text_aus_skripten` filtert schon ordentlich — Kennungen mit Bindestrich oder
Punkt, Selektoren, Adressen, eine Liste technischer Wörter. Aber
`(prefers-color-scheme: dark)` hat ein Leerzeichen und fällt damit durch alle
Einzelwort-Regeln, und `section[id]` kannte die Filterliste nicht. Jede neue
Zeile im Pflichtteil hätte neue Wörter nachgeliefert — ein Wettlauf, den die
Filterliste nicht gewinnt.

### Behoben an der Wurzel

Der Pflichtteil wird **ganz** aus dem HTML genommen, bevor Zeichenketten
gesammelt werden. Erkannt wird er an seiner ersten Zeile
(`/* Pflichtteil jeder Wiki-Seite: … */`) — dieselbe Marke, die auch
`pflichtteil-nachziehen.mjs` benutzt.

Danach gemessen: `dark`, `prefers`, `section`, `details` → **0 Treffer**.
`warn` → 13 Stellen, aber aus `abschnitt` und `seite`, also aus sichtbarem
Text. `tcp` (5), `netzwerk` (6) und `Gastnetz` (4) unverändert — die Heilung
hat den Inhalt nicht mitgenommen.

Zwei Wörter blieben zunächst übrig: `git-und-github.html` bringt einen
**eigenen** Skriptblock mit, der dasselbe tut wie der Pflichtteil (ein
Überrest aus `N-06`, bevor die Zeile dorthin wanderte). Dafür gibt es jetzt
eine allgemeine Marke: `<script data-wiki-technik>` sagt „hier steht nichts
zum Suchen". Damit sind es 0.

Acht Tests, davon einer über die **echten** mitgelieferten Seiten mit dem
**echten** Pflichtteil. Zwei Mutationsproben: Pflichtteil-Filter entfernt →
8 rot, Technikmarke ohne Wirkung → 3 rot.

### Was daraus folgt

`N-11` war richtig, und diese Quelle bleibt nötig. Sie hat nur eine
Nebenwirkung, die niemand nachgerechnet hat: Was in jeder Seite steht, taugt
nicht zum Unterscheiden von Seiten. Ein Index, der auf alles passt, ist
schlimmer als eine Lücke — eine Lücke merkt man.

---

## N-29 — Den Suchindex konnte man nur mit `curl` neu bauen

### Befund

`N-16` endete mit einem Neuaufbau des Index, der auch Reste wegräumt. Der ist
als Schnittstelle da und tut, was er soll:

```
POST /api/neuindex  als Verwalter  ->  {"ok": true, "verwaiste": 0}
POST /api/neuindex  als Editor     ->  403
```

Nur: In der Oberfläche gab es dazu **keinen Knopf**. Nicht in der Verwaltung,
nicht in den Einstellungen, nirgends — gesucht mit `grep -n "neuindex"` über
`index.html`: null Treffer.

Das heißt: Die einzige Reparatur für einen Index, der nicht mehr aufbaut,
stand einem Verwalter nur zur Verfügung, wenn er eine Kommandozeile und die
Adresse kannte. Ein Werkzeug hinter einer Tür ohne Klinke.

### Behoben

Der Knopf steht jetzt in der Verwaltung unter **Wartung**, zusammen mit dem,
was ein Verwalter dabei wissen will: wie viele Zeilen im Index stehen, wie
viele davon verwaist sind (mit dem Verweis auf `N-16` und der Erklärung, dass
der Neuaufbau sie zuerst wegräumt), und wie lange es gedauert hat.

Ausgeführt: Knopf gedrückt, Meldung *„Index neu gebaut in 0 s"*, danach die
Kennzahlen neu gelesen. Der Rechtetest dazu steht in `test_dienst.py`.

### Was daraus folgt

Eine Schnittstelle ohne Bedienung ist für den, der sie braucht, nicht
vorhanden. Beim Beheben von `N-16` war der Weg über `curl` der schnellste —
und danach hat niemand gefragt, wie ein Verwalter ihn findet.

---

## N-30 — Löschen meldete einen Serverfehler, obwohl die Seite weg war

### Befund

Gefunden beim Bau der neuen Verwaltung, an einem Bestand von 305 Testseiten.
Das Sammellöschen meldete:

```
0 entfernt, 2 nicht: seite-238-drucker: Auf dem Server ist etwas
schiefgegangen (FileNotFoundError, Kennung 57731).
```

Nachgestellt mit einer einzelnen Seite, deren Ordner von Hand entfernt wurde:

| | |
|---|---|
| Antwort | `HTTP 500` — „Auf dem Server ist etwas schiefgegangen" |
| Seiten vorher | 5 |
| Seiten nachher | **4** |

Die Seite war **weg** — aus Datenbank, Themenbaum und Suche. Die Meldung sagte
das Gegenteil.

Die Ursache steht in der Reihenfolge: Erst `index_leeren`, dann `DELETE FROM
seite`, dann `db().commit()` — und **danach** `shutil.move` des Ordners. Fehlt
der Ordner, fliegt an dieser Stelle ein `FileNotFoundError`, den der allgemeine
Fänger in eine 500 verwandelt. Das Festschreiben ist da längst passiert und
lässt sich nicht zurücknehmen.

Dieselbe Familie wie `N-12` („Server Fehler beim Einspielen, obwohl die Seite
gespeichert war") — und schlimmer: Wer die Meldung glaubt, sucht die Seite
weiter oder drückt noch einmal (dann 404) und hält das Wiki für kaputt.

### Behoben

Nach dem Festschreiben wird nichts mehr geworfen. Fehlt der Ordner, ist nichts
beiseitezulegen; das ist kein Fehler, sondern eine Auskunft:

> Die Seite ist entfernt. Einen Ordner auf der Platte hatte sie nicht mehr —
> es war nichts beiseitezulegen.

Jeder andere Ordnerfehler (Rechte, volle Platte) landet im Protokoll des
Containers und kommt als Hinweis zurück, mit der klaren Aussage, dass die Seite
entfernt ist und der Ordner noch liegt. Die Oberfläche zeigt einen solchen
Hinweis neun Sekunden statt der üblichen zweieinhalb.

### Neu dabei: Tests gegen den laufenden Dienst

Alle bisherigen Tests rufen **Funktionen** auf. Die Behandlung der Anfragen
selbst — Rechte, Rückgabewerte, was nach einem Fehler in der Datenbank steht —
war damit nicht abgedeckt, und genau dort saß dieser Befund.

`wiki/tests/test_dienst.py` startet `server.py` als eigenen Prozess auf einem
freien Port und spricht ihn über HTTP an, mit denselben Kopfzeilen, die der
Anmelde-Stellvertreter im Betrieb setzt. Neun Tests: die drei Löschwege, die
Rechte an `/api/import`, `/api/verwaltung` und `/api/neuindex`, und die Abwehr
einer Anfrage von fremder Seite.

Mutationsproben: der Fänger für den fehlenden Ordner entfernt → rot; kein
Hinweis gesetzt → rot; Hinweis auch im Normalfall → rot; die Editorprüfung
beim Einspielen entfernt → rot.

---

## N-31 — Jedes eingebettete Bild über 200 kB wurde beim Einspielen zerstört

### Befund

Gefunden beim Vorbereiten eines Bild-Bausteins, mit einer Seite, die zwei
echte PNG enthält: eines mit 74 Byte, eines mit 307 613 Byte. Nach dem
Einspielen steht in der gespeicherten Seite:

```html
<img id="klein" src="data:image/png;base64,iVBORw0KGgoAAAAN…">   ← heil
<img id="gross" src="data:image/png;base64,anhaenge/eingebettet.png">
```

Die zweite Adresse ist Unsinn: Der Browser liest alles hinter `base64,` als
Base64, bekommt `anhaenge/eingebettet.png` und zeigt **nichts**.

Die Ursache steht in einer einzigen Zeile von `anhaenge_ausgliedern`:

```python
return f'{praefix}anhaenge/{name}'
```

`praefix` ist die Gruppe `(data:image/png;base64,)` aus dem Muster. Ersetzt
werden sollte die **ganze** Adresse, ersetzt wurde nur der Datenteil — und der
Präfix blieb davorstehen.

Und wie immer bei dieser Familie: Die Prüfung meldete nichts. `/api/import`
sagte `"ok": true`, der Anhang lag mit 307 613 Byte korrekt im Ordner, die
Größenersparnis stand im Bericht. Kaputt war nur das, was der Leser sieht.

### Behoben

Die ganze Adresse wird ersetzt. Danach im Browser nachgemessen, an der
eingespielten Seite im abgeschotteten Rahmen:

| Bild | Adresse | geladen | Größe |
|---|---|---|---|
| klein | `data:image/png;base64,…` | ja | 8 × 8 |
| groß | `anhaenge/eingebettet.png` | **ja** | 320 × 320 |

Das ist zugleich die Antwort auf eine Frage, die ich nicht raten wollte: Ob
ein Bild aus dem Anhangsordner in einem Rahmen mit *opakem* Origin überhaupt
lädt, wo die CSP `img-src 'self'` sagt. Es lädt. Gemessen, nicht geschlossen.

Vier Tests in `wiki/tests/test_anhaenge.py`, drei Mutationsproben: Präfix
wieder davor → 2 rot, Schwelle ohne Wirkung → 1 rot, gleicher Name für zwei
Bilder → 1 rot.

Dabei fiel noch etwas auf: Die Schwelle wurde **zweimal** geprüft — einmal im
Aufruf, einmal in der Funktion. Zwei Riegel für dieselbe Sache, von denen
keiner für sich prüfbar ist: Nimmt man einen weg, bleibt alles grün. Jetzt
steht sie einmal, in der Funktion, und die Mutationsprobe greift.

### Eine Warnung zur Prüftechnik

Beim ersten Durchlauf blieben zwei von drei Mutationen unentdeckt — und eine
davon zu Unrecht: Python hatte den übersetzten Zwischenstand von `server.py`
im `__pycache__` und las die Mutation gar nicht ein. Aufgefallen ist es, weil
derselbe Test einzeln aufgerufen sofort rot wurde. Seither wird der Cache vor
jeder Probe gelöscht. Eine Mutationsprobe, die aus Versehen den alten Code
prüft, ist schlimmer als keine: Sie bescheinigt einem Test Zähne, die er
nicht hat.

---

## N-32 — Ein Titel mit `</script>` brach den Meta-Block der eigenen Seite auf

### Befund

Gefunden beim Bau einer Sicherheitsprobe, die jeden Baustein mit bösartigem
Text füttert. Der Meta-Block entsteht so:

```js
'<' + 'script type="application/json" id="wiki-meta">',
JSON.stringify(meta, null, 2),
'<' + '/script>',
```

`JSON.stringify` maskiert `<` **nicht** — es besteht kein Grund dazu, solange
das Ergebnis JSON bleibt. Hier steht es aber in einem `<script>`-Element, und
dort beendet die Zeichenfolge `</script>` den Block, egal wo sie steht. Ein
Titel wie

```
</script><img src=x onerror=alert(1)>
```

zerlegt damit die eigene Seite: Der Meta-Block endet mitten im JSON, der Rest
wird Text, und das Bild-Tag ist echtes Markup.

Ausgeführt, mit genau diesem Titel:

```
POST /api/pruefen
fehler: ["Der Block wiki-meta ist kein gueltiges JSON:
          Unterminated string starting at: line 4 column 12 (char 33)"]
meta lesbar: False
```

Der Server **lehnt die Seite ab** — das ist die gute Nachricht, und die Grenze
hält. Aber die Meldung spricht von JSON, wo es um einen Titel geht: Wer das
liest, sucht den Fehler an der falschen Stelle. Und „Als Datei sichern" erzeugt
eine Datei, die niemand mehr einspielen kann.

### Behoben

Ein Zeichen: `JSON.stringify(meta, null, 2).replace(/</g, '\\u003c')`. Das ist
**dasselbe JSON** — jeder Leser gibt denselben Text zurück —, aber die Folge
`</script>` kann darin nicht mehr vorkommen.

Nachgemessen mit demselben Titel:

```
JSON lesbar, Titel kommt heil zurueck: true
POST /api/pruefen   fehler: []   meta lesbar: True
Titel: </script><img src=x onerror=alert(1)>
```

### Dazu: eine Probe über alle elf Bausteine

`wiki/tests/test_editor.mjs` fährt jetzt jeden Baustein mit demselben
bösartigen Text durch — Titel, Zeilen, Formel, Einheit, Dateiname. Geprüft
wird nicht, wie das Ergebnis aussieht, sondern dass daraus **nirgends
Auszeichnung wird**: kein `script`-Element, kein Attribut, das mit `on`
anfängt, kein `javascript:` in `src` oder `href`, und ein `img` nur im
Bild-Baustein.

Der erste Anlauf dieses Tests suchte nach dem Wort `onerror` im Ergebnis und
wurde rot — bei harmlosem Text: `&lt;img src=x onerror=…` ist geschützter
Text und keine Marke. Jetzt tastet ein kleiner Scanner nur **echte** Marken
ab; geschützter Text trägt `&lt;` und wird gar nicht erst gefunden.

Dieselbe Sorte Fehler steckte in der zweiten Prüfung: Sie suchte `</script>`
im Bereich bis zum `<style>` — darin steht aber auch das **richtige** Ende
des Blocks. Der Test wäre immer rot gewesen. Jetzt wird geprüft, was ein
Browser sieht: alles bis zum ersten Skript-Ende muss lesbares JSON sein, aus
dem der Titel Zeichen für Zeichen zurückkommt. Mutationsprobe: Maskierung
entfernt → rot.

---

## N-33 — Ein Kommentar hat die ganze Oberfläche abgeschaltet

### Befund

Beim Beheben von `N-32` habe ich in den Kommentar daneben geschrieben, worum
es geht — mit der Zeichenfolge als Beispiel:

```js
/* … Ohne diesen Schritt bricht ein Titel wie
   "</script><img src=x onerror=…>" den Meta-Block auf … */
```

Ein Browser beendet ein `<script>`-Element beim **ersten** Vorkommen dieser
Folge. In einer Zeichenkette, in einem Kommentar — überall. Der gesamte Rest
von `index.html` war damit kein Programm mehr, sondern Text.

Was der Browser dazu sagte:

```
Uncaught SyntaxError: Invalid or unexpected token   (Zeile 3807)
Uncaught SyntaxError: Unexpected end of input       (Zeile 3810)
```

Die Oberfläche lud, zeigte ein Gerüst — und konnte nichts. Kein Knopf, keine
Suche, kein Editor.

### Warum nichts davon aufgefallen ist

| Prüfung | Ergebnis |
|---|---|
| 118 Node-Tests | grün |
| 117 Python-Tests | grün |
| `js_pruefen.sh` (Syntaxprobe) | „block1.js: lesbar" |

Die Funktionstests schneiden sich ihre Funktionen mit regulären Ausdrücken
aus der Datei und sehen sie nie als Ganzes. Und die Syntaxprobe schnitt
**genauso wie der Browser** am ersten Skript-Ende ab — meldete das Bruchstück
aber als vollständigen Block und damit als lesbar. Sie hat den Fehler also
gesehen und für richtig erklärt.

Aufgefallen ist es erst im Browser, beim Rundgang durch alle Ansichten.
Genau dafür steht die Regel in `CLAUDE.md`: *Eine Oberfläche ist erst
geprüft, wenn sie im Browser geladen wurde.* Es ist das dritte Mal
(`N-14`, `N-17`, jetzt `N-33`), dass ein Fehler auf oberster Ebene die
ganze Hülle gekostet hat, während alles grün war.

### Behoben, und diesmal mit einer Bremse

Der Kommentar nennt die Folge nicht mehr — er sagt stattdessen, warum er sie
nicht nennt.

Neu ist ein Test, der prüft, **was der Browser sieht**: vom ersten
`<script>` bis zum ersten Skript-Ende schneiden und das Ergebnis übersetzen
lassen. Ist die Datei dort aufgebrochen, ist das Stück kein gültiges
Programm und der Test wird rot. Dazu die Gegenprobe, dass hinter diesem Ende
nur noch der Abspann der Seite steht. Mutationsprobe: ein Kommentar mit der
Folge irgendwo in der Datei → rot.

`js_pruefen.sh` im Kratzblock trägt jetzt einen Vermerk, dass sein Ergebnis
genau diesen blinden Fleck hatte.

---

## N-34 — Unter der Oberfläche stand ein schwarzer Balken, der Kopf war weg

### Befund

Rückmeldung mit Bild: auf `#/neu` endete die Oberfläche auf halber Höhe, und
darunter lag eine schwarze Fläche über die ganze Breite. Die Kopfzeile mit dem
Seitentitel fehlte, die Seitenleiste zeigte nur noch ihren Fuß
(„Einstellungen").

### Was wirklich passiert war

Die Hülle ist als **Rahmen** gebaut: `html, body { height:100% }`,
`.app { height:100% }`, und gescrollt wird *innen* — in `.flaeche`, im
Themenbaum, in der Verwaltungstabelle. Das Dokument selbst soll nie scrollen.

Es *konnte* aber. An der Wurzel stand kein `overflow`. Sobald irgendetwas dem
`<body>` Höhe gibt — eine Browsererweiterung, die ihr Overlay anhängt, ein Rest
im Körper, eine spät geladene Schrift —, wird das ganze Dokument schiebbar. Die
Hülle ist dann weiterhin fenstergroß, rutscht aber nach oben aus dem Bild: oben
fehlt der Kopf, unten liegt der Rest des Dokuments frei. Und der lag in
`var(--bg)` — im dunklen Thema `oklch(0.16 …)`, also deutlich dunkler als die
Hülle mit `oklch(0.2 …)`. Genau der schwarze Balken.

### Gemessen, nicht überlegt

Nachgestellt im kopflosen Browser bei 1920 × 1000, Ansicht `#/neu`: ein Element
von 520 Pixeln an den Körper gehängt, dann ans Bandende gescrollt.

| | Dokument | scrollbar | gescrollt | Hüllenunterkante | Kopf sichtbar |
|---|---|---|---|---|---|
| vorher | 1000 | 0 | 0 | 1000 (100 %) | ja |
| mit Fremdhöhe | 1520 | 520 | 0 | 1000 (100 %) | ja |
| ans Bandende | 1520 | 520 | 520 | **480 (48 %)** | **nein** |

48 % — dasselbe Verhältnis wie im Bild der Rückmeldung, und derselbe fehlende
Kopf. Damit ist der Weg belegt, nicht nur vermutet.

Was dem Körper im Browser des Nutzers die Höhe gegeben hat, ist von hier aus
nicht feststellbar (im Bild sind mehrere Erweiterungen zu sehen). Es muss auch
nicht feststehen: die Hülle darf sich von *nichts* aus dem Fenster schieben
lassen.

### Behoben

```css
html,body{margin:0;padding:0;height:100%;overflow:hidden}
body{ background:var(--app); … }
```

Zwei Riegel: Die Wurzel scrollt nicht mehr — was die Hülle nicht selbst
scrollt, kann sie nicht verschieben. Und der Körper trägt dieselbe Farbe wie
die Hülle, damit auch dann keine fremde Fläche entsteht, wenn doch einmal etwas
durchscheint.

Nach der Korrektur, derselbe Versuch: Dokument 1000, scrollbar 0, ans Bandende
gescrollt 0, Hüllenunterkante 1000 (100 %), Kopf sichtbar.

### Damit `overflow:hidden` kein Deckel wird

Ein Deckel verdeckt Fehler, statt sie zu beheben. Darum eine zweite Messung
über fünf Ansichten × drei Größen (1920 × 1000, 1280 × 720, 390 × 780): jeder
Kasten, der **nicht** selbst scrollt, muss seinen Inhalt fassen
(`scrollHeight <= clientHeight`). Gefunden: **nichts geklemmt**, in keiner
Ansicht und keiner Größe, und `.flaeche` scrollt weiter da, wo der Inhalt
höher ist als das Fenster (bei 390 × 780 z. B. 1165 Zeilen auf 669 sichtbar).

### Prüflinie

`tests/test_editor.mjs`: *„Die Huelle ist ein Rahmen, kein Schriftstueck
(N-34)"* — verlangt `overflow:hidden` und `height:100%` an der Wurzel und
`background:var(--app)` am Körper.

Mutationsproben (§13a), jede einzeln:

| Mutation | Ergebnis |
|---|---|
| `overflow:hidden` entfernt | 1 Fehler |
| Körperfarbe zurück auf `var(--bg)` | 1 Fehler |
| `height:100%` entfernt | 1 Fehler |
| unverändert | 120 ok, 0 Fehler |

### Was ich dabei falsch gemacht habe

Die Mutationsproben liefen mit `git checkout -- index.html` als Rückweg — und
die Korrektur war noch nicht eingecheckt. Die dritte Probe hat sie mit
weggeräumt, und die Kontrolle stand auf „1 Fehler". Erst das machte es
sichtbar. Eine Probe braucht einen Rückweg, der nicht die eigene Arbeit ist.

## N-35 — „Eine Sache fehlt noch" war ein Satz ohne Weg

### Befund

Rückmeldung, mit Bild von der Leiste: *„Wenn ich da auf Speichern drücke, will
ich zu dem Punkt geführt werden, wo der Fehler ist. Beziehungsweise müssen
Fehler besser erkennbar sein."* Auf dem Bild ist „Eine Sache fehlt noch"
blau hinterlegt — der Nutzer hat es angeklickt, und markiert wurde nur der
Text.

Zwei Sachen waren falsch:

**1. Die Standzeile war ein `<span>`.** Sie sieht aus wie etwas, das man
anklicken kann, und ist es nicht. Ein Klick markiert Text.

**2. Markiert wurden drei von elf Fällen.** `edFehlerMarkieren` kannte genau
drei: fehlender Titel, fehlender Pfad, fehlender Abschnittstitel. Die Prüfung
`edPruefbar` fand aber elf Arten von Befunden. Fehlte etwas anderes — ein
leerer Abschnitt, ein PDF- oder Bild-Baustein ohne Datei, eine unerlaubte
Adresse, ein doppelter Anker, ein zu langer Titel oder Satz —, dann

- wurde **kein Feld markiert**,
- **sprang der Blick nirgendwohin** (`erstes` blieb `null`),
- und die Liste stand in `#ed-bericht` **am Ende des Formulars**, also
  außerhalb des Bildes, wenn man oben war.

Genau der Fall aus der Rückmeldung: „Eine Sache fehlt noch" — und beim Drücken
von *Speichern* passiert sichtbar nichts.

### Behoben

**Eine Quelle, jeder Befund mit Stelle.** `edBefunde()` liefert jetzt Objekte
`{text, ziel}`; `ziel` ist die Kennung des Feldes oder der Karte, um die es
geht. `edPruefbar()` ist nur noch die Textsicht darauf
(`edBefunde().map(b => b.text)`) — zwei Prüfungen wären zwei Wahrheiten.

Die Ziele, alle elf Fälle abgedeckt:

| Befund | Stelle |
|---|---|
| Titel fehlt / zu lang | `ed-titel` |
| Satz zu lang | `ed-kurz` |
| Adresse fehlt / unerlaubt | `ed-slug` |
| Pfad fehlt | `ed-pfad` |
| Abschnittstitel fehlt | `ed-a-titel-«i»` |
| Anker fehlt / doppelt | `ed-a-anker-«i»` |
| Abschnitt leer | `ed-abschnitt-«i»` *(neu vergebene Kennung)* |
| PDF- oder Bild-Baustein ohne Datei | `ed-block-«i»-«j»` |

**Drei Wege zur Stelle**, alle über `edZumFehler(nr)`:

- die **Standzeile** ist ein `<button>` — gesperrt, solange nichts fehlt (ein
  Knopf, der nichts tut, ist schlimmer als kein Knopf), sonst warm hinterlegt
  mit „→ hin";
- **jeder Punkt der Fehlerliste** ist ein Knopf und führt an *seine* Stelle;
- **Speichern, Ansehen und Als Datei sichern** springen von selbst an den
  ersten Befund — erst der Bericht, dann der Sprung, damit der Blick am Ende
  auf der Stelle steht und nicht auf dem Bericht.

**Besser erkennbar:** Die Meldung steht jetzt **am Feld** (`.ed-fehlerzeile`,
warm hinterlegt, mit Balken links) — am Feld darunter, an einer Karte oben,
weil „darunter" bei einem langen Kasten weit weg von der Sache wäre. Felder
bekommen `aria-invalid`, Karten `data-fehler="1"` mit warmem Rand. Und wer im
Feld etwas ändert, verliert Marke **und** Meldung dazu (`edMarkeWeg`) — sonst
stünde dort weiter „fehlt der Titel", während der Titel schon da ist.

### Im Browser gefahren (CLAUDE.md §14, CLAUDE.md)

Leere Vorlage geöffnet, *Speichern* gedrückt, nichts ausgefüllt — 1440 × 900:

| | Wert |
|---|---|
| Standzeile | `BUTTON`, „4 Sachen fehlen noch", nicht gesperrt |
| Meldungen am Feld | **4** |
| markierte Felder / Karten | **3 / 1** ← die Karte ist der Fall, den es vorher nicht gab |
| Punkte in der Liste | **4**, alle anklickbar |
| erste Meldung im Bild | **ja** |
| Konsolenfehler | **0** |

Dann weit weggescrollt (`flaeche.scrollTop` 1477, erste Meldung außer Bild)
und die Standzeile gedrückt → `scrollTop` 0, erste Meldung im Bild.

Und jeder Punkt der Liste einzeln, jedes Mal vorher ans Ende gescrollt:

| Punkt | Meldung im Bild | `scrollTop` danach |
|---|---|---|
| Der Seite fehlt der Titel. | ja | 0 |
| Der Pfad im Themenbaum fehlt. | ja | 0 |
| Abschnitt 1 hat keinen Titel. | ja | 321 |
| Im Abschnitt 1 steht noch nichts. | ja | 187 |

Titel getippt → markierte Felder 3 → **2**, Meldungen 4 → **3**, Standzeile
„3 Sachen fehlen noch".

Kontrast der neuen Teile, gegen den Grund gemessen, der wirklich dahinterliegt:
schlechtester Wert **7,69:1** (dunkel) und **6,38:1** (hell) — verlangt sind
4,5:1.

Klickdurchlauf über alle sechs Ansichten danach: 79 Klicks, **0**
Konsolenfehler, Oberfläche intakt.

### Prüflinien

`tests/test_editor.mjs`, fünf neue Linien. Die Erwartungen von Hand (§13) —
ein Zustand, der alle Arten auslöst, ergibt zehn Befunde in dieser Reihenfolge:

```
ed-titel, ed-kurz, ed-slug, ed-pfad,
ed-a-titel-0, ed-abschnitt-0, ed-block-0-0,
ed-a-anker-2, ed-abschnitt-2, ed-block-2-0
```

Der eigentliche Zahn ist *„Jede genannte Stelle gibt es wirklich"*: jedes
`ziel` wird gegen `id="…"` in `index.html` geprüft. Ein verschriebenes Ziel
wäre ein Sprung ins Leere — und der sieht genauso aus wie der Fehler aus der
Rückmeldung.

Mutationsproben (§13a), jede einzeln angebracht und zurückgenommen:

| Mutation | Ergebnis |
|---|---|
| einem Befund die Stelle nehmen (`ziel: null`) | 3 Fehler |
| Ziel verschrieben (`ed-abschnit-`) | 3 Fehler |
| Standzeile wieder als `<span>` | 1 Fehler |
| Fall `zumfehler` aus dem Verteiler entfernt | 1 Fehler |
| `edPruefbar` mit eigener Wahrheit (`return []`) | 3 Fehler |
| Sperre der Standzeile entfernt | 1 Fehler |
| unverändert | 125 ok, 0 Fehler |

Diesmal lief der Rückweg der Proben über eine Kopie im Kratzblock, nicht über
`git checkout` — die Lehre aus `N-34`.

## N-36 — „Eine HTML anfügen" führte auf eine schwarze Seite

### Befund

Rückmeldung mit Bild: `wiki.prolo.me/#/neu`, eine HTML-Datei anfügen — und die
Seite ist **vollständig leer**. Nicht nur ein Balken unten wie bei `N-34`,
sondern gar nichts: keine Seitenleiste, keine Kopfzeile, kein Inhalt.

### Was wirklich passiert war

Auf dem Startbildschirm führt die Kachel *„Ich habe eine HTML-Datei"* in den
Editor und klappt die Ablage auf. Damit man sie nicht suchen muss, stand dort:

```js
karte.open = true;
karte.scrollIntoView({block:'center'});
```

`scrollIntoView` scrollt aber nicht *einen* Kasten, sondern **jeden
scrollbaren Vorfahren** bis zur Wurzel. Der gewollte ist `.flaeche`. Der
zweite ist der Körper — und der hat seit `N-34` `overflow:hidden`. Das nimmt
ihm die Bildlaufleiste, macht ihn aber **nicht** unscrollbar: vom Programm
lässt er sich sehr wohl schieben. `block:'center'` wollte die Karte in die
Mitte des Fensters rücken und schob dafür den Körper um gut tausend Pixel.

Danach stand die Hülle vollständig außerhalb des Fensters — und weil es keine
Leiste gibt, gab es **keinen Weg zurück**. Nur die Farbe des Körpers war noch
zu sehen.

Bitter daran: `N-34` hat diesen Fall verschärft. Vorher scrollte das Dokument
mit sichtbarer Leiste, und man konnte zurückscrollen. Der Riegel gegen den
schwarzen Balken hat aus einem Ärgernis eine Sackgasse gemacht.

### Gemessen, nicht überlegt

Kopfloser Browser, 1440 × 900, `#/neu` → Kachel *„Ich habe eine HTML-Datei"* →
Datei über das Feld eingehängt (`DataTransfer`) → *In den Editor laden*:

| Schritt | `.app` oben..unten | Seitenleiste | Kopfzeile |
|---|---|---|---|
| Startbildschirm | 0 .. 900 | sichtbar | sichtbar |
| **Ablage offen** | **−1022 .. −122** | **nein** | **nein** |
| Bericht da | −1022 .. −122 | nein | nein |
| In den Editor geladen | −1022 .. −122 | nein | nein |

Und dabei: `dokScroll 0`, `window.scrollY 0`. Das Dokument war also gar nicht
gescrollt — der **Körper** war es. Genau darum war nichts mehr zu sehen und
nichts mehr zu erreichen.

Nach der Korrektur, dieselbe Strecke: `0 .. 900` in allen vier Schritten,
Seitenleiste und Kopfzeile durchgehend sichtbar, 0 Konsolenfehler, und *In den
Editor laden* füllt Titel („Netzwerk Grundlagen") und **3** Abschnitte.

### Behoben

**Erster Riegel — nur den eigenen Kasten scrollen.** Neu `hinscrollen(el,
mitte)` mit `scrollKasten(el)`: es sucht den nächsten Vorfahren, der wirklich
senkrecht scrollt, und setzt dessen `scrollTop` selbst. Gibt es keinen, ist
nichts zu tun. Alle sechs Aufrufe der Hülle gehen jetzt darüber.

Die **drei Aufrufe im Pflichtteil der Seite bleiben** `scrollIntoView` — dort
ist das Dokument der richtige Scrollbereich, weil die Seite in ihrem eigenen
Rahmen läuft.

**Zweiter Riegel — die Hülle hängt am Fenster.**

```css
.app{position:fixed;inset:0;display:flex;height:100%;background:var(--app)}
```

Ein Element mit fixer Lage hängt am Fenster, nicht am Körper. Kein Scrollen
des Körpers kann die Hülle mehr verschieben — auch keins, das erst morgen
dazukommt.

**Und das Scrollen tut weiter, was es soll:** Kachel gedrückt →
`flaeche.scrollTop` 0 → **1351**, Karte offen und im Bild, Hülle unverändert
bei 0 .. 900. Der Fehlerweg aus `N-35` ebenso: alle vier Punkte der
Fehlerliste landen bei ihrer Meldung im Bild, mit denselben Werten wie vor der
Umstellung (0, 0, 321, 187).

### Prüflinie

`tests/test_editor.mjs`: *„Die Huelle scrollt nur ihre eigenen Kaesten
(N-36)"* — kein `scrollIntoView`-**Aufruf** in der Hülle (der Pflichtteil wird
herausgerechnet), `hinscrollen` und `scrollKasten` vorhanden, `.app` mit
`position:fixed` und `inset:0`.

Gesucht wird der Aufruf (`.scrollIntoView(`), nicht das Wort: der Kommentar in
`hinscrollen` nennt `scrollIntoView` absichtlich, damit der nächste Leser
weiß, warum es dort nicht steht. Die erste Fassung der Prüfzeile suchte das
Wort und fiel über genau diesen Kommentar — dieselbe Falle wie `N-33`, nur
umgekehrt.

Mutationsproben (§13a), Rückweg über eine Kopie im Kratzblock:

| Mutation | Ergebnis |
|---|---|
| ein `scrollIntoView` zurück in die Hülle | 1 Fehler |
| `position:fixed` entfernt | 1 Fehler |
| `inset:0` entfernt | 1 Fehler |
| `hinscrollen` umbenannt | 1 Fehler |
| unverändert | 126 ok, 0 Fehler |

### Was `position:fixed` sonst noch berührt

Nachgemessen, weil eine fixe Lage die Stapelung ändern kann: `#pdf-schau`
(`z-index:70`) liegt bei 1440 × 900 **und** bei 390 × 780 über der Hülle
(`elementFromPoint` trifft sie). Nichts geklemmt in fünf Ansichten × drei
Größen. Klickdurchlauf 79 Klicks (1440 px) und 81 Klicks (390 px), je 0
Konsolenfehler.

### Ein Fehlalarm, der dabei auffiel

Beim Nachmessen sah das Menü am Handy kaputt aus: `data-menue="1"` gesetzt,
`aria-expanded="true"` — und die Seitenleiste stand weiter bei
`translateX(-248px)`. Vor der Umstellung genauso, also kein Rückschritt, aber
ein Befund?

Nein. Mit `sl.style.transition='none'` wird `transform` zu `none` und die
Leiste steht bei 0: die Regel `body[data-menue="1"] #seitenleiste` gewinnt
sehr wohl. **Hinter einem CSS-Übergang kann dieser Aufbau nichts messen** —
mit `--virtual-time-budget` läuft ein `transition` nicht weiter, der
berechnete Wert bleibt auf dem Anfangswert stehen. Steht jetzt als dritte
Lehre in `tests/README.md`.

## N-37 — Was im Repo lag und nicht gebraucht wurde

### Auftrag

„Check mal das ganze Repo und werf alles weg, das nicht gebraucht wird." Also
120 Dateien einzeln durchgegangen, mechanisch statt nach Gefühl: welche Datei
wird von keiner anderen erwähnt, welche Klasse steht im Stil und nirgends im
Markup, welche Funktion ist definiert und wird nie gerufen.

### Was wirklich weg konnte

**Zwei Funktionen, die nur noch ihr eigener Test gerufen hat.** Das ist die
schlimmere Sorte totes Holz: der Test ist grün, und er prüft nichts am
laufenden Code.

| Funktion | Aufrufer im Programm |
|---|---|
| `fts_ausdruck(begriff)` in `server.py` | **keiner** — vier Prüfzeilen in `test_suche.py` |
| `edPruefbar(nurNachsehen)` in `index.html` | **keiner** — vier Stellen in `test_editor.mjs` |

Beide waren Einzeiler vor einer echten Funktion, und beide hatten ihre
Aufrufer im Programm bei früheren Arbeitsschritten verloren: `fts_ausdruck` an
`fts_ausdruck_aus_teilen` (Suchoperatoren), `edPruefbar` an `edBefunde`
(`N-35`). Nicht bemerkt, weil die Tests weiterliefen.

Weg damit — und die Tests gehen jetzt den Weg, den der Server geht: in
`test_suche.py` steht ein Helfer `ausdruck()`, der `suchbegriff_lesen` und
`fts_ausdruck_aus_teilen` verkettet (genau wie `suchen()`), in
`test_editor.mjs` einer namens `texte()` über `edBefunde`. Die Prüfzeile, die
nur die beiden Fassungen verglich, fällt mit weg: es gibt nur noch eine.

**Eine Datei, die von nirgendwo aus zu finden war.**
`wiki/test-isolierung.html` lag neben `server.py` und wurde von keiner Datei
erwähnt. Wegwerfen wäre falsch gewesen — es ist die Abnahmehilfe, mit der man
prüft, ob der abgeschottete Rahmen wirklich hält (vier verbotene Zugriffe, alle
müssen „blockiert" melden). Sie liegt jetzt als
`wiki/tests/isolierung-probe.html` dort, wo man sie sucht, und `tests/README.md`
sagt, was sie ist. In `vorlagen/` kann sie nicht liegen: sie enthält mit
Absicht zwei Fehler, und `test_seiten.py` würde sie zu Recht beanstanden.

### Was gar nicht erst in den Baukontext gehört

Das Bordbuch hatte eine `.dockerignore`, das Wiki **keine** — und die des
Bordbuchs war unvollständig (`tests/`, `aktualisierung.conf` fehlten). Docker
überträgt vor jedem Bau den ganzen Ordner an den Dienst, auch was das
`Dockerfile` nie kopiert.

Gemessen, mit Docker-Semantik für die Muster (`*` springt nicht über `/`):

| | Dateien vorher | danach | Größe vorher | danach |
|---|---|---|---|---|
| `wiki/` | 50 | **15** | 1149,9 kB | **510,9 kB** |
| `bordbuch/` | 41 | **15** | 1016,0 kB | **661,5 kB** |

Übrig bleiben in beiden genau die fünfzehn, die gebraucht werden: `Dockerfile`,
`server.py`, `index.html`, die neun Schriftdateien mit ihren Lizenzen,
`.dockerignore` und `.gitignore`.

Die Ablagen `daten/` und `seiten/` stehen trotzdem in der Liste. Im Betrieb
liegen sie in benannten Docker-Volumes, nicht im Ordner — aber beim Lauf ohne
Docker (Tests, Vorführung) entstehen sie dort, und dann gehören eine Datenbank
und fremde Seiteninhalte erst recht nicht in den Baukontext.

### Was geprüft und ausdrücklich behalten wurde

Wegwerfen ist einfach; das Behalten braucht den Grund.

| Verdacht | Warum es bleibt |
|---|---|
| `wiki/.gitignore`, `bordbuch/.gitignore` — die Wurzeldatei deckt alles ab | CLAUDE.md §21 verlangt **zusätzlich eine je Tool**: die Wurzeldatei ist leicht zu übersehen, und ein Tool bringt seine Regel dort mit, wo die Daten entstehen |
| `traefik/logrotate.conf` — von nirgendwo erwähnt | erklärt sich selbst: der Einrichtungsbefehl steht im Kopf der Datei |
| `bordbuch/tests/gegenprobe.sh` — läuft nicht in `alle.sh` | Absicht: sie baut echte Fehler in `server.py` ein und prüft die Testsuite selbst. Von Hand, nicht bei jedem Lauf |
| dieselben neun Schriftdateien in beiden Tools | zwei getrennte Baukontexte — ein gemeinsamer Ordner wäre von keinem `Dockerfile` erreichbar |
| drei Seiten in `vorlagen/`, die niemand nennt | `test_seiten.py` nimmt den ganzen Ordner per `glob` |
| `tests/hilfe.py` in beiden Tools | wird als **Modul** importiert (`from hilfe import server`), nicht über den Dateinamen |

### Und was gar nichts hergab

- **Klassen im Stil, die niemand benutzt:** 113 Klassen in der Wiki-Hülle,
  120 im Bordbuch, **keine einzige** ungenutzt. (`N-25` war der letzte Fall,
  und der ist behoben.) Im Seitenstil des Editors: 7 Klassen, alle benutzt.
- **Serverpfade, die die Hülle nie ruft:** keine.
- **`TODO`, `FIXME`, `XXX`, `HACK`:** kein einziges Vorkommen im ganzen Repo.

Das Ergebnis ist also kurz: fünf Stellen, davon zwei totes Holz im Programm.
Der Rest des Repositorys trägt sich.

## N-38 — `prolo` wusste vom neuen Stand und holte ihn nicht

### Befund

Auftrag: *„Erweitere das Tool prolo, dass es beim Update selbst die Repo auf
Aktualisierungen prüft."*

Geprüft hat es schon — seit `#11` steckt in `aktualisieren.sh` eine
Quellstand-Prüfung, die `git fetch` macht und bei Rückstand abbricht. Drei
Dinge fehlten trotzdem:

1. **Geholt hat sie nie.** Der Lauf meldete „1 Commit(s) HINTER origin" und
   brach ab; `git pull` musste der Mensch von Hand tippen. Genau derselbe
   Griff, jedes Mal — und genau solche Griffe vergisst man.
2. **Sie lief nur beim Aktualisieren.** `prolo status` zeigte Tools, Namen,
   Zertifikate, Sicherung und Archiv — aber nicht, ob der Stand auf der Platte
   überhaupt der neueste ist. Dabei ist „ich habe vergessen zu ziehen" die
   häufigste Ursache dafür, dass eine Änderung nicht ankommt. `prolo pruefen`
   (Trockenlauf) sah sie ebenfalls nicht: die Prüfung saß hinter
   `if [ "$TROCKEN" -eq 0 ]`.
3. **Sie stand mitten im Skript**, also an genau einer Stelle benutzbar.

### Behoben

**Eine Stelle, drei Aufrufer.** Neu `werkzeuge/quellstand.sh`:

| Aufruf | Was es tut |
|---|---|
| `--pruefen` | nachsehen, berichten, die bereitliegenden Commits auflisten |
| `--holen` | nachsehen und, wenn nötig, vorspulen |
| `--kurz` | eine Zeile, für `prolo status` |

Rückgabewerte statt Text-Auswertung: `0` aktuell, `10` hinterher, `11` nicht
prüfbar, `20` geholt, `1` Holen ging nicht.

Benutzt von `aktualisieren.sh` (in der Vorprüfung und zum Holen), von
`prolo status` (eine Zeile) und vom neuen Befehl **`prolo quelle [--holen]`**.

**`prolo aktualisieren` holt jetzt selbst** — vor der Sicherung, vor dem Bau.
`--ohne-holen` behält das alte Verhalten (den Stand auf der Platte bauen),
`--trocken` fasst nichts an.

**Und startet danach neu.** Der Pull kann `aktualisieren.sh` *selbst* ersetzt
haben, und Bash liest ein Skript häppchenweise von der Platte —
weiterzulaufen hieße, halb die alte und halb die neue Fassung auszuführen.
Also `exec` mit denselben Argumenten, einmal, gesichert über eine Marke in der
Umgebung.

**Zwei Fälle, in denen ausdrücklich NICHT geholt wird**, beide mit dem Weg
heraus statt mit einem stillen Fehlschlag (CLAUDE.md §15):

- **eigene Änderungen an verfolgten Dateien** → Abbruch, der Stand bleibt
  stehen, die Dateien werden aufgelistet;
- **auseinandergelaufene Stände** (voraus *und* zurück) → Vorspulen geht
  nicht, und zusammenführen soll dieses Skript nicht.

Unverfolgte Dateien blockieren dagegen **nicht**: git bricht von sich aus ab,
falls eine geholte Datei eine von ihnen überschreiben würde, und diese Meldung
wird weitergegeben. Sie mitzuzählen hieße, dass ein vergessenes Notizblatt im
Ordner jede Aktualisierung blockiert.

Dazu der Fall, der auf dem Server wirklich vorkommt: gehört `/opt/stack` einem
anderen Nutzer, verweigert git jede Auskunft („dubious ownership") — und das
sieht aus wie „kein Netz". Jetzt steht die Abhilfe dabei.

### Zwei eigene Fehler, beide vom Ausführen gefunden

**`set -e` hat den Lauf stumm beendet.** `aktualisieren.sh` und `prolo` laufen
mit `set -euo pipefail`. `quellstand.sh` meldet seine Lage über den
Rückgabewert — und ein Rückgabewert ≠ 0 ist unter `set -e` ein Abbruch. Der
erste Testlauf zeigte es sofort:

```
=== Quellstand ===
  Quellstand         1 Commit(s) HINTER origin/haupt
  Holen ... (git pull --ff-only origin haupt)
  Geholt: 1 Commit(s), Stand jetzt 48bd721.
```

…und dann nichts mehr. Kein Neustart, kein Bau, keine Meldung. Behoben mit
`|| ERGEBNIS=$?` an allen vier Aufrufstellen — und der Grund steht als
Kommentar daneben, weil das beim Lesen niemand sieht.

**Eine Prüfzeile ohne Zähne.** Der Test für den Neustart suchte die *Meldung*
„Neustart mit dem geholten Stand". Als ich zur Probe das `exec` durch ein `:`
ersetzte, blieb er grün — die Ankündigung stand ja noch da. Eine Meldung ist
kein Beweis. Jetzt zählt er, wie oft der Lauf **beginnt**: nach einem Neustart
steht die Kopfzeile zweimal da.

**Und fast ein dritter:** `URSPRUNG="$*"` gab es in `aktualisieren.sh` schon —
für die Meldungen „`sudo $0 --ohne-sicherung <dieselben Tools>`". Mein Feld für
den Neustart hätte es überschrieben, und `"$URSPRUNG"` wäre auf sein erstes
Wort zusammengeschrumpft. Beim Durchlesen des eigenen Diffs aufgefallen, vor
dem ersten Lauf. Heißt jetzt `AUFRUF`.

### Ausgeführt

`werkzeuge/aktualisieren-pruefen.sh`, 25 neue Prüfzeilen gegen einen echten
Git-Aufbau (ein „fernes" Repo mit einem Commit mehr):

| | |
|---|---|
| hinterher | Rückgabe 10, Zahl in der Meldung, der bereitliegende Commit wird benannt, der Weg zum Holen steht dabei |
| `--kurz` | genau **eine** Zeile |
| holen | Rückgabe 20, der Stand bewegt sich wirklich, die geholte Fassung liegt da, danach „aktuell" |
| eigene Änderung | Rückgabe 1, Stand bleibt, **Datei bleibt, wie sie war** |
| unverfolgte Datei | blockiert nicht, und bleibt liegen |
| auseinandergelaufen | Rückgabe 1, Stand bleibt, Grund wird benannt |
| ohne Git | Rückgabe 11, „nicht prüfbar" statt einer Behauptung |
| über `aktualisieren.sh` | holt selbst, **beginnt zweimal**, holt dabei genau einmal, baut danach wirklich |
| `--ohne-holen` | baut den Stand auf der Platte, holt wirklich nicht |
| `--trocken` | holt nicht |

`werkzeuge/prolo-pruefen.sh`, 6 weitere: `prolo quelle` gibt **0** zurück,
obwohl der Stand zurückhängt (eine Auskunft ist kein Fehlschlag), nennt die
Zahl; `prolo status` zeigt sie in einer Zeile; `--kurz` geht dafür
ausdrücklich **nicht** ins Netz, sagt aber, dass es übersprungen wurde; die
Hilfe nennt den Befehl.

Mutationsproben (§13a), Rückweg über Kopien im Kratzblock:

| Mutation | Ergebnis |
|---|---|
| `\|\| HOL_ERGEBNIS=$?` entfernt (also `set -e` zuschlagen lassen) | 4 Fehler |
| `exec` entfernt | 1 Fehler *(erst nach der Verschärfung der Prüfzeile — vorher 0)* |
| eigene Änderungen werden ignoriert | 1 Fehler |
| unverfolgte Dateien blockieren doch | 11 Fehler |
| `--trocken` holt doch | 1 Fehler |
| `prolo quelle` gibt 10 durch | 1 Fehler |
| Quellstand aus `status` entfernt | 1 Fehler |
| Quellstand auch bei `--kurz` | 1 Fehler |
| unverändert | 0 Fehler |

Dazu alle vorhandenen Gegenproben unverändert grün:
`aktualisieren-pruefen.sh`, `prolo-pruefen.sh`, `dockerfile-pruefen.sh`,
`schriften-pruefen.sh`.

## N-39 — Zwei Regeldateien, 148 Verweise, und keiner davon geprüft

### Auftrag

„Die alten `anleitungen.md` können weg und in die `CLAUDE.md` umgezogen
werden."

Es gab drei Dateien mit Regeln: `CLAUDE.md` (57 Zeilen, eine Kurzfassung),
`prolo-regelblatt.md` (562 Zeilen, Oberfläche und Codequalität) und
`prolo-betriebsregeln.md` (1104 Zeilen, Betrieb). Die Kurzfassung sagte
selbst, die beiden anderen seien „im Zweifel maßgeblich" — also musste man
immer alle drei lesen.

### Was daraus wurde

**Eine Regeldatei.** `CLAUDE.md`, 821 Zeilen, in vier Teilen: wie hier
gearbeitet wird, Oberfläche, Robustheit, Betrieb, dazu die Checkliste. Die
Nummerierung des Regelblatts (§1–§15) bleibt erhalten, weil hunderte Verweise
darauf stehen; die Betriebsregeln schließen ab §16 an.

**Was dabei nicht mitgewandert ist**, und warum:

| Was | Wohin |
|---|---|
| die **Handgriffe** (neuer Server, Tool einhängen, Alltag, Sichern, Wiederherstellen, Fehlersuche) | in die Wiki-Seite „Prolo bedienen und verstehen" — sie sind Bedienung, keine Regel |
| die abgedruckten **Skripte** (`backup.sh`, `backup-sync.sh`, der Wachhund für die Sicherung) | sie liegen als echte Dateien im Repository und erklären sich dort selbst |
| die **Entstehungsgeschichte** jeder Regel | steht hier in `NEUE-BEFUNDE.md`, wo sie hingehört |

**Drei Token sind endlich eingetragen.** Das Regelblatt sagte „gibt es kein
passendes Token, wird eines ergänzt — ergänzt werden muss es dann aber hier"
und führte `--danger`, `--on-accent` und `--overlay` in einer Fußnote, ohne
Werte. Die Werte stehen im Wiki und im Bordbuch längst; jetzt stehen sie im
Tokenblock.

### Der eigentliche Aufwand: die Verweise

Quer durch den Stack standen **148 Verweise** auf die beiden Dateien — in
Kommentaren, Tests, Meldungen, `.conf`-Dateien, sogar in `.gitignore`. Die
Regelblatt-Nummern stimmen weiter; die Betriebsregeln-Nummern haben sich alle
verschoben (`Betriebsregeln 5` → `§19`, `10` → `§21`, `12` → `§22`,
`13`–`17` → `§23`, `19a` → `§24a`, `23` → `§25` …).

Ein Verweis auf einen Abschnitt, den es nicht mehr gibt, fällt beim Lesen
**nicht** auf: er sieht aus wie eine Begründung und ist eine Sackgasse. Also
mechanisch umgeschrieben, in 46 Dateien, und danach 22 Nennungen ohne Nummer
von Hand nachgezogen.

### Die Prüflinie, die das festhält

Neu: `werkzeuge/regeln-pruefen.sh`. Es prüft drei Dinge:

1. **Jeder Verweis `CLAUDE.md §N` trifft einen Abschnitt, den es gibt.**
   Gemessen: 29 verschiedene Abschnitte werden zitiert, alle vorhanden.
2. **Niemand nennt die beiden abgeschafften Dateien mehr.**
3. **`CLAUDE.md` bringt die Blöcke mit, auf die sich die Werkzeuge berufen:**
   Farbtoken, Pflichtblock für Fokus, `[hidden]`, Checkliste.

Mutationsproben (§13a), Rückweg über Kopien im Kratzblock:

| Mutation | Ergebnis |
|---|---|
| ein Verweis zeigt ins Leere (`§11` → `§99`) | 1 Fehler |
| jemand nennt wieder eine der alten Dateien | 1 Fehler |
| der Farbtokenblock fällt aus `CLAUDE.md` | Fehler |
| die Checkliste fällt weg | Fehler |
| unverändert | 0 Fehler |

### Zum dritten Mal dieselbe Falle

Der erste Lauf des neuen Prüfskripts meldete zwei Fehler — **über sich
selbst**: sein eigener Kommentar erklärte, warum es die alten Dateinamen
sucht, und nannte sie dabei. Dasselbe Muster wie `N-33` (ein Kommentar mit
`</script>` schaltete die Oberfläche ab) und `N-36` (eine Prüfzeile suchte das
Wort `scrollIntoView` und fiel über den Kommentar, der es erklärt).

Gelöst wie dort: die Namen werden zusammengesetzt statt ausgeschrieben
(`"prolo-" + "regelblatt.md"`).

Und ein viertes Mal, im selben Arbeitsschritt: der Eintrag in
`wiki/CHANGELOG.md`, der das Zusammenziehen beschreibt, nannte die beiden
Dateien beim Namen — das Prüfskript schlug an, und ich hatte den Fehlschlag
zunächst übersehen, weil `bash … | tail -2` den Rückgabewert von `tail`
liefert, nicht den des Skripts. Also gepusht mit rotem Prüflauf. Die Lehre
steht in den Regeln: eine Prüfung wird nicht durch eine Pipe gelesen.

Eine Ausnahme gibt es trotzdem, und die ist ausdrücklich: **diese Datei
hier.** Ein Archiv nennt, was es nicht mehr gibt — das ist sein Zweck. Damit
die Ausnahme kein Versteck wird, zählt das Prüfskript die Nennungen und
schreibt sie hin:
`(im Archiv NEUE-BEFUNDE.md genannt: prolo-betriebsregeln.md 1x, prolo-regelblatt.md 1x)`.

### Was ausdrücklich geblieben ist

`bordbuch/ANLEITUNG.md` und `wiki/EINRICHTUNG.md` sind **keine** „alten
Anleitungen", sondern die Handbücher der beiden Werkzeuge: das eine
beschreibt die Bedienung des Bordbuchs im Einzelnen, das andere den
Seitenaufbau des Wikis, auf den sich Editor, Import und Tests berufen. Beide
sind jetzt in `CLAUDE.md` genannt, damit man sie findet.

## N-40 — Die Warnung, die bei jeder Seite anging

### Wie es aufgefallen ist

Die fertige Anleitung `prolo-bedienen.html` wurde eingespielt. Über dem
Knopf „Übernehmen" stand:

> **Was diese Seite mitbringt**
> · 1 Skriptblock(e) mit zusammen 12534 Zeichen. Die Seite bringt eigenen Code mit.
> · parent. – die Seite greift nach der Huelle

Die Frage dazu war die richtige: *Warum passiert sowas?*

### Was gemessen wurde

`sicherheit_pruefen()` über alle mitgelieferten Seiten:

| Seite | Hinweise |
|---|---|
| `bausteine-im-editor.html` | 12534 Zeichen · `parent.` |
| `drucker-einrichten.html` | 12534 Zeichen · `parent.` |
| `git-und-github.html` | **13134** Zeichen · `parent.` |
| `netzwerk-grundlagen.html` | 12534 Zeichen · `parent.` |
| `prolo-bedienen.html` | 12534 Zeichen · `parent.` |
| `stromkosten-verstehen.html` | 12534 Zeichen · `parent.` |

**Jede** Seite, und auf das Zeichen dieselbe Zahl. Die 12534 sind der
**Pflichtteil** — der Skriptblock, den `edSeiteBauen` in jede Seite legt:
Inhaltsverzeichnis, Sprung zum Anker, Markieren bei „In dieser Seite suchen",
die PDF-Bausteine. Die `parent.`-Stellen sind die fünf
`window.parent.postMessage`-Aufrufe darin, die einzige Verbindung, die eine
Seite zur Hülle hat: sie läuft in einem **opaken Origin** (Sandbox ohne
`allow-same-origin`), und die Hülle nimmt eine Nachricht nur an, wenn sie aus
ihrem eigenen Rahmen kommt.

Die Meldung war also **wahr** und trotzdem **falsch**. Der Pflichtteil ist
nicht, was der Einspielende sich holt; er ist, was das Wiki dazugibt.

### Warum das mehr ist als Kosmetik

Die Prüfung machte dieselbe Überlegung **eine Zeile weiter oben schon** — der
JSON-Metablock wird aus der Zählung genommen, mit dieser Begründung im Code:

> „er darf die Zaehlung nicht aufblaehen, sonst meldet die Pruefung bei jeder
> voellig harmlosen Seite einen Skriptblock und wird nicht gelesen."

Genau das war beim Pflichtteil eingetreten, eine Stufe höher. Eine Warnung,
die immer angeht, bringt bei, sie wegzuklicken — und dann rutscht die eine
Seite durch, die wirklich etwas Fremdes mitbringt. In der Tabelle oben steht
so ein Fall: `git-und-github.html` bringt **600 Zeichen eigenen Code** über
den Pflichtteil hinaus, und in dieser Darstellung sah man den Unterschied
nicht.

### Was daraus wurde

Der Pflichtteil wird **wiedererkannt** und aus der Zählung genommen — aber
nur bei **exakter** Übereinstimmung.

- `index.html` trägt neben dem Pflichtteil seinen **Fingerabdruck**
  (`ED_PFLICHTTEIL_KENNUNG`, SHA-256). Er steht dort und nicht in einer
  eigenen Datei, damit die beiden Stände nicht auseinanderlaufen können.
- `pflichtteil-nachziehen.mjs` hält ihn auf dem Stand, `test_editor.mjs`
  verlangt es.
- `server.py` liest ihn aus `index.html` und vergleicht den Block einer
  eingespielten Seite Zeichen für Zeichen.

Drei Fälle, drei Antworten:

| Fall | Was gemeldet wird |
|---|---|
| Pflichtteil stimmt | **nichts** — und der Zusatz „(Der Pflichtteil des Wikis ist dabei nicht mitgezählt.)", falls die Seite eigenen Code hat |
| Pflichtteil weicht ab | „nicht der dieser Hülle … sieh ihn dir an; oder speichere die Seite einmal durch den Editor" — **und** der ganze Block zählt wieder als Code der Seite |
| Fingerabdruck nicht lesbar | alles wie vor `N-40` — keine stille Entwarnung |

Gemessen danach: fünf Seiten melden **gar nichts** mehr, `git-und-github.html`
meldet seine **600 Zeichen** — die Information, die vorher unterging.

### Die Probe

| Mutation | Ergebnis |
|---|---|
| ein **Leerzeichen** im Pflichtteil | „nicht der dieser Hülle" + 12535 Zeichen als eigener Code |
| `fetch('//fremd.tld/x')` in den Pflichtteil geschmuggelt | Abweichung **und** `fetch(` gemeldet |
| eigener Block daneben | nur dessen 27 Zeichen, `localStorage` gemeldet |
| Fingerabdruck auf `None` | Meldung wie vor `N-40` |
| Fingerabdruck um ein Zeichen verdreht | 1 Fehler (Node) |
| das `continue` entfernt, das den Pflichtteil herausnimmt | 9 Fehler (Python) |
| Hashvergleich immer wahr | 2 Fehler (Python) |
| Marke umformuliert, Fingerabdruck nachgezogen | 1 Fehler (Node) |
| unverändert | 0 Fehler |

### Und ein eigener Fehler dabei

Die letzte Probe hat mehr angefasst, als ich gesichert hatte. Im Kratzblock
lagen `index.html` und `server.py` — aber die Probe rief
`pflichtteil-nachziehen.mjs --schreiben`, und das schreibt **alle sieben
Seiten** mit. Nach dem Zurückrollen waren 17 Prüflinien rot.

Die Lehre schärft die Regel aus `N-34`: gesichert wird nicht, was die Probe
verändert, sondern **alles, was sie schreiben kann** — bei einem Erzeuger
also seine Ausgaben, nicht seine Eingaben. Die sieben Seiten ließen sich
hier gefahrlos aus git zurückholen, weil ihr Unterschied nachweislich aus
genau einer Zeile bestand (der Mutation selbst) und keine eigene Arbeit
darin lag; nachgesehen wurde das **vor** dem Zurückholen, nicht danach.

## N-41 — Das Werkzeug lehnte die Datei ab, um die es selbst gebeten hatte

### Wie es aufgefallen ist

Im selben Zug wie `N-40`: *„Wenn ich den Prompt ausführe und die HTML
einfüge kommt auch der Fehler."*

### Was gemessen wurde

Eine Datei, die **genau** dem Gerüst aus dem Prompt „Eine KI schreiben
lassen" folgt — Meta-Block mit `markup`, leerer `<body>`, kein CSS, kein
Skript —, durch dieselbe Prüfung geschickt, die beim Einspielen läuft:

```
FEHLER:    Im <body> steht fast kein sichtbarer Text (0 Zeichen). …
WARNUNGEN: Zum Anker 'vorbereitung' gibt es im HTML kein Element mit id=…
           Zum Anker 'einrichten'   gibt es im HTML kein Element mit id=…
           Es fehlt die viewport-Angabe. …
           Der Pflichtblock aus CLAUDE.md §8.1 fehlt …
```

**Ein Fehler, vier Warnungen** — unter der roten Überschrift „Nicht
übernehmbar". Der Prompt sagt wörtlich „Schreibe deshalb KEIN CSS, KEIN
JavaScript und keine eigene Gestaltung", und das Wiki wies die Datei
dann dafür ab. Alle vier Warnungen betrafen Dinge, die der Editor selbst
baut: Kopfangaben, Pflichtblock, `lang`, die Abschnitte samt ihrer `id`.

Einen Weg gab es: den Kasten „Aber der Inhalt ist lesbar" mit dem Knopf
„In den Editor laden". Er stand aber **unter** der roten Liste — nach fünf
Punkten, die aussahen, als sei etwas kaputt.

### Was daraus wurde

Ein **Entwurf** ist ein eigener Zustand, kein misslungener Versuch.
`ist_entwurf()` erkennt ihn an drei Dingen zusammen: die Werkzeugmarke
`editor-1`, `markup` in **jedem** Abschnitt und ein leerer Körper.

| | vorher | jetzt |
|---|---|---|
| Überschrift | „Nicht übernehmbar" (rot) | „Ein Entwurf — noch keine Seite" (neutral) |
| Punkte | 1 Fehler + 4 Warnungen | **einer**, und der ist der nächste Schritt |
| Knopf | unter der Liste | **in** der Karte, als Hauptsache |

Übernehmbar ist ein Entwurf weiter **nicht** — sonst stünde eine leere
Fläche im Themenbaum (`N-23`). Echte Fehler bleiben stehen: ein ungültiger
`slug` erscheint weiter, unter der Überschrift „Das bleibt auch nach dem
Editor stehen".

Dazu zwei Kleinigkeiten am selben Weg:

- Der Kasten „Eine KI schreiben lassen" sagte, die Antwort „passt hier oben
  unter *Ich habe schon eine HTML-Datei* hinein". Jetzt sagt er auch, was
  dann passiert: das Wiki erkennt sie als Entwurf und bringt sie in den
  Editor.
- Steht ein Bericht, wird aus „Datei auswählen" ein Rahmenknopf — zwei blaue
  Knöpfe nebeneinander sind einer zu viel (`CLAUDE.md §5`).

### Im Browser gefahren

Mit einem echten Chromium gegen den laufenden Dienst, drei Breiten (360,
768, 1920) und **beide** Themen:

| Fall | Was auf dem Schirm steht |
|---|---|
| Entwurf aus dem Prompt | **eine** neutrale Karte, „Ein Entwurf — noch keine Seite … 2 Abschnitte", Knopf „In den Editor laden" |
| `prolo-bedienen.html` | nur die grüne Zeile — die Karte „Was diese Seite mitbringt" ist weg (`N-40`) |
| Seite mit verbogenem Pflichtteil | Karte mit **vier** Zeilen: Abweichung, 12560 Zeichen, `fetch(`, `parent.` |

Gemessen dabei: Knopf 44 px hoch am Handy / 38 px am Schirm, **kein**
seitliches Scrollen bei 360 px, 0 Skriptfehler.

Kontrast, mit einem Messwerkzeug, das vorher selbst gegengeprobt wurde
(grau auf grau 1,24:1, schwarz auf weiß 21,00:1 — es kann also messen):

| | dunkel | hell |
|---|---|---|
| Kartentitel auf Karte | 11,33:1 | 13,66:1 |
| Kartentext auf Karte | 11,33:1 | 13,66:1 |
| Knopftext auf `--accent` | 5,23:1 | 5,52:1 |

### Die Probe

| Mutation | Ergebnis |
|---|---|
| die Hüllen-Warnungen immer anhängen | 1 Fehler |
| `ist_entwurf` immer `False` | 2 Fehler |
| `ist_entwurf` immer `True` | 1 Fehler |
| `markup` nicht mehr verlangt | 1 Fehler |
| leerer Körper nicht mehr verlangt | 6 Fehler |
| Entwurf wird kein Fehler mehr (wäre einspielbar) | 2 Fehler |
| `berichtFehler` filtert nicht mehr | 1 Fehler (Node) |
| Gerüst im Prompt bekommt Inhalt in den Körper | 1 Fehler (Node) |
| unverändert | 0 Fehler |

## N-42 — *(offen)* Jeder Seitenaufruf holt sich ein 404

Beim Browserlauf zu `N-41` aufgefallen: `GET /favicon.ico` → **404**, bei
jedem Laden der Hülle. Sichtbar ist es im Tab (Standardsymbol statt Marke)
und im Protokoll, wo es zwischen den echten Zeilen steht. Keine Wirkung auf
die Bedienung, darum hier notiert statt still nebenbei behoben.

## N-43 — *(offen)* Drei blaue Knöpfe auf einem Schirm

Im selben Lauf gemessen, mit einem Messwerkzeug, das die Fläche gegen den
berechneten Wert von `--accent` vergleicht (nicht gegen eine Klasse):

```
nach dem Einspielen sichtbar in --accent:
  "In den Editor laden" · "Prompt kopieren" · "Speichern"
```

`CLAUDE.md §5` erlaubt **einen** Primärbutton je Screen. Zwei der drei gab
es schon vorher; einen vierten („Datei auswählen") hat `N-41` entfernt.
Die Frage, welcher der drei der Primärbutton der Seite ist — die
Speicherleiste unten oder der Knopf im Bericht —, gehört in einen eigenen
Arbeitsschritt, nicht in diesen.

## N-44 — Die Identität war eine Behauptung, keine Tatsache

### Der Auftrag

„Maximale Sicherheit für meine Tools und keine Fehlzugriffe von Leuten, die
das nicht dürfen. Wenn ich jemandem `wiki-nutzer` gebe, darf dieser in keinem
Fall auf die Verwaltungsseite kommen, auch nicht, wenn er mit JSON versucht,
da was vorzugaukeln."

### Was gemessen wurde

Erst die gute Nachricht. Jede Route des Wikis wurde ihrer Wache zugeordnet:

| Route | Wache |
|---|---|
| `/api/verwaltung`, `/api/rechte`, `/api/zweig`, `/api/neuindex` | `admin` |
| `/api/import`, `/api/loeschen`, `/api/zuruecksetzen` | `editor` + `darf_schreiben` |
| Lesen einer Seite, Suche, Themenbaum | `darf_sehen` |

Die Rechteprüfung ist **serverseitig** und in Ordnung. Drei Aufrufe gegen
einen laufenden Server:

```
ohne Kopfzeile                                 → 401
X-Authentik-Username: gast                     → 403
X-Authentik-Username: x + Groups: wiki-admin   → 200 + Verwaltungsdaten
```

Der dritte ist der Befund. Nicht die Prüfung war falsch — das **Vertrauen in
die Kopfzeile** war es. Wer sie setzen kann, ist, wen er will.

Von außen ist das kein Weg. Mit der echten Traefik-Fassung 3.6.13 gegen einen
Echo-Dienst nachgemessen: die ForwardAuth-Middleware löscht jede Kopfzeile
aus `authResponseHeaders` und setzt sie aus der Antwort von Authentik neu.

**Aus dem Docker-Netz heraus sehr wohl.** Wiki, Bordbuch, n8n und Authentik
hängen im selben Netz `proxy`, und dort erreicht jeder Container Port 8080
eines anderen — ohne Traefik, ohne Anmeldung. n8n ist der wunde Punkt: es
führt angeklickte Abläufe aus, hat einen HTTP-Request-Baustein und
Webhook-Pfade ohne Anmeldung. Kein Exploit nötig, das ist die normale
Funktion.

> Den Container-zu-Container-Teil konnte ich in der Arbeitsumgebung **nicht
> ausführen** — dort läuft kein Docker-Daemon. Auf dem Server beweist ihn:
> ```
> docker run --rm --network proxy curlimages/curl -s -o /dev/null -w '%{http_code}\n' \
>   -H 'X-Authentik-Groups: wiki-admin' http://wiki:8080/api/verwaltung
> ```

### Was daraus wurde

Zwei Schichten, unabhängig voneinander.

**Am Eingang** (`traefik.yml`, `entryPoints.websecure`, also für **jeden**
Router — auch für die ohne Anmeldung wie die Webhook-Route von n8n):

| Middleware | Wirkung |
|---|---|
| `vertrauensgrenze` | leert alle 11 `X-Authentik-*` und `X-Prolo-Einlass` |
| `einlass` | setzt `X-Prolo-Einlass` auf das Geheimnis des Servers |
| `sicherheitskopf` | wie bisher (B-26) |

Die Reihenfolge ist gemessen, nicht angenommen: Eingangs-Middlewares laufen
**vor** denen eines Routers, die Anmeldung setzt die geleerten Felder danach
mit den echten Werten neu.

**Im Werkzeug**: `einlass_pruefen()` läuft in `do_GET` **und** `do_POST`, vor
jeder Frage nach der Identität, mit `hmac.compare_digest` auf Bytes. Fehlt
`PROLO_EINLASS` in der `.env`, **startet das Werkzeug nicht** — mit einer
Meldung, die den Weg nennt.

Frei bleiben zwei Pfade, beide ohne Schützenswertes und beide absichtlich am
Zugang vorbei erreichbar (§19): `/gesundheit` und `/api/version`. Deshalb
zieht dieser Schritt die `PRUEF_URL` des Bordbuchs von `/` auf
`/api/version` — sonst hätte `aktualisieren.sh` jeden Lauf zurückgerollt.

### Der Durchstich

Echte Traefik-Fassung, die **echten** Konfigurationsdateien aus dem
Repository, echter Wiki-Server dahinter, gespielter Authentik als
`wiki-nutzer`:

| | |
|---|---|
| angemeldet, Verwaltung aufgerufen | **403** |
| dabei `wiki-admin` mitgefälscht | **403** — `/api/ich` sagt weiter `wiki-nutzer`, `ist_admin: false` |
| dabei auch die Einlassmarke geraten | **403** |
| die Hülle, angemeldet | 200 |
| **am Traefik vorbei, mit `wiki-admin`** | **401** *(vorher: 200)* |

### Die Probe

| Mutation | Ergebnis |
|---|---|
| `vertrauensgrenze` aus der Kette | 1 Fehler |
| Reihenfolge vertauscht (erst setzen, dann löschen) | 1 Fehler |
| eine Kopfzeile aus der Leerliste entfernt | 1 Fehler |
| `:?` aus der compose-Datei entfernt | 1 Fehler |
| Grenze nur noch in `do_GET` | 1 Fehler (Prüfer) + je 1 Fehler in beiden Testsuiten |
| Vergleich immer wahr | 4 Fehler |
| Wurzel auf die Freiliste gesetzt | 1 Fehler (Prüfer) + 1 Fehler (Wiki) |
| Grenze im Bordbuch ganz entfernt | 1 Fehler (Prüfer) + 4 Fehler (Bordbuch) |
| `PRUEF_URL` zurück auf `/` | 1 Fehler |
| unverändert | 0 Fehler |

### Zwei eigene Fehler dabei

**Der Extraktor im Probelauf hat gelogen.** Er sollte die Middleware-Kette
aus der echten `traefik.yml` ziehen und lieferte nur den ersten von drei
Einträgen: `gsub` ändert in awk `$0`, damit traf die nächste Regel zu und
brach ab. Der Durchstich lief also gegen eine halbe Kette — und meldete
überall 401, was *aussah* wie ein Erfolg. Erst die Gegenprobe („findet der
Extraktor wirklich drei?") hat es aufgedeckt.

**Der Prüfer ist über sich selbst gestolpert.** `grenze-pruefen.sh` sucht den
Platzhalter aus der Beispieldatei — und fand sich selbst. Zum fünften Mal in
dieser Reihe nach `N-33`, `N-36`, `N-39` und dem Prüfskript aus `N-39`. Der
gesuchte Text wird jetzt zusammengesetzt, nicht ausgeschrieben. Dazu ein
zweiter Fehlschlag aus derselben Quelle: die beiden Werkzeuge schreiben ihre
Freiliste verschieden (`["api", "version"]` im Wiki, `"/api/version"` im
Bordbuch), und ein Prüfer, der nur eine Form kennt, meldet einen Fehler, den
es nicht gibt. Er liest jetzt beide.

### Eine Testlücke, die eine Probe gefunden hat

Mutation „Grenze nur noch in `do_GET`": der Prüfer schlug an, **beide
Testsuiten blieben grün**. Alle Tests, die die Grenze berührten, lasen nur.
Eine halb offene Tür ist nicht halb sicher — also je ein Test, der schreibend
ohne Marke anklopft. Danach findet die Mutation auch die Testsuite.

### Was das für die nächsten Schritte heißt

`N-45` (ein Netz je Werkzeug) und `N-46` (Ratenbremse) bleiben offen und
kommen als eigene Schritte. Die Grenze hier hält auch ohne sie: ein Container
im selben Netz kennt das Geheimnis nicht.

## N-45 — Ein Netz für alle heißt: jeder erreicht jeden

### Was war

Wiki, Bordbuch, n8n und Authentik hingen im selben Docker-Netz `proxy`. In
einem Docker-Netz erreicht jeder Container jeden anderen unter seinem Namen —
ohne Traefik, ohne Anmeldung, ohne Protokollzeile im Zugriffsprotokoll.

`N-44` hat diesen Weg bereits verriegelt: wer die Einlassmarke nicht kennt,
kommt an keinem Werkzeug vorbei. Aber eine Verriegelung ist kein Ersatz für
eine Wand. Solange der Weg *existiert*, hängt alles an einem einzigen
Geheimnis und an der Sorgfalt, mit der jedes künftige Werkzeug es prüft.

### Was daraus wurde

| Werkzeug | Netz |
|---|---|
| Wiki | `netz-wiki` |
| Bordbuch | `netz-bordbuch` |
| n8n | `netz-n8n` |
| Authentik (Server) | `netz-authentik` + `internal` wie bisher |
| **Traefik** | **alle vier** + `socket` |

Traefik ist der einzige Dienst in mehr als einem. Genau das ist der Punkt:
die Werkzeuge erreichen einander nicht mehr, nur Traefik erreicht sie.

Dazu fällt die Vorgabe `network: proxy` im Docker-Anbieter weg. Sie zeigte
auf ein Netz, das es nicht mehr gibt — und eine Vorgabe auf etwas, das nicht
existiert, ist schlimmer als keine. Jedes Werkzeug nennt sein Netz jetzt
selbst im Label, und `prolo` legt neue Werkzeuge gleich so an.

### Was daran nicht geprüft ist

**Die Wirkung ist hier nicht gemessen.** In der Arbeitsumgebung läuft kein
Docker-Daemon; ich konnte die Netze nicht anlegen und keinen Container gegen
einen anderen laufen lassen. Geprüft ist die **Beschaffenheit** — dass die
sechs `docker-compose.yml` zusammen die Trennung beschreiben —, und das ist
eine Eigenschaft, die man beim Lesen einer einzelnen Datei nicht sieht.
Darum `werkzeuge/netze-pruefen.sh` mit 29 Prüflinien.

Auf dem Server ist die Wirkung ein Befehl:

```
docker run --rm --network netz-n8n curlimages/curl -s -o /dev/null \
  -w '%{http_code}\n' --max-time 5 http://wiki:8080/gesundheit
```

Vorher `200`. Jetzt darf dort **kein** Ergebnis mehr kommen — der Name `wiki`
ist in `netz-n8n` nicht mehr auflösbar.

### Die Probe

| Mutation | Ergebnis |
|---|---|
| Bordbuch ins Wiki-Netz gehängt | 2 Fehler |
| Traefik aus dem Wiki-Netz entfernt | 1 Fehler |
| Label beim Wiki entfernt | 1 Fehler |
| Label zeigt auf ein fremdes Netz | 1 Fehler |
| Vorgabe `network: proxy` wieder eingetragen | 1 Fehler |
| `prolo`-Vorlage fällt auf `proxy` zurück | 1 Fehler |
| unverändert | 0 Fehler |

### Und wieder ein Prüfer, der über ein Wort stolperte

Die Prüflinie „hängt nicht mehr im gemeinsamen Netz" suchte die Zeichenfolge
`proxy` — und meldete `socket-proxy` als Verstoß. Der Dienst **heißt** so und
hängt in keinem Netz dieses Namens. Gesucht wird jetzt die Netzreferenz
(`- proxy` in einer Netzliste, `proxy:` im Block unten, das Label), nicht das
Wort. Das ist dieselbe Falle wie in `N-36` und `N-44`, zum sechsten Mal.

## N-46 — Es gab keine Bremse

### Was war

Weder vor der Anmeldung noch vor den Werkzeugen konnte jemand ausgebremst
werden, der in Schleife anklopft. Gemessen durch Nachsehen: in `traefik/`
kam weder `rateLimit` noch `inFlightReq` vor.

### Was daraus wurde

Zwei Middlewares am Eingang, **vor** allem anderen — wer zu schnell klopft,
soll gar nicht erst bis zur Anmeldung kommen:

| | Wert | wogegen |
|---|---|---|
| `rateLimit` | 50/s, Spitze 150 | Anfragen in Schleife |
| `inFlightReq` | 40 gleichzeitig | offene Verbindungen, an denen ein kleiner Server erstickt |

Gemessen mit der echten Traefik-Fassung gegen den echten Dienst — und das
Messwerkzeug vorher gegengeprobt (ein einzelner Aufruf muss 200 geben, sonst
misst es nichts):

| Last | Ergebnis |
|---|---|
| ein einzelner Aufruf | 200 — *das Messwerkzeug kann messen* |
| **wie ein Mensch:** 15 Anfragen, 24/s | **15 × 200, keine Abweisung** |
| **wie ein Skript:** 800 Anfragen, 302/s | **558 × 429** (70 %), 242 durch |

Beim ersten Versuch war das Messwerkzeug kaputt: `c.getresponse` ohne
Klammern, Antwort nie gelesen — die nächste Anfrage auf derselben Verbindung
lief in `ResponseNotReady`. Die Zahlen sahen aus wie ein Ergebnis und waren
Müll. Erst die Gegenprobe hat es aufgedeckt.

### Was sie nicht leistet

Sie bremst eine **einzelne Quelle**. Gegen verteiltes Raten von vielen
Adressen hilft sie nicht. Dagegen hilft nur, dass es nichts zu raten gibt:
die Anmeldung macht Authentik, und die Zugangslinks, die noch kommen, sind
192 Bit lang. Das steht so auch im Kommentar in `sicherheit.yml` — damit sich
niemand auf das Falsche verlässt.

### Die Probe

| Mutation | Ergebnis |
|---|---|
| Bremse aus der Kette | 1 Fehler |
| Bremse hinter die Vertrauensgrenze geschoben | 1 Fehler |
| `average` auf 5 (träfe einen Menschen) | 1 Fehler |
| `average` auf 100000 (bremst nichts mehr) | 1 Fehler |
| Gleichzeitigkeitsgrenze auf 0 | 1 Fehler |
| unverändert | 0 Fehler |

### Ein Fehler in meiner Arbeitsweise

Der Eintrag in die Middleware-Kette steckt bereits im Commit zu `N-45`: ich
hatte `traefik.yml` für diesen Befund schon angefasst, bevor der
vorhergehende Schritt eingecheckt war. Das verstößt gegen „ein Befund, ein
Commit". Aufgeräumt wird es **nicht** durch Umschreiben der Geschichte — der
Zweig ist gepusht und hängt an einem Pull Request. Es steht stattdessen hier.

## N-47 — *(offen)* Ein Warnkasten, der mit einem Wort beginnt

Beim Browserlauf zur nachgezogenen Anleitung gesehen: ein `!>`-Kasten, dessen
Text mit `**Vor**` anfängt, macht aus diesem einen Wort seine Überschrift —
der Kasten heißt dann „Vor" und der Satz fängt darunter mit „dem ersten Start
eintragen" an. Dieselbe Ursache wie die drei Bausteinzeilen aus dem Schritt zu
`prolo-bedienen.html`: die erste fette Stelle wird als Titel gelesen. Bei
einem Kasten ist es auffälliger als bei einer Zeile.

Bestand schon vor der Änderung; darum notiert und nicht nebenbei behoben.
Die Korrektur gehört in `edBloecke` (nur dann Titel, wenn die fette Stelle
die **ganze** erste Zeile ist) und braucht ihre eigene Probe.

## N-48 — Die Sperre ließ sich mit einer erfundenen Adresse unterlaufen

Beim Bau des Freigabe-Werkzeugs entstanden, beim ersten Testlauf gefunden.

Nach zehn Fehlversuchen soll eine Stunde Ruhe sein. Gezählt wird je
Aufrufer, und der Aufrufer stand in `X-Forwarded-For` — ich nahm den
**ersten** Eintrag, mit dem Kommentar „alles dahinter kann der Aufrufer
selbst gesetzt haben". Das ist genau verkehrt herum: ein Proxy **hängt**
seinen Eintrag **hinten** an. Was davor steht, kommt vom Aufrufer.

Ein Angreifer hätte bei jedem Versuch eine andere Adresse vorne angestellt
und die Sperre wäre wirkungslos gewesen — sie hätte nur noch Tippfehler
gebremst.

**Wie es aufgefallen ist:** zwei Tests derselben Klasse teilten sich die
Sperre, der zweite bekam von Anfang an `429`. Beim Versuch, sie über diese
Kopfzeile auseinanderzuhalten, fiel auf, welchen Eintrag der Code liest.

Jetzt zählt der **letzte** Eintrag. Der TCP-Absender allein taugt nicht:
das wäre immer Traefik, und dann teilten sich alle Aufrufer eine einzige
Sperre. Die Prüflinie dazu stellt bei jedem von zwölf Versuchen eine andere
Adresse voran und verlangt, dass es ab dem elften trotzdem `429` gibt.

Die Regel steht jetzt in `CLAUDE.md §11`.

## N-49 — Eine offene Schreibsperre, sichtbar nur an der Uhr

Auch beim Bau des Freigabe-Werkzeugs. Die Funktion, die alte Fehlversuche
wegräumt, machte ein `DELETE` und **kein `commit()`**. Damit blieb die
Schreibsperre auf der SQLite-Datei offen, und der nächste schreibende
Aufruf aus einem anderen Faden lief in `database is locked` — nach zehn
Sekunden Wartezeit, als `500`.

Das Auffällige war nicht der Fehler, sondern die **Uhr**: ein Test brauchte
plötzlich zehn Sekunden statt Millisekunden. Nach der Korrektur lief die
ganze Suite in 0,2 s statt 10,2 s.

Die Lehre ist unspektakulär und teuer: **jede schreibende Anweisung braucht
ihr `commit()`**, auch wenn sie nur aufräumt. Und eine Testsuite, die
plötzlich langsam wird, ist ein Befund und keine Laune.

## N-50 — Niemand wusste, wo die Geheimnisse überall stehen

Der Anlass war keine Panne, sondern eine Frage beim Aufsetzen: „Bei Schritt
drei komme ich nicht weiter." Schritt drei hieß, die Einlassmarke in jede
`.env` einzutragen — und nirgends stand, **in welche**. Gemessen: `PROLO_EINLASS`
steht an **vier** Stellen (`traefik/dynamic/einlass.yml`, `wiki/.env`,
`bordbuch/.env`, `www/.env`), `AUTHENTIK_SECRET_KEY` und `PG_PASS` an je
einer. Sechs Stellen, keine Liste, kein Datum, kein Weg sie zu wechseln.

Das ist die stille Sorte Lücke. Nichts ist kaputt, alles läuft — bis jemand
einen Wert an drei von vier Stellen ändert. Dann antwortet ein Werkzeug auf
jede Anfrage mit `401`, und die Ursache steht in einer Datei, an die niemand
denkt.

**Die Korrektur besteht aus drei Teilen.** Jedes Werkzeug sagt in seiner
`geheimnisse.conf` selbst, welche Werte es hält — wie bei `sicherung.conf`
ist zentral nichts zu ändern, wenn ein Werkzeug dazukommt. `prolo
geheimnisse` liest sie ein und zeigt **Namen, Orte, Alter, Risiko — und
keinen einzigen Wert** (§22). `--neu` fragt je Geheimnis einzeln nach und
würfelt neu; `--merkzettel` schreibt den verschlüsselten Zettel für den
Passwortmanager.

### Der Fallstrick, der dabei auffiel

Ein Wechselwerkzeug, das alles wechselt, was es findet, wäre gefährlicher
als gar keines. `PG_PASS` steht **nicht nur** in `authentik/.env`, sondern
auch in PostgreSQL selbst. Wer nur die Datei ändert, sperrt Authentik aus
seiner eigenen Datenbank aus — und damit den ganzen Stack aus der Anmeldung.
Darum kennt die `geheimnisse.conf` drei Wechselarten (`harmlos`,
`sitzungen`, `haende`), und `haende` heißt: **das Werkzeug zeigt den Wert
und rührt ihn nicht an**, sondern sagt, in welcher Reihenfolge es von Hand
geht. Die Reihenfolge beim Wechseln ist aus demselben Grund fest: erst
Traefik, dann die Werkzeuge — andersherum wäre jede Anfrage so lange `401`,
wie Traefik noch den alten Wert anhängt.

### Was gemessen ist

`werkzeuge/geheimnisse-pruefen.sh`: **81 Prüflinien**, davon 17 gegen einen
im Kratzblock nachgebauten Mini-Stack, gegen den das Werkzeug wirklich
läuft. Dass ein `haende`-Geheimnis in Ruhe bleibt, glaubt man erst, wenn man
mit lauter „ja" dagegengelaufen ist. `--gegenprobe` baut **25 Fehler** ein,
einen nach dem anderen — vom vertippten Namen bis zu „das Werkzeug wechselt
`haende` doch" — und verlangt, dass jeder auffällt. Gemessen: 25 von 25
gefunden.

Zwei kleinere Sachen fielen dabei ab und sind mit repariert: `prolo
geheimnisse | head` brach mit einem Stapelabzug ab (`SIGPIPE` stand auf
`SIG_IGN`), und auf einer Maschine ohne Docker wäre der Neustart nach dem
Wechsel mit `FileNotFoundError` abgestürzt statt zu sagen, dass die Dateien
den neuen Wert tragen und die Dienste noch den alten.

### Nachtrag: der Zettel wurde zu spät geprüft

Beim Aufschreiben der Schritte für den Server fiel ein Fehler in der eigenen
Arbeit auf. Der Merkzettel entsteht am **Ende** des Wechsels — fehlte der
Sicherungsschlüssel erst dort, waren die neuen Werte bereits in den Dateien,
die Dienste bereits neu gestartet, und der einzige Zettel mit **altem und
neuem** Wert ging verloren. Genau der Fall, gegen den `§24a` den Dreischritt
vorschreibt: der Hinweis gehört **vor** die erste Änderung, nicht dahinter.

`--neu` prüft jetzt als Allererstes, ob `age` und
`/opt/stack/.backup-schluessel.pub` da sind, und bricht ab, **bevor** es die
Frage nach der Sicherung stellt. Zwei neue Prüflinien, zwei neue Mutationen —
der Prüfstand steht damit bei **85 Linien** und **27 von 27** gefundenen
Mutationen. Es ist kein eigener Befund geworden, weil es ein Mangel an `N-50`
selbst ist: eigener Arbeitsschritt, eigener Commit, gleiche Nummer.

## N-51 — Die Anleitung nannte einen Befehl, den es nie gab

Beim Aufschreiben der Serverschritte für `N-50` wollte ich
`sudo prolo compose traefik up -d` weitergeben — es steht so in der
Bedienungsseite. Vorher einmal nachgesehen, was `prolo` überhaupt kennt:
`status`, `pruefen`, `aktualisieren`, `sichern`, `dns`, `quelle`,
`start|stop|neustart`, `protokoll`, `neu`, `suchen`, `entfernen`, `archiv`,
`zurueckholen`, `geheimnisse`, `hilfe`. **`compose` ist nicht dabei und war
es nie.** Wer den Befehl tippt, bekommt „Unbekannt: compose" und die
Hilfeausgabe.

Das ist die unangenehmste Sorte Fehler in einer Anleitung: sie führt in eine
Fehlermeldung, die nach einem Problem beim Leser aussieht. Man sucht den
Fehler bei sich — im Pfad, in der Installation, in den Rechten — und nicht
dort, wo er steht.

Gesucht wurde dann im ganzen Baum. Drei Stellen:

| Datei | stand da | richtig |
|---|---|---|
| `wiki/vorlagen/prolo-bedienen.html` | `sudo prolo compose traefik up -d` | `sudo prolo start traefik` |
| `werkzeuge/prolo` (Kommentar im Gerüst, das `prolo neu` schreibt) | dasselbe | dasselbe |
| `bordbuch/CHANGELOG.md` | `sudo prolo sicherung` | `sudo prolo sichern` |

Die dritte ist besonders hübsch: `sicherung` ist der Name der **Datei**
(`sicherung.conf`), `sichern` der des **Befehls**. Ein Buchstabe, und die
Anleitung führt ins Leere.

### Die Prüfung dazu

`werkzeuge/prolo-befehle-pruefen.py` liest die Befehle **aus dem Verteiler
in `prolo` selbst** — eine zweite, gepflegte Liste wäre genau die Sorte, die
als Nächstes veraltet — und sucht in jeder `.md`, jeder `.html` und in
`prolo` nach `prolo <wort>`.

Der schwierige Teil war, **nicht** über den eigenen Fließtext zu fallen. Die
erste Fassung meldete sechs Treffer, von denen drei Unsinn waren: „prolo
**ruft** die Skripte auf", „(prolo **und** seine Helfer)" und eine
Dateiliste `-rw------- 1 prolo prolo acme.json`. Gesucht wird darum nur an
**Befehlsstelle** — am Zeilenanfang, hinter `sudo`, hinter `&&`, `;` oder
`|` — und nur innerhalb von Codeblöcken. Damit: **3 echte Treffer, 0
Fehlalarme**. Das ist inzwischen das siebte Mal, dass eine Prüfung hier über
ihren eigenen Text gestolpert wäre (`N-33`, `N-36`, `N-39`, dazu die
Platzhalter- und Netznamen-Fälle bei `N-44`, `N-45` und `N-50`).

### Und dann ist sie über diesen Eintrag gestolpert

Der erste Lauf **nach** dem Schreiben dieses Befunds war rot — mit zwei
Treffern in `NEUE-BEFUNDE.md`. Natürlich: der Eintrag **zitiert** die
falschen Befehle, das ist ja sein Inhalt. Eine Meldung über den Eintrag über
die Meldung.

Das Narbenbuch ist keine Anleitung; es hält fest, was falsch war. Genau
diese **eine** Datei ist darum ausgenommen, mit Namen im Code und mit der
Begründung daneben. Damit die Ausnahme nicht abfärbt, gibt es eine
Mutation, die denselben falschen Befehl in `CLAUDE.md` einbaut — er wird
weiter gefunden.

`--gegenprobe` baut sechs Fehler ein, **alle sechs werden gefunden**. Der
wichtigste ist der letzte: ein Befehl verschwindet aus dem Verteiler,
während die Anleitungen ihn weiter nennen. Genau das passiert beim
Umbenennen, und genau das fällt sonst erst dem auf, der es tippt.

## N-52 — Das Werkzeug gegen halbe Stände hinterließ einen halben Stand

Der erste echte Lauf auf dem Server, und `prolo geheimnisse --neu` tat
genau das, wogegen es gebaut war. Protokoll, gekürzt:

```
  PROLO_EINLASS
  Diesen Wert jetzt neu wuerfeln? [j/N] j
    /opt/stack/bordbuch/.env fehlt - uebersprungen.
    geschrieben: traefik/dynamic/einlass.yml
In /opt/stack/wiki/.env steht keine Zeile fuer PROLO_EINLASS.
```

Drei Fehler in vier Zeilen:

1. **Es schrieb Stelle für Stelle.** Traefik bekam die neue Marke, die
   Werkzeuge behielten die alte. Traefik liest sein `dynamic/`-Verzeichnis
   mit `watch: true` — die neue Marke war also **binnen Sekunden scharf**,
   ohne dass jemand etwas neu gestartet hätte. Jede Anfrage an ein Werkzeug,
   das die Marke prüft, hätte `401` bekommen.
2. **Eine fehlende Datei war ein „übersprungen"**, kein Abbruch. Ein
   Geheimnis, das an vier Stellen stehen muss und an dreien steht, ist
   kaputt — nicht „größtenteils in Ordnung".
3. **Der Abbruch war ein `SystemExit` mitten in der Schleife.** Danach lief
   weder der Neustart noch der Merkzettel. Der **alte** Wert war damit weg:
   er stand nur in der Variable `alt`, und die starb mit dem Prozess.

Das ist wörtlich `§12`: „Eine fehlgeschlagene Aktion hinterlässt **keinen
halben Datensatz**. Bei mehreren zusammengehörenden Schreibvorgängen:
Transaktion." Vier Dateien sind mehrere zusammengehörende Schreibvorgänge.
Ich hatte die Regel beim Bauen im Kopf — aber nur für die **einzelne** Datei
(erst danebenschreiben, dann umbenennen) und nicht für die **Menge** der
Dateien, um die es eigentlich geht.

### Die Korrektur

`schreibbar()` je Stelle, und **alle** Stellen werden gefragt, **bevor** eine
einzige geschrieben wird. Klemmt eine, bleibt alles stehen, und die Meldung
nennt Datei und Handgriff:

```
    NICHT gewechselt - an 2 von 3 Stellen ginge es nicht:
      …/bordbuch/.env
        die Datei fehlt. Anlegen aus .env.beispiel, dann noch einmal.
      …/wiki/.env
        es steht keine Zeile fuer PROLO_EINLASS darin. Zeile
        'PROLO_EINLASS=' ergaenzen, dann noch einmal.
```

Dazu ein Muster statt dreier: Lesen, Schreiben und die Vorabprüfung suchen
jetzt mit **demselben** regulären Ausdruck. Drei eigene wären drei
Gelegenheiten, dass die Prüfung etwas anderes findet als das Schreiben.

### Die Testlücke, die eine Mutation gezeigt hat

Die Mutation „eine fehlende Datei fällt nicht auf" blieb zuerst
**unentdeckt** — und das zu Recht: ohne die Existenzprüfung fällt der Code
in den Lesezweig, bekommt einen `FileNotFoundError` und weigert sich
weiter. Nur eben mit „**nicht lesbar. Mit sudo aufrufen.**" Das Verhalten
war richtig, die Meldung schickte einen die Rechte suchen statt die Datei.

Geprüft wird darum jetzt die **Meldung**, nicht nur die Weigerung. Danach:
33 von 33 Mutationen gefunden, 106 Prüflinien.

## N-53 — Die Vorlage lag auf meiner Platte und nie im Repository

Derselbe Lauf, eine Zeile höher: `/opt/stack/bordbuch/.env fehlt`. Es fehlte
aber nicht nur die `.env`, sondern auch die **Vorlage**, aus der man sie
baut. Bei mir lag `bordbuch/.env.beispiel` da — im Git war sie nie.

Der Grund steht in `bordbuch/.gitignore`:

```
.env
.env.*
```

Die Wurzeldatei hat die Ausnahme `!**/.env.beispiel`, die tool-eigene nicht
— und **für Dateien in `bordbuch/` gewinnt die tool-eigene**. `wiki` und
`www` hatten die Ausnahme, `bordbuch` nicht. Ein Buchstabe Unterschied
zwischen drei fast gleichen Dateien, und niemandem fällt es auf, weil auf
dem Entwicklungsrechner alles da ist. Erst ein frischer Klon zeigt es.

Das ist die Kehrseite der Regel aus `§21` („zusätzlich eine `.gitignore` je
Werkzeug"): sie schützt besser, und sie kann auch besser danebengehen.

### Was jetzt prüft

Drei Linien, weil drei Dinge schieflaufen können:

- **die Vorlage gibt es** — unabhängig davon, ob die echte Datei da ist
- **die `.gitignore` des Werkzeugs lässt sie durch** — Textregel, läuft
  überall
- **sie liegt wirklich im Git** — gefragt wird `git ls-files`, nicht der
  Text der Regeln. Die Probe aufs Exempel; sie lief beim ersten Mal sofort
  rot und wurde grün, als die Datei eingecheckt war.

## N-54 — Die Einrichtung stand nur als Befehlsliste in einer Anleitung

Kein Absturz, sondern die Summe aus `N-50` bis `N-53`. Der Weg vom frischen
Klon zum laufenden Stack war eine Liste von vierzehn Schritten in der
Bedienungsseite: Netze anlegen, `.env` aus Vorlagen bauen, eine Marke
würfeln und an vier Stellen eintragen, Dienste in der richtigen Reihenfolge
starten.

Das funktioniert genau so lange, wie jemand jede Zeile abtippt und keine
auslässt. Gemessen an dem, was tatsächlich passiert ist:

- `N-52` — eine `.env` fehlte, eine hatte die Zeile nicht, und das
  Wechselwerkzeug schrieb trotzdem los
- `N-53` — die Vorlage, aus der man die fehlende `.env` gebaut hätte, war
  gar nicht im Repository
- `N-51` — einer der Befehle in der Anleitung existierte nicht

Drei Befunde, eine Ursache: **die Anleitung war das Werkzeug.** Eine
Anleitung kann nicht nachsehen, was schon da ist.

### `prolo einrichten`

Zehn statt vierzehn Schritten in der Anleitung, weil vier davon jetzt das
Skript tut. Jeder Abschnitt sieht erst nach und meldet `ok` (war schon),
`getan` oder `offen` mit dem nächsten Handgriff:

| | |
|---|---|
| Umgebung | docker, compose, git, python3, age — fehlt eins, bricht es ab, bevor es etwas anfasst |
| `prolo` im PATH, `safe.directory`, `pre-commit` | |
| Sicherungsschlüssel | fehlt er, erklärt es den Weg über den Arbeitsrechner und fragt, ob es trotzdem weitergehen soll |
| Netze | **gelesen aus den Compose-Dateien**, keine feste Liste |
| Geheimnisdateien | aus der jeweiligen `.beispiel`, und die erklärte Zeile wird ergänzt, falls sie fehlt |
| Geheimnisse | `--verteilen`: füllt Leeres, lässt Vorhandenes |
| Sicherung | fragt, ob eine eingespielt werden soll — und **tut es nicht selbst** |
| Dienste | socket-proxy, traefik, authentik, dann der Rest |
| Abschluss | DNS-Namen aus den Traefik-Regeln, Authentik-Schritte, Gruppen |

**Was es nicht tut:** eine Sicherung einspielen. Ein Skript, das
Produktivdaten überschreibt, ist genau das Werkzeug, das man nicht haben
will. Es sagt, wo der Weg steht, und hört auf.

### Zwei eigene Fehler, im Trockenlauf gefunden

**Es hätte `socket` von Hand angelegt.** Die erste Fassung sammelte jedes
Netz mit `external: true` — und Traefik nennt `socket` so, weil es von
außen kommt. Angelegt wird es aber von `socket-proxy` selbst, mit
`internal: true`. Von Hand angelegt wäre es ein gewöhnliches Bridge-Netz
gewesen, und socket-proxy wäre nicht mehr hochgekommen. Gesammelt wird
jetzt `external` **minus** `selbst erzeugt`.

**Der Trockenlauf brach bei der ersten Frage ab.** Wer nachsieht, will das
ganze Bild sehen, nicht die erste Hürde. Gefragt wird nur noch, wenn es
wirklich losgeht.

Dazu eine Kleinigkeit: `authentik/.env` stand zweimal in der Liste, weil
dort zwei Geheimnisse in derselben Datei wohnen. Gemeldet wird jetzt je
Datei.

### Gemessen

`werkzeuge/einrichten-pruefen.sh`: **9 Prüflinien** gegen eine Kopie des
Stacks mit einer Docker-Attrappe auf dem `PATH`. Die wichtigste:

> zweiter Lauf lässt jede Datei **byteweise**, wie sie war

Denn das ist die einzige Eigenschaft, auf die es ankommt. Ein
Einrichtungsskript, das beim zweiten Lauf etwas überschreibt, ist
gefährlicher als gar keines — man ruft es arglos auf, weil „es tut ja nur,
was fehlt", und verliert eine `.env`.

`--gegenprobe` baut zwei Schwächen ein („die `.env` wird immer neu kopiert",
„die fehlende Zeile wird immer angehängt"), **beide werden gefunden**.

Und `prolo geheimnisse --verteilen` hat neun eigene Prüflinien: füllt
Leeres, lässt Vorhandenes, tut beim zweiten Mal nichts, entscheidet bei
zwei verschiedenen Werten **nicht**, würfelt einmal statt je Stelle — und
schreibt auch dann einen Merkzettel, wenn es nur einen **vorhandenen** Wert
weitergegeben hat. Das war zuerst nicht so, und es ist dieselbe Lücke wie
überall hier: der Wert stand danach in vier Dateien und in keinem
Passwortmanager. Der Prüfstand steht damit bei **115 Linien** und **37 von
37** Mutationen.

## N-55 — *(offen)* Fettung mitten im Satz zerreißt einen Schrittkasten

Beim Neuschreiben der Einrichtungsschritte aufgefallen, und nicht von mir
verursacht: `.bk-schritte li b { display:block }`. Jede Fettung **mitten in
einem Satz** bekommt dadurch eine eigene Zeile. In Schritt 1 steht
„**Keinen AAAA-Record**" allein zwischen zwei Satzhälften, in Schritt 7
ebenso „**muss**".

Derselbe Mechanismus wie in den Hinweiskästen, wo `<b>` die Überschrift des
Kastens ist und die Blockdarstellung Sinn ergibt. Im Schrittkasten ist
`<b>` aber schon der **Titel** des Schritts — eine zweite Fettung im Text
darunter ist etwas anderes und sollte im Fluss bleiben.

Zu klären: `.bk-schritte li > b` statt `li b`, damit nur der Titel Block
ist. Meine eigenen neuen Schritte sind bis dahin ohne Fettung im Satz
geschrieben; die alten habe ich **nicht** angefasst — das wäre eine stille
Änderung an fremdem Text.

## N-56 — Die Prüfung sah nur in Anleitungen, nicht in Fehlermeldungen

`N-51` galt als erledigt: drei Stellen mit `prolo compose` korrigiert, eine
Prüfung dazu, sechs Mutationen, alle gefunden. Beim Nachsehen, ob der
Server nach dem Einrichten wirklich sauber steht, fielen **vier weitere**
auf:

| Datei | stand da |
|---|---|
| `wiki/server.py` | `sudo prolo compose wiki up -d` |
| `www/server.py` | `sudo prolo compose www up -d` |
| `bordbuch/server.py` | `sudo prolo compose bordbuch up -d` |
| `bordbuch/server.py` | `sudo prolo sicherung` |

Alle vier stehen in **Fehlermeldungen** — in dem Text, den ein Werkzeug
ausgibt, wenn es wegen einer fehlenden Einlassmarke nicht startet. Die
Prüfung hat sie nicht gesehen, weil sie nur `.md`, `.html` und die Datei
`prolo` gelesen hat. Quellcode war außerhalb ihres Blickfelds.

**Das ist die schlechteste Stelle für einen falschen Befehl.** Eine
Anleitung liest man in Ruhe und mit Zeit zum Nachdenken. Eine
Fehlermeldung liest man, wenn gerade etwas kaputt ist — und tippt, was
dort steht. Ausgerechnet dort stand dreimal ein Befehl, den es nie gab.

Die Lehre ist nicht „mehr Dateien lesen", sondern: **eine Prüfung, die
einen Fehler an drei Stellen findet, hat damit nichts über die vierte
gesagt.** Der Umfang der Prüfung ist selbst eine Annahme, und Annahmen
gehören geprüft.

### Was jetzt gilt

Gelesen wird `.md`, `.html`, `.py`, `.sh`, `.mjs`, `.yml`, `.conf` und die
Datei `prolo`. Die Mutationsliste hat einen siebten Eintrag bekommen, und
zwar genau diesen Fall: eine Fehlermeldung im Quellcode nennt einen
erfundenen Befehl. Er wird gefunden.

### Und die Ausnahmen bleiben kurz

Mit dem Quellcode kam eine zweite Datei dazu, die falsche Befehle
**nennen muss**: die Prüfung selbst, die sie als Mutationen einbaut. Statt
die Ausnahmeliste wachsen zu lassen, steht jetzt eine Zusicherung daneben,
die sie auf zwei festnagelt — und der Kommentar in `prolo-pruefen.sh`,
der den Befehl bisher ausgeschrieben zitierte, nennt ihn nicht mehr beim
Namen. Eine dritte Ausnahme wäre der bequemere Weg und das größere Loch.

## N-57 — `prolo status` zeigte ein Notzertifikat an, als wäre alles gut

Aus einer echten Statusausgabe nach dem Einrichten:

```
  NAME                       ZEIGT AUF        ZERTIFIKAT
  wiki.prolo.me              89.58.44.224     83 Tage (Let's Encrypt)
  prolo.me                   89.58.44.224     364 Tage ()
  www.prolo.me               89.58.44.224     364 Tage ()
```

Zwei Zeilen sehen unauffällig aus und sind es nicht. **364 Tage sind kein
Let's-Encrypt-Zertifikat** — das gibt es nur mit 90 Tagen. Dahinter steht
Traefiks Notzertifikat, das er ausliefert, solange für einen Namen noch
keines ausgestellt wurde. Im Browser gibt das eine Warnseite.

Es gab sogar eine Warnung dafür — sie kam nur nie:

```bash
elif printf '%s' "$aus" | grep -qi "traefik"; then
  printf '... NOTZERTIFIKAT (%s)\n' ...
```

Der Herausgeber wurde so gelesen:

```bash
sed -n 's/.*issuer=.*O *= *\([^,]*\).*/\1/p'
```

Also **nur das `O=`-Feld**. Traefiks Notzertifikat heißt
`issuer=CN = TRAEFIK DEFAULT CERT` und hat gar kein `O=`. Heraus kam eine
leere Zeichenkette, `grep -qi "traefik"` fand darin nichts, und die Zeile
fiel in den Zweig „alles in Ordnung". Die leeren Klammern in der Ausgabe
waren der einzige Hinweis, und der sieht nach Formatierung aus.

**Eine Anzeige, die im Zweifel beruhigt, ist schlimmer als keine.** Genau
dieselbe Klasse wie `N-38`: geprüft wurde, ob ein Wort vorkommt — nicht,
ob überhaupt etwas erkannt wurde.

### Die Korrektur

Das Deuten ist jetzt vom Netzaufruf getrennt (`zertifikat_deuten`), damit
es sich mit festen Eingaben prüfen lässt. Gelesen wird `O=`, ersatzweise
`CN=`, und **wenn beides fehlt, heißt das Ergebnis `unbekannt`** — nicht
leer. `zertifikat_notbehelf` schlägt bei `traefik`, `default`, `unbekannt`,
`localhost` und `selbst` an.

Sieben Prüflinien, Erwartungswerte von Hand:

| Eingabe | erwartet |
|---|---|
| `C = US, O = Let's Encrypt, CN = R11` | `Let's Encrypt`, kein Notbehelf |
| `CN = TRAEFIK DEFAULT CERT` | `TRAEFIK DEFAULT CERT`, **Notbehelf** |
| `C = XX` | `unbekannt`, **Notbehelf** |
| ohne `notAfter` | Fehlschlag, keine Zeile |

Drei Mutationen, alle gefunden — darunter der ursprüngliche Fehler selbst
(„der `CN=`-Rückfall fällt weg"), „leer heißt wieder in Ordnung" und
„`traefik` fällt aus der Notbehelf-Liste".

### Was das für den Server heißt

Die beiden Namen brauchen ein echtes Zertifikat. Ursache ist meist, dass
der Router für sie erst neu dazugekommen ist oder die Anwendung in
Authentik noch fehlt — Traefik fordert dann keines an. Nach dem Beheben
zeigt `prolo status` dort `90 Tage (Let's Encrypt)`; bis dahin steht jetzt
ehrlich `NOTZERTIFIKAT (…) - kein Let's Encrypt` da.

## N-58 — Ein neues Netz erreicht einen laufenden Container nicht

`prolo einrichten` lief durch, meldete „Alles eingerichtet", alle sieben
Dienste liefen und meldeten sich gesund. Im Browser: **Gateway Timeout**
auf `wiki.prolo.me`.

Die Kette, rückwärts:

1. Vor dem Lauf gab es die Netze `netz-*` **noch nicht** — Wiki, Bordbuch
   und www waren darum aus.
2. Schritt 5 legte sie an. Schritt 9 startete die drei Werkzeuge; sie
   hingen danach richtig in ihrem Netz.
3. **Traefik lief schon.** Schritt 9 sah „läuft" und ließ ihn in Ruhe —
   also im alten Netzsatz, ohne `netz-wiki`.

Traefik hatte die Route, fand den Container aber nicht: `504`. Von außen
sieht das aus, als sei das Wiki kaputt. Es war kerngesund; die beiden
standen nur in verschiedenen Räumen.

**Ein Container bekommt ein Netz nicht nachträglich.** Docker hängt ihn
beim Anlegen hinein. Wer ein Netz anlegt, muss jeden, der hineingehört,
neu verbinden — und das trifft **immer** Traefik, denn der ist der
Einzige, der in alle Werkzeugnetze gehört.

Aufgelöst hat es sich später von selbst, weil `prolo aktualisieren --alle`
Traefik neu startete. Das ist genau die Sorte Heilung, die einen Fehler
verschleiert: Es ging wieder, und niemand wüsste warum.

### Die Korrektur

Schritt 9 fragt jetzt nicht mehr nur „läuft?", sondern **„hängt er auch in
seinen Netzen?"**. Für jedes externe Netz, das die Compose-Datei eines
Werkzeugs nennt, muss mindestens einer seiner Container darin hängen —
mindestens einer, weil ein Compose mehrere Dienste in verschiedenen Netzen
haben kann (Authentiks Datenbank etwa nur im internen). Fehlt eines, läuft
`docker compose up -d`, und danach wird **nachgesehen**, ob es geholfen
hat:

```
  getan   traefik neu verbunden
```

### Gemessen

Drei neue Prüflinien, gegen eine Docker-Attrappe, die sich je Container
merkt, in welchen Netzen er hängt:

- ein laufender Traefik wird in ein neues Netz nachgehängt
- danach hängt er **wirklich** drin (nicht nur die Meldung — `N-38`)
- beim nächsten Lauf passiert nichts mehr

Zwei Mutationen, beide gefunden: „ein laufender Container wird nie
nachgehängt" und „fehlende Netze werden gar nicht erst gesucht". Der
Prüfstand steht bei **12 Linien** und **4 von 4** Schwächen.

## N-59 — Ein fehlendes `middlewares=` sieht aus wie ein vergessenes

Kein Absturz, sondern eine **Entscheidung** — und der Weg, sie so
festzuhalten, dass sie nicht zur Erosion wird.

Der Auftrag war: *„Ich finde, dass es reicht, wenn Tools wie n8n in einem
extra Netz sind. Ich muss da keine zweite Anmeldung vorschalten und ggf.
Features kaputt machen."* Für Vaultwarden ist das ohnehin zwingend — die
Handy-App und die Browser-Erweiterung sprechen die API direkt und können
keine ForwardAuth-Anmeldung im Browser durchlaufen.

Bei n8n stand vorher ein **zweiter Router** ohne Anmeldung daneben, für
Webhooks und Formulare. Dessen `priority` war die einzige Klammer zwischen
„geschützt" und „offen". **Ein Router ist ehrlicher als zwei, von denen
einer aus Versehen gewinnt.**

### Das eigentliche Problem

`middlewares=authentik@file` **fehlt** — das sieht genau gleich aus, ob es
ein Entschluss war oder ein Versehen. Eine Regel, die nur im Kopf steht,
ist nach dem dritten Werkzeug weg.

Darum wird jetzt jeder Router ohne Authentik **erklärt**, mit einem Label
neben der Sache, die es beschreibt:

| Label | heißt |
|---|---|
| `prolo.anmeldung=eigene` | das ganze Werkzeug bringt seine eigene Anmeldung mit (n8n, Authentik selbst) |
| `prolo.oeffentlich=<router>` | **dieser** Router ist mit Absicht offen (`www`: Startseite und Zugangslinks) |

Dazu die Bedingungen aus `§17a`: eigenes Netz, Ratenbremse, 2FA in der
eigenen Anmeldung, und ein Vermerk im `HINWEIS` der `sicherung.conf` —
dort sieht ein Betreiber nach, nicht in den Labels.

**Eigener Code darf das nie.** Ein Werkzeug mit `Dockerfile`, das
`prolo.anmeldung=eigene` setzt, hätte die Anmeldung selbst gebaut, und
genau das tun wir nicht (`§17`).

### Zwei eigene Fehler beim Bauen der Prüfung

**Sie hat `www` gefunden — zu Recht.** Dessen öffentlicher Router war
Absicht, stand aber nirgends. Die Regel hatte nur zwei Fälle, es gibt
drei. Jetzt erklärt.

**Sie hat `n8n` gar nicht angesehen.** Die Schleife lief über
`werkzeuge` — und das ist im Prüfskript die Liste der Werkzeuge mit
eigenem `server.py`. n8n und Authentik stehen nicht darin, also genau die
Fremdwerkzeuge, um die es geht. **Die Prüfung hätte das Werkzeug
übersehen, für das sie geschrieben wurde.** Derselbe Fehler wie `N-56`:
der Umfang einer Prüfung ist selbst eine Annahme.

### Und der dritte, den erst die Mutationsprobe zeigte

Die Korrektur dazu war zuerst:

```python
sag(len(alle_werkzeuge) > len(werkzeuge), "sieht MEHR Werkzeuge an …")
```

Die Mutation „die Prüfung sieht wieder nur eigenen Code an" änderte die
**Schleife**, nicht die Listen — und blieb **grün**. Natürlich: geprüft war,
dass die Liste größer ist, nicht dass sie benutzt wird. `N-38` in Reinform.

Jetzt wird die Wirkung gemessen: *wurde tatsächlich ein Fremdwerkzeug
angesehen?*

```
ok     angesehen wurde auch mindestens ein Fremdwerkzeug (authentik, n8n)
```

**6 von 6 Mutationen gefunden**, der Prüfstand steht bei 52 Linien.

### Was das nicht behebt

Der `504` auf `n8n.prolo.me`. Authentik lag nie auf diesem Weg — n8n
antwortet schlicht nicht. Das ist ein eigener Befund und bleibt offen.

## Sicherheitsaufnahme — der Stand nach `N-44` bis `N-46`

Der Auftrag war: „Maximale Sicherheit für meine Tools und keine Fehlzugriffe
von Leuten, die das nicht dürfen." Hier steht, was davon jetzt gemessen ist,
was nur beschaffenheitsgeprüft ist, und was offen bleibt.

### Die Rechtematrix

`wiki/tests/test_rechtematrix.py`: **13 Routen × 5 Rollen = 65 Felder**, jeder
Erwartungswert von Hand eingetragen. Die Rollen sind `anonym`,
`wiki-nutzer`, `fremd` (Verwaltungsgruppe eines **anderen** Werkzeugs),
`wiki-editor`, `wiki-admin`.

| Route | anonym | nutzer | fremd | editor | admin |
|---|---|---|---|---|---|
| `/api/version`, `/gesundheit` | durch | durch | durch | durch | durch |
| `/api/ich`, `/api/baum`, `/api/suche` | **401** | durch | durch | durch | durch |
| `/api/verwaltung` | **401** | **403** | **403** | **403** | durch |
| `/api/rechte`, `/api/zweig`, `/api/neuindex` | **401** | **403** | **403** | **403** | durch |
| `/api/pruefen`, `/api/import` | **401** | **403** | **403** | durch | durch |
| `/api/einstellungen`, `/api/lesezeichen` | **401** | durch | durch | durch | durch |

Die Antwort auf die Ausgangsfrage steht in Zeile drei und vier: ein
`wiki-nutzer` bekommt auf **jede** Verwaltungsroute **403** — mit gültiger
Anmeldung, mit gültiger Einlassmarke und mit gefälschtem JSON im Körper.

### Was gemessen ist und was nicht

| | Stand | wie belegt |
|---|---|---|
| Rechteprüfung je Route und Rolle | **gemessen** | 65 Felder, 4 Mutationsproben |
| Kopfzeilen-Fälschung von außen | **gemessen** | echte Traefik-Fassung, Echo-Dienst |
| Kopfzeilen-Fälschung von innen | **gemessen** | 401 statt vorher 200 |
| Ratenbremse | **gemessen** | 24/s durch, 302/s zu 70 % abgewiesen |
| Netztrennung | **nur Beschaffenheit** | kein Docker-Daemon in der Arbeitsumgebung; 29 Prüflinien über sechs compose-Dateien |
| Gruppenfilter | **gemessen** | `gruppen` gegen `gruppen_andere` |

### Risikomatrix

| Befund | Wirkung | Eintritt | Schwere | Stand |
|---|---|---|---|---|
| `N-44` Kopfzeile ungeprüft | voller Admin auf Wiki und Bordbuch | mittel | **hoch** | **behoben**, gemessen |
| `N-45` flaches Netz | macht `N-44` erreichbar, seitliche Bewegung | — | **hoch** | **behoben**, Beschaffenheit |
| `N-46` keine Ratenbremse | Raten und Zudecken | hoch | mittel | **behoben**, gemessen |
| n8n-Webhooks ohne Anmeldung | Pfad von außen in ein Fremdprodukt | hoch | mittel | bleibt — bewusst so, jetzt aber gebremst und ohne Weg zu anderen Werkzeugen |
| Rechteprüfung in den Werkzeugen | — | — | — | **war schon in Ordnung**, jetzt belegt |
| Eine Person, ein Geheimnis für alle Werkzeuge | wer `einlass.yml` liest, kommt an jedem Werkzeug vorbei | niedrig (root nötig) | mittel | **offen** — je Werkzeug ein eigenes Geheimnis wäre besser |
| Kein Protokoll über abgewiesene Zugriffe | ein Angriffsversuch fällt niemandem auf | — | niedrig | **offen** |
| `N-42` 404 auf `/favicon.ico` | Rauschen im Protokoll | — | sehr niedrig | offen |
| `N-43` drei Primärflächen | Bedienung, nicht Sicherheit | — | sehr niedrig | offen |

### Was als Nächstes wirklich hilft

1. **Je Werkzeug ein eigenes Einlassgeheimnis** statt eines gemeinsamen. Dann
   nimmt ein gelesenes Geheimnis nur ein Werkzeug mit.
2. **Abgewiesene Zugriffe zählen und sichtbar machen** — heute merkt niemand,
   wenn jemand an der Tür rüttelt.
3. Dieselbe Matrix für das **Bordbuch**. Dort gibt es bisher nur die sechs
   Prüflinien der Vertrauensgrenze, nicht die volle Tabelle.

## Was daraus für die Abnahme folgt

`N-01` bis `N-05` sind behoben. `N-05` ist der einzige, der nach außen
sichtbar war — und der einzige, den keine Prüfung hier gefunden hätte,
weil er erst mit echten Dateirechten auf einem echten Server entsteht.

`N-11` bis `N-15` kamen aus der ersten Rückmeldung nach dem Einspielen von
Wiki 1.1.0 — und `N-11` ist der Befund, der am meisten über Prüfungen sagt:
Die Suche war technisch in Ordnung, der Index wurde gebaut, jede Prüfung war
grün. Nur stand im Index nicht, was auf der Seite zu sehen ist. Gemerkt hat
es der Mensch, der „tcp" eingetippt hat.

`N-15` ist der Gegenbeweis zur bequemen Annahme, ein Befund käme immer von
außen: Er steckte in der Lösung von `N-13`, wurde im selben Arbeitsschritt
geschrieben und im selben Durchgang gefunden — aber erst, weil der Durchgang
nach einer erlaubten Handlung noch einmal nachgefragt hat. Vierzehn von
fünfzehn Prüfungen waren grün, und die vierzehn waren nicht falsch.

`N-10` ist der schwerste Befund dieser Reihe: falsche Geldbeträge, die
niemandem auffallen müssen, weil sie plausibel aussehen, solange man sie nicht
mit der Datei vergleicht. Er zeigt dasselbe Muster wie `N-05` und `N-08` — die
Prüfung sagte „Import erfolgreich", und das war auch richtig. Nur der Betrag
war falsch.

`N-08` war der einzige Befund, der einen neuen Benutzer komplett ausgesperrt
hat — und er war mit keiner Prüfung dieses Repositorys zu finden, weil beide
Seiten für sich richtig sind: die Oberfläche schickt eine ehrliche 0, der
Server prüft ehrlich auf Plausibilität. Sichtbar wurde er erst dadurch, dass
jemand den Assistenten wirklich zu Ende geklickt hat.

`N-06` und `N-07` steckten in der Seitenvorlage, die jede künftige Wiki-Seite
kopiert; beide sind jetzt an der Quelle behoben — in `test-seite.html`, im
Vorlagenblock von `EINRICHTUNG.md` und im Editor, der neue Seiten erzeugt.
Beide zeigen dasselbe Muster wie `N-05`: der Import meldet „keine Fehler",
weil er Meta-Block, Farben und Anker prüft — nicht, ob die Seite im Browser
tut, was sie soll. Dagegen steht jetzt `wiki/tests/test_seiten.py`: es prüft
die mitgelieferten Seiten mit derselben Funktion, die beim Einspielen läuft,
und verlangt den korrigierten Pflichtteil.


---

## N-60 — Die Standmeldung nannte den Weg und verschwieg die Mauer davor

Gemessen am 20.09.2026 auf dem Server, direkt nach dem Mergen von `N-59`:

```
prolo@…:/opt/stack$ git pull origin main
Updating 6ef1d5b..c55b524
error: Your local changes to the following files would be overwritten by merge:
        n8n/docker-compose.yml
Please commit your changes or stash them before you merge.
Aborting
```

`prolo status` hatte kurz vorher gesagt: **„N Commit(s) hinter
origin/main"**. Wahr. `prolo pruefen` hatte den Weg dazu genannt: `prolo
quelle --holen`, *oder* `git pull origin main`. Auch richtig.

Und beide zusammen führten in eine Mauer, von der `quellstand.sh` zu
diesem Zeitpunkt **schon wusste**: die Variable `SCHMUTZ` — geänderte
verfolgte Dateien — wird ganz oben im Skript berechnet, lange bevor
irgendeine Meldung entsteht. Benutzt wurde sie nur im Zweig `--holen`.
`--kurz` (das ist `prolo status`) und `--pruefen` (das ist `prolo pruefen`
und die Vorprüfung von `prolo aktualisieren`) ließen sie fallen.

> **Ein Hindernis, das das Werkzeug kennt, gehört in jede Meldung, die
> einen Weg nennt — nicht erst in die, gegen die man läuft.**

Das ist nicht dasselbe wie `N-35` („die Meldung führt nicht an die
Stelle"), sondern eine Stufe davor: hier war die Meldung vollständig
korrekt und trotzdem irreführend, weil sie eine bekannte Bedingung
weggelassen hat. Eine Teilwahrheit, die zur Tat auffordert, ist eine
Falle.

### Was jetzt passiert

`prolo status`, eine Zeile:

```
1 Commit(s) hinter origin/main - Holen blockiert (1 geaenderte Datei(en))
```

`prolo pruefen` und `prolo quelle --holen` nennen dieselbe Stelle und
denselben Weg heraus — **mit der Kopie vor dem Verwerfen**:

```
  BLOCKIERT: im Arbeitsstand liegen eigene Aenderungen an
             1 verfolgten Datei(en). Daran bricht jedes Holen ab -
             auch ein 'git pull' von Hand.

              M n8n/docker-compose.yml

             Erst die Kopie, dann verwerfen - in dieser Reihenfolge:
               cd /opt/stack
               cp n8n/docker-compose.yml /root/docker-compose.yml.von-hand
               git checkout -- n8n/docker-compose.yml

             Danach erneut holen. Was anders war, zeigt danach:
               diff -u n8n/docker-compose.yml /root/docker-compose.yml.von-hand
```

Die alte Meldung im `--holen`-Zweig sagte *„Erst aufräumen (git stash /
git checkout --)"* — ein Rat, der mit dem Löschen anfängt. `git checkout
--` fragt nicht nach (`§15`). Die Kopie steht jetzt davor, und die
Reihenfolge ist eine eigene Prüflinie, keine Absichtserklärung.

### Die Mutationsprobe hat dabei meine eigene Arbeit gelöscht

Der erste Lauf der Gegenprobe fand **null von sieben** Mutationen — mit
der Begründung „Muster nicht eindeutig (0)". Der Grund: die Probe rollte
vor jeder Mutation auf die Kopie im Kratzblock zurück, und die war
**vor** dem Patch angelegt worden. Der erste Rückrollvorgang hat die
Korrektur entfernt, gegen die geprüft werden sollte.

Das ist `N-34` und `N-40` in einem, und zwar in der Form, die am
leisesten zuschnappt: die Probe lief durch, meldete ordentlich, und was
sie maß, war ein Stand ohne die Arbeit. Dazu kam eine Kontrollzeile, die
nichts kontrollierte — `diff -q datei kopie-von-derselben-datei` ist
immer grün.

> **Der Rückweg einer Probe ist der Stand, der geprüft werden soll — nicht
> der, von dem man losgegangen ist.** Und eine Kontrolle, die eine Datei
> gegen ihre eigene Kopie hält, prüft nichts.

### Prüfung

`werkzeuge/aktualisieren-pruefen.sh`: **74 ok** (vorher 64), `RC=0`.
Zehn neue Prüflinien, sieben Mutationen, **7 von 7 gefunden**.


---

## N-61 — Ein Fremdwerkzeug ist kein eigener Code, und das Gerüst tat so

Der Auftrag: *„Externe Tools, wie n8n, Bitwarden, Seafile usw. sollen normal
wie vom Hersteller vorgeschlagen laufen. Der einzige Eingriff, der von
unserer Seite passiert, ist der, dass wir eine x.prolo.me auf das gewünschte
Tool zeigen lassen und mit einem Zertifikat versehen."*

Genau das konnte `prolo neu` nicht. Es schrieb **eine** `docker-compose.yml`
mit unserem Gerüst darin und danach eine Liste mit vier Dingen, die „noch von
Hand" zu tun seien: Netz anlegen, Netz bei Traefik eintragen (an zwei
Stellen), Authentik einrichten, environment und volumes ergänzen. Wer die
Datei des Herstellers hatte, musste sie in unser Gerüst hineinschreiben — und
bei der nächsten Fassung dasselbe noch einmal, von Hand, mit dem Risiko,
eine unserer Zeilen mitzuverlieren.

### Zwei Dateien statt einer

`docker compose` liest `docker-compose.yml` **und**
`docker-compose.override.yml` von selbst, ohne `-f` und ohne Umweg. Damit
geht die Trennung sauber auf:

| Datei | wem sie gehört |
|---|---|
| `docker-compose.yml` | **dem Hersteller** — unverändert, bei neuer Fassung ersetzen |
| `docker-compose.override.yml` | **uns** — Netz, Route, Zertifikat, Anmeldung, Grenzen |

Gemessen mit Compose v5.1.1: die Labels des Herstellers bleiben stehen, unsere
kommen dazu; ein Dienst ohne eigenes `networks:` landet nur in unserem Netz;
Nebendienste (Datenbank, Worker) bleiben im projekteigenen Netz und damit
unerreichbar von außen. Und **`docker compose config` braucht keinen
laufenden Docker-Dienst** — das macht die zusammengesetzte Konfiguration zu
etwas, das man messen kann, statt sie mit regulären Ausdrücken nachzubauen.

### Was eine override-Datei NICHT kann

Sie kann eine `ports:`-Zeile nicht wegnehmen. Compose hängt Listen
aneinander. Und fast jedes Fremdwerkzeug bringt eine mit — sie ist in der
Anleitung des Herstellers der normale Weg.

> Eine `ports:`-Zeile hebelt Firewall **und** Anmeldung gleichzeitig aus. Das
> ist nicht eine Regel unter vielen, das ist der eigentliche Schutz (`§19`).

Also eine Sperre, und zwar eine **messende**: `prolo start` liest die
zusammengesetzte Konfiguration und lässt nichts los, das einen Port
veröffentlicht, ohne ihn mit `prolo.ports=<grund>` zu erklären. Traefik hat
diese Erklärung jetzt (80 und 443 sind der Eingang); alles andere wird
abgelehnt, mit dem Weg heraus in der Meldung. Die Sperre sitzt in `prolo`,
nicht in Docker: wer es wirklich will, kann immer noch
`cd <ordner> && docker compose up -d` tippen. Der **geführte** Weg soll nur
nicht der sein, auf dem man aus Versehen einen Dienst ins offene Netz stellt.

Dieselbe Sperre gilt für einen Router ganz ohne Anmeldung: entweder
`authentik@file`, oder `prolo.anmeldung=eigene` mit Grund (`§17a`) — sonst
kein Start.

### Und die Anmeldung wird gefragt, nicht vorgegeben

`prolo neu` fragt: Authentik davor, oder eigene Anmeldung des Werkzeugs?
**Ohne Vorgabe** — ein Enter darf hier nicht genügen. Bei `--art eigen`
entfällt die Frage, weil `§17` keine Wahl lässt.

### Das Netz zuerst, dann der Ordner

Die erste Fassung legte den Ordner an und richtete danach das Netz ein.
Schlug das fehl, stand ein Ordner da, den niemand von einem fertigen
Werkzeug unterscheiden kann. Jetzt läuft das Netz zuerst: geht es nicht,
entsteht gar nichts (`§12`).

### Und ein dritter Prüfer, der beim Umstellen von n8n die Hälfte übersah

Beim Umstellen von `n8n/` auf die zwei Dateien fiel `grenze-pruefen.sh` von
61 auf 57 Prüfzeilen — **und blieb grün**. Der Grund: es las nur
`docker-compose.yml`, fand dort kein `traefik.enable=true` mehr (das steht
jetzt im Overlay) und sprang über n8n hinweg.

> Der Prüfer wurde **leiser**, nicht richtiger. Und „alles grün" hieß
> danach: „ich habe n8n nicht angesehen."

Die Wirkungsmessung, die genau davor schützen sollte, war zu schwach: sie
verlangte „mindestens **ein** Fremdwerkzeug angesehen", und `authentik`
blieb übrig. Jetzt wird gegen eine Liste gemessen, die **ohne** den Filter
der Schleife entsteht: jedes Werkzeug, das irgendwo in seinen
Compose-Dateien einen Router hat, muss angesehen worden sein.

```
ok     kein Werkzeug mit Router blieb ungeprueft (6 angesehen)
```

**Dreimal derselbe Fehler in einer Sitzung** — `N-56`, dann `N-59`, jetzt
hier. Der Umfang einer Prüfung ist selbst eine Annahme, und eine Zahl, die
sinkt, ohne dass jemand hinsieht, ist die leiseste Art, eine Prüfung zu
verlieren.

### Prüfung

`werkzeuge/neu-pruefen.sh`, **76 ok, RC=0**. Der Prüfer reicht
`docker compose config` an das echte `docker` durch — das ist die einzige
Stelle, an der wirklich gemessen und nicht nachgebildet wird.

`werkzeuge/neu-gegenprobe.py`: **12 Mutationen, 12 gefunden.** Die Fehler
landen in den Kopien im Wegwerfordner, nie im Arbeitsstand (`N-34`, `N-60`).

**Eine Prüfzeile war beim ersten Lauf grün, ohne zu prüfen.** „eigener Code
mit eigener Anmeldung wird abgelehnt" rief `prolo neu` ohne `--grund` auf —
und scheiterte damit an der fehlenden Begründung, nie an der `§17`-Regel. Die
Mutation, die genau diese Regel ausbaute, blieb unentdeckt. Jetzt wird
`--grund` mitgegeben, und zusätzlich geprüft, dass `§17` der genannte Grund
ist.

---

## N-62 — Man konnte nicht nachsehen, wer in welchem Netz hängt

Die Netztrennung aus `N-45` ist die wichtigste Schutzschicht des Stacks. Sie
war aber nur von Hand herzustellen — `docker network create`, dann zwei
Stellen in der Traefik-Datei, dann Traefik **neu anlegen** (`N-58`) — und vor
allem: man konnte sie nicht **ansehen**. „Welche Netze gibt es, wer hängt
drin, hängt Traefik überall mit, ist irgendwo ein Router offen?" war eine
Frage an drei `docker`-Befehle und fünf Dateien.

`prolo netze` beantwortet sie:

```
Netze
  NETZ                 GEHOERT ZU               TRAEFIK  DOCKER  CONTAINER
  netz-admin           admin                    ja       ja      1
  netz-n8n             n8n                      ja       ja      1
  ...
Werkzeuge
  WERKZEUG      DIENST          NETZ                     SCHUTZ      OFFENE PORTS
  n8n           n8n             netz-n8n                 eigene      -
  traefik       traefik         netz-authentik,netz-bo.. -           80,443 (Eingang des Stacks)
```

Dazu `anlegen` (Netz + **beide** Stellen bei Traefik), `schliessen` (nur,
wenn es niemand mehr erklärt und kein Container mehr drin hängt) und
`umziehen <werkzeug> <netz>`.

**Umziehen ist das Riskanteste hier**, darum mit Kopie, Ersetzen, **Messen**
und Rücknahme: nach dem Ersetzen wird die zusammengesetzte Konfiguration
gelesen, und steht dort nicht genau das erwartete Netz, geht alles zurück.
Keine Datei bleibt halb geändert (`§12`).

### Die Spalte, um die es eigentlich geht

**SCHUTZ.** Sie wird aus der Middleware-Kette in den Labels **gelesen**, nicht
geraten: `authentik@file` → „authentik"; `prolo.anmeldung` → dessen Wert;
`prolo.oeffentlich` → „öffentlich"; ein Router ohne all das → **`OFFEN`**.
Ein fehlendes `middlewares=` sieht sonst genauso aus wie ein vergessenes
(`N-59`), und es sah bisher niemand.

### Drei Fehlalarme, die der eigene Prüfer erst erzeugt hat

1. **`authentik_internal` sollte Traefik bekommen.** Das ist Authentiks
   projekteigenes Netz — da hat Traefik nichts verloren. Die Regel „jedes
   erklärte Netz braucht Traefik" war zu breit. Jetzt bleiben projekteigene
   Netze draußen, erkannt am Namen `<projekt>_<schlüssel>`.
2. **Traefiks Ports 80/443 galten als Verstoß.** Sind sie nicht — sie sind
   der Eingang. Aber das stand nirgends. Jetzt steht es dort, als Label.
3. **`docker compose config` scheiterte auf einem frischen Klon.** An jedem
   `${...}` aus einer `.env`, die es gerade nicht gibt — also an fast allem.
   `--no-interpolate` behebt es: Netze und Labels benutzen keine Variablen.

> Ein Prüfer, der jeden Tag denselben Fehlalarm gibt, ist schlimmer als
> keiner. Beim echten Fund sieht dann niemand mehr hin.

### Geteilte Netze sind jetzt erlaubt — wenn sie erklärt sind

Der Wunsch war ein Testbereich: *„damit kann ich mir ein Netz test anlegen
und mir da irgendwelche Docker-Container anlegen."* Bisher verlangte
`netze-pruefen.sh` ein Netz je Werkzeug, ohne Ausnahme. Jetzt darf geteilt
werden — aber **alle** Beteiligten schreiben `prolo.netz.geteilt=<grund>`.
Sonst sieht ein geteiltes Netz genauso aus wie ein verwechseltes.

### Prüfung

`werkzeuge/netze-pruefen.sh`: **42 ok**, RC=0 (vorher 35). Es liest jetzt
**beide** Compose-Dateien — ein Prüfer, der bei einem Fremdwerkzeug nur die
Herstellerdatei liest, sieht von Netz, Route und Anmeldung nichts und meldet
Entwarnung für etwas, das er gar nicht angesehen hat.

---

## N-63 — Der Stack hatte keine Ansicht

Es gab keinen Ort, an dem man den Zustand des Stacks **sieht**. `prolo status`
sagt viel, aber im Terminal und nur auf dem Server. Der Auftrag: *„fange
außerdem mit der Admin-Seite an … Das soll eine Umgebung sein, die ganz
einfach zu administrieren und zu verwalten ist, aber trotzdem mächtig und
sicher. Also muss die Admin-Seite sehr gut geschützt sein."*

`admin/` — eigener Code, Python-Standardbibliothek, hinter Authentik **und**
hinter der Gruppe `admin`. Vier Ansichten: Übersicht, Werkzeuge, Netze,
Einstellungen.

### Was sie liest, und warum das der schmalere Weg ist

Zwei lesende Aufrufe an den Vermittler vor dem Docker-Socket:
`/containers/json` und `/networks`. **Kein Zugriff auf `/opt/stack`.** Der
naheliegende Weg wäre gewesen, den Stack-Ordner schreibgeschützt
hineinzuhängen — dann läge aber jede `.env` in Reichweite. So liegt keine.

Was bleibt: wer lesend an der Docker-API sitzt, kann die
Umgebungsvariablen von Containern abfragen, und da stehen Geheimnisse drin.
Das ist genau die Berechtigung, die **Traefik seit `B-02` ohnehin hat** —
diese Seite weitet sie nicht aus, sie teilt sie. Der Preis ist bewusst
bezahlt und steht in der `docker-compose.yml`, nicht in einer Fußnote.

### Was sie mit Absicht NICHT tut

Sie startet nichts und hält nichts an. Dafür müsste der Vermittler
schreibende Aufrufe durchlassen (`POST: 1`), und damit wäre aus einer
Übersichtsseite der kürzeste Weg zur Serverübernahme geworden. Kommt das
später, dann mit einem **eigenen** Vermittler für genau diesen einen Aufruf
und als eigene Entscheidung — nicht nebenbei.

### Der Fund, den sie liefern soll

Die Übersicht zählt nicht Container, sondern **Punkte zum Klären**: ein
Router ohne Anmeldung und ohne Erklärung, ein unerklärt offener Port, ein
Container, der in einem anderen Netz läuft als sein Label sagt (`N-58`), ein
Dienst, der nicht läuft. Das ist die Hero-Kennzahl, und sie steht oben.

### Prüfung

`admin/tests/alle.sh`: **36 Tests, RC=0**, Fassung an allen drei Stellen
gleich. `admin/tests/gegenprobe.sh`: **14 Mutationen, 14 gefunden** — darunter
„ein Router ohne Anmeldung gilt als geschützt", „die Marke von Traefik wird
nur am Anfang verglichen" und „Labels werden ungefiltert ausgegeben".

**Zwei Tests haben sich beim ersten Lauf gegenseitig belogen.** `urllib`
folgt einer 303 von selbst — der Test maß die Seite *danach* und nie die
Weiterleitung. Und `setUpClass` hatte `docker_lesen` global ersetzt und nie
zurückgegeben, sodass der nächste Test gegen die Attrappe lief und etwas
anderes prüfte, als er zu prüfen glaubte.

### Im Browser, nicht nur getestet

Vier Ansichten × drei Breiten (360/768/1920) × zwei Themen, dazu Zoom 200 %:
**150 Messpunkte, 0 Fehler** — nach zwei echten Funden:

- **Kontrast 3.3:1** beim aktiven Eintrag der Tabbar im Dunkelmodus
  (`--accent` auf `--chrome`, 12 px — `§8` verlangt 4.5:1). Behoben über die
  Kontrast-Ausnahme aus `§2`: `--accent-ink`. Der 3-px-Strich bleibt
  `--accent`, die Farbe als Signal geht nicht verloren.
- **Die Marke fehlte am Handy.** Die Sidebar ist unter 900 px ausgeblendet —
  und damit war die Marke weg, die `§5` auf jeder Ansicht verlangt. Das sieht
  man beim Lesen des Codes nicht.

Dazu Tabellenspalten von Hand gesetzt (die Zustandsspalte brach
„Up 13 days (healthy)" auf vier Zeilen) und die Segmentknöpfe von 38 auf
44 px (`§9` schlägt die 38 aus `§5`).

**Und der Prüfer wurde gegengeprobt** (`§14a`): blasser Text, seitliches
Scrollen und zu kleine Touchziele wurden absichtlich eingebaut — **3 von 3
gefunden**. Die Farben kommen als `oklch()` und werden über die Leinwand des
Browsers umgerechnet, nicht von Hand: ein Prüfer, der `oklch` als RGB liest,
hat hier schon einmal gelogen.


---

## N-64 — „Liefert keine lesbare Konfiguration" — und das war alles

Gemessen am 21.09.2026 auf dem Server, erster Lauf von `prolo netze` nach
dem Einspielen:

```
Werkzeuge
  WERKZEUG      DIENST          NETZ                     SCHUTZ
  admin         admin           netz-admin,socket        authentik
  authentik     server          internal,netz-authentik  eigene
  n8n           n8n             netz-n8n                 eigene
  traefik       traefik         netz-admin,netz-authen.. -
  wiki          wiki            netz-wiki                authentik

Zu klaeren
  Diese Ordner liefern keine lesbare Konfiguration: bordbuch www
     Nachsehen mit: cd /opt/stack/<ordner> && docker compose config
```

Die erste Frage danach war: **„Wo ist das Bordbuch?"** Genau die Frage, die
eine Übersicht nicht auslösen darf.

### Was schiefging

`docker compose config` war fehlgeschlagen, und das Skript hatte die
Meldung dazu **in der Hand**:

```bash
docker compose config --no-interpolate --format json 2>/dev/null
```

`2>/dev/null`. Der einzige Satz, der den Unterschied zwischen „die Datei ist
kaputt", „ich darf sie nicht lesen" und „dieses docker kennt den Schalter
nicht" ausmacht — weggeworfen, und übrig blieb, dass irgendetwas nicht geht.

> **Eine Meldung, die eine Folge benennt und die Ursache verschweigt, die
> sie gerade in der Hand hatte, ist keine Meldung.** Das ist `N-60` noch
> einmal, an einer anderen Stelle: dort wurde das Hindernis verschwiegen,
> das den genannten Weg versperrt, hier die Ursache des gemeldeten
> Zustands.

Jetzt steht sie da:

```
  bordbuch: die Konfiguration laesst sich nicht lesen. Docker sagt:
     failed to read /opt/stack/bordbuch/.env: line 1: key cannot contain a space
     Selbst nachsehen - genau diesen Aufruf macht prolo:
       cd /opt/stack/bordbuch && docker compose config --no-interpolate
```

### Der zweite Fehler: der Hinweis führte woandershin

Der alte Text riet zu `docker compose config` — **ohne** `--no-interpolate`.
Das ist nicht derselbe Aufruf. Auf einem Stand ohne `.env` scheitert der
Befehl aus der Anleitung an der Interpolation, während das Skript an etwas
ganz anderem gescheitert war. Wer dem Hinweis folgt, sucht an der falschen
Stelle.

> Ein Hinweis zum Nachsehen nennt **genau den Aufruf**, den das Werkzeug
> gemacht hat. Sonst schickt er einen an eine andere Stelle als die, an der
> es geklemmt hat.

### Der dritte: ein Rat, der immer danebensteht

Die erste Korrektur hängte an jede solche Meldung „steht dort *permission
denied*, dann mit sudo". Bei einem YAML-Fehler ist das Unsinn. Ein Rat, der
immer danebensteht, ist nach dem dritten Mal Tapete. Jetzt kommt er nur,
wenn die Meldung ihn hergibt.

### Und der vierte, den erst der Probelauf zeigte

Die erste Fassung meldete brav „Docker sagt:" — und danach eine **leere
Zeile**. Grund: der Aufrufer schreibt

```bash
j=$(konfig_json "$t")
```

und alles, was die Funktion dabei an Variablen setzt, bleibt in der Subshell
der Kommandoersetzung zurück. Die Meldung geht jetzt über eine Datei.

Vier Anläufe für eine Fehlermeldung. Sie ist deshalb nicht überbezahlt: die
Frage „Wo ist das Bordbuch?" war die teuerste Zeile des ganzen Laufs.

### Prüfung

`werkzeuge/neu-pruefen.sh`: **83 ok**, RC=0 (vorher 76). Sechs neue
Prüflinien, drei neue Mutationen — „die Meldung wird wieder weggeworfen",
„es wird ein anderer Aufruf genannt als der gemachte", „der sudo-Rat kommt
auch bei einem YAML-Fehler".


---

## N-65 — „Von Hand eintragen" war eine Sackgasse

Gemessen am 21.09.2026 beim Aufsetzen von n8n:

```
  N8N_ENCRYPTION_KEY
    Fehlt ueberall - und dieses Geheimnis wuerfelt das
    Werkzeug NICHT (es steht auch ausserhalb seiner Datei).
    Von Hand eintragen: /opt/stack/n8n/.env

  Nichts zu verteilen.
```

Drei Dinge daran waren falsch.

### 1. Die Begründung stimmte nicht

*„Es steht auch außerhalb seiner Datei"* — für ein n8n, das gerade frisch
aufgesetzt wird, steht es **nirgends**. Es gab keinen alten Wert, den ein
neuer hätte kaputtmachen können.

`WECHSEL=haende` heißt: ein **neuer** Wert macht etwas kaputt, das den
**alten** hält. Das Werkzeug hat daraus „niemals anfassen" gemacht und
damit zwei verschiedene Dinge verwechselt:

| | |
|---|---|
| **wechseln** | einen vorhandenen Wert ersetzen — bei `haende` gefährlich |
| **füllen** | eine leere Stelle besetzen, wo es keinen alten gibt — genau wofür `--verteilen` da ist |

Beweisen können die Dateien es nicht: `PG_PASS` steht auch in PostgreSQL,
der Schlüssel von n8n auch im Volume. „Fehlt in allen Dateien" heißt nicht
„es gibt ihn nirgends". Also wird **gefragt**, statt zu verweigern oder
blind zu würfeln:

```
Frisch aufgesetzt, also noch kein alter Wert irgendwo? [j/N]
```

Ohne Terminal antwortet `--frisch` dasselbe. Und `--frisch` ist **kein**
Generalschlüssel: steht der Wert schon irgendwo, wird er auch damit nicht
angefasst — sonst wäre aus der Bremse ein Schalter geworden, der genau das
tut, wovor `haende` schützen soll. Dafür gibt es eine eigene Prüflinie.

### 2. Die Meldung sagte nicht, wie

*„Von Hand eintragen: /opt/stack/n8n/.env"* — und dann? Womit? Welche
Zeile? Das ist `§7` verfehlt: eine Meldung sagt, **was zu tun ist**. Jetzt:

```
    Nicht gewuerfelt. Von Hand:
      /opt/stack/n8n/.env
        Zeile:  N8N_ENCRYPTION_KEY=<wert>
      Einen Wert herstellen:  openssl rand -base64 33

    Oder, wenn es wirklich ein frischer Aufbau ist:
      sudo prolo geheimnisse --verteilen --frisch
```

Dazu die Erklärung aus der `geheimnisse.conf` — dort steht ja, was ein
neuer Wert kostet, und genau das gehört an diese Stelle.

### 3. Die Anleitung daneben versprach das Gegenteil

`n8n/docker-compose.override.yml`, `werkzeuge/ANLEITUNG.md` und die
`${…:?}`-Meldung sagten alle: *„kommt aus `sudo prolo geheimnisse
--verteilen`"*. Das tat es nicht.

> Eine Anleitung, die etwas verspricht, was das Werkzeug verweigert, ist
> schlimmer als keine: man glaubt ihr und sucht den Fehler bei sich. Beide
> gehören in **denselben** Arbeitsschritt.

### Prüfung

`werkzeuge/geheimnisse-pruefen.sh`: **149 ok**, RC=0 (vorher 140). Neun
neue Prüflinien, darunter „`--frisch` fasst einen vorhandenen
`haende`-Wert NICHT an" — die wichtigere Richtung.

`werkzeuge/geheimnisse-pruefen.sh --gegenprobe`: **42 von 42 gefunden**
(vorher 37). Neu unter anderem „ein `haende`-Geheimnis wird blind
gewürfelt", „die Meldung sagt nicht, WIE man einen Wert macht" und
„`--frisch` tut gar nichts" — ein Schalter, der nichts tut, ist schlimmer
als keiner.


---

## N-66 — Ein Werkzeug, das im Git steht, wurde neu angelegt statt zurückgeholt

Gemessen am 21.09.2026. n8n war auf dem Server entfernt worden, lag aber
weiter im Repository — es ist ja versioniert wie alles andere. Der nächste
Griff war der naheliegende:

```
prolo@…:/opt/stack$ sudo prolo neu n8n

  Was fuer ein Werkzeug?
  Wahl [1]: 1
  Abbild des Herstellers (z. B. vaultwarden/server:1.34.1): n8n
Ohne Fassung nicht erlaubt (§19: nie latest, immer fest).
Beispiel: n8n:1.2.3
```

Zwei Fehler in fünf Zeilen.

### 1. Es hätte gar nicht fragen dürfen

`prolo neu` prüfte nur, ob der **Ordner** da ist. Er war es nicht — aber die
Dateien standen im Git, fertig und richtig. Wäre der Abbildname durchgegangen,
hätte das Gerüst genau die `docker-compose.override.yml` verdrängt, die
längst stimmte, und der nächste `git pull` hätte einen Konflikt geliefert.

> **„Nicht auf der Platte" heißt nicht „gibt es nicht".** In einem
> versionierten Stack ist die Platte nur eine Auslage; das Repository ist
> der Bestand.

Jetzt:

```
Es gibt n8n schon - im Git, nur hier nicht ausgecheckt:
  n8n/docker-compose.yml
  n8n/docker-compose.override.yml
  …
  Das will ZURUECKGEHOLT werden, nicht neu angelegt:
    cd /opt/stack && git checkout -- n8n/

  Soll es wirklich weg, gehoert es auch im Git weg - sonst holt
  der naechste Pull es zurueck oder bricht daran ab:
    cd /opt/stack && git rm -r n8n && git commit -m "n8n entfernt"
```

Und `prolo entfernen` sagt dasselbe **vorher** und noch einmal am Ende:
solange die Entscheidung nicht getroffen ist, steht der Arbeitsstand auf
gelöschten Dateien — und der nächste `git pull` bricht daran ab. Dass er
das tut, sagt seit `N-60` immerhin die Standmeldung; **warum** er es tut,
sagt jetzt der Befehl, der es verursacht hat.

### 2. „Beispiel: n8n:1.2.3" war schlicht falsch

Das Abbild von n8n heißt `docker.n8n.io/n8nio/n8n`. Die Meldung nahm die
Eingabe des Menschen und hängte eine Fassung an — und schlug damit einen
Namen vor, den es nicht gibt. Eine Fehlermeldung, die rät, ist schlimmer
als eine, die nur tadelt: man tippt den Vorschlag ab und läuft in den
nächsten Fehler.

Jetzt nennt die Frage schon vorher drei echte Namen und `prolo suchen`, und
die Fehlermeldung wiederholt den echten n8n-Namen als Gegenbeispiel zum
eingetippten.

### Die Gegenrichtung ist die wichtigere Prüflinie

Eine Bremse, die bei **jedem** Namen greift, wäre schlimmer als keine —
dann ließe sich gar kein Werkzeug mehr anlegen. Darum steht neben
„im Git, nicht ausgecheckt → abgelehnt" die Zeile „nicht im Git → wird
normal angelegt", und die Mutation *„die Git-Bremse greift auch bei einem
ganz neuen Namen"* muss auffallen.

### Prüfung

`werkzeuge/neu-pruefen.sh`: **91 ok**, RC=0 (vorher 83).
`werkzeuge/prolo-pruefen.sh`: **51 ok**, RC=0 (vorher 47) — darunter
„ohne Git kommt der Hinweis nicht", damit aus dem Hinweis keine Tapete wird.
`werkzeuge/neu-gegenprobe.py`: **18 Mutationen** (vorher 15).


---

## N-67 — Die Meldung nannte die Aufgabe, nicht den Befehl, der sie erledigt

Gemessen am 21.09.2026, beim Aufsetzen von n8n nach `N-65`. Die Frage kam
richtig, die Antwort war „j" — und dann:

```
  Frisch aufgesetzt, also noch kein alter Wert irgendwo? [j/N] j
    NICHT angefasst - an 2 von 2 Stellen ginge es nicht:
      /opt/stack/n8n/.env
        die Datei fehlt. Anlegen aus .env.beispiel, dann noch einmal.
```

Wieder eine Sackgasse, und diesmal eine besonders ärgerliche: **es gibt
einen Befehl, der genau das tut.** `prolo einrichten` legt jede fehlende
Geheimnisdatei aus ihrer Vorlage an, ergänzt die leere Zeile darin, und ist
idempotent — Schritt 6 seit `N-54`. Die Meldung wusste nur nichts davon und
schickte zum Abtippen.

> Eine Meldung, die die **Aufgabe** nennt statt des **Befehls**, der sie
> erledigt, ist eine halbe Meldung. `§7` verlangt, dass sie sagt, was zu tun
> ist — und „was zu tun ist" heißt hier: dieser eine Befehl.

Jetzt:

```
        die Datei fehlt. Das legt 'sudo prolo einrichten' an (aus
        .env.beispiel, mit der leeren Zeile darin) - danach noch einmal.

    Das ist kein Fehler, sondern ein ausgelassener Schritt:
      sudo prolo einrichten
    legt jede fehlende Geheimnisdatei aus ihrer Vorlage an.
    Er laeuft beliebig oft; beim zweiten Mal passiert nichts.
```

Der gebündelte Hinweis kommt **nur**, wenn ausschließlich Dateien fehlen.
Klemmt es aus einem anderen Grund, hat er dort nichts zu suchen — ein Rat,
der immer danebensteht, ist nach dem dritten Mal Tapete (`N-64`).

### Warum der Schritt ausgelassen war

n8n kam per `git pull` dazu, nicht über `prolo neu`. Ein Werkzeug, das so
in den Stack kommt, bringt seine `.env.beispiel` mit, aber keine `.env` —
und niemand sagt einem, dass `prolo einrichten` noch einmal laufen will.
Jetzt sagt es die Stelle, an der es auffällt.

### Und die Mutationsprobe fand ihre eigene Lücke

Zwei Stück:

- Die Prüfzeile `"prolo einrichten" in aus` war grün, obwohl die Mutation
  den Befehl aus der **Grund**-Meldung entfernt hatte — er stand ja noch im
  gebündelten Hinweis darunter. Eine Prüfung auf „steht irgendwo in der
  Ausgabe" lässt eine von zwei Stellen verschwinden. Jetzt ist jede Zeile
  an ihre eigene Stelle gebunden.
- Die Mutation *„eine fehlende Datei fällt nicht auf"* traf die **falsche
  Funktion**: `os.path.exists(self.pfad)` steht zweimal in der Datei, in
  `lesen()` und in `schreibbar()`, und ersetzt wurde die erste. Sie bewies
  damit gar nichts. Dasselbe war in dieser Sitzung schon einmal passiert —
  **ein Mutationsmuster muss eindeutig sein, und das prüft niemand für
  einen.**

### Prüfung

`werkzeuge/geheimnisse-pruefen.sh`: **156 ok**, RC=0 (vorher 149).
`--gegenprobe`: **45 von 45 gefunden** (vorher 42).

---

## N-68 — Die Übersicht zeigte die Kollision und nannte sie nicht

Derselbe Lauf. Auf dem Server lag neben `n8n/` noch ein `n8n_alt/` — eine
Kopie von vor dem Umbau. `prolo netze` zeigte das brav:

```
  netz-n8n             n8n,n8n_alt              ja       ?       ?

  WERKZEUG      DIENST          NETZ             SCHUTZ      OFFENE PORTS
  n8n_alt       n8n             netz-n8n         eigene      -
  n8n           n8n             netz-n8n         eigene      -
```

Und sagte dazu: nichts. Kein Wort unter „Zu klären".

Dabei stehen da zwei Dinge, die beide falsch sind:

1. **Zwei Werkzeuge in einem Netz.** In einem Docker-Netz erreicht jeder
   Container jeden anderen direkt, ohne Traefik und ohne Anmeldung — das
   ist `N-45`, die teuerste Narbe im ganzen Stack.
2. **Zwei Router auf demselben Hostnamen.** Beide beanspruchten
   `n8n.prolo.me`. Traefik nimmt einen davon, und welchen, sieht man
   nirgends.

> Eine Zeile, die man selbst deuten muss, ist keine Meldung. Die Übersicht
> hatte beides vor Augen und hat es als Datenzeile behandelt.

### Was jetzt kommt

```
  netz-x teilen sich mehrere Werkzeuge: a b
     In einem Netz erreicht jeder Container jeden anderen direkt - ohne
     Traefik und ohne Anmeldung (N-45). Erlaubt ist das, aber als
     Entscheidung, nicht aus Versehen. Wer teilt, sagt warum:
       - "prolo.netz.geteilt=<grund>"
     Es fehlt bei: a b

  gleich.prolo.me wird von mehreren Diensten beansprucht:
       a/a
       b/b
     Traefik nimmt einen davon, und welchen, sieht man nirgends.
```

`netze-pruefen.sh` kannte die Regel für geteilte Netze seit `N-62` — aber
nur als **statische** Prüfung über das Repository. Auf dem Server, wo ein
Ordner auch ohne Git entstehen kann, sah sie niemand.

### Gast ist nicht gleich Eigentümer

Die erste Fassung beanstandete `socket` — Traefik, socket-proxy und admin
hängen dort gemeinsam drin, und das ist so gebaut. Die Regel war zu grob.

> Wer sein Netz **selbst anlegt**, teilt nichts; er ist der Eigentümer. Erst
> ein **zweiter Gast** macht daraus eine gemeinsame Fläche.

Gezählt werden darum nur die Werkzeuge, die sich in ein *fremdes* Netz
hängen (`external: true`). socket-proxy legt `socket` an, admin ist der eine
Gast — kein Fund. Kämen zwei Gäste dazu, wäre es einer.

Und die beiden Beanstandungen schalten sich nicht gegenseitig stumm: wer
das geteilte Netz erklärt, wird den doppelten Hostnamen trotzdem nicht los.
Eigene Prüflinie dafür.

### Prüfung

`werkzeuge/neu-pruefen.sh`: **99 ok**, RC=0 (vorher 91).
`werkzeuge/neu-gegenprobe.py`: **21 von 21 gefunden** (vorher 18).

Und genau diese Mutation — *„auch ein Netz mit genau einem Gast gilt als
geteilt"* — **entwischte im ersten Lauf**. Nicht, weil die Prüfzeile falsch
war, sondern weil der Fall im Wegwerfstack **gar nicht vorkam**: es gab dort
kein Netz mit Eigentümer und genau einem Gast, also änderte die Mutation
nichts, was jemand hätte sehen können.

> Eine Prüfzeile über einen Fall, den der Prüfstand nicht herstellt, ist
> grün aus Mangel an Gelegenheit. Der Stand muss den Fall **haben**, nicht
> nur die Zeile darüber.

Jetzt legt der Prüfstand ihn an (ein `vermittler`, der ein Netz mit festem
Namen erzeugt, und ein `gast`, der sich hineinhängt) — und daneben steht die
Zeile „mit einem **zweiten** Gast wird es einer", damit die erste nicht
grün bleiben kann, wenn gar nichts mehr geprüft wird.

---

## N-69 — Ursache und Wirkung standen nebeneinander, gesagt wurde es nie

`admin.prolo.me` ließ sich im Browser nicht öffnen: „Seite ist nicht
sicher". `prolo status` hatte den Grund längst gemessen — in zwei Zellen
derselben Zeile:

```
  NAME                       ZEIGT AUF        ZERTIFIKAT
  admin.prolo.me             217.160.0.1 (FREMD) keine Antwort auf 443
  auth.prolo.me              89.58.44.224     80 Tage (Let's Encrypt)
```

Beide Angaben stimmen. Der Fußtext erklärte auch beide — `FREMD` in einem
Absatz, `NOTZERTIFIKAT` in einem zweiten. Nur das Wort dazwischen fehlte:
**weil**. Der Name zeigt nicht hierher, also erreicht die Prüfung von
Let's Encrypt diesen Server nie, also entsteht kein Zertifikat, also
meckert der Browser. Vier Glieder, drei davon im Werkzeug, keines
verbunden.

Gefragt wurde genau danach:

> „Das Problem mit dem Nicht sichere Verbindung hatten wir schonmal. Ich
> weiß nicht, was da der Fix ist, aber kann man das nicht automatisch
> machen lassen?"

Die Antwort auf die zweite Hälfte ist: das Zertifikat **ist** automatisch.
Traefik holt es von selbst, sobald der Name hierher zeigt. Automatisieren
lässt sich nur der A-Eintrag beim DNS-Anbieter nicht — dafür bräuchte der
Server dessen API-Schlüssel, und der hätte auf einer Maschine, die im Netz
steht, nichts verloren (§21). Was das Werkzeug also schuldig blieb, ist
**nicht die Tat, sondern der Satz**.

> Zwei richtige Zellen nebeneinander sind keine Diagnose. Wer die Ursache
> und die Wirkung beide gemessen hat, sagt auch, dass die eine die andere
> ist — sonst verlangt er vom Menschen genau die Arbeit, für die es ihn
> gibt. Dieselbe Narbe wie `N-60` und `N-64`, nur eine Zeile weiter rechts.

### Was jetzt kommt

```
  NAME                       ZEIGT AUF        ZERTIFIKAT
  admin.beispiel             217.160.0.1 (FREMD) keine Antwort auf 443
  n8n.beispiel               217.160.0.1 (FREMD) keine Antwort auf 443
  auth.beispiel              9.9.9.9          80 Tage (Let's Encrypt)
  notzert.beispiel           9.9.9.9          NOTZERTIFIKAT (…) - kein Let's Encrypt

  Was daraus folgt:

  admin.beispiel hat kein Zertifikat, WEIL der Name auf 217.160.0.1 zeigt und nicht hierher.
    A-Eintrag fuer admin.beispiel auf 9.9.9.9 setzen.
  n8n.beispiel hat kein Zertifikat, WEIL der Name auf 217.160.0.1 zeigt und nicht hierher.
    A-Eintrag fuer n8n.beispiel auf 9.9.9.9 setzen.
  notzert.beispiel zeigt hierher, und trotzdem kommt kein Zertifikat
  von Let's Encrypt. Am Namen liegt es also nicht.

  Let's Encrypt prueft ueber Port 80 an genau der Adresse, auf die der Name
  zeigt. Ist das nicht dieser Server, kann hier kein Zertifikat entstehen -
  im Browser steht dann "Seite ist nicht sicher".
  Zu tun ist es beim DNS-Anbieter, nicht auf dem Server. […]
  Danach holt Traefik das Zertifikat von selbst, meist in unter einer
  Minute. Sofort versuchen lassen:
    sudo prolo start traefik

  Haeufigste Ursache sind die Rechte an acme.json (N-05). Woran es wirklich
  liegt, sagt Traefik selbst:
    sudo prolo protokoll traefik
```

Vier Lagen, und jede hat einen Grund:

1. **Der Satz nennt das Warum** und die IP, auf die der A-Eintrag zeigen
   muss — nicht „richtig setzen", sondern `auf 9.9.9.9`.
2. **Zeigt der Name hierher, wird das ausdrücklich gesagt.** „Am Namen
   liegt es also nicht" schließt die halbe Fehlersuche, bevor sie anfängt.
   Eine Meldung, die in beiden Fällen gleich klingt, schickt in einem der
   beiden in die Irre.
3. **Die Erklärung kommt einmal je Art, nicht einmal je Name.** Bei drei
   betroffenen Namen wären es dreimal dieselben zehn Zeilen gewesen — nach
   dem zweiten Mal Tapete (§7).
4. **Wo alles heil ist, steht nichts.** Eine Folgerung, die immer kommt,
   wird überlesen.

`prolo dns` kennt keine Zertifikate, weiß aber, dass eines daran hängt —
und sagt es jetzt, samt Ziel-IP und `sudo prolo start traefik`.

### Was sich NICHT automatisieren lässt — und warum das in Ordnung ist

Der A-Eintrag liegt beim DNS-Anbieter. Ihn vom Server aus zu setzen hieße,
dessen API-Schlüssel dort zu hinterlegen: ein Wert, mit dem man jede
Subdomain auf jeden Rechner der Welt zeigen lassen kann, auf der Maschine,
die direkt am Netz hängt. Das ist der Handgriff, der ein Mensch bleibt.
Alles danach läuft von selbst.

### Prüfung

`werkzeuge/prolo-pruefen.sh`: **87 ok**, RC=0 (vorher 41).
`werkzeuge/prolo-gegenprobe.py` (neu): **14 von 14 gefunden**.

Die Gegenprobe gab es für `prolo` bis jetzt nicht — geprüft wurde die
Datei im Arbeitsstand, mutiert hätte sich nur die Kopie im Wegwerfordner.
Beides zeigt jetzt auf dieselbe Kopie (`QUELLE_PROLO`), sonst wäre die
Probe grün gewesen, ohne je etwas verändert zu haben.

Und eine Mutation **entwischte** im ersten Lauf: *„ein abgelaufenes
Zertifikat gilt als vorhanden"*. Nicht weil die Prüfzeile fehlte, sondern
weil der Prüfstand keinen Namen mit abgelaufenem Zertifikat hatte — wieder
`N-68`: grün aus Mangel an Gelegenheit. Der Stand hat jetzt einen.

Dazu ein eigener Stolperstein: die Attrappe für `openssl` steht in einem
`<<'STUB'`-Block, in dem nichts ausgewertet wird. Das übliche
`'"'"'`-Geflecht für ein Apostroph wurde dort **wörtlich** übernommen und
riss die ganze Attrappe syntaktisch auf — woraufhin *jeder* Name als „kein
Zertifikat" galt und der heile Name mit in der Liste stand. Eine kaputte
Attrappe fällt auf, wenn eine Prüfzeile verlangt, dass ein heiler Fall
**nichts** meldet. Ohne diese Zeile wäre der Fehler durchgelaufen.

---

## N-70 — Der Name von n8n stand unter keiner Aufsicht mehr

Im Status des Servers fehlte etwas, was niemandem auffiel, weil nichts rot
wurde — die Liste war nur kürzer:

```
  NAME                       ZEIGT AUF        ZERTIFIKAT
  admin.prolo.me             217.160.0.1 (FREMD) keine Antwort auf 443
  auth.prolo.me              89.58.44.224     80 Tage (Let's Encrypt)
  bordbuch.prolo.me          89.58.44.224     80 Tage (Let's Encrypt)
  …
```

`n8n.prolo.me` kam nicht vor. Nicht, weil es den Namen nicht gäbe — der
Browser erreicht ihn —, sondern weil `hostnamen()` ihn nicht mehr fand:

```bash
grep -ho 'Host(`[^`]*`)' "$STACK"/*/docker-compose.yml
```

Seit `N-61` steht bei einem Fremdwerkzeug **alles von uns** in der
`docker-compose.override.yml` — Netz, Route, Zertifikat. Die
Herstellerdatei bleibt unberührt, und genau sie war die einzige, die hier
gelesen wurde. Mit dem Umbau auf die saubere Trennung ist der Name aus der
Aufsicht gefallen: kein Zertifikatsalter, keine DNS-Prüfung, kein
`prolo dns`.

> Eine Aufsicht, die leiser wird, sieht aus wie eine Aufsicht, die nichts
> zu beanstanden hat. Das ist dieselbe Narbe wie bei
> `grenze-pruefen.sh`, das beim selben Umbau von 61 auf 57 Prüfungen fiel
> und grün blieb.

Die Regel dagegen stand zu dem Zeitpunkt schon in `CLAUDE.md` §16 — „jeder
Prüfer, der nur `docker-compose.yml` liest, sieht bei einem Fremdwerkzeug
die Hälfte". `prolo` selbst hat sie gebrochen. Eine Regel, die nur für die
Prüfskripte gilt, ist halb geschrieben; sie steht jetzt für jede Stelle
da, die Compose-Dateien liest.

### Was jetzt kommt

`hostnamen()` liest beide Dateien und vereinigt sie (`sort -u`, ein Name
in beiden zählt einmal). Auf dem Arbeitsstand sind es damit sieben Namen
statt sechs; `n8n.prolo.me` ist wieder dabei.

Und die Prüfung dazu fragt **beide** Richtungen ab: ein Name aus der
override-Datei muss durchkommen, und einer aus der Herstellerdatei muss es
weiterhin. Ohne die zweite Zeile wäre „lies nur noch die override-Datei"
eine Korrektur gewesen, die dieselbe Lücke nur verschiebt — die Mutation
dazu steht in der Gegenprobe.

### Prüfung

`werkzeuge/prolo-pruefen.sh`: **90 ok**, RC=0 (vorher 87).
`werkzeuge/prolo-gegenprobe.py`: **16 von 16 gefunden** (vorher 14).

---

## N-71 — Genau die auffällige Zeile sprengte die Spalte

In derselben Tabelle, in derselben Ausgabe:

```
  NAME                       ZEIGT AUF        ZERTIFIKAT
  admin.prolo.me             217.160.0.1 (FREMD) keine Antwort auf 443
  auth.prolo.me              89.58.44.224     80 Tage (Let's Encrypt)
```

Die Spalte war `%-16s` breit. Eine IPv4 passt da hinein (15 Zeichen), das
`(FREMD)` dahinter nicht — 19 Zeichen, und die letzte Spalte rutscht nach
rechts. Ausgerechnet in der Zeile, auf die man schaut.

> Eine Spalte wird nach ihrem längsten Wert bemessen, nicht nach ihrem
> häufigsten. Der längste ist hier immer der Problemfall — das ist keine
> Ausnahme, sondern der Zweck der Tabelle (§14a, Punkt 5).

`%-23s`: 15 Zeichen IPv4 plus `" (FREMD)"` sind genau 23.

### Prüfung

`werkzeuge/prolo-pruefen.sh`: **92 ok**, RC=0 (vorher 90).
`werkzeuge/prolo-gegenprobe.py`: **17 von 17 gefunden** (vorher 16).

Die Prüfzeile misst die Stelle, an der die Spalte `ZERTIFIKAT` beginnt —
handgerechnet aus dem Formatstring (`2 + 26 + 1 + 23 + 1 = 53`), einmal in
einer Zeile mit langem und einmal mit kurzem Eintrag. Eine Prüfung, die
nur die beiden Zeilen miteinander vergleicht, hielte auch eine Tabelle für
heil, die als Ganzes verrutscht ist.

---

## N-72 — Die Startseite stand im Quelltext, nicht im Werkzeug

Gefragt wurde: „Wie setze ich jetzt eine Webseite auf prolo.me?"

Die ehrliche Antwort war bis hierher: gar nicht. `prolo.me` zeigte
jedem, der ohne Link vorbeikam, denselben Satz — „Hier liegt nichts offen
herum." Das war richtig gedacht: was hier liegt, gehört niemandem in die
Hände, der keinen Zugangslink hat. Nur ließ es sich nicht ändern, ohne
`seite_start()` in `server.py` anzufassen und das Abbild neu zu bauen.

> Ein Werkzeug, das Seiten ablegt und ausliefert, sollte auch die Seite
> ablegen und ausliefern können, die ganz vorne steht. Dass ausgerechnet
> die einzige öffentliche Adresse fest verdrahtet war, ist keine
> Sicherheitsentscheidung gewesen, sondern eine, die nie jemand getroffen
> hat.

### Was jetzt kommt

In der Verwaltung gibt es die Karte **„Die Startseite"**: eine der
abgelegten Seiten auswählen, Übernehmen. Wer `prolo.me` ohne Link
aufruft, sieht ab dann diese Seite. „keine" wählen stellt das Schild
wieder her — die Seite selbst bleibt liegen.

Vier Dinge, die daran wichtiger sind als die Funktion selbst:

1. **Es wird gesagt, was es bedeutet.** Die Karte trägt eine Warnung,
   und beim Übernehmen fragt das Werkzeug nach: *„Die Seite wird damit für
   JEDEN sichtbar, der die Adresse aufruft — ohne Link und ohne Anmeldung,
   und Suchmaschinen dürfen sie finden."* Wer hier aus Versehen den
   Lebenslauf hinlegt, soll es vorher lesen und nicht hinterher merken.
2. **Der Riegel bleibt derselbe.** Eine Startseite ist fremder Code wie
   jede andere abgelegte Seite und bekommt dieselbe CSP. Die stand vorher
   nur an einer Stelle im Quelltext; sie heißt jetzt `CSP_SEITE` und wird
   von beiden benutzt. Zwei Fassungen wären zwei Gelegenheiten,
   auseinanderzulaufen — und die öffentliche wäre die laschere gewesen.
3. **`robots.txt` sagt die Wahrheit.** Ohne Startseite: `Disallow: /`,
   wie bisher. Mit: `Allow: /$` und darunter weiter `Disallow: /` — genau
   die Wurzel, nichts darunter. Die freigegebenen Seiten unter `/s/` und
   die Links unter `/z/` bleiben draußen.
4. **Die Markierung kann nicht ins Leere zeigen.** Wird die Seite
   gelöscht, verschwindet die Markierung in derselben Transaktion (§12),
   und der Löschdialog sagt vorher, dass es diese Seite ist. Zeigt sie
   trotzdem einmal auf etwas Gelöschtes oder auf eine verschwundene Datei,
   steht dort wieder das Schild — kein 500, denn der Besucher kann daran
   nichts ändern.

### Der Prüfer hat gelogen, und zwar genau so wie angekündigt

Im Browserdurchgang fiel ein echter Fehler auf, den kein Test gefunden
hätte: der Verweis „ansehen" in der neuen Karte bekam die Vorgabe des
Browsers — Dunkelblau. Auf `--surface` im dunklen Thema ist das nicht zu
lesen, und ein Farbwert ohne Token wäre es ohnehin nicht gewesen (§2).
Das Werkzeug hatte bis dahin gar keine Regel für einen Verweis im
Fließtext; jetzt hat es eine, über `--accent-ink`.

Und beim Nachmessen fiel der **Messende** hinein:

```
"ansehen-Link": 1.02,   "Zustandszeile": 1.04,   "Label": 1.04
```

Alles um 1, also unsichtbarer Text — auf einem Bildschirmfoto, auf dem
man ihn deutlich liest. `getComputedStyle().color` gibt bei einem
`oklch()`-Wert **`oklch()` zurück**, und die drei Zahlen daraus als R, G, B
zu lesen ergibt Unsinn. Das ist wörtlich die erste der drei Lügen aus
§14a — aufgeschrieben, gelesen, und trotzdem hineingelaufen.

Der Prüfer rechnet jetzt nicht mehr selbst, sondern lässt den Browser
umrechnen (Leinwand, sRGB), erkennt einen abgelehnten Farbwert an einer
Kennfarbe statt still die vorige zu messen, und sucht zu einer
durchsichtigen Fläche den ersten undurchsichtigen Vorfahren, statt gegen
Schwarz zu messen. Dazu vier Gegenproben mit von Hand bekanntem Ergebnis:

| Probe | erwartet | gemessen |
|---|---|---|
| Schwarz auf Weiß | 21 | 21 |
| dieselbe Farbe auf sich selbst | 1 | 1 |
| `oklch(0 0 0)` auf `oklch(1 0 0)` | 21 | 21 |
| `oklch(0 0 0)` auf `rgb(255,255,255)` | 21 | 21 |

Die dritte Zeile ist die eigentliche: sie beweist, dass der oklch-Weg
trägt. Ohne sie wäre der Prüfer wieder nur grün gewesen.

### Prüfung

**Im Browser geladen**, Chromium, beide Themen, 360 / 768 / 1920 px:
kein seitliches Scrollen (`quer = 0` in allen sechs Läufen), kein
Überlauf aus einer Karte, keine Fehler auf der Konsole. Bildschirmfotos
liegen im Kratzblock.

Kontrast nach der Korrektur, gemessen: „ansehen" **10,49** (dunkel) und
**10,24** (hell), Zustandszeile 6,04 / 5,52, Warnung 7,95 / 6,38,
Auswahlfeld 14,91 / 18,14 — alles über 4,5:1.

Touchziele: das neue Auswahlfeld und „Übernehmen" sind 44 px. Fünf
**bestehende** Elemente sind es nicht (36 px bzw. 37 px) — eigener Befund,
nicht still nebenbei.

| | |
|---|---|
| `www/tests/alle.sh` | **40 Tests**, RC=0 (vorher 27) |
| `www/tests/gegenprobe.py` (neu) | **13 von 13 gefunden** |

Die Gegenprobe gab es für dieses Werkzeug noch nicht. Zwei Mutationen
entwischten im ersten Lauf — *„eine gelöschte Seite bleibt öffentlich
stehen"* und *„das Löschen lässt die Markierung stehen"* —, und zwar
**beide aus demselben Grund**: gegen diesen Fall sichern zwei Stellen
gleichzeitig (der Filter `geloescht = 0` und das `DELETE` beim Löschen),
und solange eine steht, merkt der Test von der anderen nichts.

> Zwei Riegel und eine Prüfzeile ergeben einen blinden Fleck. Jeder
> Riegel braucht einen Test, der ihn **allein** trägt.

Dafür schaut ein Test jetzt in die Datenbank statt durch die
Schnittstelle (ist die Zeile wirklich weg, nicht nur wirkungslos?), und
ein zweiter stellt von Hand einen Zustand her, den die Schnittstelle gar
nicht erzeugen kann (Markierung auf eine gelöschte Seite). Danach: 13 von
13.

---

## N-73 — Vier Klickflächen, die für einen Daumen zu klein waren

Beim Browserdurchgang zu `N-72` meldete die Messung fünf Elemente unter
44 Pixel — und keines davon war neu:

```
A "PProloFreigabe" 37
BUTTON "Seite löschen" 36
BUTTON "Seite löschen" 36
BUTTON "Zurückziehen" 36
BUTTON "Passwort setzen" 36
```

`.knopf` ist 44 hoch, wie §9 es verlangt. Drei Stellen in der Verwaltung
haben das mit einem `min-height:36px` im Stil-Attribut überschrieben,
damit die Tabellenzeilen kompakt bleiben. Und die Marke oben links ist ein
Verweis auf die Startseite, also ein Bedienelement — ihre Höhe ergab sich
aus der 30-Pixel-Kachel plus Text: 37.

> „Nicht verhandelbar" (§9) heißt: auch dann nicht, wenn es enger besser
> aussieht. Diese Werkzeuge werden am Handy benutzt, mit Daumen und teils
> mit Handschuhen — drei Knöpfe, bei denen man danebentrifft, sind teurer
> als eine Tabelle, die zwölf Pixel höher ist.

Die Überschreiber sind weg; die schmale Polsterung (`padding:0 10px`)
bleibt, eng ist erlaubt, flach nicht. Die Marke bekommt `min-height:44px`,
die Kachel bleibt bei 30 (§5).

### Prüfung

Gemessen im Browser, beide Themen, 360 / 768 / 1920 px: **kein Element
unter 44 px mehr**, in allen sechs Läufen. Vorher fünf.

**Und der Prüfer wurde gegengeprobt** (§14a). „Nichts gefunden" heißt
nichts, solange nicht gezeigt ist, dass der Prüfer etwas finden *kann*:
in einer Kopie im Kratzblock wurde ein `min-height:36px` wieder
eingesetzt und ein zweiter Dienst daneben gestartet.

```
8112 ["Seite löschen=36"]     <- die Kopie mit dem Fehler
8111 []                       <- der Arbeitsstand
```

`www/tests/alle.sh`: 40 Tests, RC=0.

Die Fassung bleibt `1.1.0`: zwischen den beiden Befunden wurde nichts
veröffentlicht, also gibt es kein Abbild, das die alte Nummer trüge. Im
CHANGELOG steht es unter derselben Fassung.

---

## N-74 — Die erste Tür stand an der falschen Wand

Die Verwaltung von `www` hat noch nie funktioniert. Wer sie öffnete, sah
die Seite — und darunter ein rotes Band:

> Die Liste kam nicht — bist du noch angemeldet?

Die Anmeldung war es nicht. Dieses Werkzeug hat **zwei Router** auf
demselben Hostnamen (§19), und der geschützte trifft genau einen Pfad:

```
(Host(`prolo.me`) || Host(`www.prolo.me`)) && PathPrefix(`/verwaltung`)
```

Die Aufrufe der Verwaltung lagen aber unter `/api/` — `/api/verwaltung`,
`/api/hochladen`, `/api/freigabe`, `/api/zustand`, `/api/passwort`,
`/api/loeschen`, seit `N-72` auch `/api/startseite`. **Kein einziger**
davon wird von `PathPrefix(`/verwaltung`)` getroffen. Sie liefen alle über
den **öffentlichen** Router, der kein `authentik@file` hat — und Traefik
setzt die Identitätskopfzeilen nur dort, wo die Middleware läuft.

Also kam jeder dieser Aufrufe ohne `X-Authentik-Username` an, und
`verwalter()` hat ihn mit 401 abgewiesen. Vollkommen richtig.

> Offen gestanden hat nichts. Die zweite Tür — die Prüfung im Werkzeug
> selbst (§17, `N-44`) — hat jeden einzelnen Aufruf gehalten, obwohl die
> erste gar nicht im Weg stand. Das ist der Tag, an dem sich die Regel
> „eine Kopfzeile ist nur so viel wert wie die Gewissheit, dass sie von
> Traefik kommt" bezahlt gemacht hat: derselbe Fehler ohne sie wäre eine
> offene Verwaltung im Netz gewesen.

Und die Meldung führte in die Irre: „bist du noch angemeldet?" war eine
Vermutung, und bei 401 war sie falsch — angemeldet war man, der Weg war
der falsche. Das ist `N-75`.

### Was jetzt kommt

Alles, was Verwalterrechte braucht, liegt unter **einem** Präfix:

| vorher | jetzt |
|---|---|
| `/api/verwaltung` | `/verwaltung/api/daten` |
| `/api/hochladen` | `/verwaltung/api/hochladen` |
| `/api/freigabe` | `/verwaltung/api/freigabe` |
| `/api/zustand` | `/verwaltung/api/zustand` |
| `/api/passwort` | `/verwaltung/api/passwort` |
| `/api/loeschen` | `/verwaltung/api/loeschen` |
| `/api/startseite` | `/verwaltung/api/startseite` |

Die Router-Regel bleibt unverändert — sie stimmt jetzt von selbst.

**Eine Ausnahmeliste wäre der nächste Fehler gewesen.** `PathPrefix(`/api/`)`
dazuzunehmen hätte `/api/version` mitgeschützt, und das ist die
`PRUEF_URL`-Nachbarschaft, die absichtlich ohne Anmeldung erreichbar sein
muss (§17). Dann stünde dort `/api/ ausser /api/version` — eine Regel mit
einer Ausnahme, und bei der nächsten Erweiterung zwei. Ein Präfix, der
**geschützt** bedeutet, braucht keine: was öffentlich bleiben muss, liegt
nicht darunter.

### Die Prüfzeile, die den Rückfall unmöglich macht

Der Fehler war nicht, dass jemand falsch gedacht hat — es war, dass
**zwei Dateien dasselbe wissen mussten** und niemand sie verglichen hat.
Also vergleicht sie jetzt ein Test:

- alle Wege aus `server.py` einsammeln; jeder, der nicht in der
  ausdrücklichen Liste der öffentlichen steht, **muss** unter
  `/verwaltung` liegen;
- die Compose-Datei muss genau diesen Präfix treffen, mit
  `authentik@file` und der höheren `priority`;
- und beides wird zusätzlich **gemessen**: jeder Weg der Verwaltung
  antwortet ohne Kopfzeile mit 401, jeder öffentliche mit 200.

Dazu ein Prüferbeweis in der Prüfzeile selbst: findet die Suche weniger
als acht Wege, ist sie kaputt und nicht der Code heil.

### Prüfung

| | |
|---|---|
| `www/tests/alle.sh` | **44 Tests**, RC=0 (vorher 40) |
| `www/tests/gegenprobe.py` | **16 von 16 gefunden** (vorher 13) |

Die Gegenprobe mutiert ab jetzt **jede** Datei des Werkzeugs, nicht nur
`server.py` — die Router-Regel steht in der Compose-Datei, und eine Probe,
die dort nicht hinkommt, kann die Hälfte dieses Befunds nicht prüfen.

Gemessen am laufenden Dienst, mit und ohne Kopfzeilen:

```
=== Mit Kopfzeilen ===            === OHNE Kopfzeilen ===
/verwaltung            200        /verwaltung            401
/verwaltung/api/daten  200        /verwaltung/api/daten  401

=== Oeffentlich bleibt oeffentlich ===   === Die alten Wege ===
/            200   /api/version  200     /api/verwaltung  404
/gesundheit  200   /robots.txt   200     /api/startseite  404
```

**Im Browser geladen**: `artur · Fassung 1.1.0` oben rechts, kein
Fehlerband, die Liste gefüllt, die Auswahl der Startseite gefüllt, keine
Konsolenfehler. Vorher stand dort das rote Band und sonst nichts.

---

## N-75 — Die Meldung riet, und lag daneben

Unter der Verwaltung stand, zwei Tage lang, genau dieser Satz:

> Die Liste kam nicht — bist du noch angemeldet?

Angemeldet war man. Der Fehler war `N-74`: der Aufruf lief über den
falschen Router. Die Meldung hat also nicht nur nichts gesagt — sie hat in
die **falsche** Richtung gezeigt, und zwar mit einer Frage, die man
gutgläubig mit „ja, bin ich" beantwortet und dann ratlos dasteht.

Dabei lag die Antwort im selben Codeblock:

```js
const a = await fetch('/api/verwaltung');
if(!a.ok){ melden('Die Liste kam nicht — bist du noch angemeldet?', 'fehler');
           return; }
```

`a.status` war da. Der JSON-Körper mit dem Satz des Werkzeugs war da.
Beides wurde weggeworfen und durch eine Vermutung ersetzt.

> Das ist `N-64` im Browser. Wer eine Ursache in der Hand hat und
> stattdessen rät, macht aus einer Diagnose eine Suche — und die beginnt
> dann an der Stelle, auf die geraten wurde.

### Was jetzt kommt

Gemessen im Browser, mit abgefangener Antwort:

| Antwort | Meldung |
|---|---|
| `503` + Grund | Die Liste kam nicht (HTTP 503): Die Datenbank ist gerade nicht erreichbar. |
| `302`, kein JSON | Die Liste kam nicht (HTTP 302). Der Server hat keine Erklärung mitgeschickt — dann kam die Antwort nicht von diesem Werkzeug, sondern vom Zugang davor. |
| `401` | Die Liste kam nicht (HTTP 401): Nicht angemeldet. … Melde dich neu an; bleibt es dabei, sieh im Protokoll nach: `sudo prolo protokoll www` |

Die mittlere Zeile ist die wichtigste: **kommt kein JSON zurück, hat nicht
das Werkzeug geantwortet.** Genau das war bei `N-74` der Fall, und genau
das hätte den Befund in zwei Minuten statt zwei Tagen gestellt. Die
Vermutung „bist du angemeldet" bleibt erhalten — aber nur bei 401/403, wo
sie hingehört, und zusammen mit dem Befund, nicht an seiner Stelle.

### Prüfung

`www/tests/alle.sh`: **45 Tests**, RC=0.
`www/tests/gegenprobe.py`: **17 von 17 gefunden**.

Und auch hier hat der erste Messlauf gelogen: die drei Fälle zeigten noch
den alten Satz, weil der Probedienst seit **vor** der Änderung lief. Eine
Codeänderung ist kein Beweis, solange der Prozess sie nicht geladen hat
(§ TEIL 0). Nach dem Neustart standen die Sätze oben.

---

## N-76 — Ein Werkzeug konnte laufen und ungesichert sein, und die Sicherung meldete Erfolg

Im Sicherungsprotokoll eines ganz normalen Laufs stand das hier:

```
Sichere bitwarden
  Hinweis: /opt/stack/bitwarden/.env gibt es nicht - uebersprungen.
...
Verschluesselt: /opt/backups/2026-09-21.tar.gz.age
Backup fertig: 2026-09-21
```

„Backup fertig." Von bitwarden war **nichts** darin. Kein Tresor, kein
Schlüssel, keine Datei — der Container lief und legte Daten ab, und die
Sicherung ging an ihm vorbei, ohne zu stolpern.

Der Grund ist banal und deshalb gefährlich: `prolo neu` schreibt die
`sicherung.conf`, **bevor** es die Datei des Herstellers gibt. `VOLUMES`
bleibt leer, weil es zu dem Zeitpunkt nichts einzutragen gibt. Und danach
hat nie jemand nachgesehen.

> §25 sagt: „Eine Sicherung, deren Scheitern niemand merkt, ist keine
> Sicherung." Dieser Fall ist die schlimmere Schwester davon — eine
> Sicherung, die **nicht scheitert**, weil sie gar nicht weiß, dass sie
> etwas übersehen hat.

### Was der Prüfer beim ersten Lauf sofort fand

Nicht nur bitwarden. Auf dem gepflegten Arbeitsstand:

```
authentik|bind|custom-templates|FEHLT
traefik|bind|traefik.yml|FEHLT
traefik|bind|dynamic|FEHLT
traefik|bind|acme.json|FEHLT
traefik|bind|log|FEHLT
```

**`traefik` hatte als einziges Werkzeug gar keine `sicherung.conf`.**
`backup.sh` geht die `sicherung.conf`-Dateien durch — ohne eine wurde
traefik schlicht übersprungen. Was von ihm gesichert wurde, stand als
**fester Block mit Toolnamen** im zentralen Skript, und der deckte genau
eine Datei ab: `acme.json`.

Nicht gesichert war damit `dynamic/` — und darin liegt `einlass.yml` mit
der Marke der Vertrauensgrenze (`N-44`). Die Datei ist bewusst nicht im
Git (§21). Nach einem Verlust gibt es sie nur neu, und dann muss sie in
jedes Werkzeug nachgezogen werden, wobei alle Sitzungen ablaufen.

### Was jetzt kommt

**`werkzeuge/volumes.py`** misst, was ein Werkzeug wirklich ablegt:

```
$ python3 werkzeuge/volumes.py /opt/stack
admin|volume|admin_admin_daten|gesichert
traefik|bind|acme.json|gesichert
traefik|bind|log|erklaert|Betriebsprotokoll - faengt nach einer Wiederherstellung neu an
bitwarden|volume|bitwarden_bw-data|FEHLT
```

Drei Entscheidungen darin:

1. **Gemessen wird die zusammengesetzte Konfiguration**, nicht eine
   Datei. Bei einem Fremdwerkzeug steht die Hälfte im Overlay (§16), und
   ein Prüfer, der nur eine der beiden liest, sieht die Hälfte — dieselbe
   Narbe wie `N-70`.
2. **Der Laufzeitname kommt von `docker compose config`**, nicht aus einer
   Rechnung. Er lautet `<ordner>_<schlüssel>` und nicht `<schlüssel>` —
   genau daran vertippt man sich beim Eintragen von Hand. Die Meldung
   schreibt ihn aus. (Und `config` braucht dafür keinen laufenden Docker.)
3. **Bind-Mounts zählen mit.** Die sieht `docker volume ls` gar nicht, und
   bei authentik und traefik lag genau dort das Unbewachte.

**Die Sicherung bricht jetzt ab**, wenn etwas fehlt — kein `.letzter-erfolg`,
Rückgabewert 1, also stoppt auch `prolo aktualisieren`, bevor es etwas
anfasst. Das ist die richtige Reihenfolge: nichts aktualisieren, dessen
Daten nicht gesichert sind. Und die Meldung nennt die Zeile, nicht die
Aufgabe (§7, `N-67`):

```
ACHTUNG: hier entstehen Daten, die NICHT gesichert werden.

  bitwarden      volume  bitwarden_bw-data

  Das ist keine Warnung, sondern eine Luecke: was hier nicht steht,
  ist nach einem Verlust weg. Je Zeile EINE der beiden Zeilen in
  die sicherung.conf des Werkzeugs:

    VOLUMES="... <name>"          # es wird gesichert
    VOLUMES_OHNE="<name>|<warum>" # es braucht keine Sicherung
```

**`VOLUMES_OHNE` ist der ehrliche Ausweg.** Nicht jedes Volume braucht
eine Sicherung — ein Zwischenspeicher nicht, ein Protokoll nicht. Aber
das ist eine **Entscheidung**, und sie wird hingeschrieben, wie
`prolo.ports=` und `prolo.netz.geteilt=` auch. Stillschweigen zählt nicht.

**`prolo start` warnt, blockiert aber nicht.** Starten muss man ein
Werkzeug auch, bevor die Sicherung steht — sonst wird aus „einfach mal
ausprobieren" eine Hürde. Der Hinweis steht an der Stelle, an der man noch
etwas dagegen tun kann; das Abbrechen macht die Sicherung selbst.

**`prolo neu`** nennt den Schritt jetzt in seiner Liste — nach dem
Einsetzen der Herstellerdatei, weil es vorher nichts zu messen gibt, und
vor dem Starten, weil danach Daten entstehen.

Der feste `acme.json`-Block in `backup.sh` ist weg: traefik hat jetzt eine
eigene `sicherung.conf`. Ein Toolname im zentralen Skript war genau das,
was der Grundsatz verbietet.

### Prüfung

| | |
|---|---|
| `werkzeuge/sicherung-pruefen.sh` (neu) | **12 ok**, RC=0 |
| `werkzeuge/sicherung-gegenprobe.py` (neu) | **8 von 8 gefunden** |
| prolo / netze / grenze / neu | 92 / 42 / 62 / 101, alle RC=0 |
| einrichten / regeln / dockerfile | 12 / 6 / 4, alle RC=0 |
| `python3 werkzeuge/volumes.py .` | RC=**0** — vorher 5 Lücken |

Zwei Dinge sind beim Bauen schiefgegangen, beide durch Hinsehen gefunden:

**Der Prüfer gab Falschalarm.** Er meldete `authentik/custom-templates`
als Lücke, obwohl der Eintrag längst dastand — er zog das führende `?`
(„darf fehlen") nur bei `DATEIEN` ab, nicht bei `ORDNER`. Ein Prüfer, der
Falschalarm gibt, wird nach dem zweiten Mal weggeklickt und ist dann
schlimmer als keiner.

**Und eine Mutation entwischte**, zum wiederholten Mal aus demselben
Grund wie in `N-68` und `N-72`: *„liest nur die Herstellerdatei"* änderte
nichts, weil im Prüfstand **jedes** Volume in der Herstellerdatei stand.
Der Fall „ein Volume kommt erst im Overlay dazu" kam gar nicht vor. Er
kommt jetzt vor.

> Zum dritten Mal dieselbe Lehre: eine Prüfzeile über einen Fall, den der
> Prüfstand nicht herstellt, ist grün aus Mangel an Gelegenheit. Beim
> Schreiben einer Prüfzeile gehört die Frage dazu: **kommt dieser Fall im
> Stand überhaupt vor?**

---

## N-77 — Es gab keinen Weg zurück

§23 steht seit Anfang an so da:

> **Die Wiederherstellung wird geübt**, solange nur Testdaten drin sind.
> Das ist der Schritt, den fast alle überspringen, und der einzige, der
> zählt.

Übersprungen hatten wir ihn auch. Es gab schlicht **keinen Befehl**.
`prolo zurueckholen` holt ein Werkzeug aus dem Archiv zurück, nachdem man
es mit `prolo entfernen` weggeräumt hat — mit der täglichen Sicherung unter
`/opt/backups` hat das nichts zu tun. Wer von dort etwas gebraucht hätte,
hätte sich die Schritte selbst zusammensuchen müssen: entschlüsseln,
auspacken, den richtigen Ordner finden, Volumes per `docker run … tar`
füllen, Datenbanken einspielen — und dabei jeden der Stolpersteine selbst
finden, die weiter unten stehen.

> Eine Sicherung, die nie zurückgespielt wurde, ist eine Vermutung. Und
> eine Vermutung merkt man sich als Gewissheit.

### `prolo wiederherstellen`

```
prolo wiederherstellen --probe                 üben, ohne etwas anzufassen
prolo wiederherstellen [--stand JJJJ-MM-TT] [--schluessel <datei>] [tool …]
```

**`--probe` ist der eigentliche Punkt.** Sie entschlüsselt, packt aus,
vergleicht den Inhalt gegen die `sicherung.conf` jedes Werkzeugs und liest
**jedes einzelne Stück wirklich**: `tar tzf` für Archive, `gzip -t` für
Dumps, und für jede SQLite-Datei ein `PRAGMA integrity_check`. Sie fasst
nichts an und lässt sich darum jeden Tag laufen.

Dass eine Datei *da* ist, ist eben noch keine Sicherung. Ob
`sqlite3.backup()` beim Sichern wirklich einen geschlossenen Stand
erwischt hat, sieht man erst, wenn jemand nachsieht.

Der geheime `age`-Schlüssel liegt nach §23 auf dem **Arbeitsrechner**,
nicht auf dem Server. Darum nimmt der Befehl beides: ein verschlüsseltes
Archiv samt `--schluessel` (die Datei wird gelesen, nie gespeichert), oder
ein bereits entschlüsseltes `.tar.gz`. Fehlt der Schlüssel, sagt die
Meldung beide Wege — samt dem fertigen `age -d`-Aufruf für den anderen
Rechner.

### Drei Dinge, die still zerstört hätten

**1. Das fremde Journal.** Erwischt die Sicherung ein Volume, während
geschrieben wird, liegt neben der Datenbank ein `-wal` im Archiv. Beim
Einspielen kommt es zurück — und obendrauf kommt die *heile* Kopie, die
`sqlite3.backup()` gezogen hat. Beim nächsten Öffnen spielt SQLite dann
ein Journal auf eine Datenbank, zu der es nicht gehört. Die Datei sieht
heil aus und ist es nicht. `-wal` und `-shm` werden darum gezielt
entfernt.

**2. Die Reihenfolge.** Das Volume-Archiv enthält die Datenbank auch — nur
eben möglicherweise zerrissen. Die heile Einzelkopie muss also **zuletzt**
darüber, nicht davor.

**3. Ersetzen, nicht ergänzen.** Ein Volume wird leergeräumt, bevor das
Archiv hineingeht. Sonst überlebt genau das, was man loswerden wollte.

Und für §15: der jetzige Stand wandert **vorher** nach
`/opt/backups/.vor-wiederherstellung-<zeitstempel>`. Der Ordner trägt die
Uhrzeit und wird nie überschrieben — auch ein zweiter, ebenfalls
schiefgegangener Lauf nimmt einem den ersten Rückweg nicht weg. Ohne
Terminal und ohne `--ja` passiert gar nichts; von Hand muss man die Anzahl
der betroffenen Werkzeuge eintippen.

### Prüfung

| | |
|---|---|
| `werkzeuge/wiederherstellen-pruefen.sh` (neu) | **31 ok**, RC=0 |
| `werkzeuge/wiederherstellen-gegenprobe.py` (neu) | **12 von 12 gefunden** |
| prolo / sicherung / netze / grenze / neu | 92 / 12 / 42 / 62 / 101, RC=0 |
| `www/tests/alle.sh` | 45 Tests, RC=0 |

Der Kern des Prüfers ist kein Einzeltest, sondern ein **Rundlauf**:
sichern, die Daten wirklich vernichten, zurückspielen, und danach die
**Inhalte** vergleichen. „Der Befehl lief durch" ist kein Beweis. Docker
ist dabei gefälscht, bewegt aber echte Archive — eine Attrappe, die nur
`exit 0` sagt, besteht jeden Rundlauf, ohne ein Byte anzufassen. Und
`docker compose config` wird gar nicht gefälscht, sondern durchgereicht:
es braucht keinen Daemon, und eine Attrappe, die auch das erfindet, prüft
am Ende nur sich selbst.

### Vier Lügen beim Bauen, alle durch Hinsehen gefunden

**Der erste Lauf meldete „vollständig und lesbar" über einen leeren
Plan.** `"${TOOLS[@]-}"` ergibt bei einem leeren Feld *ein leeres
Element* — der Befehl suchte nach einem Werkzeug namens `""`, fand nichts,
und nannte das Erfolg. Dieselbe Lüge wie „Backup fertig" in `N-76`, nur
von der anderen Seite. Ein leerer Plan ist jetzt ausdrücklich ein Fehler.

**Der Auspackordner wurde nie gelöscht.** `AUSPACK` wurde in einer
Subshell gesetzt (`$( )`), der `trap` im Elternprozess sah eine leere
Variable. Darin liegen `.env`-Dateien und Datenbanken im Klartext (§21).

**Der Rundlauf bewies den SQLite-Schritt nicht.** Die Datenbank kam über
das *Volume-Archiv* zurück und sah damit richtig aus — der eigentliche
Schritt war nie geprüft. Jetzt steht im Volume absichtlich eine **alte**
Datenbank und daneben die heile: kommt `VOLUME-DB-ALT` heraus, lief der
Schritt nicht.

**Und die schönste:** die Prüfzeile *„das fremde `-wal` ist entfernt"* war
immer grün — weil die Zeile **darüber** die Datenbank öffnete. SQLite
spielt beim Öffnen ein vorhandenes Journal ein und löscht es danach. Der
Test hat also genau den Schaden weggeräumt, den er nachweisen sollte.

> Ein Test, der seinen eigenen Beweis anfasst, misst sich selbst. Die
> Reihenfolge der Prüfzeilen ist Teil der Prüfung.

---

## N-78 — Die Meldung nannte die Zeile, die nicht passt

`N-76` hatte gerade erst dafür gesorgt, dass die Sicherung ihre Lücken
benennt. Beim ersten echten Einsatz auf dem Server sah das so aus:

```
ACHTUNG: hier entstehen Daten, die NICHT gesichert werden.

  bitwarden      bind    vw-data

  … Je Zeile EINE der beiden Zeilen in die sicherung.conf des Werkzeugs:

    VOLUMES="... <name>"          # es wird gesichert
    VOLUMES_OHNE="<name>|<warum>" # es braucht keine Sicherung
```

Die Diagnose stimmte. Der Rat nicht. `vw-data` ist ein **Bind-Mount** —
Vaultwarden bindet `./vw-data` aus dem Werkzeugordner ein —, und in
`VOLUMES` gehören ausschließlich **benannte Docker-Volumes**. Wer der
Meldung folgt, trägt es dort ein, und beim nächsten Lauf steht dieselbe
Beanstandung wieder da: `VOLUMES` schickt `backup.sh` in ein
`docker run -v vw-data:/daten`, und ein Volume dieses Namens gibt es nicht.

Die Spalte daneben sagte es sogar — `bind` stand da. Die Meldung hat ihre
eigene Ausgabe nicht gelesen.

> Eine Meldung, die einen Weg nennt, muss den Weg nennen, der zum Ziel
> führt (§7). Ein Rat, der sich beim Befolgen als falsch herausstellt, ist
> teurer als gar keiner: beim ersten Mal sucht man den Fehler bei sich.

### Was jetzt kommt

Die Zeile hängt an der Art, und `werkzeuge/volumes.py` unterscheidet sie
jetzt auch: ein Bind-Mount auf einen **Ordner** gehört in `ORDNER`, auf
eine **Datei** in `DATEIEN`, ein benanntes Volume in `VOLUMES`.

```
  bitwarden/vw-data  (Ordner im Werkzeugordner)
      ORDNER="... vw-data"
      oder  VOLUMES_OHNE="vw-data|<warum>"

  n8n/n8n_n8n_data  (benanntes Docker-Volume)
      VOLUMES="... n8n_n8n_data"
      oder  VOLUMES_OHNE="n8n_n8n_data|<warum>"

  traefik/acme.json  (Datei im Werkzeugordner)
      DATEIEN="... acme.json"
      oder  VOLUMES_OHNE="acme.json|<warum>"
```

Gibt es den Pfad noch nicht, gilt er als Ordner — das ist, was Docker bei
einem Bind-Mount ins Leere anlegt.

### Prüfung

| | |
|---|---|
| `werkzeuge/prolo-pruefen.sh` | **96 ok**, RC=0 (vorher 92) |
| `werkzeuge/prolo-gegenprobe.py` | **18 von 18** (vorher 17) |
| `werkzeuge/sicherung-pruefen.sh` | **14 ok**, RC=0 (vorher 12) |
| `werkzeuge/sicherung-gegenprobe.py` | **9 von 9** (vorher 8) |
| wiederherstellen / netze / grenze / neu | 31 / 42 / 62 / 101, RC=0 |

Geprüft wird nicht der Text, sondern die **Wirkung**: `prolo start` läuft
gegen ein Werkzeug mit einem ungesicherten Bind-Ordner, und die Ausgabe
muss `ORDNER="... vw-data"` enthalten und `VOLUMES="... vw-data"` **nicht**.
Dazu der Prüferbeweis: ist es eingetragen, schweigt der Hinweis — sonst
wäre eine Zeile grün, die immer meckert.

Dafür reicht der bisherige Docker-Ersatz in `prolo-pruefen.sh` nicht: er
beantwortete `compose config` mit nichts, also sah `volumes.py` gar keine
Bind-Mounts. `compose config` braucht keinen Daemon und wird darum
durchgereicht statt erfunden — wie im Prüfer für die Wiederherstellung.

---

## N-79 — Die Bremse war am Wiki bemessen, und n8n blieb schwarz

Gemeldet vom Betreiber, nach einer Woche Benutzung:

> egal auf welche seite ich gehe n8n Bitwarden auth ich immer einmal die
> seite neu laden muss. Irgenwas wird geladen aber die Seite ist einfach
> schwart oben steht z.b. n8n mit dem Icon aber erst, wenn ich neu lade
> kommt der inhalt. Daurrch funktionier z.B. n8n nicht richtig.

Die Beschreibung enthielt die Diagnose schon: **Titel und Symbol waren
da.** Das HTML-Dokument ist also angekommen; was fehlte, war das, was die
Seite danach nachlädt. Und es traf genau die drei Werkzeuge, die ihre
Oberfläche erst im Browser zusammenbauen — n8n, Vaultwarden und die
Anmeldeoberfläche von Authentik —, und keines der eigenen, die fertige
Seiten ausliefern.

In unserer Schicht gibt es genau zwei Dinge, die sich anders verhalten,
je nachdem wie **viele** Anfragen gleichzeitig ankommen: die Ratenbremse
und die Grenze für gleichzeitige Anfragen, beide aus `N-46`. Und der
zweite Aufruf ist genau der, bei dem kaum noch Anfragen ankommen, weil
alles im Browserspeicher liegt.

### Gemessen, nicht vermutet

Ein Nachbau der beiden Middlewares (Token-Eimer `average`/`burst`, Zähler
für gleichzeitige Anfragen) vor einer Seite, die ihre Oberfläche aus `n`
Teilen zusammensetzt, geladen mit einem echten Chromium — erst frisch,
dann nach vier Sekunden noch einmal, genau der Handgriff aus der Meldung:

| Teile | abgewiesen | erster Aufruf | nach dem Neuladen |
|---:|---:|---|---|
| 200 | 0 | Oberfläche nach 1,6 s | da |
| 300 | 28 | **schwarz** | da (0,3 s) |
| 400 | 97 | **schwarz** | da (0,8 s) |
| 600 | 219 | **schwarz** | da (1,7 s) |

`average: 50, burst: 150, amount: 40` — der Stand von `N-46`.

Zwei Zahlen aus demselben Lauf erklären den Rest. Ein einzelner Browser
feuert in der Spitze **134 Anfragen in einer Sekunde**; die Bremse ließ
50 zu. Und es braucht keinen Sturm: mit der Grenze für gleichzeitige
Anfragen allein (Ratenbremse aus, `amount: 2`) wurden von 300 Anfragen
**vier** abgewiesen — die Seite blieb trotzdem schwarz. Fehlt ein Teil,
wird die Oberfläche nicht gebaut.

> Die Werte waren am Wiki bemessen: einer Seite, die fertig vom Server
> kommt und rund 15 Anfragen braucht. Gemessen wurde damals, was es schon
> gab — und was es noch nicht gab, fiel durch. Dieselbe Lehre wie `N-68`,
> `N-72`, `N-76` und `N-77`, diesmal nicht an einer Prüfzeile, sondern an
> einer Einstellung.

### Was jetzt kommt

`burst: 700` statt 150, `amount: 200` statt 40 — und `average` bleibt bei
**50**. Das ist der Kern: `burst` ist ein **einmaliger** Vorrat für einen
Seitenaufbau, `average` die **Dauerbremse**. Wer in Schleife anklopft,
braucht den Vorrat auf und hängt danach bei genau denselben 50 Anfragen je
Sekunde wie vorher. Die Bremse gegen ein Skript ist unverändert; nur der
erste Schwung ist groß genug für einen Browser.

Mit `burst: 700` kamen dieselben vier Seiten ohne **eine einzige**
Abweisung durch — Oberfläche nach 1,7 / 2,4 / 3,2 / 4,9 Sekunden.

Dazu steht `sourceCriterion` jetzt ausdrücklich an beiden Middlewares.
Dass „je Quelladresse" gemessen wird, stand vorher nur im Kommentar. Eine
Vorgabe, auf die man sich verlässt, ohne sie hinzuschreiben, ist eine
Annahme — dieselbe Regel wie bei `traefik.docker.network` seit `N-45`.

### Der Prüfer hat gelogen, bevor er half

Beim ersten Durchgang meldete er bei 400 Teilen „schwarz", obwohl **keine
einzige** Anfrage abgewiesen worden war: er wartete 2,5 Sekunden und die
Seite war noch nicht fertig. Eine feste Wartezeit misst die Geschwindigkeit
des Rechners, nicht die Wirkung der Bremse. Gewartet wird jetzt auf die
Oberfläche.

Und der Prüfer wurde gegengeprobt (§14a): mit einem Eimer von **1** Token
meldet er schwarz, mit **5000** meldet er die Oberfläche. Ohne diesen
Beweis heißt „nichts gefunden" nichts.

### Was nicht gemessen werden konnte

Traefik spricht mit einem Browser HTTP/2, der Nachbau nur HTTP/1.1. Über
HTTP/1.1 öffnet ein Browser sechs Verbindungen — mehr als sechs Anfragen
lagen im Nachbau also nie gleichzeitig an, und `amount: 40` konnte dort
gar nicht zuschlagen. Über HTTP/2 liegen sie auf **einer** Verbindung und
gehen zu vielen gleichzeitig hinaus. Dass eine zu enge Grenze genau dieses
Bild erzeugt, ist oben gemessen (`amount: 2`); **wie viele** es über
HTTP/2 tatsächlich sind, ist es nicht. Darum ist `amount: 200` mit
Abstand gewählt und nicht auf die Kante.

Was auf dem Server wirklich abgewiesen wurde, steht im Zugriffsprotokoll
von Traefik — und das konnte bisher niemand lesen. Darum `N-80`.

### Prüfung

| | |
|---|---|
| `werkzeuge/grenze-pruefen.sh` | **66 ok**, RC=0 (vorher 62) |
| `werkzeuge/grenze-gegenprobe.py` | **12 von 12** (neu — der Prüfer hatte keine) |
| netze / regeln / dockerfile | 42 / 6 / 4, RC=0 |

Die Gegenprobe arbeitet auf einer Kopie der **versionierten** Dateien
(`git ls-files`) in einem Wegwerfordner — so kann weder eine `.env` noch
eine Datenbank hineingeraten (§21), und der Rückweg ist nie die eigene
Arbeit (`N-34`, `N-60`). Sie verlangt nicht, dass *irgendeine* Prüfzeile
rot wird, sondern die **richtige**: sonst deckt eine fremde Zeile die
Lücke zu.

---

## N-80 — Die Antwort stand seit Tagen im Protokoll, und niemand kam heran

`N-79` ließ sich nur deshalb messen, weil ein Nachbau der beiden
Middlewares hier im Kleinen gebaut werden konnte. Auf dem Server selbst
hätte dieselbe Frage — *wurde hier etwas abgewiesen, und was?* — in einer
Minute beantwortet werden können: Traefik schreibt seit `B-26` jede
Anfrage samt Statuscode nach `traefik/log/zugriff.log`.

Nur kam niemand heran. Es gab keinen Befehl dafür, `prolo status` erwähnt
die Datei nicht, und 14.000 JSON-Zeilen liest man nicht von Hand. Die
Diagnose lag die ganze Zeit auf der Platte.

> Dieselbe Lehre wie `N-64` und `N-69`: was das Werkzeug **in der Hand
> hatte**, darf es nicht verschweigen. Hier war es nicht einmal
> verschwiegen — es war nur nicht abholbar.

### Was jetzt kommt

```
sudo prolo abweisungen [--stunden N]
```

Liest `zugriff.log` samt der gedrehten Fassungen daneben (`.1`, `.gz`) und
zeigt je Name, wie viele Anfragen ankamen, wie viele mit **429** abgewiesen
wurden, wie viele mit **5xx** scheiterten und über wie viele Quelladressen
das lief — dazu die Pfade, die es am häufigsten traf.

Nach §7: der Satz mit dem **weil** steht je Name, die Erklärung dahinter
genau **einmal** — sie nennt die Datei, in der die beiden Werte stehen,
die Werte selbst, und den Befehl, der eine Änderung wirksam macht
(`N-64`, `N-67`). Wurde nichts abgewiesen, sagt es das und zieht die
Folgerung mit: dann liegt es *nicht* an der Bremse am Eingang.

### Was dabei nicht auf den Schirm darf

In den Pfaden des Zugriffsprotokolls stehen die Zugangslinks von `www`:
`/z/<Marke>`, 192 Bit, und wer sie hat, kommt hinein. Ein Werkzeug, das
Protokollzeilen anzeigt, zeigt sie mit — und die Ausgabe landet im
nächsten Chat (§22). Darum werden Pfade entschärft, **bevor** irgendetwas
gedruckt wird: `/z/…` und `/s/…` werden zu `/z/<Marke>`, und jedes
Wegstück ab 16 Zeichen ohne Punkt wird auf vier Zeichen gekürzt.
Quelladressen werden nur **gezählt**, nicht genannt.

Zwei Regeln, und die Mutationsprobe verlangt, dass **jede für sich**
durchfallen kann: nimmt man nur die `/z/`-Regel heraus, fängt die
Längenregel die Marke noch ab — die Prüfzeile bliebe grün, während die
Regel weg ist. Darum steht im Testprotokoll ein zweites langes Merkmal
außerhalb von `/z/`.

Und die Prüfzeile sucht ein **Stück** der Marke, nicht die ganze: die
Ausgabe kürzt Pfade auf 44 Zeichen, und 44 von 64 Zeichen eines
Geheimnisses sind auch dann ein Leck, wenn die vollständige Marke nicht
dasteht. Mit der ganzen Marke als Muster wäre die Zeile grün geblieben,
während zwei Drittel des Geheimnisses auf dem Schirm stehen — genau die
Art Prüfzeile, die nichts prüft (§13a).

### Prüfung

| | |
|---|---|
| `werkzeuge/zugriff-pruefen.sh` | **18 ok**, RC=0 (neu) |
| `werkzeuge/zugriff-gegenprobe.py` | **15 von 15** (neu) |
| `werkzeuge/prolo-pruefen.sh` | 96 ok, RC=0 — kennt den neuen Befehl |
| `wiki/tests/alle.sh` | 129 ok, 0 Fehler |

Die Zahlen im Testprotokoll sind **von Hand gezählt** (§13): n8n 10
Anfragen / 3 abgewiesen / 1 Fehler / 2 Quellen, wiki 4 / 0 / 0 / 0,
www 2 / 1 / 0 / 1. Die gedrehte Kopie daneben muss dieselben Zahlen
**verdoppeln** — sonst wäre „liest auch `.gz`" eine Behauptung ohne
Wirkung (`N-38`).

Drei Mutationen entwischten beim ersten Lauf und haben je eine Prüflinie
nachgezogen: die Längenregel (deckte sich mit der `/z/`-Regel), der
saubere Lauf (die Mutation hatte nur die halbe Meldung entfernt) und die
Marke selbst (siehe oben). Ohne die Gegenprobe wären alle drei als
geprüft durchgegangen.

`prolo-bedienen.html` führt den Befehl jetzt in der Befehlsliste und in
der Symptomtabelle unter „Die Seite bleibt beim ersten Aufruf schwarz".

---

## N-81 — „Kein Zugriff auf origin" — und das war alles

Direkt nach `N-80` gemeldet, beim Versuch, den neuen Stand zu holen:

> Der sudo kann das Repo nicht sehen und machen. Was soll ich machen?

Die Antwort darauf konnte niemand geben, auch nicht das Werkzeug selbst.
In `werkzeuge/quellstand.sh` stand:

```bash
timeout 20 git -C "$STACK" fetch --quiet origin "$ZWEIG" 2>/dev/null \
  || nicht_pruefbar "kein Zugriff auf origin"
```

Damit sah **jede** Ursache gleich aus:

| was wirklich los ist | was dastand |
|---|---|
| root hat keine Zugangsdaten für ein privates Repository | kein Zugriff auf origin |
| der Ordner gehört einem anderen Nutzer | kein Zugriff auf origin |
| kein Netz, DNS kaputt, Proxy davor | kein Zugriff auf origin |
| origin zeigt ins Leere | kein Zugriff auf origin |

Drei Ursachen, drei völlig verschiedene Abhilfen — und eine Zeile, aus der
sich keine davon ableiten lässt. Wer das liest, kann nur raten.

> Das ist wörtlich `N-64`, nur in einer anderen Datei: **ein `2>/dev/null`
> über dem fehlgeschlagenen Aufruf macht aus einer Diagnose eine Frage.**
> Eine Regel gilt nicht dort, wo sie aufgeschrieben wurde, sondern überall.

Besonders unangenehm war die Schleife: das Werkzeug, das sagt, wie man den
neuen Stand holt, war selbst nur durch einen neuen Stand zu reparieren. Der
Weg von Hand musste darum in die Meldung — und stand nicht drin.

### Was jetzt kommt

Die Meldung von `git` wird aufgehoben und weitergegeben, im Wortlaut, und
dazu **genau der Aufruf**, den das Skript gemacht hat:

```
  Quellstand         nicht pruefbar (kein Zugriff auf origin)

                     git sagt:
                       fatal: '…' does not appear to be a git repository
                       fatal: Could not read from remote repository.

                       Please make sure you have the correct access rights
                       and the repository exists.

                     Selbst nachsehen - genau dieser Aufruf war es:
                       sudo git -C /opt/stack fetch origin main
```

Drei Kleinigkeiten, die dazugehören:

- Das `sudo` steht nur da, wenn das Skript **als root** läuft — sonst wäre
  es der Rat, der nur manchmal passt und nach dem dritten Mal Tapete ist
  (`N-64`).
- Läuft der Aufruf in die Zeitgrenze, sagt `git` gar nichts mehr. Dann
  steht das da, statt einer leeren Stelle.
- `--kurz` verspricht **eine** Zeile und nichts, was ins Netz muss. Die
  Erklärung erscheint dort nicht.

Die beiden anderen `2>/dev/null` in derselben Datei wurden angesehen und
bleiben: `rev-list --count` kann nach einem geglückten `fetch` praktisch
nicht mehr scheitern, und scheitert `status --porcelain`, bricht das
darauffolgende `pull --ff-only` mit seiner eigenen — weitergegebenen —
Meldung ab. Stillschweigen entsteht dort also nicht.

### Prüfung

| | |
|---|---|
| `werkzeuge/prolo-pruefen.sh` | **101 ok**, RC=0 (vorher 96) |
| `werkzeuge/prolo-gegenprobe.py` | **23 von 23** (vorher 18) |
| `wiki/tests/alle.sh` | 129 ok, 0 Fehler |

Geprüft wird die **Wirkung**, nicht der Text: der Git-Teststand bekommt ein
`origin`, das ins Leere zeigt, und in der Ausgabe muss `does not appear to
be a git repository` **im Wortlaut** stehen — eine Prüfzeile, die nur „git
sagt:" sucht, bliebe grün, wenn darunter eine Umschreibung steht (`N-38`).

**Und `quellstand.sh` war für die Mutationsprobe gar nicht erreichbar.**
`prolo-pruefen.sh` kopiert die Dateien, die mutiert werden dürfen, in
seinen Wegwerfordner — `quellstand.sh` war nicht dabei, sondern wurde aus
dem Arbeitsstand genommen. Jede Mutation darauf wäre grün geblieben, aus
Mangel an Gelegenheit; genau die Falle, vor der der Kommentar zwei Zeilen
darüber warnt. Jetzt liegt sie wie `prolo` in der Kopie
(`QUELLE_QUELLSTAND`).

### Und der Prüfer der Wiki-Seite hat geholfen

Die Symptomtabelle in `prolo-bedienen.html` steht dreimal in der Datei:
als `markup`, als `text` und als gerendertes HTML. Im ersten Versuch landete
dort ein rohes `"` mitten in einem JSON-String — die Seite war damit
unlesbar. Aufgefallen ist es sofort, weil die Prüfung **vor** dem Schreiben
läuft: die Datei blieb unangetastet, statt kaputt im Arbeitsstand zu liegen.

## N-82 — Ein Browser, der wegklickt, beendete die Admin-Seite

Beim Durchsehen des ganzen Projekts gefunden, nicht gemeldet. In
`admin/server.py`, `main()`:

```python
# Ohne das bricht der Dienst mit BrokenPipeError ab, sobald ein Browser
# eine Antwort nicht zu Ende liest.
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
```

Der Kommentar beschreibt das Gegenteil dessen, was die Zeile tut. Python
**ignoriert** SIGPIPE von sich aus; ein Schreibversuch in eine geschlossene
Leitung wird dann zu einem `BrokenPipeError` in genau dem einen Faden, der
schreibt. Mit `SIG_DFL` dagegen beendet der Kern den **ganzen Prozess**.
Die Zeile gehört in ein Kommandozeilenwerkzeug, dessen Ausgabe in `head`
läuft — `werkzeuge/geheimnisse.py` hat sie dort zu Recht. In einen Dienst
kopiert, ist sie ein Ausschalter, den jeder Browser bedienen kann.

### Gemessen, nicht überlegt

Echter Prozess, zehn Verbindungen, die nach der Anfrage mit RST statt mit
einem geordneten Schließen enden (das tut ein Browser beim Wegklicken):

| | vorher | nachher |
|---|---|---|
| Verbindungen bis zum Ende des Dienstes | **1** (Rückgabe −13 = SIGPIPE) | keine nach 30 |
| `SigIgn` des Prozesses, Bit 13 | nicht gesetzt | gesetzt |

`restart: unless-stopped` hätte den Container jedes Mal neu gestartet —
sichtbar wäre davon nur ein kurzes „nicht erreichbar" gewesen, und in der
Liste der Neustarts ein Zähler, der langsam wächst. Genau der Zähler, an
dem `prolo aktualisieren` eine Fassung für kaputt hält (siehe `N-89`).

### Behoben

Die Zeile ist weg, und in `_lauf` wird `BrokenPipeError` /
`ConnectionResetError` still verworfen: wer schon weg ist, bekommt keine
Fehlerseite hinterhergeschickt — das wäre der zweite Schreibversuch in
dieselbe geschlossene Leitung, und genau der hat das Signal ausgelöst.

### Die Probe hat meine erste Prüflinie durchfallen lassen

Die erste Fassung des Tests holte eine Schriftdatei und prüfte, ob der
Dienst danach noch lebt. Die Mutation „SIGPIPE wieder auf Voreinstellung"
blieb damit **grün**, aus zwei Gründen:

- `gegenprobe.sh` kopiert nur `server.py` und `tests/` — ohne `schriften/`
  antwortete die Kopie mit einer kleinen 404, nicht mit der Datei.
- Mein neuer `except`-Zweig verhindert den zweiten Schreibversuch. Die
  Mutation baute also nur die **halbe** Ursache wieder ein.

Jetzt sind es zwei Prüflinien: eine misst die Ursache direkt (`SigIgn` in
`/proc/<pid>/status`), eine die Wirkung am echten Prozess. Und zwei
Mutationen: eine setzt nur das Signal zurück, eine stellt den alten Stand
im Ganzen her (Signal **und** Fehlerseite nach dem Schreibfehler).

| | |
|---|---|
| `admin/tests/alle.sh` | grün, 2 neue Prüflinien |
| `admin/tests/gegenprobe.sh` | **16 von 16** gefunden (vorher 14 von 14) |

Fassung 0.1.0 → **0.1.1** an allen drei Stellen.

## N-83 — `prolo einrichten` sah von einem Fremdwerkzeug nur die Hälfte

Beim Durchsehen gefunden. `N-70` hat die Regel aufgeschrieben — **jeder**
Prüfer, der nur `docker-compose.yml` liest, sieht bei einem Fremdwerkzeug
die Hälfte — und `prolo status`, `prolo dns` und die Grenzprüfung
nachgezogen. `werkzeuge/einrichten.sh` las an zwei Stellen weiter nur die
Datei des Herstellers:

| Schritt | was er liest | was dabei verloren ging |
|---|---|---|
| 5. Netze | externe Netze je Werkzeug | jedes Netz, das nur in der override-Datei steht |
| 9. Dienste starten | fehlende Netze je laufendem Werkzeug (`netze_fehlen`) | dasselbe, beim Nachhängen |
| 10. Was nur du tun kannst | die DNS-Namen | `n8n.prolo.me` |

Gemessen am Repository: Schritt 10 nannte **6** Namen, die Compose-Dateien
enthalten **7** — `n8n.prolo.me` fehlte. Wer einen neuen Server nach
dieser Liste beim DNS-Anbieter einträgt, vergisst genau diesen A-Eintrag,
und `n8n.prolo.me` bekommt nie ein Zertifikat (`N-69`).

Beim Netz ist n8n zufällig gedeckt: `netz-n8n` steht zusätzlich in der
Compose-Datei von Traefik und wird darüber angelegt. Ein Werkzeug, das
`prolo neu` gerade angelegt hat und dessen Netz Traefik noch nicht nennt,
wäre es nicht.

### Behoben

Beide Stellen lesen jetzt beide Dateien; bei den Netzen gewinnt die
override-Datei je Schlüssel, wie bei `docker compose` selbst. Die
Nachbildung mit regulären Ausdrücken bleibt — `docker compose config`
setzt eine `.env` voraus, und die gibt es beim Einrichten gerade noch
nicht.

### Probe

`einrichten-pruefen.sh` legt in seiner Kopie ein Fremdwerkzeug
`fremdprobe` an, dessen Netz und Name **nur** in der override-Datei stehen
und dessen Netz Traefik nicht nennt. Die Kopie nimmt jetzt auch die
override-Dateien mit (vorher nicht — auch die Probe sah nur die Hälfte),
und die Docker-Attrappe verbindet bei `up` die Netze aus beiden Dateien.

| | |
|---|---|
| `werkzeuge/einrichten-pruefen.sh` | **15 ok** (vorher 12) — *berichtigt in `N-85`: hier stand zuerst „18 (vorher 15)", nachgezählt an beiden Commits* |
| `… --gegenprobe` | **6 von 6** gefunden (vorher 4 von 4) |

Die neue Zählprüfung zählt die Namen mit `grep` über alle Compose-Dateien,
nicht mit dem Code, der geprüft wird: 8 in der Kopie (7 im Repository und
`fremdprobe.prolo.me`), 8 in der Liste.

## N-84 — Ein `authentik@file` irgendwo schützte den ganzen Dienst

Beim Durchsehen gefunden. Drei Stellen beantworten die Frage „ist dieser
Dienst geschützt?", und nur eine davon richtig:

| Stelle | läuft wo | wie sie urteilte |
|---|---|---|
| `werkzeuge/grenze-pruefen.sh` | im Repository | **je Router** — richtig |
| `werkzeuge/netze.sh` (`prolo start`, `prolo netze`) | auf dem Server | je Dienst: ein `authentik@file` in **irgendeiner** Middleware-Kette genügte |
| `admin/server.py` | auf dem Server | ebenso |

Damit fiel genau der Fall durch, vor dem `§17a` warnt: ein Werkzeug mit
geschütztem Hauptrouter und einem **zweiten** Router für Webhooks, der aus
Versehen ohne Anmeldung bleibt. `grenze-pruefen.sh` hätte ihn gefunden —
aber nur für Werkzeuge im Repository. Ein Werkzeug, das `prolo neu` auf dem
Server anlegt, sieht diese Prüfung nie; dort lief nur die Stelle, die sich
mit einem Treffer zufriedengab.

Gemessen mit einem Dienst `halb1`: Router `halb1` mit `authentik@file`,
Router `halb1-haken` (Priorität 100, `PathPrefix(/haken)`) ohne.

| | vorher | nachher |
|---|---|---|
| `prolo start halb1` | startet | **NICHT gestartet**, nennt `halb1-haken` |
| `prolo netze`, Spalte SCHUTZ | `authentik` | `OFFEN` |
| Admin-Seite | „Authentik" | „OFFEN – ohne Anmeldung · halb1-haken" |

### Behoben

Alle drei urteilen jetzt nach derselben Regel: jeder Router hat
`authentik@file`, oder steht in `prolo.oeffentlich=<router,…>`, oder der
Dienst erklärt `prolo.anmeldung=eigene`. `traefik.enable=true` **ohne**
eigenen Router gilt als offen — Traefik legt dann selbst einen an, mit
Vorgaberegel und ohne Middleware.

`netze.sh --dienste` gibt ein elftes Feld aus: die Router ohne Anmeldung.
`prolo start` nennt den Router beim Namen, statt `routers.<werkzeug>`
vorzuschlagen — bei zwei Routern ist der offene oft gerade **nicht** der,
der wie das Werkzeug heißt. Dazu kommt der dritte Ausweg in der Meldung,
`prolo.oeffentlich=<router>`, den `grenze-pruefen.sh` schon kannte.

Eine sichtbare Folge: **www** steht jetzt als „öffentlich" da statt als
„Authentik". Das ist die ehrlichere Angabe — die Startseite und die
Zugangslinks sind mit Absicht offen, nur `/verwaltung` liegt hinter der
Anmeldung.

### Probe

| | |
|---|---|
| `werkzeuge/neu-pruefen.sh` | **106 ok** (5 neue Prüflinien, Abschnitt 4e) |
| `werkzeuge/neu-gegenprobe.py` | **24 von 24** (3 neue Mutationen) |
| `admin/tests/alle.sh` | 41 Tests grün (3 neue) |
| `admin/tests/gegenprobe.sh` | **18 von 18** (2 neue) |
| `netze-pruefen.sh` / `prolo-pruefen.sh` / `grenze-pruefen.sh` | 42 / 101 / 66 ok |

Zwei alte Erwartungswerte im Admin-Test waren zu schwach und sind
angepasst — beide von Hand: `schutz_lesen` für einen Dienst **ohne** Router,
aber mit `prolo.oeffentlich=www`, ergab „öffentlich"; mit Router `www`
ergibt es das jetzt immer noch, ohne ist es „OFFEN (Vorgabe)". Und der
offene Router steht jetzt im zweiten Feld, statt einer leeren Zeichenkette.

Admin 0.1.1 → **0.1.2**.

## N-85 — Die Startsperre stand nur an einer von drei Türen

Beim Durchsehen gefunden. `prolo start` lässt nichts los, das einen
unerklärten Port veröffentlicht oder einen Router ohne Anmeldung hat
(`N-61`, `N-59`). Dienste werden aber auf **drei** Wegen gestartet:

| Weg | Sperre vorher |
|---|---|
| `prolo start` | ja |
| `prolo aktualisieren` (`aktualisieren.sh`, `docker compose up -d`) | **nein** |
| `prolo einrichten` (`einrichten.sh`, Schritt 9, Start und Neuverbinden) | **nein** |

Der gefährlichste der drei ist der zweite, weil er sich sicher anfühlt: er
sichert vorher und rollt bei Fehlschlag zurück. Der Fall aus der Praxis ist
eine neue Fassung eines Fremdwerkzeugs — man ersetzt die Datei des
Herstellers (§16), und der Hersteller hat seine `ports:`-Zeile wieder
drin. `prolo aktualisieren` holte, startete, fand den Dienst gesund und
meldete „FERTIG" — mit dem Dienst am offenen Netz, an Traefik und an der
Anmeldung vorbei.

Gemessen mit `aktualisieren-pruefen.sh`, Herstellerdatei mit
`ports: - "5678:5678"`:

| | vorher | nachher |
|---|---|---|
| Rückgabe | 0, „FERTIG" | **1**, „NICHT gestartet: probe/probe veröffentlicht Port(s) 5678" |
| `docker compose pull` | ja | **nein** |
| `docker compose up -d` | ja | **nein** |
| Zurückrollen | — | nein, es ist nichts passiert |

### Behoben

Die Sperre steht jetzt in `werkzeuge/startsperre.sh` und wird von allen
drei Wegen gelesen. `aktualisieren.sh` fragt sie **vor** dem Holen: was
gesperrt ist, wird gar nicht erst angefasst, und die laufenden Container
bleiben, wie sie waren. `einrichten.sh` fragt sie vor dem ersten Start und
vor dem Neuverbinden — Neuverbinden heißt neu anlegen, mit der
Konfiguration von jetzt.

### Probe

Die Attrappen in `aktualisieren-pruefen.sh` und `einrichten-pruefen.sh`
reichen `compose config` jetzt an das echte `docker` durch (wie
`neu-pruefen.sh` seit `N-61`) — vorher gaben sie dafür eine feste Zeile
zurück, und die Sperre hätte dort nie etwas zu sehen bekommen.
`aktualisieren-pruefen.sh` schreibt jeden Docker-Aufruf mit, damit sich
prüfen lässt, was **nicht** passiert ist.

| | |
|---|---|
| `werkzeuge/aktualisieren-pruefen.sh` | **79 ok** (5 neue) |
| `… --gegenprobe` (neu) | **2 von 2**: Sperre fehlt; Sperre erst nach dem Holen |
| `werkzeuge/einrichten-pruefen.sh` | **17 ok** (2 neue) |
| `… --gegenprobe` | **7 von 7** (1 neue) |
| `neu-gegenprobe.py` / `prolo-gegenprobe.py` | 24 von 24 / 23 von 23 — die drei Mutationen zur Sperre zeigen jetzt auf `startsperre.sh` |

Die zweite Mutation in `aktualisieren-pruefen.sh --gegenprobe` ist mir
zuerst falsch geraten: sie setzte einen zusätzlichen Aufruf **hinter** das
Holen und ließ den echten davor stehen. Sie blieb grün — zu Recht, denn
sie hatte nichts kaputt gemacht. Jetzt schaltet sie den echten Aufruf aus
und setzt ihn hinter das Holen; die Prüflinie „und nicht einmal geholt"
findet sie.

### Berichtigung zu `N-83`

Dort stand „`einrichten-pruefen.sh` 18 ok (vorher 15)". Nachgezählt an den
beiden Commits: **12 vor, 15 nach** `N-83`. Die drei neuen Prüflinien
stimmen, die Summen nicht — ich hatte die Ausgabe abgeschnitten gelesen
und dazugezählt, statt zu zählen. Die Zahl im Eintrag ist korrigiert; die
im Commit von `N-83` bleibt falsch, und darum steht es hier.

## N-86 — Der zweite Lauf eines Tages ersetzte den ersten, auch wenn er scheiterte

Beim Durchsehen gefunden. `backup.sh` legt „genau einen Stand pro Tag" ab
(`B-08`), und `age` schrieb dafür direkt auf `<datum>.tar.gz.age` — egal, wie
der Lauf ausgegangen war. Weil `prolo aktualisieren` **vor jedem Lauf**
sichert, gibt es an einem Arbeitstag leicht drei, vier Läufe. Scheitert
einer davon — Authentiks Datenbank startet gerade neu, ein Volume fehlt —,
ersetzt sein halbes Archiv das vollständige vom Morgen.

Und das halbe Archiv sah heil aus. `pg_dump | gzip > datenbank.sql.gz`:
scheitert `pg_dump`, schreibt `gzip` trotzdem eine gültige, leere
`.gz`-Datei. Bei SQLite wurde eine gescheiterte Kopie schon immer
weggeräumt („keine halbe Datei liegen lassen"), bei PostgreSQL nicht.

Gemessen am alten Stand, nur die Pfade umgebogen, zwei Läufe am selben Tag:

| | alter Stand |
|---|---|
| Lauf 1 | Rückgabe 0, Archiv `41b52456…` |
| Lauf 2, `pg_dump` scheitert | Rückgabe 1, Archiv **`cafdc267…`** — ersetzt |
| `datenbank.sql.gz` im Archiv des Tages | 20 Bytes, entpackt **0 Bytes** |

Die Datenbanksicherung vom Morgen war weg, und an ihrer Stelle lag eine
Datei, die genauso heißt. `§15` sagt es für Migrationen ausdrücklich: eine
bestehende Kopie wird nicht überschrieben, sonst ersetzt ein zweiter,
ebenfalls gescheiterter Lauf den einzigen brauchbaren Stand. Für die
Sicherung selbst galt es nicht.

### Behoben

`age` schreibt jetzt in eine Zwischendatei, und erst **nach** dem Lauf
wird entschieden, wohin sie kommt:

| Lauf | wohin |
|---|---|
| ohne Fehler | ersetzt `<datum>.tar.gz.age` — ein Stand pro Tag, wie bisher |
| mit Fehlern, der Tag hat schon einen Stand | daneben: `<datum>-unvollstaendig-<zeit>.tar.gz.age` |
| mit Fehlern, der Tag hat noch keinen | wird `<datum>.tar.gz.age` — besser als nichts, und der Erfolgsvermerk bleibt aus |

`<datum>-unvollstaendig-…` sortiert **vor** `<datum>.tar.gz.age` (`-` vor
`.`), also nimmt `prolo wiederherstellen` ohne `--stand` weiter den
vollständigen. Eine gescheiterte PostgreSQL-Sicherung wird weggeräumt wie
eine gescheiterte SQLite-Kopie.

Damit sich das prüfen lässt, nimmt `backup.sh` seine drei Orte aus
`PROLO_STACK`, `PROLO_SICHERUNGEN` und `PROLO_BESITZER`; auf dem Server
gelten die Vorgaben `/opt/stack`, `/opt/backups`, `prolo`.

### Probe

`werkzeuge/sicherung-lauf-pruefen.sh` ist neu: es gab bisher **keine**
Probe, die `backup.sh` selbst laufen lässt — `sicherung-pruefen.sh` prüft
`volumes.py`, also nur, ob alles in einer `sicherung.conf` steht. Die neue
Probe arbeitet mit einer Docker-Attrappe und dem echten `age` und
entschlüsselt die Archive, um hineinzusehen.

| | |
|---|---|
| `werkzeuge/sicherung-lauf-pruefen.sh` | **18 ok** |
| `… --gegenprobe` | **4 von 4**: halber Lauf überschreibt; leere Dump-Datei bleibt; halbes Archiv sortiert dahinter; guter Lauf ersetzt nicht |

Die Probe prüft die **Wirkung**: die Prüfsumme des Morgen-Archivs vor und
nach dem halben Lauf, und den entschlüsselten Inhalt der Datenbankdatei —
nicht die Meldung „UNVOLLSTAENDIG", die nur zusätzlich gesucht wird
(`N-38`). Die Mutationsprobe verweigert eine Mutation, die sich nicht
einbauen lässt, statt sie als „gefunden" zu zählen.

## N-87 — Die Sicherung wusste, was ein Werkzeug speichert, aber nicht, was es ist

Beim Durchsehen gefunden. `backup.sh` sichert je Werkzeug genau das, was
seine `sicherung.conf` nennt: Volumes, Datenbanken, `.env`, einzelne
Ordner. Die **Compose-Dateien** und die `conf`-Dateien selbst nicht — die
lagen im Git (`socket-proxy/sicherung.conf`: „die Datei docker-compose.yml
liegt im Git").

Das stimmt nur für Werkzeuge, die im Git **stehen**. `prolo neu` legt
Werkzeuge auf dem Server an (`N-61`), und dort entsteht ein Ordner ohne
Git (`N-68`). Nach einem Serververlust wären seine Daten in der Sicherung
— und niemand wüsste mehr, zu welchem Abbild, welchem Netz, welcher
Route sie gehören. `prolo wiederherstellen` meldete für so ein Werkzeug
`OHNE-CONF` und spielte gar nichts ein: ohne `sicherung.conf` auf dem
Server weiß es nicht einmal, was im Archiv zu wem gehört.

Mit einer Oberfläche, in die man eine Compose-Datei hineinwirft, wird
das der Normalfall, nicht die Ausnahme.

### Behoben

**Sichern:** je Werkzeug zusätzlich `werkzeug.tar.gz` — der Ordner, ohne
die `ORDNER`, die ohnehin einzeln gesichert werden, und ohne Ordner aus
`VOLUMES_OHNE` (Traefiks Zugriffsprotokolle können groß werden und
gehören nicht in eine Konfiguration). Dateien aus `VOLUMES_OHNE` bleiben
drin: „braucht keine Datensicherung" heißt nicht „gehört nicht zur
Konfiguration". `VOLUMES_OHNE` wurde vorher zwischen zwei Werkzeugen nicht
zurückgesetzt; das ist mit behoben, weil es jetzt gelesen wird.

**Einspielen:** fehlt ein Werkzeugordner auf dem Server und liegt er in
der Sicherung, liest `wiederherstellen.sh` die `sicherung.conf` aus dem
Archiv, sagt bei `--probe`, dass der Ordner angelegt würde — und legt ihn
erst beim echten Lauf an. Ein **vorhandener** Ordner wird nie
überschrieben (`§15`): dort liegt, was nach der Sicherung geändert wurde,
und für die Konfiguration ist das Git der bessere Rückweg.

Ältere Sicherungen ohne `werkzeug.tar.gz` bleiben einspielbar — das Stück
darf fehlen.

### Probe

| | |
|---|---|
| `werkzeuge/sicherung-lauf-pruefen.sh` | **24 ok** (6 neue) |
| `… --gegenprobe` | **7 von 7** (3 neue) |
| `werkzeuge/wiederherstellen-pruefen.sh` | **38 ok** (7 neue, Abschnitt 8c) |
| `werkzeuge/wiederherstellen-gegenprobe.py` | **16 von 16** (4 neue) |

Der Rundlauf in 8c: ein Archiv mit einem Werkzeug `neuling`, das es im
Wegwerfstack nicht gibt, und einem `werkzeug.tar.gz` für `probe`, dessen
Compose-Datei ein anderes Abbild nennt. Nach dem Einspielen muss
`neuling` mit Compose-Datei **und** Daten dastehen und `probe` seine
eigene Compose-Datei behalten haben.

## N-88 — „Kein Neustart nötig" kam mit echtem Docker nie

Beim Nachmessen zu `N-89` gefunden — mit einem echten Docker-Dienst, den
es in dieser Arbeitsumgebung bisher nicht gab und der sich jetzt starten
ließ.

`aktualisieren.sh` wollte einen Neustart sparen, wenn sich die Abbilder
nicht geändert haben und alle Container laufen. Die Entscheidung stand in
`alle_laufen()`:

```bash
veraltet=$(docker compose ps 2>/dev/null | grep -ci "created\|exited" || true)
[ "$veraltet" -gt 0 ] && return 1
```

`docker compose ps` druckt eine Tabelle, und ihre Kopfzeile lautet
`NAME IMAGE COMMAND SERVICE CREATED STATUS PORTS`. Das Wort **CREATED**
steht in jeder Ausgabe. Mit echtem Docker lief der Zweig „Kein Neustart
nötig" darum **nie** — jeder Lauf meldete „Container werden neu
gestartet ...", auch wenn nichts neu gestartet wurde. Die Attrappe in
`aktualisieren-pruefen.sh` druckte für `compose ps` nur `c1`, ohne
Kopfzeile — sie hat den Fehler nicht nur nicht gefunden, sie hat ihn
verdeckt, und zwei Prüflinien waren grün, weil sie einen Zweig prüften,
den es in Wirklichkeit nicht gibt.

Schaden hat das keinen angerichtet, und genau darum ist es lehrreich:
`docker compose up -d` ist von sich aus sparsam. Compose legt nur neu an,
was sich geändert hat — Abbild **oder** Konfiguration — und lässt alles
andere laufen. Die eigene Vorhersage war nicht nur tot, sie war auch
schlechter als das, was sie ersetzen wollte: sie kannte nur Abbilder,
keine Konfiguration. Hätte sie funktioniert, wäre eine geänderte
Umgebungsvariable bei gleichem Abbild nie angekommen.

### Behoben

`docker compose up -d` läuft immer. Ob etwas neu angelegt wurde, sagen
die Container-Kennungen vorher und nachher (`docker compose ps -a -q`) —
gemessen, nicht vorhergesagt. Die Meldung heißt jetzt „Nichts neu
angelegt — Abbilder und Konfiguration sind unverändert" statt „Kein
Neustart nötig", weil das die Aussage ist, die gemessen wurde.

### Gemessen mit echtem Docker

| | Ausgabe | Container |
|---|---|---|
| nichts geändert | „Nichts neu angelegt", „FERTIG. probe ist aktuell und läuft." | läuft weiter |
| nur `environment:` geändert | „FERTIG. probe läuft." | neu angelegt, `EINSTELLUNG=neu` im Container |

### Probe

Die Attrappe druckt für `compose ps` jetzt eine Tabelle **mit** Kopfzeile,
wie das echte, und wechselt die Container-Kennung nur, wenn `up`
wirklich neu anlegt.

| | |
|---|---|
| `werkzeuge/aktualisieren-pruefen.sh` | **82 ok** (4 neue; eine alte Prüflinie auf die gemessene Aussage umgestellt) |
| `… --gegenprobe` | **4 von 4** (2 neue: Vorhersage statt Messung; `up -d` entfällt bei gleichen Abbildern) |

## N-89 — Wer einmal neu gestartet ist, ließ jede Aktualisierung scheitern

Beim Durchsehen gefunden, mit echtem Docker bestätigt. `aktualisieren.sh`
erkennt einen Dauerabsturz an `RestartCount > 2`. Docker zählt diesen Wert
aber über die **ganze Lebenszeit** eines Containers — gemessen: ein
Container, der dreimal abstürzt und dann läuft, zeigt nach 1, 3, 6, 12, 20
und 35 Sekunden unverändert `3`, und so bleibt es, bis er neu angelegt
wird.

Ein einziger Datenbankausfall in der Nacht, bei dem ein Werkzeug dreimal
neu startet, bis Authentik wieder da ist — und von da an scheitert jeder
`prolo aktualisieren`-Lauf für dieses Werkzeug:

```
[3/4] Container werden neu gestartet ...
  FEHLER: probe-probe-1 startet staendig neu (3 Neustarts).
!!! FEHLGESCHLAGEN - probe wird zurueckgerollt.
```

Mit echtem Docker so gemessen, bei einem Container, der seit Minuten
gesund lief und an dem sich nichts geändert hatte. Liegt ein Rückweg vor,
wird er auch gegangen: die `docker-compose.yml` wird auf den letzten
erfolgreichen Stand zurückgesetzt — bei einem Werkzeug, das gar kein
Problem hat. `N-82` hätte genau diesen Zähler bei der Admin-Seite mit
jedem weggeklickten Browser hochgetrieben.

### Behoben

Vor `docker compose up -d` merkt sich der Lauf die Neustarts jedes
Containers, und in der Prüfung zählt nur, was **seitdem** dazukommt. Ein
Container, den `up -d` neu anlegt, hat eine neue Kennung und zählt von 0.

### Gemessen mit echtem Docker

| | vorher | nachher |
|---|---|---|
| früher 3× neu gestartet, jetzt gesund, nichts geändert | FEHLER, Rückgabe 1, Zurückrollen | „FERTIG. probe ist aktuell und läuft.", Rückgabe 0 |
| echter Dauerabsturz (`exit 1`) | FEHLER | FEHLER, „5 Neustarts seit Beginn dieses Laufs", Zurückrollen |

### Probe

Die Attrappe hatte einen **festen** Zählerstand 7 für „Dauerneustart" —
das ist in Wirklichkeit ein Container, der irgendwann einmal neu gestartet
ist, also genau der Fall, der kein Fehler sein darf. Jetzt wächst der
Zähler bei jeder Abfrage, und der feste Wert heißt `frueher`.

| | |
|---|---|
| `werkzeuge/aktualisieren-pruefen.sh` | **85 ok** (3 neue) |
| `… --gegenprobe` | **5 von 5** (1 neue: Zählung über die Lebenszeit) |

## N-90 — „kam nicht hoch: sudo prolo protokoll …" — und das Protokoll war leer

Gefunden beim ersten echten Lauf von `prolo einrichten` auf einem frischen
Stapel mit echtem Docker (in dieser Arbeitsumgebung ließ sich zum ersten
Mal ein Docker-Dienst starten). Schritt 9 meldete:

```
FEHLER  socket-proxy kam nicht hoch:  sudo prolo protokoll socket-proxy
FEHLER  traefik kam nicht hoch:  sudo prolo protokoll traefik
FEHLER  authentik kam nicht hoch:  sudo prolo protokoll authentik
FEHLER  admin kam nicht hoch:  sudo prolo protokoll admin
FEHLER  n8n kam nicht hoch:  sudo prolo protokoll n8n
FEHLER  wiki kam nicht hoch:  sudo prolo protokoll wiki
```

Sechs Fehler, sechs Verweise auf `prolo protokoll` — und das zeigt bei
einem Container, der nie angelegt wurde, **nichts**. Die Ursache hatte
das Skript in der Hand: `docker compose up -d >/dev/null 2>&1`. Wörtlich
`N-64` und `N-81`, in der dritten Datei.

Was docker tatsächlich gesagt hätte (nachgeholt, von Hand):

| Werkzeug | Ursache |
|---|---|
| socket-proxy | das Abbild ließ sich nicht laden (hier: Netzsperre der Arbeitsumgebung) |
| traefik, admin | `network socket declared as external, but could not be found` — Folge von socket-proxy |
| authentik | `required variable PG_PASS is missing a value` — Schritt 7 hat ihn offen gelassen |
| n8n | `required variable N8N_ENCRYPTION_KEY is missing a value` — ebenso |
| wiki | der Bau scheiterte an `apt-get` (hier: Netzsperre der Arbeitsumgebung) |

Jede dieser Zeilen führt direkt zur Abhilfe. Keine davon stand da.

### Behoben

Die Ausgabe von `docker compose up -d` wird aufgehoben. Scheitert es,
stehen die letzten Zeilen **ohne** den Fortschritt davor da (beim ersten
Start schreibt docker seitenweise „Pulling fs layer" — die Ursache steht
darunter). Für die beiden häufigen Ursachen beim Einrichten kommt der Weg
daraus dazu, und nur dann, wenn die Meldung ihn hergibt:

```
FEHLER  authentik kam nicht hoch:
        docker sagt:
          error while interpolating services.postgresql.environment.POSTGRES_PASSWORD:
          required variable PG_PASS is missing a value: database password required
        Ein Wert fehlt in authentik/.env - Schritt 7 hat ihn offen gelassen.
        Bei einem frischen Aufbau (noch keine Daten) fuellt ihn:
          sudo prolo geheimnisse --verteilen --frisch
        Beliebig oft aufrufbar - vorhandene Werte bleiben stehen.
```

Das ist die echte Ausgabe aus dem zweiten Lauf auf dem Wegwerf-Server.

### Probe

| | |
|---|---|
| `werkzeuge/einrichten-pruefen.sh` | **20 ok** (3 neue) |
| `… --gegenprobe` | **9 von 9** (2 neue: Meldung verschluckt; Rauschen nicht gefiltert) |

Die zweite Mutation ist mir zuerst falsch geraten: sie nahm `tail -4` weg
und ließ den Filter stehen — sie blieb grün, zu Recht. Der Filter steht
jetzt in einer eigenen Variable, die Mutation leert sie.

## N-91 — Auf jedem neuen Server war `acme.json` ein Ordner

Beim ersten echten Lauf auf einem frischen Stapel gefunden. Traefik hängt
`./acme.json` ein. Auf einem frischen Klon gibt es die Datei nicht — sie
steht mit Absicht nicht im Git (`§21`) —, und Docker legt für eine
fehlende Quelle eines Bind-Mounts einen **Ordner** an. Traefik dazu, im
Wortlaut:

```
ERR The ACME resolve is skipped from the resolvers list
    error="unable to get ACME account: permissions 755 for
    /letsencrypt/acme.json are too open, please use 600"
```

Kein Let's Encrypt, auf keinem Namen. Jede Seite zeigt „nicht sicher",
und das Notzertifikat heißt `TRAEFIK DEFAULT CERT`. Das ist die Narbe aus
`N-05` — dort waren es die Rechte an einer vorhandenen Datei, hier ist es
die Datei selbst. Die Anleitung im Kommentar der Compose-Datei nennt
`chown` und `chmod` für `acme.json`, aber nirgends, dass sie erst
**angelegt** werden muss, und `prolo einrichten` tat es nicht. Genau die
Sorte Handgriff, die `N-54` aus den Anleitungen ins Skript holen wollte.

### Behoben

`prolo einrichten` hat einen Schritt **6b**: alles, was ein Werkzeug aus
seinem Ordner einhängt, muss vor dem ersten Start da sein. Was es wo
braucht, sagt das Werkzeug selbst, in der `sicherung.conf`, die es ohnehin
hat:

| steht in | wird angelegt als |
|---|---|
| `DATEIEN` | leere Datei, `0600` |
| `ORDNER`, `VOLUMES_OHNE` | leerer Ordner |
| nirgends | **nichts** — gemeldet mit `git checkout` bzw. dem Hinweis auf die `sicherung.conf`; eine leere Konfigurationsdatei wäre falsch, nicht fehlend |

Ein **leerer** Ordner, wo eine Datei hingehört, ist das Überbleibsel eines
früheren Starts und wird ersetzt. Ein Ordner **mit Inhalt** wird nicht
angefasst, sondern gemeldet.

### Gemessen auf dem Wegwerf-Server

```
6b. Was eingehaengt wird, muss vor dem ersten Start da sein
  getan   authentik/certs/ angelegt
  getan   authentik/custom-templates/ angelegt
  getan   authentik/data/ angelegt
  getan   traefik/acme.json war ein leerer Ordner (Ueberbleibsel eines Starts) - jetzt eine Datei, 0600
  ok      traefik/dynamic
  ok      traefik/log/
  ok      traefik/traefik.yml
```

Danach Traefik neu angelegt: **0** Zeilen „too open" im Protokoll (vorher 1).
Beim zweiten Lauf nur noch `ok`.

Beim ersten Lauf auf dem Server kam dazu ein `BrokenPipeError` aus meinem
eigenen Python-Stück: seine Ausgabe läuft in `grep -q`, und das schließt
nach dem ersten Treffer. Dort ist `SIGPIPE` auf Voreinstellung richtig —
genau der Fall, für den die Zeile gedacht ist, die in `N-82` aus dem
Dienst weg musste.

### Probe

| | |
|---|---|
| `werkzeuge/einrichten-pruefen.sh` | **26 ok** (6 neue) |
| `… --gegenprobe` | **11 von 11** (2 neue: leerer Ordner bleibt; Datei ohne `0600`) |

## N-92 — Ohne IPv6 im Kern gab es keinen einzigen Router

Beim ersten echten Lauf gefunden. `socket-proxy` startete in Schleife neu:

```
[ALERT] Starting frontend dockerfrontend: cannot create listening socket [:::2375]
```

Das Abbild bindet von sich aus an `[::]`. Diese Arbeitsumgebung hat gar
kein IPv6 im Kern (`/proc/sys/net/ipv6` fehlt) — auf gewöhnlichen Servern
ist das anders, aber gehärtete Server schalten es oft mit
`ipv6.disable=1` ab, und genau dort passiert dasselbe. Ohne den
Vermittler findet Traefik **keinen** Router; der ganze Stack ist dann
unerreichbar, und `prolo status` zeigt „socket-proxy 0/1".

Der Stack benutzt IPv6 nirgends: `prolo einrichten` verlangt ausdrücklich
keinen AAAA-Eintrag, und `socket` ist ein internes IPv4-Netz. Das Abbild
kennt dafür `DISABLE_IPV6`.

| | vorher | nachher |
|---|---|---|
| `socket-proxy` auf einem Kern ohne IPv6 | Neustart in Schleife (6 Neustarts nach Sekunden) | läuft, 0 Neustarts |

### Probe

| | |
|---|---|
| `werkzeuge/grenze-pruefen.sh` | 1 neue Prüflinie, grün |
| `werkzeuge/grenze-gegenprobe.py` | **13 von 13** (1 neue; muss genau an dieser Zeile rot werden) |

## N-93 — `sniStrict` stand in einer Option, die für fremde Namen nie gilt

Beim ersten echten Lauf gefunden. `traefik/dynamic/sicherheit.yml`
verspricht:

> sniStrict: eine Anfrage ohne passenden Servernamen bekommt KEIN
> Standardzertifikat mehr. Zusammen mit B-27 ist damit der Weg zu einer
> Täuschungsseite auf einem fremden Hostnamen zu.

Gemessen mit Traefik 3.6.13 und einem Testzertifikat für `prolo.me`:

| Anfrage | vorher | nachher |
|---|---|---|
| `prolo.me` | 200 | 200 |
| fremder Name `fremd.example` | **Handshake mit dem Notzertifikat, 404** | Handshake verweigert |
| ganz ohne Namen | **Handshake mit dem Notzertifikat, 404** | Handshake verweigert |
| TLS 1.1 auf `prolo.me` | — | verweigert |

Die Einstellung stand in einer Option namens `streng`, und der Eingang
verwies darauf. Für einen **unbekannten** Namen gibt es aber keinen
Router — also auch keine Option vom Router oder vom Eingang. Traefik
nimmt dann die Option `default`, und in der stand nichts. `sniStrict`
galt damit nur für Namen, die ohnehin einen Router haben: genau dort, wo
es nichts zu verhindern gibt.

Viel Schaden war nicht drin — hinter dem Notzertifikat kam eine 404 —,
aber eine Sicherheitseigenschaft, die in der Datei behauptet wird und
nicht gilt, ist schlimmer als eine, die fehlt: man verlässt sich darauf.
Und das Notzertifikat trägt den Namen `TRAEFIK DEFAULT CERT` — für jeden,
der nach Traefik-Servern sucht, ein Schild an der Tür.

### Behoben

Die Option heißt `default`. Sie gilt damit für jeden Router, der keine
andere nennt, **und** für jeden Namen ohne Router; am Eingang steht keine
Option mehr (`tls: {}`).

### Probe

| | |
|---|---|
| `werkzeuge/grenze-pruefen.sh` | 2 neue Prüflinien, grün |
| `werkzeuge/grenze-gegenprobe.py` | **14 von 14** (1 neue, muss genau an dieser Zeile rot werden) |
| echter Traefik, vorher/nachher | siehe Tabelle |

## N-94 — `prolo geheimnisse` startete, was nie lief, und an der Sperre vorbei

Beim ersten echten Lauf von `prolo einrichten` gefunden. Schritt 7
verteilt die Geheimnisse und startete danach die betroffenen Dienste
„neu":

```
PROLO_EINLASS
  neu gewuerfelt: admin/.env
  ...
  traefik neu starten ...
  FEHLGESCHLAGEN: Image traefik:v3.6.13 Pulling
   7e8a8ec6ab16 Pulling fs layer 0B
   8213dc07c4f6 Pulling fs layer 0B
   ...
```

Drei Fehler in einer Meldung:

1. **Es startete, was nie lief.** `dienste_neu()` rief `docker compose up
   -d` für jedes Werkzeug, dessen Datei es angefasst hatte. Auf einem
   frischen Server heißt das: Traefik wird mitten in Schritt 7 zum ersten
   Mal gestartet — vor socket-proxy, dessen Netz er braucht, und zwei
   Schritte vor dem Schritt, der die Reihenfolge kennt.
2. **Die Ursache war abgeschnitten.** Gezeigt wurden die ersten 300
   Zeichen von stderr — dort schreibt docker seinen Fortschritt. Was
   wirklich schiefging, stand darunter und fehlte.
3. **Die vierte Tür ohne Sperre.** `up -d` legt neu an, mit der
   Konfiguration von jetzt. `N-85` hat die Startsperre an drei Türen
   gestellt; diese war die vierte.

### Behoben

Neu gestartet wird nur, was läuft; was nicht läuft, liest den neuen Wert
beim nächsten Start von selbst, und das steht so da. Vor dem Neustart
steht dieselbe Sperre wie bei `prolo start`. Scheitert er, stehen die
letzten Zeilen von docker ohne Fortschritt da.

### Probe

Die Probe baut einen Mini-Stapel mit drei Werkzeugen — `halt` (läuft
nicht), `laeuft`, `offenport` (läuft, mit unerklärtem Port) — und eine
Docker-Attrappe, die jeden Aufruf mitschreibt und `compose config` an das
echte docker durchreicht.

Beim Schreiben ist mir die Reihenfolge fast durchgerutscht: die Schleife
geht alphabetisch und bricht nach einer Sperre ab. Hieß das nicht
laufende Werkzeug `steht`, kam es **nach** `offenport` und wurde nie
erreicht — seine Prüflinie wäre grün gewesen, aus Mangel an
Gelegenheit. Es heißt darum `halt`, und die Prüflinie verlangt
zusätzlich, dass „halt laeuft nicht" in der Ausgabe steht.

| | |
|---|---|
| `werkzeuge/geheimnisse-pruefen.sh` | **161 ok** (5 neue) — *berichtigt in `N-95`: zuerst stand hier 160/4* |
| `… --gegenprobe` | **48 von 48** (3 neue) |

Der Vorlauf der Mutationsprobe war zuerst rot: ihre Kopie des Stapels
kannte `startsperre.sh` und `netze.sh` nicht. Genau dafür gibt es den
Vorlauf — ohne ihn wäre jede Mutation „gefunden" gewesen.

## N-95 — Die Gruppe, ohne die die Admin-Seite 403 sagt, stand nirgends

Beim ersten echten Lauf gefunden. `prolo einrichten` endet mit einer
Liste der Gruppen, die man in Authentik anlegen soll:

```
  Gruppen in Authentik anlegen und sich selbst zuweisen:
    wiki-editor, wiki-admin   Wiki: schreiben bzw. verwalten
    stack-admin               Verwaltung auf prolo.me
```

Die Liste stand **fest im Skript** — genau die Sorte zweite Liste, die
veraltet, und `§16` sagt: im zentralen Skript steht kein Werkzeugname.
Veraltet war sie: die Admin-Seite (seit `N-63`) verlangt die Gruppe
`admin`, das Bordbuch `bordbuch-admin` für die Gesamtsicherung. Beide
fehlten. Wer nach dieser Liste einrichtet, bekommt auf `admin.prolo.me`
eine 403 und weiß nicht, dass die Liste unvollständig war.

### Behoben

Jedes Werkzeug nennt seine Gruppen selbst, als Label an seinem Dienst:

```yaml
- "prolo.gruppen=wiki-editor=Seiten anlegen und die eigenen bearbeiten; wiki-admin=das Wiki verwalten"
```

`prolo einrichten` liest sie aus beiden Compose-Dateien (`N-83`) und
listet sie mit dem Werkzeug dazu. Auf dem Wegwerf-Server:

```
  Gruppen in Authentik anlegen und sich selbst zuweisen:
    admin            admin        die Stack-Uebersicht sehen
    bordbuch-admin   bordbuch     alle Fahrtenbuecher sichern und zurueckspielen
    stack-admin      www          Seiten und Zugangslinks auf prolo.me verwalten
    wiki-admin       wiki         das Wiki verwalten
    wiki-editor      wiki         Seiten anlegen und die eigenen bearbeiten
```

Damit das Label nicht selbst die nächste veraltete Liste wird, prüft
`grenze-pruefen.sh` je Werkzeug: jede Gruppe, die der Code **wirklich**
prüft (Vorgabe im Code, überschrieben von der Compose-Datei), steht im
Label. Nach der Aufteilung in eigene Repositorys gehört das Label in die
Compose-Datei, die das Werkzeug mitbringt — das Werkzeug sagt, was es
braucht.

### Probe

| | |
|---|---|
| `werkzeuge/grenze-pruefen.sh` | **73 ok** (4 neue, je Werkzeug eine) |
| `werkzeuge/grenze-gegenprobe.py` | **16 von 16** (2 neue: Admin nennt seine Gruppe nicht; Wiki nennt nur eine von zwei) |
| `werkzeuge/einrichten-pruefen.sh` | **28 ok** (2 neue: `admin` steht da; alle 5 erklärten Gruppen stehen da) |
| `… --gegenprobe` | **13 von 13** (2 neue) |

### Berichtigung zu `N-94`

Dort stand „`geheimnisse-pruefen.sh` 160 ok (4 neue)". Gezählt: **161,
5 neue** — die fünfte ist die Prüflinie zur abgeschnittenen Ursache, die
ich nachträglich dazugeschrieben und in der Summe vergessen hatte.

## N-96 — Die Vorlage nannte einen Befehl, den es nie gab

Beim Durchsehen gefunden. `traefik/dynamic/einlass.yml.beispiel` —
die Datei, die man abschreibt, um die Vertrauensgrenze (`N-44`)
einzurichten — sagte unter „ANLEGEN":

```
#   4. Erst Traefik, dann die Werkzeuge:
#        sudo prolo compose traefik  up -d
#        sudo prolo compose wiki     up -d
#        sudo prolo compose bordbuch up -d
```

`prolo compose` gibt es nicht; `N-51` und `N-56` haben genau diesen
erfundenen Befehl schon zweimal aus Anleitungen und Fehlermeldungen
geholt. Die Prüfung aus `N-51` las alle Dateien auf `.md .html .py .sh
.mjs .yml .conf` — eine **Vorlage** endet auf `.beispiel`, und die sah
sie nie. Gemessen: mit `.beispiel` in der Liste meldet sie sofort
`traefik/dynamic/einlass.yml.beispiel nennt "prolo compose"`.

Und die Vorlage beschrieb vier Handgriffe — würfeln, kopieren, in jede
`.env` eintragen, in der richtigen Reihenfolge neu starten —, die seit
`N-50` ein einziger Befehl erledigt, idempotent. `§7` (`N-67`): die
Meldung nennt den Befehl, nicht die Aufgabe.

### Behoben

- Die Befehlsprüfung liest auch `.beispiel`-Dateien.
- Die Vorlage nennt `sudo prolo geheimnisse --verteilen` (anlegen) und
  `--neu` (wechseln), mit dem Hinweis, dass er beliebig oft aufrufbar ist;
  der Weg von Hand steht darunter, mit echten Befehlen (`prolo start`).

### Probe

| | |
|---|---|
| `prolo-befehle-pruefen.py .` | ok, 42 bekannte Befehle (vorher mit `.beispiel`: 1 FEHLER) |
| `… --gegenprobe` | neue Mutation „eine Vorlage nennt einen erfundenen Befehl" **gefunden** |

Beim Lauf der Gegenprobe fiel auf, dass eine **andere**, ältere Mutation
sich seit `N-61` nicht mehr einbauen lässt — sie zielt auf einen
Kommentar, den es seitdem nicht mehr gibt. Die Gegenprobe war damit seit
Wochen rot, ohne dass es jemand gemerkt hat. Das ist ein eigener Befund:
`N-97`.

## N-97 — Eine Gegenprobe war seit `N-61` rot, und niemand hat es gemerkt

Beim Arbeiten an `N-96` gefunden. `prolo-befehle-pruefen.py --gegenprobe`
meldete:

```
2. Geruest-Kommentar nennt prolo compose  NICHT EINGEBAUT
   (Textstelle fehlt in werkzeuge/prolo: '  #   sudo prolo start traefik\n')
1 von 7 Mutationen blieben unentdeckt
```

Die Mutation zielte auf einen Kommentar in `werkzeuge/prolo`, den `N-61`
entfernt hat (`git log -S` nennt den Commit `ad790cc`). Seitdem ließ sie
sich nicht mehr einbauen, und die Gegenprobe war rot. Gemerkt hat es
niemand, denn sie läuft nur, wenn jemand sie von Hand aufruft — und
`prolo-pruefen.sh` ruft nur die Prüfung, nicht ihre Gegenprobe.

Das ist die Lehre aus `§13a` eine Ebene höher: eine Gegenprobe beweist,
dass eine Prüfung Zähne hat — aber nur, wenn sie läuft. Es gab
**34** Prüfungen und Gegenproben in diesem Stapel und **keinen** Lauf,
der alle ausführt.

### Behoben

- **`werkzeuge/alle-pruefen.sh`**: jede `*/tests/alle.sh`, jede
  `werkzeuge/*-pruefen.sh`, jede Gegenprobe — gefunden am Dateisystem,
  nicht an einer Liste (`§16`); eine neue Prüfung braucht dort keine
  Zeile. Eine Tabelle mit Dauer und Ergebnis, bei Rot die ersten
  Fehlzeilen, und ein Rückgabewert, der nur bei **allem** grün 0 ist.
  `--schnell` lässt die Gegenproben weg (Minuten statt einer
  Viertelstunde).
- **`.github/workflows/pruefen.yml`**: derselbe Lauf bei jedem Push und
  jedem Pull Request.
- Die veraltete Mutation zielt jetzt auf eine Meldung, die `prolo` selbst
  ausgibt (`sudo prolo neu <name>` → `sudo prolo anlegen <name>`).

### Ausgeführt

Der erste Sammellauf, **vor** der Reparatur:

```
Gegenproben (haben die Pruefungen Zaehne? §13a)
  ...
  werkzeuge/prolo-befehle-pruefen.py --gegenprobe      ROT       0s  (Rueckgabe 1)
        2. Geruest-Kommentar nennt prolo compose      NICHT EINGEBAUT (...)
  ...
1 rot: werkzeuge/prolo-befehle-pruefen.py --gegenprobe
```

33 von 34 grün, und der eine rote genau der seit `N-61`. Danach
`prolo-befehle-pruefen.py --gegenprobe`: **8 von 8** gefunden.

## N-98 — `CLAUDE.md` verwies auf einen Abschnitt, den es nie gab

Beim Zusammenstellen der Regeln für die ausgelagerten Werkzeuge gefunden.
`§15` sagt: „Vor Migrationen, die Daten verändern, gilt der Dreischritt
aus **§19a**". Einen §19a gibt es nicht — der Dreischritt steht in `§24a`.

`regeln-pruefen.sh` prüft seit `N-39`, dass jeder zitierte Abschnitt
existiert: 148 Verweise der Form „CLAUDE.md §…" aus allen anderen
Dateien. Die Regeldatei selbst schloss er aus (`p == regeln`) — und ihre
eigenen 21 Verweise wurden nie geprüft. Gemessen: genau einer davon zeigt
ins Leere.

### Behoben

`§15` verweist auf `§24a`, und die Prüfung liest auch die Verweise in der
Regeldatei selbst.

### Probe

| | |
|---|---|
| `werkzeuge/regeln-pruefen.sh` | grün, „jeder der 32 zitierten Abschnitte gibt es wirklich" |
| Mutation (Kopie nach der Korrektur, `§24a` → `§19a`) | **rot**: „jeder der 33 zitierten Abschnitte" — FEHLER |

---

# Umbau: proloWorld wird die Betriebsplattform

**Auftrag (29.09.2026):** „Die Projekte www, Bordbuch und wiki will ich
separat halten. Also eigene Repos … Mein Wunsch ist, dass proloWorld nur
das Administrieren von Tools ganz einfach macht … Nur auch so Tools wie
das Bordbuch sollen als extern gesehen werden."

Die Schritte dieses Umbaus sind keine Befunde, sondern Entscheidungen.
Sie bekommen darum eine eigene Nummernfolge: `U-01` aufwärts.

## U-01 — Eigene Werkzeuge bekommen eine Herstellerdatei wie n8n

**Entscheidung.** Ein eigenes Werkzeug wird im Betrieb genauso behandelt
wie ein fremdes (`§16`, `N-61`): seine `docker-compose.yml` ist die
**Herstellerdatei** — sie gehört zum Werkzeug und liegt später in dessen
eigenem Repository —, und alles, was vom Betrieb kommt, steht daneben in
der `docker-compose.override.yml`.

| Herstellerdatei (Werkzeug) | override (Betrieb) |
|---|---|
| Abbild, `build: .`, `container_name` | Netz `netz-<werkzeug>` |
| Rechte: `cap_drop`, `no-new-privileges`, `read_only`, `tmpfs` | Traefik: Route, Zertifikat, Anmeldung |
| Umgebung, `PROLO_EINLASS` mit `:?` | `mem_limit`, `pids_limit` |
| Volumes, Label `prolo.gruppen` | |

Eine Abweichung, und sie ist Absicht: bei **www** stehen die beiden Router
in der Herstellerdatei. Welche Pfade öffentlich sind, ist dort die
Sicherheitsgrenze des Werkzeugs (`N-74`), und `www/tests/test_freigabe.py`
hält Code und Regel zusammen — das geht nur im selben Repository.

Dazu zwei Festlegungen, die den Umzug später zu einer Zeile machen:

- Das Abbild heißt schon jetzt so, wie es veröffentlicht wird:
  `ghcr.io/prolo2408/<werkzeug>:<fassung>`. Solange `build: .` dasteht,
  wird es wie bisher auf dem Server gebaut und nur so benannt.
- Der Projektname steht fest (`name: <werkzeug>`). Nach ihm heißen die
  Volumes (`bordbuch_bordbuch_daten` …); ohne ihn hinge er am Ordnernamen,
  und ein Klon unter anderem Namen fände seine Daten nicht.

### Ausgeführt

Die zusammengesetzte Konfiguration (`docker compose config`) alt gegen
neu, je Werkzeug, normalisiert:

| | Abbild | sonst |
|---|---|---|
| wiki | `wiki:1.4.1` → `ghcr.io/prolo2408/wiki:1.4.1` | nur der Hinweistext bei fehlendem `PROLO_EINLASS` (nennt jetzt `prolo geheimnisse --verteilen`, `N-96`) |
| bordbuch | `bordbuch:2.6.1` → `ghcr.io/prolo2408/bordbuch:2.6.1` | ebenso |
| www | `www:1.1.1` → `ghcr.io/prolo2408/www:1.1.1` | ebenso |

Volume-Namen, Netze, Labels, Grenzen: unverändert. Auf dem Server
bedeutet das beim nächsten `prolo aktualisieren`: einmal neu bauen unter
neuem Namen, Container neu anlegen, **dieselben** Volumes.

`werkzeuge/alle-pruefen.sh --schnell`: **alles grün** (4 Werkzeug-Suiten,
15 Prüfungen des Stapels). `wiki/tests/test_fassung.py` erwartet den
neuen Abbildnamen. Die Gegenproben der drei Werkzeuge: bordbuch vollständig,
www 17 von 17, admin 18 von 18.

## N-99 — Das Bordbuch hatte als einziges Werkzeug keine `/gesundheit`

Beim Schreiben des Vertragstests für die ausgelagerten Werkzeuge
gefunden (`U-03`). Der Vertrag sagt: `/gesundheit` antwortet `ok`,
`/api/version` gibt die Fassung, beide ohne Anmeldung und ohne
Einlassmarke. Wiki, www und admin halten das ein. Das Bordbuch hatte nur
`/api/version` frei; die Gesundheitsprüfung im Dockerfile und `PRUEF_URL`
liefen darüber.

Das funktionierte — aber es war die eine Ausnahme, die man sich merken
muss. Wer ein Werkzeug über `/gesundheit` anspricht (eine Überwachung,
die künftige Admin-Seite), bekam beim Bordbuch eine 401.

### Behoben

`EINLASS_FREI = ("/gesundheit", "/api/version")`, `/gesundheit` antwortet
`ok` als Text wie überall; Dockerfile und `PRUEF_URL` prüfen darüber.
Fassung **2.6.1 → 2.6.2** an allen drei Stellen.

### Probe

| | |
|---|---|
| `bordbuch/tests/alle.sh` | **138** Python-Tests grün (2 neue), Node grün |
| `bordbuch/tests/gegenprobe.sh` | alle gefunden, 1 neue Mutation (Gesundheit wieder hinter der Marke) |
| Abbild 2.6.2 mit echtem Docker, nur `PROLO_EINLASS` gesetzt | `healthy` |

## U-02 — Die Prüfungen von proloWorld hängen nicht mehr an den Werkzeugquellen

Nach dem Umzug liegt in `wiki/`, `bordbuch/` und `www/` nur noch, was dem
Betrieb gehört. Drei Prüfungen hätten das nicht überstanden — und zwei
davon **still**, genau die Falle aus `N-70`:

| Prüfung | hing an | nach dem Umzug |
|---|---|---|
| `grenze-pruefen.sh` | `server.py` mit `PROLO_EINLASS` | drei Werkzeuge fallen aus der Liste, **grün** |
| `schriften-pruefen.sh` | mindestens zwei `*/schriften/` | rot („weniger als zwei") |
| `prolo-befehle-pruefen.py` | Mutationen in `wiki/server.py`, `bordbuch/CHANGELOG.md` | Gegenprobe rot („nicht einbaubar") |

### Was daraus wurde

- **`grenze-pruefen.sh`** erkennt ein eigenes Werkzeug an etwas, das nicht
  von der Prüfung selbst abhängt: `server.py` hier **oder** ein Abbild aus
  `ghcr.io/prolo2408/`. Wer `PROLO_EINLASS` aus einer Compose-Datei nimmt,
  wird rot, statt aus der Liste zu fallen — die erste Fassung dieser
  Änderung hätte genau das nicht getan (69 statt 73 Prüflinien, beim
  Nachzählen bemerkt). Was nur am Code prüfbar ist (Grenze in
  `do_GET`/`do_POST`, Wurzel nicht frei, Gruppen im Label), wird geprüft,
  wo der Code hier liegt — und für die ausgelagerten im Werkzeug selbst
  (`U-03`).
- **`schriften-pruefen.sh`** vergleicht, wenn es etwas zu vergleichen gibt;
  bei einem Werkzeug prüft es nur, dass jede Regel ihre Datei hat.
- **`prolo-befehle-pruefen.py`** findet das Bedienhandbuch in
  `wiki/vorlagen/` oder `doku/`, und seine Mutationen zielen nur noch auf
  Dateien, die in proloWorld bleiben (`admin/server.py`,
  `werkzeuge/ANLEITUNG.md`).

### Ausgeführt

Heute: `grenze-pruefen.sh` **73 ok**, Gegenprobe **17 von 17** (neu: das
Wiki reicht die Marke nicht mehr durch); `prolo-befehle-pruefen.py
--gegenprobe` **8 von 8**; `schriften-pruefen.sh` grün.

Und der Zustand **nach** dem Umzug, simuliert in einer Kopie, in der von
den drei Werkzeugen nur die Betriebsdateien liegen: `grenze-pruefen.sh`
grün mit 61 ok und denselben **4** Werkzeugen (admin, bordbuch, wiki,
www); weggefallen sind genau die 12 Code-Prüfungen, die in den
Werkzeug-Repos weiterlaufen. `schriften`, `dockerfile`, `regeln`,
`sicherung`, `netze`, `geheimnisse` und die Befehlsprüfung: grün.

### Ein eigener Fehler dabei

Der Befehl, der die Simulation baute, hat `prolo-bedienen.html` aus dem
**echten** Arbeitsstand in die Kopie *verschoben* — `mv … || cp …`, und
das `mv` gelang. Bemerkt in `git status` (` D wiki/vorlagen/…`), die Datei
aus der Kopie zurückgeholt, nicht per `git checkout` (`N-34`): 0
Unterschiede zum Git-Stand. Die Regel dazu steht in `TEIL 0` schon — eine
Probe darf nichts im Arbeitsstand bewegen —, und ich habe sie mit einem
Rückfallpfad unterlaufen, der nur im Fehlerfall kopiert.

## U-03 — Was jedes Werkzeug-Repository mitbringt

Damit in `prolo2408/wiki`, `…/bordbuch` und `…/www` ein Claude (oder ein
Mensch) vom ersten Tag an so arbeiten kann wie hier, liegt in jedem der
drei Ordner schon jetzt, was dort gebraucht wird. `git subtree split`
nimmt es mit (`U-04`), und `.github/` landet dabei an der Wurzel — wo
GitHub es liest. Solange die Ordner hier liegen, tut `.github/` darin
nichts.

| Datei | Inhalt |
|---|---|
| `CLAUDE.md` | die Regeln: **der Vertrag mit dem Betrieb** zuerst, dann Arbeitsweise, Oberfläche (§1–§10), Robustheit (§11–§15), Anmeldung, Datentrennung, Benennung, Schützenswertes, Protokolle, Fassung und Migration. Die Abschnittsnummern sind dieselben wie hier — im Code stehen hunderte Verweise wie „§17", und sie sollen stimmen. Neue Befunde bekommen eine eigene Folge (`WK-`, `BB-`, `WW-`). |
| `README.md` | was es ist, wie man testet, lokal startet (ausprobiert: alle drei antworten mit 200) und veröffentlicht |
| `BEFUNDE.md` | leer, mit dem Verweis auf die Narben hier |
| `.github/workflows/abbild.yml` | bei jedem Push: Tests, Gegenprobe, Fassung an drei Stellen, Dockerfile, **Abbild bauen und gesund starten**. Bei einem Tag `v<fassung>`: Tag gegen Code und Herstellerdatei prüfen, eine schon vorhandene Fassung **verweigern** (`§16`), bauen, nach `ghcr.io` schieben, Veröffentlichung mit der Herstellerdatei (ohne `build:`) anhängen |
| `tests/test_vertrag.py` | die 12 Code-Prüfungen, die in proloWorld wegfallen (`U-02`): Grenze in `do_GET` und `do_POST`, freie Pfade genau `/gesundheit` und `/api/version`, `:?` an der Marke, jede geprüfte Gruppe im Label, Abbild und Changelog tragen die Fassung aus dem Code, und die Herstellerdatei enthält nichts, was dem Betrieb gehört (Netz, Speichergrenzen, Ports) |
| `tests/gegenprobe_vertrag.py` | die Zähne dazu, aufgerufen aus `tests/alle.sh` |

### Ausgeführt

| | wiki | bordbuch | www |
|---|---|---|---|
| `tests/alle.sh` | grün (156 Python-Tests) | grün (138) | grün (52) |
| `gegenprobe_vertrag.py` | **7 von 7** | **7 von 7** | **7 von 7** |
| Abbild bauen, nur mit `PROLO_EINLASS` starten | `healthy` | `healthy` | `healthy` |
| `actionlint` (mit shellcheck) auf `abbild.yml` | sauber | sauber | sauber |
| Fassung an drei Stellen, Auszug der Versionshinweise | 1.4.1 | 2.6.2 | 1.1.1 |

Der Vertragstest hat sofort etwas gefunden: das Bordbuch hatte keine
`/gesundheit` — das ist `N-99`, eigens behoben.

`werkzeuge/alle-pruefen.sh --schnell`: alles grün.

Die Regeldateien sind aus der `CLAUDE.md` des Stapels erzeugt (Abschnitte
wörtlich übernommen, Pfade, die im Werkzeug-Repo nicht mehr stimmen,
umgebogen). Ab dem Umzug leben sie eigenständig weiter.

## N-100 — Die Einrichtungsprobe bog den echten `prolo` um — und lief ohne root gar nicht

Zwei Seiten derselben Sache, beide durch die neue Prüfung auf GitHub
(`.github/workflows/pruefen.yml`) ans Licht gekommen.

**Ohne root:** Der erste Lauf auf GitHub war rot — `einrichten-pruefen.sh`
und `neu-pruefen.sh`. `einrichten.sh` und `neu.sh` fragen als Erstes
`id -u` und hören ohne root sofort auf. Hier lief jede Probe bisher als
root, also fiel es nie auf. Ein Prüfer, der nur als root grün wird, prüft
auf dem Rechner des nächsten Menschen nichts.

**Mit root — schlimmer:** Schritt 2 von `prolo einrichten` legt
`/usr/local/bin/prolo` an. Die Probe lief in einem Wegwerfordner, aber
dieser Pfad war fest — also bog jeder Lauf **den echten Verweis** auf den
Wegwerfordner um, und nach dem Aufräumen zeigte er ins Leere. Gemessen:
nach einem Probelauf als root war `prolo` auf dem Prüfrechner weg
(`readlink` zeigte auf ein gelöschtes `/tmp/…`). Auf einem Server, auf dem
jemand die Probe laufen lässt, wäre es genauso.

### Behoben

- `einrichten.sh`: `ZIEL="${PROLO_BIN:-/usr/local/bin/prolo}"` — setzbar
  nur, damit die Probe ihren Verweis in die Kopie legt.
- `einrichten-pruefen.sh` und `neu-pruefen.sh`: ein `id` im eigenen
  `PATH`, das auf `-u` mit `0` antwortet. Geschrieben wird ohnehin nur im
  Wegwerfordner.
- `einrichten-pruefen.sh` prüft die Wirkung, nicht die Absicht: der
  Verweis liegt **in der Kopie** und zeigt auf sie, und der echte
  `/usr/local/bin/prolo` ist nach dem Lauf **derselbe** wie vorher.
- Mutation 12: `ZIEL` wieder fest auf `/usr/local/bin/prolo`. Als root
  stellt die Probe den echten Verweis danach sofort wieder her.

### Ausgeführt

| | als root | ohne root (`pruefer`) |
|---|---|---|
| `einrichten-pruefen.sh` | grün, 30 ok | grün, 30 ok |
| `einrichten-pruefen.sh --gegenprobe` | — | **14 von 14** gefunden |
| `neu-pruefen.sh` | grün | grün, 106 ok |
| `/usr/local/bin/prolo` danach | unverändert (`/opt/stack/werkzeuge/prolo`) | unverändert |

`werkzeuge/alle-pruefen.sh` als `pruefer`: alle Werkzeugtests und alle
Prüfungen des Stapels grün (der Lauf wurde in den Gegenproben durch einen
Neustart des Prüfrechners abgebrochen, nicht durch einen Fehler).

## U-04 — Auslagern und Umstellen als Befehl, nicht als Anleitung

Der Umzug eines Werkzeugs in sein eigenes Repository hat zwei Hälften,
und jede hat eine Stelle, an der man sich still etwas kaputt macht:

- **Auslagern** ohne Geschichte (Dateien kopieren, neu anfangen) verliert
  jede Narbe: `git blame` auf eine seltsame Zeile führt dann auf „erster
  Commit" statt auf `N-41`. Und wer die Betriebsdateien mitnimmt, hat
  zwei Stellen für Netz und Anmeldung, die auseinanderlaufen.
- **Umstellen**, bevor das Abbild veröffentlicht ist, hinterlässt ein
  Werkzeug, das sich weder bauen (Code weg) noch holen (Abbild fehlt)
  lässt — gemerkt beim nächsten `prolo aktualisieren`, also nachts.

Darum zwei Skripte statt einer Befehlsliste (`N-54`):

| | tut | hält an, wenn |
|---|---|---|
| `werkzeuge/auslagern.sh <w> <ziel>` | `git subtree split` (ganze Geschichte), ein Commit entfernt die Betriebsdateien, `push` nach `main`. In proloWorld ändert sich nichts. `--trocken` zeigt die Wurzel und schiebt nichts. | das Ziel nicht leer ist, im Ordner nicht Eingechecktes liegt, eine der Dateien aus `U-03` fehlt, ein Zweig eines früheren Versuchs liegt |
| `werkzeuge/umstellen.sh <w>` | Code, Tests, Schriften weg (`git rm`), `build:` aus der Herstellerdatei, `TYP="image"`, eine `LIESMICH.md`, beim Wiki das Bedienhandbuch nach `doku/` samt Verweis in `CLAUDE.md`. Vorgemerkt, **nicht** eingecheckt. | sich das Abbild nicht holen lässt (`docker manifest inspect`) — dann mit dem Befehl, der es veröffentlicht, und bei „denied" mit dem `docker login` dazu |

Die Anleitung dazu: `werkzeuge/ANLEITUNG.md`, Abschnitt 7.

### Der Prüfstand, und was er zuerst gefunden hat

`werkzeuge/auslagern-pruefen.sh` zieht das Wiki **wirklich** in ein
leeres (lokales) Repository um und stellt danach in einer Kopie von
proloWorld alle drei Werkzeuge um. Zwei seiner eigenen Prüflinien waren
zuerst falsch:

- „ein alter Commit ist wiederzufinden" war rot, **obwohl** der Commit da
  war: `git log | grep -q` unter `pipefail` — `grep` hört beim ersten
  Treffer auf, `git log` bekommt SIGPIPE, die Leitung ist „gescheitert".
  Jetzt wird in eine Variable gelesen. Die Betriebsskripte habe ich auf
  dieselbe Falle durchgesehen: überall schreibt dort ein einzelnes
  `printf`, `awk` oder Python, das seine Ausgabe in einem Stück abgibt —
  kein Fall mit mehreren Schreibvorgängen vor einem `grep -q`.
- „nicht Eingechecktes hält an" war grün aus dem **falschen** Grund: das
  Ziel-Repository gab es im Test gar nicht, also hielt schon `git
  ls-remote` an. Die Mutationsprobe hat es gefunden (die Sperre
  abgeschaltet — und die Prüfung blieb grün). Jetzt mit einem echten
  leeren Ziel, und geprüft wird die Wirkung: das Ziel bleibt leer.

Auf GitHub klont die Prüfung seitdem mit ganzer Geschichte
(`fetch-depth: 0`) — flach geklont gäbe es nichts mitzunehmen.

### Ausgeführt

`werkzeuge/auslagern-pruefen.sh --gegenprobe` (237 s):

| | |
|---|---|
| Auslagern des Wikis | Code an der Wurzel, `CLAUDE.md` und `abbild.yml` dabei, alle 5 Betriebsdateien fehlen dort, 72 Commits am Wiki hier → 79 dort, der älteste (`B-22`) ist dabei, **`tests/alle.sh` läuft im neuen Repository allein grün** |
| Verweigerungen | Ziel mit Inhalt, nicht Eingechecktes (Ziel bleibt leer), Abbild nicht zu holen (nichts vorgemerkt, Meldung nennt `git tag v…`) |
| Umstellen aller drei | `wiki/` enthält danach genau 8 Betriebsdateien, kein `build:`, `TYP="image"`, Handbuch in `doku/`, `CLAUDE.md` zeigt dorthin, Volumes heißen wie vorher (`bordbuch_bordbuch_belege`, `bordbuch_bordbuch_daten`) |
| Stapel nach dem Umzug | `grenze`, `schriften`, `regeln`, `sicherung`, `netze`, `geheimnisse`, `einrichten`, `dockerfile`, `prolo-befehle` grün; `grenze-pruefen` sieht weiter alle vier eigenen Werkzeuge |
| gesamt | **41 ok**, 0 Fehler |
| Mutationsprobe | **6 von 6** gefunden (Betriebsdateien gehen mit, Ziel mit Inhalt wird beschrieben, nicht Eingechecktes hält nicht an, `build:` bleibt, `TYP` bleibt `build`, Abbild wird nicht geprüft) |

`actionlint` auf `pruefen.yml`: sauber.

## A-01 — Das Auftragsbuch: die Admin-Seite darf handeln, ohne an den Socket zu kommen

Der Wunsch: Werkzeuge im Browser starten, anhalten, aktualisieren,
anlegen. Der kürzeste Weg dahin — dem Container der Admin-Seite
schreibenden Zugriff auf den Docker-Socket geben, direkt oder über
`POST: 1` im Vermittler — ist auch der kürzeste Weg zur Übernahme des
ganzen Servers: wer den Socket schreibend hat, startet einen Container mit
`/` eingehängt und ist root. Und eine Webseite ist genau die Stelle, an
der man am ehesten hereinkommt. Portainer, Dockge und Komodo gehen diesen
Weg; für einen Stapel, dessen Regeln an `prolo` hängen (Sperre, Sicherung,
Rückweg), wäre es außerdem ein zweiter Weg an allen Regeln vorbei.

**Darum spricht die Seite nicht mit Docker, sie legt Aufträge ab:**

```
admin/auftraege/eingang/<kennung>.json    schreibt die Seite (nur sie: 0700, uid 10004)
admin/auftraege/erledigt/<kennung>.json   Lage und Ergebnis        (root, 0755 - die Seite liest)
admin/auftraege/erledigt/<kennung>.log    die Ausgabe von prolo
admin/auftraege/erledigt/protokoll.jsonl  wer wann was
```

`werkzeuge/auftrag.py` läuft auf dem Server als root, angestoßen von
systemd (`werkzeuge/systemd/prolo-auftraege.path`, nur `*.json` löst aus),
und führt **nur** aus, was in `ARTEN` steht — über `prolo`, also mit allem,
was `prolo` ohnehin prüft:

| Art | wird zu | Zeitgrenze |
|---|---|---|
| `start`, `neustart`, `stop`, `pruefen` | `prolo <art> <werkzeug>` | 10 min |
| `aktualisieren` | `prolo aktualisieren <werkzeug>` (sichert vorher, rollt zurück) | 60 min |
| `sichern` | `prolo sichern` | 60 min |
| `netz_anlegen` | `prolo netze anlegen <netz>` | 5 min |

Was im Eingang liegt, ist fremde Eingabe (§11), geschrieben von einem
Container, der übernommen sein könnte:

- nur Dateinamen nach `JJJJMMTT-HHMMSS-<8 hex>.json`; kein Symlink
  (`O_NOFOLLOW`), nur eine gewöhnliche Datei, höchstens 256 KiB
- nur bekannte Arten und Felder, jedes gegen sein Muster; der Werkzeugname
  muss ein Ordner mit `docker-compose.yml` sein
- `traefik`, `authentik`, `socket-proxy`, `admin` lassen sich von der
  Seite aus nicht **anhalten** — danach gäbe es keine Seite mehr, von der
  aus man sie wieder startet. Neu starten geht.
- keine Shell, eine feste Umgebung (nichts vom Aufrufer), eigene
  Prozessgruppe: nach der Zeitgrenze wird die ganze Gruppe beendet, nicht
  nur `prolo`
- Ausgabe höchstens 1 MiB, der Rest wird gelesen und verworfen
- was sich nicht verarbeiten lässt, wandert nach `verworfen/` und ins
  Protokoll — liegen bleiben darf nichts, sonst stieße systemd den Dienst
  in einer Schleife an; ein Name, der zweimal auftaucht, beendet den Lauf
  statt ihn kreisen zu lassen
- eine Sperre (`flock`): zwei Läufe gleichzeitig gibt es nicht; was bei
  einem Absturz „läuft" blieb, heißt beim nächsten Lauf „abgebrochen"

`prolo einrichten` legt die Ordner mit den richtigen Besitzern an und
schaltet den Wächter ein (Schritt 6c) — beides erst nach Nachsehen, beim
zweiten Lauf passiert nichts. Ohne systemd sagt es, wie man von Hand
abarbeitet.

Die Seite selbst kommt in `A-02`; hier steht nur, was sie benutzen wird.

### Ausgeführt

| | |
|---|---|
| `werkzeuge/auftrag-pruefen.sh` | **49 ok**: Normalfall (genau `start wiki`, Lage, Ausgabe, Protokoll, 0644), Fehlschlag mit Rückgabe, 13 Ablehnungen (unbekannte Art, `../traefik`, `./wiki`, nicht vorhanden, Großbuchstaben, `stop traefik`, `stop admin`, Feld zu viel, Liste statt Text, Feld fehlt, `netz;reboot`, Zeilenumbruch in `wer`) — **keine** davon erreicht `prolo`; 6 verworfene Dateien (Symlink, 300 KB, fremder Name, kein JSON, kein Objekt, Ordner), das Ziel des Symlinks unberührt; doppelte Kennung; halbe Datei frisch/alt; Zeitgrenze samt Kind; 1-MiB-Grenze; „abgebrochen"; Sperre; `ADMIN_UID` = Nutzer in `admin/Dockerfile` |
| `--gegenprobe` | **12 von 12** (Symlink gefolgt, Zugang anhaltbar, jeder Name, fremde Felder, nur `prolo` beendet, Ausgabe unbegrenzt, „läuft" bleibt, Verworfenes bleibt, keine Größengrenze, Umgebung durchgereicht, keine Sperre, Kennung überschrieben) |
| `werkzeuge/einrichten-pruefen.sh` | **34 ok** (vorher 30): Ordner 0700/0755, Einheiten mit echtem Pfad statt `@STACK@`, Wächter eingeschaltet, zweiter Lauf tut nichts, `--trocken` schreibt keine Einheit |
| `einrichten-pruefen.sh --gegenprobe` (als Nicht-root) | **17 von 17** — davon 3 neu: Auftragsbuch nicht angelegt, Einheiten mit Platzhalter, Wächter nie eingeschaltet |
| `auslagern-pruefen.sh` | grün, 41 ok — nachdem er den **ganzen** Ordner `werkzeuge/` in seinen Klon kopiert: vorher nur die obersten Dateien, und `systemd/` fehlte dort |
| `alle-pruefen.sh` als Nicht-root | alle Werkzeugtests, alle Stapelprüfungen und alle Gegenproben grün bis auf `auslagern-pruefen.sh` (eben dieser Fehler, im alten Stand der Kopie) |

Zwei Fallen im eigenen Prüfstand, beide beim ersten Lauf aufgefallen: der
Zähler für die Kennungen lief in `$(...)` — jede Kennung war dieselbe, und
fast alles wurde als Doppel verworfen; und ein beendetes Kind ohne Eltern
bleibt in diesem Container als Zombie stehen, `kill -0` hielt es für
lebendig. Gemessen wird jetzt über eine Zählerdatei und über den
Prozesszustand.
