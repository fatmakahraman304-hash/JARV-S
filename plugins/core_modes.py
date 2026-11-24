"""Inspect core modes and prepare reusable task drafts without executing or saving."""
import json
from core import core_modes as core

PLUGIN = {
    "name": "core_modes",
    "tier": "core",
    "description": "30 çekirdek çalışma modu: list, guide (number 1–30), route (query), draft (name,goal,inputs,constraints,output,acceptance). Yalnızca öneri ve taslak; hiçbir işlemi yetkilendirmez, çalıştırmaz veya kaydetmez.",
    "parameters": {"type":"OBJECT","properties":{
        "action":{"type":"STRING","enum":["list","guide","route","draft"]},
        "number":{"type":"INTEGER"},"query":{"type":"STRING"},
        "name":{"type":"STRING"},"goal":{"type":"STRING"},"inputs":{"type":"STRING"},
        "constraints":{"type":"STRING"},"output":{"type":"STRING"},"acceptance":{"type":"STRING"},
    },"required":["action"]},
}

def run(parameters, player=None, session_memory=None):
    p = parameters or {}
    action = p.get("action")
    try:
        if action == "list":
            return "\n".join(f"{n}. {m.name}" for n,m in core.MODES.items())
        if action == "guide":
            return core.turn_hint((int(p.get("number")),)) or "Geçersiz çekirdek mod."
        if action == "route":
            return core.turn_hint(core.route(p.get("query", ""))) or "İstek gerekli."
        if action == "draft":
            task = core.subtask(**{k:p.get(k,"") for k in ("name","goal","inputs","constraints","output","acceptance")})
            return json.dumps(task, ensure_ascii=False)
    except (ValueError,TypeError,KeyError) as exc:
        return "status=failed: " + str(exc)[:200]
    return "Geçersiz işlem."
