"""
How loud FRIDAY's own voice is — and softer at night.

FRIDAY does not boom through the house at 2 a.m. The voice's loudness is
a gain applied to FRIDAY's speech only (the computer's volume and every other
program stay as they are): the user's chosen level, and between NIGHT_FROM and
NIGHT_TO a softer one, unless they turned the night setting off.
"""
from __future__ import annotations

from datetime import datetime

DEFAULTS = {"level": 100, "night": True, "night_level": 55, "night_from": 23, "night_to": 7}


def settings() -> dict:
    out = dict(DEFAULTS)
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("voice_level") or {}
        out.update({k: cfg[k] for k in DEFAULTS if k in cfg})
    except Exception:
        pass
    out["level"] = min(150, max(10, int(out["level"])))
    out["night_level"] = min(150, max(10, int(out["night_level"])))
    out["night_from"] = int(out["night_from"]) % 24
    out["night_to"] = int(out["night_to"]) % 24
    return out


def is_night(hour: int, start: int, end: int) -> bool:
    if start == end:
        return False
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


def gain(now: datetime | None = None, cfg: dict | None = None) -> float:
    """The factor FRIDAY's speech is multiplied by now (1.0 = as generated)."""
    cfg = cfg or settings()
    hour = (now or datetime.now()).hour
    level = cfg["level"]
    if cfg["night"] and is_night(hour, cfg["night_from"], cfg["night_to"]):
        level = min(level, cfg["night_level"])
    return level / 100.0


def apply(pcm16: bytes, factor: float) -> bytes:
    """Scale 16-bit PCM by `factor`, clipping instead of wrapping."""
    if abs(factor - 1.0) < 0.01 or not pcm16:
        return pcm16
    import numpy as np
    x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) * float(factor)
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()
