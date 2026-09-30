# 0.4.1

- Die Seite "Werkzeug anlegen" schrieb das Namensmuster mit `'\-'` in einen
  gewoehnlichen Python-Text - eine ungueltige Escape-Folge. Ab Python 3.12
  meldete das bei jedem Start eine `SyntaxWarning` im Protokoll, eine
  kuenftige Fassung macht einen Fehler daraus (N-112). Jetzt `'\\-'`; das
  ausgelieferte HTML ist Byte fuer Byte dasselbe.

# 0.4.0

- **Firewall** (F-02): eine eigene Seite unter `/firewall` - aktive Sperren
  mit Grund und Restdauer, Meldungen der letzten sieben Tage, die
  Freigabeliste, die eigenen Regeln aus `crowdsec/regeln/`, was CrowdSec
  liest, und ob der Bouncer auf dem Server abholt. Sperren, Aufheben,
  Freigeben und Entfernen legen Auftraege ab (`firewall_*`), ausgefuehrt von
  `prolo firewall` auf dem Server - die Seite spricht nie mit CrowdSec.
- Die eigene Adresse (letzter Eintrag in `X-Forwarded-For`, §11) laesst
  sich nicht sperren, auch nicht als Teil eines Netzes; freigeben geht mit
  einem Knopf.
- Die Lage schreibt `werkzeuge/auftrag.py` alle fuenf Minuten und nach
  jedem Auftrag nach `auftraege/erledigt/firewall.json`. Was dort fehlt,
  alt oder kaputt ist, steht unter "Zu klaeren" - mit dem Weg daraus.
- Uebersicht: eine Kachel "Firewall"; am Handy ist sie der Weg dorthin.

# 0.3.0

- **Werkzeug anlegen aus einer Compose-Datei** (A-03): die Datei des
  Herstellers einwerfen, pruefen lassen (Dienste, Ports, Volumes,
  Variablen - und Gefahren wie privileged, Host-Netz, Docker-Socket, Pfade
  vom Server), mit Dienst, Port, Netz und Anmeldung bestaetigen. Angelegt
  wird ueber `prolo neu --compose`: Herstellerdatei unveraendert, unsere
  Zutat daneben, ohne die Ports des Herstellers, alle Volumes in der
  Sicherung, geheime Variablen gewuerfelt. Mit Gefahren wird aus der Seite
  nichts angelegt.
- "Konfiguration uebernehmen" fuer laufende Werkzeuge (`prolo start`):
  legt neu an, was sich geaendert hat - z. B. ein neues Netz bei Traefik.
- Formulare: Felder ohne Luecken, lange Pfade brechen um.

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
