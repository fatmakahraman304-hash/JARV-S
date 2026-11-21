"""Ambient awareness switches: which changes around the computer Mayk mentions by itself.

The watching is core/sentinel.py; this only holds the user's choice per kind.
"""
from __future__ import annotations

PLUGIN = {
    "name": "awareness",
    "description": (
        "Which changes around the computer Mayk mentions by itself: a USB drive plugged in/out (usb), the "
        "charger plugged/unplugged (power), the internet back after an outage (network), a download finished "
        "(downloads). Turn a kind off ('USB takınca söyleme', 'indirmeleri bildirme'), on, or ask what is on. "
        "action: on | off | status. kind: usb | power | network | downloads | all. "
        "action=recent: what just happened, with full paths — use it to resolve 'az önce indirdiğim dosya', "
        "'son indirilen', 'taktığım USB' before opening, sending or listing it (kind: download | usb, optional)."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | status | recent"},
        "kind": {"type": "STRING", "description": "usb | power | network | downloads | all"},
    }, "required": ["action"]},
}

NAMES = {"usb": "USB drives", "power": "the charger", "network": "the internet coming back",
         "downloads": "finished downloads"}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sentinel
        from memory.config_manager import save_plugin_config
        action = str(parameters.get("action") or "status").strip().lower()
        kind = str(parameters.get("kind") or "all").strip().lower()
        if action == "recent":
            want = {"downloads": "download", "download": "download", "usb": "usb"}.get(kind, "")
            items = sentinel.recent(want)
            if not items:
                return "Nothing noticed recently" + (f" of that kind ({kind})." if want else ".")
            import time as _t
            now = _t.time()
            return "Most recent first:\n" + "\n".join(
                f"- {int((now - float(i['at'])) // 60)} min ago, {i['kind']}: {i['text']}"
                + (f" — {i['path']}" if i.get("path") else "") for i in items)
        if action in ("on", "off"):
            kinds = sentinel.KINDS if kind in ("all", "") else (kind,)
            if any(k not in sentinel.KINDS for k in kinds):
                return f"Unknown kind '{kind}'; use usb, power, network, downloads or all."
            save_plugin_config("awareness", {k: action == "on" for k in kinds})
        elif action != "status":
            return "Unknown action; use on, off or status."
        cur = sentinel.settings()
        on = [NAMES[k] for k in sentinel.KINDS if cur[k]]
        off = [NAMES[k] for k in sentinel.KINDS if not cur[k]]
        return ("Mentioned by itself: " + (", ".join(on) or "nothing") + "."
                + (" Off: " + ", ".join(off) + "." if off else ""))
    except Exception as exc:
        return f"Could not change the awareness settings: {exc}"
