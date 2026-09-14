# Wiki — Aenderungen

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
