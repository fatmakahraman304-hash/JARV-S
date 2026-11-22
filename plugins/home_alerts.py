"""Which house events AETHER says by itself: doors/windows opening, and alarms (smoke, gas, leak, CO).

The watching is core/home_watch.py (needs Home Assistant connected through smart_home).
"""
from __future__ import annotations

PLUGIN = {
    "name": "home_alerts",
    "description": (
        "House events AETHER announces by itself through Home Assistant: doors/windows/garage opening or closing "
        "(doors) and alarms — smoke, gas, water leak, carbon monoxide (alarms; also sent to the phone, even in "
        "quiet mode), and presence — a welcome home when someone arrives, a phone note about lights left on "
        "when they leave (presence). 'kapı açılınca söyleme', 'eve gelince karşılama', 'ev uyarıları açık mı'. "
        "action: on | off | status. kind: doors | alarms | presence | all."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | status"},
        "kind": {"type": "STRING", "description": "doors | alarms | presence | all"},
    }, "required": ["action"]},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import home_watch
        from memory.config_manager import save_plugin_config
        action = str(parameters.get("action") or "status").strip().lower()
        kind = str(parameters.get("kind") or "all").strip().lower()
        kinds = ("doors", "alarms", "presence") if kind in ("all", "") else (kind,)
        if any(k not in ("doors", "alarms", "presence") for k in kinds):
            return "Unknown kind; use doors, alarms, presence or all."
        if action in ("on", "off"):
            save_plugin_config("home_alerts", {k: action == "on" for k in kinds})
        elif action != "status":
            return "Unknown action; use on, off or status."
        cur = home_watch.settings()
        warn = (" Alarms are off — smoke, gas and leaks will NOT be announced; say so plainly to the user."
                if not cur["alarms"] else "")
        return (f"Doors/windows: {'on' if cur['doors'] else 'off'}. Alarms (smoke, gas, leak, CO): "
                f"{'on' if cur['alarms'] else 'off'}. Presence (welcome home, lights left on): "
                f"{'on' if cur['presence'] else 'off'}.{warn}")
    except Exception as exc:
        return f"Could not change house alerts: {exc}"
