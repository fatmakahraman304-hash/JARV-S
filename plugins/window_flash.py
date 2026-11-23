"""Explain briefly appearing Windows/MAYK popups from local diagnostics."""
from __future__ import annotations

PLUGIN = {
    "name": "window_flash",
    "description": (
        "MAYK ekranında bir pencere aniden açılıp kaybolduğunda hangi "
        "program veya MAYK paneli olduğunu yerel pencere izinden bul. "
        "Kullanıcı 'ne açılıp kapanıyor', 'anlık pencereyi bul', "
        "'son açılan pencere ne' derse bunu kullan. Yalnızca yerel "
        "tanılama geçmişi; ekran görüntüsü ya da özel içerik toplamaz."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "limit": {"type": "INTEGER", "description": "Son kaç olay? (1–20)"},
        },
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core.window_flash import recent
        n = max(1, min(20, int((parameters or {}).get("limit") or 6)))
        items = recent(n)
        if not items:
            return ("Henüz kısa süreli açılıp kapanan bir pencere yakalanmadı. "
                    "Windows üzerinde MAYK'ı açık tut; olay yakalanırsa "
                    "son anlık pencereleri bu araçla gösterebilirim.")
        return ("Windows/MAYK anlık pencere kayıtları (eski → yeni):\n" +
                "\n".join(items) +
                "\nNot: Harici bir Windows konsolu tespit edilmesi, onun "
                "MAYK tarafından açıldığını tek başına kanıtlamaz.")
    except (OSError, ValueError, TypeError) as exc:
        return "Pencere tanılama kaydı okunamadı: " + type(exc).__name__
