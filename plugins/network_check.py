"""İnternet kontrolü: bağlantı var mı, ne kadar hızlı yanıt veriyor, DNS çalışıyor mu."""
from __future__ import annotations

import socket
import time

PLUGIN = {
    "name": "network_check",
    "description": (
        "İnternet bağlantısını kontrol et: 'internet çalışıyor mu', 'internet neden yavaş', 'ping kaç', "
        "'ağ durumunu kontrol et'. Gecikme, DNS ve yerel IP'yi ölçer ve ne yapılabileceğini söyler."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}

TARGETS = (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443))


def tcp_ms(host: str, port: int, timeout: float = 2.0):
    t = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - t) * 1000)
    except OSError:
        return None


def dns_ms(name: str = "www.google.com"):
    t = time.perf_counter()
    try:
        socket.getaddrinfo(name, 443)
        return round((time.perf_counter() - t) * 1000)
    except OSError:
        return None


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def verdict(pings: list, dns, ip: str) -> str:
    ok = [p for p in pings if p is not None]
    if not ip:
        return "Bu bilgisayar hiçbir ağa bağlı değil: Wi-Fi'yi ya da kabloyu kontrol et."
    if not ok:
        return f"Ağa bağlısın (IP {ip}) ama internete çıkılamıyor: modemi kapatıp açmayı dene."
    best = min(ok)
    lost = len(pings) - len(ok)
    dns_part = "DNS çalışmıyor — adresler çözülemiyor; DNS'i 1.1.1.1 yapmak işe yarayabilir. " if dns is None else \
               f"DNS yavaş ({dns} ms). " if dns > 300 else ""
    if best < 40:
        q = "İnternet iyi"
    elif best < 120:
        q = "İnternet normal"
    else:
        q = "İnternet yavaş"
    tail = " Modeme yaklaşmak ya da kablo kullanmak yardımcı olur." if best >= 120 or lost else ""
    loss = f", {lost}/{len(pings)} hedef yanıt vermedi" if lost else ""
    return f"{q}: gecikme {best} ms{loss}. {dns_part}Yerel IP {ip}.{tail}".replace("  ", " ")


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        return verdict([tcp_ms(h, p) for h, p in TARGETS], dns_ms(), local_ip())
    except Exception as exc:
        return f"Ağ kontrol edilemedi: {exc}"
