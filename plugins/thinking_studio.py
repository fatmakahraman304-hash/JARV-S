"""Language-model workflows; no external actions or new hardware capabilities."""
from core import thinking_studio as studio
from core import integrated_capabilities as integrated
from core.core_modes import route

PLUGIN = {
    "name": "thinking_studio",
    "description": (
        "FRIDAY'in yerleşik 1000 yeteneği. resolve: kullanıcının doğal isteğinden ilgili tam iş akışlarını getir; "
        "mod seçilmesi gerekmez. guide: numarayla ayrıntılı yöntem ve gerçek durum. "
        "search/list/status: salt okunur katalog; list tüm ilkeleri ve uygulama durumlarını da kapsar. "
        "Sayfa aralığı en fazla 100 özellik; search en fazla 20 sonuç. İzin, yeni donanım veya işlem garantisi vermez."
    ),
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "resolve | list | search | status | guide"},
        "number": {"type": "INTEGER", "description": "guide: 1–1000"},
        "query": {"type": "STRING", "description": "resolve: natural user request; search: feature name or number"},
        "first": {"type": "INTEGER", "description": "list/search: first feature number (1–1000)"},
        "last": {"type": "INTEGER", "description": "list/search: last feature number (1–1000)"},
    }, "required": ["action"]},
}

def _feature_number(value, default=None):
    """Accept only exact integer identifiers; never truncate a float or bool."""
    if value is None and default is not None:
        return default
    if type(value) is str and value.isascii() and value.isdecimal() and len(value) <= 4:
        value = int(value)
    if type(value) is not int or not 1 <= value <= studio.MAX_FEATURE:
        raise ValueError("Özellik numarası 1–1000 arasında tam sayı olmalı.")
    return value


def _range(parameters, page_size):
    first = _feature_number(parameters.get("first"), 1)
    last = _feature_number(parameters.get("last"), min(first+page_size-1, studio.MAX_FEATURE))
    if last < first:
        raise ValueError("Son özellik numarası ilk numaradan küçük olamaz.")
    return first, last


def _kind(n):
    if n in studio.POLICY:
        return "Sürekli ilke"
    if n in studio.APP_FEATURES:
        return "Uygulama"
    return "Sohbet yeteneği"


def run(parameters, player=None, session_memory=None):
    if not isinstance(parameters,dict):
        return "Geçersiz katalog isteği."
    action = parameters.get("action")
    try:
        if action == "resolve":
            query = parameters.get("query", "")
            if not isinstance(query,str) or len(query)>16000:
                raise ValueError("İstek metni en fazla 16000 karakter olmalı.")
            return integrated.guidance(integrated.resolve(query, route(query))) or "Belirgin ek yöntem bulunamadı; normal sohbeti sürdür."
        if action == "list":
            first,last = _range(parameters,100)
            end = min(last,first+99)
            rows = [f"{n}. {studio.FEATURES[n][0]} [{_kind(n)} · {studio.implementation_kind(n)}]" for n in range(first,end+1)]
            prefix = f"Katalog: {first}–{end} / {studio.MAX_FEATURE}"
            if end<last or end<studio.MAX_FEATURE:
                prefix += f" | Sonraki sayfa: first={end+1}"
            return prefix+"\n"+"\n".join(rows)
        if action == "search":
            query = parameters.get("query","")
            if not isinstance(query,str) or len(query)>300:
                raise ValueError("Arama metni en fazla 300 karakter olmalı.")
            first,last = _range(parameters,studio.MAX_FEATURE)
            rows = studio.search_features(query,first,last)
            shown = rows[:20]
            if not shown:
                return "Eşleşme yok."
            prefix = f"{len(rows)} eşleşme, {len(shown)} gösteriliyor."
            if len(rows)>20:
                prefix += f" Sonraki aralık: first={shown[-1][0]+1}, last={last}."
            return prefix+"\n"+"\n".join(f"{n}. {title}: {guide} [{_kind(n)}; {studio.implementation_kind(n)}; {status}]" for n,title,guide,status in shown)
        if action == "status":
            return studio.mode_prompt() or "Normal sohbet açık; yerleşik yetenekler otomatik kullanılır."
        if action == "guide":
            n = _feature_number(parameters.get("number"))
            title,_ = studio.FEATURES[n]
            if n in studio.APP_FEATURES:
                guidance = "Uygulama gereksinimi ve gerçek durumu: "+studio.feature_status(n)+". Uygulanmış olmayan işlemi yapılmış sayma."
            else:
                guidance = studio.workflow_for(n)
            return f"{n}. {title}: {guidance}\nTür: {_kind(n)} · {studio.implementation_kind(n)}\nDurum: {studio.feature_status(n)}"
    except (TypeError, ValueError, KeyError) as exc:
        return "Geçersiz katalog isteği: "+str(exc)[:160]
    # Mutations are handled by main.py after checking the actual user utterance.
    return "Mod değişikliği yalnız doğrulanmış kullanıcı komutuyla yapılabilir."
