"""Stop what JARVIS is doing: "dur", "iptal et", "vazgeçtim", "Blender'daki işi durdur".

Reaches every kind of long job: the ones registered in core.jobs (Blender …) and
the background task engine (research, drafting).
"""
from __future__ import annotations

PLUGIN = {
    "name": "job_control",
    "description": (
        "Stop or list JARVIS's long-running jobs (Blender builds/renders, background research and drafting tasks). "
        "Use when the user says stop / cancel / give up on a job that is running: 'dur', 'iptal et', "
        "'vazgeçtim', 'Blender'daki işi durdur', 'araştırmayı iptal et'. action=list shows what is running."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "cancel | list"},
        "which": {"type": "STRING", "description": "Optional: words naming the job ('Blender', 'araştırma'); empty = all"},
    }, "required": ["action"]},
}


def _tasks():
    try:
        from core.tasks import desktop
        eng = desktop.engine()
        if eng is None:
            return None, []
        from core.tasks.engine import ACTIVE
        return eng, [t for t in eng.list(50) if t.get("status") in ACTIVE]
    except Exception:
        return None, []


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import jobs
        p = parameters or {}
        action = str(p.get("action") or "list").lower().strip()
        which = str(p.get("which") or "").strip()
        eng, tasks = _tasks()
        try:
            from plugins import blender_studio
            waiting = [f"- Sırada (Blender): {q}" for q in blender_studio.queued()]
        except Exception:
            waiting = []
        if action == "list":
            lines = jobs.describe() + waiting + [f"- Arka plan görevi '{t.get('title')}': {t.get('status')}" for t in tasks]
            return "Şu an süren işler:\n" + "\n".join(lines) if lines else "Şu an süren bir iş yok."
        stopped = jobs.cancel(which)
        if waiting and (not which or "blender" in which.lower() or "sıra" in which.lower()):
            from plugins import blender_studio
            blender_studio.stop_all() if not stopped else None      # nothing running: just clear the line
            stopped.append(f"sıradaki {len(waiting)} Blender işi")
        w = which.lower()
        for t in tasks:
            if not w or w in str(t.get("title", "")).lower() or w in ("görev", "araştırma", "task", "research", "arka plan"):
                try:
                    if eng.cancel(t["id"]):
                        stopped.append(f"Arka plan görevi '{t.get('title')}'")
                except Exception:
                    pass
        if not stopped:
            return "Durduracak süren bir iş bulamadım." + (f" ('{which}' ile eşleşen yok.)" if which else "")
        return "Durdurdum: " + "; ".join(stopped)
    except Exception as exc:
        return f"İşi durduramadım: {exc}"
