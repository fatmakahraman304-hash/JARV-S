"""Sistem uyarıları: işlemci uzun süre %90'ın üstünde, bellek dolmak üzere ya
da disk bitmek üzereyse MAYK kendiliğinden söyler (açılınca)."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "system_alerts",
    "description": (
        "Bilgisayarı arka planda izle ve sorun olunca haber ver: 'sistemi izle', 'bilgisayar zorlanınca söyle', "
        "'sistem uyarılarını kapat'. action: on | off | status. İşlemci 1,5 dakika %90 üstü, bellek %92 üstü, "
        "disk 5 GB altına inince en çok kaynak kullanan programla birlikte söyler (her uyarı en fazla saatte bir)."
    ),
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "description": "on | off | status"}}, "required": ["action"]},
}

STEP = 30
CPU_HIGH, CPU_SAMPLES, RAM_HIGH, DISK_LOW_GB, QUIET = 90, 3, 92, 5, 3600
_state = {"on": False}


def check(sample: dict, memo: dict, now: float) -> list[str]:
    """sample: {"cpu", "ram", "disk_free_gb", "top"}; memo keeps streaks and
    when each kind was last said. Returns what to say now."""
    out = []
    memo["cpu_streak"] = memo.get("cpu_streak", 0) + 1 if sample.get("cpu", 0) >= CPU_HIGH else 0
    top = f" En çok {sample['top']} kullanıyor." if sample.get("top") else ""
    want = []
    if memo["cpu_streak"] >= CPU_SAMPLES:
        want.append(("cpu", f"İşlemci bir süredir %{round(sample['cpu'])} çalışıyor.{top}"))
    if sample.get("ram", 0) >= RAM_HIGH:
        want.append(("ram", f"Bellek %{round(sample['ram'])} dolu, bilgisayar yavaşlayabilir.{top}"))
    if sample.get("disk_free_gb") is not None and sample["disk_free_gb"] < DISK_LOW_GB:
        want.append(("disk", f"Diskte yalnızca {sample['disk_free_gb']:.1f} GB kaldı; 'gereksiz dosyaları temizle' diyebilirsin."))
    for kind, text in want:
        last = memo.get("said_" + kind)
        if last is None or now - last >= QUIET:
            memo["said_" + kind] = now
            out.append(text)
    return out


def _sample() -> dict:
    import psutil
    import shutil
    procs = sorted(psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
                   key=lambda p: (p.info.get("cpu_percent") or 0) + (p.info.get("memory_percent") or 0), reverse=True)
    top = next((p.info["name"] for p in procs if p.info.get("name") and p.info["name"].lower() not in ("system idle process", "idle")), "")
    free = shutil.disk_usage(Path.home().anchor or "/").free / 1024 ** 3
    return {"cpu": psutil.cpu_percent(interval=1), "ram": psutil.virtual_memory().percent, "disk_free_gb": free, "top": top}


def _loop(player):
    memo: dict = {}
    while _state["on"]:
        try:
            for text in check(_sample(), memo, time.time()):
                kit.log(player, text)
                kit.say_soon(text, "system_alerts")
        except Exception as exc:
            kit.out(f"[alerts] {exc}")
        for _ in range(STEP):
            if not _state["on"]:
                return
            time.sleep(1)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        act = str((parameters or {}).get("action") or "status").lower()
        if act == "on":
            if not _state["on"]:
                _state["on"] = True
                threading.Thread(target=_loop, args=(player,), daemon=True, name="system-alerts").start()
            return "Sistemi izliyorum; işlemci, bellek ya da disk sorun çıkarırsa söyleyeceğim."
        if act == "off":
            _state["on"] = False
            return "Sistem uyarıları kapatıldı."
        return "Sistem uyarıları açık." if _state["on"] else "Sistem uyarıları kapalı; 'sistemi izle' dersen açarım."
    except Exception as exc:
        return f"Sistem uyarıları ayarlanamadı: {exc}"
