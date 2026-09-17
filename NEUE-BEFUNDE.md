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
überschrieben, und das Protokoll sagt es (Regelblatt §15).

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
**Gefunden bei:** dem Bedienungsdurchgang, Punkt 12 aus Regelblatt §14b
(„ganz falsche Eingabe")

Regelblatt §11 fragt ausdrücklich: *„Text auf sinnvolle Länge begrenzt?"* Für
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
