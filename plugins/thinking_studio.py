"""Language-model workflows; no external actions or new hardware capabilities."""
from core import thinking_studio as studio

PLUGIN = {
    "name": "thinking_studio",
    "description": (
        "FRIDAY düşünce stüdyosu. list: numaralı modları göster; status: aktif modu oku; "
        "select: kullanıcının TAM mod komutunu command alanına yaz. "
        "Örnek: 'FRIDAY karşı ben', 'mod 11 ve 16', 'normal moda dön'. "
        "guide: belirli bir modun talimatlarını numarasıyla oku. "
        "Modlar düşünme yaklaşımıdır, gerçek cihaz veya kalıcı kayıt oluşturmaz."
    ),
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "list | status | select | guide"},
        "command": {"type": "STRING", "description": "select: kullanıcının tam komutu"},
        "number": {"type": "INTEGER", "description": "guide: 1–140"},
    }, "required": ["action"]},
}

def run(parameters, player=None, session_memory=None):
    action = parameters.get("action")
    if action == "list":
        return studio.describe_modes()
    if action == "status":
        return studio.mode_prompt() or "Normal mod açık."
    if action == "guide":
        try:
            n = int(parameters.get("number"))
            title, guidance = studio.FEATURES[n]
            return f"{n}. {title}: {guidance}"
        except (TypeError, ValueError, KeyError):
            return "Geçersiz özellik numarası."
    # Mutations are handled by main.py after checking the actual user utterance.
    return "Mod değişikliği yalnız doğrulanmış kullanıcı komutuyla yapılabilir."
