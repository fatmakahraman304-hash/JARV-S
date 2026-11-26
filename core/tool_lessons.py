"""FRIDAY learns from its own mistakes with any tool.

A tool call fails; a few minutes later the same tool succeeds with different
arguments (the app's real name, the right folder, another platform). That pair
is a lesson: "open_app with app_name='spotfy' failed (not found); app_name='Spotify'
worked." Lessons are kept on disk, the recent ones go into every session, and
when the same mistake is about to repeat, the failing result carries the cure.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

WINDOW = 600.0           # a success within ten minutes of the failure counts as its fix
KEEP = 200
_lock = threading.Lock()
_last_fail: dict[str, dict] = {}


def _path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "AetherMurat" / "tool_lessons.json"


PATH = _path()
SKIP = {"save_memory", "recall_memory", "work_status", "self_check", "capabilities", "job_control"}


def _short(args: dict | None) -> dict:
    return {k: v for k, v in (args or {}).items() if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 120}


def load() -> list[dict]:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-KEEP:], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, PATH)


def record(tool: str, args: dict | None, ok: bool, result: str = "", now: float | None = None) -> dict | None:
    """Note one call. Returns the lesson when this success fixes a recent failure."""
    if tool in SKIP:
        return None
    now = now or time.time()
    a = _short(args)
    with _lock:
        if not ok:
            first = next((l for l in str(result).splitlines() if l.strip()), "")[:200]
            _last_fail[tool] = {"args": a, "error": first, "t": now}
            return None
        fail = _last_fail.pop(tool, None)
        if not fail or now - fail["t"] > WINDOW or fail["args"] == a:
            return None
        lesson = {"tool": tool, "bad": fail["args"], "good": a, "error": fail["error"],
                  "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(now))}
        items = [l for l in load() if not (l["tool"] == tool and l["bad"] == lesson["bad"])]
        items.append(lesson)
        try:
            _save(items)
        except OSError:
            pass
        return lesson


def hint(tool: str, args: dict | None) -> str:
    """When a call fails the way it failed before: what worked then."""
    a = _short(args)
    for l in reversed(load()):
        if l["tool"] == tool and l["bad"] == a:
            return (f"[LESSON] This exact call failed before too; then {tool} worked with "
                    f"{json.dumps(l['good'], ensure_ascii=False)}. Use that instead.")
    return ""


def prompt_block(limit: int = 8) -> str:
    items = load()[-limit:]
    if not items:
        return ""
    lines = [f"- {l['tool']}: {json.dumps(l['bad'], ensure_ascii=False)} failed ({l['error'][:80]}); "
             f"{json.dumps(l['good'], ensure_ascii=False)} worked" for l in items]
    return "\n[LESSONS FROM YOUR OWN MISTAKES — do it the way that worked]\n" + "\n".join(lines) + "\n"
