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

Mit B-30 sind die drei Token ins Regelblatt aufgenommen worden, weil das
Bordbuch sie sinnvoll ergänzt hatte. Das Wiki definiert sie nicht — geprüft:
alle drei fehlen im Tokenblock.

Das ist kein rein theoretischer Punkt:

- Das Wiki hat **zerstörende Aktionen** (Seite löschen, Fassung
  zurücksetzen). Ohne `--danger` sehen sie aus wie gewöhnliche Knöpfe oder
  wie eine Warnung — Regelblatt §2 unterscheidet beides bewusst.
- Es stehen **vier hartkodierte `#fff`** in der Datei. Regelblatt §1 erlaubt
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
dem Regelblatt selbst. Löschen und Zurücksetzen tragen `gefahr` und färben sich
im Hover auf `--danger` — dieselbe Kette wie `.danger` im Bordbuch.

Eine Abweichung von der ursprünglichen Notiz: `--overlay` hat im Wiki **keine
Fundstelle**. Es gibt dort keinen eigenen Dialog, gefragt wird über `confirm()`.
Das Token ist trotzdem definiert, weil genau das sein im Regelblatt genannter
Zweck ist — damit der nächste Dialog nicht sein eigenes `rgba(0,0,0,.5)`
erfindet. `--danger-soft` und `--on-overlay` sind **nicht** übernommen worden:
die sind Ergänzungen des Bordbuchs, stehen nicht im Regelblatt und hätten hier
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
Inhalt ist sie eine stille Vorgabe im Sinne von Regelblatt §11 — nur an einer
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
**Datei:** Prüfbericht, B-49, und `prolo-betriebsregeln.md` §11
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
bereits verfolgte Dateien.** Eine vollständige Pflichtliste nach Betriebsregeln
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
Betriebsregeln als Grenze benannt.

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

**Vor dem Berichtigen sichern** (Regelblatt 15) — der Schalter sagt es selbst
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

## Was daraus für die Abnahme folgt

`N-01` bis `N-05` sind behoben. `N-05` ist der einzige, der nach außen
sichtbar war — und der einzige, den keine Prüfung hier gefunden hätte,
weil er erst mit echten Dateirechten auf einem echten Server entsteht.

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
