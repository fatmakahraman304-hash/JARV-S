"""What FRIDAY has been doing, and what is still running.

The answer to "bitti mi?", "ne yaptın?", "hâlâ çalışıyor mu?", "Blender'daki iş ne
durumda?" — read from the real records: the activity log every tool call goes
into, the background task engine's task files, and the long jobs that keep
their own state (Blender). Read-only: it never starts or repeats anything.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

PLUGIN = {
    "name": "work_status",
    "description": (
        "What FRIDAY did recently and what is still running in the background — the real outcomes (done, failed, "
        "still working). Use it for status questions about your own work: 'bitti mi?', 'ne yaptın?', 'hâlâ çalışıyor "
        "mu?', 'kurulum ne durumda?', 'is it done?'. Never starts or repeats a job."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "about": {"type": "STRING", "description": "Optional: what the user asks about (e.g. 'Blender', 'araştırma')"},
    }},
}

ROOT = Path(__file__).resolve().parent.parent


def _ago(ts: float) -> str:
    s = max(0, int(time.time() - ts))
    return f"{s} sn önce" if s < 60 else f"{s // 60} dk önce" if s < 3600 else f"{s // 3600} sa önce"


def _activity(about: str) -> list[str]:
    try:
        from core import activity
        events = [e for e in activity.recent(60) if e.node not in ("voice", "chat")]
    except Exception:
        return []
    if about:
        a = about.lower()
        hit = [e for e in events if a in e.text.lower() or a in e.node.lower()]
        events = hit or events
    mark = {"ok": "tamam", "warn": "doğrulanamadı", "fail": "BAŞARISIZ", "info": "bilgi"}
    return [f"- {_ago(e.ts)}: {e.text} ({mark.get(e.status, e.status)})" for e in events[-12:]]


def _background() -> list[str]:
    out = []
    try:
        from core import jobs
        out += [line.replace("- ", "- ŞU AN SÜRÜYOR: ", 1) for line in jobs.describe()]
    except Exception:
        pass
    try:
        from plugins import blender_studio
        lock = getattr(blender_studio, "_lock", None)
        running = lock is not None and lock.locked()
        out.append(f"- Blender: {'ŞU AN ÇALIŞIYOR — ' if running else ''}{blender_studio._status}")
        out += [f"- Sırada (Blender): {q}" for q in blender_studio.queued()]
    except Exception:
        pass
    try:
        from core.tasks.desktop import tasks_dir
        tasks = []
        for f in sorted(Path(tasks_dir()).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]:
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(t, dict) and t.get("title"):
                tasks.append(f"- Görev '{t.get('title')}': {t.get('status', '?')}"
                             + (f" ({_ago(f.stat().st_mtime)})" if f.stat().st_mtime else ""))
        out += tasks
    except Exception:
        pass
    try:
        from actions import dev_agent
        # dev_agent.status_text() tek bir gerçek kaynaktan, aktif iş
        # parçacığı ve SQLite günlük kaydından durumu okur.
        out.append(f"- Kodlama ajanı: {dev_agent.status_text()}")
    except Exception:
        pass
    return out


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        about = str((parameters or {}).get("about") or "").strip()
        bg = _background()
        act = _activity(about)
        parts = []
        if bg:
            parts.append("ARKA PLANDAKİ İŞLER:\n" + "\n".join(bg))
        parts.append("SON YAPILANLAR:\n" + ("\n".join(act) if act else "- bu oturumda henüz bir iş yapılmadı"))
        parts.append("(Bu çıktılar gerçek iş kaydıdır. Kullanıcıya çalışan iş ile yalnızca geçmişte kayıtlı "
                     "olan işi ayırarak söyle. Hiçbir işi bu durum sorgusuyla yeniden başlatma.)")
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Durum okunamadı: {exc}"
