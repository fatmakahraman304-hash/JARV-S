"""Odak modu (pomodoro): N dakika çalış, M dakika mola — bitince AETHER söyler,
telefon ve saat de bilir (ortak hatırlatıcı)."""
from __future__ import annotations

import time

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "focus_mode",
    "description": (
        "Odak modu / pomodoro: 'odak modunu aç', '25 dakika çalışacağım', '50 dakika odaklan 10 dakika mola', "
        "'odak ne durumda', 'odağı bitir'. action: start | status | stop. minutes: çalışma (varsayılan 25), "
        "break_minutes: mola (varsayılan 5), cycles: kaç tur (varsayılan 1), task: ne üzerinde çalışılıyor. "
        "Çalışma ve mola bitince sesli söylenir; telefon ve saat de haber verir."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "start | status | stop"},
        "minutes": {"type": "NUMBER"}, "break_minutes": {"type": "NUMBER"},
        "cycles": {"type": "NUMBER"}, "task": {"type": "STRING"},
    }, "required": ["action"]},
}

SOURCE = "focus_mode"
STATE = "focus.json"


def plan(minutes: float, brk: float, cycles: int, start: float, task: str = "") -> list[dict]:
    """Phase ends: [{"at": ts, "text": what to say}]."""
    minutes = max(1, min(240, float(minutes or 25)))
    brk = max(0, min(60, float(brk if brk is not None else 5)))
    cycles = max(1, min(8, int(cycles or 1)))
    out, t = [], start
    what = f" ({task})" if task else ""
    for c in range(1, cycles + 1):
        t += minutes * 60
        last = c == cycles
        if last:
            out.append({"at": t, "text": f"Odak bitti{what}. {cycles} tur tamamlandı, tebrikler. Biraz dinlen."})
        else:
            out.append({"at": t, "text": f"Odak turu {c} bitti{what}. {kit.fmt_minutes(brk)} mola."})
            t += brk * 60
            out.append({"at": t, "text": f"Mola bitti, odak turu {c + 1} başlıyor."})
    return out


def status_text(st: dict, now: float) -> str:
    phases = [p for p in st.get("phases", []) if p["at"] > now]
    if not phases:
        return "Odak modu kapalı."
    nxt = phases[0]
    left = (nxt["at"] - now) / 60
    return f"Odak modu açık{' (' + st['task'] + ')' if st.get('task') else ''}: {kit.fmt_minutes(left)} sonra — {nxt['text'].split('.')[0].lower()}."


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        act = str(p.get("action") or "start").lower()
        st, now = kit.load(STATE), time.time()
        if act == "status":
            return status_text(st, now)
        if act == "stop":
            kit.cancel(SOURCE, st.get("shared", []))
            done = st.get("phases") and st["phases"][-1]["at"] > now
            kit.save(STATE, {"log": st.get("log", [])})
            return "Odak modu kapatıldı." if done else "Zaten açık bir odak yoktu."
        kit.cancel(SOURCE, st.get("shared", []))
        task = str(p.get("task") or "").strip()[:80]
        phases = plan(p.get("minutes") or 25, p.get("break_minutes"), p.get("cycles") or 1, now, task)
        shared = [x for x in (kit.say_at(ph["at"], ph["text"], SOURCE) for ph in phases) if x]
        log = (st.get("log") or [])[-200:] + [{"start": now, "end": phases[-1]["at"], "task": task}]
        kit.save(STATE, {"phases": phases, "shared": shared, "task": task, "log": log})
        kit.log(player, f"Odak modu: {len(phases)} aşama, bitiş {time.strftime('%H:%M', time.localtime(phases[-1]['at']))}")
        mins = round((phases[0]["at"] - now) / 60)
        return (f"Odak modu başladı: {mins} dakika{' — ' + task if task else ''}. Bitince söyleyeceğim"
                + ("; telefonun ve saatin de bilecek." if shared else "."))
    except Exception as exc:
        return f"Odak modu açılamadı: {exc}"
