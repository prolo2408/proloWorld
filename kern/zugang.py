"""Git-Zugaenge fuer private Repositories (N-134) - einer je Anbieter.

    /etc/prolo/git-zugang.json   {"github.com": {"benutzer", "token", "gesetzt", "ablauf"}}
                                 root, 0600 - kommt mit /etc/prolo in die Sicherung

git bekommt den Token ueber einen eigenen Helfer (prolo git-zugang helfer),
nicht ueber "credential.helper store": store loescht bei einer Absage (401)
den Eintrag - ein abgelaufener Token waere dann still verschwunden. Der
Helfer gibt nur heraus, er speichert und loescht nichts.

Der Token steht nie in einer URL, einem Argument, einer Ausgabe oder in
status.json. Die Seite sieht Anbieter, Benutzer und Ablaufdatum.
"""
import datetime
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.request

from . import auftrag, docker, orte
from .orte import Abbruch

DATEI = os.path.join(orte.ETC, "git-zugang.json")
WARNEN_TAGE = auftrag.ZUGANG_WARNEN_TAGE
NEU = "Neuen Token anlegen (github.com -> Settings -> Developer settings -> Fine-grained tokens)"


def lesen():
    try:
        with open(DATEI, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return {}
    except ValueError as e:
        raise Abbruch("%s ist kaputt (%s). Zugänge neu setzen:  sudo prolo git-zugang setzen "
                      "<anbieter> --benutzer <name>" % (DATEI, e))
    return d if isinstance(d, dict) else {}


def _schreiben(d):
    orte.datei_schreiben(DATEI, json.dumps(d, ensure_ascii=False, indent=1) + "\n", 0o600)


def git_env():
    """Umgebung fuer git: keine Rueckfrage, und nur unser Helfer (der leere
    Eintrag davor verwirft Helfer aus der Konfiguration des Systems)."""
    helfer = "%s %s git-zugang helfer" % (shlex.quote(sys.executable),
                                          shlex.quote(os.path.join(orte.REPO, "prolo")))
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="2",
                GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="",
                GIT_CONFIG_KEY_1="credential.helper", GIT_CONFIG_VALUE_1=helfer)


def helfer(aktion):
    """git fragt: protocol=https, host=github.com ... Leerzeile. Antwort nur
    bei 'get' und nur, wenn ein Zugang da ist - sonst nichts (git fragt dann
    nicht weiter, GIT_TERMINAL_PROMPT=0)."""
    frage = {}
    for zeile in sys.stdin:
        zeile = zeile.rstrip("\n")
        if not zeile:
            break
        k, _, v = zeile.partition("=")
        frage[k] = v
    if aktion != "get" or frage.get("protocol") != "https":
        return 0
    try:
        z = lesen().get(frage.get("host", ""))
    except (OSError, Abbruch):
        return 0
    if isinstance(z, dict) and z.get("token") and z.get("benutzer"):
        sys.stdout.write("username=%s\npassword=%s\n" % (z["benutzer"], z["token"]))
    return 0


def ablauf_fragen(host, token):
    """(gilt, ablauf). Nur GitHub sagt das Ablaufdatum (Kopfzeile jeder
    API-Antwort). gilt=None: nicht gefragt oder nicht erreichbar.
    ablauf: 'JJJJ-MM-TT' oder '' (ohne Ablauf / unbekannt)."""
    if host != "github.com":
        return None, ""
    frage = urllib.request.Request("https://api.github.com/rate_limit", headers={
        "Authorization": "Bearer " + token, "User-Agent": "prolo",
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(frage, timeout=15) as r:
            kopf = r.headers.get("github-authentication-token-expiration") or ""
    except urllib.error.HTTPError as e:
        return (False, "") if e.code == 401 else (None, "")
    except (OSError, ValueError):
        return None, ""
    return True, kopf[:10] if re.match(r"\d{4}-\d{2}-\d{2}", kopf) else ""


def host_von(url):
    """https://github.com:443/a/b -> github.com"""
    teile = (url or "").split("/")
    return teile[2].split(":")[0].lower() if len(teile) > 2 and teile[2] else "?"


def heute():
    return datetime.date.today().isoformat()


def tage_bis(ablauf, ab=None):
    try:
        bis = datetime.date.fromisoformat(ablauf)
    except (TypeError, ValueError):
        return None
    return (bis - (ab or datetime.date.today())).days


def setzen(host, benutzer, token=None, token_datei=None):
    orte.root_noetig("git-zugang setzen %s --benutzer %s" % (host, benutzer))
    if not auftrag.HOST.fullmatch(host or "") or not auftrag.BENUTZER.fullmatch(benutzer or ""):
        token = "x" * 8             # erst Anbieter und Benutzer melden, nicht nach dem Token fragen
    elif token_datei:
        with open(token_datei, encoding="utf-8") as f:
            token = f.read()
    elif token is None:
        token = token_lesen(host)
    token = (token or "").strip()
    if not token:
        raise Abbruch("Kein Token eingegeben - nichts gespeichert.")
    try:
        auftrag.pruefen({"art": "zugang_setzen", "felder": {
            "host": host, "benutzer": benutzer, "token": token}})
    except auftrag.Ungueltig as u:
        raise Abbruch(str(u))
    orte.abschnitt("Git-Zugang für %s" % host)
    gilt, ablauf = ablauf_fragen(host, token)
    if gilt is False:
        raise Abbruch("GitHub lehnt den Token ab - abgelaufen, widerrufen oder nicht ganz "
                      "kopiert. Nichts gespeichert. %s, dann noch einmal." % NEU)
    d = lesen()
    d[host] = {"benutzer": benutzer, "token": token, "gesetzt": heute(), "ablauf": ablauf}
    _schreiben(d)
    orte.ok("gespeichert: %s als %s" % (host, benutzer))
    if gilt is None and host == "github.com":
        orte.warnung("GitHub war nicht erreichbar - ob der Token gilt und wann er abläuft, ist "
                     "ungeprüft. Später:  sudo prolo git-zugang testen <repository>")
    elif ablauf:
        print("  Der Token läuft am %s ab - %d Tage vorher steht es unter „Was zu tun ist“."
              % (datum_text(ablauf), WARNEN_TAGE), flush=True)
    elif gilt:
        print("  Der Token läuft nicht ab.", flush=True)


def token_lesen(host):
    """Am Terminal verdeckt; ohne Terminal eine Zeile von stdin
    (printf '%s' "$T" | sudo prolo git-zugang setzen ...)."""
    if not sys.stdin.isatty():
        return sys.stdin.readline()
    import getpass
    try:
        return getpass.getpass("Token für %s (wird nicht angezeigt): " % host)
    except EOFError:
        raise Abbruch("Kein Token eingegeben - nichts gespeichert.")


def entfernen(host):
    orte.root_noetig("git-zugang entfernen %s" % host)
    d = lesen()
    if host not in d:
        raise Abbruch("Für %s ist kein Git-Zugang gespeichert. Gespeichert: %s"
                      % (host, ", ".join(sorted(d)) or "keiner"))
    del d[host]
    _schreiben(d)
    orte.ok("entfernt: %s - private Repositories dort lassen sich nicht mehr holen" % host)


def uebersicht():
    """Fuer status.json und die Liste: alles ausser dem Token."""
    return [{"host": h, "benutzer": z.get("benutzer", ""), "gesetzt": z.get("gesetzt", ""),
             "ablauf": z.get("ablauf", "")}
            for h, z in sorted(lesen().items()) if isinstance(z, dict)]


def hinweise(alle, ab=None):
    """(stufe, text, tat) fuer 'Was zu tun ist': abgelaufen oder bald."""
    aus = []
    for z in alle:
        tage = tage_bis(z.get("ablauf"), ab)
        if tage is None or tage > WARNEN_TAGE:
            continue
        tat = "%s, dann: sudo prolo git-zugang setzen %s --benutzer %s" % (
            NEU, z["host"], z.get("benutzer") or "<name>")
        if tage < 0:
            aus.append(("fehler", "Der Git-Zugang für %s ist am %s abgelaufen - private "
                        "Repositories dort lassen sich nicht mehr aktualisieren."
                        % (z["host"], datum_text(z["ablauf"])), tat))
        else:
            aus.append(("warn", "Der Git-Zugang für %s läuft am %s ab (%s)."
                        % (z["host"], datum_text(z["ablauf"]),
                           "heute" if tage == 0 else "in %d Tagen" % tage), tat))
    return aus


def datum_text(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso or "-"


def liste():
    orte.root_noetig("git-zugang")
    alle = uebersicht()
    if not alle:
        print("Kein Git-Zugang gespeichert. Für private Repositories:\n"
              "  sudo prolo git-zugang setzen github.com --benutzer <name>")
        return
    print("%-24s %-20s %-12s %s" % ("ANBIETER", "BENUTZER", "GESETZT", "LÄUFT AB"))
    for z in alle:
        print("%-24s %-20s %-12s %s" % (z["host"], z["benutzer"], datum_text(z["gesetzt"]),
                                        datum_text(z["ablauf"]) if z["ablauf"] else "-"))


def testen(url):
    orte.root_noetig("git-zugang testen %s" % url)
    if not auftrag.GIT_URL.fullmatch(url or ""):
        raise Abbruch("Repository: eine https://-Adresse, z. B. https://github.com/name/repo.")
    host = host_von(url)
    d = lesen()
    orte.abschnitt("Lese %s" % url)
    rc, aus = docker.lauf(["git", "ls-remote", "--heads", "--", url], zeit_s=60,
                          env=git_env(), pruefen=False)
    if rc != 0:
        raise Abbruch(fehler_text(url, host, aus, host in d))
    zweige = [z.split("refs/heads/", 1)[1] for z in aus.splitlines() if "refs/heads/" in z]
    orte.ok("lesbar%s - Zweige: %s" % (" mit dem Zugang für %s" % host if host in d else
                                        " ohne Zugang (öffentlich)", ", ".join(zweige[:5]) or "keine"))
    if host in d:                   # bei der Gelegenheit das Ablaufdatum auffrischen
        gilt, ablauf = ablauf_fragen(host, d[host].get("token", ""))
        if gilt and ablauf != d[host].get("ablauf"):
            d[host]["ablauf"] = ablauf
            _schreiben(d)
        if d[host].get("ablauf"):
            print("  Der Token läuft am %s ab." % datum_text(d[host]["ablauf"]), flush=True)


def fehler_text(url, host, ausgabe, hat_zugang):
    """Was git sagt, in das, was zu tun ist."""
    setzen_befehl = ("Einstellungen -> Git-Zugänge, oder:  sudo prolo git-zugang setzen %s "
                     "--benutzer <name>" % host)
    if re.search(r"could not read Username|Authentication failed|terminal prompts disabled|"
                 r"Invalid username or (password|token)", ausgabe):
        if hat_zugang:
            return ("%s lehnt den gespeicherten Zugang für %s ab - der Token ist abgelaufen oder "
                    "widerrufen. %s, dann: %s" % (host, url, NEU, setzen_befehl))
        return ("%s ist privat, und für %s ist kein Git-Zugang gespeichert. Eintragen unter %s"
                % (url, host, setzen_befehl))
    if re.search(r"not found|does not exist|Repository not found", ausgabe, re.I):
        if hat_zugang:
            return ("%s gibt es nicht - oder der Token für %s darf es nicht sehen. Auf %s beim "
                    "Token unter „Repository access“ das Repository auswählen." % (url, host, host))
        return "%s gibt es nicht. Adresse prüfen (https://%s/<name>/<repo>)." % (url, host)
    return "git ging nicht für %s:\n%s" % (url, docker.kern_der_meldung(ausgabe))
