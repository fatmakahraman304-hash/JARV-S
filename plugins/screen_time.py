"""Ekran süresi: bilgisayarda hangi uygulamada ne kadar zaman geçti.
Açınca her 30 saniyede öndeki uygulamaya bakar; yalnız bu bilgisayarda tutulur."""
from __future__ import annotations

import sys
import threading
import time
from datetime import date, timedelta

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "screen_time",
    "description": (
        "Bilgisayarda ekran süresi: 'ekran süremi takip et', 'bugün bilgisayarda ne kadar zaman geçirdim', "
        "'en çok hangi uygulamayı kullandım', 'bu hafta', 'takibi kapat'. action: start | report | stop. "
        "period: today | yesterday | week. Veriler yalnız bu bilgisayarda kalır."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "start | report | stop"},
        "period": {"type": "STRING", "description": "today | yesterday | week"},
    }, "required": ["action"]},
}

FILE = "screen_time.json"
STEP = 30
IDLE_LIMIT = 300            # no input this long: not counted
_state = {"on": False}

NAMES = {"chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "code": "VS Code", "explorer": "Dosya Gezgini",
         "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint", "spotify": "Spotify", "discord": "Discord",
         "whatsapp": "WhatsApp", "steam": "Steam", "python": "MAYK", "pythonw": "MAYK", "blender": "Blender",
         "obs64": "OBS", "vlc": "VLC", "teams": "Teams", "ms-teams": "Teams", "notepad": "Not Defteri"}


def app_label(proc: str) -> str:
    base = (proc or "").rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    base = base[:-4] if base.lower().endswith(".exe") else base
    return NAMES.get(base.lower(), base[:1].upper() + base[1:] if base else "Bilinmeyen")


def add_sample(data: dict, day: str, app: str, seconds: int) -> dict:
    d = data.setdefault(day, {})
    d[app] = d.get(app, 0) + seconds
    for k in sorted(data)[:-60]:          # keep 60 days
        data.pop(k, None)
    return data


def report_text(data: dict, period: str, today: date | None = None) -> str:
    today = today or date.today()
    if period == "yesterday":
        days, label = [today - timedelta(days=1)], "Dün"
    elif period == "week":
        days, label = [today - timedelta(days=i) for i in range(7)], "Son 7 günde"
    else:
        days, label = [today], "Bugün"
    tot: dict[str, int] = {}
    for d in days:
        for app, s in (data.get(d.isoformat()) or {}).items():
            tot[app] = tot.get(app, 0) + s
    total = sum(tot.values())
    if not total:
        return f"{label} için kayıt yok" + ("" if _state["on"] else " (takip kapalı; 'ekran süremi takip et' de)") + "."
    top = sorted(tot.items(), key=lambda kv: -kv[1])[:4]
    parts = ", ".join(f"{a} {kit.fmt_minutes(s / 60)}" for a, s in top)
    return f"{label} bilgisayarda {kit.fmt_minutes(total / 60)} aktiftin. En çok: {parts}."


def _active_app() -> str:
    if sys.platform == "win32":
        try:
            import win32gui, win32process, psutil
            _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
            return psutil.Process(pid).name()
        except Exception:
            return ""
    if sys.platform == "darwin":
        try:
            import subprocess
            return subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
                                  capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception:
            return ""
    try:
        import subprocess, psutil
        pid = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"], capture_output=True, text=True, timeout=3).stdout.strip()
        return psutil.Process(int(pid)).name() if pid else ""
    except Exception:
        return ""


def _idle_seconds() -> float:
    if sys.platform == "win32":
        try:
            import ctypes

            class LII(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            li = LII(); li.cbSize = ctypes.sizeof(LII)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
            return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
        except Exception:
            return 0.0
    return 0.0


def _loop():
    data = kit.load(FILE)
    n = 0
    while _state["on"]:
        time.sleep(STEP)
        try:
            if _idle_seconds() > IDLE_LIMIT:
                continue
            proc = _active_app()
            if proc:
                add_sample(data, date.today().isoformat(), app_label(proc), STEP)
                n += 1
                if n % 4 == 0:
                    kit.save(FILE, data)
        except Exception as exc:
            kit.out(f"[screen_time] {exc}")
    kit.save(FILE, data)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        act = str(p.get("action") or "report").lower()
        if act == "start":
            if not _state["on"]:
                _state["on"] = True
                threading.Thread(target=_loop, daemon=True, name="screen-time").start()
                cfg = kit.load("pc_extras.json"); cfg["screen_time"] = True; kit.save("pc_extras.json", cfg)
            return "Ekran süreni takip ediyorum (her 30 saniyede öndeki uygulama; veriler bu bilgisayarda kalır)."
        if act == "stop":
            _state["on"] = False
            cfg = kit.load("pc_extras.json"); cfg["screen_time"] = False; kit.save("pc_extras.json", cfg)
            return "Ekran süresi takibi kapatıldı."
        return report_text(kit.load(FILE), str(p.get("period") or "today").lower())
    except Exception as exc:
        return f"Ekran süresi okunamadı: {exc}"


# Turned on before: keep counting after a restart.
if kit.load("pc_extras.json").get("screen_time") and not _state["on"]:
    _state["on"] = True
    threading.Thread(target=_loop, daemon=True, name="screen-time").start()
