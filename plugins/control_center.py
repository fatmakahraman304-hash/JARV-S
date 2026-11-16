"""Open or close the Control Centre: Jarvis's network and live activity feed.

The window does the work (gui/control_center.py); this plugin only asks the
Qt thread to switch to it through player.show_control_center, which is
thread-safe. It also answers "what have you done so far?" from the same live
activity log, so the spoken answer and the screen never disagree.
"""
from core import activity, outcome

PLUGIN = {
    "name": "control_center",
    "description": (
        "Open or close the Control Centre (Kontrol Merkezi): the network view of "
        "Jarvis's capabilities and apps with the live activity feed of every action "
        "taken this session. Use when the user says 'kontrol merkezini aç', "
        "'ağı göster', 'canlı etkinliği göster', 'show the control centre/network', "
        "or asks what Jarvis has done so far in this session (action='summary'). "
        "Not for system CPU/memory stats — use system_status for those."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'open' (default), 'close', or 'summary' to list recent actions.",
            },
        },
        "required": [],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str((parameters or {}).get("action") or "open").strip().lower()
        if action == "summary":
            events = [e for e in activity.recent(40) if e.status != "info"][-10:]
            if not events:
                return outcome.done("control_center", actions_this_session=0)
            lines = "; ".join(f"{activity.NODE_LABEL.get(e.node, e.node)}: {e.text} [{e.status}]"
                              for e in events)
            return outcome.done("control_center", actions_this_session=len(events), recent=lines)
        if player is None or not hasattr(player, "show_control_center"):
            return outcome.failed("control_center", "the window is not available")
        opened = action != "close"
        player.show_control_center(opened)
        return outcome.done("control_center", opened=opened)
    except Exception as exc:          # a plugin never raises
        return outcome.failed("control_center", str(exc)[:160])
