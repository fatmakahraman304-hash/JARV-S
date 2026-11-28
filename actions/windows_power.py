"""User-facing Windows power scheme control, with a durable encrypted journal."""
from __future__ import annotations

import json
import platform

from core import outcome
from core import windows_executive as executive
from core.neural_journal import JournalError


def windows_power(parameters: dict, player=None) -> str:
    args = dict(parameters or {})
    action = str(args.get("action") or "status").strip().lower()
    if platform.system() != "Windows":
        return outcome.failed("windows_power", "Windows power control is available only on Windows")
    try:
        if action == "status":
            snapshot = executive.status()
            pending = executive.pending_operations()
            shown = False
            if player is not None:
                try:
                    player.show_content("WINDOWS GÜÇ PLANI", json.dumps(snapshot, ensure_ascii=False, indent=2))
                    shown = True
                except Exception:
                    pass
            result = outcome.done("windows_power_status", observed=True, panel_shown=shown,
                                  pending_count=len(pending))
            from core.hardware_privacy import model_sharing_enabled
            if model_sharing_enabled():
                result += "\n" + outcome.untrusted("power-status", json.dumps(snapshot))
            return result
        if action == "history":
            history = executive.operation_history()
            return ("\n".join(f"operation_id={x['id']} status={x['status']}" for x in history)
                    if history else "No Windows power operations recorded.")
        if action in ("set", "pointer_speed"):
            if player is None:
                return outcome.failed("windows_power", "The local desktop interface is unavailable")
            mode = str(args.get("mode") or "").strip().lower()
            record = executive.set_plan(mode) if action == "set" else executive.set_pointer_speed(args.get("speed"))
            label = "Windows güç planı" if action == "set" else "Windows işaretçi hızı"
            facts = {"mode": mode} if action == "set" else {"speed": args["speed"]}
            if record["status"] == "unchanged":
                return outcome.done("windows_power", **facts, changed=False, verified=True)
            ident = record["operation_id"]
            from core.undo import push_undo
            def restore():
                executive.undo(ident)
                return "Previous Windows setting verified."
            push_undo(label, restore)
            return outcome.done("windows_power", **facts, changed=True, verified=True, operation_id=ident)
        if action == "undo":
            if player is None:
                return outcome.failed("windows_power", "The local desktop interface is unavailable")
            ident = str(args.get("operation_id") or "").strip()
            executive.undo(ident)
            return outcome.done("windows_power_undo", operation_id=ident, verified=True)
        if action == "review":
            if player is None:
                return outcome.failed("windows_power", "The local desktop interface is unavailable")
            ident = str(args.get("operation_id") or "").strip()
            record = next((x for x in executive.pending_operations() if x["id"] == ident), None)
            if not record:
                return outcome.failed("windows_power", "No matching unresolved operation")
            from core import confirm
            expected = record["status"]
            detail = (f"İşlem {ident}. Windows ayarını kontrol edin. Onay yalnızca belirsiz işlem "
                      "kaydını incelenmiş olarak işaretler; ayarı değiştirmez veya geri almaz.")
            def acknowledge():
                executive.acknowledge(ident, expected)
                return outcome.done("windows_power_review", operation_id=ident, system_changed=False)
            return confirm.request("windows_power_review", "Belirsiz Windows işlemini incele", detail, acknowledge)
        return outcome.failed("windows_power", "Unknown action")
    except executive.UnknownOutcome as exc:
        return outcome.unverified("windows_power", "the operation may have changed Windows; inspect before retrying",
                                  operation_id=exc.operation_id, retry_automatically=False)
    except (executive.ExecutiveError, JournalError, ValueError) as exc:
        return outcome.failed("windows_power", str(exc))
    except Exception as exc:
        return outcome.failed("windows_power", type(exc).__name__)


TOOL = {
    "name": "windows_power",
    "description": ("Windows only. Inspect the power plan locally or select an existing built-in "
                    "balanced, power_saver or high_performance plan. The setting is checked before and "
                    "after; it is reversible. pointer_speed sets mouse pointer speed (1–20) for this Windows session. Do not claim success unless verified. history lists operation "
                    "ids; undo needs the operation_id; review requires the user's physical confirmation "
                    "for an unresolved operation. Never invent availability or change another setting."),
    "brief": "Inspect or reversibly switch an existing Windows power scheme with verification.",
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["status", "set", "pointer_speed", "undo", "history", "review"]},
        "speed": {"type": "INTEGER", "description": "Mouse pointer speed 1 through 20"},
        "mode": {"type": "STRING", "enum": ["balanced", "power_saver", "high_performance"]},
        "operation_id": {"type": "STRING"}}, "required": ["action"]},
    "handler": windows_power,
}
