# 0.1.0

Erste Fassung. Lesende Uebersicht ueber den Stack.

- Uebersicht: was laeuft, wie viele Routen, und was jemand ansehen sollte
- Werkzeuge: Container, Abbild, Zustand, Netz, Hostname, Schutz, offene Ports
- Netze: welche es gibt, welche intern sind, wer drin haengt
- Einstellungen: Darstellung je Nutzer in der Datenbank, Konto, Abmelden

Liest ausschliesslich ueber den Vermittler vor dem Docker-Socket
(`/containers/json`, `/networks`). Kein Zugriff auf `/opt/stack`, keine
schreibenden Aufrufe. Hinter Authentik **und** hinter der Gruppe `admin`.
