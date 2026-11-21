"""
Keeping watch over the user, the way Mayk does over Tony.

In the films Mayk notices when Tony has been at it all night and says so
— once, dryly, and then lets him get on with it. This module is that, grounded
in what actually happened rather than guessed: it measures the current work
stretch from real activity (mouse/keyboard input, or speech) and notices two
things only:

  * a long stretch without a real break (STRETCH_HOURS, default 3 h; a break is
    BREAK_MIN minutes with no input and no speech);
  * working in the small hours (01:00–05:00), once a night.

It says each at most once (per stretch / per night), never more often than
COOLDOWN, and not at all when the user turned it off ("bana mola hatırlatma"
→ care_notes off). It never decides for the user: a sentence, then nothing.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

ACTIVE_WITHIN = 5 * 60       # input or speech this recent: working now
BREAK_MIN = 20               # minutes of nothing that count as a real break
STRETCH_HOURS = 3.0
COOLDOWN = 90 * 60
LATE_FROM, LATE_TO = 1, 5    # the small hours
LATE_MIN_STRETCH = 30 * 60   # a moment at 2 a.m. is not "working through the night"


def settings() -> dict:
    """The user's choices: on/off, how long a stretch, whether the small hours count."""
    out = {"enabled": True, "stretch_hours": STRETCH_HOURS, "late_night": True}
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("care") or {}
        out.update({k: cfg[k] for k in out if k in cfg})
        out["stretch_hours"] = min(12.0, max(1.0, float(out["stretch_hours"])))
    except Exception:
        pass
    return out


def _night_of(now: datetime) -> str:
    """The night a small-hours moment belongs to: 02:00 on the 5th is the night of the 4th."""
    return (now - timedelta(hours=12)).date().isoformat()


class Vigil:
    def __init__(self):
        self.stretch_start: float | None = None
        self.last_active: float | None = None
        self.stretch_told = False
        self.night_told = ""
        self.last_note = float("-inf")

    def observe(self, now: float, input_idle: float | None, speech_quiet: float) -> bool:
        """Record whether the user is working right now; True if they are."""
        active = speech_quiet < ACTIVE_WITHIN or (input_idle is not None and input_idle < ACTIVE_WITHIN)
        if not active:
            return False
        # Back after a long gap (ticks while away don't count as active): the gap was a break.
        if self.last_active is None or (now - self.last_active) >= BREAK_MIN * 60:
            self.stretch_start = now
            self.stretch_told = False
        self.last_active = now
        return True

    def stretch(self, now: float) -> float:
        return 0.0 if self.stretch_start is None else max(0.0, now - self.stretch_start)

    def due(self, now: float, wall: datetime, input_idle: float | None, speech_quiet: float,
            cfg: dict | None = None) -> dict | None:
        """What is worth saying now, if anything: {"kind", "minutes", "clock"} — not yet marked said."""
        cfg = cfg or settings()
        if not cfg.get("enabled", True):
            return None
        if not self.observe(now, input_idle, speech_quiet):
            return None
        if now - self.last_note < COOLDOWN:
            return None
        length = self.stretch(now)
        if (cfg.get("late_night", True) and LATE_FROM <= wall.hour < LATE_TO
                and self.night_told != _night_of(wall) and length >= LATE_MIN_STRETCH):
            return {"kind": "late", "minutes": int(length // 60), "clock": wall.strftime("%H:%M")}
        if not self.stretch_told and length >= float(cfg.get("stretch_hours", STRETCH_HOURS)) * 3600:
            return {"kind": "stretch", "minutes": int(length // 60), "clock": wall.strftime("%H:%M")}
        return None

    def mark(self, note: dict, now: float, wall: datetime) -> None:
        """It was said: not again this stretch / this night, and nothing else for a while."""
        self.last_note = now
        if note["kind"] == "late":
            self.night_told = _night_of(wall)
            self.stretch_told = True          # one note covers both
        else:
            self.stretch_told = True


def _span(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    if not h:
        return f"{m} min"
    return f"{h} h {m} min" if m else f"{h} h"


def instruction(note: dict) -> str:
    """What the session is told to say."""
    if note["kind"] == "late":
        fact = (f"It is {note['clock']} at night and the user has been working for {_span(note['minutes'])} "
                "without a break.")
        example = "'Saat gecenin ikisi, efendim. Yarın da bir gün; isterseniz kaldığınız yeri not edeyim.'"
    else:
        fact = f"The user has been working for {_span(note['minutes'])} without a real break."
        example = "'Efendim, üç saattir aralıksız çalışıyorsunuz. Kısa bir mola fena olmazdı.'"
    return ("[CARE_NOTE] " + fact + " Say so once, the way Mayk would — one warm, dry sentence "
            f"with the real figure, e.g. {example} No lecture, no health advice, no repeating it. "
            "If they say they will keep going, accept it at once ('Peki, efendim.'). Do not call any tool. "
            "If they ask not to be reminded again, call care_notes(action='off').")
