"""Which house events JARVIS says by itself: doors/windows opening, and alarms (smoke, gas, leak, CO).

The watching is core/home_watch.py (needs Home Assistant connected through smart_home).
"""
from __future__ import annotations

PLUGIN = {
    "name": "home_alerts",
    "description": (
        "House events JARVIS announces by itself through Home Assistant: doors/windows/garage opening or closing "
        "(doors) and alarms — smoke, gas, water leak, carbon monoxide (alarms; also sent to the phone, even in "
        "quiet mode). 'kapı açılınca söyleme', 'kapı bildirimlerini aç', 'ev uyarıları açık mı'. "
        "action: on | off | status. kind: doors | alarms | all."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | status"},
        "kind": {"type": "STRING", "description": "doors | alarms | all"},
    }, "required": ["action"]},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import home_watch
        from memory.config_manager import save_plugin_config
        action = str(parameters.get("action") or "status").strip().lower()
        kind = str(parameters.get("kind") or "all").strip().lower()
        kinds = ("doors", "alarms") if kind in ("all", "") else (kind,)
        if any(k not in ("doors", "alarms") for k in kinds):
            return "Unknown kind; use doors, alarms or all."
        if action in ("on", "off"):
            save_plugin_config("home_alerts", {k: action == "on" for k in kinds})
        elif action != "status":
            return "Unknown action; use on, off or status."
        cur = home_watch.settings()
        warn = (" Alarms are off — smoke, gas and leaks will NOT be announced; say so plainly to the user."
                if not cur["alarms"] else "")
        return (f"Doors/windows: {'on' if cur['doors'] else 'off'}. Alarms (smoke, gas, leak, CO): "
                f"{'on' if cur['alarms'] else 'off'}.{warn}")
    except Exception as exc:
        return f"Could not change house alerts: {exc}"
