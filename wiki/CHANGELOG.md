# Wiki — Aenderungen

## Wichtig zum Einspielen

**Eingespielte Seiten bringen eigenen Code mit. Spiele nur Seiten ein, deren
Herkunft du kennst.** Das ist Absicht und der Kern der Architektur: die Seiten
sind eigenstaendig und haben eigenes Verhalten. Es heisst aber auch, dass eine
Seite aus fremder Quelle - von einem Kollegen, aus einem Export, von einem
Sprachmodell erzeugt - Code ist, den du auf deinem Server laufen laesst.

Zwei Schichten schuetzen dabei (beide aus der Pruefung vom 14.09.2026):

- Die Seiten laufen in einem **abgeschotteten Rahmen mit eigenem, opakem
  Origin**. Sie kommen nicht an die Wiki-Schnittstelle, nicht an Cookies,
  nicht an die Anmeldung und nicht an die Huelle. Vorher war eine
  eingespielte Seite gleichbedeutend mit Code-Ausfuehrung auf
  `wiki.prolo.me` (B-03 Teil 4).
- Die Pruefung beim Einspielen zeigt unter **"Was diese Seite mitbringt"**,
  welches Verhalten im Code steckt: Skriptbloecke, Abrufe nach draussen,
  Zugriffe auf Cookies oder Speicher, iframes. Das sind Hinweise, keine
  Fehler - aber sie stehen vor dem "Uebernehmen"-Knopf, nicht dahinter
  (B-07).

## 2026-09-14 — Fassung 0.1

Erstes Grundgeruest.

- Shell mit Themenbaum, Suche, Seitenanzeige im iframe und Verwaltung
- Anmeldung ausschliesslich ueber die Authentik-Kopfzeilen, ohne Gastzugang
- Freigabe je Seite und je Themenzweig, wirkt auch auf Baum und Suchtreffer
- Suche: FTS5 mit Praefix- und Teilwortindex, Wortvorschlag bei Tippfehlern,
  Treffer auf Abschnittsebene mit Sprung zum Anker
- Import prueft die Datei gegen Regelblatt und Betriebsregeln, legt eine
  Vorschau an und schreibt erst nach Bestaetigung
- Eingebettete Base64-Bloecke ueber 200 kB werden zu Anhaengen; PDF-Anhaenge
  werden seitenweise durchsuchbar
- Jede Uebernahme legt die bisherige Fassung ab, Ruecksprung per Klick
