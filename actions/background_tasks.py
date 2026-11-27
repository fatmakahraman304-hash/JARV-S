"""background_tasks — hand long work to an agent while the conversation goes on.

The tool is thin on purpose: everything that makes a task survive a restart,
respect a budget, wait out a quota or stay away from the user's computer lives
in core/tasks. This file turns what the model asked for into a call on the
engine and turns the answer back into facts (core/outcome.py) for the model to
say in the user's language.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta


def _when(at: str) -> float:
    """'YYYY-MM-DD HH:MM', or 'HH:MM' meaning the next time the clock reads it."""
    text = str(at or "").strip()
    now = datetime.now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    try:
        hm = datetime.strptime(text, "%H:%M")
    except ValueError:
        raise ValueError("'at' must be 'YYYY-MM-DD HH:MM' or 'HH:MM'") from None
    when = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return when.timestamp()


def _minutes(task: dict) -> str:
    return f"{task['used']['seconds'] / 60:.1f}/{task['budget']['minutes']} min"


def _row(t: dict) -> str:
    return f"{t['id']} [{t['status']}] {t['agent']} · {t['title']} · {_minutes(t)}"


def background_tasks(parameters: dict, player=None) -> str:
    from core import outcome
    from core.tasks import ACTIVE
    from core.tasks import desktop

    eng = desktop.ensure(player)
    a = dict(parameters or {})
    action = str(a.get("action") or "list").strip().lower()

    if action == "cognitive_start":
        try:
            doc = eng.cognitive.create(a.get("task"), a.get("nodes"), a.get("deliver") or "voice")
        except (ValueError, TypeError) as e:
            return outcome.failed("cognitive_workflow", str(e))
        return outcome.started("cognitive_workflow", workflow_id=doc["id"], nodes=len(doc["nodes"]),
                               note="independent nodes may run in parallel; final result is not independently verified")

    if action == "cognitive_list":
        docs = eng.cognitive.all()[:10]
        return ("\n".join(f"{p['id']} [{p['status']}] {p['goal'][:150]}" for p in docs)
                if docs else "No cognitive workflows yet.")

    if action in ("cognitive_status", "cognitive_cancel", "cognitive_revise"):
        try:
            wid = str(a.get("workflow_id") or "").strip()
            docs = eng.cognitive.all() if not wid else []
            doc = eng.cognitive.get(wid) if wid else (docs[0] if docs else None)
            if not doc:
                return outcome.failed("cognitive_workflow", "no such workflow")
            if action == "cognitive_cancel":
                if not eng.cognitive.cancel(doc["id"]):
                    return outcome.failed("cognitive_workflow", "workflow is not active")
                return outcome.started("cognitive_cancel", workflow_id=doc["id"],
                                       note="cancellation requested; an in-flight tool may still be stopping")
            if action == "cognitive_revise":
                if not eng.cognitive.revise(doc["id"], str(a.get("node_id") or ""), a.get("note")):
                    return outcome.failed("cognitive_workflow", "only an unstarted node can be revised")
                return outcome.done("cognitive_revise", workflow_id=doc["id"], node=a.get("node_id"))
        except (ValueError, TypeError) as e:
            return outcome.failed("cognitive_workflow", str(e))
        lines = [f"workflow_id={doc['id']} workflow_status={doc['status']}",
                 "Task reports do not independently verify the overall goal; monetary costs are not capped."]
        for node in doc["nodes"]:
            child = eng.get(node["task_id"])
            lines.append(f"{node['id']} · {node['status']} · {node['agent']} · attempt {node['attempt'] + 1}")
            if child:
                budget = child.get("cognitive_budget") or {}
                lines.append(f"  tool_calls={budget.get('used_calls', 0)}/{budget.get('max_calls', 0)}")
                if child.get("result"):
                    lines.append(outcome.untrusted("node-result", child["result"][:2000]))
            for artifact in node.get("artifacts") or []:
                lines.append(f"  file={artifact.get('location') or artifact.get('path')} verification={artifact.get('status')}")
        if doc.get("error"):
            lines.append("error=" + str(doc["error"])[:300])
        return "\n".join(lines)

    if action == "plan":
        try:
            plan = eng.plans.create(a.get("task"), a.get("steps"), a.get("deliver") or "voice")
        except (ValueError, TypeError) as e:
            return outcome.failed("background_plan", str(e))
        return outcome.started("background_plan", plan_id=plan["id"], steps=len(plan["steps"]),
                               note="steps run in order; the final outcome is not independently verified")

    if action == "plan_list":
        plans = eng.plans.all()[:10]
        return ("\n".join(f"{p['id']} [{p['status']}] {p['goal'][:150]}" for p in plans)
                if plans else "No background plans yet.")

    if action in ("plan_status", "plan_cancel"):
        try:
            plan_id = str(a.get("plan_id") or "").strip()
            if plan_id:
                plan = eng.plans.get(plan_id)
            else:
                plans = eng.plans.all()
                plan = next((p for p in plans if p["status"] == "running"), None) if action == "plan_cancel" else (plans[0] if plans else None)
        except ValueError as e:
            return outcome.failed("background_plan", str(e))
        if not plan:
            return outcome.failed("background_plan", "no such plan")
        if action == "plan_cancel":
            if not eng.plans.cancel(plan["id"]):
                return outcome.failed("background_plan", "this plan is not running")
            return outcome.started("background_plan_cancel", plan_id=plan["id"],
                                   note="cancellation requested; an in-flight tool may still be stopping")
        lines = [f"plan_id={plan['id']} plan_status={plan['status']}",
                 "Finished means task reports are ready; the overall outcome is not independently verified."]
        for index, step in enumerate(plan["steps"], 1):
            child = eng.get(step["task_id"])
            status = (child or {}).get("status", step.get("status", "pending"))
            lines.append(f"{index}. {step['task']} · {status} · {step['agent']} · {step['model_tier']}")
            for artifact in step.get("artifacts") or []:
                lines.append(f"  file={artifact.get('location') or artifact['path']} verification={artifact['status']} "
                             f"sha256={artifact.get('sha256', '')} checked_at={artifact.get('checked_at', '')}")
            if child and child.get("result"):
                lines.append(outcome.untrusted("step-result", child["result"][:2500]))
        if plan.get("error"):
            lines.append("error=" + str(plan["error"])[:300])
        return "\n".join(lines)

    if action == "start":
        task = str(a.get("task") or "").strip()
        if not task:
            return outcome.failed("background_tasks", "start needs the whole task, in the user's words")
        not_before = 0.0
        if a.get("at"):
            try:
                not_before = _when(a["at"])
            except ValueError as e:
                return outcome.failed("background_tasks", str(e))
        files = [a["file_path"]] if a.get("file_path") else None
        try:
            t = eng.start(task, agent=a.get("agent") or "general", minutes=a.get("minutes"),
                          deliver=a.get("deliver") or "voice", not_before=not_before, files=files)
        except ValueError as e:
            return outcome.failed("background_tasks", str(e))
        starts = time.strftime("%Y-%m-%d %H:%M", time.localtime(not_before)) if not_before else "now"
        return outcome.started("background_tasks", task_id=t["id"], agent=t["agent"],
                               minutes=t["budget"]["minutes"], starts=starts,
                               note="the result is announced when it is done; the conversation "
                                    "carries on meanwhile")

    if action == "agents":
        return "\n".join(f"{p.name}: {p.description} (default {p.minutes} min)"
                         for p in eng.agents(reload=True).values())

    if action == "list":
        rows = [_row(t) for t in eng.list(10)]
        return "\n".join(rows) if rows else "No background tasks yet."

    tid = str(a.get("task_id") or "").strip()
    tasks = eng.list(50)
    if tid:
        task = eng.get(tid)
    else:
        # No id: the task this most plausibly means — the latest still running,
        # or for a result, the latest at all.
        pool = tasks if action == "result" else [t for t in tasks if t["status"] in ACTIVE]
        task = pool[0] if pool else None
    if task is None:
        return outcome.failed("background_tasks", "no such task" if tid else "there is no task to act on")

    if action == "status":
        recent = [e["text"] for e in task.get("events") or [] if e["kind"] in ("progress", "tool")][-4:]
        return outcome.done("background_tasks", task_id=task["id"], status=task["status"],
                            agent=task["agent"], title=task["title"], time=_minutes(task),
                            rounds=f"{task['used']['rounds']}/{task['budget']['rounds']}",
                            recent=" | ".join(recent) or None, error=task.get("error") or None)
    if action == "result":
        if task["status"] != "done":
            return outcome.done("background_tasks", task_id=task["id"], status=task["status"],
                                note="not finished yet")
        return (outcome.done("background_tasks", task_id=task["id"], report=task.get("report") or None)
                + "\n" + outcome.untrusted("task-result", (task.get("result") or "")[:12_000]))
    if action == "finish":
        ok = eng.cancel(task["id"], finish=True)
        return (outcome.started("background_tasks", task_id=task["id"],
                                note="stopping and writing up what was found")
                if ok else outcome.failed("background_tasks", "that task is not running"))
    if action == "cancel":
        ok = eng.cancel(task["id"])
        return (outcome.done("background_tasks", task_id=task["id"], cancelled=True)
                if ok else outcome.failed("background_tasks", "that task is not running"))
    if action == "steer":
        ok = eng.steer(task["id"], a.get("note") or "")
        return (outcome.done("background_tasks", task_id=task["id"], note_added=True)
                if ok else outcome.failed("background_tasks", "needs a running task and a note"))
    return outcome.failed("background_tasks", f"unknown action '{action}'")


TOOL = {
    "name": "background_tasks",
    "description": (
        "Long work that runs in the background on this computer while the conversation carries on: "
        "real research, reading and comparing many sources, writing a report, working through a "
        "list. For a quick answer the user is waiting for, use web_search instead. "
        "start = hand the task to an agent — agent 'researcher' for research (it plans, reads "
        "sources in full, checks every quote against the page and writes a cited report), "
        "'general' for other work and 'system_diagnostics' for read-only local system assessment; "
        "task = the whole request, self-contained, in the user's words; "
        "minutes = the time budget when the user gives one ('research this for 10 minutes' -> 10); "
        "without one, 10 for research, more (20-40) when the user asks for something thorough or "
        "in depth; at = start later, "
        "'YYYY-MM-DD HH:MM' or 'HH:MM' local time ('tonight at 2' -> '02:00'); file_path = a file to "
        "work from. After start, say in one short sentence that it is under way — the result is "
        "announced by itself when done. "
        "list = the tasks and their state; status = how one is going; result = a finished task's "
        "result; finish = stop now and write up what was found; cancel = stop without a result; "
        "steer = add an instruction to a running task (note); agents = the available agents. "
        "plan = actually run an explicitly requested multi-step goal as 1-6 ordered background "
        "steps, each with task, agent, optional minutes and model_tier; choose fast only for "
        "simple extraction or formatting, smart for reasoning and all research. The user's "
        "existing provider preferences and model fallback remain in effect. Wait for a step to finish before "
        "starting the next. Use this only when the user wants work carried out, not merely "
        "a plan drafted. cognitive_start runs 1-6 nodes with explicit depends_on ids; "
        "independent nodes can run in parallel. Provide bounded alternatives where useful, "
        "without expanding tool permissions; uncertain operations are not repeated. Each node has minutes, rounds and max_calls; report or "
        "file_written selects the evidence check. Monetary costs are not capped. "
        "cognitive_list/status/cancel manage workflows; cognitive_revise updates only an unstarted "
        "node when the user asks. Do not treat generated reports as independently verified. "
        "The existing restricted background tools apply; no computer control, "
        "external messaging or purchases. plan_list shows saved plans, plan_status and "
        "plan_cancel accept plan_id or use the latest matching plan. Results "
        "are task reports, not proof that real-world actions succeeded. "
        "task_id may be left empty to mean the latest task."),
    "brief": "Runs background work: cognitive_start executes dependency graphs with budgets and "
             "cognitive_status/cancel/revise manage them; plan runs ordered steps. Also supports task start/list/status/cancel.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "enum": ["start", "list", "status", "result", "finish", "cancel", "steer", "agents", "plan", "plan_list", "plan_status", "plan_cancel", "cognitive_start", "cognitive_list", "cognitive_status", "cognitive_cancel", "cognitive_revise"]},
            "task": {"type": "STRING", "description": "for start: the whole task, self-contained"},
            "agent": {"type": "STRING", "description": "for start: researcher | general | system_diagnostics"},
            "minutes": {"type": "INTEGER", "description": "for start: time budget in minutes"},
            "at": {"type": "STRING", "description": "for start: when to begin, local time"},
            "deliver": {"type": "STRING", "enum": ["voice", "panel", "silent"],
                        "description": "for start: how to announce the result (default voice)"},
            "file_path": {"type": "STRING", "description": "for start: a file to work from"},
            "task_id": {"type": "STRING"},
            "note": {"type": "STRING", "description": "for steer: the new instruction"},
            "plan_id": {"type": "STRING", "description": "for plan_status or plan_cancel"},
            "workflow_id": {"type": "STRING", "description": "for cognitive workflow actions"},
            "node_id": {"type": "STRING", "description": "for cognitive_revise: unstarted node id"},
            "nodes": {"type": "ARRAY", "description": "for cognitive_start: 1-6 dependency graph nodes",
                      "items": {"type": "OBJECT", "properties": {
                          "id": {"type": "STRING"}, "task": {"type": "STRING"},
                          "agent": {"type": "STRING"},
                          "depends_on": {"type": "ARRAY", "items": {"type": "STRING"}},
                          "alternatives": {"type": "ARRAY", "items": {"type": "STRING"}},
                          "minutes": {"type": "INTEGER"}, "rounds": {"type": "INTEGER"},
                          "max_calls": {"type": "INTEGER"},
                          "model_tier": {"type": "STRING", "enum": ["fast", "smart"]},
                          "verification": {"type": "STRING", "enum": ["report", "file_written"]}},
                          "required": ["id", "task"]}},
            "steps": {"type": "ARRAY", "description": "for plan: 1-6 ordered steps",
                      "items": {"type": "OBJECT", "properties": {
                          "task": {"type": "STRING"},
                          "agent": {"type": "STRING", "description": "available agent, e.g. general, researcher or system_diagnostics"},
                          "minutes": {"type": "INTEGER"},
                          "model_tier": {"type": "STRING", "enum": ["fast", "smart"]}}, "required": ["task"]}},
        },
        "required": ["action"],
    },
    "handler": background_tasks,
}
