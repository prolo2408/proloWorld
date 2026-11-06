"""Den Unterbau einrichten, hochfahren und aktualisieren.

"prolo einrichten" bringt einen Server vom frischen Klon zum laufenden
Unterbau - und einen halb eingerichteten von dort, wo er steht. Jeder
Schritt sieht erst nach, ob er noetig ist: der Befehl laeuft beliebig oft,
und beim zweiten Mal passiert nichts Neues. Nichts Vorhandenes wird
ueberschrieben - keine Einstellung, kein Geheimnis, kein Schluessel.
"""
import json
import os
import re
import shutil
import sys
import time

from . import docker, orte, sicherung, tools
from .orte import Abbruch

SYSTEMD = os.environ.get("PROLO_SYSTEMD", "/etc/systemd/system")
NEUSTART_FLAGGE = os.path.join(orte.AGENT, "neustart")

KONF_KOPF = """# ProloWelt - Einstellungen dieses Servers
#
# Nach einer Aenderung:  sudo prolo einrichten
#
# PROLO_DOMAIN  die Tools liegen unter <name>.<domain>, die Anmeldung unter
#               auth.<domain>, die Verwaltung unter admin.<domain>
# PROLO_EMAIL   fuer Let's Encrypt und als E-Mail des ersten Nutzers (akadmin)
# BACKUP_TAGE   so lange bleiben Sicherungen liegen (die drei neuesten immer)
# AUTO_UPDATE   ja: nach der naechtlichen Sicherung "prolo update"
# ADMIN_GRUPPE  wer in Authentik in dieser Gruppe ist, darf auf admin.<domain>
# ADMIN_NETZE   leer: admin.<domain> von ueberall (hinter der Anmeldung). Sonst
#               nur aus diesen Netzen, z. B. 203.0.113.7/32,10.8.0.0/24 (VPN)"""

UNITS = {
    "prolo-agent.service": """[Unit]
Description=ProloWelt: Agent der Admin-Seite (Auftraege ausfuehren, Status schreiben)
After=docker.service
Wants=docker.service

[Service]
ExecStart=/usr/bin/python3 {repo}/prolo agent
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""",
    "prolo-nacht.service": """[Unit]
Description=ProloWelt: naechtliche Sicherung und Update
After=docker.service
Wants=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {repo}/prolo nacht
TimeoutStartSec=6h
""",
    "prolo-nacht.timer": """[Unit]
Description=ProloWelt: jede Nacht sichern und aktualisieren

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=20min
Persistent=true

[Install]
WantedBy=timers.target
""",
}


def git(*args, pruefen=True, zeit_s=120):
    return docker.lauf(["git", "-C", orte.REPO, "-c", "safe.directory=" + orte.REPO, *args],
                       pruefen=pruefen, zeit_s=zeit_s,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C"))


# ---------------------------------------------------------- Einrichten
def einstellungen(domain, email):
    orte.abschnitt("Einstellungen (%s)" % orte.KONF)
    roh = orte.env_lesen(orte.KONF)
    if domain:
        roh["PROLO_DOMAIN"] = domain.strip().lower()
    if email:
        roh["PROLO_EMAIL"] = email.strip()
    for feld, frage, muster in (("PROLO_DOMAIN", "Domain (z. B. prolo.me)", orte.DOMAIN),
                                ("PROLO_EMAIL", "E-Mail für Let's Encrypt und Anmeldung",
                                 orte.EMAIL)):
        while not muster.fullmatch(roh.get(feld) or ""):
            if roh.get(feld):
                orte.fehler("%s=%s ist nicht gültig." % (feld, roh[feld]))
            if not sys.stdin.isatty():
                raise Abbruch("%s fehlt. Mitgeben:  sudo prolo einrichten --domain <domain> "
                              "--email <adresse>" % feld)
            roh[feld] = input("  %s: " % frage).strip()
            if feld == "PROLO_DOMAIN":
                roh[feld] = roh[feld].lower()
    werte = {k: roh.get(k) or v for k, v in orte.KONF_FELDER.items()}
    alt = orte.env_lesen(orte.KONF)
    if not os.path.isfile(orte.KONF) or any(alt.get(k) != w for k, w in werte.items()):
        os.makedirs(orte.ETC, mode=0o700, exist_ok=True)
        orte.env_schreiben(orte.KONF, werte, KONF_KOPF, 0o600)
        orte.getan("geschrieben")
    else:
        orte.ok("Domain %s, E-Mail %s" % (werte["PROLO_DOMAIN"], werte["PROLO_EMAIL"]))
    orte.konf()


def geheimnisse_anlegen():
    orte.abschnitt("Geheimnisse (%s)" % orte.GEHEIM)
    werte = orte.env_lesen(orte.GEHEIM)
    neu = [k for k in orte.GEHEIM_FELDER if not werte.get(k)]
    for k in neu:
        werte[k] = orte.zufall(24 if k == "AUTHENTIK_BOOTSTRAP_PASSWORD" else 50)
    if neu:
        orte.env_schreiben(orte.GEHEIM, werte,
                           "# ProloWelt - Geheimnisse dieses Servers. Nie in Git, nie in einen "
                           "Chat.\n# PG_PASS steht auch IN der Datenbank - hier ändern sperrt "
                           "Authentik aus.", 0o600)
        orte.getan("gewürfelt: %s" % ", ".join(neu))
    else:
        orte.ok("alle da")
    os.chmod(orte.GEHEIM, 0o600)
    return "AUTHENTIK_BOOTSTRAP_PASSWORD" in neu


def ordner_anlegen():
    orte.abschnitt("Ordner")
    plan = [
        (orte.ETC, 0o700, None),
        (orte.VAR, 0o755, None),
        (os.path.join(orte.VAR, "traefik"), 0o755, None),
        (os.path.join(orte.VAR, "traefik", "acme"), 0o700, None),
        (os.path.join(orte.VAR, "traefik", "dynamic"), 0o755, None),
        (orte.AGENT, 0o755, None),
        # Hier schreibt die Admin-Seite (Nutzer 10004) ihre Auftraege hinein.
        (orte.EINGANG, 0o700, (orte.ADMIN_UID, orte.ADMIN_UID)),
        # Hier liest sie Status und Ergebnisse - nur lesen, nicht schreiben.
        (orte.AUSGANG, 0o750, (0, orte.ADMIN_UID)),
        (orte.TOOLS, 0o700, None),
        (orte.BACKUP, 0o700, None),
    ]
    for pfad, modus, besitz in plan:
        neu = not os.path.isdir(pfad)
        os.makedirs(pfad, exist_ok=True)
        os.chmod(pfad, modus)
        if besitz and orte.ist_root():
            os.chown(pfad, *besitz)
        (orte.getan if neu else orte.ok)("%s" % pfad)


def pruefer_anlegen():
    """Der Nutzer ohne Rechte, als der prolo Compose-Dateien prueft
    (kern/kaefig.py, N-137): kein Login, kein Zuhause, keine Gruppe ausser
    der eigenen."""
    from . import kaefig
    import pwd
    try:
        pwd.getpwnam(kaefig.PRUEFER)
        orte.ok("Nutzer %s (prüft Compose-Dateien ohne Rechte)" % kaefig.PRUEFER)
        return
    except KeyError:
        pass
    docker.lauf(["useradd", "--system", "--user-group", "--no-create-home",
                 "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin",
                 kaefig.PRUEFER], zeit_s=60)
    orte.getan("Nutzer %s angelegt (prüft Compose-Dateien ohne Rechte)" % kaefig.PRUEFER)


UNTERBAU_ROUTEN = "unterbau.yml"


def unterbau_routen(domain, admin_netze=()):
    """Die Router fuer auth.<domain>, den Rueckweg der Anmeldung und
    admin.<domain> - als Datei, nicht als Labels (N-139). Die Ziele heissen
    prolo-...: diese Namen darf kein Tool tragen (kern/kaefig.py)."""
    q = tools.q
    re_domain = re.escape(domain)
    return "".join([
        tools.KOPF,
        "# Der Unterbau. Erzeugt von \"prolo einrichten\" aus prolo.conf.\n",
        "http:\n  routers:\n",
        "    prolo-auth:\n",
        "      rule: %s\n" % q("Host(`auth.%s`)" % domain),
        "      entryPoints: [\"websecure\"]\n      service: prolo-auth\n",
        "    # Der Rueckweg nach der Anmeldung, auf jedem Namen DIESER Domain.\n",
        "    prolo-outpost:\n",
        "      rule: %s\n" % q("HostRegexp(`^([a-z0-9-]+\\.)?%s$`) && "
                             "PathPrefix(`/outpost.goauthentik.io/`)" % re_domain),
        "      entryPoints: [\"websecure\"]\n      priority: 1000\n      service: prolo-auth\n",
        "    prolo-admin:\n",
        "      rule: %s\n" % q("Host(`admin.%s`)" % domain),
        "      entryPoints: [\"websecure\"]\n      service: prolo-admin\n",
        # Erst das Netz, dann die Anmeldung: von draussen sieht man dann nicht
        # einmal die Anmeldeseite (N-141).
        "      middlewares: [%s\"authentik@file\"]\n" % ("\"admin-netz\", " if admin_netze else ""),
    ] + ([
        "  middlewares:\n",
        "    # ADMIN_NETZE aus prolo.conf. Die echte Gegenstelle zaehlt, keine Kopfzeile.\n",
        "    admin-netz:\n      ipAllowList:\n        sourceRange: [%s]\n"
        % ", ".join(q(n) for n in admin_netze),
    ] if admin_netze else []) + [
        "  services:\n",
        "    prolo-auth:\n      loadBalancer:\n        servers:\n"
        "          - url: \"http://prolo-authentik:9000\"\n",
        "    prolo-admin:\n      loadBalancer:\n        servers:\n"
        "          - url: \"http://prolo-admin:8080\"\n",
    ])


def docker_netze():
    """Die Adressbereiche aller Docker-Netze auf diesem Server - auch solche
    ausserhalb der ueblichen Bereiche (eigene default-address-pools)."""
    rc, aus = docker.lauf(["docker", "network", "ls", "-q"], pruefen=False, zeit_s=60)
    ids = aus.split() if rc == 0 else []
    if not ids:
        return []
    rc, aus = docker.lauf(["docker", "network", "inspect", "--format",
                           "{{range .IPAM.Config}}{{.Subnet}} {{end}}", *ids],
                          pruefen=False, zeit_s=60)
    return [n for n in aus.split() if "/" in n] if rc == 0 else []


def traefik_dateien():
    """Die dynamische Konfiguration aus dem Repository nach VAR kopieren und
    die Router des Unterbaus schreiben. Dateien lokal-*.yml dort gehoeren dem
    Betreiber, tool-*.yml den Tools - beide bleiben stehen."""
    orte.abschnitt("Traefik-Konfiguration")
    quelle = os.path.join(orte.REPO, "traefik", "dynamic")
    ziel = os.path.join(orte.VAR, "traefik", "dynamic")
    soll = {n for n in os.listdir(quelle) if n.endswith((".yml", ".yaml"))}
    texte = {}
    for n in sorted(soll):
        with open(os.path.join(quelle, n), encoding="utf-8") as f:
            texte[n] = f.read()
    k = orte.konf()
    netze = orte.admin_netze(k["ADMIN_NETZE"], docker_netze())
    texte[UNTERBAU_ROUTEN] = unterbau_routen(k["PROLO_DOMAIN"], netze)
    soll.add(UNTERBAU_ROUTEN)
    for n in sorted(soll):
        text = texte[n]
        p = os.path.join(ziel, n)
        try:
            with open(p, encoding="utf-8") as f:
                gleich = f.read() == text
        except FileNotFoundError:
            gleich = False
        if gleich:
            orte.ok(n)
        else:
            orte.datei_schreiben(p, text, 0o644)
            orte.getan(n)
    for n in os.listdir(ziel):
        if n.endswith((".yml", ".yaml")) and n not in soll and \
                not n.startswith(("lokal-", tools.ROUTE_VORSILBE)):
            os.remove(os.path.join(ziel, n))
            orte.getan("%s entfernt (steht nicht mehr im Repository)" % n)


def netze():
    orte.abschnitt("Netze und Router der Tools")
    alle = tools.namen()
    for n in alle:
        if docker.netz_anlegen(tools.netzname(n)):
            orte.getan(tools.netzname(n))
        else:
            orte.ok(tools.netzname(n))
        tools.route_schreiben(n, tools.conf(n))
    tools.netze_schreiben()
    if not alle:
        orte.ok("noch keine Tools")


def tools_auffrischen():
    """Was prolo dem Tool dazutut (prolo.override.yml), hat sich mit dem neuen
    Code womoeglich geaendert - seit N-139 etwa der Name, unter dem Traefik
    das Tool erreicht. Dann wird das Tool neu angelegt, nach der Pruefung wie
    bei jedem Start (N-138). Findet die neue Pruefung etwas, bleibt es, wie es
    ist, und die Meldung sagt, was zu tun ist. Gibt die Meldungen zurueck."""
    meldungen = []
    for n in tools.namen():
        pfad = os.path.join(docker.tool_ordner(n), "prolo.override.yml")
        try:
            with open(pfad, encoding="utf-8") as f:
                alt = f.read()
        except FileNotFoundError:
            alt = None
        try:
            tools.kaefig_pruefen(n, "neu anlegen")
            tools.override_neu(n, tools.conf(n))
            with open(pfad, encoding="utf-8") as f:
                if f.read() == alt:
                    continue
            if docker.container(n):
                docker.tool(n, "up", "-d", "--remove-orphans", zeit_s=1800)
            orte.getan("%s mit dem neuen Code neu angelegt" % n)
        except Abbruch as a:
            m = ("%s ist nicht neu angelegt (%s). Ansehen, dann bestätigen:  sudo prolo "
                 "einrichten" % (n, str(a).splitlines()[0]))
            orte.warnung(m)
            meldungen.append(m)
    return meldungen


def systemd():
    orte.abschnitt("Dienste auf dem Server (systemd)")
    if os.environ.get("PROLO_OHNE_SYSTEMD") or not shutil.which("systemctl"):
        orte.warnung("ohne systemd: kein Agent für die Admin-Seite, keine nächtliche "
                     "Sicherung. Von Hand:  prolo agent  /  prolo nacht")
        return
    geaendert = False
    for name, vorlage in UNITS.items():
        p = os.path.join(SYSTEMD, name)
        text = vorlage.format(repo=orte.REPO)
        try:
            with open(p, encoding="utf-8") as f:
                gleich = f.read() == text
        except FileNotFoundError:
            gleich = False
        if gleich:
            orte.ok(name)
        else:
            orte.datei_schreiben(p, text, 0o644)
            orte.getan(name)
            geaendert = True
    if geaendert:
        docker.lauf(["systemctl", "daemon-reload"], zeit_s=60)
    for einheit in ("prolo-agent.service", "prolo-nacht.timer"):
        rc, _ = docker.lauf(["systemctl", "is-active", "--quiet", einheit], pruefen=False)
        if rc != 0:
            docker.lauf(["systemctl", "enable", "--now", einheit], zeit_s=60)
            orte.getan("%s eingeschaltet" % einheit)
        else:
            orte.ok("%s läuft" % einheit)
    # Der Agent laedt neuen Code erst nach einem Neustart. Den macht er
    # selbst, sobald er nichts zu tun hat - ein Neustart von aussen braeche
    # einen laufenden Auftrag ab (auch den, der gerade dieses Update macht).
    orte.datei_schreiben(NEUSTART_FLAGGE, time.strftime("%Y-%m-%dT%H:%M:%S\n"), 0o644)


def hochfahren():
    """Abbilder holen, Admin-Seite bauen, alles starten und warten, bis es
    gesund ist."""
    orte.abschnitt("Unterbau starten")
    rc, aus = docker.unterbau("pull", "--ignore-buildable", "--quiet", zeit_s=3600, pruefen=False)
    if rc != 0:
        orte.warnung("Abbilder ließen sich nicht holen - es geht mit den vorhandenen weiter:\n"
                     + docker.kern_der_meldung(aus, 3))
    docker.lauf(["docker", "pull", "--quiet", orte.HILFSABBILD], zeit_s=600, pruefen=False)
    print("  Baue die Admin-Seite ...", flush=True)
    docker.unterbau("build", "--quiet", zeit_s=1800)
    print("  Starte und warte, bis alles gesund ist (beim ersten Mal bis zu 5 Minuten) ...",
          flush=True)
    rc, aus = docker.unterbau("up", "-d", "--remove-orphans", "--wait", "--wait-timeout", "420",
                              zeit_s=900, pruefen=False)
    alle = docker.container(docker.UNTERBAU)
    for c in sorted(alle, key=lambda c: c["dienst"]):
        z = docker.zustand([c])
        (orte.ok if z in ("gesund", "laeuft") else orte.fehler)("%-18s %s" % (c["dienst"], z))
    if rc != 0:
        raise Abbruch("Der Unterbau kam nicht vollständig hoch:\n%s\n  Protokoll:  "
                      "sudo prolo compose logs --tail 50 <dienst>" % docker.kern_der_meldung(aus))
    anmeldung_einrichten()


PRUEF_ANMELDUNG = """
from authentik.outposts.models import Outpost
from authentik.policies.models import PolicyBinding
from authentik.providers.proxy.models import ProxyProvider
o = Outpost.objects.filter(managed="goauthentik.io/outposts/embedded").first()
p = ProxyProvider.objects.filter(name="ProloWelt", mode="forward_domain", cookie_domain="%(d)s").first()
a = ProxyProvider.objects.filter(name="ProloWelt Admin", mode="forward_single",
                                 external_host="https://admin.%(d)s").first()
print("PROLO-ANMELDUNG", "OK" if o and p and o.providers.filter(pk=p.pk).exists() else "FEHLT")
print("PROLO-ADMIN", "OK" if o and a and o.providers.filter(pk=a.pk).exists() else "FEHLT")
try:
    g = PolicyBinding.objects.filter(target__application__slug="prolowelt-admin",
                                     group__name="%(g)s").exists()
except Exception:
    g = False
print("PROLO-ADMIN-GRUPPE", "OK" if g else "FEHLT")
"""


# Wer antwortet fuer welchen Namen? Leitet der Outpost admin.<domain> zu
# admin.<domain>/outpost.goauthentik.io/start weiter, hat die Admin-Seite ihr
# eigenes Cookie (N-140); ein Tool geht zu auth.<domain>.
OUTPOST_FRAGEN = """
import urllib.error, urllib.request
class K(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
for host in ("admin.%(d)s", "prolo-pruefung.%(d)s"):
    r = urllib.request.Request("http://127.0.0.1:9000/outpost.goauthentik.io/auth/traefik", headers={
        "X-Forwarded-Host": host, "X-Forwarded-Proto": "https", "X-Forwarded-Uri": "/",
        "X-Forwarded-Method": "GET", "Accept": "text/html"})
    try:
        a = urllib.request.build_opener(K).open(r, timeout=10)
        print("OUTPOST", host, a.status, a.headers.get("Location") or "-")
    except urllib.error.HTTPError as e:
        print("OUTPOST", host, e.code, e.headers.get("Location") or "-")
"""

BLUEPRINTS = ("prolo/prolowelt.yaml", "prolo/prolowelt-admin-gruppe.yaml")


def outpost_lage(antwort, domain):
    """Aus der Ausgabe von OUTPOST_FRAGEN: (alle Namen weitergeleitet,
    admin mit eigenem Cookie)."""
    ziel = {}
    for z in antwort.splitlines():
        teile = z.split()
        if len(teile) == 4 and teile[0] == "OUTPOST":
            ziel[teile[1]] = (teile[2], teile[3])
    admin = ziel.get("admin." + domain, ("", ""))
    tool = ziel.get("prolo-pruefung." + domain, ("", ""))
    weiter = admin[0] == "302" and tool[0] == "302"
    eigen = (admin[1].startswith("https://admin.%s/outpost.goauthentik.io/" % domain) and
             tool[1].startswith("https://auth.%s/" % domain))
    return weiter, eigen


def anmeldung_einrichten(zeit_s=300):
    """Die Blueprints ausdruecklich anwenden und warten, bis sie WIRKEN.

    Authentik richtet sich nach "gesund" noch asynchron ein: seine
    Standard-Ablaeufe entstehen erst nach und nach (vorher scheitert der
    Blueprint still, N-115), und der eingebaute Outpost laedt einen neuen
    Provider erst Sekunden spaeter - bis dahin beantwortet er jede
    Anmeldepruefung mit 404 (gemessen im Durchlauf). Geprueft wird darum die
    Wirkung: haengen beide Provider am Outpost, und leitet der Outpost
    admin.<domain> zu sich selbst (eigenes Cookie, N-140) und ein Tool zu
    auth.<domain> weiter?"""
    k = orte.konf()
    domain = k["PROLO_DOMAIN"]
    werte = {"d": domain, "g": k["ADMIN_GRUPPE"].replace("\\", "").replace('"', "")}
    worker = docker.unterbau_befehl("exec", "-T", "authentik-worker", "ak")
    server = docker.unterbau_befehl("exec", "-T", "authentik-server", "python3", "-c",
                                    OUTPOST_FRAGEN % werte)
    ende = time.time() + zeit_s
    gewartet = False
    while True:
        aus = ""
        for b in BLUEPRINTS:
            aus += docker.lauf(worker + ["apply_blueprint", b], env=docker.unterbau_env(),
                               zeit_s=300, pruefen=False)[1]
        _, pruef = docker.lauf(worker + ["shell", "-c", PRUEF_ANMELDUNG % werte],
                               env=docker.unterbau_env(), zeit_s=300, pruefen=False)
        _, antwort = docker.lauf(server, env=docker.unterbau_env(), zeit_s=60, pruefen=False)
        weiter, eigen = outpost_lage(antwort, domain)
        steht = "PROLO-ANMELDUNG OK" in pruef and "PROLO-ADMIN OK" in pruef
        if steht and weiter and eigen:
            orte.ok("Anmeldung für *.%s steht, admin.%s mit eigenem Cookie (Outpost antwortet)"
                    % (domain, domain))
            if "PROLO-ADMIN-GRUPPE OK" in pruef:
                orte.ok("admin.%s nur für die Gruppe „%s“" % (domain, k["ADMIN_GRUPPE"]))
            else:
                orte.warnung("Die Gruppe „%s“ gibt es in Authentik nicht - admin.%s prüft sie "
                             "selbst, Authentik weist darum niemanden vorher ab. Gruppe anlegen "
                             "(auth.%s -> Verzeichnis -> Gruppen) oder ADMIN_GRUPPE in %s "
                             "anpassen, dann:  sudo prolo einrichten"
                             % (k["ADMIN_GRUPPE"], domain, domain, orte.KONF))
            return
        if time.time() > ende:
            if not steht:
                grund = "Provider fehlt"
            elif not weiter:
                grund = "Outpost antwortet: %s" % (antwort.strip().splitlines() or ["nichts"])[-1]
            else:
                grund = ("admin.%s geht nicht über den eigenen Provider - das Cookie der ganzen "
                         "Domain gälte dort" % domain)
            raise Abbruch("Der Authentik-Blueprint hat nicht gewirkt (%s):\n%s\n  Nachsehen in "
                          "Authentik: auth.%s -> Anpassung -> Blueprints -> 'ProloWelt'.\n"
                          "  Noch einmal versuchen ist gefahrlos:  sudo prolo einrichten"
                          % (grund, docker.kern_der_meldung(aus + pruef + antwort, 4), domain))
        if not gewartet:
            print("  Authentik richtet sich noch ein - warte auf die Anmeldung ...", flush=True)
            gewartet = True
        time.sleep(10)


def einrichten(domain=None, email=None, schluessel=None, nach_update=None):
    orte.root_noetig("einrichten")
    orte.abschnitt("Voraussetzungen")
    for p in ("git", "age", "age-keygen", "tar"):
        if not shutil.which(p):
            raise Abbruch("%s fehlt. Am einfachsten:  sudo %s/install.sh" % (p, orte.REPO))
    v = docker.da()
    orte.ok("docker compose %s" % v)

    einstellungen(domain, email)
    erstes_mal = geheimnisse_anlegen()
    orte.abschnitt("Sicherungsschluessel")
    if sicherung.schluessel_anlegen(schluessel):
        orte.getan("%s angelegt" % orte.SCHLUESSEL)
        schluessel_hinweis = True
    else:
        orte.ok(orte.SCHLUESSEL_PUB)
        schluessel_hinweis = False
    ordner_anlegen()
    pruefer_anlegen()
    traefik_dateien()
    netze()
    systemd()
    try:
        hochfahren()
    except Abbruch as a:
        if nach_update:
            update_merken(False, nach_update, str(a))
        raise
    orte.abschnitt("Tools")
    meldungen = tools_auffrischen()
    if nach_update:
        update_merken(True, nach_update, "", "\n".join(meldungen))
        orte.abschnitt("Update fertig: %s -> %s" % (nach_update[:7], git_lage()["commit"]))
        return
    zusammenfassung(schluessel_hinweis, erstes_mal)


def zusammenfassung(schluessel_hinweis, erstes_mal):
    k = orte.konf()
    g = orte.env_lesen(orte.GEHEIM)
    d = k["PROLO_DOMAIN"]
    orte.abschnitt("Fertig")
    # Das Passwort steht nur beim ersten Mal hier - danach landete es mit
    # jedem Lauf im Journal und in den Auftraegen der Admin-Seite (§22).
    pw = (g.get("AUTHENTIK_BOOTSTRAP_PASSWORD", "?") + "  (gleich in Authentik aendern)"
          if erstes_mal else "steht in %s (AUTHENTIK_BOOTSTRAP_PASSWORD)" % orte.GEHEIM)
    print("""
  Verwaltung   https://admin.%(d)s
  Anmeldung    https://auth.%(d)s   Nutzer: akadmin
               Erstes Passwort: %(pw)s

  DNS: beim Anbieter EINEN Eintrag  *.%(d)s  (A-Record, Wildcard) auf die
  IP dieses Servers - dann ist jedes neue Tool sofort erreichbar. Die
  Zertifikate holt Traefik von selbst.

  Ein Tool installieren:
    sudo prolo tool add uptime --image louislam/uptime-kuma:1
  oder auf der Verwaltungsseite unter "Tools".

  Jede Nacht um 03:30 wird gesichert (nach %(b)s) und danach aktualisiert.
  Stand ansehen:  sudo prolo status""" % {"d": d, "pw": pw, "b": orte.BACKUP})
    if schluessel_hinweis:
        print("""
  WICHTIG - der Schluessel fuer die Sicherungen:
    sudo prolo backup schluessel
  zeigt ihn. Kopiere ihn in deinen Passwortmanager. Ohne ihn laesst sich
  eine Sicherung auf einem neuen Server nicht oeffnen.""")
    print()


# ------------------------------------------------------------ Update
def update_merken(ok, alt, text, warnung=""):
    _, neu = git("rev-parse", "--short", "HEAD", pruefen=False)
    orte.datei_schreiben(orte.UPDATE_JSON, json.dumps({
        "zeit": sicherung.jetzt(), "ok": ok, "von": (alt or "")[:12], "auf": neu.strip(),
        "version": orte.version(), "meldung": text[-1000:], "warnung": warnung[-500:]},
        ensure_ascii=False, indent=1), 0o644)


def git_lage(holen=False):
    """{'commit', 'hinter', 'voraus', 'geaendert', 'fehler'} - ohne Netz, wenn
    holen=False (dann gilt der Stand vom letzten 'git fetch')."""
    lage = {"commit": "", "hinter": 0, "voraus": 0, "geaendert": [], "fehler": ""}
    rc, aus = git("rev-parse", "--short", "HEAD", pruefen=False)
    if rc != 0:
        lage["fehler"] = "kein git clone"
        return lage
    lage["commit"] = aus.strip()
    if holen:
        rc, aus = git("fetch", "--quiet", pruefen=False, zeit_s=120)
        if rc != 0:
            lage["fehler"] = "git fetch: " + (aus.strip().splitlines() or ["?"])[-1][:200]
    rc, aus = git("rev-list", "--left-right", "--count", "HEAD...@{u}", pruefen=False)
    if rc == 0 and re.fullmatch(r"\d+\s+\d+", aus.strip()):
        voraus, hinter = aus.split()
        lage["voraus"], lage["hinter"] = int(voraus), int(hinter)
    elif not lage["fehler"]:
        lage["fehler"] = "kein Upstream-Zweig eingestellt"
    _, aus = git("status", "--porcelain", "--untracked-files=no", pruefen=False)
    lage["geaendert"] = [z[3:] for z in aus.splitlines() if z.strip()]
    return lage


def abbild_ids():
    _, aus = docker.unterbau("config", "--images", pruefen=False, zeit_s=120)
    ids = {}
    for bild in aus.split():
        rc, i = docker.lauf(["docker", "image", "inspect", "--format", "{{.Id}}", bild],
                            pruefen=False, zeit_s=30)
        ids[bild] = i.strip() if rc == 0 else ""
    return ids


def update(sichern=True):
    orte.root_noetig("update")
    orte.abschnitt("Unterbau: neuer Stand im Git?")
    lage = git_lage(holen=True)
    if lage["fehler"]:
        raise Abbruch("Den Stand im Git kann ich nicht pruefen: %s" % lage["fehler"])
    if lage["geaendert"]:
        raise Abbruch("Im Unterbau (%s) wurde von Hand geändert: %s\n"
                      "  prolo update überschreibt das nicht. Ansehen:  git -C %s diff\n"
                      "  Verwerfen (vorher selbst sichern, was du behalten willst):  git -C %s stash"
                      % (orte.REPO, ", ".join(lage["geaendert"][:5]), orte.REPO, orte.REPO))
    if lage["voraus"]:
        raise Abbruch("Der Unterbau hat %d eigene Commits, die nicht im Git stehen - "
                      "zusammenführen muss ein Mensch:  git -C %s status"
                      % (lage["voraus"], orte.REPO))
    if lage["hinter"]:
        orte.ok("%d neue Commits" % lage["hinter"])
        if sichern:
            sicherung.sichern(grund="vor dem Update des Unterbaus")
        with orte.sperre("update"):
            alt = lage["commit"]
            git("merge", "--ff-only", "--quiet", "@{u}", zeit_s=300)
            orte.getan("Unterbau auf %s" % git_lage()["commit"])
        # Ab hier gilt der NEUE Code - also neu starten, statt halb mit dem
        # alten weiterzulaufen.
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable, os.path.join(orte.REPO, "prolo"),
                                  "einrichten", "--nach-update", alt])
    orte.ok("Unterbau ist auf dem Stand von Git (%s)" % lage["commit"])
    orte.abschnitt("Abbilder: neue Fehlerbehebungen?")
    with orte.sperre("update"):
        vorher = abbild_ids()
        rc, aus = docker.unterbau("pull", "--ignore-buildable", "--quiet", zeit_s=3600,
                                  pruefen=False)
        if rc != 0:
            # Kein Fehlschlag: es laeuft alles wie vorher, nur ohne Neues.
            # Jede Nacht "Update fehlgeschlagen" waere Tapete (§7).
            w = "Abbilder ließen sich nicht prüfen:\n" + docker.kern_der_meldung(aus, 3)
            orte.warnung(w)
            update_merken(True, lage["commit"], "", w)
            return
        nachher = abbild_ids()
        neu = sorted(b for b in nachher if nachher[b] != vorher.get(b))
    if not neu:
        orte.ok("alle Abbilder aktuell")
        update_merken(True, lage["commit"], "")
        return
    orte.getan("neu: %s" % ", ".join(neu))
    if sichern:
        sicherung.sichern(grund="vor dem Update der Abbilder")
    with orte.sperre("update"):
        try:
            hochfahren()
        except Abbruch as a:
            update_merken(False, lage["commit"], str(a))
            raise
    update_merken(True, lage["commit"], "")


def nacht():
    """Jede Nacht: sichern, dann (wenn eingeschaltet) aktualisieren."""
    orte.root_noetig("nacht")
    k = orte.konf()
    try:
        sicherung.sichern(grund="naechtlich")
    except Abbruch as a:
        orte.fehler(str(a))
        print("Kein Update ohne vollständige Sicherung.")
        return 1
    if k["AUTO_UPDATE"] == "ja":
        try:
            update(sichern=False)
        except Abbruch as a:
            orte.fehler(str(a))
            return 1
    docker.lauf(["docker", "image", "prune", "-f"], pruefen=False, zeit_s=600)
    return 0


def schluessel_zeigen():
    orte.root_noetig("backup schluessel")
    if not os.path.isfile(orte.SCHLUESSEL):
        raise Abbruch("Auf diesem Server liegt kein geheimer Schlüssel (%s)." % orte.SCHLUESSEL)
    with open(orte.SCHLUESSEL, encoding="utf-8") as f:
        text = f.read()
    print("Der geheime Schlüssel für die Sicherungen. Ganz kopieren (alle Zeilen) und")
    print("im Passwortmanager ablegen. Ohne ihn lässt sich keine Sicherung öffnen.\n")
    print(text.rstrip())
    print("\nAuf einem neuen Server:  sudo ./install.sh --schluessel <datei mit diesem Text>")
