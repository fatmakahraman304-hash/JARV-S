"""
core/coding_router.py — which coding model works on the next job.

The best one first, always; when it hits its usage limit (or is signed out),
the next one takes over, and the best one is tried again once its limit has
had time to reset. The order, best first:

    1. Claude Code        (agent in the project folder)
    2. Codex CLI          (agent in the project folder)
    3. the coding API chosen under ENGINE & PROVIDERS → CODING, if it is an API
    4. Gemini's own ladder (always there, the last resort)

Only what is installed and signed in takes part. A model that hit its limit
rests for an hour, one that would not start (signed out, not found) for fifteen
minutes; the rests are kept in config/coding_cooldown.json so a restart does not
send the next job straight back into a wall.

No Qt; nothing here raises.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core import claude_coding, codex_coding

BASE_DIR = Path(__file__).resolve().parent.parent
_COOL_FILE = BASE_DIR / "config" / "coding_cooldown.json"
LIMIT_REST = 60 * 60           # usage limit: try the best again after an hour
DOWN_REST = 15 * 60            # signed out / not installed / would not start
GEMINI = ""                    # the Gemini ladder (never rests)

AGENTS = (claude_coding.PROVIDER_ID, codex_coding.PROVIDER_ID)
NAMES = {claude_coding.PROVIDER_ID: "Claude Code", codex_coding.PROVIDER_ID: "Codex", GEMINI: "Gemini"}

_lock = threading.Lock()


def name(provider: str) -> str:
    return NAMES.get(provider) or provider.partition("@")[2] or provider or "Gemini"


def _load() -> dict:
    try:
        data = json.loads(_COOL_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        _COOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOL_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def resting(provider: str, now: float | None = None) -> float:
    """Seconds left of this provider's rest, or 0."""
    if provider == GEMINI:
        return 0.0
    now = time.time() if now is None else now
    with _lock:
        until = float((_load().get(provider) or {}).get("until", 0))
    return max(0.0, until - now)


def is_limit(err) -> bool:
    s = str(err).casefold()
    return any(w in s for w in ("kullanım sınır", "usage limit", "rate limit", "429", "quota",
                                "resource_exhausted", "too many requests", "limit reached",
                                "limitine", "sınırına ulaş"))


def is_unavailable(err) -> bool:
    s = str(err).casefold()
    return any(w in s for w in ("oturum", "not logged in", "login", "401", "bulunamadı",
                                "başlatılamadı", "not found", "unauthorized", "sürümü eski",
                                "desteklemiyor", "zaman aşımı", "süre sınırını", "timeout",
                                "yanıt vermedi", "every model on the ladder failed"))


def should_switch(err) -> bool:
    """Is this a failure another model can get past (as opposed to a bad request)?"""
    return is_limit(err) or is_unavailable(err)


def rest(provider: str, err) -> float:
    """Put a provider to rest after `err`. Returns the seconds it rests."""
    if provider == GEMINI:
        return 0.0
    secs = LIMIT_REST if is_limit(err) else DOWN_REST
    with _lock:
        data = _load()
        data[provider] = {"until": time.time() + secs, "why": str(err)[:200]}
        _save(data)
    return secs


def ladder(chosen: str = "", installed=None) -> list[str]:
    """Every provider to try, best first, minus the ones resting. Never empty:
    Gemini is always last. `chosen` is the API picked in the CODING setting;
    `installed(provider)` says whether an agent CLI is present."""
    if installed is None:
        from core import agent_coding
        installed = agent_coding.available
    out = [p for p in AGENTS if installed(p)]
    if chosen and chosen not in AGENTS and chosen not in ("auto",):
        out.append(chosen)
    out = [p for p in out if not resting(p)]
    return out + [GEMINI]


def status_line(chosen: str = "") -> str:
    """For the job panel: the order this job will try."""
    parts = []
    for p in list(AGENTS) + ([chosen] if chosen and chosen not in AGENTS else []):
        left = resting(p)
        if left:
            parts.append(f"{name(p)} (limitte, {int(left // 60) + 1} dk)")
    return ", ".join(parts)
