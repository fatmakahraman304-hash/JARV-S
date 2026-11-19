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
