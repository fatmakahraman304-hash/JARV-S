"""Care notes: JARVIS mentions — once — a long stretch without a break or working in the small hours.

'Bana mola hatırlatma' → off. 'Mola hatırlatmalarını aç' → on. 'Dört saatte bir söyle' → hours=4.
The watching itself is core/vigil.py; this only holds the user's choice.
"""
from __future__ import annotations

PLUGIN = {
    "name": "care_notes",
    "description": (
        "JARVIS's care notes — the single, film-style remark when the user has worked for hours without a break "
        "or is still at it in the small hours. Turn them off ('bana mola hatırlatma', 'gece uyarma'), back on, "
        "change after how many hours, or ask whether they are on. action: on | off | status | set. "
        "hours: for set (1–12). late_night: for set, whether the small-hours note is wanted."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | status | set"},
        "hours": {"type": "NUMBER", "description": "set: hours of work without a break before the note"},
        "late_night": {"type": "BOOLEAN", "description": "set: also note working between 01:00 and 05:00"},
    }, "required": ["action"]},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import vigil
        from memory.config_manager import save_plugin_config
        action = str(parameters.get("action") or "status").strip().lower()
        cur = vigil.settings()
        if action == "off":
            save_plugin_config("care", {"enabled": False})
            return "Care notes are off: no more break or late-night remarks until the user turns them back on."
        if action == "on":
            save_plugin_config("care", {"enabled": True})
            cur = vigil.settings()
        elif action == "set":
            values = {"enabled": True}
            if parameters.get("hours") not in (None, ""):
                values["stretch_hours"] = min(12.0, max(1.0, float(parameters["hours"])))
            if parameters.get("late_night") is not None:
                values["late_night"] = bool(parameters["late_night"])
            save_plugin_config("care", values)
            cur = vigil.settings()
        elif action != "status":
            return "Unknown action; use on, off, status or set."
        if not cur["enabled"]:
            return "Care notes are off."
        hours = cur["stretch_hours"]
        hours_txt = f"{int(hours)}" if float(hours).is_integer() else f"{hours:g}"
        late = "and once a night when working between 01:00 and 05:00" if cur["late_night"] else \
            "(the late-night note is off)"
        return f"Care notes are on: one remark after {hours_txt} h of work without a 20-minute break, {late}."
    except Exception as exc:
        return f"Could not change the care notes: {exc}"
