"""Was laeuft, was fehlt, was zu tun ist - fuer "prolo status" und die
Admin-Seite (die liest status.json, die der Agent alle 30 s schreibt).

Jeder Hinweis nennt, was zu tun ist - nicht nur, was nicht stimmt.
"""
import datetime
import json
import os
import shutil

from . import docker, orte, sicherung, tools, unterbau
from .orte import Abbruch

DIENSTE = ("traefik", "authentik-server", "authentik-worker", "authentik-db", "admin",
           "socket-proxy")
SICHERUNG_ALT_H = 48


def _json(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _alter_h(iso):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return (datetime.datetime.now(t.tzinfo) - t).total_seconds() / 3600


def _oder_none(f, *args):
    """Ein kaputtes Tool soll nicht den ganzen Stand verderben."""
    try:
        return f(*args)
    except (OSError, Abbruch):
        return None


def sammeln():
    hinweise = []

    def hinweis(stufe, text, tat=""):
        hinweise.append({"stufe": stufe, "text": text, "tat": tat})

    try:
        k = orte.konf()
    except Abbruch as a:
        return {"zeit": sicherung.jetzt(), "fehler": str(a), "hinweise": [
            {"stufe": "fehler", "text": str(a), "tat": "sudo prolo einrichten"}]}
    s = {"zeit": sicherung.jetzt(), "version": orte.version(), "domain": k["PROLO_DOMAIN"],
         "auto_update": k["AUTO_UPDATE"] == "ja", "backup_tage": int(k["BACKUP_TAGE"])}

    # --- Unterbau
    try:
        alle = docker.container()
        docker_ok = True
    except Abbruch as a:
        alle, docker_ok = [], False
        hinweis("fehler", "Docker antwortet nicht: %s" % a, "sudo systemctl status docker")
    s["unterbau"] = []
    for d in DIENSTE:
        cs = [c for c in alle if c["projekt"] == docker.UNTERBAU and c["dienst"] == d]
        z = docker.zustand(cs)
        s["unterbau"].append({"dienst": d, "zustand": z,
                              "abbild": cs[0]["abbild"] if cs else "",
                              "status": cs[0]["status"] if cs else ""})
        if docker_ok and z not in ("gesund", "laeuft"):
            hinweis("fehler", "%s ist %s." % (d, z), "sudo prolo compose logs --tail 50 %s" % d)

    # --- Tools
    s["tools"] = []
    for n in tools.namen():
        c = tools.conf(n)
        cs = [x for x in alle if x["projekt"] == n]
        z = docker.zustand(cs)
        try:
            ms = docker.mounts(n) if cs else []
        except Abbruch:
            ms = []
        ordner = os.path.realpath(docker.tool_ordner(n))
        aussen = [m["quelle"] for m in ms if m["art"] == "bind"
                  and not os.path.realpath(m["quelle"]).startswith(ordner + os.sep)]
        s["tools"].append({
            "name": n, "zustand": z, "url": tools.url(c), "host": c.get("HOST", ""),
            "anmeldung": c.get("ANMELDUNG", ""), "quelle": c.get("QUELLE", ""),
            "herkunft": c.get("ABBILD") or c.get("GIT") or "Compose-Datei",
            "dienst": c.get("DIENST", ""), "port": c.get("PORT", ""),
            "angelegt": c.get("ANGELEGT", ""),
            "dienste": [{"dienst": x["dienst"], "zustand": docker.zustand([x]),
                         "status": x["status"], "abbild": x["abbild"]} for x in cs],
            "volumes": sorted(m["name"] for m in ms if m["art"] == "volume"),
            "nicht_gesichert": aussen,
            # Zum Bearbeiten auf der Admin-Seite: die Datei und die NAMEN der
            # Variablen - ihre Werte (Passwoerter) verlassen den Server nicht.
            "compose": _oder_none(tools.compose_text, n, c),
            "variablen": _oder_none(tools.variablen_namen, n) or []})
        if z in ("krank", "teilweise"):
            hinweis("warn", "Tool %s ist %s." % (n, z), "sudo prolo tool logs %s" % n)
        for p in aussen:
            hinweis("warn", "Tool %s hängt %s ein - das wird nicht gesichert." % (n, p),
                    "Daten nach %s/app/ verlegen" % docker.tool_ordner(n))

    # --- Sicherung
    st = _json(orte.SICHERUNG_JSON) or {}
    staende = []
    for name, m in sicherung.staende()[:40]:
        if m is None:
            staende.append({"ordner": name, "kaputt": True})
            continue
        staende.append({"ordner": name, "stand": m.get("stand"), "zeit": m.get("zeit"),
                        "grund": m.get("grund", ""), "bytes": m.get("bytes", 0),
                        "tools": m.get("tools") or [], "unterbau": m.get("unterbau", False),
                        "geprueft": m.get("geprueft", ""), "fehler": len(m.get("fehler") or [])})
    s["sicherung"] = {"letzte": st.get("letzte"), "letzte_vollstaendige": st.get("letzte_vollstaendige"),
                      "staende": staende, "schluessel_auf_server": os.path.isfile(orte.SCHLUESSEL),
                      "ordner": orte.BACKUP}
    lv = st.get("letzte_vollstaendige")
    alter = _alter_h(lv.get("zeit")) if lv else None
    s["sicherung"]["alter_h"] = alter
    if lv is None:
        hinweis("fehler", "Es gibt noch keine vollständige Sicherung.", "sudo prolo backup")
    elif alter is not None and alter > SICHERUNG_ALT_H:
        hinweis("fehler", "Die letzte vollständige Sicherung ist %d Stunden alt - die "
                "nächtliche läuft nicht." % alter, "sudo systemctl status prolo-nacht.timer")
    letzte = st.get("letzte")
    if letzte and letzte.get("fehler"):
        hinweis("fehler", "Die letzte Sicherung (%s) war unvollständig: %s"
                % (letzte.get("stand"), letzte["fehler"][0][:200]), "sudo prolo backup")

    # --- Update
    s["git"] = unterbau.git_lage(holen=False)
    s["update"] = _json(orte.UPDATE_JSON)
    if s["update"] and not s["update"].get("ok"):
        hinweis("fehler", "Das letzte Update ist fehlgeschlagen: %s"
                % (s["update"].get("meldung") or "")[:300],
                "sudo prolo update  - oder zurück:  sudo prolo restore --unterbau")
    if s["update"] and s["update"].get("ok") and s["update"].get("warnung"):
        hinweis("warn", "Beim letzten Update: %s" % s["update"]["warnung"].splitlines()[0][:200],
                "sudo prolo update")
    if s["git"].get("hinter"):
        hinweis("info", "Neue Fassung des Unterbaus im Git (%d Commits)." % s["git"]["hinter"],
                "sudo prolo update")
    if s["git"].get("geaendert"):
        hinweis("warn", "Im Unterbau wurde von Hand geändert (%s) - prolo update hält dann an."
                % ", ".join(s["git"]["geaendert"][:3]), "git -C %s diff" % orte.REPO)

    # --- Platz
    s["platz"] = {}
    for wofuer, pfad in (("sicherung", orte.BACKUP), ("docker", "/var/lib/docker")):
        if not os.path.isdir(pfad):
            pfad = "/"
        u = shutil.disk_usage(pfad)
        s["platz"][wofuer] = {"frei": u.free, "gesamt": u.total, "pfad": pfad}
        if u.free < 5 * 1024 ** 3 or u.free < u.total * 0.1:
            hinweis("warn", "Unter %s sind nur noch %s frei." % (pfad, sicherung.groesse_text(u.free)),
                    "alte Abbilder: docker image prune -a  |  Sicherungen: BACKUP_TAGE in %s"
                    % orte.KONF)
    s["hinweise"] = hinweise
    return s


ZUSTAND_TEXT = {"gesund": "gesund", "laeuft": "laeuft", "startet": "startet",
                "krank": "KRANK", "teilweise": "TEILWEISE", "aus": "AUS"}


def zeigen(als_json=False):
    s = sammeln()
    if als_json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return
    if "fehler" in s:
        orte.fehler(s["fehler"])
        return
    g = s["git"]
    print("ProloWelt %s  (git %s%s)   %s" % (s["version"], g.get("commit") or "?",
                                            ", %d neue Commits" % g["hinter"] if g.get("hinter") else "",
                                            s["domain"]))
    orte.abschnitt("Unterbau")
    for u in s["unterbau"]:
        print("  %-18s %-10s %s" % (u["dienst"], ZUSTAND_TEXT.get(u["zustand"], u["zustand"]),
                                    u["abbild"]))
    orte.abschnitt("Tools")
    if not s["tools"]:
        print("  noch keine - installieren:  sudo prolo tool add <name> --image <abbild>")
    for t in s["tools"]:
        print("  %-18s %-10s %-10s %s" % (t["name"], ZUSTAND_TEXT.get(t["zustand"], t["zustand"]),
                                          "Authentik" if t["anmeldung"] == "authentik" else "OFFEN",
                                          t["url"]))
    orte.abschnitt("Sicherung")
    lv = s["sicherung"]["letzte_vollstaendige"]
    if lv:
        print("  letzte vollständige: %s  (%s, %s)" % (
            lv["stand"], sicherung.groesse_text(lv.get("bytes", 0)),
            "entschlüsselt und gelesen" if lv.get("geprueft") == "ok" else "Prüfsummen"))
    print("  %d Stände in %s, je %d Tage" % (len(s["sicherung"]["staende"]), orte.BACKUP,
                                             s["backup_tage"]))
    orte.abschnitt("Was zu tun ist")
    if not s["hinweise"]:
        print("  nichts - alles in Ordnung")
    for h in s["hinweise"]:
        {"fehler": orte.fehler, "warn": orte.warnung}.get(h["stufe"], lambda t: print("  " + t))(h["text"])
        if h["tat"]:
            print("           -> %s" % h["tat"])
