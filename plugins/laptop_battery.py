"""Laptop pili: durum, kalan süre, öneri — ve istenirse arka planda izleme
(%20 / %10'da şarja tak, %95'te şarjdan çıkar)."""
from __future__ import annotations

import threading
import time

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "laptop_battery",
    "description": (
        "Bilgisayarın/laptopun pili: 'pil kaç', 'şarj ne kadar gider', 'pili izle', 'pil uyarılarını kapat'. "
        "action: status | watch | unwatch. watch açıkken %20 ve %10'da şarja takmayı, %95'te (pil ömrü için) "
        "şarjdan çıkarmayı sesli hatırlatır. Telefonun/başka cihazın pili için status_report kullan."
    ),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "description": "status | watch | unwatch"}}},
}

LEVELS_LOW = (20, 10)
LEVEL_FULL = 95
_watch = {"on": False, "thread": None, "last": None}


def advice(percent: float, plugged: bool, secsleft) -> str:
    p = round(percent)
    if plugged:
        if p >= LEVEL_FULL:
            return f"Pil %{p}, şarjda. Pil ömrü için şarjdan çıkarabilirsin."
        return f"Pil %{p}, şarj oluyor."
    left = ""
    if isinstance(secsleft, (int, float)) and 0 < secsleft < 48 * 3600:
        left = f", yaklaşık {kit.fmt_minutes(secsleft / 60)} gider"
    tip = " Şarja takmanı öneririm." if p <= LEVELS_LOW[0] else ""
    return f"Pil %{p}, şarjda değil{left}.{tip}"


def crossing(prev, cur: float, plugged: bool) -> str:
    """The warning to give when the level crosses a threshold, else ""."""
    if prev is None:
        return ""
    if not plugged:
        for lvl in LEVELS_LOW:
            if prev > lvl >= cur:
                return f"Laptopun pili %{round(cur)}'e düştü, şarja tak." if lvl == 10 else f"Laptopun pili %{round(cur)}, şarj aletini yakına al."
    elif prev < LEVEL_FULL <= cur:
        return "Laptop %95 doldu; pil ömrü için şarjdan çıkarabilirsin."
    return ""


def _battery():
    import psutil
    return psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None


def _loop(player):
    while _watch["on"]:
        try:
            b = _battery()
            if b is not None:
                msg = crossing(_watch["last"], b.percent, bool(b.power_plugged))
                if msg:
                    kit.log(player, msg)
                    kit.say_soon(msg, "laptop_battery")
                _watch["last"] = b.percent
        except Exception as exc:
            print(f"[battery] {exc}")
        for _ in range(60):
            if not _watch["on"]:
                return
            time.sleep(1)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        act = str((parameters or {}).get("action") or "status").lower()
        b = _battery()
        if b is None:
            return "Bu bilgisayarda pil yok ya da okunamıyor (masaüstü olabilir)."
        if act == "unwatch":
            _watch["on"] = False
            return "Pil uyarıları kapatıldı."
        if act == "watch":
            if not _watch["on"]:
                _watch.update(on=True, last=b.percent)
                _watch["thread"] = threading.Thread(target=_loop, args=(player,), daemon=True, name="laptop-battery")
                _watch["thread"].start()
            return "Pili izliyorum: %20 ve %10'da şarja takmanı, %95'te çıkarmanı söyleyeceğim. " + advice(b.percent, bool(b.power_plugged), b.secsleft)
        return advice(b.percent, bool(b.power_plugged), b.secsleft)
    except Exception as exc:
        return f"Pil okunamadı: {exc}"
