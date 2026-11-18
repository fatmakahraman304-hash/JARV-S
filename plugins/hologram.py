"""Iron Man 2'deki gibi: "Jarvis, bunu dijital olarak modelle" — JARVIS'in kendi
penceresinde hologram masası açılır (gui/holo_panel.py): kamera nesneyi tarar,
gerçeğe benzeyen bir 3B model çıkar (GPU'da stüdyo görüntüsü ya da turuncu
hologram), eller kameraya gösterilerek döndürülür, büyütülür, parçalara ayrılır.
Sesle de değiştirilir: "kanatları kırmızı yap", "hologram görünümüne geç"."""
from __future__ import annotations

PLUGIN = {
    "name": "hologram",
    "description": (
        "Iron Man tarzı hologram masası, JARVIS'in penceresinde: kameraya gösterilen nesneyi gerçeğe benzeyen 3B "
        "modele çevirir; kullanıcı elleriyle (kameraya göstererek) ya da fareyle döndürür, büyütür, parçalara ayırır. "
        "action: scan ('bunu dijital olarak modelle', 'kameradakini tara') | make (request: 'bana bir Iron Man kaskı "
        "modelle') | edit (request: açık modeli değiştir — 'kanatları kırmızı yap', 'tekerlek ekle', 'daha büyük yap') | "
        "explode ('parçalarına ayır') | assemble | reset | real (gerçekçi görünüm) | holo (hologram görünümü) | "
        "hands (el kontrolünü aç/kapat; on) | save | stl (3D yazıcı dosyası) | throw (modeli at) | open | close. "
        "Hologram açıkken model hakkındaki değişiklik isteklerini edit ile gönder."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "scan | make | edit | explode | assemble | reset | real | holo | hands | save | stl | throw | open | close"},
        "request": {"type": "STRING", "description": "make / edit için ne istendiği"},
        "on": {"type": "BOOLEAN", "description": "hands için: aç (true) / kapat (false)"},
        "hands": {"type": "BOOLEAN", "description": "açarken el kontrolü de başlasın mı"},
    }, "required": ["action"]},
}

REPLIES = {
    "scan": "Hologram masasını açtım. Nesneyi kameraya göster; üçten geriye sayınca biraz çevir, gerisini ben hallederim.",
    "make": "Hologram masasında tasarlıyorum, birkaç saniye.",
    "edit": "Modeli güncelliyorum.",
    "explode": "Parçalarına ayırıyorum.",
    "assemble": "Birleştirdim.",
    "reset": "Görünümü sıfırladım.",
    "real": "Gerçekçi görünüm.",
    "holo": "Hologram görünümü.",
    "save": "Model kaydedildi.",
    "stl": "STL dosyasını Belgeler'deki JARVIS Modeller klasörüne kaydediyorum.",
    "throw": "Attım; istersen geri getiririm.",
    "open": "Hologram masası açık.",
    "close": "Hologram masasını kapattım.",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        action = str(p.get("action") or "scan").lower().strip()
        request = str(p.get("request") or "").strip()
        if action in ("make", "edit") and not request:
            return "Ne modellememi ya da neyi değiştirmemi istediğini söyler misin?"
        if player is None or not hasattr(player, "show_hologram"):
            return "Hologram masası JARVIS'in penceresinde açılır; pencere şu an yok."
        cmd = {"action": action, "request": request}
        if action == "hands":
            cmd["on"] = p.get("on") is not False
        if p.get("hands") or action == "scan":
            cmd["hands"] = bool(p.get("hands", action == "scan"))
        player.show_hologram(cmd)
        if action == "hands":
            return ("El kontrolü açık: çimdikleyip sürükleyerek döndür, iki elle yakınlaştır, avucunu açık tutarak parçala."
                    if cmd["on"] else "El kontrolü kapandı.")
        return REPLIES.get(action, "Tamam.")
    except Exception as exc:
        return f"Hologram açılamadı: {exc}"
