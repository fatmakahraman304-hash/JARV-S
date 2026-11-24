"""Language-model workflows; no external actions or new hardware capabilities."""
from core import thinking_studio as studio

PLUGIN = {
    "name": "thinking_studio",
    "description": (
        "FRIDAY düşünce stüdyosu. list: numaralı modları aralıkla göster; search: ad veya numaradan özellik bul; status: aktif modu oku; "
        "select: kullanıcının TAM mod komutunu command alanına yaz. "
        "Örnek: 'FRIDAY karşı ben', 'mod 11 ve 16', 'normal moda dön'. "
        "guide: belirli bir modun talimatlarını numarasıyla oku. "
        "Modlar düşünme yaklaşımıdır, gerçek cihaz veya kalıcı kayıt oluşturmaz."
    ),
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "list | search | status | select | guide"},
        "command": {"type": "STRING", "description": "select: kullanıcının tam komutu"},
        "number": {"type": "INTEGER", "description": "guide: 1–500"},
        "query": {"type": "STRING", "description": "search: Turkish feature name or number"},
        "first": {"type": "INTEGER", "description": "list: first feature number"},
        "last": {"type": "INTEGER", "description": "list: last feature number"},
    }, "required": ["action"]},
}

def run(parameters, player=None, session_memory=None):
    action = parameters.get("action")
    if action == "list":
        return studio.describe_modes(parameters.get("first") or 1, parameters.get("last") or 140)
    if action == "search":
        rows = studio.search_features(str(parameters.get("query") or ""))[:20]
        return "\n".join(f"{n}. {title}: {guide} [{status}]" for n,title,guide,status in rows) or "Eşleşme yok."
    if action == "status":
        return studio.mode_prompt() or "Normal mod açık."
    if action == "guide":
        try:
            n = int(parameters.get("number"))
            title, guidance = studio.FEATURES[n]
            return f"{n}. {title}: {guidance}\nDurum: {studio.feature_status(n)}"
        except (TypeError, ValueError, KeyError):
            return "Geçersiz özellik numarası."
    # Mutations are handled by main.py after checking the actual user utterance.
    return "Mod değişikliği yalnız doğrulanmış kullanıcı komutuyla yapılabilir."
