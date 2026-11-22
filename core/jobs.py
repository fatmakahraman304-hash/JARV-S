"""Long jobs AETHER is running right now — and how to stop each one.

A job registers itself when it starts (`with jobs.running("Blender: apartman", cancel=fn): ...`)
and disappears when it ends. "dur", "iptal et", "vazgeçtim" go through `cancel()`:
the matching job (or every job) is asked to stop; work_status lists them.
"""
from __future__ import annotations

import itertools
import threading
import time
from contextlib import contextmanager


class Cancelled(BaseException):
    """Raised inside a job that the user stopped. A BaseException on purpose: the many
    `except Exception` retry loops inside a job must not swallow a stop."""


_lock = threading.Lock()
_ids = itertools.count(1)
_jobs: dict[int, dict] = {}


@contextmanager
def running(name: str, cancel=None):
    jid = next(_ids)
    with _lock:
        _jobs[jid] = {"id": jid, "name": name, "started": time.time(), "cancel": cancel}
    try:
        yield jid
    finally:
        with _lock:
            _jobs.pop(jid, None)


def current() -> list[dict]:
    with _lock:
        return [dict(j) for j in _jobs.values()]


def describe() -> list[str]:
    now = time.time()
    return [f"- {j['name']} ({int(now - j['started'])} sn'dir sürüyor)" for j in current()]


def cancel(which: str = "") -> list[str]:
    """Stop the jobs whose name contains `which` (all of them when empty). Returns their names."""
    w = (which or "").lower().strip()
    stopped = []
    for j in current():
        if w and w not in j["name"].lower():
            continue
        fn = j.get("cancel")
        try:
            if fn:
                fn()
            stopped.append(j["name"])
        except Exception:
            pass
    return stopped
