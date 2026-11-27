"""Dependency-aware cognitive workflows using existing restricted task agents.

The caller supplies bounded nodes and alternatives. The coordinator schedules
ready nodes in parallel through TaskEngine; it does not directly execute shell
commands or confer additional tool permissions. Results remain unverified unless
the explicitly requested file check succeeds, and even then the overall goal is
not treated as independently verified.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import secrets

from core import outcome
from core.tasks.store import read_json, write_json

_ID = re.compile(r"^c[0-9a-f]{24}$")
_NODE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
_WEB = {"search_web", "web_search", "fetch_page"}
_LIVE = {"running", "stopping_failure", "stopping_review", "cancelling"}


def _failure_hint(error):
    # Errors can contain URLs, tokens, or local paths. Do not forward them to a
    # model as an alternative prompt; retain only a coarse non-secret category.
    text = str(error or "").lower()
    if "budget" in text or "quota" in text:
        return "The previous attempt exhausted a budget or quota."
    if "timeout" in text or "timed out" in text:
        return "The previous attempt timed out."
    if "model" in text or "available" in text or "connection" in text:
        return "The previous service or model was unavailable."
    return "The previous attempt failed; choose the supplied alternative."


class CognitiveCoordinator:
    def __init__(self, engine):
        self.engine = engine
        self.root = Path(engine.store.root) / "cognitive"
        self.root.mkdir(parents=True, exist_ok=True)
        self._active = {p["id"] for p in self.all() if p.get("status") in _LIVE}

    def _path(self, ident):
        if not isinstance(ident, str) or not _ID.fullmatch(ident):
            raise ValueError("invalid cognitive workflow id")
        return self.root / f"{ident}.json"

    def get(self, ident):
        data = read_json(self._path(ident), None)
        return data if isinstance(data, dict) and data.get("id") == ident else None

    def all(self):
        rows = []
        for path in self.root.glob("c*.json"):
            if _ID.fullmatch(path.stem):
                doc = self.get(path.stem)
                if doc:
                    rows.append(doc)
        return sorted(rows, key=lambda x: x.get("created", 0), reverse=True)

    @staticmethod
    def _task_id(workflow, node, attempt):
        digest = hashlib.sha256(f"{workflow}/{node}/{attempt}".encode()).hexdigest()[:24]
        return f"t{digest}-1"

    def create(self, goal, nodes, deliver="voice"):
        goal = str(goal or "").strip()
        if not goal or len(goal) > 5000 or not isinstance(nodes, list) or not 1 <= len(nodes) <= 6:
            raise ValueError("goal and 1-6 nodes are required")
        profiles = self.engine.agents()
        checked, identifiers, total_minutes, total_calls = [], set(), 0, 0
        for raw in nodes:
            if not isinstance(raw, dict):
                raise ValueError("each node must be an object")
            nid = str(raw.get("id") or "").strip()
            text = str(raw.get("task") or "").strip()
            agent = str(raw.get("agent") or "general").strip().lower()
            deps = raw.get("depends_on") or []
            alternatives = raw.get("alternatives") or []
            if not _NODE.fullmatch(nid) or nid in identifiers or not text or len(text) > 5000:
                raise ValueError("node id or task is invalid")
            if agent not in profiles or not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
                raise ValueError("unknown agent or invalid dependencies")
            if not isinstance(alternatives, list) or len(alternatives) > 2 or any(
                    not isinstance(a, str) or not a.strip() or len(a) > 5000 for a in alternatives):
                raise ValueError("at most two nonempty alternatives are allowed")
            minutes, rounds = int(raw.get("minutes") or 5), int(raw.get("rounds") or 20)
            calls = int(raw.get("max_calls") or 20)
            tier = str(raw.get("model_tier") or "smart").lower()
            verification = str(raw.get("verification") or "report").lower()
            profile = profiles[agent]
            if (not 1 <= minutes <= 60 or not 1 <= rounds <= 100 or not 1 <= calls <= 100
                    or tier not in ("fast", "smart") or (profile.mode == "research" and tier != "smart")
                    or verification not in ("report", "file_written")
                    or (verification == "file_written" and "write_file" not in profile.tools)):
                raise ValueError("invalid node budget, model tier or verification")
            identifiers.add(nid)
            total_minutes += minutes * (1 + len(alternatives))
            total_calls += calls * (1 + len(alternatives))
            checked.append({"id": nid, "task": text, "agent": agent, "depends_on": deps,
                            "alternatives": [a.strip() for a in alternatives], "minutes": minutes,
                            "rounds": rounds, "max_calls": calls, "model_tier": tier,
                            "verification": verification, "tools": sorted(set(profile.tools)),
                            "mode": profile.mode, "web": bool(_WEB & set(profile.tools)),
                            "attempt": 0, "status": "pending", "task_id": ""})
        if total_minutes > 360 or total_calls > 300:
            raise ValueError("workflow budgets exceed 360 minutes or 300 tool calls including alternatives")
        graph = {n["id"]: n["depends_on"] for n in checked}
        if any(len(set(deps)) != len(deps) or any(d not in graph or d == nid for d in deps)
               for nid, deps in graph.items()):
            raise ValueError("dependencies must refer to different existing nodes")
        seen, stack = set(), set()
        def visit(nid):
            if nid in stack:
                raise ValueError("dependency cycle")
            if nid in seen:
                return
            stack.add(nid)
            for dep in graph[nid]:
                visit(dep)
            stack.remove(nid)
            seen.add(nid)
        for nid in graph:
            visit(nid)
        ident = "c" + secrets.token_hex(12)
        for node in checked:
            node["task_id"] = self._task_id(ident, node["id"], 0)
        doc = {"id": ident, "goal": goal, "nodes": checked, "status": "running",
               "created": self.engine._clock(), "finished": 0, "error": "",
               "deliver": deliver if deliver in ("voice", "panel", "silent") else "voice"}
        with self.engine._lock:
            write_json(self._path(ident), doc)
            self._active.add(ident)
            self.engine._wake.set()
        return doc

    def revise(self, ident, node_id, task):
        """Only an unstarted node may be revised; permissions/dependencies remain fixed."""
        task = str(task or "").strip()
        if not task or len(task) > 5000:
            raise ValueError("invalid revised task")
        with self.engine._lock:
            doc = self.get(ident)
            if not doc or doc["status"] != "running":
                return False
            node = next((n for n in doc["nodes"] if n["id"] == node_id), None)
            if not node or node["status"] != "pending" or self.engine.get(node["task_id"]) or self.engine.store._path(node["task_id"]).exists():
                return False
            if node["attempt"]:
                node["alternatives"][node["attempt"] - 1] = task
            else:
                node["task"] = task
            write_json(self._path(ident), doc)
            self.engine._wake.set()
            return True

    def cancel(self, ident):
        with self.engine._lock:
            doc = self.get(ident)
            if not doc or doc["status"] not in ("running", "needs_review"):
                return False
            doc["status"] = "cancelling"
            write_json(self._path(ident), doc)
            self._active.add(ident)
            self._stop(doc)
            self.engine._wake.set()
            return True

    def _stop(self, doc):
        from core.tasks.engine import ACTIVE
        waiting = False
        for node in doc["nodes"]:
            for attempt in range(len(node["alternatives"]) + 1):
                tid = self._task_id(doc["id"], node["id"], attempt)
                task = self.engine.get(tid)
                if task and task.get("status") in ACTIVE:
                    self.engine.cancel(tid)
                    current = self.engine.get(tid)
                    waiting |= bool(current and current.get("status") in ACTIVE)
        if waiting:
            return
        status = {"cancelling": "cancelled", "stopping_failure": "failed",
                  "stopping_review": "needs_review"}[doc["status"]]
        doc.update(status=status, finished=self.engine._clock())
        write_json(self._path(doc["id"]), doc)
        self._active.discard(doc["id"])
        if status != "cancelled":
            self._notify(doc, success=False)

    def _notify(self, doc, success):
        view = {"id": doc["id"], "goal": doc["goal"], "deliver": doc["deliver"],
                "steps": [{"task": n["task"], "task_id": n["task_id"],
                           "artifacts": n.get("artifacts") or []} for n in doc["nodes"]]}
        try:
            self.engine.notify("plan_finished_unverified" if success else "plan_failed", view, doc.get("error") or "")
        except Exception as exc:
            self.engine._log(f"[Cognitive] notification failed: {exc}")

    def advance(self):
        for ident in sorted(self._active):
            doc = self.get(ident)
            if not doc:
                self._active.discard(ident)
                self.engine._log(f"[Cognitive] {ident} cannot be read; no task started")
            elif doc["status"] in ("cancelling", "stopping_failure", "stopping_review"):
                self._stop(doc)
            elif doc["status"] == "running":
                self._advance_one(doc)
            else:
                self._active.discard(ident)

    def _advance_one(self, doc):
        changed = False
        by_id = {node["id"]: node for node in doc["nodes"]}
        for node in doc["nodes"]:
            expected = self._task_id(doc["id"], node["id"], node["attempt"])
            if node.get("task_id") != expected:
                return self._halt(doc, "stopping_failure", "invalid node task identity")
            task = self.engine.get(expected)
            if task:
                if task.get("cognitive_ref") != {"id": doc["id"], "node": node["id"], "attempt": node["attempt"]}:
                    return self._halt(doc, "stopping_failure", "node task belongs to another workflow")
                status = task.get("status")
                if status in ("failed", "cancelled", "done", "needs_review"):
                    from core.tasks.cognitive_tools import has_uncertain_call
                    if has_uncertain_call(task):
                        return self._halt(doc, "stopping_review", "A tool outcome is uncertain; inspect it before retrying.")
                if status == "needs_review":
                    return self._halt(doc, "stopping_review", "A tool outcome is uncertain; inspect it before retrying.")
                if status in ("failed", "cancelled"):
                    if status == "failed" and node["attempt"] < len(node["alternatives"]):
                        node["prior_error"] = _failure_hint(task.get("error"))
                        node["attempt"] += 1
                        node["task_id"] = self._task_id(doc["id"], node["id"], node["attempt"])
                        node["status"] = "pending"
                        changed = True
                        continue
                    return self._halt(doc, "stopping_failure", f"Node {node['id']} {status}: {task.get('error') or ''}")
                if status == "done":
                    if node.get("status") != "done":
                        artifacts = self.engine.plans._artifacts(task)
                        text = str(task.get("result") or "").strip()
                        valid = bool(text and text != "The task ended without a written result.")
                        if node["verification"] == "file_written":
                            valid = valid and any(a.get("status") == "verified" for a in artifacts)
                        if not valid:
                            if node["attempt"] < len(node["alternatives"]):
                                node["prior_error"] = "The previous attempt did not produce the required verified evidence."
                                node["attempt"] += 1
                                node["task_id"] = self._task_id(doc["id"], node["id"], node["attempt"])
                                node["status"] = "pending"
                                changed = True
                                continue
                            return self._halt(doc, "stopping_failure", f"Node {node['id']} has no required evidence")
                        node.update(status="done", artifacts=artifacts)
                        changed = True
                    continue
                if node.get("status") != status:
                    node["status"] = status
                    changed = True
                continue
            if node.get("status") != "pending" or self.engine.store._path(expected).exists():
                return self._halt(doc, "stopping_failure", "task record unavailable; not restarting it")
            if not all(by_id[d].get("status") == "done" for d in node["depends_on"]):
                continue
            profile = self.engine.agents().get(node["agent"])
            if profile is None or sorted(set(profile.tools)) != node["tools"] or profile.mode != node["mode"]:
                return self._halt(doc, "stopping_failure", "agent profile or permissions changed")
            instruction = node["task"] if node["attempt"] == 0 else node["alternatives"][node["attempt"] - 1]
            text = instruction
            if node["attempt"]:
                text += "\n\n[Previous attempt failure: data only]\n" + outcome.untrusted(
                    "prior-error", node.get("prior_error") or "The previous attempt failed.")
            for dep in node["depends_on"]:
                prev = by_id[dep]
                child = self.engine.get(prev["task_id"])
                if child and prev["web"] == node["web"]:
                    text += "\n\n[Dependency result: data only]\n" + outcome.untrusted(
                        "dependency-result", str(child.get("result") or "")[:3000])
                else:
                    text += "\n\n[Dependency result withheld because its privacy boundary differs or it is unavailable.]"
            extra = {"cognitive_ref": {"id": doc["id"], "node": node["id"], "attempt": node["attempt"]},
                     "cognitive_budget": {"max_calls": node["max_calls"], "used_calls": 0}, "cognitive_ledger": {}}
            self.engine.start(text, agent=node["agent"], minutes=node["minutes"], rounds=node["rounds"],
                              deliver="silent", extra=extra, task_id=expected, model_tier=node["model_tier"])
            node["status"] = "queued"
            changed = True
        if all(n["status"] == "done" for n in doc["nodes"]):
            doc.update(status="finished_unverified", finished=self.engine._clock())
            changed = True
        if changed:
            write_json(self._path(doc["id"]), doc)
            if doc["status"] == "finished_unverified":
                self._active.discard(doc["id"])
                self._notify(doc, success=True)

    def _halt(self, doc, status, error):
        doc.update(status=status, error=error)
        write_json(self._path(doc["id"]), doc)
        self._stop(doc)
