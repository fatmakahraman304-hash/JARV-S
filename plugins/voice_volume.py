"""JARVIS's own voice level: 'sesini biraz kıs', 'daha yüksek konuş', 'gece sessiz konuş', 'gece kısma'.

Only JARVIS's speech gets louder or softer; the computer's volume (computer_settings) is untouched.
"""
from __future__ import annotations

PLUGIN = {
    "name": "voice_volume",
    "description": (
        "Loudness of JARVIS's OWN voice only (not the computer's volume, not music): 'sesini kıs', 'biraz daha "
        "yüksek konuş', 'sesin çok yüksek', 'gece daha sessiz konuş', 'gece sesini kısma'. action: set | louder | "
        "softer | night_on | night_off | status. level: for set, 10–150 (percent). night_level: for set, the night "
        "level. The computer's master volume is computer_settings, not this."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "set | louder | softer | night_on | night_off | status"},
        "level": {"type": "NUMBER", "description": "set: percent, 100 = normal"},
        "night_level": {"type": "NUMBER", "description": "set: percent used between 23:00 and 07:00"},
    }, "required": ["action"]},
}

STEP = 20


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import voice_level
        from memory.config_manager import save_plugin_config
        action = str(parameters.get("action") or "status").strip().lower()
        cur = voice_level.settings()
        changes = {}
        if action == "louder":
            changes["level"] = min(150, cur["level"] + STEP)
        elif action == "softer":
            changes["level"] = max(10, cur["level"] - STEP)
        elif action == "set":
            if parameters.get("level") not in (None, ""):
                changes["level"] = min(150, max(10, int(float(parameters["level"]))))
            if parameters.get("night_level") not in (None, ""):
                changes["night_level"] = min(150, max(10, int(float(parameters["night_level"]))))
        elif action in ("night_on", "night_off"):
            changes["night"] = action == "night_on"
        elif action != "status":
            return "Unknown action; use set, louder, softer, night_on, night_off or status."
        if changes:
            save_plugin_config("voice_level", changes)
            cur = voice_level.settings()
        night = (f"softer at night ({cur['night_level']}% from {cur['night_from']:02d}:00 to "
                 f"{cur['night_to']:02d}:00)" if cur["night"] else "the same at night")
        now = int(round(voice_level.gain() * 100))
        return f"JARVIS's voice: {cur['level']}%, {night}; right now {now}%. Reply at the new level in a few words."
    except Exception as exc:
        return f"Could not change the voice level: {exc}"
