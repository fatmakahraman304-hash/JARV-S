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
        "laptop pili, yapılacaklar ve sıradaki hatırlatıcılar, ve FRIDAY'ın o gün gerçekten yaptığı işler; ayrıntısı "
        "ekranda açılır. period=week: 'bu hafta neler yaptık', 'haftalık rapor' — FRIDAY'ın iş günlüğünden son 7 gün."
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
            end = s.get("end") or now
            minutes += max(0.0, min(end, now) - s["start"]) / 60
    return n, max(0.0, minutes)


def build(screen: str, focus: tuple[int, float], battery: str, todos: str, upcoming: list[str]) -> tuple[str, str]:
    """(spoken, full text)."""
    n, m = focus
    focus_line = f"{n} odak turu, toplam {kit.fmt_minutes(m)}." if n else "Bugün odak modu kullanılmadı."
    lines = ["EKRAN SÜRESİ", screen, "", "ODAK", focus_line]
    if battery:
        lines += ["", "PİL", battery]
    lines += ["", "YAPILACAKLAR", todos or "Görev listesi okunamadı."]
    if upcoming:
        lines += ["", "SIRADAKİ HATIRLATICILAR", *upcoming]
    open_todos = [t for t in (todos or "").splitlines() if t.strip() and t.lstrip()[:1].isdigit()]
    spoken = f"{screen} {focus_line}" + (f" Listende {len(open_todos)} iş var." if open_todos else "") + \
             (f" Sıradaki: {upcoming[0]}." if upcoming else "")
    return spoken, "\n".join(lines)


def upcoming_reminders(now: float | None = None) -> tuple[list[str], list[str]]:
    """Read available reminder sources; shared copies of local routines count once."""
    now = time.time() if now is None else now
    entries, issues, shared_ids = [], [], set()
    try:
        from core import sync_hub
        settings = sync_hub.settings()
        if settings.get("github_token") and settings.get("gist_id"):
            issues.append("Ortak hatırlatıcılar yerel eşitleme kaydından okundu; güncellik doğrulanmadı.")
            for item in list(sync_hub._state.get("reminders") or []):
                try:
                    due = float(item.get("due") or 0) / 1000
                    if item.get("cancelled") or due <= now:
                        continue
                    rid = str(item.get("id") or "")
                    if rid:
                        shared_ids.add(rid)
                    entries.append((due, str(item.get("text") or "Hatırlatma")))
                except (TypeError, ValueError, AttributeError):
                    issues.append("Bazı ortak hatırlatıcılar okunamadı.")
        else:
            issues.append("Ortak cihaz hatırlatıcıları bağlı değil.")
    except Exception:
        issues.append("Ortak cihaz hatırlatıcıları okunamadı.")
    try:
        from core.routines import desktop
        engine = desktop.engine()
        if engine is None:
            issues.append("Yerel hatırlatıcı motoru çalışmıyor; liste doğrulanamadı.")
        else:
            for routine in engine.list():
                source = str(routine.get("source") or "")
                if source != "reminder" and not source.startswith("shared:"):
                    continue
                if not routine.get("enabled") or source.startswith("shared:") and source[7:] in shared_ids:
                    continue
                try:
                    due = float(routine.get("next_ts") or 0)
                    if due > now:
                        text = str(routine.get("text") or routine.get("name") or "Hatırlatma")
                        entries.append((due, text.removeprefix("Hatırlatma: ")))
                except (TypeError, ValueError):
                    issues.append("Bazı yerel hatırlatıcılar okunamadı.")
    except Exception:
        issues.append("Yerel hatırlatıcılar okunamadı.")
    entries.sort(key=lambda entry: entry[0])
    return [f"{datetime.fromtimestamp(due):%d.%m.%Y %H:%M} — {text}" for due, text in entries[:4]], list(dict.fromkeys(issues))


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
        return text + "\n(Report it like FRIDAY: two or three sentences, the numbers that matter.)"
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
        try:
            from plugins import todo_list
            todos = todo_list.run({"action": "list"})
        except Exception:
            todos = "Görev listesi okunamadı."
        upcoming, issues = upcoming_reminders()
        spoken, full = build(screen, focus, battery, todos, upcoming)
        if todos.startswith("Yapılacaklar listesine ulaşamadım") or todos == "Görev listesi okunamadı.":
            spoken += " Görev listesine ulaşılamadı."
        if issues:
            full += "\n\nKAYNAK DURUMU\n" + "\n".join(issues)
            spoken += " " + " ".join(issues)
        full += "\n\nTAKVİM\nTakvim etkinlikleri bu raporda kontrol edilmedi."
        spoken += " Takvim etkinlikleri bu raporda kontrol edilmedi."
        work = journal.summary(date.today(), date.today())
        if not work.startswith("No work"):
            full += "\n\nFRIDAY BUGÜN\n" + work
            spoken += " FRIDAY bugün: " + work.splitlines()[0]
        if player:
            try:
                player.show_content("GÜN SONU", full)
            except Exception:
                pass
        return spoken
    except Exception as exc:
        return f"Gün sonu raporu hazırlanamadı: {exc}"
