"""Habits: what the user has FRIDAY do again and again, at about the same time.

Every successful tool call the user asked for is noted (tool, its short
arguments, the time) in a small file that survives restarts. `suggestions()`
looks at the last three weeks: the same command on at least four different days
within the same 90-minute window of the day is a habit, and FRIDAY may offer —
once — to make it a routine ("Her akşam 21:00 civarı Spotify'ı açtırıyorsun;
rutin yapayım mı?"). Nothing is ever set up without the user's yes.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

WINDOW_DAYS = 21
MIN_DAYS = 4
SPREAD_MIN = 45            # minutes either side of the usual time
KEEP_LINES = 5000

# tools that are not habits: looking things up about FRIDAY itself, memory, control of FRIDAY's own jobs
SKIP = {"save_memory", "recall_memory", "undo", "routines", "job_control", "work_status", "self_check",
        "self_update", "status_report", "background_tasks", "screen_process", "close_camera"}
_lock = threading.Lock()


def _dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "AetherMurat"


LOG = _dir() / "habits.jsonl"
OFFERED = _dir() / "habits_offered.json"


def signature(tool: str, args: dict | None) -> str:
    """The command in a stable short form: 'open_app: spotify'. Long free text is left out —
    'search for X' with a new X every time is not the same command."""
    vals = []
    for k in sorted((args or {}).keys()):
        v = (args or {}).get(k)
        if isinstance(v, (str, int, float, bool)) and str(v).strip():
            sv = " ".join(str(v).lower().split())
            if len(sv) <= 40:
                vals.append(sv)
    return f"{tool}: {', '.join(vals[:4])}" if vals else tool


def record(tool: str, args: dict | None, ok: bool = True, when: float | None = None) -> None:
    if not ok or tool in SKIP:
        return
    line = json.dumps({"t": when or time.time(), "tool": tool, "sig": signature(tool, args),
                       "args": {k: v for k, v in (args or {}).items() if isinstance(v, (str, int, float, bool))}},
                      ensure_ascii=False)
    with _lock:
        try:
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if LOG.stat().st_size > 2_000_000:          # keep the newest lines
                lines = LOG.read_text(encoding="utf-8").splitlines()[-KEEP_LINES:]
                LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def _events(now: float) -> list[dict]:
    try:
        rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []
    since = now - WINDOW_DAYS * 86400
    return [r for r in rows if r.get("t", 0) >= since]


def _offered() -> set:
    try:
        return set(json.loads(OFFERED.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def mark_offered(sig: str) -> None:
    done = _offered() | {sig}
    try:
        OFFERED.parent.mkdir(parents=True, exist_ok=True)
        OFFERED.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _circular_mean(minutes: list[float]) -> float:
    ang = [m / 1440 * 2 * math.pi for m in minutes]
    x, y = sum(math.cos(a) for a in ang), sum(math.sin(a) for a in ang)
    return (math.atan2(y, x) / (2 * math.pi) * 1440) % 1440


def _diff(a: float, b: float) -> float:
    d = abs(a - b) % 1440
    return min(d, 1440 - d)


def suggestions(now: float | None = None) -> list[dict]:
    """Habits not offered yet, strongest first:
    {"sig", "tool", "args", "time": "HH:MM", "days": n, "weekdays_only": bool, "of_days": span}"""
    now = now or time.time()
    by_sig = defaultdict(list)
    for r in _events(now):
        by_sig[r["sig"]].append(r)
    offered, out = _offered(), []
    for sig, rows in by_sig.items():
        if sig in offered:
            continue
        mins = [datetime.fromtimestamp(r["t"]).hour * 60 + datetime.fromtimestamp(r["t"]).minute for r in rows]
        centre = _circular_mean(mins)
        near = [r for r, m in zip(rows, mins) if _diff(m, centre) <= SPREAD_MIN]
        days = {datetime.fromtimestamp(r["t"]).date() for r in near}
        if len(days) < MIN_DAYS:
            continue
        centre = _circular_mean([datetime.fromtimestamp(r["t"]).hour * 60 + datetime.fromtimestamp(r["t"]).minute
                                 for r in near])
        hh, mm = int(centre // 60) % 24, int(round(centre % 60 / 5) * 5) % 60
        weekdays_only = all(d.weekday() < 5 for d in days) and len(days) >= 5
        out.append({"sig": sig, "tool": rows[-1]["tool"], "args": rows[-1].get("args", {}),
                    "time": f"{hh:02d}:{mm:02d}", "days": len(days), "weekdays_only": weekdays_only,
                    "of_days": WINDOW_DAYS})
    out.sort(key=lambda h: -h["days"])
    return out


def offer_text(h: dict) -> str:
    when = "hafta içi her gün" if h["weekdays_only"] else "her gün"
    return (f"[HABIT_SUGGESTION] Over the last {h['of_days']} days the user had you run {h['tool']} with "
            f"{json.dumps(h['args'], ensure_ascii=False)} on {h['days']} different days, each time around {h['time']} "
            f"({when}). In ONE short sentence, in their language, describe what they keep asking for and offer to do it "
            f"automatically {when} at {h['time']}. Only if they say yes: routines(action=add, kind=prompt, "
            f"time={h['time']}{', days=[1,2,3,4,5]' if h['weekdays_only'] else ''}, name=<a short name>, "
            f"text=<the instruction in their words, e.g. 'Spotify'ı aç'>). If they say no, drop it.")
