"""Limited Realtime tool bridge: static guide and HUD-confirmed volume/brightness.

The model cannot select a Python module, file, command, or arbitrary plugin.
Only strictly validated arguments to explicitly declared tools are accepted.
"""
from __future__ import annotations

import json
import re

from .realtime_transport import RealtimeError

TOPICS = ("index", "startup", "providers", "audio", "plugins", "routines",
          "updates", "diagnostics", "tasks")
MAX_ARGUMENTS = 2048
MAX_ROUNDS = 2


def declaration():
    return {"type": "function", "name": "assistant_help",
            "description": "Read FRIDAY's static user guide; does not execute actions or check live state.",
            "parameters": {"type": "object", "properties": {
                "topic": {"type": "string", "enum": list(TOPICS)}},
                "required": ["topic"], "additionalProperties": False}}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def guide_output(response, *, enabled, seen):
    """Return a function_call_output event or None; never execute other tools."""
    items = response.get("output", [])
    if not isinstance(items, list):
        raise RealtimeError("Realtime araç yanıtı geçersiz.")
    calls = [item for item in items if isinstance(item, dict) and item.get("type") == "function_call"]
    if not calls:
        return None
    if len(calls) != 1 or not enabled():
        raise RealtimeError("Realtime araç çağrısı izinli değil.")
    call = calls[0]
    cid, name, raw = call.get("call_id"), call.get("name"), call.get("arguments")
    if (name != "assistant_help" or call.get("status") != "completed"
            or not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cid)
            or cid in seen or not isinstance(raw, str) or len(raw) > MAX_ARGUMENTS):
        raise RealtimeError("Realtime araç çağrısı geçersiz.")
    try:
        args = json.loads(raw, object_pairs_hook=_unique_pairs)
        if (not isinstance(args, dict) or set(args) != {"topic"}
                or not isinstance(args["topic"], str) or args["topic"] not in TOPICS):
            raise ValueError("invalid topic")
    except (ValueError, RecursionError):
        raise RealtimeError("Realtime araç parametresi geçersiz.") from None
    seen.add(cid)
    from plugins.assistant_help import run
    result = run(args)
    # Clarify that this engine cannot perform actions mentioned in the guide.
    result = ("Static guide for FRIDAY generally. Realtime preview only supports explicitly "
              "enabled, HUD-confirmed controls; it cannot inspect private memory or run diagnostics.\n" + result)
    return {"type": "conversation.item.create", "item": {
        "type": "function_call_output", "call_id": cid,
        "output": json.dumps({"guide": result}, ensure_ascii=False)}}


def volume_declaration():
    return {"type": "function", "name": "request_volume",
            "description": "Request an absolute speaker volume change only on explicit user request. "
                           "The local HUD must approve it. Never claim it has been performed.",
            "parameters": {"type": "object", "properties": {
                "percent": {"type": "integer", "minimum": 0, "maximum": 100}},
                "required": ["percent"], "additionalProperties": False}}


def brightness_declaration():
    return {"type": "function", "name": "request_brightness",
            "description": "Request an absolute display brightness change (10–100 percent) only "
                           "on explicit user request. The local HUD must approve it.",
            "parameters": {"type": "object", "properties": {
                "percent": {"type": "integer", "minimum": 10, "maximum": 100}},
                "required": ["percent"], "additionalProperties": False}}


def tool_output(response, *, guide_enabled, volume_enabled, seen, brightness_enabled=None):
    """Select only an allowed function; never dispatch arbitrary action names."""
    items = response.get("output", [])
    if not isinstance(items, list):
        raise RealtimeError("Realtime araç yanıtı geçersiz.")
    calls = [item for item in items if isinstance(item, dict) and item.get("type") == "function_call"]
    if not calls:
        return None
    if len(calls) != 1:
        raise RealtimeError("Realtime araç çağrısı izinli değil.")
    call = calls[0]
    name = call.get("name")
    if name == "request_volume":
        allowed, minimum, action = volume_enabled, 0, "volume_set"
        key, label = "realtime_volume", "Hoparlör sesini"
    elif name == "request_brightness":
        allowed, minimum, action = brightness_enabled or (lambda: False), 10, "brightness_set"
        key, label = "realtime_brightness", "Ekran parlaklığını"
    else:
        return guide_output(response, enabled=guide_enabled, seen=seen)
    cid, raw = call.get("call_id"), call.get("arguments")
    if (not allowed() or call.get("status") != "completed"
            or not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cid)
            or cid in seen or not isinstance(raw, str) or len(raw) > MAX_ARGUMENTS):
        raise RealtimeError("Realtime ayar kontrolü izinli değil.")
    try:
        args = json.loads(raw, object_pairs_hook=_unique_pairs)
        if (not isinstance(args, dict) or set(args) != {"percent"}
                or type(args["percent"]) is not int or not minimum <= args["percent"] <= 100):
            raise ValueError("invalid volume")
    except (ValueError, RecursionError):
        raise RealtimeError("Realtime ayar seviyesi geçersiz.") from None
    seen.add(cid)
    target = args["percent"]
    from core import confirm

    def after_human_approval():
        if not allowed():
            return "NOT EXECUTED: Realtime izni veya oturumu sona erdi."
        from actions.computer_settings import computer_settings
        return computer_settings({"action": action, "value": target})

    # The actual fixed operation is retained locally by the existing HUD gate.
    # Nothing returned to the model can approve it or substitute parameters.
    result = confirm.request(
        key=key, title=f"{label} %{target} yap",
        detail=f"Realtime {label.lower()} %{target} yapmak istiyor. "
               "Yalnızca ekrandaki onayınızdan sonra uygulanır.",
        run=after_human_approval)
    pending = result.startswith("[CONFIRMATION_PENDING]")
    return {"type": "conversation.item.create", "item": {
        "type": "function_call_output", "call_id": cid,
        "output": json.dumps({"status": "pending_confirmation" if pending else "not_executed",
                              "percent": target,
                              "message": "Not performed. Ask for HUD approval." if pending
                                         else "Not performed; confirmation unavailable."})}}
