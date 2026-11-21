"""MAYK kodlama kurulumu: DeepSeek durumu, bakiye ve model önceliği."""

from core import coding_router, jarvis_agent

PLUGIN = {
    "name": "coding_setup",
    "description": (
        "Kodlama ajanını Türkçe yönet. DeepSeek V4 Pro ilk tercih, "
        "DeepSeek Flash ikinci, NVIDIA Build üçüncü, Gemini son yedektir. "
        "'Kodlama durumunu kontrol et', 'DeepSeek bakiyemi kontrol et', "
        "'NVIDIA API durumunu kontrol et', 'kodlama sırasını göster' komutları. "
        "action: status | balance | nvidia | model. DeepSeek modeli V4 Pro veya Flash olabilir. "
        "API anahtarını sesli komutla isteme veya çıktıda gösterme; anahtar gizli ayarlarda saklanır."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "status | balance | nvidia | model"},
            "name": {"type": "STRING", "description": "İsteğe bağlı model: deepseek-v4-pro | deepseek-flash"},
        },
        "required": ["action"],
    },
}


def status() -> str:
    from core import deepseek_account, nvidia_account
    info = deepseek_account.status_text()
    nvidia_info = nvidia_account.status_text()
    models = " → ".join(jarvis_agent.deepseek_models())
    resting = coding_router.status_line()
    suffix = f" Geçici sınır: {resting}." if resting else ""
    return (info + " " + nvidia_info + " Kodlama sırası: " + models +
            " → NVIDIA Build → kullanılabilir Gemini modelleri." + suffix)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str((parameters or {}).get("action") or "status").strip().lower()
        if action in {"status", "balance", "limit", "deepseek", "login", "install"}:
            return status()
        if action in {"nvidia", "nvidia_status"}:
            from core import nvidia_account
            return nvidia_account.status_text()
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
            return f"Kodlamada önce {val}, sınırda diğer DeepSeek modeli, ardından NVIDIA ve Gemini kullanılacak."
        return status()
    except Exception:
        return "Kodlama durumuna ulaşılamadı. Yerel API ayarlarını ve internet bağlantısını kontrol edin."
