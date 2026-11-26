"""'Bir saat rahatsız etme', 'toplantıdayım', 'film izliyorum sessiz ol', 'sessiz modu kapat'.

The state and rules are core/quiet.py; FRIDAY holds back everything it would
volunteer and tells it in one short report when quiet ends.
"""
from __future__ import annotations

PLUGIN = {
    "name": "quiet_mode",
    "description": (
        "Do-not-disturb for FRIDAY itself: while on, it volunteers nothing (finished jobs, things it noticed, "
        "offers, check-ins, news wait and are told in one short report afterwards); reminders still come and "
        "it still answers when spoken to. 'bir saat rahatsız etme', 'toplantıdayım', 'film izliyorum, sessiz "
        "ol', 'ben söyleyene kadar sessiz', 'sessiz modu kapat', 'sessiz mod açık mı'. "
        "action: on | off | status. minutes: how long (omit for 'until I say'). reason: optional, e.g. 'meeting'. "
        "listen=false for a meeting or a phone call ('toplantıdayım', 'telefondayım', 'görüşmedeyim'): FRIDAY also "
        "stops listening so other people's words are not taken as commands, and wakes by itself when it ends."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | status"},
        "minutes": {"type": "NUMBER", "description": "on: how many minutes; omit for until the user ends it"},
        "reason": {"type": "STRING", "description": "on: why (meeting, film, call …), optional"},
        "listen": {"type": "BOOLEAN", "description": "on: false = also stop listening (meetings, calls)"},
    }, "required": ["action"]},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import away, quiet
        action = str(parameters.get("action") or "status").strip().lower()
        if action == "on":
            minutes = parameters.get("minutes")
            minutes = float(minutes) if minutes not in (None, "") else None
            listen = parameters.get("listen")
            listen = True if listen is None else str(listen).lower() not in ("false", "0", "no")
            quiet.start(minutes, str(parameters.get("reason") or ""), listen=listen)
            if not listen and player is not None and hasattr(player, "request_sleep"):
                try:
                    player.request_sleep("sessiz mod — dinlemiyorum")   # after the confirmation is heard
                except Exception:
                    pass
            if player is not None:
                try:
                    player.write_log("SYS: Sessiz mod açık — " + quiet.describe())
                except Exception:
                    pass
            return quiet.describe() + " Confirm in a few words ('Anlaşıldı, efendim; sessizim.') and say nothing more."
        if action == "off":
            was = quiet.stop()
            if not was:
                return "Quiet mode was not on."
            n = len(away.pending())
            return ("Quiet mode is off." + (f" {n} held item(s) will be told in a moment." if n else
                                            " Nothing came up meanwhile."))
        if action == "status":
            return quiet.describe()
        return "Unknown action; use on, off or status."
    except Exception as exc:
        return f"Could not change quiet mode: {exc}"
