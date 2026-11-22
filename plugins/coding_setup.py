"""AETHER kodlama model kontrolü: NVIDIA Build → Gemini."""

from core import coding_router

PLUGIN = {
    "name": "coding_setup",
    "description": (
        "AETHER kodlama modellerini Türkçe kontrol et. Öncelik NVIDIA Build'dir, "
        "NVIDIA kullanılamazsa Gemini'ye geçilir. "
        "'Kodlama durumunu kontrol et', 'NVIDIA API durumunu kontrol et', "
        "'kodlama sırasını göster', 'NVIDIA modelini değiştir' komutları. "
        "action: status | nvidia | model | metrics. API anahtarını isteme veya gösterme; "
        "anahtar yalnızca yerel güvenli ayarlarda saklanır."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "status | nvidia | model | metrics"},
            "name": {"type": "STRING", "description": "İsteğe bağlı NVIDIA model kimliği"},
        },
        "required": ["action"],
    },
}


def status() -> str:
    from core import nvidia_account
    info = nvidia_account.status_text()
    resting = coding_router.status_line()
    suffix = f" Bekleyen model: {resting}." if resting else ""
    return info + " Kodlama sırası: NVIDIA Build → Gemini." + suffix


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import nvidia_account
        action = str((parameters or {}).get("action") or "status").strip().lower()
        if action in {"status", "nvidia", "nvidia_status", "limit"}:
            return status()
        if action == "metrics":
            from core.gemini import model_report
            rows = model_report()
            if not rows:
                return "Bu oturumda henüz tek istekli model çağrısı ölçülmedi."
            return "\n".join(
                f"{model}: {row['attempts']} çağrı, ortalama {row['mean_ms']} ms, "
                f"hata %{row['error_rate'] * 100:.0f}, son hata: {row['last_error'] or 'yok'}"
                for model, row in rows.items())
        if action == "model":
            model = str((parameters or {}).get("name") or "").strip()
            if not model:
                return "NVIDIA model kimliğini belirtin."
            models = nvidia_account.available_models(refresh=True, verified_only=True)
            if model not in models:
                return ("Model, NVIDIA hesabınızda doğrulanamadı. "
                        "MOTOR VE SAĞLAYICILAR içinden YENİLE'yi kullanın.")
            from memory.config_manager import save_plugin_config
            save_plugin_config("coding", {"nvidia_models": [model]})
            return f"Kodlamada önce {model}, ardından diğer NVIDIA modelleri ve Gemini denenir."
        return status()
    except Exception:
        return "Kodlama durumuna ulaşılamadı. NVIDIA ayarlarını ve interneti kontrol edin."
