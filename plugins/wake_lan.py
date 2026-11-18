"""Wake-on-LAN: aynı ağdaki başka bir bilgisayarı uzaktan aç ('masaüstünü uyandır')."""
from __future__ import annotations

import re
import socket

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "wake_lan",
    "description": (
        "Ağdaki başka bir bilgisayarı uzaktan aç (Wake-on-LAN): 'masaüstünü uyandır', 'oyun bilgisayarını aç'. "
        "action: wake (name) | save (name, mac: o bilgisayarın ağ kartı MAC adresi) | list | forget (name). "
        "O bilgisayarın BIOS'unda Wake-on-LAN açık olmalı."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "wake | save | list | forget"},
        "name": {"type": "STRING"}, "mac": {"type": "STRING"},
    }, "required": ["action"]},
}

FILE = "pc_extras.json"


def norm_mac(mac: str) -> str:
    hexs = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(hexs) != 12:
        raise ValueError("MAC adresi 12 onaltılık haneden oluşmalı (ör. AA:BB:CC:DD:EE:FF).")
    return ":".join(hexs[i:i + 2] for i in range(0, 12, 2)).upper()


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(norm_mac(mac).replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send(mac: str, broadcast: str = "255.255.255.255") -> None:
    pkt = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            s.sendto(pkt, (broadcast, port))


def find(saved: dict, name: str) -> tuple[str, str] | None:
    n = (name or "").casefold().strip()
    if not saved:
        return None
    if not n and len(saved) == 1:
        return next(iter(saved.items()))
    for k, v in saved.items():
        if k.casefold() == n:
            return k, v
    for k, v in saved.items():
        if n and (n in k.casefold() or k.casefold() in n):
            return k, v
    return None


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        act = str(p.get("action") or "wake").lower()
        cfg = kit.load(FILE)
        saved = cfg.setdefault("wol", {})
        name = str(p.get("name") or "").strip()
        if act == "save":
            if not name:
                return "Bu bilgisayara ne ad vereyim?"
            saved[name] = norm_mac(str(p.get("mac") or ""))
            kit.save(FILE, cfg)
            return f"Kaydettim: '{name}' ({saved[name]}). Artık '{name} bilgisayarını uyandır' diyebilirsin."
        if act == "list":
            return "Kayıtlı bilgisayarlar: " + ", ".join(f"{k} ({v})" for k, v in saved.items()) if saved else "Kayıtlı bilgisayar yok."
        if act == "forget":
            hit = find(saved, name)
            if not hit:
                return "Öyle kayıtlı bir bilgisayar yok."
            saved.pop(hit[0]); kit.save(FILE, cfg)
            return f"'{hit[0]}' silindi."
        hit = find(saved, name)
        if not hit:
            return ("Önce o bilgisayarı kaydetmem lazım: adını ve MAC adresini söyle "
                    "(Windows'ta o bilgisayarda 'getmac' komutu gösterir).") if not saved else \
                   f"'{name}' bulunamadı. Kayıtlı olanlar: {', '.join(saved)}."
        send(hit[1])
        kit.log(player, f"Wake-on-LAN: {hit[0]} ({hit[1]})")
        return f"{hit[0]} için uyandırma sinyali gönderdim; açılması bir dakika sürebilir."
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Uyandırma sinyali gönderilemedi: {exc}"
