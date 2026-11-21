"""
A heads-up before what is coming — "Efendim, toplantınıza on beş dakika var."

Reminders fire at their time. For an appointment that is too late: you need the
quarter of an hour before it. For reminders that read like an appointment (a
meeting, a call, a flight, the doctor …) MAYK gives one heads-up LEAD minutes
before — once, and only if the reminder was set well before that.
"""
from __future__ import annotations

import re
import time

LEAD_MIN = 15
WORDS = ("toplanti", "randevu", "gorusme", "ucus", "ucak", "tren", "otobus", "mac", "sinav", "doktor", "ders",
         "mulakat", "sunum", "konser", "sinema", "meeting", "call", "flight", "appointment", "interview", "exam",
         "class", "zoom", "teams")


def _norm(text: str) -> str:
    t = str(text or "").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("i̇", "i")):
        t = t.replace(a, b)
    return t


def looks_like_appointment(text: str) -> bool:
    words = re.findall(r"[a-z0-9]+", _norm(text))
    return any(w.startswith(k) for w in words for k in WORDS)


def due_soon(reminders: list[dict], told: set, now: float | None = None, lead_min: int = LEAD_MIN) -> list[dict]:
    """Reminders (sync_hub shape: id, text, due in ms) to give a heads-up for now."""
    now = time.time() if now is None else now
    out = []
    for r in reminders or []:
        if r.get("cancelled") or r.get("id") in told:
            continue
        due = float(r.get("due") or 0) / 1000.0
        left = due - now
        if 0 < left <= lead_min * 60 and left > (lead_min - 5) * 60 and looks_like_appointment(r.get("text", "")):
            out.append(r)
    return out


def instruction(r: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    mins = max(1, round((float(r["due"]) / 1000.0 - now) / 60))
    return (f"[HEADS_UP] In {mins} minutes: {r.get('text', '')}. Give the user a heads-up the way MAYK "
            f"would — one sentence ('Efendim, toplantınıza {mins} dakika var.'), offering the obvious help at "
            "most once (opening the meeting link, the route). Do not call any tool unless they ask.")


def from_routines(routines: list[dict]) -> list[dict]:
    """Spoken one-shot reminders from the routine engine, in the shared-reminder shape."""
    out = []
    for r in routines or []:
        if not r.get("enabled", True) or r.get("kind") != "say":
            continue
        trig = r.get("trigger") or {}
        if trig.get("type") != "time" or (trig.get("rule") or {}).get("type") != "once":
            continue
        due = float(r.get("next_ts") or (trig.get("rule") or {}).get("at_ts") or 0)
        if due:
            out.append({"id": "rt:" + str(r.get("id")), "text": r.get("text") or r.get("name", ""), "due": due * 1000})
    return out


def merge(shared: list[dict], local: list[dict]) -> list[dict]:
    """Both lists, the same appointment once (same text, same minute)."""
    seen, out = set(), []
    for r in list(shared or []) + list(local or []):
        key = (_norm(r.get("text", "")).strip(), int(float(r.get("due") or 0) // 60000))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
