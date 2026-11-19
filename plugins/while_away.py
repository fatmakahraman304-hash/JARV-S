"""'Ben yokken ne oldu?' — what came up while the user was away.

JARVIS keeps what it could not tell an empty room (core/away.py) and tells it
once when the user is back. This answers the question directly: what is still
waiting to be told (and marks it told), or, if that was already said, the last
welcome-back report again. Read-only otherwise: it never starts anything.
"""
from __future__ import annotations

import time

PLUGIN = {
    "name": "while_away",
    "description": (
        "What came up while the user was away or JARVIS was asleep — finished jobs, reminders, system alerts, "
        "updates that could not be told then. Use for 'ben yokken ne oldu?', 'kaçırdığım bir şey var mı?', "
        "'what did I miss?', and to hear the last welcome-back report again. Never starts or repeats a job. "
        "action=welcome_off when the user does not want to be greeted on coming back to the desk "
        "('döndüğümde karşılama'), welcome_on to have it again. action=push_off when they do not want phone "
        "notifications about jobs finished / alarms while they are away from the desk, push_on to have them again."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "report (default) | welcome_on | welcome_off | push_on | push_off"},
    }},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import away
        action = str((parameters or {}).get("action") or "report").strip().lower()
        if action in ("welcome_on", "welcome_off"):
            from memory.config_manager import save_plugin_config
            on = action == "welcome_on"
            save_plugin_config("away", {"welcome": on})
            return ("The welcome back after a long absence is on." if on else
                    "No more welcome back after an absence; news that came up while away is still told.")
        if action in ("push_on", "push_off"):
            from memory.config_manager import save_plugin_config
            on = action == "push_on"
            save_plugin_config("away", {"push": on})
            return ("Phone notifications while away from the desk are on." if on else
                    "No phone notifications while away; everything is still told on return.")
        items = away.take()
        if items:
            return ("Not yet told — report these briefly, most important first, merging related items and "
                    "dropping progress notes a later item makes stale:\n" + away.describe(items))
        last = away.last_told()
        if last.get("items"):
            told = float(last.get("told_at") or time.time())
            mins = int((time.time() - told) // 60)
            return (f"Nothing new since the last welcome-back report ({mins} min ago). That report was:\n"
                    + away.describe(last["items"]))
        return "Nothing came up while the user was away; nothing is waiting to be told."
    except Exception as exc:
        return f"Could not read what happened while you were away: {exc}"
