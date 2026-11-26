"""Offline FRIDAY usage guide, independent of the selected model provider."""

from __future__ import annotations

PLUGIN = {
    "name": "assistant_help",
    "description": (
        "FRIDAY'in kendi kullanım kılavuzu: ayarlar nerede, hangi motoru seçebilirim, "
        "mikrofon veya model çalışmıyorsa ne yapmalıyım, rutin, güncelleme ve eklenti "
        "nasıl kullanılır? Use for specific how-to questions about FRIDAY itself, "
        "not generic capability lists (capabilities) or actual diagnostics (self_check)."
    ),
    "brief": "FRIDAY'in yerel kullanım ve sorun giderme kılavuzu.",
    "tier": "extra",
    "parameters": {"type": "OBJECT", "properties": {
        "topic": {"type": "STRING", "enum": [
            "index", "startup", "providers", "audio", "plugins", "routines",
            "updates", "diagnostics", "tasks"
        ], "description": "Kullanıcının sorduğu kılavuz bölümü."}
    }, "required": ["topic"]},
}

# Static, project-specific instructions. Do not read private configuration,
# make network requests, execute commands, or infer current session health.
_GUIDE = {
    "startup": ("Başlatma", "Windows'ta Python 3.13 ile kaynak ZIP'i yazılabilir bir klasöre çıkar; "
        "FRIDAY_BASLAT.cmd dosyasını çalıştır. İlk açılış yerel Python ortamını hazırlar. "
        "Sonraki açılışlarda aynı ortam kullanılır.", "readme.md"),
    "providers": ("Motor ve sağlayıcılar", "Motor ve sağlayıcılar panelinden Gemini Live, "
        "pipeline veya deneysel OpenAI Realtime seçilebilir. Realtime ayrı API anahtarı ve açık "
        "bulut aktarımı onayı ister; mikrofon isteğe bağlıdır, bilgisayar araçları henüz desteklenmez. "
        "Pipeline dinleme, düşünme ve konuşma bileşenlerini ayrı kullanır. "
        "Mevcut seçenekleri panelden seçip bağlantı testini çalıştır; sağlayıcının gerekli anahtarı "
        "veya yerel sunucusu gerekebilir. Anahtarını sohbete yazma. Bu kılavuz bağlantıyı test etmez.",
        "gui/providers_panel.py; providers/registry.py"),
    "audio": ("Mikrofon ve ses", "Doğru giriş ve çıkış aygıtını seç; işletim sistemindeki mikrofon "
        "iznini, fiziksel sessize alma düğmesini ve ses seviyesini kontrol et. "
        "Gerçek aygıt teşhisi için 'kendini kontrol et' de.", "plugins/self_check.py"),
    "plugins": ("Eklentiler", "Eklenti yöneticisinden mevcut araçların etkin ve geçerli olup "
        "olmadığını kontrol et. Bir eklenti hata veriyorsa gösterilen hata mesajını incele. "
        "Geliştirme için plugins/_template.py sözleşmesini kullan; sadece güvenilir kod yükle. "
        "Bir Python eklentisi bilgisayarındaki izinlerle çalışabilir. Bu rehber eklenti kurmaz.",
        "core/plugin_loader.py; plugins/_template.py"),
    "routines": ("Rutinler", "'Akşam modu diye bir rutin yap: ışığı kıs, müzik aç' gibi bir komutla "
        "rutin tanımlayabilirsin; sonra adını söyleyerek çağırabilirsin. "
        "'Her cuma 17:00'de raporu hatırlat' gibi zamanlı rutinler de tanımlanabilir. "
        "Bu rehber rutin oluşturmaz veya çalıştırmaz.", "readme.md; actions/routines.py"),
    "updates": ("Güncelleme", "'Yeni sürüm var mı?' diye sorarak güncellemeyi kontrol edebilirsin. "
        "GÜNCELLE panelindeki durumu takip et. Hata varsa hata metnini sakla ve 'son hataları göster' de. "
        "Bu rehber indirme, kurulum veya geri alma işlemi başlatmaz.", "plugins/self_update.py; plugins/self_check.py"),
    "diagnostics": ("Teşhis", "'Kendini kontrol et' model, ağ, ses aygıtları, disk ve diğer "
        "bileşenleri denetlemek için kullanılır. 'Son hataları göster' yakın tarihli hataları gösterir. "
        "Bu kılavuz canlı bir teşhis sonucu değildir.", "plugins/self_check.py"),
    "tasks": ("Arka plan görevleri", "Uzun araştırmalar arka plan görevleri olarak yürütülebilir. "
        "'Arka planda bir rapor hazırla' veya 'ne yaptın?' diyebilirsin. Görev panosu ve iş durumu "
        "gerçek yürütme durumunu gösterir; bu rehber bir görevin bittiğini iddia etmez.", "readme.md; plugins/work_status.py"),
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    topic = parameters.get("topic") if isinstance(parameters, dict) else None
    if isinstance(topic, str):
        topic = topic.strip().lower()
    if not isinstance(topic, str) or topic not in _GUIDE:
        sections = "; ".join(f"{key}: {value[0]}" for key, value in _GUIDE.items())
        prefix = "FRIDAY kullanım kılavuzu" if topic in ("index", None, "") else "Bu konuda doğrulanmış kılavuz bölümü yok"
        return f"{prefix}. Bölümler: {sections}."
    title, body, source = _GUIDE[topic]
    return f"{title}: {body}\nProje içi başvuru: {source}."
