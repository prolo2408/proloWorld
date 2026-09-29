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
