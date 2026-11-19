"""Gün sonu raporu: bugün bilgisayarda ne kadar zaman geçti, kaç odak turu
yapıldı, yapılacaklar ve yarının hatırlatıcıları — ekranda ve kısaca sesli."""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "day_report",
    "description": (
        "Gün sonu özeti: 'bugün nasıl geçti', 'günümü özetle', 'gün sonu raporu'. Ekran süresi, odak turları, "
        "laptop pili, yapılacaklar ve sıradaki hatırlatıcılar, ve JARVIS'in o gün gerçekten yaptığı işler; ayrıntısı "
        "ekranda açılır. period=week: 'bu hafta neler yaptık', 'haftalık rapor' — JARVIS'in iş günlüğünden son 7 gün."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "period": {"type": "STRING", "description": "today (default) | week"},
    }},
}


def focus_today(log: list, today: date | None = None) -> tuple[int, float]:
    today = today or date.today()
    n, minutes = 0, 0.0
    now = time.time()
    for s in log or []:
        if datetime.fromtimestamp(s.get("start", 0)).date() == today:
            n += 1
            minutes += (min(s.get("end", 0), now) - s["start"]) / 60
    return n, max(0.0, minutes)


def build(screen: str, focus: tuple[int, float], battery: str, todos: str, upcoming: list[str]) -> tuple[str, str]:
    """(spoken, full text)."""
    n, m = focus
    focus_line = f"{n} odak turu, toplam {kit.fmt_minutes(m)}." if n else "Bugün odak modu kullanılmadı."
    lines = ["EKRAN SÜRESİ", screen, "", "ODAK", focus_line]
    if battery:
        lines += ["", "PİL", battery]
    lines += ["", "YAPILACAKLAR", todos or "Liste boş."]
    if upcoming:
        lines += ["", "SIRADAKİ HATIRLATICILAR", *upcoming]
    open_todos = [t for t in (todos or "").splitlines() if t.strip() and not t.lower().startswith(("liste boş", "yapılacaklar listesi boş"))]
    spoken = f"{screen} {focus_line}" + (f" Listende {len(open_todos)} iş var." if open_todos else "") + \
             (f" Sıradaki: {upcoming[0]}." if upcoming else "")
    return spoken, "\n".join(lines)


def run(parameters: dict, player=None, session_memory=None) -> str:
    from core import journal
    if str((parameters or {}).get("period") or "").lower() == "week":
        today = date.today()
        text = journal.summary(today - timedelta(days=6), today)
        if player:
            try:
                player.show_content("HAFTALIK RAPOR", text)
            except Exception:
                pass
        return text + "\n(Report it like J.A.R.V.I.S.: two or three sentences, the numbers that matter.)"
    try:
        from plugins import screen_time, laptop_battery
        screen = screen_time.report_text(kit.load(screen_time.FILE), "today")
        focus = focus_today(kit.load("focus.json").get("log", []))
        battery = ""
        try:
            b = laptop_battery._battery()
            if b is not None:
                battery = laptop_battery.advice(b.percent, bool(b.power_plugged), b.secsleft)
        except Exception:
            pass
        todos = ""
        try:
            from plugins import todo_list
            todos = todo_list.run({"action": "list"})
        except Exception:
            pass
        upcoming = []
        try:
            from core import sync_hub
            now = time.time() * 1000
            rem = [r for r in sync_hub._state.get("reminders") or [] if not r.get("cancelled") and float(r.get("due") or 0) > now]
            upcoming = [f"{datetime.fromtimestamp(float(r['due']) / 1000):%a %H:%M} — {r.get('text', '')}" for r in sorted(rem, key=lambda r: r["due"])[:4]]
        except Exception:
            pass
        spoken, full = build(screen, focus, battery, todos, upcoming)
        work = journal.summary(date.today(), date.today())
        if not work.startswith("No work"):
            full += "\n\nJARVIS BUGÜN\n" + work
            spoken += " JARVIS bugün: " + work.splitlines()[0]
        if player:
            try:
                player.show_content("GÜN SONU", full)
            except Exception:
                pass
        return spoken
    except Exception as exc:
        return f"Gün sonu raporu hazırlanamadı: {exc}"
