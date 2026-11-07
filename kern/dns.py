"""Ein winziger DNS-Dienst: admin.<domain> im VPN (N-149).

Mit ADMIN_NETZE (N-141) ist die Admin-Seite nur aus dem VPN erreichbar, etwa
aus Tailscale (100.64.0.0/10). Im oeffentlichen DNS zeigt admin.<domain> aber
auf die oeffentliche Adresse - ein Geraet im VPN ginge trotzdem uebers
Internet und waere ausgesperrt. Dieser Dienst antwortet im VPN: admin.<domain>
ist die VPN-Adresse des Servers. Tailscale fragt ihn per "Split DNS" nur fuer
diesen einen Namen; das oeffentliche DNS (und damit das Zertifikat) bleibt.

Er beantwortet genau einen Namen, lauscht nur auf der VPN-Adresse, laeuft als
Nutzer ohne Rechte (systemd DynamicUser) und liest nichts als das Paket.
Alles andere bekommt REFUSED, Unsinn wird verworfen. Ein DNS-Paket ist
fremde Eingabe: jede Laenge wird geprueft, bevor gelesen wird.
"""
import ipaddress
import socket
import struct

PORT = 53
GROESSE = 512           # klassisches UDP-DNS; groessere Anfragen braucht hier niemand
TTL = 60
IP_FREEBIND = 15        # Linux: binden, auch wenn die Adresse (noch) nicht da ist

A, AAAA, ANY, KLASSE_IN = 1, 28, 255, 1
NOERROR, FORMERR, REFUSED, NOTIMP = 0, 1, 5, 4


def _kopf(kennung, flags_frage, rcode, antworten):
    # QR=1, AA=1, RD wie gefragt, RA=0 (wir fragen niemanden weiter)
    flags = 0x8000 | 0x0400 | (flags_frage & 0x0100) | rcode
    return struct.pack("!HHHHHH", kennung, flags, 1, antworten, 0, 0)


def frage_lesen(paket):
    """(kennung, flags, name, typ, klasse, rohe frage) - oder None, wenn das
    Paket keine einfache Anfrage ist."""
    if not 12 <= len(paket) <= GROESSE:
        return None
    kennung, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", paket[:12])
    if flags & 0x8000 or qd != 1 or an or ns:
        return None                 # eine Antwort, oder mehr als eine Frage
    i, teile = 12, []
    while True:
        if i >= len(paket):
            return None
        laenge = paket[i]
        i += 1
        if laenge == 0:
            break
        if laenge > 63 or i + laenge > len(paket) or len(teile) >= 127:
            return None             # auch: Zeiger (0xC0) gibt es in einer Frage nicht
        teile.append(paket[i:i + laenge])
        i += laenge
    if i + 4 > len(paket):
        return None
    typ, klasse = struct.unpack("!HH", paket[i:i + 4])
    try:
        name = b".".join(teile).decode("ascii").lower()
    except UnicodeDecodeError:
        return None
    return kennung, flags, name, typ, klasse, paket[12:i + 4]


def antwort(paket, name, ip):
    """Die Antwort auf ein Paket, oder None (verwerfen)."""
    f = frage_lesen(paket)
    if f is None:
        return None
    kennung, flags, frage_name, typ, klasse, frage = f
    if (flags >> 11) & 0xF:                         # nur gewoehnliche Anfragen
        return _kopf(kennung, flags, NOTIMP, 0) + frage
    if frage_name != name or klasse != KLASSE_IN:
        return _kopf(kennung, flags, REFUSED, 0) + frage
    if typ in (A, ANY):
        satz = struct.pack("!HHHIH", 0xC00C, A, KLASSE_IN, TTL, 4) + \
            ipaddress.IPv4Address(ip).packed
        return _kopf(kennung, flags, NOERROR, 1) + frage + satz
    return _kopf(kennung, flags, NOERROR, 0) + frage   # AAAA u. a.: gibt es nicht


def laufen(name, ip, port=PORT):
    name = name.lower().rstrip(".")
    ipaddress.IPv4Address(ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_IP, IP_FREEBIND, 1)
    s.bind((ip, port))
    print("DNS: %s -> %s, nur auf %s:%d" % (name, ip, ip, port), flush=True)
    while True:
        try:
            paket, von = s.recvfrom(4096)
            a = antwort(paket, name, ip)
            if a is not None:
                s.sendto(a, von)
        except OSError as e:
            print("DNS: %s" % e, flush=True)
