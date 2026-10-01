"""prolo - ein Befehl fuer die ganze ProloWelt."""
import argparse
import os
import sys

from . import orte
from .orte import Abbruch

HILFE = """ProloWelt - der Unterbau fuer deine Tools.

Alltag:
  prolo status                    was laeuft, was zu tun ist
  prolo tool list                 installierte Tools
  prolo tool add <name> --image <abbild> [--port <p>]
  prolo tool add <name> --compose <datei> | --git <url>
  prolo tool start|stop|restart|update|logs|rm <name>
  prolo backup                    jetzt sichern (laeuft auch jede Nacht)
  prolo backup list               vorhandene Sicherungen
  prolo restore [<stand>] [--tool <name>]
  prolo update                    Unterbau auf den Stand von Git bringen

Seltener:
  prolo einrichten                alles anlegen/reparieren (gefahrlos zu wiederholen)
  prolo backup pruefen [<stand>]  eine Sicherung vollstaendig lesen
  prolo backup schluessel         den Schluessel fuer den Passwortmanager zeigen
  prolo tool set <name> --port <p> | --anmeldung authentik|keine
  prolo compose <args>            docker compose fuer den Unterbau
  prolo tool compose <name> <args>

Was etwas veraendert, braucht sudo. Hilfe zu einem Befehl:  prolo <befehl> -h
"""


def parser():
    p = argparse.ArgumentParser(prog="prolo", description=HILFE,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="befehl", metavar="<befehl>")

    s = sub.add_parser("status", help="was läuft, was zu tun ist")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("einrichten", aliases=["setup"], help="Unterbau anlegen und starten")
    s.add_argument("--domain")
    s.add_argument("--email")
    s.add_argument("--schluessel", help="vorhandenen Sicherungsschlüssel übernehmen (Umzug)")
    s.add_argument("--nach-update", help=argparse.SUPPRESS)

    s = sub.add_parser("update", aliases=["aktualisieren"], help="Unterbau aktualisieren")
    s.add_argument("--ohne-sicherung", action="store_true")

    s = sub.add_parser("backup", aliases=["sichern"], help="sichern (ohne Zusatz: jetzt)")
    s.add_argument("--tool", action="append", help="nur dieses Tool (mehrfach moeglich)")
    bs = s.add_subparsers(dest="was", metavar="list|pruefen|schluessel")
    bs.add_parser("list", aliases=["liste"], help="vorhandene Sicherungen")
    b = bs.add_parser("pruefen", aliases=["verify"], help="eine Sicherung vollständig lesen")
    b.add_argument("stand", nargs="?")
    b.add_argument("--schluessel")
    bs.add_parser("schluessel", aliases=["key"], help="den geheimen Schlüssel zeigen")

    s = sub.add_parser("restore", aliases=["wiederherstellen"], help="aus einer Sicherung zurückholen")
    s.add_argument("stand", nargs="?", help="ohne Angabe: der neueste passende")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--tool", help="nur dieses Tool")
    g.add_argument("--unterbau", action="store_true", help="nur den Unterbau")
    s.add_argument("--schluessel", help="geheimer Schlüssel, wenn er nicht auf dem Server liegt")
    s.add_argument("--ja", action="store_true", help="nicht nachfragen")
    s.add_argument("--ohne-sicherung", action="store_true",
                   help="den jetzigen Stand vorher NICHT sichern")

    s = sub.add_parser("tool", aliases=["tools"], help="Tools verwalten")
    ts = s.add_subparsers(dest="was", metavar="list|add|rm|start|stop|restart|update|logs|set|compose")
    ts.add_parser("list", aliases=["liste", "ls"])
    a = ts.add_parser("add", aliases=["neu", "install"], help="ein Tool installieren")
    a.add_argument("name")
    q = a.add_mutually_exclusive_group(required=True)
    q.add_argument("--image", help="ein einzelnes Abbild, z. B. louislam/uptime-kuma:1")
    q.add_argument("--compose", help="eine Compose-Datei (bleibt unveraendert)")
    q.add_argument("--git", help="ein Repository mit docker-compose.yml")
    a.add_argument("--port", help="auf diesem Port antwortet die Oberfläche")
    a.add_argument("--dienst", help="welcher Dienst die Oberfläche ist")
    a.add_argument("--anmeldung", choices=("authentik", "keine"), default="authentik",
                   help="authentik (Vorgabe) oder keine (oeffentlich / eigene Anmeldung)")
    a.add_argument("--host", help="statt <name>.<domain>")
    a.add_argument("--env", action="append", default=[], metavar="NAME=wert")
    a.add_argument("--env-datei", help=argparse.SUPPRESS)
    a.add_argument("--ja", action="store_true", help="nicht nachfragen")
    a.add_argument("--von-web", action="store_true", help=argparse.SUPPRESS)
    for was in ("start", "stop", "restart"):
        ts.add_parser(was).add_argument("name")
    u = ts.add_parser("update", aliases=["aktualisieren"])
    u.add_argument("name")
    u.add_argument("--ohne-sicherung", action="store_true")
    r = ts.add_parser("rm", aliases=["entfernen", "remove"], help="entfernen (vorher gesichert)")
    r.add_argument("name")
    r.add_argument("--ja", action="store_true")
    r.add_argument("--ohne-sicherung", action="store_true")
    lg = ts.add_parser("logs", aliases=["protokoll"])
    lg.add_argument("name")
    lg.add_argument("--zeilen", default="100")
    lg.add_argument("-f", "--folgen", action="store_true")
    st = ts.add_parser("set", aliases=["aendern"], help="Port, Anmeldung, Dienst oder Adresse ändern")
    st.add_argument("name")
    st.add_argument("--port")
    st.add_argument("--anmeldung", choices=("authentik", "keine"))
    st.add_argument("--dienst")
    st.add_argument("--host")
    c = ts.add_parser("compose", help="docker compose für ein Tool")
    c.add_argument("name")
    c.add_argument("args", nargs=argparse.REMAINDER)

    c = sub.add_parser("compose", help="docker compose für den Unterbau")
    c.add_argument("args", nargs=argparse.REMAINDER)
    sub.add_parser("agent", help="Aufträge der Admin-Seite ausführen (läuft als Dienst)")
    sub.add_parser("nacht", help="sichern und aktualisieren (laeuft jede Nacht)")
    sub.add_parser("version")
    return p


def env_werte(liste, datei):
    from .auftrag import Ungueltig, env_zeilen
    text = "\n".join(liste)
    if datei:
        with open(datei, encoding="utf-8") as f:
            text += "\n" + f.read()
    try:
        return env_zeilen(text)
    except Ungueltig as u:
        raise Abbruch(str(u))


def ausfuehren(a):
    from . import agent, docker, sicherung, status, tools, unterbau
    b = a.befehl
    if b in (None,):
        print(HILFE)
        return 0
    if b == "version":
        lage = unterbau.git_lage()
        print("ProloWelt %s (git %s)" % (orte.version(), lage["commit"] or "?"))
        return 0
    if b == "status":
        status.zeigen(a.json)
        return 0
    if b in ("einrichten", "setup"):
        unterbau.einrichten(a.domain, a.email, a.schluessel, a.nach_update)
        return 0
    if b in ("update", "aktualisieren"):
        unterbau.update(sichern=not a.ohne_sicherung)
        return 0
    if b in ("backup", "sichern"):
        if a.was in ("list", "liste"):
            sicherung.liste()
        elif a.was in ("pruefen", "verify"):
            sicherung.pruefen(a.stand, a.schluessel)
        elif a.was in ("schluessel", "key"):
            unterbau.schluessel_zeigen()
        else:
            sicherung.sichern(nur=a.tool, grund="von Hand" if not os.environ.get("PROLO_AGENT")
                              else "Admin-Seite")
        return 0
    if b in ("restore", "wiederherstellen"):
        sicherung.zurueckholen(a.stand, a.tool, a.unterbau, a.schluessel, a.ja,
                               not a.ohne_sicherung)
        return 0
    if b in ("tool", "tools"):
        w = a.was
        if w in (None, "list", "liste", "ls"):
            tools.liste()
        elif w in ("add", "neu", "install"):
            tools.anlegen(a.name, abbild=a.image, compose=a.compose, git=a.git, dienst=a.dienst,
                          port=a.port, anmeldung=a.anmeldung, host=a.host,
                          env=env_werte(a.env, a.env_datei), ja=a.ja, von_web=a.von_web)
        elif w == "start":
            tools.starten(a.name)
        elif w == "stop":
            tools.anhalten(a.name)
        elif w == "restart":
            tools.neustarten(a.name)
        elif w in ("update", "aktualisieren"):
            tools.aktualisieren(a.name, sichern=not a.ohne_sicherung)
        elif w in ("rm", "entfernen", "remove"):
            tools.entfernen(a.name, ja=a.ja, sichern=not a.ohne_sicherung)
        elif w in ("logs", "protokoll"):
            return tools.protokoll(a.name, a.zeilen, a.folgen)
        elif w in ("set", "aendern"):
            tools.aendern(a.name, a.port, a.anmeldung, a.dienst, a.host)
        elif w == "compose":
            orte.root_noetig("tool compose")
            tools.conf(a.name)
            os.chdir(os.path.join(docker.tool_ordner(a.name), "app"))
            befehl = docker.tool_befehl(a.name, *a.args)
            os.execvp(befehl[0], befehl)
        return 0
    if b == "compose":
        orte.root_noetig("compose")
        befehl = docker.unterbau_befehl(*a.args)
        os.execvpe(befehl[0], befehl, docker.unterbau_env())
    if b == "agent":
        return agent.laufen()
    if b == "nacht":
        return unterbau.nacht()
    return 2


def main(argv):
    a = parser().parse_args(argv)
    try:
        return ausfuehren(a) or 0
    except Abbruch as e:
        print("", flush=True)
        orte.fehler(str(e))
        return 1
    except PermissionError as e:
        # Einstellungen und Geheimnisse gehoeren root - ohne sudo kommt man
        # nicht heran. Ein Traceback waere hier nur Laerm.
        orte.fehler("Keine Berechtigung für %s - mit sudo aufrufen:  sudo prolo %s"
                    % (e.filename or "eine Datei", " ".join(argv)))
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
