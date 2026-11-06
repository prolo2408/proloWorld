"""Der Kaefig: was eine Compose-Datei darf, bevor prolo sie als root startet.

Wer bestimmt, was in einer Compose-Datei steht, bestimmt ueber Docker - und
Docker ist root auf dem Server. Darum wird jede Datei geprueft, bevor sie
startet, und zwar als ERLAUBNISLISTE: jeder Schluessel, den prolo nicht
ausdruecklich kennt, ist eine Gefahr. Eine Sperrliste ("privileged, Socket,
...") hat Luecken, sobald Compose etwas Neues lernt - gefunden wurden
driver_opts, fremde Volume- und Netznamen, post_start mit privileged,
provider, use_api_socket (N-135).

Geprueft wird das, was Compose selbst versteht (docker compose config), nicht
der Text der Datei: Anker, Erweiterungen und Variablen sind dort aufgeloest.

    gefahren(cfg, app, projekt) -> (gefahren, hinweise, binds_aussen)

Gefahren legt die Admin-Seite nie an; auf der Kommandozeile fragt prolo nach.
"""
import os
import re

SOCKET = re.compile(r"(^|/)docker\.sock$")

# Was ein Dienst ohne weitere Pruefung haben darf: es wirkt nur im eigenen
# Container oder auf seine eigenen Grenzen.
DIENST_FREI = frozenset((
    "annotations", "attach", "cap_drop", "command", "cpu_count", "cpu_percent",
    "cpu_period", "cpu_quota", "cpu_shares", "cpus", "cpuset", "depends_on", "dns",
    "dns_opt", "dns_search", "domainname", "entrypoint", "environment", "expose",
    "extra_hosts", "group_add", "healthcheck", "hostname", "image", "init", "links",
    "mac_address", "mem_limit", "mem_reservation", "mem_swappiness", "memswap_limit",
    "pids_limit", "platform", "ports", "profiles", "pull_policy", "read_only", "restart",
    "scale", "shm_size", "stdin_open", "stop_grace_period", "stop_signal", "sysctls",
    "tmpfs", "tty", "ulimits", "user", "working_dir",
))

# Namespaces, die ein Dienst teilen darf - nur mit sich selbst bzw. privat.
NAMENSRAUM = {
    "pid": ("",), "uts": ("",), "cgroup": ("", "private"), "userns_mode": ("",),
    "ipc": ("", "private", "shareable"),
}
NAMENSRAUM_TEXT = {
    "pid": "sieht die Prozesse von %s (pid: %s)",
    "ipc": "teilt den Speicher mit %s (ipc: %s)",
    "uts": "teilt den Rechnernamen mit %s (uts: %s)",
    "cgroup": "teilt die cgroups mit %s (cgroup: %s)",
    "userns_mode": "verlässt den Nutzer-Namensraum (userns_mode: %s)",
}
PROTOKOLL = ("json-file", "local", "none")
BUILD_FREI = frozenset(("context", "dockerfile", "dockerfile_inline", "args", "target",
                        "labels", "shm_size", "extra_hosts", "pull", "no_cache", "platforms",
                        "tags", "ulimits", "cache_from", "secrets", "additional_contexts",
                        "network"))
VOLUME_FREI = frozenset(("name", "labels", "driver", "external"))
NETZ_FREI = frozenset(("name", "labels", "driver", "internal", "attachable", "enable_ipv6",
                       "enable_ipv4", "external", "ipam"))
DIENST_NETZ_FREI = frozenset(("aliases", "priority", "gw_priority", "mac_address",
                              "interface_name"))
GEHEIM_FREI = frozenset(("file", "content", "name", "labels", "template_driver"))
EINHAENGEN_FREI = frozenset(("type", "source", "target", "read_only", "bind", "volume",
                             "tmpfs", "consistency"))
# Namen, die der Unterbau selbst vergibt (Container, Netz-Aliasse von prolo).
RESERVIERT = re.compile(r"^prolo", re.I)


def verweise(app, auslassen=()):
    """Verweise (Symlinks) in app, die nach draussen zeigen - als Liste von
    Texten. Ein Git-Repository kann sie mitbringen: .env -> /etc/prolo/
    geheim.env gaebe Compose die Geheimnisse des Unterbaus (gemessen, N-136).
    Uebergangen werden .git und die Ordner, die Container einhaengen - dort
    liest prolo nichts (siehe Pruefung.ordner)."""
    app_echt = os.path.realpath(app)
    auslassen = {os.path.normpath(a) for a in auslassen}
    aus = []
    for wurzel, ordner, dateien in os.walk(app):
        rel = os.path.relpath(wurzel, app)
        if rel == ".git" or rel.startswith(".git" + os.sep) or \
                os.path.normpath(wurzel) in auslassen:
            ordner[:] = []
            continue
        for n in sorted(ordner + dateien):
            p = os.path.join(wurzel, n)
            if os.path.islink(p):
                ziel = os.path.realpath(p)
                if not (ziel == app_echt or ziel.startswith(app_echt + os.sep)):
                    aus.append("%s zeigt nach %s - außerhalb des Tools"
                               % (os.path.relpath(p, app), os.readlink(p)))
        if rel == ".":
            ordner[:] = [o for o in ordner if o != ".git"]
    return aus


def _innen(pfad, app):
    """Liegt pfad in app (nach Aufloesen aller Verweise)?"""
    echt = os.path.realpath(pfad)
    return echt.startswith(os.path.realpath(app) + os.sep)


class Pruefung:
    def __init__(self, cfg, app, projekt):
        self.cfg = cfg
        self.app = app
        self.projekt = projekt
        self.gef, self.hin, self.aussen = [], [], []
        self.dienste = cfg.get("services") or {}

    def g(self, wo, text):
        self.gef.append("%s: %s" % (wo, text) if wo else text)

    # ---------------------------------------------------- oben
    def alles(self):
        for k in self.cfg:
            if k not in ("name", "services", "volumes", "networks", "secrets", "configs") \
                    and not str(k).startswith("x-"):
                self.g("", "prolo kennt '%s' nicht - darum nur auf der Kommandozeile" % k)
        for k, v in sorted((self.cfg.get("volumes") or {}).items()):
            self.volume(k, v or {})
        for k, v in sorted((self.cfg.get("networks") or {}).items()):
            self.netz(k, v or {})
        for art in ("secrets", "configs"):
            for k, v in sorted((self.cfg.get(art) or {}).items()):
                self.geheimnis(art, k, v or {})
        for name, d in sorted(self.dienste.items()):
            self.dienst(name, d or {})
        self.ordner()
        return self.gef, self.hin, self.aussen

    # ------------------------------------------- der Ordner app/
    def ordner(self):
        """Was ein Container einhaengt, kann er veraendern. Darum duerfen dort
        keine Dateien liegen, die prolo oder Compose als root lesen (.git, die
        Compose-Datei, .env, env_file, Dockerfile ...), keine zweite
        Einhaengung darin - sonst ersetzt der Container sie durch einen Verweis
        auf den Server, und der naechste Start haengt den Server ein -, und der
        Weg dorthin fuehrt ueber keinen Verweis (N-136)."""
        app = os.path.normpath(self.app)
        binds = set()
        for name, d in sorted(self.dienste.items()):
            for v in (d or {}).get("volumes") or []:
                if isinstance(v, dict) and v.get("type") == "bind":
                    q = os.path.normpath(str(v.get("source") or ""))
                    if q.startswith(app + os.sep):
                        binds.add((q, name))
        gelesen = {os.path.join(app, n) for n in (".env", ".git", "compose.yaml", "compose.yml",
                                                   "docker-compose.yaml", "docker-compose.yml")}
        for name, d in self.dienste.items():
            d = d or {}
            for e in d.get("env_file") or []:
                gelesen.add(os.path.normpath(str(e.get("path") if isinstance(e, dict) else e)))
            b = d.get("build") or {}
            if b.get("context") and not str(b["context"]).startswith("https://"):
                ctx = os.path.normpath(str(b["context"]))
                gelesen.add(os.path.normpath(os.path.join(ctx, str(b.get("dockerfile") or
                                                                    "Dockerfile"))))
        for art in ("secrets", "configs"):
            for v in (self.cfg.get(art) or {}).values():
                if (v or {}).get("file"):
                    gelesen.add(os.path.normpath(str(v["file"])))
        for q, name in sorted(binds):
            rel = os.path.relpath(q, app)
            if rel.split(os.sep)[0] == ".git":
                self.g(name, "hängt %s ein - darüber schreibt der Container Git-Hooks, die "
                       "root beim nächsten Update ausführt" % rel)
            weg = app
            for teil in rel.split(os.sep):
                weg = os.path.join(weg, teil)
                if os.path.islink(weg):
                    self.g(name, "hängt %s über einen Verweis ein (%s)"
                           % (rel, os.path.relpath(weg, app)))
                    break
            for p in sorted(gelesen):
                if p == q or p.startswith(q + os.sep):
                    self.g(name, "hängt %s ein - darin liegt %s, das prolo als root liest"
                           % (rel, os.path.relpath(p, app)))
            for q2, _ in sorted(binds):
                if q2 != q and q2.startswith(q + os.sep):
                    self.g(name, "hängt %s ein, und darin wird %s eingehängt - der Container "
                           "könnte es durch einen Verweis auf den Server ersetzen"
                           % (rel, os.path.relpath(q2, app)))
        for v in verweise(app, {q for q, _ in binds}):
            self.g("", v)

    def eigener_name(self, art, k, name):
        """Volumes und Netze heissen <projekt>_<name> - mit einem anderen
        Namen greift das Tool auf das Volume oder Netz eines anderen
        Projekts zu (auch auf die Datenbank von Authentik)."""
        if not str(name or "").startswith(self.projekt + "_"):
            self.g("", "%s %s heißt %s - das gehört nicht zu diesem Tool (erlaubt: ohne "
                   "name: oder %s_…)" % (art, k, name, self.projekt))

    def volume(self, k, v):
        fremd = sorted(set(v) - VOLUME_FREI)
        if fremd:
            self.g("", "Volume %s: %s - damit kann ein Volume auf den Server zeigen"
                   % (k, ", ".join(fremd)))
        if v.get("external"):
            self.g("", "erwartet ein fremdes Volume %s (external)" % (v.get("name") or k))
        else:
            self.eigener_name("Volume", k, v.get("name"))
        if v.get("driver") not in (None, "", "local"):
            self.g("", "Volume %s: Treiber %s" % (k, v["driver"]))

    def netz(self, k, v):
        if k == "prolo":
            self.g("", "ein Netz namens prolo vergibt prolo selbst")
        fremd = sorted(set(v) - NETZ_FREI)
        if fremd:
            self.g("", "Netz %s: %s" % (k, ", ".join(fremd)))
        if v.get("external"):
            self.g("", "hängt sich in ein fremdes Netz %s (external)" % (v.get("name") or k))
        else:
            self.eigener_name("Netz", k, v.get("name"))
        if v.get("driver") not in (None, "", "bridge"):
            self.g("", "Netz %s: Treiber %s" % (k, v["driver"]))
        if v.get("ipam"):
            self.g("", "Netz %s legt seine Adressen selbst fest (ipam)" % k)

    def geheimnis(self, art, k, v):
        fremd = sorted(set(v) - GEHEIM_FREI)
        if fremd:
            self.g("", "%s %s: %s - liest vom Server, nicht aus dem Tool"
                   % (art, k, ", ".join(fremd)))
        if v.get("file") and not _innen(v["file"], self.app):
            self.g("", "%s %s liest %s vom Server" % (art, k, v["file"]))

    # -------------------------------------------------- Dienst
    def dienst(self, name, d):
        if RESERVIERT.search(name):
            self.g(name, "Dienstnamen mit prolo… vergibt der Unterbau")
        for k in sorted(d):
            if k in DIENST_FREI or str(k).startswith("x-"):
                continue
            pruefer = getattr(self, "d_" + k, None)
            if pruefer is None:
                self.g(name, "prolo kennt '%s' nicht - darum nur auf der Kommandozeile" % k)
            else:
                pruefer(name, d[k], d)
        bild = str(d.get("image") or "")
        if bild and not d.get("build") and (bild.endswith(":latest") or
                                            ":" not in bild.rsplit("/", 1)[-1]):
            self.hin.append("%s: Abbild %s ohne feste Fassung - ein Update kann einen großen "
                            "Sprung machen" % (name, bild))

    def d_privileged(self, name, w, d):
        if w:
            self.g(name, "läuft mit allen Rechten des Servers (privileged)")

    def d_network_mode(self, name, w, d):
        if w == "host":
            self.g(name, "hängt direkt im Netz des Servers (network_mode: host) - an Traefik "
                   "und Anmeldung vorbei")
        elif w:
            self.g(name, "teilt das Netz eines anderen Containers (network_mode: %s)" % w)

    def _namensraum(self, art):
        def pruefer(name, w, d):
            if str(w or "") not in NAMENSRAUM[art]:
                wer = "dem Server" if w == "host" else str(w).split(":", 1)[-1]
                self.g(name, NAMENSRAUM_TEXT[art] % ((w,) if art == "userns_mode" else (wer, w)))
        return pruefer

    def __getattr__(self, k):
        if k.startswith("d_") and k[2:] in NAMENSRAUM:
            return self._namensraum(k[2:])
        raise AttributeError(k)

    def d_cap_add(self, name, w, d):
        if w:
            self.g(name, "holt Linux-Fähigkeiten zurück: %s" % ", ".join(sorted(map(str, w))))

    def d_devices(self, name, w, d):
        if w:
            self.g(name, "greift auf Geräte des Servers zu (devices)")

    def d_security_opt(self, name, w, d):
        for s in w or []:
            if not re.fullmatch(r"no-new-privileges(?:[:=]true)?", str(s)):
                self.g(name, "ändert den Schutz des Containers (security_opt: %s)" % s)

    def d_oom_score_adj(self, name, w, d):
        if int(w or 0) < 0:
            self.g(name, "drängt sich beim Speicher vor den Server (oom_score_adj: %s)" % w)

    def d_logging(self, name, w, d):
        if (w or {}).get("driver") not in (None, "") + PROTOKOLL:
            self.g(name, "schickt sein Protokoll über %s weg (logging)" % w["driver"])

    def d_container_name(self, name, w, d):
        if RESERVIERT.search(str(w)):
            self.g(name, "Containernamen mit prolo… vergibt der Unterbau")
        self.hin.append("%s: fester Containername %s" % (name, w))

    def d_labels(self, name, w, d):
        for k in w or {}:
            if str(k).startswith(("com.docker.compose.", "prolo.")):
                self.g(name, "setzt das Label %s, das Compose bzw. prolo gehört" % k)
            elif str(k).startswith("traefik."):
                self.hin.append("%s: bringt eigene Traefik-Einstellungen mit - prolo ersetzt "
                                "sie" % name)
                break

    def d_deploy(self, name, w, d):
        res = (w or {}).get("resources") or {}
        if (res.get("reservations") or {}).get("devices"):
            self.g(name, "greift auf Geräte des Servers zu (deploy … devices)")

    def d_volumes_from(self, name, w, d):
        for v in w or []:
            quelle = str(v).split(":")[0] if not str(v).startswith("container:") else None
            if quelle not in self.dienste:
                self.g(name, "hängt die Volumes eines fremden Containers ein (volumes_from: %s)"
                       % v)

    def d_networks(self, name, w, d):
        oben = self.cfg.get("networks") or {}
        for netz, einst in (w or {}).items():
            if netz not in oben:
                self.g(name, "hängt in einem Netz %s, das die Datei nicht anlegt" % netz)
            einst = einst or {}
            fremd = sorted(set(einst) - DIENST_NETZ_FREI)
            if fremd:
                self.g(name, "Netz %s: %s" % (netz, ", ".join(fremd)))
            for a in einst.get("aliases") or []:
                if RESERVIERT.search(str(a)):
                    self.g(name, "Netz-Aliasse mit prolo… vergibt der Unterbau")

    def d_secrets(self, name, w, d):
        pass        # verweist nur auf die Eintraege oben - die sind geprueft

    d_configs = d_secrets

    def d_env_file(self, name, w, d):
        for e in w or []:
            pfad = e.get("path") if isinstance(e, dict) else e
            if pfad and not _innen(pfad, self.app):
                self.g(name, "liest Variablen vom Server: %s (env_file)" % pfad)

    def d_build(self, name, w, d):
        w = w or {}
        fremd = sorted(set(w) - BUILD_FREI)
        if fremd:
            self.g(name, "build: %s - das greift beim Bauen auf den Server zu" % ", ".join(fremd))
        ctx = str(w.get("context") or "")
        if ctx and not re.match(r"https://", ctx) and not (
                _innen(ctx, self.app) or os.path.realpath(ctx) == os.path.realpath(self.app)):
            self.g(name, "baut aus %s vom Server (build.context)" % ctx)
        if w.get("dockerfile") and ctx and not re.match(r"https://", ctx):
            df = os.path.join(ctx, str(w["dockerfile"]))
            if not _innen(df, self.app):
                self.g(name, "liest das Dockerfile %s vom Server" % w["dockerfile"])
        for k, v in (w.get("additional_contexts") or {}).items():
            v = str(v)
            if not (v.startswith(("docker-image://", "service:", "https://")) or
                    _innen(v, self.app)):
                self.g(name, "baut mit %s vom Server (additional_contexts)" % v)
        for c in w.get("cache_from") or []:
            if "type=local" in str(c):
                self.g(name, "liest beim Bauen vom Server (cache_from: %s)" % c)
        if str(w.get("network") or "default") not in ("default", "none"):
            self.g(name, "baut im Netz %s (build.network)" % w["network"])

    def d_volumes(self, name, w, d):
        oben = self.cfg.get("volumes") or {}
        app_echt = os.path.realpath(self.app)
        for v in w or []:
            if not isinstance(v, dict):
                self.g(name, "Einhängung %s versteht prolo nicht" % v)
                continue
            fremd = sorted(set(v) - EINHAENGEN_FREI)
            if fremd:
                self.g(name, "Einhängung %s: %s" % (v.get("target"), ", ".join(fremd)))
            art = v.get("type")
            if art == "volume":
                if v.get("source") and v["source"] not in oben:
                    self.g(name, "hängt ein Volume %s ein, das die Datei nicht anlegt"
                           % v["source"])
            elif art == "bind":
                quelle = os.path.realpath(str(v.get("source") or ""))
                if (v.get("bind") or {}).get("propagation") not in (None, "", "rprivate",
                                                                    "private"):
                    self.g(name, "teilt Einhängungen mit dem Server (%s)"
                           % v["bind"]["propagation"])
                if SOCKET.search(quelle):
                    self.g(name, "hängt den Docker-Socket ein - das ist root auf dem Server")
                elif quelle == app_echt:
                    self.g(name, "hängt seinen ganzen Ordner ein (samt .env)")
                elif not quelle.startswith(app_echt + os.sep):
                    self.g(name, "hängt %s vom Server ein - das liegt außerhalb des Tools und "
                           "wird NICHT gesichert" % quelle)
                    self.aussen.append(quelle)
            elif art != "tmpfs":
                self.g(name, "Einhängung der Art %s" % art)


def gefahren(cfg, app, projekt):
    """Alles, womit ein Container aus seinem Kaefig auf den Server greift.
    Gibt (gefahren, hinweise, binds_aussen) zurueck."""
    return Pruefung(cfg, app, projekt).alles()
