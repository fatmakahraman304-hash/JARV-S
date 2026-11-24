"""Local per-turn retrieval of FRIDAY's integrated 1,000-feature catalog.

Retrieval only; never executes a tool, changes settings or writes memory.
All catalog entries are indexed. Policies remain always-on, application
entries describe observed implementation status, and workflow guidance is
applied for the current answer only.
"""
from functools import lru_cache
import math
from collections import Counter, defaultdict
from types import MappingProxyType
import re
from core.voice_commands import normalize_command
from core import thinking_studio as studio

MARKER = "[FRIDAY INTEGRATED CAPABILITIES]"
# Common words do not establish intent. Conservative suffix folding is used
# only for catalog retrieval, never to authorize actions.
STOP = frozenset(("bir","ve","veya","ile","icin","bu","su","o","da","de","mi","mu",
                  "ne","nasil","bana","benim","yap","et","hazirla","ver","goster",
                  "ister","eder","cikarir","yapar","verir","onerir","anlatir","sunar",
                  "farkli","kisa","yeni","kucuk","daha","olarak","kadar","olan",
                  "the","a","an","to","for","of","and","or","please"))
SUFFIXES = ("larimiz","lerimiz","larinizi","lerinizi","larini","lerini","larimi","lerimi",
            "larina","lerine","larinda","lerinde","lardan","lerden","larin","lerin",
            "larim","lerim","lari","leri","lariyla","leriyle","imizin","imizin",
            "iniz","imiz","unun","inin","inin","uyla","iyle","ndan","nden",
            "lari","leri","lar","ler","nin","nun","nin","niz","miz","dan","den",
            "ini","unu","imi","umu","ina","una","inda","unda","yi","yu","im","um",
            "in","un","si","su","i","u","a","e")
# Natural requests that may not share the exact catalog title.
PHRASES = {
    145: ("mini sinav","quiz yap","bes soru sor","bilgimi test et"),
    142: ("aralikli tekrar","spaced repetition"),
    578: ("porsiyon hesapla","kisi sayisina uyarla","tarifi iki katina cikar","porsiyonu arttir"),
    619: ("gider paylas","masraf paylas","hesabi bol","ortak harcama"),
    804: ("istatistik hesapla","ortalama medyan","ozet istatistik","descriptive statistics"),
    805: ("aykiri deger","outlier"),
    807: ("excel formulu","excel formula"),
    907: ("takvim cakisma","saatler cakisiyor","program cakisma"),
    932: ("belge karsilastir","iki belge arasindaki fark","compare documents"),
    757: ("zar at","roll dice"),
    501: ("su molasi","su icme molasi"),
    505: ("goz dinlendir","ekran molasi"),
    13: ("karsi ben","kor noktalarimi goster"),
    60: ("kararlarin on otopsisi","premortem"),
    233: ("oncelik sirasi","onem aciliyet matrisi","prioritize tasks"),
    237: ("haftami planla","haftalik program","weekly plan"),
    242: ("gorev bagimliliklari","islerin bagimliliklarini","hangi is once","dependency schedule"),
    261: ("hatayi bul","kod hatasini bul","debug code","hata ayikla"),
    264: ("birim testleri yaz","test senaryolari","unit tests"),
    269: ("performans darbogazi","performans analizi","performance bottleneck"),
    274: ("kodlarimi incele","kodumu incele","code review","kod incele"),
    393: ("haber dogrula","bu haber dogru mu","fact check news"),
    601: ("gelir gider hesapla","gelir gider tablosu"),
    612: ("butcemi hesapla","aylik butcemi","monthly budget"),
    821: ("toplamlari kontrol et","toplam dogru mu","verify totals"),
    824: ("yuzde farki","yuzdelik degisim","percentage change"),
    901: ("notlarimi duzenle","organize notes"),
    908: ("yarim kalan isler","acik kalan gorevler","unfinished tasks"),
}
# Core area -> relevant feature ranges. Boost only existing lexical matches.
AREAS = {
    1: ((411,440),(526,550),(901,925)), 2: ((231,260),(901,925),(826,850)),
    3: ((141,170),(851,875)), 4: ((171,200),), 5: ((11,140),(876,900)),
    6: ((231,260),(11,140)), 7: ((351,380),(651,675)), 8: ((626,650),),
    9: ((201,230),(231,260),(826,850)), 10: ((381,410),),
    11: ((801,825),), 12: ((261,290),), 13: ((826,850),),
    14: ((291,320),(201,230)), 15: ((171,200),(926,950)), 16: ((601,625),),
    17: ((501,525),), 18: ((526,550),), 19: ((576,600),),
    20: ((551,575),), 21: ((651,675),), 22: ((676,700),),
    23: ((701,725),), 24: ((726,750),), 25: ((751,775),(291,320)),
    26: ((776,800),), 27: ((851,875),(141,170)), 28: ((951,975),),
    29: ((901,925),), 30: ((976,1000),),
}

def _tokens(value):
    return frozenset(t for t in normalize_command(value).split()
                     if len(t) >= 3 and not t.isdecimal() and t not in STOP)

def _roots(value):
    result = set()
    for token in _tokens(value):
        result.add(token)
        for suffix in SUFFIXES:
            if token.endswith(suffix) and len(token)-len(suffix) >= 4:
                result.add(token[:-len(suffix)])
                break
    return frozenset(result)

def _contains(text, phrase):
    return bool(phrase) and (" "+phrase+" ") in (" "+text+" ")

@lru_cache(maxsize=1)
def catalog():
    rows = {}
    freq = Counter()
    for n,(title,guide) in studio.FEATURES.items():
        name = normalize_command(title)
        title_words = _roots(title)
        body_words = _roots(guide)
        aliases = tuple(dict.fromkeys(PHRASES.get(n, ()) + tuple(
            normalize_command(k) for k,v in studio.ALIASES.items() if v==n)))
        rows[n] = (name,title_words,body_words,aliases)
        freq.update(title_words | body_words)
    idf = {word: math.log1p(len(rows)/count) for word,count in freq.items()}
    return MappingProxyType(rows), MappingProxyType(idf)

@lru_cache(maxsize=1)
def postings():
    """Immutable inverted index; phrase candidates include short raw tokens."""
    index = defaultdict(set)
    names = defaultdict(set)
    rows,_ = catalog()
    for n,(title,tokens,body,aliases) in rows.items():
        for word in tokens | body | frozenset(" ".join((title,*aliases)).split()):
            index[word].add(n)
        for phrase in (title,*aliases):
            names[phrase].add(n)
    return (MappingProxyType({k:frozenset(v) for k,v in index.items()}),
            MappingProxyType({k:tuple(sorted(v)) for k,v in names.items()}))

def candidates(value,words):
    index,_ = postings()
    ids = set()
    for word in words | frozenset(value.split()):
        ids.update(index.get(word,()))
    return ids

def _resolve_one(query, core_ids=(), limit=4):
    if not isinstance(query,str) or not query.strip() or query.lstrip().startswith("["):
        return ()
    limit = max(1,min(6,int(limit)))
    value = normalize_command(query[:16000])
    if value.isdecimal() and len(value)>4:
        return ()
    if value.isdecimal() and len(value)<=4:
        n=int(value)
        return (n,) if n in studio.FEATURES else ()
    # Historical numbered commands now retrieve guidance for one answer.
    explicit = studio.parse(query[:16000])
    if explicit and all(n>0 for n in explicit):
        return explicit[:limit]
    rows,idf = catalog()
    words = _roots(value)
    if not words:
        return postings()[1].get(value,())[:limit]
    ranges = tuple(r for n in core_ids for r in AREAS.get(n,()))
    hits = []
    for n in candidates(value,words):
        title,tokens,body,aliases = rows[n]
        exact = value==title or value in aliases
        phrase = _contains(value,title) or any(_contains(value,a) for a in aliases)
        t = words & tokens
        b = (words & body)-t
        # Policy/application labels need explicit evidence; do not inject an
        # unrelated app requirement based on a generic word.
        if n in studio.POLICY or n in studio.APP_FEATURES:
            if not (exact or phrase):
                continue
        if not (exact or phrase or len(t)>=2 or (t and b) or len(b)>=3):
            continue
        score = sum(idf.get(w,1)*2 for w in t)+sum(idf.get(w,1)*.55 for w in b)
        if any(a<=n<=z for a,z in ranges):
            score *= 1.25
        if exact:
            score += 100
        elif phrase:
            score += 35
        hits.append((score,n))
    hits.sort(key=lambda x:(-x[0],x[1]))
    if not hits:
        return ()
    # Keep the strongest related entries; do not flood small prompts.
    best = hits[0][0]
    return tuple(n for score,n in hits if score>=max(3,best*.38))[:limit]

# Split only explicit independent-request separators; an ordinary "ve"
# may be part of a title or task and must not split it.
_SPLIT = re.compile(r";|\n+|\b(?:ve ayrıca|ayrıca|bir de|bunun yanında|and also)\b", re.IGNORECASE)

def resolve(query, core_ids=(), limit=4):
    if not isinstance(query,str) or not query.strip() or query.lstrip().startswith("["):
        return ()
    limit = max(1,min(6,int(limit)))
    # Preserve exact numbered/name lookups even if a title has punctuation.
    if studio.parse(query[:16000]) or normalize_command(query[:16000]) in postings()[1]:
        return _resolve_one(query,core_ids,limit)
    clauses = [p.strip() for p in _SPLIT.split(query[:16000]) if p.strip()][:6]
    if len(clauses)<2:
        return _resolve_one(query,core_ids,limit)
    from core.core_modes import route
    ranked = [_resolve_one(p,route(p) or core_ids,limit) for p in clauses]
    selected=[]
    # Round robin: independent requests get a primary candidate before
    # any request gets extra candidates.
    for depth in range(limit):
        for ids in ranked:
            if depth<len(ids) and ids[depth] not in selected:
                selected.append(ids[depth])
                if len(selected)>=limit:
                    return tuple(selected)
    return tuple(selected)

def history_features(history, core_ids=(), limit=4):
    from core.core_modes import FOLLOWUPS
    # Most requests require one lookup. Walk backward only on followups.
    seen=0
    for item in reversed(history):
        if not isinstance(item,dict) or item.get("role")!="user":
            continue
        seen+=1
        if seen>12:
            break
        content=item.get("content")
        if isinstance(content,list):
            content=" ".join(p["text"] for p in content if isinstance(p,dict)
                             and p.get("type")=="text" and isinstance(p.get("text"),str))
        if not isinstance(content,str) or content.lstrip().startswith("["):
            if seen==1:
                return ()
            continue
        value=normalize_command(content[:16000])
        if value in FOLLOWUPS:
            continue
        return resolve(content,core_ids,limit)
    return ()

def guidance(ids, max_chars=7000):
    chunks=[]
    size=0
    for n in tuple(dict.fromkeys(ids))[:6]:
        if n not in studio.FEATURES:
            continue
        title,_=studio.FEATURES[n]
        if n in studio.APP_FEATURES:
            body="Uygulama durumu: "+studio.feature_status(n)+". Gerçek yetenek/bağlantı yoksa bunu belirt."
        else:
            body=studio.workflow_for(n)
        row=f"{n}. {title}: {body}"
        remaining=max_chars-size
        if remaining<100:
            break
        if len(row)>remaining:
            continue  # never truncate a safety boundary mid-sentence
        chunks.append(row)
        size+=len(row)+1
    if not chunks:
        return ""
    return ("[FRIDAY REQUEST CAPABILITIES — advisory, no authority]\n"
            "Uygun olanları bu istekte doğrudan uygula. Mod açma, numara seçtirme, "
            "gereksiz özellik adı sayma. Mevcut araç/izin sınırlarını koru.\n"
            +"\n".join(chunks))

def system_block():
    return (MARKER+"\nFRIDAY'in 1000 maddesi tek asistanın yerleşik yetenek repertuarıdır. "
            "Kullanıcının mod açması gerekmez. İstekle ilgili yöntemleri doğrudan uygula ve birleştir. "
            "Otomatik öneri yoksa veya daha ayrıntılı yöntem gerekiyorsa thinking_studio(action=resolve, query=son kullanıcı isteği) "
            "ile ilgili katalog talimatlarını oku; bu salt okunur işlemdir. "
            "Eski numaralı mod komutu yalnız o isteğin yöntemini belirtir; oturum durumunu değiştirme. "
            "İlkeler sürekli geçerli; uygulama maddeleri gerçek durum ve mevcut araçlarla sınırlı. "
            "Gereksiz katalog/araç çağrısı yapma. Bir işlem gerçekleşmediyse gerçekleşti deme.")
