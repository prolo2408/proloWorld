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

## Was daraus für die Abnahme folgt

`N-01` und `N-02` sind offen. Beide sind klein, beide sind keine
Sicherheitslücken — aber sie gehören in dieselbe Liste wie alles andere,
statt in einer Commit-Nachricht zu verschwinden.
