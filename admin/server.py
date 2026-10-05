#!/usr/bin/env python3
"""ProloWelt Admin - der Stand des Unterbaus und der Tools, und die Griffe dazu.

Was die Seite NICHT hat: Zugriff auf Docker. Wer den hat, hat root - und
eine Webseite ist die Stelle, an der man am ehesten hereinkommt. Sie liest,
was der Agent auf dem Server (prolo agent) alle 30 s nach
/agent/aus/status.json schreibt, und sie legt AUFTRAEGE in /agent/ein ab.
Ausgeführt werden die vom Agenten, über prolo - mit denselben Prüfungen
wie auf der Kommandozeile. Welche Aufträge es gibt und in welcher Form,
steht in kern/auftrag.py, das Seite und Agent gemeinsam benutzen.

Wer darf: wer bei Authentik angemeldet ist UND in der Gruppe ADMIN_GRUPPE
(Vorgabe "authentik Admins"). Die Anmeldung kommt als Kopfzeile von
Traefik; Traefik löscht am Eingang jede mitgeschickte X-Authentik-*.
Erreichbar ist die Seite nur über Traefik: ihr Netz prolo-admin teilt sie
mit niemandem sonst.

Standardbibliothek und SQLite, kein Fremdpaket.
"""
import datetime
import html
import json
import os
import re
import secrets
import signal
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kern import auftrag  # noqa: E402

VERSION = os.environ.get("PROLO_VERSION", "?")
PORT = int(os.environ.get("ADMIN_PORT", "8080"))
DATEN = os.environ.get("ADMIN_DATEN", "/daten")
AGENT = os.environ.get("ADMIN_AGENT", "/agent")
EIN = os.path.join(AGENT, "ein")
AUS = os.path.join(AGENT, "aus")
GRUPPE = os.environ.get("ADMIN_GRUPPE", "authentik Admins")
DOMAIN = os.environ.get("PROLO_DOMAIN", "")
SCHRIFTEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schriften")
THEMEN = ("system", "hell", "dunkel")
STATUS_ALT_S = 180
MAX_FORMULAR = 3 * auftrag.MAX_COMPOSE + 16 * 1024


class Antwort(Exception):
    def __init__(self, kode, text):
        super().__init__(text)
        self.kode, self.text = kode, text


# ------------------------------------------------------------- Daten
def verbindung():
    k = sqlite3.connect(os.path.join(DATEN, "admin.db"), timeout=5)
    k.row_factory = sqlite3.Row
    return k


def datenbank_anlegen():
    os.makedirs(DATEN, exist_ok=True)
    with verbindung() as k:
        k.execute("CREATE TABLE IF NOT EXISTS nutzer (nutzer_id TEXT PRIMARY KEY, "
                  "anzeigename TEXT, email TEXT, thema TEXT NOT NULL DEFAULT 'system')")


def nutzer_holen(kennung, name, email):
    """Wiedererkannt am Anmeldenamen - die E-Mail kann sich ändern."""
    with verbindung() as k:
        k.execute("INSERT INTO nutzer (nutzer_id, anzeigename, email) VALUES (?,?,?) "
                  "ON CONFLICT(nutzer_id) DO UPDATE SET anzeigename=excluded.anzeigename, "
                  "email=excluded.email", (kennung, name, email))
        return dict(k.execute("SELECT * FROM nutzer WHERE nutzer_id=?", (kennung,)).fetchone())


def thema_setzen(kennung, thema):
    if thema not in THEMEN:
        raise Antwort(400, "Unbekannte Darstellung.")
    with verbindung() as k:
        k.execute("UPDATE nutzer SET thema=? WHERE nutzer_id=?", (thema, kennung))


def json_datei(pfad, grenze=4 * 1024 * 1024):
    try:
        with open(pfad, "rb") as f:
            roh = f.read(grenze + 1)
        if len(roh) > grenze:
            return None
        return json.loads(roh.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def status_lesen():
    s = json_datei(os.path.join(AUS, "status.json"))
    if not isinstance(s, dict):
        return None, None
    alter = alter_s((s.get("agent") or {}).get("zeit") or s.get("zeit"))
    return s, alter


def alter_s(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso))
        return (datetime.datetime.now(t.tzinfo) - t).total_seconds()
    except (TypeError, ValueError):
        return None


def auftraege(grenze=50, name=None):
    """Erledigte und laufende aus aus/, wartende aus ein/ - neueste zuerst."""
    liste = []
    try:
        for n in os.listdir(EIN):
            k = n[:-5]
            if n.endswith(".json") and auftrag.KENNUNG.fullmatch(k):
                d = json_datei(os.path.join(EIN, n), auftrag.MAX_AUFTRAG) or {}
                f = d.get("felder") or {}
                liste.append({"kennung": k, "art": d.get("art"), "status": "wartet",
                              "wer": d.get("wer"), "eingang": d.get("zeit"),
                              "titel": auftrag.ARTEN.get(d.get("art"), ((), (), "?", 0))[2],
                              "felder": {x: f.get(x) for x in ("name", "stand") if f.get(x)}})
    except FileNotFoundError:
        pass
    try:
        namen = sorted((n for n in os.listdir(AUS) if n.endswith(".json")
                        and auftrag.KENNUNG.fullmatch(n[:-5])), reverse=True)
    except FileNotFoundError:
        namen = []
    for n in namen[:400]:
        d = json_datei(os.path.join(AUS, n))
        if isinstance(d, dict):
            liste.append(d)
    if name:
        liste = [a for a in liste if (a.get("felder") or {}).get("name") == name]
    liste.sort(key=lambda a: a.get("kennung", ""), reverse=True)
    return liste[:grenze]


def auftrag_lesen(kennung):
    if not auftrag.KENNUNG.fullmatch(kennung or ""):
        raise Antwort(404, "Diesen Auftrag gibt es nicht.")
    lage = json_datei(os.path.join(AUS, kennung + ".json"))
    if lage is None:
        if os.path.exists(os.path.join(EIN, kennung + ".json")):
            return {"kennung": kennung, "status": "wartet"}, ""
        raise Antwort(404, "Diesen Auftrag gibt es nicht (mehr).")
    try:
        with open(os.path.join(AUS, kennung + ".log"), "rb") as f:
            f.seek(0, 2)
            groesse = f.tell()
            f.seek(max(0, groesse - 256 * 1024))
            ausgabe = f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        ausgabe = ""
    return lage, ausgabe


def tool_holen(name, s=None):
    """Ein Tool aus dem Stand des Servers - oder 404."""
    if s is None:
        s, _ = status_lesen()
    t = next((x for x in (s or {}).get("tools") or [] if x.get("name") == name), None)
    if t is None or not auftrag.NAME.fullmatch(name):
        raise Antwort(404, "Ein Tool '%s' kennt der Server nicht. Alle Tools: /tools" % name[:40])
    return t


def auftrag_ablegen(art, felder, wer):
    daten = {"art": art, "felder": {k: v for k, v in felder.items() if v}, "wer": wer,
             "zeit": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    try:
        auftrag.pruefen(daten)
    except auftrag.Ungueltig as u:
        raise Antwort(400, str(u))
    kennung = "%s-%s" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S"),
                         secrets.token_hex(4))
    neu = os.path.join(EIN, kennung + ".neu")
    try:
        with open(os.open(neu, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w",
                  encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False)
        os.replace(neu, os.path.join(EIN, kennung + ".json"))
    except OSError:
        raise Antwort(503, "Der Auftrag ließ sich nicht ablegen - das Auftragsbuch fehlt. "
                           "Auf dem Server:  sudo prolo einrichten")
    return kennung


# ----------------------------------------------------- Darstellung
def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def zahl(n, stellen=1):
    """1234.5 -> '1.234,5' (deutsch, §7)."""
    t = "{:,.{}f}".format(n, stellen)
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


def bytes_text(n):
    n = float(n or 0)
    for einheit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or einheit == "TB":
            return ("%d %s" % (n, einheit)) if einheit == "B" else \
                   ("%s %s" % (zahl(n), einheit))
        n /= 1024
    return "-"


def wert_und_einheit(n):
    """Fuer eine Kennzahl: Zahl und Einheit getrennt - die Einheit steht
    daneben, kleiner (§5). Der schmale Abstand hat in Sora keine Breite."""
    zahl_, _, einheit = bytes_text(n).partition("\u202f")
    return zahl_, einheit


def zeit_kurz(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso)).strftime("%d.%m. %H:%M")
    except ValueError:
        return ""


def zeit(iso):
    """Der Browser setzt sie in die Ortszeit - der Container kennt nur UTC."""
    k = zeit_kurz(iso)
    return '<time datetime="%s">%s</time>' % (e(iso), e(k)) if k else "-"


def vor(sekunden):
    if sekunden is None:
        return "-"
    if sekunden < 90:
        return "gerade eben"
    if sekunden < 5400:
        return "vor %d Min." % (sekunden // 60)
    if sekunden < 172800:
        return "vor %d Std." % (sekunden // 3600)
    return "vor %d Tagen" % (sekunden // 86400)


# Farbe ist nie die einzige Information (§2): jeder Marker traegt das Wort.
ZUSTAND = {
    "gesund": ("m-gut", "gesund"), "laeuft": ("m-gut", "läuft"),
    "startet": ("m-weg", "startet"), "krank": ("m-rot", "krank"),
    "teilweise": ("m-rot", "teilweise"), "aus": ("m-warm", "angehalten"),
}
AUFTRAG = {
    "ok": ("m-gut", "erledigt"), "fehler": ("m-rot", "fehlgeschlagen"),
    "abgelehnt": ("m-warm", "abgelehnt"), "laeuft": ("m-weg", "läuft"),
    "wartet": ("m-weg", "wartet"),
}
STUFE = {"fehler": ("m-rot", "Fehler"), "warn": ("m-warm", "Achtung"), "info": ("m-weg", "Hinweis")}


def marker(tabelle, wert):
    klasse, wort = tabelle.get(wert, ("m-warm", wert or "?"))
    return '<span class="marker %s">%s</span>' % (klasse, e(wort))


def anmeldung_marker(a):
    if a == "authentik":
        return '<span class="marker m-gut">Authentik</span>'
    return '<span class="marker m-warm">ohne Anmeldung</span>'


TOKENS = """
:root{
  --bg:oklch(0.96 0.004 250); --app:oklch(0.985 0.002 250); --surface:#fff;
  --chrome:oklch(0.995 0.001 250); --line:oklch(0.92 0.004 250);
  --line-soft:oklch(0.96 0.002 250); --hover:oklch(0.96 0.003 250);
  --ink:oklch(0.2 0.01 250); --ink-2:oklch(0.3 0.01 250); --ink-3:oklch(0.52 0.01 250);
  --accent:oklch(0.52 0.17 262); --accent-hover:oklch(0.45 0.17 262);
  --accent-soft:oklch(0.94 0.02 262); --accent-ink:oklch(0.38 0.13 262);
  --on-accent:oklch(0.99 0.002 250); --bar:oklch(0.86 0.03 262);
  --good:oklch(0.45 0.14 158); --good-soft:oklch(0.97 0.01 158);
  --warm-soft:oklch(0.94 0.01 60); --warm-ink:oklch(0.45 0.08 60);
  --danger:oklch(0.52 0.18 25); --overlay:oklch(0.28 0.02 258);
  --feature:oklch(0.34 0.12 262); --feature-ink:oklch(0.99 0.002 250);
  --feature-ink-2:oklch(0.86 0.03 262); --feature-line:oklch(0.46 0.11 262);
  --feature-good:oklch(0.88 0.16 158); --track:oklch(0.94 0.004 250);
  --shadow:0 24px 60px -20px oklch(0.4 0.03 250 / 0.22);
}
body[data-theme="dark"]{
  --bg:oklch(0.16 0.012 258); --app:oklch(0.2 0.012 258);
  --surface:oklch(0.235 0.013 258); --chrome:oklch(0.205 0.012 258);
  --line:oklch(0.31 0.014 258); --line-soft:oklch(0.27 0.012 258); --hover:oklch(0.27 0.013 258);
  --ink:oklch(0.96 0.004 250); --ink-2:oklch(0.87 0.006 250); --ink-3:oklch(0.69 0.01 250);
  --accent:oklch(0.62 0.16 262); --accent-hover:oklch(0.69 0.16 262);
  --accent-soft:oklch(0.33 0.06 262); --accent-ink:oklch(0.85 0.09 262); --bar:oklch(0.38 0.06 262);
  --on-accent:oklch(0.16 0.012 258);
  --good:oklch(0.8 0.14 158); --good-soft:oklch(0.29 0.05 158);
  --warm-soft:oklch(0.33 0.05 60); --warm-ink:oklch(0.86 0.08 60);
  --danger:oklch(0.7 0.16 25); --overlay:oklch(0.2 0.012 258);
  --feature:oklch(0.31 0.07 262); --feature-ink:oklch(0.97 0.004 250);
  --feature-ink-2:oklch(0.8 0.02 250); --feature-line:oklch(0.42 0.05 262);
  --feature-good:oklch(0.85 0.15 158); --track:oklch(0.3 0.014 258);
  --shadow:0 24px 60px -20px oklch(0.05 0 0 / 0.6);
}
"""

STIL = """
@font-face{font-family:Sora;src:url(/schriften/sora-latin.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:Sora;src:url(/schriften/sora-latin-ext.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0100-02AF,U+0304,U+0308,U+0329,U+1E00-1E9F,U+2020-20AB}
@font-face{font-family:'Instrument Sans';src:url(/schriften/instrument-latin.woff2)format('woff2');
  font-weight:400 700;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:'Instrument Sans';src:url(/schriften/instrument-latin-ext.woff2)format('woff2');
  font-weight:400 700;font-display:swap;unicode-range:U+0100-02AF,U+1E00-1E9F,U+2020-20AB}
@font-face{font-family:'JetBrains Mono';src:url(/schriften/jetbrains-latin.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+2000-206F,U+20AC,U+2122,U+2212}
@font-face{font-family:'JetBrains Mono';src:url(/schriften/jetbrains-latin-ext.woff2)format('woff2');
  font-weight:100 800;font-display:swap;unicode-range:U+0100-02AF,U+1E00-1E9F,U+2020-20AB}

/* Muss VOR allen display-Regeln stehen (CLAUDE.md §8.1). */
[hidden]{display:none!important}

*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--ink-2);
  font-family:'Instrument Sans',system-ui,sans-serif;font-size:14px;line-height:1.5;
  -webkit-text-size-adjust:100%}
h1,h2,h3{font-family:Sora,'Instrument Sans',sans-serif;font-weight:600;
  letter-spacing:-0.02em;color:var(--ink);margin:0}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
p{margin:0}

button:focus-visible, a:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }

.huelle{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
.seite{background:var(--chrome);border-right:1px solid var(--line);
  display:flex;flex-direction:column;padding:20px 0}
.marke{display:flex;gap:10px;align-items:center;padding:0 20px 22px;color:inherit;text-decoration:none}
.marke.klein{display:none}
.kachel{width:30px;height:30px;border-radius:8px;background:var(--accent);color:var(--on-accent);
  display:grid;place-items:center;font-family:Sora,sans-serif;font-weight:600;font-size:16px;flex:none}
.marke .n{font-family:Sora,sans-serif;font-weight:600;font-size:14px;color:var(--ink);line-height:1.2}
.marke .u{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3)}
nav.haupt-nav{display:flex;flex-direction:column;flex:1}
nav.haupt-nav a{display:flex;align-items:center;min-height:44px;padding:0 20px;
  color:var(--ink-2);text-decoration:none;border-left:4px solid transparent;font-weight:500}
nav.haupt-nav a:hover{background:var(--hover)}
nav.haupt-nav a[aria-current=page]{border-left-color:var(--accent);background:var(--accent-soft);
  color:var(--accent-ink);font-weight:600}
nav.haupt-nav .unten{margin-top:auto}

.haupt{min-width:0;display:flex;flex-direction:column}
header{min-height:76px;background:var(--chrome);border-bottom:1px solid var(--line);
  display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 32px}
header .titel{min-width:0}
header h1{font-size:21px}
.ktx{font-size:12px;color:var(--ink-3)}
header .rechts{display:flex;align-items:center;gap:12px}
header a.ich{color:var(--ink-2);text-decoration:none;font-weight:500;min-height:44px;
  display:flex;align-items:center;padding:0 10px;border-radius:10px}
header a.ich:hover{background:var(--hover)}
main{padding:24px 32px 64px;max-width:1280px;margin:0 auto;width:100%;min-width:0;
  display:flex;flex-direction:column;gap:20px}

.karte{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px;min-width:0}
.karte > h2{font-size:15px}
.karte > h2 + .ktx{margin-top:2px}
.reihe{display:grid;gap:16px;min-width:0}
.reihe > *{min-width:0}
.kpi4{grid-template-columns:repeat(4,minmax(0,1fr))}
.kpi3{grid-template-columns:repeat(3,minmax(0,1fr))}
.zwei{grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);align-items:start}
.kpi .lbl{font-size:12px;color:var(--ink-3)}
.kpi .wert{font-family:Sora,sans-serif;font-weight:600;font-size:30px;color:var(--ink);
  letter-spacing:-0.02em;line-height:1.15;margin-top:2px;overflow-wrap:anywhere}
.kpi .wert small{font-size:14px;color:var(--ink-3);font-weight:500;letter-spacing:0}
.kpi .sub{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--ink-3);margin-top:4px}
a.kpi-verweis{text-decoration:none;color:inherit;display:block;border-radius:14px}
a.kpi-verweis:hover .karte{background:var(--hover)}

.feature{background:var(--feature);color:var(--feature-ink);border:1px solid var(--feature-line);
  border-radius:14px;padding:18px;min-width:0}
.feature .lbl{color:var(--feature-ink-2);font-size:12px}
.feature .wert{font-family:Sora,sans-serif;font-weight:600;font-size:30px;letter-spacing:-0.02em;
  line-height:1.15;margin-top:2px}
.feature .sub{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--feature-ink);margin-top:4px}

.tabelle{overflow-x:auto;margin-top:12px}
table{width:100%;border-collapse:collapse}
thead th{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);text-align:left;font-weight:500;
  padding:0 12px 8px 0;white-space:nowrap}
tbody td{font-size:13px;color:var(--ink-2);padding:6px 12px 6px 0;
  border-top:1px solid var(--line-soft);vertical-align:middle}
tbody tr:hover{background:var(--hover)}
td.z, th.z{text-align:right}
td.z{font-family:'JetBrains Mono',monospace}
td.lang{overflow-wrap:anywhere}
td.knapp{white-space:nowrap;width:1%}
.nur-schmal{display:none}

.marker{display:inline-block;padding:2px 7px;border-radius:5px;font-size:11px;font-weight:600;
  white-space:nowrap}
.m-gut{background:var(--good-soft);color:var(--good)}
.m-warm{background:var(--warm-soft);color:var(--warm-ink)}
.m-weg{background:var(--accent-soft);color:var(--accent-ink)}
.m-rot{background:var(--danger);color:var(--on-accent)}

.leer{color:var(--ink-3);font-size:13px;padding:12px 0 0}
.hinweis{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;
  border-top:1px solid var(--line-soft);padding:12px 0}
.hinweis:first-of-type{border-top:0}
.hinweis > .marker{align-self:start}
.hinweis .was{color:var(--ink);font-size:13px}
.hinweis .tat{grid-column:2;font-family:'JetBrains Mono',monospace;font-size:12px;
  color:var(--ink-2);overflow-wrap:anywhere}

a.zeile, a.mehr{font-weight:600;text-decoration:none;display:inline-flex;align-items:center;
  min-height:44px;min-width:44px}
a.zeile{color:var(--ink)}
a.mehr{color:var(--accent-ink)}
a.zeile:hover, a.mehr:hover{text-decoration:underline}
a.extern{color:var(--accent-ink);text-decoration:none;overflow-wrap:anywhere;
  display:inline-flex;align-items:center;min-height:44px}
a.extern:hover{text-decoration:underline}

.aktionen{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:14px}
.aktionen form{margin:0}
.knopf, .knopf-rahmen{display:inline-flex;align-items:center;justify-content:center;
  min-height:44px;padding:0 18px;border-radius:10px;font:inherit;font-weight:600;
  cursor:pointer;text-decoration:none;white-space:nowrap}
.knopf{background:var(--accent);color:var(--on-accent);border:0}
.knopf:hover{background:var(--accent-hover)}
.knopf-rahmen{background:transparent;color:var(--ink);border:1px solid var(--line)}
.knopf-rahmen:hover{background:var(--hover)}
.knopf-gefahr{color:var(--danger);border-color:var(--danger)}
button:disabled{opacity:.55;cursor:not-allowed}

.formular{display:flex;flex-direction:column;gap:16px;margin-top:14px;max-width:760px}
.feld{display:flex;flex-direction:column;gap:6px;min-width:0}
.feld label, .feld .lbl{font-size:12px;color:var(--ink-3)}
.feld input, .feld select, .feld textarea{border:1px solid var(--line);border-radius:10px;
  background:var(--surface);color:var(--ink);font:inherit;min-width:0;padding:0 12px}
.feld input, .feld select{min-height:44px;font-family:'JetBrains Mono',monospace;font-size:13px}
.feld textarea{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.5;
  padding:10px 12px;min-height:120px;resize:vertical}
.feld textarea.gross{min-height:300px}
.erkl{font-size:12px;color:var(--ink-3);overflow-wrap:anywhere}
.zeile2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
fieldset{border:1px solid var(--line-soft);border-radius:10px;padding:10px 14px;margin:0;min-width:0}
legend{font-size:12px;color:var(--ink-3);padding:0 4px}
label.wahl{display:flex;gap:10px;align-items:flex-start;min-height:44px;padding:8px 0;
  color:var(--ink-2);cursor:pointer}
label.wahl input{margin-top:3px;width:18px;height:18px;flex:none;accent-color:var(--accent)}
label.wahl b{color:var(--ink);font-weight:600}

.segment{display:inline-flex;background:var(--track);border-radius:10px;padding:3px;gap:3px;
  flex-wrap:wrap}
.segment button{border:0;background:transparent;color:var(--ink-3);font:inherit;font-weight:600;
  font-size:13px;border-radius:8px;padding:0 14px;min-height:44px;cursor:pointer}
.segment button[aria-pressed=true]{background:var(--surface);color:var(--ink);
  box-shadow:0 1px 2px oklch(0.4 0.03 250 / .18)}

dl.fakten{display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px 16px;margin:14px 0 0}
dl.fakten dt{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-3);padding-top:2px}
dl.fakten dd{margin:0;color:var(--ink-2);overflow-wrap:anywhere;min-width:0}

pre.ausgabe{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.5;color:var(--ink-2);
  background:var(--app);border:1px solid var(--line-soft);border-radius:10px;padding:12px;
  margin:14px 0 0;white-space:pre-wrap;overflow-wrap:anywhere;max-height:65vh;overflow:auto}
.banner{border:1px solid var(--line);border-left:4px solid var(--danger);background:var(--surface);
  border-radius:14px;padding:14px 18px;color:var(--ink)}
.banner.gut{border-left-color:var(--good)}
.banner .tat{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--ink-2);margin-top:4px;
  overflow-wrap:anywhere}

.tabbar{display:none}
@media (max-width:1100px){ .kpi4{grid-template-columns:repeat(2,minmax(0,1fr))} }
@media (max-width:900px){
  /* Am Handy nichts unter 12 px (§3). */
  thead th, dl.fakten dt, .marker, .kpi .sub, .feature .sub, .marke .u{font-size:12px}
  .zwei, .zeile2{grid-template-columns:minmax(0,1fr)}
  .huelle{grid-template-columns:minmax(0,1fr)}
  .seite{display:none}
  header{padding:12px 20px;min-height:auto;flex-wrap:wrap;justify-content:flex-start;gap:6px 10px}
  .marke.klein{display:flex;padding:0;flex:1 1 auto;min-height:44px}
  .marke.klein .kachel{width:26px;height:26px;font-size:14px}
  header .titel{flex:1 1 100%;order:3}
  header .rechts{margin-left:auto}
  main{padding:16px 20px calc(88px + env(safe-area-inset-bottom));gap:16px}
  .karte, .feature{border-radius:18px}
  .tabbar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));position:fixed;left:0;right:0;
    bottom:0;background:var(--chrome);border-top:1px solid var(--line);
    padding-bottom:env(safe-area-inset-bottom);z-index:5}
  .tabbar a{min-height:56px;display:flex;align-items:center;justify-content:center;
    color:var(--ink-3);text-decoration:none;font-size:12px;font-weight:600;
    border-top:3px solid transparent;padding:0 2px;text-align:center;overflow:hidden}
  /* --accent-ink statt --accent: 12 px brauchen 4.5:1 (§8). */
  .tabbar a[aria-current=page]{color:var(--accent-ink);border-top-color:var(--accent)}
  .nur-breit{display:none}
  .nur-schmal{display:block}
}
@media (max-width:480px){ .kpi4,.kpi3{grid-template-columns:minmax(0,1fr)} }
"""

NAV = (("/", "Übersicht"), ("/tools", "Tools"), ("/sicherungen", "Sicherungen"),
       ("/auftraege", "Aufträge"), ("/einstellungen", "Einstellungen"))
TABS = (("/", "Übersicht"), ("/tools", "Tools"), ("/sicherungen", "Sicherungen"),
        ("/einstellungen", "Einstellungen"))

SKRIPT = """<script>
(function(){
  var w = %(thema)s;
  function an(){
    var d = (w === 'system')
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : (w === 'dunkel' ? 'dark' : 'light');
    document.body.dataset.theme = d;
  }
  an();
  try { window.matchMedia('(prefers-color-scheme: dark)')
          .addEventListener('change', function(){ if (w === 'system') an(); }); } catch (x) {}
  // Nicht doppelt absenden (§10); was fragen soll, fragt vorher. Gesperrt
  // wird erst nach dem Absenden - sonst fehlte der Wert des Knopfs.
  document.addEventListener('submit', function(ev){
    var f = ev.target, frage = f.getAttribute('data-frage');
    if (frage && !window.confirm(frage)) { ev.preventDefault(); return; }
    setTimeout(function(){
      var k = f.querySelectorAll('button');
      for (var i = 0; i < k.length; i++) { k[i].disabled = true; }
    }, 0);
  });
  var z = document.querySelectorAll('time[datetime]');
  function zw(n){ return (n < 10 ? '0' : '') + n; }
  for (var q = 0; q < z.length; q++) {
    var d = new Date(z[q].getAttribute('datetime'));
    if (!isNaN(d)) z[q].textContent = zw(d.getDate()) + '.' + zw(d.getMonth() + 1) + '. '
                                      + zw(d.getHours()) + ':' + zw(d.getMinutes());
  }
  // Die Quelle eines neuen Tools: nur die passenden Felder zeigen.
  var wahl = document.querySelectorAll('input[name=quelle]');
  function quelle(){
    for (var i = 0; i < wahl.length; i++) {
      var teil = document.getElementById('q-' + wahl[i].value);
      if (teil) teil.hidden = !wahl[i].checked;
    }
  }
  for (var j = 0; j < wahl.length; j++) wahl[j].addEventListener('change', quelle);
  quelle();
  var p = document.querySelectorAll('pre.ausgabe');
  for (var k = 0; k < p.length; k++) p[k].scrollTop = p[k].scrollHeight;
})();
</script>"""


def seite(titel, ktx, inhalt, pfad, nutzer, knopf="", nachher=""):
    nav = "".join('<a href="%s"%s%s>%s</a>' % (
        p, ' aria-current="page"' if p == pfad else "",
        ' class="unten"' if p == "/einstellungen" else "", e(t)) for p, t in NAV)
    tabs = "".join('<a href="%s"%s>%s</a>' % (p, ' aria-current="page"' if p == pfad else "", e(t))
                   for p, t in TABS)
    ich = nutzer.get("anzeigename") or nutzer.get("nutzer_id") or ""
    return """<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>%(titel)s - ProloWelt</title>
<style>%(tokens)s%(stil)s</style>
</head>
<body data-theme="dark">
<div class="huelle">
  <div class="seite">
    <a class="marke" href="/"><span class="kachel" aria-hidden="true">P</span>
      <span><span class="n">ProloWelt</span><br><span class="u">Verwaltung</span></span></a>
    <nav class="haupt-nav" aria-label="Bereiche">%(nav)s</nav>
  </div>
  <div class="haupt">
    <header>
      <a class="marke klein" href="/"><span class="kachel" aria-hidden="true">P</span>
        <span class="n">ProloWelt</span></a>
      <div class="titel"><h1>%(titel)s</h1><div class="ktx">%(ktx)s</div></div>
      <div class="rechts">%(knopf)s<a class="ich" href="/einstellungen">%(ich)s</a></div>
    </header>
    <main>%(inhalt)s</main>
  </div>
</div>
<nav class="tabbar" aria-label="Bereiche">%(tabs)s</nav>
%(skript)s%(nachher)s
</body></html>""" % {"titel": e(titel), "ktx": e(ktx), "inhalt": inhalt, "nav": nav, "tabs": tabs,
                     "tokens": TOKENS, "stil": STIL, "ich": e(ich), "knopf": knopf,
                     "skript": SKRIPT % {"thema": json.dumps(nutzer.get("thema", "system"))},
                     "nachher": nachher}


def auftrag_knopf(art, beschriftung, felder=None, klasse="knopf-rahmen", frage=""):
    versteckt = "".join('<input type="hidden" name="%s" value="%s">' % (e(k), e(v))
                        for k, v in (felder or {}).items())
    return ('<form method="post" action="/auftrag"%s><input type="hidden" name="art" value="%s">'
            '%s<button class="%s" type="submit">%s</button></form>'
            % (' data-frage="%s"' % e(frage) if frage else "", e(art), versteckt, klasse,
               e(beschriftung)))


def kpi(lbl, wert, einheit="", sub="", verweis=""):
    karte = ('<div class="karte kpi"><div class="lbl">%s</div><div class="wert">%s%s</div>'
             '<div class="sub">%s</div></div>'
             % (e(lbl), e(wert), (" <small>%s</small>" % e(einheit)) if einheit else "", e(sub)))
    return '<a class="kpi-verweis" href="%s">%s</a>' % (e(verweis), karte) if verweis else karte


def agent_banner(s, alter):
    if s is None:
        return ('<div class="banner"><b>Noch kein Stand vom Server.</b> Der Agent hat keinen '
                'Status geschrieben. Ist er eingerichtet?'
                '<div class="tat">sudo prolo einrichten   |   sudo systemctl status prolo-agent</div>'
                '</div>')
    if alter is not None and alter > STATUS_ALT_S:
        return ('<div class="banner"><b>Der Stand ist %s alt.</b> Der Agent auf dem Server '
                'antwortet nicht - Aufträge bleiben liegen, bis er wieder läuft.'
                '<div class="tat">sudo systemctl restart prolo-agent</div></div>' % e(vor(alter)))
    if s.get("fehler"):
        return '<div class="banner"><b>%s</b></div>' % e(s["fehler"])
    return ""


def hinweise_karte(s):
    hs = (s or {}).get("hinweise") or []
    if not hs:
        return ""
    zeilen = "".join(
        '<div class="hinweis">%s<div class="was">%s</div>%s</div>'
        % (marker(STUFE, h.get("stufe")), e(h.get("text")),
           ('<div class="tat">%s</div>' % e(h["tat"])) if h.get("tat") else "")
        for h in hs)
    return ('<div class="karte"><h2>Was zu tun ist</h2><div class="ktx">Jeder Punkt mit dem '
            'Befehl, der ihn erledigt (auf dem Server)</div><div style="margin-top:6px">%s</div>'
            '</div>' % zeilen)


def tool_tabelle(tools, kurz=False):
    if not tools:
        return ('<p class="leer">Noch keine Tools. Das erste installieren: oben auf '
                '&bdquo;Tool installieren&ldquo; &ndash; zum Beispiel '
                '<span class="mono">louislam/uptime-kuma:1</span>.</p>')
    zeilen = "".join(
        '<tr><td><a class="zeile" href="/tool/%(n)s">%(n)s</a></td><td>%(z)s</td>'
        '<td class="lang"><a class="extern" href="%(u)s" rel="noopener">%(h)s</a></td>%(rest)s</tr>'
        % {"n": e(t["name"]), "z": marker(ZUSTAND, t.get("zustand")), "u": e(t.get("url")),
           "h": e(t.get("host")),
           "rest": "" if kurz else '<td>%s</td><td class="lang mono nur-breit">%s</td>'
           % (anmeldung_marker(t.get("anmeldung")), e(t.get("herkunft")))}
        for t in tools)
    kopf = "<th>Tool</th><th>Zustand</th><th>Adresse</th>" + (
        "" if kurz else '<th>Anmeldung</th><th class="nur-breit">Quelle</th>')
    return '<div class="tabelle"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
        kopf, zeilen)


NAMEN_UNTERBAU = {"traefik": "Traefik", "authentik-server": "Authentik", "authentik-worker":
                  "Authentik Worker", "authentik-db": "Authentik Datenbank", "admin": "Admin-Seite",
                  "socket-proxy": "Docker-Vermittler"}


def ansicht_uebersicht(s, alter, liste):
    oben = agent_banner(s, alter)
    if s is None or s.get("fehler"):
        return oben
    tools = s.get("tools") or []
    laufen = sum(1 for t in tools if t.get("zustand") in ("gesund", "laeuft"))
    ub = s.get("unterbau") or []
    ub_ok = sum(1 for u in ub if u.get("zustand") in ("gesund", "laeuft"))
    sich = s.get("sicherung") or {}
    lv = sich.get("letzte_vollstaendige")
    g = s.get("git") or {}
    kpis = (
        kpi("Tools in Betrieb", "%d" % laufen, einheit="von %d" % len(tools), verweis="/tools",
            sub=("alle laufen" if laufen == len(tools) else
                 "%d angehalten oder gestört" % (len(tools) - laufen))
            if tools else "noch keine installiert") +
        kpi("Unterbau", "%d/%d" % (ub_ok, len(ub)),
            sub="Dienste gesund" if ub_ok == len(ub) else "%d Dienst(e) gestört" % (len(ub) - ub_ok)) +
        kpi("Letzte Sicherung", vor(alter_s(lv.get("zeit"))) if lv else "keine", verweis="/sicherungen",
            sub=("%s, %s" % (bytes_text(lv.get("bytes")), "gelesen und geprüft"
                             if lv.get("geprueft") == "ok" else "Prüfsummen")) if lv
            else "sudo prolo backup") +
        kpi("Fassung", s.get("version", "?"),
            sub=("%d neue Commits im Git" % g["hinter"]) if g.get("hinter")
            else "git %s, aktuell" % (g.get("commit") or "?")))
    unterbau = "".join(
        '<tr><td>%s</td><td class="knapp">%s</td></tr>'
        % (e(NAMEN_UNTERBAU.get(u["dienst"], u["dienst"])), marker(ZUSTAND, u.get("zustand")))
        for u in ub)
    update = ""
    if g.get("hinter"):
        update = ('<div class="aktionen">%s</div>'
                  % auftrag_knopf("update", "Unterbau aktualisieren",
                                  frage="Erst sichern, dann den Unterbau auf den Stand von Git "
                                        "bringen? Die Seite ist dabei kurz weg."))
    letzte = "".join(auftrag_zeile(a) for a in liste[:5])
    return """%(oben)s%(hinweise)s
<div class="reihe kpi4">%(kpis)s</div>
<div class="reihe zwei">
  <div class="karte"><h2>Tools</h2><div class="ktx">Jedes unter seinem eigenen Namen bei %(dom)s</div>
    %(tools)s</div>
  <div class="reihe">
    <div class="karte"><h2>Unterbau</h2><div class="ktx">Eingang, Anmeldung und diese Seite</div>
      <div class="tabelle"><table><tbody>%(ub)s</tbody></table></div>%(update)s</div>
    <div class="karte"><h2>Letzte Aufträge</h2><div class="ktx">Von dieser Seite angestoßen</div>
      %(letzte)s</div>
  </div>
</div>""" % {"oben": oben, "hinweise": hinweise_karte(s), "kpis": kpis, "dom": e(s.get("domain")),
             "tools": tool_tabelle(tools, kurz=True), "ub": unterbau, "update": update,
             "letzte": ('<div class="tabelle"><table><tbody>%s</tbody></table></div>'
                        '<a class="mehr" href="/auftraege">Alle Aufträge</a>' % letzte)
             if letzte else '<p class="leer">Noch keine.</p>'}


def ansicht_tools(s, alter):
    oben = agent_banner(s, alter)
    tools = (s or {}).get("tools") or []
    return oben + ('<div class="karte"><h2>Installierte Tools</h2><div class="ktx">%d Tools, '
                   'jedes in seinem eigenen Netz hinter Traefik</div>%s</div>'
                   % (len(tools), tool_tabelle(tools)))


def ansicht_tool(t, s, liste):
    n = t["name"]
    laeuft = t.get("zustand") in ("gesund", "laeuft", "startet", "krank", "teilweise")
    knoepfe = [
        auftrag_knopf("tool_stop", "Anhalten", {"name": n},
                      frage="%s anhalten? Es ist dann nicht erreichbar." % n) if laeuft else
        auftrag_knopf("tool_start", "Starten", {"name": n}),
        auftrag_knopf("tool_restart", "Neu starten", {"name": n}),
        auftrag_knopf("tool_update", "Aktualisieren", {"name": n},
                      frage="%s erst sichern, dann die neuesten Abbilder holen und neu starten?" % n),
        auftrag_knopf("tool_logs", "Protokoll anzeigen", {"name": n}),
        '<a class="knopf-rahmen" href="/tool/%s/bearbeiten">Bearbeiten</a>' % e(n),
    ]
    dienste = "".join(
        '<tr><td class="mono">%s</td><td class="knapp">%s</td><td class="lang mono">%s</td>'
        '<td class="lang nur-breit">%s</td></tr>'
        % (e(d["dienst"]), marker(ZUSTAND, d.get("zustand")), e(d.get("abbild")), e(d.get("status")))
        for d in t.get("dienste") or [])
    staende = [x for x in ((s.get("sicherung") or {}).get("staende") or [])
               if n in (x.get("tools") or []) and not x.get("fehler") and not x.get("kaputt")]
    anders = "keine" if t.get("anmeldung") == "authentik" else "authentik"
    aussen = "".join('<div class="hinweis">%s<div class="was">%s wird eingehängt, liegt außerhalb '
                     'des Tools und wird NICHT gesichert.</div></div>'
                     % (marker(STUFE, "warn"), e(p)) for p in t.get("nicht_gesichert") or [])
    zurueck = ""
    if staende:
        wahl = "".join('<option value="%s">%s - %s</option>' % (
            e(x["stand"]), e(zeit_kurz(x.get("zeit")) or x["stand"]), e(x.get("grund")))
            for x in staende)
        zurueck = """<form method="post" action="/auftrag" class="formular"
  data-frage="%(n)s auf diesen Stand zurücksetzen? Der jetzige Stand wird vorher gesichert.">
  <input type="hidden" name="art" value="tool_restore"><input type="hidden" name="name" value="%(n)s">
  <div class="feld"><label for="stand">Stand</label><select id="stand" name="stand">%(wahl)s</select></div>
  <div><button class="knopf-rahmen" type="submit">Aus Sicherung zurückholen</button></div>
</form>""" % {"n": e(n), "wahl": wahl}
    else:
        zurueck = '<p class="leer">Noch keine Sicherung mit %s.</p>' % e(n)
    letzte = "".join(auftrag_zeile(a) for a in liste[:8])
    return """<div class="reihe zwei">
<div class="karte"><h2>%(n)s</h2><div class="ktx">%(z)s</div>
  <dl class="fakten">
    <dt>Adresse</dt><dd><a class="extern" href="%(u)s" rel="noopener">%(u)s</a></dd>
    <dt>Anmeldung</dt><dd>%(anm)s</dd>
    <dt>Quelle</dt><dd class="mono">%(herkunft)s</dd>
    <dt>Oberfläche</dt><dd class="mono">Dienst %(dienst)s, Port %(port)s</dd>
    <dt>Volumes</dt><dd class="mono">%(vols)s</dd>
    <dt>Ordner</dt><dd class="mono">/opt/tools/%(n)s</dd>
  </dl>
  <div class="aktionen">%(knoepfe)s</div>
  %(aussen)s
</div>
<div class="reihe">
  <div class="karte"><h2>Sicherung</h2><div class="ktx">Ein früherer Stand dieses Tools - Ordner
    und Volumes</div>%(zurueck)s</div>
  <div class="karte"><h2>Anmeldung und Entfernen</h2><div class="ktx">Selten gebraucht</div>
    <div class="aktionen">%(anm_knopf)s%(rm)s</div>
    <p class="erkl" style="margin-top:10px">Ohne Anmeldung ist %(n)s für jeden im Internet
      erreichbar - nur für Tools mit eigener Anmeldung oder öffentliche Seiten.
      Entfernen sichert vorher; zurückholen geht, solange die Sicherung liegt.</p></div>
</div>
</div>
<div class="karte"><h2>Container</h2><div class="ktx">So, wie Docker sie gerade sieht</div>
  <div class="tabelle"><table><thead><tr><th>Dienst</th><th>Zustand</th><th>Abbild</th>
  <th class="nur-breit">Status</th></tr></thead><tbody>%(dienste)s</tbody></table></div>%(keine)s</div>
<div class="karte"><h2>Aufträge für %(n)s</h2>%(letzte)s</div>""" % {
        "n": e(n), "z": e(ZUSTAND.get(t.get("zustand"), ("", t.get("zustand")))[1]),
        "u": e(t.get("url")), "anm": anmeldung_marker(t.get("anmeldung")),
        "herkunft": e(t.get("herkunft")), "dienst": e(t.get("dienst")), "port": e(t.get("port")),
        "vols": e(", ".join(t.get("volumes") or []) or "keine"), "knoepfe": "".join(knoepfe),
        "aussen": aussen, "zurueck": zurueck,
        "anm_knopf": auftrag_knopf("tool_set", "Anmeldung: %s" % (
            "abschalten" if anders == "keine" else "Authentik einschalten"),
            {"name": n, "anmeldung": anders},
            frage=("%s OHNE Anmeldung öffentlich machen?" % n) if anders == "keine" else ""),
        "rm": auftrag_knopf("tool_rm", "Entfernen", {"name": n}, "knopf-rahmen knopf-gefahr",
                            "%s mit allen Daten entfernen? Vorher wird es gesichert." % n),
        "dienste": dienste, "keine": "" if dienste else '<p class="leer">Keine Container - das '
                                                        'Tool ist angehalten.</p>',
        "letzte": ('<div class="tabelle"><table><tbody>%s</tbody></table></div>' % letzte)
        if letzte else '<p class="leer">Noch keine.</p>'}


def ansicht_bearbeiten(t, fehler="", werte=None):
    w = werte or {}
    n = t["name"]
    if t.get("compose") is not None:
        compose = """<div class="feld"><label for="compose">Compose-Datei</label>
    <textarea id="compose" name="compose" class="gross" spellcheck="false">%s</textarea>
    <div class="erkl">Wie beim Anlegen: offene Ports nimmt prolo weg, Gefahren (privileged,
      Docker-Socket, Pfade des Servers ...) nimmt die Seite nicht an.</div></div>""" % e(
            w["compose"] if "compose" in w else t["compose"])
    elif t.get("quelle") == "git":
        compose = ('<p class="erkl">Die Compose-Datei kommt aus dem Repository <span class="mono">'
                   '%s</span> - dort ändern, dann hier &bdquo;Aktualisieren&ldquo;.</p>'
                   % e(t.get("herkunft")))
    else:
        compose = ('<p class="erkl">Die Compose-Datei ist zu groß für die Seite - auf dem '
                   'Server ändern:  <span class="mono">sudo prolo tool edit %s --compose '
                   '&lt;datei&gt;</span></p>' % e(n))
    namen = t.get("variablen") or []
    return """%(fehler)s<div class="karte"><h2>Compose-Datei und Variablen</h2>
<div class="ktx">Vorher wird %(n)s gesichert. Startet es danach nicht, gilt wieder der Stand
  davor.</div>
<form class="formular" method="post" action="/tool/%(n)s/bearbeiten"
  data-frage="%(n)s jetzt sichern, ändern und neu starten? Es ist dafür kurz nicht erreichbar.">
  %(compose)s
  <div class="feld"><label for="env">Variablen setzen (freiwillig)</label>
    <textarea id="env" name="env" spellcheck="false" placeholder="NAME=wert">%(env)s</textarea>
    <div class="erkl">Je Zeile NAME=wert - setzt einen Wert oder ersetzt ihn. Steht ein $ im
      Wert (etwa ein Hash), in einfache Anführungszeichen: NAME='wert'. Neue Variablen der
      Datei ohne Wert füllt prolo wie beim Anlegen.</div>
    <div class="erkl">In app/.env stehen: <span class="mono">%(namen)s</span> - die Werte
      bleiben auf dem Server.</div></div>
  <div class="aktionen"><button class="knopf" type="submit">Speichern und neu starten</button>
    <a class="knopf-rahmen" href="/tool/%(n)s">Abbrechen</a></div>
</form></div>""" % {
        "fehler": ('<div class="banner"><b>%s</b></div>' % e(fehler)) if fehler else "",
        "n": e(n), "compose": compose, "env": e(w.get("env")),
        "namen": e(", ".join(namen) or "noch keine")}


def ansicht_neu(fehler="", werte=None):
    w = werte or {}
    q = w.get("quelle") or "abbild"

    def gewaehlt(x):
        return " checked" if q == x else ""

    return """%(fehler)s<div class="karte"><h2>Neues Tool</h2>
<div class="ktx">Es bekommt seinen Namen als Adresse (name.%(dom)s), ein eigenes Netz, die
  Anmeldung davor und kommt in die nächtliche Sicherung.</div>
<form class="formular" method="post" action="/tools/neu">
  <div class="zeile2">
    <div class="feld"><label for="name">Name</label>
      <input id="name" name="name" required maxlength="30" pattern="[a-z][a-z0-9\\-]{0,28}[a-z0-9]|[a-z]"
        value="%(name)s" autocomplete="off" spellcheck="false">
      <div class="erkl">Kleinbuchstaben, Ziffern, Bindestrich. Wird zur Adresse.</div></div>
    <div class="feld"><label for="port">Port (freiwillig)</label>
      <input id="port" name="port" inputmode="numeric" maxlength="5" value="%(port)s">
      <div class="erkl">Auf diesem Port antwortet die Oberfläche im Container. Leer: aus dem
        Abbild gelesen.</div></div>
  </div>
  <fieldset><legend>Quelle</legend>
    <label class="wahl"><input type="radio" name="quelle" value="abbild"%(qa)s>
      <span><b>Ein Abbild</b><br><span class="erkl">Ein Container aus Docker Hub o. a., z. B.
      louislam/uptime-kuma:1</span></span></label>
    <label class="wahl"><input type="radio" name="quelle" value="compose"%(qc)s>
      <span><b>Compose-Datei</b><br><span class="erkl">Die docker-compose.yml des Herstellers -
      sie bleibt unverändert</span></span></label>
    <label class="wahl"><input type="radio" name="quelle" value="git"%(qg)s>
      <span><b>Git-Repository</b><br><span class="erkl">Ein Repository mit docker-compose.yml
      (auch eigener Code). Update holt den neuen Stand.</span></span></label>
  </fieldset>
  <div class="feld" id="q-abbild"><label for="abbild">Abbild</label>
    <input id="abbild" name="abbild" value="%(abbild)s" spellcheck="false" autocomplete="off"
      placeholder="louislam/uptime-kuma:1"></div>
  <div class="feld" id="q-compose"><label for="compose">Compose-Datei</label>
    <textarea id="compose" name="compose" class="gross" spellcheck="false">%(compose)s</textarea>
    <div class="erkl">Mehrere Dienste gehen. Offene Ports nimmt prolo weg - erreichbar ist das
      Tool nur über seine Adresse.</div>
    <div class="feld" style="margin-top:10px"><label for="dienst">Dienst mit der Oberfläche
      (freiwillig)</label><input id="dienst" name="dienst" value="%(dienst)s" spellcheck="false"></div>
  </div>
  <div class="feld" id="q-git"><label for="git">Repository (https)</label>
    <input id="git" name="git" value="%(git)s" spellcheck="false" autocomplete="off"
      placeholder="https://github.com/name/repo.git"></div>
  <fieldset><legend>Anmeldung</legend>
    <label class="wahl"><input type="radio" name="anmeldung" value="authentik"%(aa)s>
      <span><b>Authentik</b> (empfohlen)<br><span class="erkl">Nur wer bei auth.%(dom)s angemeldet
      ist, kommt hinein.</span></span></label>
    <label class="wahl"><input type="radio" name="anmeldung" value="keine"%(ak)s>
      <span><b>Ohne</b><br><span class="erkl">Für jeden erreichbar - nur für Tools mit eigener
      Anmeldung oder öffentliche Seiten.</span></span></label>
  </fieldset>
  <div class="feld"><label for="env">Variablen (freiwillig)</label>
    <textarea id="env" name="env" spellcheck="false" placeholder="NAME=wert">%(env)s</textarea>
    <div class="erkl">Je Zeile NAME=wert. Passwörter und Schlüssel, die die Datei verlangt,
      würfelt prolo selbst.</div></div>
  <div><button class="knopf" type="submit">Installieren</button></div>
</form></div>""" % {
        "fehler": ('<div class="banner"><b>%s</b></div>' % e(fehler)) if fehler else "",
        "dom": e(DOMAIN or "deine-domain"), "name": e(w.get("name")), "port": e(w.get("port")),
        "abbild": e(w.get("abbild")), "compose": e(w.get("compose")), "dienst": e(w.get("dienst")),
        "git": e(w.get("git")), "env": e(w.get("env")),
        "qa": gewaehlt("abbild"), "qc": gewaehlt("compose"), "qg": gewaehlt("git"),
        "aa": "" if w.get("anmeldung") == "keine" else " checked",
        "ak": " checked" if w.get("anmeldung") == "keine" else ""}


def ansicht_sicherungen(s, alter):
    oben = agent_banner(s, alter)
    if s is None or s.get("fehler"):
        return oben
    sich = s.get("sicherung") or {}
    staende = sich.get("staende") or []
    lv = sich.get("letzte_vollstaendige")
    platz = (s.get("platz") or {}).get("sicherung") or {}
    feature = """<div class="feature"><div class="lbl">Letzte vollständige Sicherung</div>
  <div class="wert">%s</div><div class="sub">%s</div></div>""" % (
        e(vor(alter_s(lv.get("zeit")))) if lv else "noch keine",
        e("%s - %s, %s" % (zeit_kurz(lv.get("zeit")), bytes_text(lv.get("bytes")),
                           "jedes Stück entschlüsselt und gelesen" if lv.get("geprueft") == "ok"
                           else "Pruefsummen")) if lv else "jetzt sichern: oben rechts")
    zeilen = "".join(
        '<tr><td class="mono">%s</td><td class="lang">%s</td><td class="lang">%s</td>'
        '<td class="z">%s</td><td class="knapp">%s</td></tr>'
        % (zeit(x.get("zeit")), e(x.get("grund")),
           e(", ".join((["Unterbau"] if x.get("unterbau") else []) + list(x.get("tools") or [])) or "-"),
           e(bytes_text(x.get("bytes"))),
           '<span class="marker m-rot">unbrauchbar</span>' if x.get("kaputt") else
           '<span class="marker m-rot">unvollständig</span>' if x.get("fehler") else
           '<span class="marker m-gut">gelesen</span>' if x.get("geprueft") == "ok" else
           '<span class="marker m-weg">Prüfsummen</span>')
        for x in staende)
    tabelle = ('<div class="tabelle"><table><thead><tr><th>Wann</th><th>Anlass</th><th>Inhalt</th>'
               '<th class="z">Größe</th><th>Prüfung</th></tr></thead><tbody>%s</tbody></table>'
               '</div>' % zeilen) if zeilen else '<p class="leer">Noch keine Sicherung.</p>'
    schluessel = ("Der geheime Schlüssel liegt auf diesem Server (/etc/prolo/backup.key). Eine "
                  "Kopie gehört in den Passwortmanager - ohne sie lässt sich eine Sicherung auf "
                  "einem neuen Server nicht öffnen." if sich.get("schluessel_auf_server") else
                  "Auf dem Server liegt nur der öffentliche Schlüssel - zum Zurückholen "
                  "braucht es den geheimen (--schluessel).")
    return """%(oben)s<div class="reihe kpi3">%(feature)s
  %(anzahl)s%(frei)s</div>
<div class="karte"><h2>Stände</h2><div class="ktx">Neueste zuerst, in %(ordner)s - verschlüsselt,
  jedes Stück nach dem Packen wieder gelesen</div>%(tabelle)s</div>
<div class="karte"><h2>Schlüssel und Zurückholen</h2><div class="ktx">Auf dem Server</div>
  <p class="erkl" style="margin-top:10px;font-size:13px;color:var(--ink-2)">%(schluessel)s</p>
  <dl class="fakten">
    <dt>Schlüssel</dt><dd class="mono">sudo prolo backup schluessel</dd>
    <dt>Ein Tool</dt><dd class="mono">auf der Seite des Tools, oder: sudo prolo restore --tool &lt;name&gt;</dd>
    <dt>Alles</dt><dd class="mono">sudo prolo restore</dd>
    <dt>Prüfen</dt><dd class="mono">sudo prolo backup pruefen</dd>
  </dl></div>""" % {
        "oben": oben, "feature": feature,
        "anzahl": kpi("Stände", "%d" % len(staende),
                      sub="je %s Tage aufbewahrt" % s.get("backup_tage", "?")),
        "frei": kpi("Platz frei", *wert_und_einheit(platz.get("frei")),
                    sub="von %s auf %s" % (bytes_text(platz.get("gesamt")), platz.get("pfad", "?"))),
        "ordner": e(sich.get("ordner", "/opt/backup")), "tabelle": tabelle,
        "schluessel": e(schluessel)}


def auftrag_zeile(a):
    f = a.get("felder") or {}
    ziel = f.get("name") or f.get("stand") or ""
    wann = zeit(a.get("eingang") or a.get("beginn"))
    # Am Handy steht die Zeit unter dem Titel: als eigene Spalte liess sie ihm
    # so wenig Platz, dass Woerter in Silben zerbrachen (N-133).
    return ('<tr><td class="mono knapp nur-breit">%s</td><td class="lang"><a class="zeile" '
            'href="/auftrag/%s">%s%s</a><div class="mono erkl nur-schmal">%s</div></td>'
            '<td class="knapp">%s</td></tr>'
            % (wann, e(a.get("kennung")), e(a.get("titel") or a.get("art") or "?"),
               (" &middot; " + e(ziel)) if ziel else "", wann, marker(AUFTRAG, a.get("status"))))


def ansicht_auftraege(liste):
    if not liste:
        return '<div class="karte"><h2>Aufträge</h2><p class="leer">Noch keine.</p></div>'
    return ('<div class="karte"><h2>Aufträge</h2><div class="ktx">Ausgeführt vom Agenten auf dem '
            'Server, einer nach dem anderen</div><div class="tabelle"><table><thead><tr><th class="nur-breit">'
            'Wann</th><th>Was</th><th>Stand</th></tr></thead><tbody>%s</tbody></table></div></div>'
            % "".join(auftrag_zeile(a) for a in liste))


def ansicht_auftrag(lage, ausgabe):
    st = lage.get("status")
    f = lage.get("felder") or {}
    weiter = ""
    if st == "ok" and lage.get("art") == "tool_add" and f.get("name"):
        weiter = '<a class="knopf" href="/tool/%s">Zum Tool</a>' % e(f["name"])
    elif st in ("fehler", "abgelehnt") and lage.get("art") == "tool_add":
        weiter = '<a class="knopf-rahmen" href="/tools/neu">Zurück zum Formular</a>'
    elif f.get("name"):
        weiter = '<a class="knopf-rahmen" href="/tool/%s">Zum Tool</a>' % e(f["name"])
    return """<div class="karte"><h2>%(titel)s</h2><div class="ktx">%(wer)s</div>
  <div class="aktionen"><span id="stand">%(st)s</span>%(meldung)s</div>
  <pre class="ausgabe" id="ausgabe">%(aus)s</pre>
  <div class="aktionen">%(weiter)s</div></div>""" % {
        "titel": e(lage.get("titel") or lage.get("art") or "Auftrag"),
        "wer": e("angestoßen von %s" % lage["wer"] if lage.get("wer") else ""),
        "st": marker(AUFTRAG, st),
        "meldung": (' <span class="erkl">%s</span>' % e(lage["meldung"])) if lage.get("meldung") else "",
        "aus": e(ausgabe) or ("Wartet auf den Agenten ..." if st == "wartet" else ""),
        "weiter": weiter}


def nachladen(kennung):
    """Solange ein Auftrag läuft, holt die Seite alle 2 s den neuen Stand."""
    return """<script>
(function(){
  var aus = document.getElementById('ausgabe'), stand = document.getElementById('stand');
  function holen(){
    fetch('/api/auftrag/%s', {credentials:'same-origin'}).then(function(r){ return r.json(); })
    .then(function(d){
      var unten = aus.scrollTop + aus.clientHeight >= aus.scrollHeight - 20;
      aus.textContent = d.ausgabe || 'Wartet auf den Agenten ...';
      if (unten) aus.scrollTop = aus.scrollHeight;
      stand.innerHTML = d.marker;
      if (d.offen) setTimeout(holen, 2000); else location.reload();
    }).catch(function(){ setTimeout(holen, 5000); });
  }
  setTimeout(holen, 1500);
})();
</script>""" % e(kennung)


def ansicht_einstellungen(nutzer, meldung, s):
    seg = "".join('<button type="submit" name="thema" value="%s" aria-pressed="%s">%s</button>'
                  % (w, "true" if nutzer.get("thema") == w else "false", t)
                  for w, t in (("system", "System"), ("hell", "Hell"), ("dunkel", "Dunkel")))
    return """%(meldung)s<div class="karte"><h2>Darstellung</h2>
  <div class="ktx">Gilt für dieses Konto auf allen Geräten</div>
  <form method="post" action="/einstellungen/thema" style="margin-top:12px">
    <div class="segment" role="group" aria-label="Darstellung">%(seg)s</div>
    <div class="erkl" style="margin-top:6px">System folgt der Einstellung des Geräts.</div>
  </form></div>
<div class="karte"><h2>Wie diese Seite arbeitet</h2><div class="ktx">Und warum sie es nicht selbst tut</div>
  <p style="font-size:13px;margin-top:12px">Sie hat keinen Zugriff auf Docker und keinen auf die
    Dateien des Servers. Sie liest den Stand, den der Agent auf dem Server alle 30 Sekunden
    schreibt, und legt Aufträge ab - ausgeführt werden sie vom Agenten über
    <span class="mono">prolo</span>, mit denselben Prüfungen wie auf der Kommandozeile. Alles,
    was hier geht, geht auch dort: <span class="mono">sudo prolo -h</span>.</p>
  <dl class="fakten">
    <dt>Fassung</dt><dd class="mono">%(version)s</dd>
    <dt>Domain</dt><dd class="mono">%(dom)s</dd>
    <dt>Zugang</dt><dd>Gruppe <span class="mono">%(gruppe)s</span> in Authentik</dd>
  </dl></div>
<div class="karte"><h2>Konto</h2><div class="ktx">Verwaltet wird es zentral in Authentik</div>
  <dl class="fakten">
    <dt>Anmeldename</dt><dd class="mono">%(id)s</dd>
    <dt>Anzeigename</dt><dd>%(name)s</dd>
    <dt>E-Mail</dt><dd class="mono">%(mail)s</dd>
  </dl>
  <div class="aktionen"><a class="knopf" href="/outpost.goauthentik.io/sign_out">Abmelden / neu laden</a>
    <a class="knopf-rahmen" href="https://auth.%(dom)s/if/user/" rel="noopener">Konto in Authentik</a></div>
  <div class="erkl" style="margin-top:6px">Abmelden ist eine Weiterleitung zur Anmeldung - die
    Seite lädt danach neu.</div></div>""" % {
        "meldung": ('<div class="banner gut">%s</div>' % e(meldung)) if meldung else "",
        "seg": seg, "version": e((s or {}).get("version") or VERSION), "dom": e(DOMAIN),
        "gruppe": e(GRUPPE), "id": e(nutzer.get("nutzer_id")),
        "name": e(nutzer.get("anzeigename") or "-"), "mail": e(nutzer.get("email") or "-")}


# ------------------------------------------------------------ Dienst
class Handler(BaseHTTPRequestHandler):
    server_version = "prolo-admin"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Keine Kopfzeilen ins Protokoll (§22) - nur Weg und Kode.
        sys.stderr.write("%s\n" % (fmt % args))

    def angemeldet(self):
        """Angemeldet (Authentik) UND in der Gruppe. Traefik löscht am Eingang
        jede mitgeschickte X-Authentik-*, die Werte hier stammen also von
        Authentik."""
        kennung = (self.headers.get("X-Authentik-Username") or "").strip()
        if not kennung:
            raise Antwort(401, "Nicht angemeldet. Diese Seite liegt hinter der Anmeldung.")
        gruppen = {g.strip() for g in (self.headers.get("X-Authentik-Groups") or "").split("|")}
        if GRUPPE not in gruppen:
            raise Antwort(403, "Dafür braucht es die Gruppe '%s' in Authentik. Zuweisen unter "
                               "auth.%s -> Verzeichnis -> Gruppen." % (GRUPPE, DOMAIN))
        return nutzer_holen(kennung[:150], (self.headers.get("X-Authentik-Name") or "").strip()[:150],
                            (self.headers.get("X-Authentik-Email") or "").strip()[:150])

    def gleicher_ursprung(self):
        """Eine Absendung muss von dieser Seite kommen - sonst koennte eine
        fremde Seite im Namen des Angemeldeten Tools entfernen."""
        ziel = self.headers.get("Host") or ""
        quelle = self.headers.get("Origin") or ""
        if quelle:
            if urlparse(quelle).netloc == ziel:
                return
        elif (self.headers.get("Sec-Fetch-Site") or "") == "same-origin":
            return
        raise Antwort(403, "Die Absendung kam nicht von dieser Seite.")

    def do_GET(self):
        self._lauf(self.get)

    def do_HEAD(self):
        self._lauf(self.get)

    def do_POST(self):
        self._lauf(self.post)

    def _lauf(self, was):
        try:
            was()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Antwort as a:
            self.fehlerseite(a.kode, a.text)
        except Exception:
            import traceback
            traceback.print_exc()
            self.fehlerseite(500, "Da ist bei uns etwas schiefgegangen. Der Fehler steht im "
                                  "Protokoll:  sudo prolo compose logs admin")

    def get(self):
        url = urlparse(self.path)
        pfad = url.path
        if pfad == "/gesundheit":
            return self.roh(200, b"ok", "text/plain; charset=utf-8")
        if pfad.startswith("/schriften/"):
            return self.schrift(pfad)
        nutzer = self.angemeldet()
        fr = parse_qs(url.query)

        def zeigen(titel, ktx, inhalt, nav, knopf="", nachher=""):
            return self.html(seite(titel, ktx, inhalt, nav, nutzer, knopf, nachher))

        neu_knopf = '<a class="knopf nur-breit" href="/tools/neu">Tool installieren</a>'
        if pfad == "/":
            s, alter = status_lesen()
            return zeigen("Übersicht", "Stand vom Server: %s" % vor(alter), ansicht_uebersicht(
                s, alter, auftraege(10)), pfad, neu_knopf)
        if pfad == "/tools":
            s, alter = status_lesen()
            return zeigen("Tools", "Installiert unter /opt/tools", ansicht_tools(s, alter), pfad,
                          '<a class="knopf" href="/tools/neu">Tool installieren</a>')
        if pfad == "/tools/neu":
            return zeigen("Tool installieren", "Abbild, Compose-Datei oder Git", ansicht_neu(),
                          "/tools")
        if pfad.startswith("/tool/") and pfad.endswith("/bearbeiten"):
            t = tool_holen(pfad[len("/tool/"):-len("/bearbeiten")])
            return zeigen("%s bearbeiten" % t["name"], "Compose-Datei und Variablen",
                          ansicht_bearbeiten(t), "/tools")
        if pfad.startswith("/tool/"):
            name = pfad[len("/tool/"):]
            s, alter = status_lesen()
            t = tool_holen(name, s)
            return zeigen(name, "Stand vom Server: %s" % vor(alter),
                          agent_banner(s, alter) + ansicht_tool(t, s, auftraege(20, name)), "/tools")
        if pfad == "/sicherungen":
            s, alter = status_lesen()
            return zeigen("Sicherungen", "Jede Nacht um 03:30 - Unterbau und alle Tools",
                          ansicht_sicherungen(s, alter), pfad,
                          auftrag_knopf("sichern", "Jetzt sichern", klasse="knopf",
                                        frage="Jetzt sichern? Die Tools werden dafür kurz "
                                              "angehalten."))
        if pfad == "/auftraege":
            return zeigen("Aufträge", "Was von hier angestoßen wurde", ansicht_auftraege(
                auftraege(100)), pfad)
        if pfad.startswith("/api/auftrag/"):
            lage, ausgabe = auftrag_lesen(pfad[len("/api/auftrag/"):])
            return self.json_aus({"status": lage.get("status"), "ausgabe": ausgabe,
                                  "marker": marker(AUFTRAG, lage.get("status")),
                                  "offen": lage.get("status") in ("wartet", "laeuft")})
        if pfad.startswith("/auftrag/"):
            kennung = pfad[len("/auftrag/"):]
            lage, ausgabe = auftrag_lesen(kennung)
            offen = lage.get("status") in ("wartet", "laeuft")
            return zeigen(lage.get("titel") or "Auftrag", "Auftrag %s" % kennung,
                          ansicht_auftrag(lage, ausgabe), "/auftraege",
                          nachher=nachladen(kennung) if offen else "")
        if pfad == "/einstellungen":
            s, _ = status_lesen()
            return zeigen("Einstellungen", "Darstellung und Konto", ansicht_einstellungen(
                nutzer, (fr.get("ok") or [""])[0][:80], s), pfad)
        raise Antwort(404, "Diese Seite gibt es nicht.")

    def formular(self, grenze=8192):
        laenge = int(self.headers.get("Content-Length") or 0)
        if laenge > grenze:
            raise Antwort(413, "Das war zu viel für ein Formular.")
        roh = self.rfile.read(laenge).decode("utf-8", "replace")
        return {k: v[0] for k, v in parse_qs(roh, keep_blank_values=True).items()}

    def post(self):
        pfad = urlparse(self.path).path
        nutzer = self.angemeldet()
        self.gleicher_ursprung()
        if pfad == "/einstellungen/thema":
            thema_setzen(nutzer["nutzer_id"], self.formular().get("thema", ""))
            return self.weiter("/einstellungen?ok=" + quote("Darstellung gespeichert."))
        if pfad == "/auftrag":
            f = self.formular()
            art = f.pop("art", "")
            erlaubt = set(sum((auftrag.ARTEN.get(art, ((), (), "", 0))[:2]), ()))
            kennung = auftrag_ablegen(art, {k: v for k, v in f.items() if k in erlaubt},
                                      nutzer["nutzer_id"])
            return self.weiter("/auftrag/%s" % kennung)
        if pfad.startswith("/tool/") and pfad.endswith("/bearbeiten"):
            t = tool_holen(pfad[len("/tool/"):-len("/bearbeiten")])
            f = self.formular(MAX_FORMULAR)
            # Browser schicken CRLF; unveraendert heisst: die Datei nicht anfassen.
            compose = f.get("compose", "").replace("\r\n", "\n")
            if t.get("compose") is None or compose == t["compose"]:
                compose = ""
            try:
                kennung = auftrag_ablegen("tool_edit", {"name": t["name"], "compose": compose,
                                                        "env": f.get("env", "")},
                                          nutzer["nutzer_id"])
            except Antwort as a:
                if a.kode != 400:
                    raise
                return self.html(seite("%s bearbeiten" % t["name"], "Compose-Datei und Variablen",
                                       ansicht_bearbeiten(t, a.text, f), "/tools", nutzer), 400)
            return self.weiter("/auftrag/%s" % kennung)
        if pfad == "/tools/neu":
            f = self.formular(MAX_FORMULAR)
            felder = {k: f.get(k, "") for k in ("name", "quelle", "port", "dienst", "anmeldung",
                                                "env")}
            q = felder["quelle"]
            if q in ("abbild", "git", "compose"):
                felder[q] = f.get(q, "")
            if q != "compose":
                felder["dienst"] = ""
            try:
                kennung = auftrag_ablegen("tool_add", felder, nutzer["nutzer_id"])
            except Antwort as a:
                if a.kode != 400:
                    raise
                inhalt = ansicht_neu(a.text, f)
                return self.html(seite("Tool installieren", "Abbild, Compose-Datei oder Git",
                                       inhalt, "/tools", nutzer), 400)
            return self.weiter("/auftrag/%s" % kennung)
        raise Antwort(404, "Diesen Weg gibt es nicht.")

    # ---------------------------------------------------------- Antwort
    def schrift(self, pfad):
        name = os.path.basename(pfad)
        ziel = os.path.join(SCHRIFTEN, name)
        if not re.fullmatch(r"[a-z0-9-]+\.woff2", name) or not os.path.isfile(ziel):
            raise Antwort(404, "Diese Datei gibt es nicht.")
        with open(ziel, "rb") as f:
            self.roh(200, f.read(), "font/woff2",
                     {"Cache-Control": "public, max-age=31536000, immutable"})

    def roh(self, kode, koerper, art, extra=None):
        self.send_response(kode)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("Cache-Control", (extra or {}).pop("Cache-Control", "no-store"))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; "
                         "script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; "
                         "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(koerper)

    def html(self, text, kode=200):
        self.roh(kode, text.encode("utf-8"), "text/html; charset=utf-8")

    def json_aus(self, obj):
        self.roh(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                 "application/json; charset=utf-8")

    def weiter(self, ziel):
        self.send_response(303)
        self.send_header("Location", ziel)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def fehlerseite(self, kode, text):
        # Nach einem Fehler die Verbindung schliessen: wurde eine Absendung
        # abgewiesen, bevor ihr Inhalt gelesen war, laege der sonst in der
        # Leitung und wuerde als naechste Anfrage gelesen.
        self.close_connection = True
        koerper = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(k)d - ProloWelt</title><style>%(tokens)s%(stil)s</style></head>
<body data-theme="dark"><main style="max-width:600px">
<div class="karte"><h2 class="mono" style="font-size:12px;color:var(--ink-3)">FEHLER %(k)d</h2>
<p style="font-size:15px;color:var(--ink);margin-top:10px">%(t)s</p>
<div class="aktionen"><a class="knopf" href="/">Zur Übersicht</a></div></div></main>
<script>if (window.matchMedia && !window.matchMedia('(prefers-color-scheme: dark)').matches)
document.body.dataset.theme = 'light';</script></body></html>""" % {
            "k": kode, "t": e(text), "tokens": TOKENS, "stil": STIL}
        self.roh(kode, koerper.encode("utf-8"), "text/html; charset=utf-8",
                 {"Connection": "close"})


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    datenbank_anlegen()
    # Als PID 1 im Container gibt es fuer SIGTERM keine Vorgabe - ohne das
    # wartete jedes "docker stop" (also jede Sicherung) 60 s auf den
    # Abschuss. Gemessen: 60,2 s statt unter einer.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    sys.stderr.write("ProloWelt Admin %s auf Port %d (Gruppe '%s')\n" % (VERSION, PORT, GRUPPE))
    srv.serve_forever()


if __name__ == "__main__":
    main()
