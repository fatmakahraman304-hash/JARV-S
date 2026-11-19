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
        "detail ('daha fazla ayrıntı ekle', 'detaylandır': açık modele bir ayrıntı turu daha) | explode ('parçalarına ayır') | "
        "assemble | reset | real (gerçekçi görünüm) | holo (hologram görünümü) | cut (kesit görünümü, on) | measure "
        "(ölçüleri göster, on) | isolate (request: parça adı — 'sadece kulpu göster') | show_all | hands (el kontrolü; on) | "
        "save | stl (dışa aktar: STL + OBJ + GLB) | blender (modeli Blender Cycles'ta fotoğraf gerçekliğinde çek) | lib (kayıtlı modeller galerisi) | shot (4K görüntü kaydet) | throw (modeli at) | upright (yan yatmış modeli doğrult) | "
        "video (6 sn dönen video, MP4) | cancel (süren taramayı iptal et) | real_engine (gerçek 3B: yapay zekâ fotoğraftan dokulu gerçek model — varsayılan) | parts_engine (parça modeli) | "
        "hf_token (request: kullanıcının verdiği anahtar — Hugging Face hf_…, Tripo tsk_…, Meshy msy_…; gerçek 3B için) | open | close. "
        "Hologram açıkken model hakkındaki değişiklik isteklerini edit ile gönder."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "scan | make | edit | detail | video | cancel | explode | assemble | reset | real | holo | cut | measure | isolate | show_all | hands | save | stl | shot | throw | upright | real_engine | parts_engine | hf_token | open | close"},
        "request": {"type": "STRING", "description": "make / edit için ne istendiği"},
        "on": {"type": "BOOLEAN", "description": "hands / cut / measure için: aç (true) / kapat (false)"},
        "hands": {"type": "BOOLEAN", "description": "açarken el kontrolü de başlasın mı"},
    }, "required": ["action"]},
}

REPLIES = {
    "scan": "Hologram masasını açtım. Nesneyi kameraya göster; üçten geriye sayınca biraz çevir, gerisini ben hallederim.",
    "make": "Hologram masasında tasarlıyorum, birkaç saniye.",
    "edit": "Modeli güncelliyorum.",
    "detail": "Bir ayrıntı turu daha yapıyorum; yeni parçalar birazdan eklenecek.",
    "cut": "Kesit görünümü.",
    "measure": "Ölçüler ekranda.",
    "isolate": "O parçayı tek başına gösteriyorum.",
    "show_all": "Bütün parçalar görünüyor.",
    "shot": "4K görüntüyü Belgeler'deki JARVIS Modeller klasörüne kaydediyorum.",
    "explode": "Parçalarına ayırıyorum.",
    "assemble": "Birleştirdim.",
    "reset": "Görünümü sıfırladım.",
    "real": "Gerçekçi görünüm.",
    "holo": "Hologram görünümü.",
    "save": "Model kaydedildi.",
    "stl": "Modeli STL, OBJ ve GLB olarak Belgeler'deki JARVIS Modeller klasörüne kaydediyorum.",
    "lib": "Kayıtlı modellerin galerisini açtım.",
    "blender": "Modeli Blender'a gönderdim; Cycles ile stüdyo fotoğrafı çekiyorum, birkaç dakika sürebilir.",
    "throw": "Attım; istersen geri getiririm.",
    "open": "Hologram masası açık.",
    "close": "Hologram masasını kapattım.",
    "upright": "Modeli doğrulttum.",
    "video": "Dönen videoyu çekiyorum; Belgeler'deki JARVIS Modeller klasörüne kaydedeceğim.",
    "cancel": "İptal ettim.",
    "real_engine": "Gerçek 3B motoru: fotoğraftan dokulu gerçek model.",
    "parts_engine": "Parça motoru: Gemini parçalardan kuracak.",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        action = str(p.get("action") or "scan").lower().strip()
        request = str(p.get("request") or "").strip()
        if action in ("make", "edit") and not request:
            return "Ne modellememi ya da neyi değiştirmemi istediğini söyler misin?"
        if action == "hf_token":
            tok = request.strip().strip("'\"")
            if tok.startswith("tsk_") and len(tok) > 20:
                from memory.config_manager import save_holo_key
                save_holo_key("tripo", tok)
                return "Tripo anahtarını kaydettim; gerçek 3B modeller önce Tripo ile yapılacak."
            if tok.startswith("msy_") and len(tok) > 20:
                from memory.config_manager import save_holo_key
                save_holo_key("meshy", tok)
                return "Meshy anahtarını kaydettim; gerçek 3B modeller önce Meshy ile yapılacak."
            if not tok.startswith("hf_") or len(tok) < 20:
                return ("Bu bir anahtara benzemiyor. Ücretsiz Hugging Face anahtarı 'hf_' ile başlar (huggingface.co → Settings → "
                        "Access Tokens); Tripo 'tsk_', Meshy 'msy_' ile başlar.")
            from memory.config_manager import save_hf_token
            save_hf_token(tok)
            return "Hugging Face anahtarını kaydettim; gerçek 3B modellerde günlük kota artık daha büyük."
        if action in ("make", "edit") and request:
            from core import intent                 # "araba yapabilir mi?" is a question, not an order
            if not intent.should_act(request):
                return intent.not_a_command(request)
        if player is None or not hasattr(player, "show_hologram"):
            return "Hologram masası JARVIS'in penceresinde açılır; pencere şu an yok."
        cmd = {"action": action, "request": request}
        if action in ("hands", "cut", "measure"):
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
