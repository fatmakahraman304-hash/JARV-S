"""Small, testable rules JARVIS uses to notice that something stopped working and fix it itself."""
from __future__ import annotations

import time

MIC_SILENCE = 3.0      # a live input stream calls back every ~20-60 ms; 3 s of nothing means it is gone


def mic_dead(heartbeat: float, active: bool = True, now: float | None = None) -> bool:
    """The microphone stream stopped: no callback for MIC_SILENCE seconds, or PortAudio says it is inactive."""
    now = time.monotonic() if now is None else now
    return (not active) or (now - heartbeat > MIC_SILENCE)
