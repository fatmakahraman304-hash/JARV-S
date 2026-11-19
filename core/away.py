"""
While you were away — what JARVIS had to say when nobody was there to hear it.

In the films J.A.R.V.I.S. never reports to an empty room: Tony walks back in and
hears "Welcome home, sir" and then what happened. Here, before this module, a
result that arrived while JARVIS was asleep (wake-word mode) was spoken by the
model and its audio thrown away, and one that arrived while the user had simply
left the desk was said to no one. Both were lost.

Now every announcement passes through `should_hold()`. When the user is away it
goes into the digest instead (kept on disk, so a restart does not lose it), and
when they come back — they wake JARVIS, speak, or touch the mouse or keyboard —
`take()` hands the whole digest over once, to be told in one short welcome.

Away means: JARVIS is asleep (nothing it says is heard), or nobody has spoken to
it AND nobody has touched the computer for AWAY_AFTER seconds. When the system
cannot report input idleness, silence alone counts, over a longer window.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIGEST_PATH = BASE_DIR / "memory" / "away_digest.json"

AWAY_AFTER = 15 * 60            # speech AND input both quiet this long: away
AWAY_AFTER_NO_INPUT = 30 * 60   # when input idleness is unknown, silence alone, longer
BACK_INPUT = 20                 # input within this many seconds: someone is here again
MAX_ITEMS = 30
KEEP_FOR = 24 * 3600            # older than this is no longer news

_lock = threading.Lock()


# ── input idleness ────────────────────────────────────────────────────────────

def input_idle_seconds() -> float | None:
    """Seconds since the last mouse or keyboard input, or None when this system can't say."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return max(0.0, ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0)
    except Exception:
        return None


def is_away(awake: bool, speech_quiet: float, input_idle: float | None) -> bool:
    """The user would not hear JARVIS now."""
    if not awake:
        return True
    if input_idle is None:
        return speech_quiet >= AWAY_AFTER_NO_INPUT
    return speech_quiet >= AWAY_AFTER and input_idle >= AWAY_AFTER


def is_back(awake: bool, speech_quiet: float, input_idle: float | None) -> bool:
    """Someone is here again: awake, and they spoke or touched the computer just now."""
    if not awake:
        return False
    if speech_quiet < BACK_INPUT:
        return True
    return input_idle is not None and input_idle < BACK_INPUT


# ── the digest ────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    try:
        items = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return []
    except Exception:
        return []
    cutoff = time.time() - KEEP_FOR
    return [i for i in items if isinstance(i, dict) and i.get("text") and float(i.get("at", 0)) >= cutoff]


def _save(items: list[dict]) -> None:
    try:
        DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = DIGEST_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(DIGEST_PATH)
    except Exception as exc:
        print(f"[Away] could not save the digest: {exc}")


def add(text: str, kind: str = "note", key: str = "") -> None:
    """Keep one thing to tell the user when they are back. Same key: the newer one replaces the older."""
    text = (text or "").strip()
    if not text:
        return
    with _lock:
        items = _load()
        if key:
            items = [i for i in items if i.get("key") != key]
        items.append({"at": time.time(), "kind": kind, "key": key, "text": text[:1500]})
        _save(items[-MAX_ITEMS:])


def pending() -> list[dict]:
    with _lock:
        return _load()


def take() -> list[dict]:
    """Everything kept, oldest first, and the digest emptied — so it is told exactly once."""
    with _lock:
        items = _load()
        if items:
            _save([])
            _remember_last(items)
        return items


_LAST_PATH = BASE_DIR / "memory" / "away_digest_last.json"


def _remember_last(items: list[dict]) -> None:
    try:
        _LAST_PATH.write_text(json.dumps({"told_at": time.time(), "items": items},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def last_told() -> dict:
    """The digest told most recently, for 'what did I miss again?'."""
    try:
        data = json.loads(_LAST_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _ago(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    h, m = divmod(m, 60)
    return f"{h} h {m} min ago" if m else f"{h} h ago"


def describe(items: list[dict], now: float | None = None) -> str:
    """The items as lines the model can turn into one short report."""
    now = now or time.time()
    return "\n".join(f"- ({_ago(now - float(i.get('at', now)))}, {i.get('kind', 'note')}) {i['text']}"
                     for i in items)


def welcome_instruction(items: list[dict], away_for: float = 0.0) -> str:
    """What the session is told when the user is back."""
    gone = f" They were away for about {_ago(away_for).replace(' ago', '')}." if away_for >= 60 else ""
    return ("[AWAY_DIGEST] The user is back." + gone + " These came up while they were away and "
            "have not been told yet:\n" + describe(items) + "\n"
            "Welcome them back the way J.A.R.V.I.S. does in the films and tell them what happened, "
            "most important first, in at most three short sentences: merge related items, drop "
            "progress notes a later item makes stale, give the outcome rather than the steps. "
            "If they have just asked something, answer that first. Offer details only if there is "
            "more worth hearing. If an item was one step of a longer request, ask whether to carry on with the "
            "rest. Do not call any tool for these, and do not repeat them later.")


def ready_to_tell(awake: bool, speaking: bool, busy: bool, speech_quiet: float,
                  input_idle: float | None) -> bool:
    """A good moment for the welcome: awake, not mid-sentence or mid-job, the user's own words
    answered (a few quiet seconds), and they are here — they engaged just now."""
    if not awake or speaking or busy or speech_quiet < 6:
        return False
    if speech_quiet < 600:
        return True
    return input_idle is not None and input_idle < 60


# ── welcome home ──────────────────────────────────────────────────────────────
# "Welcome home, sir." After a long absence J.A.R.V.I.S. greets the user even when
# nothing happened — but only when they came back to the desk on their own (not
# when they woke JARVIS with a command: that command comes first), and only when
# the user has not turned it off.

WELCOME_AFTER = 2 * 3600        # away at least this long (after the 15-minute threshold)


def welcome_enabled() -> bool:
    try:
        from memory.config_manager import get_plugin_config
        return bool((get_plugin_config("away") or {}).get("welcome", True))
    except Exception:
        return True


def should_welcome(away_for: float, woke_by_command: bool) -> bool:
    return away_for >= WELCOME_AFTER and not woke_by_command and welcome_enabled()


def greeting_instruction(away_for: float, hour: int) -> str:
    """A welcome back with nothing to report."""
    part = ("morning" if 5 <= hour < 12 else "afternoon" if hour < 18 else "evening" if hour < 23 else "night")
    return ("[WELCOME_BACK] The user has just come back to the computer after about "
            f"{_ago(away_for).replace(' ago', '')} away; it is {part} now. Nothing happened while they were "
            "away. Greet them the way J.A.R.V.I.S. greets Tony coming home — one short, warm sentence "
            "('Tekrar hoş geldiniz, efendim.' / 'İyi akşamlar, efendim; her şey yolunda.'), adding at most "
            "that all is in order. Do not ask a question, do not list anything, do not call any tool.")


# ── word to the phone ─────────────────────────────────────────────────────────
# J.A.R.V.I.S. reaches Tony wherever he is. When the user has left the desk (not
# merely JARVIS asleep with them sitting there) and a job they started finishes,
# or the computer raises an alarm, their phone gets a notification too — the
# same Web Push the phone app already uses for reminders. Reminders are not
# repeated here: they push on their own.

PUSH_GAP = 10 * 60
_last_push = {"at": float("-inf")}


def push_enabled() -> bool:
    try:
        from memory.config_manager import get_plugin_config
        return bool((get_plugin_config("away") or {}).get("push", True))
    except Exception:
        return True


def phone_note(instruction: str, kind: str) -> tuple[str, str] | None:
    """(title, body) for the phone, or None when this is not worth a notification."""
    import re
    text = (instruction or "").strip()
    if kind == "result":
        m = re.search(r"The '([^']+)' tool", text)
        tool = (m.group(1) if m else "").replace("_", " ")
        r = re.search(r"Result:\s*(.*)", text, re.S)
        body = (r.group(1) if r else text).strip()
        return (f"JARVIS — {tool} tamamlandı" if tool else "JARVIS — iş tamamlandı"), body[:300]
    if kind == "system":
        body = re.sub(r"^\[[A-Z_]+\]\s*", "", text)
        return "JARVIS — sistem uyarısı", body[:300]
    return None


def should_push(kind: str, input_idle: float | None, now: float | None = None) -> bool:
    """Truly away from the desk (input idle), a kind worth it, not too soon after the last one."""
    now = time.monotonic() if now is None else now
    if kind not in ("result", "system") or not push_enabled():
        return False
    if input_idle is None or input_idle < AWAY_AFTER:
        return False
    return now - _last_push["at"] >= PUSH_GAP


def push_to_phones(title: str, body: str) -> int:
    """Send to every phone/tablet that turned notifications on (not this computer); how many."""
    sent = 0
    try:
        from core import sync_hub
        me = sync_hub.device_id()
        for dev in list((sync_hub._state.get("push_subs") or {})):
            if dev != me and sync_hub.push_to(dev, title, body, tag="away"):
                sent += 1
    except Exception as exc:
        print(f"[Away] push: {exc}")
    if sent:
        _last_push["at"] = time.monotonic()
    return sent


# ── good morning ──────────────────────────────────────────────────────────────
# The opening briefing runs when JARVIS starts. A computer left on overnight
# never starts again, so the user would never get one: the first return of a new
# morning stands in for the start — "Günaydın, efendim" and the briefing, with
# whatever came up overnight folded in.

BRIEFED_PATH = BASE_DIR / "memory" / "last_briefing.json"
MORNING_FROM, MORNING_TO = 5, 13
MORNING_AWAY = 3 * 3600


def mark_briefed(today: str) -> None:
    try:
        BRIEFED_PATH.parent.mkdir(parents=True, exist_ok=True)
        BRIEFED_PATH.write_text(json.dumps({"date": today}), encoding="utf-8")
    except Exception:
        pass


def last_briefed() -> str:
    try:
        return str(json.loads(BRIEFED_PATH.read_text(encoding="utf-8")).get("date") or "")
    except Exception:
        return ""


def morning_due(today: str, hour: int, away_for: float, woke_by_command: bool,
                briefing_enabled: bool, last: str | None = None) -> bool:
    """The first return of a morning after a long night away, no briefing yet today."""
    last = last_briefed() if last is None else last
    return (briefing_enabled and not woke_by_command and MORNING_FROM <= hour < MORNING_TO
            and away_for >= MORNING_AWAY and last != today)


def overnight_extra(items: list[dict]) -> str:
    """What the briefing should fold in from the night."""
    if not items:
        return ""
    return ("Also tell them, briefly and most important first, what came up while they were away "
            "(merge related items, outcomes not steps):\n" + describe(items))
