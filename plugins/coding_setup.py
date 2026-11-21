"""MAYK kodlama kurulumu: DeepSeek durumu, bakiye ve model önceliği."""

from core import coding_router, jarvis_agent

PLUGIN = {
    "name": "coding_setup",
    "description": (
        "Kodlama ajanını Türkçe yönet. DeepSeek V4 Pro ilk tercih, "
        "DeepSeek Flash ikinci, kullanılabilen en güçlü Gemini modeli yedektir. "
        "'Kodlama durumunu kontrol et', 'DeepSeek bakiyemi kontrol et', "
        "'kodlama sırasını göster' ve 'DeepSeek kullanım sınırına bak' komutları. "
        "action: status | balance | model. Model yalnızca DeepSeek V4 Pro veya Flash olabilir. "
        "API anahtarını sesli komutla isteme veya çıktıda gösterme; anahtar gizli ayarlarda saklanır."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "status | balance | model"},
            "name": {"type": "STRING", "description": "İsteğe bağlı model: deepseek-v4-pro | deepseek-flash"},
        },
        "required": ["action"],
    },
}


def status() -> str:
    from core import deepseek_account
    info = deepseek_account.status_text()
    models = " → ".join(jarvis_agent.deepseek_models())
    resting = coding_router.status_line()
    suffix = f" Geçici sınır: {resting}." if resting else ""
    return (info + " Kodlama modeli sırası: " + models +
            " → kullanılabilir Gemini Pro / Flash." + suffix)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str((parameters or {}).get("action") or "status").strip().lower()
        if action in {"status", "balance", "limit", "deepseek", "login", "install"}:
            return status()
        if action == "model":
            val = str((parameters or {}).get("name") or "").strip().lower()
            names = {"pro": "deepseek-v4-pro", "v4-pro": "deepseek-v4-pro",
                     "flash": "deepseek-flash"}
            val = names.get(val, val)
            if val not in {"deepseek-v4-pro", "deepseek-flash"}:
                return "Kodlama için DeepSeek V4 Pro veya DeepSeek Flash seçebilirsiniz."
            from memory.config_manager import save_plugin_config
            ordered = [val, "deepseek-flash" if val == "deepseek-v4-pro" else "deepseek-v4-pro"]
            save_plugin_config("coding", {"deepseek_models": ordered})
            return f"Kodlamada önce {val}, sınırda diğer DeepSeek modeli, ardından Gemini kullanılacak."
        return status()
    except Exception:
        return "Kodlama durumuna ulaşılamadı. Yerel API ayarlarını ve internet bağlantısını kontrol edin."
