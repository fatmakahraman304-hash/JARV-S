"""Shared helpers for the computer-side plugins added together (focus_mode,
laptop_battery, screen_time, system_alerts, …). The leading underscore keeps
the plugin loader from treating this file as a tool."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "memory"
_lock = threading.Lock()


def battery():
    import psutil
    try:
        return psutil.sensors_battery()
    except (AttributeError, OSError, NotImplementedError):
        return None


def out(text: str) -> None:
    """print() that never fails: a Windows console in cp1252 cannot show
    Turkish letters and would raise UnicodeEncodeError."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))
    except Exception:
        pass


def load(name: str, default=None):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def save(name: str, value) -> None:
    with _lock:
        DATA.mkdir(parents=True, exist_ok=True)
        tmp = DATA / (name + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(DATA / name)


def log(player, text: str) -> None:
    if player:
        try:
            player.write_log(f"AETHER: {text}")
        except Exception:
            pass
    out(f"[pc] {text}")


def say_at(ts: float, text: str, source: str, share: bool = True) -> str:
    """Said aloud here at `ts` (the desktop routines engine) and, when the
    devices are linked, put in the shared reminders so the phone/watch say it
    if they have the voice. Returns the shared reminder id or ""."""
    try:
        from core.routines import desktop
        eng = desktop.engine()
        if eng is not None:
            eng.add(name=text[:60], kind="say", text=text,
                    trigger={"type": "time", "rule": {"type": "once", "at_ts": ts}}, source=source)
    except Exception as exc:
        out(f"[pc] spoken copy not set: {exc}")
    if not share:
        return ""
    try:
        from core import sync_hub
        s = sync_hub.settings()
        if s.get("github_token") and s.get("gist_id"):
            return sync_hub.add_reminder(text, ts)
    except Exception as exc:
        out(f"[pc] not shared: {exc}")
    return ""


def say_soon(text: str, source: str = "pc-alert") -> None:
    """Say something now-ish (a background watcher noticed it)."""
    say_at(time.time() + 2, text, source, share=False)


def cancel(source: str, shared_ids=()) -> int:
    n = 0
    try:
        from core.routines import desktop
        eng = desktop.engine()
        if eng is not None:
            for r in eng.list():
                if r.get("source") == source:
                    n += bool(eng.remove(r["id"]))
    except Exception:
        pass
    try:
        from core import sync_hub
        for rid in shared_ids:
            sync_hub.cancel_reminder(rid)
    except Exception:
        pass
    return n


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def fmt_minutes(m: float) -> str:
    m = max(0, round(m))
    h, r = divmod(m, 60)
    return f"{h} sa {r} dk" if h and r else f"{h} sa" if h else f"{r} dk"
