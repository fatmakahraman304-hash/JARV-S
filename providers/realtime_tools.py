"""First Realtime tool bridge: one bundled read-only guide, no general dispatch.

The model cannot select a Python module, file, command, or arbitrary plugin.
Only a validated topic from the published guide schema is accepted.
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
    result = ("Static guide for FRIDAY generally. Realtime preview cannot execute "
              "computer actions, inspect private memory or run diagnostics.\n" + result)
    return {"type": "conversation.item.create", "item": {
        "type": "function_call_output", "call_id": cid,
        "output": json.dumps({"guide": result}, ensure_ascii=False)}}
