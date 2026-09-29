#!/usr/bin/env bash
# werkzeuge/grenze-pruefen.sh
#
# Steht der Eingang noch? (N-44 Vertrauensgrenze, N-46 Ratenbremse)
#
# Der Anlass, gemessen: eine Anfrage mit "X-Authentik-Groups: wiki-admin"
# bekam vom Wiki 200 und die Verwaltungsdaten, dieselbe ohne Gruppe 403. Die
# Rechtepruefung war also richtig - das Vertrauen in die Kopfzeile nicht. Von
# aussen ist das kein Weg, weil Traefik die Kopfzeilen am Eingang loescht;
# aus dem Docker-Netz heraus schon, denn dort erreicht jeder Container Port
# 8080 eines anderen direkt.
#
# Die Korrektur besteht aus Teilen an fuenf Stellen. Faellt EINE davon weg,
# ist das Loch wieder da - und zwar lautlos, weil alles weiter funktioniert.
# Genau das prueft dieses Skript.
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$(dirname "$HIER")"

python3 - "$STACK" <<'PY'
import ast, os, re, sys
stack = sys.argv[1]
fehler = 0

def sag(ok, text, zusatz=""):
    global fehler
    print(("ok     " if ok else "FEHLER ") + text + (("  -> " + zusatz) if zusatz and not ok else ""))
    if not ok:
        fehler += 1

def grenze_erreichbar(code, einstieg, tiefe=2):
    """Fuehrt dieser Einstieg an einlass_pruefen vorbei - direkt oder ueber
    einen Helfer?

    Gelesen wird der Syntaxbaum, nicht der Text: welche Methoden ruft der
    Einstieg auf, und ruft eine davon die Grenze? Zwei Ebenen reichen fuer
    das Muster "do_GET -> _lauf -> einlass_pruefen"; tiefer verschachtelt
    waere es ohnehin nicht mehr nachvollziehbar.
    """
    try:
        baum = ast.parse(code)
    except SyntaxError:
        return False
    koerper = {}
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef):
            koerper[knoten.name] = knoten

    def rufe(name):
        k = koerper.get(name)
        if k is None:
            return set()
        aus = set()
        for x in ast.walk(k):
            if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute):
                aus.add(x.func.attr)
            elif isinstance(x, ast.Call) and isinstance(x.func, ast.Name):
                aus.add(x.func.id)
        return aus

    offen, gesehen = {einstieg}, set()
    for _ in range(tiefe + 1):
        if "einlass_pruefen" in offen:
            return True
        naechste = set()
        for n in offen - gesehen:
            gesehen.add(n)
            naechste |= rufe(n)
        offen = naechste
    return "einlass_pruefen" in offen


def freie_pfade(code):
    """Die Freiliste eines Werkzeugs als Pfade, egal wie sie geschrieben ist.

    Das Wiki zerlegt Pfade in Teile (["api", "version"]), das Bordbuch
    vergleicht ganze Pfade ("/api/version"). Beides ist in seinem Werkzeug
    richtig - ein Pruefer, der nur eine Form kennt, meldet darum einen
    Fehler, den es nicht gibt. Genau das ist hier passiert.
    """
    m = re.search(r"EINLASS_FREI = (\(.*?\))\n", code, re.S)
    if not m:
        return set()
    try:
        werte = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return set()
    aus = set()
    for w in werte:
        aus.add(w if isinstance(w, str) else "/" + "/".join(w))
    return aus


def lies(*teile):
    p = os.path.join(stack, *teile)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()

# --- 1. Die Kette am Eingang -------------------------------------------
statisch = lies("traefik", "traefik.yml") or ""
m = re.search(r"^      middlewares:\n((?:\s*#.*\n|\s*- .*\n)+)", statisch, re.M)
kette = re.findall(r"^\s*- (\S+)", m.group(1), re.M) if m else []
sag("vertrauensgrenze@file" in kette,
    "traefik.yml: vertrauensgrenze haengt am Eingang",
    "ohne sie reicht JEDER Router durch, was der Client schickt")
sag("einlass@file" in kette,
    "traefik.yml: einlass haengt am Eingang",
    "ohne sie bekommt kein Werkzeug die Marke und alles antwortet 401")
if "vertrauensgrenze@file" in kette and "einlass@file" in kette:
    sag(kette.index("vertrauensgrenze@file") < kette.index("einlass@file"),
        "traefik.yml: erst loeschen, dann setzen",
        "andersherum loescht die Grenze die eigene Marke wieder")

# --- 1b. Die Ratenbremse (N-46) -----------------------------------------
sag("ratenbremse@file" in kette, "traefik.yml: die Ratenbremse haengt am Eingang",
    "ohne sie kann eine einzelne Quelle in Schleife anklopfen")
sag("gleichzeitig@file" in kette,
    "traefik.yml: die Grenze fuer gleichzeitige Anfragen haengt am Eingang")
if "ratenbremse@file" in kette and "vertrauensgrenze@file" in kette:
    sag(kette.index("ratenbremse@file") < kette.index("vertrauensgrenze@file"),
        "traefik.yml: erst bremsen, dann alles andere",
        "wer zu schnell klopft, soll gar nicht erst bis zur Anmeldung kommen")
sicher_roh = lies("traefik", "dynamic", "sicherheit.yml") or ""
werte = dict(re.findall(r"^\s*(average|burst|amount):\s*(\d+)\s*$",
                        sicher_roh, re.M))
# Von Hand gerechnet: ein Seitenaufruf des Wikis sind etwa 15 Anfragen mit
# Schriften und Schnittstelle. Unter 20 je Sekunde wuerde die Bremse einen
# Menschen treffen - gemessen wurden bei 24/s null Abweisungen.
sag(int(werte.get("average", 0)) >= 20,
    "die Bremse trifft keinen Menschen (average=%s)" % werte.get("average"),
    "ein Seitenaufruf sind rund 15 Anfragen")
sag(0 < int(werte.get("average", 0)) <= 200,
    "die Bremse bremst ueberhaupt (average=%s)" % werte.get("average"),
    "ein zu hoher Wert ist dasselbe wie keine Bremse")
sag(int(werte.get("amount", 0)) > 0,
    "gleichzeitige Anfragen sind begrenzt (amount=%s)" % werte.get("amount"))

# --- 1c. ... und trifft auch keine Anwendung, die sich nachlaedt (N-79) --
#
# Die drei Zeilen darueber waren am Wiki bemessen: eine Seite, die fertig
# vom Server kommt. Eine Anwendung, die ihre Oberflaeche erst im Browser
# zusammenbaut, holt ein paar hundert Teile auf einmal - und faellt ein
# einziges davon weg, bleibt die Seite schwarz.
#
# Gemessen mit einem echten Chromium gegen einen Nachbau beider
# Middlewares: bei burst=150 wurden von einer Seite mit 300 Teilen 28
# Anfragen abgewiesen und die Oberflaeche kam nicht; bei burst=700 kamen
# 200, 300, 400 und 600 Teile ohne eine einzige Abweisung durch. In der
# Spitze feuert ein Browser dabei 134 Anfragen in einer Sekunde.
sag(int(werte.get("burst", 0)) >= 600,
    "der Vorrat traegt einen ganzen Seitenaufbau (burst=%s)"
    % werte.get("burst"),
    "gemessen: 600 Teile sind 602 Anfragen am Stueck, 150 reichen dafuer nicht")
sag(int(werte.get("amount", 0)) >= 150,
    "gleichzeitige Anfragen eines Browsers passen durch (amount=%s)"
    % werte.get("amount"),
    "vier abgewiesene von 300 genuegen, damit die Oberflaeche schwarz bleibt")

# Und gemessen wird je Quelladresse, weil es dasteht - nicht, weil es die
# Vorgabe ist. Dieselbe Regel wie bei traefik.docker.network seit N-45.
for name, mitte in (("ratenbremse", "rateLimit"),
                    ("gleichzeitig", "inFlightReq")):
    block = re.search(r"^    %s:\n(.*?)(?=^    \S|^\S)" % name,
                      sicher_roh, re.S | re.M)
    inhalt = block.group(1) if block else ""
    sag("sourceCriterion" in inhalt and "ipStrategy" in inhalt,
        "%s misst ausdruecklich je Quelladresse" % name,
        "ohne sourceCriterion gilt die Vorgabe von Traefik, und die steht "
        "nirgends bei uns")

# --- 2. Jede Kopfzeile, die Authentik setzen darf, wird vorher geleert ---
auth = lies("traefik", "dynamic", "authentik.yml") or ""
gesetzt = [h.strip().lower() for h in
           re.findall(r"^\s*- (X-[Aa]uthentik-\S+)\s*$", auth, re.M)]
sicher = lies("traefik", "dynamic", "sicherheit.yml") or ""
block = re.search(r"    vertrauensgrenze:\n(.*?)(?=\n    \S|\ntls:)", sicher, re.S)
geleert = ([h.strip().lower() for h in
            re.findall(r'^\s*(X-\S+):\s*""\s*$', block.group(1), re.M)]
           if block else [])
sag(bool(gesetzt), "authentik.yml nennt Kopfzeilen (%d)" % len(gesetzt),
    "ohne sie prueft dieser Abgleich nichts")
fehlt = [h for h in gesetzt if h not in geleert]
sag(not fehlt,
    "sicherheit.yml leert alle %d Kopfzeilen aus authentik.yml" % len(gesetzt),
    "nicht geleert: " + ", ".join(fehlt))
sag("x-prolo-einlass" in geleert,
    "sicherheit.yml leert auch X-Prolo-Einlass",
    "sonst bestimmt der Client die Marke, falls einlass.yml einmal fehlt")

# --- 3. Das Geheimnis liegt richtig ------------------------------------
sag(lies("traefik", "dynamic", "einlass.yml.beispiel") is not None,
    "einlass.yml.beispiel liegt im Repository")
ign = lies(".gitignore") or ""
sag("traefik/dynamic/einlass.yml" in ign,
    ".gitignore haelt einlass.yml heraus",
    "das ist ein Geheimnis wie eine .env (CLAUDE.md §21)")

# Der Platzhalter darf in keiner versionierten Datei als echter Wert stehen.
# Zusammengesetzt, nicht ausgeschrieben: ein Pruefer, der den gesuchten
# Text im Klartext enthaelt, findet sich selbst (wie in N-36 und N-39).
platzhalter = "HIER-EINEN-" + "GEWUERFELTEN-WERT-" + "EINTRAGEN"
treffer = []
for wurzel, ordner, dateien in os.walk(stack):
    ordner[:] = [o for o in ordner if o not in (".git", "__pycache__", "node_modules")]
    for d in dateien:
        p = os.path.join(wurzel, d)
        if p.endswith(".beispiel"):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                if platzhalter in f.read():
                    treffer.append(os.path.relpath(p, stack))
        except (UnicodeDecodeError, OSError):
            pass
sag(not treffer, "der Platzhalter steht nur in der Beispieldatei",
    ", ".join(treffer))

# --- 4. Jedes Werkzeug, das die Marke prueft, bekommt sie auch ----------
# Die Werkzeuge finden sich selbst. Eine feste Liste haette das naechste
# uebersehen - genau das ist beim Anlegen von www/ beinahe passiert.
werkzeuge = sorted(
    o for o in os.listdir(stack)
    if os.path.exists(os.path.join(stack, o, "server.py"))
    and "PROLO_EINLASS" in (lies(o, "server.py") or ""))
sag(len(werkzeuge) >= 2,
    "Werkzeuge mit eigener Vertrauensgrenze gefunden (%d: %s)"
    % (len(werkzeuge), ", ".join(werkzeuge)),
    "ohne sie prueft der Rest dieses Skripts nichts")
for werkzeug in werkzeuge:
    code = lies(werkzeug, "server.py") or ""
    compose = lies(werkzeug, "docker-compose.yml") or ""
    sag("PROLO_EINLASS" in compose,
        "%s/docker-compose.yml reicht PROLO_EINLASS durch" % werkzeug)
    sag("${PROLO_EINLASS:?" in compose,
        "%s: fehlender Wert bricht schon beim Hochfahren ab" % werkzeug,
        'ohne ":?" startet der Container und weist dann jede Anfrage ab')
    sag("PROLO_EINLASS" in (lies(werkzeug, ".env.beispiel") or ""),
        "%s/.env.beispiel nennt PROLO_EINLASS" % werkzeug)
    # Beide Einstiege muessen an der Grenze vorbei. Gezaehlt wird NICHT,
    # wie oft der Aufruf dasteht: ein Werkzeug darf ihn aus einem
    # gemeinsamen Helfer rufen, den do_GET und do_POST beide benutzen.
    # Genau so macht es www, und eine Zaehlung haette das als Fehler
    # gemeldet, den es nicht gibt. Gesucht wird die ERREICHBARKEIT, mit
    # ast statt mit einem regulaeren Ausdruck.
    for einstieg in ("do_GET", "do_POST"):
        sag(grenze_erreichbar(code, einstieg),
            "%s: %s fuehrt an der Vertrauensgrenze vorbei" % (werkzeug, einstieg),
            "eine Haelfte offen ist nicht halb sicher")
    # Der freie Pfad darf nicht die Wurzel sein.
    frei = re.search(r"EINLASS_FREI = \((.*?)\)", code, re.S)
    sag(frei is not None and '"/"' not in frei.group(1)
        and "[]" not in frei.group(1),
        "%s: die Wurzel steht nicht auf der Freiliste" % werkzeug)

# --- 4b. Wer ohne Authentik laeuft, hat es ERKLAERT (§17a, N-59) -------
#
# Ein fehlendes "middlewares=authentik@file" sieht genauso aus, ob es ein
# Entschluss war oder ein Versehen. Darum muss ein Werkzeug, das ohne
# Authentik laufen soll, das Label "prolo.anmeldung=eigene" tragen - und
# eigener Code darf das NIE. Sonst haetten wir die Anmeldung selbst
# gebaut, und genau das tun wir nicht (§17).
# ACHTUNG, hier NICHT "werkzeuge" nehmen: das sind nur die mit eigenem
# server.py. n8n und authentik stehen nicht darin - also genau die
# Fremdwerkzeuge, um die es hier geht. Die erste Fassung dieser Pruefung
# haette das Werkzeug uebersehen, fuer das sie geschrieben wurde. Derselbe
# Fehler wie N-56: der Umfang einer Pruefung ist selbst eine Annahme.
alle_werkzeuge = sorted(
    o for o in os.listdir(stack)
    if os.path.isfile(os.path.join(stack, o, "docker-compose.yml")))
# UND BEIDE Compose-Dateien lesen (N-61). Seit ein Fremdwerkzeug die
# Datei des Herstellers unveraendert behaelt, stehen Netz, Route und
# Anmeldung nebenan in docker-compose.override.yml. Beim Umstellen von n8n
# ist genau das passiert: der Pruefer fand in der Herstellerdatei kein
# "traefik.enable=true" mehr, sprang ueber n8n hinweg - und meldete
# weiterhin "alles gruen". Er wurde LEISER, nicht richtiger.
def compose_alles(w):
    return "\n".join(lies(w, d) or ""
                     for d in ("docker-compose.yml", "docker-compose.override.yml"))

geprueft = []
for werkzeug in alle_werkzeuge:
    compose = compose_alles(werkzeug)
    if "traefik.enable=true" not in compose:
        continue
    geprueft.append(werkzeug)
    # Router, die auf dem oeffentlichen Eingang haengen.
    router = set(re.findall(r"traefik\.http\.routers\.([A-Za-z0-9_-]+)\.rule", compose))
    if not router:
        continue
    eigene = "prolo.anmeldung=eigene" in compose
    # Einzelne Router duerfen mit ABSICHT offen sein (www: Startseite und
    # Zugangslinks). Auch das wird erklaert, nicht stillschweigend - ein
    # fehlendes "middlewares=" sieht sonst genauso aus wie ein vergessenes.
    offen = set()
    for m in re.finditer(r"prolo\.oeffentlich=([A-Za-z0-9_,-]+)", compose):
        offen |= {x for x in m.group(1).split(",") if x}
    sag(not (offen - router),
        "%s: jeder als offen erklaerte Router gibt es auch" % werkzeug,
        "erklaert, aber nicht vorhanden: %s" % ", ".join(sorted(offen - router)))
    ohne = [r for r in sorted(router)
            if r not in offen
            and not re.search(r"traefik\.http\.routers\.%s\.middlewares=[^\"']*authentik@file"
                              % re.escape(r), compose)]
    if eigene:
        sag(not os.path.isfile(os.path.join(stack, werkzeug, "Dockerfile")),
            "%s: eigener Code setzt NICHT 'prolo.anmeldung=eigene'" % werkzeug,
            "eigener Code baut keine eigene Anmeldung (§17) - das ist kein Grenzfall")
        hinweis = lies(werkzeug, "sicherung.conf") or ""
        sag("EIGENE ANMELDUNG" in hinweis,
            "%s: der HINWEIS der sicherung.conf sagt es auch" % werkzeug,
            "dort sieht ein Betreiber nach, nicht in den Labels")
        sag("netz-%s" % werkzeug in compose,
            "%s: laeuft im eigenen Netz" % werkzeug,
            "ohne Anmeldung ist das Netz die einzige Trennung")
    else:
        sag(not ohne,
            "%s: jeder Router ist geschuetzt oder erklaert" % werkzeug,
            "ohne authentik@file, ohne 'prolo.anmeldung=eigene' und ohne "
            "'prolo.oeffentlich=' ist offen, ob das ein Entschluss war: %s"
            % ", ".join(ohne))

# Und jetzt die WIRKUNG, nicht die Ankuendigung: wurde wirklich ein
# Fremdwerkzeug angesehen? Eine erste Fassung verglich nur die Laenge der
# beiden Listen - und blieb gruen, als die Schleife danach wieder ueber
# die kurze lief. Eine Mutationsprobe hat das gezeigt (N-38, N-59).
fremde = [w for w in geprueft
          if not os.path.exists(os.path.join(stack, w, "server.py"))]
sag(fremde != [],
    "angesehen wurde auch mindestens ein Fremdwerkzeug (%s)"
    % (", ".join(fremde) or "keins"),
    "genau die fallen sonst durch - um sie geht es bei §17a")

# "Mindestens eins" war zu wenig. Als n8n aus der Schleife fiel, blieb
# authentik uebrig und diese Zeile gruen - der Pruefer sah die Haelfte und
# sagte es nicht. Jetzt wird gegen eine Liste gemessen, die OHNE den
# Filter der Schleife entsteht: jedes Werkzeug, das irgendwo in seinen
# Compose-Dateien einen Router hat, MUSS angesehen worden sein.
mit_router = {w for w in alle_werkzeuge
              if re.search(r"traefik\.http\.routers\.[A-Za-z0-9_-]+\.rule",
                           compose_alles(w))}
uebersehen = sorted(mit_router - set(geprueft))
sag(not uebersehen,
    "kein Werkzeug mit Router blieb ungeprueft (%d angesehen)" % len(geprueft),
    "uebersehen: %s" % ", ".join(uebersehen))

# --- 4a. Jede Gruppe, die ein Werkzeug prueft, nennt es auch (N-95) ----
# "prolo einrichten" liest die Gruppen aus dem Label prolo.gruppen. Prueft
# ein Werkzeug eine Gruppe, die dort nicht steht, legt niemand sie an - und
# das Werkzeug weist jeden mit 403 ab. Gelesen wird, was WIRKLICH gilt:
# die Vorgabe im Code, ueberschrieben von der Compose-Datei.
for werkzeug in werkzeuge:
    code = lies(werkzeug, "server.py") or ""
    compose = compose_alles(werkzeug)
    gilt = {}
    for m in re.finditer(r'os\.environ\.get\("([A-Z_]*_GRUPPE)",\s*"([^"]+)"\)', code):
        gilt[m.group(1)] = m.group(2)
    for var in list(gilt):
        kurz = var.split("_", 1)[1] if var.count("_") > 1 else var
        for name in (var, kurz):
            u = re.search(r"^\s+%s:\s*\"?(?:\$\{%s:-)?([A-Za-z0-9_.-]+)" % (name, name), compose, re.M)
            if u:
                gilt[var] = u.group(1)
    genannt = set()
    for m in re.finditer(r"prolo\.gruppen=([^\"\n]+)", compose):
        genannt |= {t.strip().partition("=")[0].strip() for t in m.group(1).split(";")}
    fehlt = sorted(set(gilt.values()) - genannt)
    sag(gilt and not fehlt,
        "%s: jede gepruefte Gruppe steht in prolo.gruppen (%s)"
        % (werkzeug, ", ".join(sorted(set(gilt.values()))) or "keine gefunden"),
        "fehlt: %s - 'prolo einrichten' nennt sie dann nicht, und niemand legt sie an"
        % ", ".join(fehlt))

# --- 4b. sniStrict steht dort, wo Traefik es liest (N-93) --------------
# Fuer einen UNBEKANNTEN Namen gibt es keinen Router, also nur die Option
# "default". Unter einem anderen Namen galt sniStrict nur fuer Namen, die
# ohnehin einen Router haben - gemessen: fremder Name -> Notzertifikat, 404.
sicher = lies("traefik", "dynamic/sicherheit.yml") or ""
m = re.search(r"^tls:\n  options:\n(?:    #.*\n)*    default:\n((?:      .*\n|\s*\n)+)", sicher, re.M)
sag(m is not None and re.search(r"^      sniStrict:\s*true\s*$", m.group(1), re.M) is not None,
    "sniStrict steht in der TLS-Option 'default' (N-93)",
    "in einer anders benannten Option gilt es fuer fremde Namen nicht")
statisch_tls = lies("traefik", "traefik.yml") or ""
sag(not re.search(r"^\s+options:\s*(?!default)\S+@file", statisch_tls, re.M),
    "der Eingang verweist auf keine andere TLS-Option als 'default'",
    "sonst gilt fuer die Router etwas anderes als fuer fremde Namen")

# --- 4c. Der Vermittler startet auch ohne IPv6 (N-92) ------------------
# Ohne ihn kein einziger Router. Auf einem Kern ohne IPv6 bindet er sonst
# an [::] und startet in Schleife neu - gemessen.
vermittler = lies("socket-proxy", "docker-compose.yml") or ""
sag(re.search(r"^\s+DISABLE_IPV6:\s*[\"']?(1|true)[\"']?\s*$", vermittler, re.M) is not None,
    "socket-proxy bindet nur IPv4 und startet auch ohne IPv6 (N-92)",
    "ohne DISABLE_IPV6 stirbt er auf einem Kern ohne IPv6 - und Traefik findet keinen Router")

# --- 5. Die Pruefadresse liegt auf einem freien Pfad --------------------
for werkzeug in werkzeuge:
    conf = lies(werkzeug, "aktualisierung.conf") or ""
    url = re.search(r'PRUEF_URL="([^"]*)"', conf)
    if not url or not url.group(1):
        continue
    pfad = re.sub(r"^https?://[^/]+", "", url.group(1)) or "/"
    code = lies(werkzeug, "server.py") or ""
    sag(pfad in freie_pfade(code),
        "%s: PRUEF_URL zeigt auf einen freien Pfad (%s)" % (werkzeug, pfad),
        "aktualisieren.sh ruft intern auf und hat die Marke nicht - "
        "die Pruefung wuerde immer fehlschlagen und jeden Lauf zurueckrollen")

print("")
print("Alles gruen." if not fehler else "%d Fehler." % fehler)
sys.exit(1 if fehler else 0)
PY
