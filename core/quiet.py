"""
Quiet mode — "Mute, sir." / "Bir saat rahatsız etme." / "Toplantıdayım."

While it is on JARVIS volunteers nothing: finished jobs, things it noticed, care
notes, offers, check-ins and news all wait (in the same digest as when the user
is away, core/away.py) and are told in one short report when quiet ends. What
the user asked to be reminded of still comes — they asked for that moment — and
JARVIS still answers whenever it is spoken to.

It ends by itself after the time given, or when the user says so. State is on
disk, so a restart in the middle of a meeting does not break the silence.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_PATH = BASE_DIR / "memory" / "quiet.json"
MAX_HOURS = 12                  # "until I say" still ends by itself — never silent for days
_lock = threading.Lock()


def _read() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(data: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        print(f"[Quiet] {exc}")


def start(minutes: float | None = None, reason: str = "", now: float | None = None, listen: bool = True) -> dict:
    """Quiet for `minutes` (None: until the user says, at most MAX_HOURS). listen=False (a meeting, a
    call): JARVIS also stops listening — asleep, so other people's words are not taken as commands —
    and wakes by itself when the quiet ends."""
    now = time.time() if now is None else now
    mins = MAX_HOURS * 60 if not minutes or minutes <= 0 else min(float(minutes), MAX_HOURS * 60)
    data = {"since": now, "until": now + mins * 60, "open": not minutes, "reason": (reason or "")[:80],
            "listen": bool(listen)}
    with _lock:
        _write(data)
    return data


def last_listen_off(now: float | None = None) -> bool:
    """The quiet on record (even if just expired) had listening off — for waking up when it ends."""
    data = _read()
    return bool(data.get("until")) and data.get("listen") is False


def stop() -> dict:
    """End it; returns what it was (empty if it was not on)."""
    with _lock:
        data = _read()
        _write({})
    return data if data.get("until") else {}


def state(now: float | None = None) -> dict:
    """The current quiet, or {} when not on (an expired one counts as off)."""
    now = time.time() if now is None else now
    data = _read()
    if not data.get("until") or now >= float(data["until"]):
        return {}
    return data


def is_on(now: float | None = None) -> bool:
    return bool(state(now))


def holds(kind: str, now: float | None = None) -> bool:
    """Whether something of this kind waits while quiet: everything volunteered, not reminders."""
    return kind not in ("reminder", "heads_up") and is_on(now)


def describe(now: float | None = None) -> str:
    now = time.time() if now is None else now
    data = state(now)
    if not data:
        return "Quiet mode is off."
    left = int((float(data["until"]) - now) // 60)
    why = f" ({data['reason']})" if data.get("reason") else ""
    if data.get("listen") is False:
        why += ", not listening (asleep; wake word or the WAKE button to talk)"
    if data.get("open"):
        return f"Quiet mode is on until the user ends it{why}; it ends by itself in {left} min at the latest."
    return f"Quiet mode is on for {left} more min{why}."


def ended_instruction(items: list[dict], describe_items) -> str:
    """What the session is told when quiet ends with things waiting."""
    return ("[QUIET_ENDED] Quiet mode is over. While it was on, these came up and were held back:\n"
            + describe_items(items) + "\nTell the user, J.A.R.V.I.S.-style, in at most three short "
            "sentences, most important first: merge related items, drop progress a later item makes "
            "stale, outcomes not steps. Do not call any tool, and do not repeat them later.")
