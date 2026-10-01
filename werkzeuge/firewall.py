#!/usr/bin/env python3
"""werkzeuge/firewall.py - prolo firewall: die Firewall ansehen und bedienen (F-02)

    prolo firewall                                   die Lage
    prolo firewall --json                            dasselbe fuer die Admin-Seite
    prolo firewall sperren <adresse> <dauer> <grund> z.B. 203.0.113.7 12h "raet Links"
    prolo firewall aufheben <adresse>
    prolo firewall erlauben <adresse> <grund>        nie sperren (Freigabeliste)
    prolo firewall nicht-mehr-erlauben <adresse>

<adresse> ist eine Adresse oder ein Netz (203.0.113.0/24). <dauer> in
Minuten, Stunden oder Tagen: 30m, 12h, 7d.

Alles laeuft ueber cscli im Container crowdsec - derselbe Weg, den die
Admin-Seite ueber das Auftragsbuch nimmt (A-01). Darum gibt es ihn auch
per SSH, wenn die Seite nicht erreichbar ist: etwa weil man sich selbst
ausgesperrt hat (crowdsec/LIESMICH.md).
"""
import datetime
import ipaddress
import json
import os
import re
import subprocess
import sys

HIER = os.path.dirname(os.path.realpath(__file__))
STACK = os.path.dirname(HIER)
# Von aussen setzbar nur fuer die Probe (werkzeuge/crowdsec-probe).
CONTAINER = os.environ.get("PROLO_FIREWALL_CONTAINER", "crowdsec")
LISTE = "prolo"                     # die Freigabeliste in CrowdSec
DAUER = re.compile(r"([1-9][0-9]{0,3})([mhd])")
MAX_DAUER_H = 24 * 365
# Ein Netz, das groesser ist, sperrt Unbeteiligte in Mengen - und ist
# fast immer ein Tippfehler (/8 statt /24).
MIN_PRAEFIX = {4: 16, 6: 48}
GRUND_MAX = 200
# Ein Bouncer, der laenger nicht gefragt hat, setzt nichts mehr durch.
BOUNCER_STILL_S = 120


class Nein(Exception):
    """Wird nicht getan - mit dem Grund im Klartext."""


def cscli(*args, zeit_s=60):
    try:
        r = subprocess.run(["docker", "exec", CONTAINER, "cscli"] + list(args),
                           capture_output=True, text=True, timeout=zeit_s)
    except subprocess.TimeoutExpired:
        return 124, "", "cscli antwortet nicht (%d s)" % zeit_s
    except OSError as e:
        return 127, "", "docker laesst sich nicht aufrufen: %s" % e
    return r.returncode, r.stdout, r.stderr


def cscli_json(*args):
    rc, aus, fehler = cscli(*(list(args) + ["-o", "json"]))
    if rc != 0:
        raise Nein("cscli %s: %s" % (" ".join(args), letzte_zeile(fehler) or "Rueckgabe %d" % rc))
    try:
        return json.loads(aus or "null")
    except ValueError:
        raise Nein("cscli %s lieferte kein JSON" % " ".join(args))


def letzte_zeile(text):
    zeilen = [z.strip() for z in (text or "").strip().splitlines() if z.strip()]
    # cscli schreibt 'level=error msg="..."' - die Meldung allein genuegt.
    z = zeilen[-1] if zeilen else ""
    m = re.search(r'msg="([^"]*)"', z)
    return m.group(1) if m else z


# ---------------------------------------------------------------- Pruefen
def adresse(text, zum_sperren):
    """Eine Adresse oder ein Netz - geprueft, bevor irgendetwas passiert (§11)."""
    text = (text or "").strip()
    try:
        netz = ipaddress.ip_network(text, strict=False)
    except ValueError:
        raise Nein("%r ist keine Adresse und kein Netz (so: 203.0.113.7 oder "
                   "203.0.113.0/24)" % text[:60])
    einzeln = "/" not in text
    if not einzeln and netz.prefixlen < MIN_PRAEFIX[netz.version]:
        raise Nein("%s ist zu gross - hoechstens /%d. Ein so grosses Netz sperrt "
                   "Unbeteiligte in Mengen." % (netz, MIN_PRAEFIX[netz.version]))
    # Gesperrt wird nur, was im Internet vorkommt. Privat, Docker-intern,
    # Tailscale (100.64.0.0/10), Dokumentation: darueber reden die Container
    # untereinander und mit Traefik - gesperrt waere der Stapel selbst.
    if zum_sperren and (not netz.is_global or netz.is_multicast):
        raise Nein("%s ist keine oeffentliche Adresse (privat, intern oder reserviert) - "
                   "darueber reden die Container mit Traefik. Gesperrt waere der Stapel "
                   "selbst." % text)
    wert = str(netz.network_address) if einzeln else str(netz)
    return ("ip" if einzeln else "range"), wert


def dauer(text):
    m = DAUER.fullmatch((text or "").strip())
    if not m:
        raise Nein("%r ist keine Dauer (so: 30m, 12h, 7d)" % (text or "")[:20])
    n, einheit = int(m.group(1)), m.group(2)
    stunden = {"m": n / 60, "h": n, "d": n * 24}[einheit]
    if stunden > MAX_DAUER_H:
        raise Nein("%s ist laenger als ein Jahr" % text)
    # cscli nimmt Go-Dauern: Tage kennt es nicht.
    return "%dm" % n if einheit == "m" else "%dh" % (n * 24 if einheit == "d" else n)


def grund(text):
    text = (text or "").strip()
    if not text:
        raise Nein("ohne Grund wird nichts gesperrt oder freigegeben - spaeter weiss "
                   "sonst niemand, warum")
    if len(text) > GRUND_MAX or not text.isprintable():
        raise Nein("der Grund ist zu lang (hoechstens %d Zeichen) oder hat Steuerzeichen"
                   % GRUND_MAX)
    return text


def wer():
    w = os.environ.get("PROLO_FIREWALL_WER") or os.environ.get("SUDO_USER") or "root"
    return re.sub(r"[^A-Za-z0-9._@-]", "", w)[:60] or "?"


# --------------------------------------------------------------- Freigaben
def freigaben():
    rc, aus, fehler = cscli("allowlists", "inspect", LISTE, "-o", "json")
    if rc != 0:
        if "not found" in (fehler + aus).lower():
            return []
        raise Nein("cscli allowlists inspect %s: %s" % (LISTE, letzte_zeile(fehler)))
    d = json.loads(aus or "{}")
    return [{"wert": i.get("value"), "grund": i.get("description") or "",
             "seit": i.get("created_at") or ""} for i in d.get("items") or []]


def liste_anlegen():
    rc, aus, fehler = cscli("allowlists", "inspect", LISTE, "-o", "json")
    if rc == 0:
        return
    rc, aus, fehler = cscli("allowlists", "create", LISTE, "-d",
                            "Adressen, die nie gesperrt werden (prolo firewall erlauben)")
    if rc != 0:
        raise Nein("die Freigabeliste liess sich nicht anlegen: %s" % letzte_zeile(fehler))


def auf_der_liste(wert):
    netz = ipaddress.ip_network(wert, strict=False)
    for f in freigaben():
        try:
            if ipaddress.ip_network(f["wert"], strict=False).overlaps(netz):
                return f
        except (ValueError, TypeError):
            continue
    return None


# ------------------------------------------------------------------ Taten
def sperren(a, d, g):
    art, wert = adresse(a, zum_sperren=True)
    go_dauer = dauer(d)
    g = grund(g)
    f = auf_der_liste(wert)
    if f:
        raise Nein("%s steht auf der Freigabeliste (%s: %s) - erst 'prolo firewall "
                   "nicht-mehr-erlauben %s'" % (wert, f["wert"], f["grund"], f["wert"]))
    rc, aus, fehler = cscli("decisions", "add", "--" + art, wert, "--duration", go_dauer,
                            "--type", "ban", "--reason", "von Hand (%s): %s" % (wer(), g))
    if rc != 0:
        raise Nein("cscli decisions add: %s" % letzte_zeile(fehler))
    return ("%s gesperrt fuer %s. Der Bouncer auf dem Server setzt das in wenigen "
            "Sekunden um." % (wert, d.strip()))


def entfernen(art, wert):
    rc, aus, fehler = cscli("decisions", "delete", "--" + art, wert)
    if rc != 0:
        raise Nein("cscli decisions delete: %s" % letzte_zeile(fehler))
    m = re.search(r"(\d+) decision\(s\) deleted", aus + fehler)
    return int(m.group(1)) if m else 0


def aufheben(a):
    art, wert = adresse(a, zum_sperren=False)
    n = entfernen(art, wert)
    if n == 0:
        return ("%s war nicht gesperrt - nichts zu tun. (Steht die Adresse auf einer "
                "Blockliste der Gemeinschaft, kommt sie mit der naechsten Liste wieder: "
                "dafuer 'prolo firewall erlauben'.)" % wert)
    return "%s ist wieder frei (%d Sperre(n) aufgehoben)." % (wert, n)


def erlauben(a, g):
    _, wert = adresse(a, zum_sperren=False)
    g = grund(g)
    liste_anlegen()
    rc, aus, fehler = cscli("allowlists", "add", LISTE, wert, "-d", g)
    if rc != 0:
        raise Nein("cscli allowlists add: %s" % letzte_zeile(fehler))
    # Eine bestehende Sperre hebt CrowdSec dabei selbst auf - gemessen an
    # 1.7.4, beim Bouncer (werkzeuge/crowdsec-probe). Ein eigenes Loeschen
    # hier war wirkungslos und ist darum weg; die Probe haelt fest, dass es
    # so bleibt.
    return ("%s steht auf der Freigabeliste und wird nie gesperrt - eine bestehende "
            "Sperre ist damit aufgehoben." % wert)


def nicht_mehr_erlauben(a):
    _, wert = adresse(a, zum_sperren=False)
    if not any(f["wert"] == wert for f in freigaben()):
        return "%s stand nicht auf der Freigabeliste - nichts zu tun." % wert
    rc, aus, fehler = cscli("allowlists", "remove", LISTE, wert)
    if rc != 0:
        raise Nein("cscli allowlists remove: %s" % letzte_zeile(fehler))
    return "%s steht nicht mehr auf der Freigabeliste." % wert


# ------------------------------------------------------------------- Lage
def eigene_regeln():
    """Was in crowdsec/regeln/ liegt - Name, Art, Beschreibung."""
    ordner = os.path.join(STACK, "crowdsec", "regeln")
    aus = []
    for n in sorted(os.listdir(ordner)) if os.path.isdir(ordner) else []:
        if not n.endswith((".yaml", ".yml")):
            continue
        t = open(os.path.join(ordner, n), encoding="utf-8", errors="replace").read()
        feld = {k: (re.search(r"(?m)^%s:\s*\"?([^\"\n]*)\"?\s*$" % k, t) or [None, ""])[1]
                for k in ("name", "type", "description", "capacity", "leakspeed")}
        aus.append({"datei": n, "name": feld["name"], "art": feld["type"],
                    "beschreibung": feld["description"],
                    "mass": ("sofort" if feld["type"] == "trigger" else
                             "%s in Folge, einer weniger alle %s" %
                             (int(feld["capacity"] or 0) + 1, feld["leakspeed"]))})
    return aus


def alter_s(zeit):
    """Sekunden seit einer Zeit von cscli ('2026-09-30T09:30:01.747290317Z', UTC)."""
    try:
        t = datetime.datetime.strptime((zeit or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    jetzt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return int((jetzt - t).total_seconds())


def lage():
    l = {"stand": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
         "crowdsec": {"laeuft": False, "gesundheit": ""}, "bouncer": [], "sperren": [],
         "gemeinschaft": 0, "meldungen": [], "freigaben": [], "regeln": eigene_regeln(),
         "gelesen": {}, "fehler": []}
    try:
        r = subprocess.run(["docker", "inspect", CONTAINER, "--format",
                            "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}"],
                           capture_output=True, text=True, timeout=30)
        teile = r.stdout.split()
        l["crowdsec"] = {"laeuft": bool(teile) and teile[0] == "true",
                         "gesundheit": teile[1] if len(teile) > 1 else ""}
    except (OSError, subprocess.TimeoutExpired) as e:
        l["fehler"].append("docker inspect: %s" % e)
    if not l["crowdsec"]["laeuft"]:
        l["fehler"].append("CrowdSec laeuft nicht - sudo prolo start crowdsec")
        return l

    def versuch(was, f):
        try:
            return f()
        except Nein as e:
            l["fehler"].append("%s: %s" % (was, e))
        except (ValueError, KeyError, TypeError) as e:
            l["fehler"].append("%s: unerwartete Antwort (%s)" % (was, e))
        return None

    for b in versuch("Bouncer", lambda: cscli_json("bouncers", "list")) or []:
        l["bouncer"].append({"name": b.get("name"), "version": b.get("version") or "",
                             "letzte_abfrage": b.get("last_pull") or "",
                             "still_s": alter_s(b.get("last_pull")),
                             "abgemeldet": bool(b.get("revoked"))})
    for a in versuch("Sperren", lambda: cscli_json("decisions", "list", "--limit", "500")) or []:
        quelle = a.get("source") or {}
        for e in a.get("decisions") or []:
            l["sperren"].append({"wert": e.get("value"), "art": (e.get("scope") or "").lower(),
                                 "regel": e.get("scenario") or "", "herkunft": e.get("origin") or "",
                                 "bleibt": dauer_lesbar(e.get("duration") or ""),
                                 "land": quelle.get("cn") or "",
                                 "netzbetreiber": quelle.get("as_name") or ""})
    m = versuch("Zahlen", lambda: cscli_json("metrics", "show", "decisions")) or {}
    for regel in (m.get("decisions") or {}).values():
        for herkunft, arten in (regel or {}).items():
            if herkunft.upper() in ("CAPI", "LISTS"):
                l["gemeinschaft"] += sum(v for v in (arten or {}).values() if isinstance(v, int))
    for a in versuch("Meldungen", lambda: cscli_json("alerts", "list", "--limit", "100",
                                                   "--since", "168h")) or []:
        q = a.get("source") or {}
        l["meldungen"].append({"zeit": a.get("created_at") or "", "regel": a.get("scenario") or "",
                               "adresse": q.get("value") or q.get("ip") or "",
                               "land": q.get("cn") or "", "anzahl": a.get("events_count") or 0,
                               "zur_sperre": bool(a.get("decisions")),
                               "beobachtet": bool(a.get("simulated"))})
    l["freigaben"] = versuch("Freigaben", freigaben) or []
    # Jede Datei aus erfassung/ steht da - auch mit 0 Zeilen. Eine Quelle,
    # aus der nie etwas kommt, ist der Hinweis auf einen falschen Pfad.
    for q in erfasste_dateien():
        l["gelesen"][q] = {"zeilen": 0, "erkannt": 0}
    g = versuch("Erfassung", lambda: cscli_json("metrics", "show", "acquisition")) or {}
    for quelle, zahl in (g.get("acquisition") or {}).items():
        l["gelesen"][quelle.split(":", 1)[-1]] = {"zeilen": (zahl or {}).get("reads", 0),
                                                  "erkannt": (zahl or {}).get("parsed", 0)}
    return l


def erfasste_dateien():
    ordner = os.path.join(STACK, "crowdsec", "erfassung")
    aus = []
    for n in sorted(os.listdir(ordner)) if os.path.isdir(ordner) else []:
        t = open(os.path.join(ordner, n), encoding="utf-8", errors="replace").read()
        aus += re.findall(r"(?m)^\s*-\s*(/\S+)\s*$", t)
    return aus


def dauer_lesbar(text):
    """'311h59m48.1s' -> '13 Tage', '23h57m29s' -> '23 h 57 min'."""
    h = re.search(r"(\d+)h", text)
    m = re.search(r"(\d+)m(?!s)", text)
    h, m = (int(h.group(1)) if h else 0), (int(m.group(1)) if m else 0)
    if h >= 48:
        return "%d Tage" % ((h + 12) // 24)
    if h:
        return "%d h %d min" % (h, m)
    return "%d min" % max(m, 1)


def lage_text(l):
    z = []
    c = l["crowdsec"]
    z.append("CrowdSec     %s" % ("laeuft" + (" (%s)" % c["gesundheit"] if c["gesundheit"] else "")
                                  if c["laeuft"] else "LAEUFT NICHT - sudo prolo start crowdsec"))
    if not l["bouncer"] and c["laeuft"]:
        z.append("Bouncer      KEINER angemeldet - CrowdSec erkennt, aber niemand sperrt."
                 " sudo prolo einrichten richtet ihn ein.")
    for b in l["bouncer"]:
        if b["still_s"] is None:
            zustand = "hat noch nie abgefragt - laeuft er? systemctl status crowdsec-firewall-bouncer"
        elif b["still_s"] > BOUNCER_STILL_S:
            zustand = "seit %d min still - setzt nichts mehr durch. systemctl status " \
                      "crowdsec-firewall-bouncer" % (b["still_s"] // 60)
        else:
            zustand = "holt die Sperren ab (zuletzt vor %d s)" % b["still_s"]
        z.append("Bouncer      %s: %s" % (b["name"], zustand))
    z.append("Sperren      %d eigene, %d aus der Gemeinschafts-Blockliste"
             % (len(l["sperren"]), l["gemeinschaft"]))
    for s in l["sperren"][:20]:
        z.append("  %-18s %-28s noch %-10s %s" % (s["wert"], s["regel"][:28], s["bleibt"],
                                                 s["land"]))
    z.append("Meldungen    %d in 7 Tagen" % len(l["meldungen"]))
    for m in l["meldungen"][:10]:
        z.append("  %s  %-18s %-28s %s" % (m["zeit"][:16].replace("T", " "), m["adresse"],
                                           m["regel"][:28], "-> Sperre" if m["zur_sperre"] else ""))
    z.append("Freigaben    %d" % len(l["freigaben"]))
    for f in l["freigaben"]:
        z.append("  %-18s %s" % (f["wert"], f["grund"]))
    z.append("Gelesen")
    for q, n in sorted(l["gelesen"].items()):
        z.append("  %-34s %d Zeilen, %d erkannt%s" % (q, n["zeilen"], n["erkannt"],
                 "" if n["zeilen"] else " - seit dem Start nichts gelesen"))
    z.append("Eigene Regeln")
    for r in l["regeln"]:
        z.append("  %-28s %s - %s" % (r["name"], r["mass"], r["beschreibung"]))
    for f in l["fehler"]:
        z.append("FEHLER       %s" % f)
    return "\n".join(z)


# ------------------------------------------------------------------- Aufruf
def main(argv):
    args = argv[1:]
    try:
        if not args:
            print(lage_text(lage()))
            return 0
        if args == ["--json"]:
            print(json.dumps(lage(), ensure_ascii=False, indent=1))
            return 0
        befehl, rest = args[0], args[1:]
        taten = {"sperren": (sperren, 3), "aufheben": (aufheben, 1),
                 "erlauben": (erlauben, 2), "nicht-mehr-erlauben": (nicht_mehr_erlauben, 1)}
        if befehl not in taten:
            raise Nein("unbekannt: %s - moeglich: %s, --json" % (befehl, ", ".join(taten)))
        f, n = taten[befehl]
        if len(rest) != n:
            raise Nein("%s braucht %d Angabe(n) - siehe 'prolo hilfe'" % (befehl, n))
        print(f(*rest))
        return 0
    except Nein as e:
        print("Nicht getan: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
