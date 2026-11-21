"""
Mayk's work journal — what it actually did, day by day, kept on disk.

The Control Centre's activity log lives only for one run. This keeps the gist
of every finished tool call (which tool, whether it worked, a short line) in one
small file per day, so "bugün neler yaptın?" and "bu hafta neler yaptık?" are
answered from the record, not from memory. Old days are pruned after KEEP_DAYS.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "memory" / "journal"
KEEP_DAYS = 60
SKIP = {"save_memory", "recall_memory", "work_status", "while_away", "self_check", "capabilities", "status_report",
        "day_report"}          # looking things up about itself is not work done
_lock = threading.Lock()
_pruned = {"day": ""}


def _file(day: date) -> Path:
    return DIR / f"{day.isoformat()}.jsonl"


def record(tool: str, ok: str, text: str, when: float | None = None) -> None:
    """One finished tool call. ok: 'ok' | 'warn' | 'fail'. Never raises."""
    if not tool or tool in SKIP:
        return
    when = time.time() if when is None else when
    line = json.dumps({"t": round(when), "tool": tool, "ok": ok, "text": str(text)[:120]}, ensure_ascii=False)
    try:
        with _lock:
            DIR.mkdir(parents=True, exist_ok=True)
            day = datetime.fromtimestamp(when).date()
            with open(_file(day), "a", encoding="utf-8") as f:
                f.write(line + "\n")
            if _pruned["day"] != day.isoformat():
                _pruned["day"] = day.isoformat()
                _prune(day)
    except Exception:
        pass


def _prune(today: date) -> None:
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    for p in DIR.glob("*.jsonl"):
        if p.stem < cutoff:
            try:
                p.unlink()
            except OSError:
                pass


def entries(start: date, end: date) -> list[dict]:
    out = []
    day = start
    while day <= end:
        try:
            with open(_file(day), encoding="utf-8") as f:
                for raw in f:
                    try:
                        out.append(json.loads(raw))
                    except ValueError:
                        continue
        except OSError:
            pass
        day += timedelta(days=1)
    return out


NAMES = {"blender_studio": "Blender işi", "web_search": "web araması", "send_message": "mesaj",
         "open_app": "uygulama açma", "youtube_video": "YouTube", "reminder": "hatırlatıcı",
         "smart_home": "akıllı ev komutu", "dev_agent": "kod işi", "file_controller": "dosya işi",
         "browser_control": "tarayıcı işi", "generate_image": "resim", "computer_settings": "bilgisayar ayarı",
         "screen_process": "ekrana bakma", "weather_report": "hava durumu"}


def summary(start: date, end: date) -> str:
    """A short account of the period for the model to turn into a sentence or two."""
    rows = entries(start, end)
    if not rows:
        return "No work recorded for this period."
    done = [r for r in rows if r.get("ok") != "fail"]
    failed = [r for r in rows if r.get("ok") == "fail"]
    by_tool = Counter(r["tool"] for r in done)
    top = ", ".join(f"{n}× {NAMES.get(t, t.replace('_', ' '))}" for t, n in by_tool.most_common(6))
    days = len({datetime.fromtimestamp(r["t"]).date() for r in rows})
    lines = [f"{len(done)} tasks done over {days} day(s), {len(failed)} failed.", f"Most: {top}."]
    notable = [r["text"] for r in done if r["tool"] in ("blender_studio", "dev_agent", "generate_image",
                                                         "send_message", "smart_home")][-5:]
    if notable:
        lines.append("Notable: " + " | ".join(notable))
    if failed:
        lines.append("Failed: " + " | ".join(r["text"] for r in failed[-3:]))
    return "\n".join(lines)
