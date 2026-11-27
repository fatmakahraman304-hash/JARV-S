"""Budget and interruption guard for restricted cognitive-task tools."""
from __future__ import annotations

import hashlib
import json

from core import outcome

# Only tools with an understood interruption and privacy contract can be used.
# A future addition to TaskTools must not silently grant the workflow new powers.
_ALLOWED = frozenset({"search_web", "web_search", "fetch_page", "notes", "write_file",
                      "recall_memory", "system_snapshot"})


class CognitiveTools:
    def __init__(self, engine, tid, tools):
        self.engine, self.tid, self._tools = engine, tid, tools

    def __getattr__(self, name):
        return getattr(self._tools, name)

    @property
    def names(self):
        return [name for name in self._tools.names if name in _ALLOWED]

    def declarations(self):
        return [decl for decl in self._tools.declarations() if decl.get("name") in self.names]

    @property
    def on_page(self):
        return self._tools.on_page

    @on_page.setter
    def on_page(self, value):
        self._tools.on_page = value

    def execute(self, name, args):
        args = dict(args or {})
        if name not in self.names:
            return outcome.failed(name, "this tool is not available to cognitive workflows")
        changes = name == "write_file" or (name == "notes" and str(args.get("action") or "").lower() == "add")
        signature = hashlib.sha256(json.dumps([name, args], sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")).encode("utf-8")).hexdigest()
        decision = {}
        def reserve(task):
            budget = task["cognitive_budget"]
            ledger = task.setdefault("cognitive_ledger", {})
            existing = ledger.get(signature) if changes else None
            if existing:
                decision.update(existing)
                return
            if budget["used_calls"] >= budget["max_calls"]:
                task["cognitive_budget_exhausted"] = True
                decision["status"] = "budget_exhausted"
                return
            budget["used_calls"] += 1
            if changes:
                ledger[signature] = {"status": "started", "tool": name}
            decision["status"] = "run"
        self.engine.store.mutate(self.tid, reserve)
        if decision["status"] == "completed":
            return decision["result"]
        if decision["status"] == "started":
            return outcome.unverified(name, "a previous execution may have finished; inspect it before retrying",
                                      verified=False, retry_automatically=False)
        if decision["status"] == "budget_exhausted":
            return outcome.failed(name, "the cognitive task tool-call budget is exhausted")
        try:
            result = outcome.result_text(name, self._tools.execute(name, args))
        except Exception as exc:
            # The tool may already have acted; keep the started record for
            # explicit review rather than inventing a safe failure.
            if changes:
                return outcome.unverified(name, f"execution interrupted: {type(exc).__name__}",
                                          verified=False, retry_automatically=False)
            return outcome.failed(name, f"{type(exc).__name__}: {str(exc)[:160]}")
        if changes:
            if not result.startswith(f"status=done action={name}"):
                # A write may have partially happened before a tool returned an
                # error. Do not label it safely repeatable.
                return outcome.unverified(name, "the write outcome is uncertain; inspect it before retrying",
                                          verified=False, retry_automatically=False)
            def finish(task):
                task["cognitive_ledger"][signature] = {"status": "completed", "tool": name,
                                                        "result": result[:40000]}
            self.engine.store.mutate(self.tid, finish)
        return result


def has_uncertain_call(task):
    ledger = task.get("cognitive_ledger")
    # A missing or malformed ledger cannot establish that no write occurred.
    if not isinstance(ledger, dict):
        return True
    return any(not isinstance(value, dict) or value.get("status") != "completed"
               for value in ledger.values())
