"""Language-model workflows; no external actions or new hardware capabilities."""
from core import thinking_studio as studio
from core import integrated_capabilities as integrated
from core.core_modes import route

PLUGIN = {
    "name": "thinking_studio",
    "description": (
        "FRIDAY'in yerleşik 1000 yeteneği. resolve: kullanıcının doğal isteğinden ilgili tam iş akışlarını getir; "
        "mod seçilmesi gerekmez. guide: numarayla ayrıntılı yöntem ve gerçek durum. "
        "search/list/status: salt okunur katalog. İzin, yeni donanım veya işlem garantisi vermez."
    ),
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "resolve | list | search | status | guide"},
        "number": {"type": "INTEGER", "description": "guide: 1–1000"},
        "query": {"type": "STRING", "description": "resolve: natural user request; search: feature name or number"},
        "first": {"type": "INTEGER", "description": "list: first feature number"},
        "last": {"type": "INTEGER", "description": "list: last feature number"},
    }, "required": ["action"]},
}

def run(parameters, player=None, session_memory=None):
    action = parameters.get("action")
    if action == "resolve":
        query = parameters.get("query", "")
        return integrated.guidance(integrated.resolve(query, route(query))) or "Belirgin ek yöntem bulunamadı; normal sohbeti sürdür."
    if action == "list":
        return studio.describe_modes(parameters.get("first") or 1, parameters.get("last") or min((parameters.get("first") or 1) + 139, studio.MAX_FEATURE))
    if action == "search":
        rows = studio.search_features(str(parameters.get("query") or ""))[:20]
        return "\n".join(f"{n}. {title}: {guide} [{status}]" for n,title,guide,status in rows) or "Eşleşme yok."
    if action == "status":
        return studio.mode_prompt() or "Normal mod açık."
    if action == "guide":
        try:
            n = int(parameters.get("number"))
            title, _ = studio.FEATURES[n]
            guidance = studio.workflow_for(n)
            return f"{n}. {title}: {guidance}\nDurum: {studio.feature_status(n)}"
        except (TypeError, ValueError, KeyError):
            return "Geçersiz özellik numarası."
    # Mutations are handled by main.py after checking the actual user utterance.
    return "Mod değişikliği yalnız doğrulanmış kullanıcı komutuyla yapılabilir."
