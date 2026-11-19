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
        "'what did I miss?', and to hear the last welcome-back report again. Never starts or repeats a job."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import away
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
