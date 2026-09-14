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

Seiten mit umgeschalteten Bereichen — so wie deine Netzwerk-Seite, wo
alle Abschnitte `display:none` sind — müssen in `springen()` zusätzlich
den richtigen Bereich öffnen, bevor sie scrollen.

## 3. Tokens und Zustandsblock

Farben nur über die Tokens aus Regelblatt Abschnitt 2, dazu der
Pflichtblock aus 8.1 (`focus-visible`, `prefers-reduced-motion`). Der
Import prüft beides und meldet, was fehlt.

---

# Einspielen

Verwaltung → Datei hineinziehen. Was dann passiert:

1. **Geprüft.** Fehler verhindern die Übernahme und stehen im Klartext da:
   fehlender Meta-Block, doppelte Anker, externe Verweise. Hinweise
   verhindern nichts, werden aber an der Seite vermerkt.
2. **Anhänge ausgelagert.** Base64-Blöcke über 200 kB werden Dateien. Bei
   PDFs wird zusätzlich der Text seitenweise indexiert — ein Suchtreffer
   nennt dann die Seitenzahl im Dokument.
3. **Vorschau.** Ansehen, bevor es zählt.
4. **Übernehmen.** Die bisherige Fassung wandert ins Archiv, Rücksprung
   per Klick.

Gleiche `slug` noch einmal einspielen heißt: Seite ersetzen. Neue `slug`
heißt: neue Seite. Mehr Regeln gibt es nicht.

## Was noch fehlt

- Der Skill, mit dem Claude Seiten nach diesem Schema erzeugt. Bis dahin
  reicht es, `test-seite.html` und diesen Abschnitt mitzugeben.
- Die Netzwerk-Seite selbst: Tokens, Zustandsblock und das Nachladen des
  Kompendiums über `data-wiki-anhang` statt aus dem eingebetteten Block.
