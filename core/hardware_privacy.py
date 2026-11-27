"""Policy for hardware measurements crossing the local/model boundary.

The user's opt-in is deliberately narrow: it does not authorize device sync,
file transfer, screenshots, conversations or other classes of private data.
"""
from __future__ import annotations

import json
import math

from core import outcome


def model_sharing_enabled() -> bool:
    try:
        from memory.config_manager import get_hardware_model_sharing
        return get_hardware_model_sharing() is True
    except Exception:
        return False


def _percentage(value):
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 100):
        return round(value, 1)
    return None


def system_status_result(snapshot, player=None):
    """Keep the full status local; disclose only CPU/RAM percentages on opt-in."""
    shown = False
    if player is not None:
        try:
            player.show_content("SİSTEM DURUMU", json.dumps(snapshot, ensure_ascii=False, indent=2))
            shown = True
        except Exception:
            pass
    result = outcome.done("system_status", observed=True, panel_shown=shown)
    if model_sharing_enabled():
        selected = {key: _percentage(snapshot.get(key)) for key in ("cpu_percent", "ram_percent")}
        # Recheck after processing so a revoked preference fails closed.
        if model_sharing_enabled():
            result += "\n" + outcome.untrusted("local-system-metrics", json.dumps(selected))
    return result


async def route_monitor_alert(alert, player, send_model=None):
    """Always display the measured alert locally; send only a generic alert if allowed.

    Alerts are not forwarded to devices or an away queue: model consent is not
    authorization to sync hardware data over the separate device transport.
    """
    if not alert:
        return False
    try:
        player.write_log("SYS: " + str(alert))
    except Exception:
        pass
    if send_model is None or not model_sharing_enabled():
        return False
    await send_model("[SYSTEM_ALERT] The local system monitor raised a resource warning. "
                     "Tell the user to check the local activity panel; do not invent measurements.")
    return True
