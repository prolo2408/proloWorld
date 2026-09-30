# 0.2.1

- Am Handy keine Schrift mehr unter 12 px (§3): Tabellenkoepfe, Marker,
  Beschriftungen und Unterzeilen waren dort 10-11 px (N-102).

# 0.2.0

- **Bedienen** (A-02): Starten, Neu starten, Anhalten, Pruefen,
  Aktualisieren je Werkzeug, "Jetzt sichern", Netze anlegen. Die Seite tut
  es nicht selbst - sie legt einen Auftrag ins Auftragsbuch, und auf dem
  Server fuehrt `prolo` ihn aus (A-01), mit Startsperre, Sicherung und
  Rueckweg. Schreibenden Zugriff auf Docker hat die Seite weiterhin nicht.
- Neue Gruppe `admin-betrieb`: wer nur `admin` hat, sieht, bedient aber
  nicht und liest keine Protokolle.
- Jedes Werkzeug hat eine eigene Seite: Bedienen, Dienste, was auf dem
  Server liegt (Art, Netze, Volumes, Sicherung), das Protokoll der
  Container, die letzten Auftraege.
- Angehaltene Werkzeuge verschwinden nicht mehr: die Liste kommt aus
  Docker UND aus dem Bestand der Werkzeugordner.
- Auftraege mit Stand und Ausgabe, die waechst, solange er laeuft. Ein
  Auftrag, der schon offen ist, wird nicht ein zweites Mal abgelegt.
- Anhalten fragt nach; Traefik, Authentik, den Vermittler und diese Seite
  selbst kann man von hier aus nicht anhalten (nur neu starten).

# 0.1.2

- Schutz wird JE ROUTER gelesen, nicht je Dienst (N-84). Ein
  `authentik@file` an einem Router machte den ganzen Dienst "geschuetzt" -
  ein zweiter Router ohne Anmeldung daneben fiel nicht auf. Jetzt steht er
  als OFFEN da, mit seinem Namen. Ein als oeffentlich erklaerter Router
  (`prolo.oeffentlich=<router>`) zeigt sich als "oeffentlich", auch wenn
  die anderen hinter Authentik liegen - bei www stand vorher "Authentik",
  obwohl die Startseite mit Absicht offen ist.

# 0.1.1

- Eine einzige abgebrochene Verbindung beendete den ganzen Dienst (N-82).
  `main()` setzte SIGPIPE auf die Voreinstellung zurueck - richtig fuer ein
  Kommandozeilenwerkzeug, falsch fuer einen Dienst. Jetzt bleibt es
  ignoriert, und ein Schreibfehler in eine geschlossene Leitung wird im
  betroffenen Faden still verworfen statt mit einer Fehlerseite ein zweites
  Mal hineinzuschreiben.

# 0.1.0

Erste Fassung. Lesende Uebersicht ueber den Stack.

- Uebersicht: was laeuft, wie viele Routen, und was jemand ansehen sollte
- Werkzeuge: Container, Abbild, Zustand, Netz, Hostname, Schutz, offene Ports
- Netze: welche es gibt, welche intern sind, wer drin haengt
- Einstellungen: Darstellung je Nutzer in der Datenbank, Konto, Abmelden

Liest ausschliesslich ueber den Vermittler vor dem Docker-Socket
(`/containers/json`, `/networks`). Kein Zugriff auf `/opt/stack`, keine
schreibenden Aufrufe. Hinter Authentik **und** hinter der Gruppe `admin`.
