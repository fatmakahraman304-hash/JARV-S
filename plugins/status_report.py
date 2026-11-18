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
        parts.append("(Kullanıcıya Iron Man'deki JARVIS gibi kısa, akıcı bir rapor olarak özetle; "
                     "düşük pil ya da dolu disk varsa uyar.)")
        return "\n\n".join(parts)
    except Exception as exc:
        return f"Durum raporu hazırlanamadı: {exc}"
