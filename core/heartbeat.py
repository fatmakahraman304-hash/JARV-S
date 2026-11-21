"""
Heartbeats of MAYK's background watchers — so "kendini kontrol et" can tell a
watcher that is alive from one that quietly stopped.

Each watcher loop calls beat(name) once per pass; status() says how long ago
each one last beat. Nothing is persisted: it describes this run only.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_beats: dict[str, float] = {}
_stopped: dict[str, str] = {}

# how often each watcher passes, roughly: older than ~4× this means it is stuck
EXPECTED = {"away": 3, "vigil": 60, "sentinel": 15, "say_queue": 0.4}


def beat(name: str) -> None:
    with _lock:
        _beats[name] = time.monotonic()
        _stopped.pop(name, None)


def stopped(name: str, why: str) -> None:
    with _lock:
        _stopped[name] = why[:200]


def status(now: float | None = None) -> dict[str, dict]:
    """{name: {"age": seconds or None, "ok": bool, "why": str}} for every known watcher."""
    now = time.monotonic() if now is None else now
    with _lock:
        beats, gone = dict(_beats), dict(_stopped)
    out = {}
    for name in sorted(set(EXPECTED) | set(beats) | set(gone)):
        age = None if name not in beats else now - beats[name]
        limit = max(30.0, EXPECTED.get(name, 60) * 4)
        if name in gone:
            out[name] = {"age": age, "ok": False, "why": gone[name]}
        elif age is None:
            out[name] = {"age": None, "ok": True, "why": "not started yet"}
        else:
            out[name] = {"age": age, "ok": age <= limit, "why": "" if age <= limit else "no sign of life"}
    return out
