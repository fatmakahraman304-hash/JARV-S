"""
Iron Man tarzı durum raporu: bütün cihazlar (açık mı, pil, işlemci, bellek,
disk), sıradaki ortak hatırlatıcılar, yapılacaklar listesi ve projeler.
Web uygulamasındaki `status_report` aracının bilgisayar tarafı.
"""

PLUGIN = {
    "name": "status_report",
    "description": (
        "Durum raporu: bütün cihazlar (bilgisayar, telefon, tablet, TV — açık/kapalı, pil, işlemci, "
        "bellek, disk), sıradaki hatırlatıcılar, yapılacaklar ve projeler. 'durum raporu', "
        "'sistemler nasıl', 'telefonumun şarjı kaç', 'cihazlarım ne durumda'."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}


def _own_state() -> str:
    """JARVIS's own side of the report: what it is doing, whether it is keeping quiet, what waits to be told."""
    lines = []
    try:
        from core import jobs
        running = jobs.describe()
        lines.append("- çalışan işler: " + (", ".join(running) if running else "yok"))
    except Exception:
        pass
    try:
        from core import quiet
        if quiet.is_on():
            lines.append("- " + quiet.describe())
    except Exception:
        pass
    try:
        from core import away
        n = len(away.pending())
        if n:
            lines.append(f"- söylenmeyi bekleyen {n} gelişme var (while_away ile anlatılabilir)")
    except Exception:
        pass
    try:
        from core import sentinel
        last = sentinel.recent(limit=3)
        if last:
            lines.append("- son fark edilenler: " + "; ".join(i["text"] for i in last))
    except Exception:
        pass
    return "JARVIS:\n" + ("\n".join(lines) or "- her şey sakin")


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        parts = [sync_hub.status_report()]
        try:
            from plugins import todo_list
            parts.append("YAPILACAKLAR:\n" + todo_list.run({"action": "list"}))
        except Exception:
            pass
        try:
            projects = sync_hub.projects_summary(limit=5)
            unfinished = [p for p in projects if p.get("status") not in ("bitti", "iptal")]
            parts.append("PROJELER:\n" + ("\n".join(
                f"- #{p['id']} {p['title']}: {p['status']}" + (f", aşama {p['stage']}/{p['stages']}" if p.get("stages") else "")
                for p in unfinished) or "- yarım proje yok"))
        except Exception:
            pass
        parts.append(_own_state())
        parts.append("(Kullanıcıya Iron Man'deki JARVIS gibi kısa, akıcı bir rapor olarak özetle; "
                     "düşük pil ya da dolu disk varsa uyar.)")
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Durum raporu hazırlanamadı: {exc}"
