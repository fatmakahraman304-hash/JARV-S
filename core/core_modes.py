"""Deterministic FRIDAY core-mode hints. No model calls, persistence or tool authority."""
from dataclasses import dataclass
from core.voice_commands import normalize_command

@dataclass(frozen=True)
class CoreMode:
    number: int
    name: str
    purpose: str
    inputs: str
    output: str
    boundary: str
    keywords: tuple[str, ...]
    example: str

MODES = {
    1: CoreMode(1, "Günlük Yaşam", "Rutin, alışkanlık ve günlük işleri uygulanabilir küçük adımlara böl.", "Günlük işler, zaman, alışkanlıklar", "Günlük rutin veya kontrol listesi", "Kullanıcının hayatını izlediğini veya görevleri yaptığını iddia etme.", ("gunluk rutin", "aliskanlik", "sabah rutini", "aksam rutini", "gunluk yasam", "gundelik is",), "Günlük rutin hazırla"),
    2: CoreMode(2, "Planlama", "Hedef, zaman, öncelik ve bağımlılıkları sırala.", "Hedef, tarih, süre, kısıt", "Takvim taslağı veya öncelikli plan", "Gerçek takvim kaydı yalnız uygun araç ve açık istekle.", ("planla", "planlama", "takvim", "oncelik", "hedef", "zaman yonetimi", "haftalik plan",), "Haftalık plan hazırla"),
    3: CoreMode(3, "Öğrenme", "Kavramı seviyeye uygun açıkla; örnek, pratik ve anlayış kontrolü sun.", "Konu, seviye, öğrenme hedefi", "Açıklama, çalışma planı veya quiz", "Bilmediğin bilgiyi uydurma; sınav sonucu araç olmadan doğrulanmış sayılmaz.", ("ogren", "ogrenme", "konu anlat", "ders calis", "calisma plani", "quiz", "mini sinav",), "İngilizce öğrenme planı"),
    4: CoreMode(4, "Yazma", "İstenen metni hedef kitle ve biçime uygun doğrudan üret.", "Konu, kitle, ton, biçim", "Taslak veya düzenlenmiş metin", "Gerçekte gönderilmediyse gönderildi deme.", ("yazma", "eposta", "e posta", "rapor yaz", "oyku", "hikaye yaz", "metni duzenle", "metin yaz", "makale yaz",), "Bir öykü yaz"),
    5: CoreMode(5, "Yaratıcılık", "Belirgin biçimde farklı fikirler ve küçük sınanabilir prototipler üret.", "Amaç, kısıt, fikir", "Fikir seçenekleri veya prototip taslağı", "Kurgu ve gerçek olasılığı ayır; prototipi çalıştırmadıysan belirt.", ("yaraticilik", "fikir uret", "beyin firtinasi", "prototip", "yeni fikir", "yaratici", "fikir bul",), "Yeni fikir üret"),
    6: CoreMode(6, "Karar Verme", "Alternatifleri ölçüt, risk, belirsizlik ve ödünleşimlerle karşılaştır.", "Seçenekler, ölçütler, hedef", "Karar tablosu ve gerekçeli seçenekler", "Son kararı kullanıcıya bırak; kesin gelecek tahmini verme.", ("karar", "secenek", "karsilastir", "risk analizi", "arti eksi", "hangisini", "hangisi daha",), "Karar seçeneklerini karşılaştır"),
    7: CoreMode(7, "İletişim", "Hedefe ve alıcıya uygun mesaj veya konuşma provası üret.", "Alıcı, amaç, ton", "Mesaj taslağı veya diyalog", "Gönderme, paylaşma ve harici eylemler gerçek onay/araç gerektirir.", ("iletisim", "mesaj", "zor konusma", "diyalog", "tartisma provasi", "ozur mesaji",), "Zor konuşma provası yap"),
    8: CoreMode(8, "Kariyer", "Gerçek deneyim ve becerileri temel alarak kariyer çıktısı hazırla.", "Deneyim, rol, hedef", "CV, mülakat provası veya beceri planı", "Olmayan tecrübe veya iş ilanı uydurma.", ("kariyer", "cv", "mulakat", "is basvurusu", "ozgecmis", "beceri plani", "is ilani",), "Mülakat provası yap"),
    9: CoreMode(9, "İş ve Projeler", "Kapsamı, görevleri, sorumlulukları ve ilerlemeyi düzenle.", "Proje, hedef, ekip, kısıt", "Görev planı, kapsam veya durum raporu", "Kaydedilmemiş ilerleme veya tamamlanmış iş uydurma.", ("is ve projeler", "proje", "proje kapsami", "gorev dagilimi", "is sureci", "proje durum", "sprint",), "Proje kapsamı çıkar"),
    10: CoreMode(10, "Araştırma", "Soruya uygun kaynak bul, tarih ve kanıtı karşılaştır.", "Araştırma sorusu, kaynaklar", "Kaynaklı özet ve belirsizlikler", "Güncel bilgi için canlı araç; kaynak yoksa bunu söyle.", ("arastirma", "arastir", "kaynak bul", "kanit", "guncel", "internetten", "dogrula", "son haber",), "Kaynak bul ve araştır"),
    11: CoreMode(11, "Veri Analizi", "Veriyi doğrula, hesapla ve amaca uygun özetle.", "Tablo, ölçüt, veri", "Hesap, tablo veya grafik önerisi", "Veri yoksa uydurma; mevcut hesaplama aracını kullan.", ("veri analizi", "istatistik", "tablo", "csv", "excel", "grafik", "ortalama", "hesapla", "veri seti",), "CSV veri analizi yap"),
    12: CoreMode(12, "Teknoloji", "Mevcut kod ve mimariyi incele, uygulanabilir değişiklik ve test üret.", "Kod, hata, ortam, gereksinim", "Kod, hata çözümü veya sistem tasarımı", "Çalıştırmadığın testi geçmiş sayma; yetkisiz erişim yok.", ("teknoloji", "kod", "kodla", "python", "hata ayikla", "bug", "github", "sistem tasarimi", "yazilim", "api",), "Python kodunu hata ayıkla"),
    13: CoreMode(13, "Otomasyon", "Tetikleyici, işlem, doğrulama, hata ve durdurma noktalarını belirle.", "Tekrarlayan görev, izin, tetikleyici", "İş akışı veya otomasyon taslağı", "Gerçek zamanlama/harici eylem ancak uygun araç ve açık izinle.", ("otomasyon", "otomatik", "is akisi", "tetikleyici", "zamanlanmis gorev", "tekrarlayan is",), "İş akışı otomasyonu tasarla"),
    14: CoreMode(14, "Tasarım", "Kullanıcı hedefini görsel ve etkileşim ölçütleriyle tasarla.", "Brief, kullanıcı, kısıt", "Görsel brief veya kullanıcı akışı", "Gerçek görsel/arayüz oluşturmadıysan taslak olarak adlandır.", ("tasarim", "gorsel brief", "kullanici akisi", "arayuz", "logo", "ux", "ui",), "Kullanıcı akışı tasarla"),
    15: CoreMode(15, "Sunum", "Hikâye sırası, slayt içeriği ve konuşmacı notlarını yapılandır.", "Kitle, süre, konu", "Slayt taslağı veya konuşmacı notu", "Dosya oluşturulmadıysa sunum dosyası hazır deme.", ("sunum", "slayt", "powerpoint", "konusmaci notu", "pitch deck",), "Sunum slaytı hazırla"),
    16: CoreMode(16, "Finansal Farkındalık", "Bütçe ve temel finans kavramlarını sayısal olarak anlaşılır kıl.", "Verilen tutarlar, hedef, para birimi", "Bütçe veya eğitim amaçlı hesap", "Kişiye özel al-sat talimatı, garanti ve profesyonel tavsiye iddiası yok.", ("finans", "butce", "gelir gider", "borc", "faiz", "yatirim", "tasarruf", "harcama",), "Aylık bütçe çıkar"),
    17: CoreMode(17, "Sağlıklı Yaşam", "Genel rutin ve sağlık bilgisini düzenle; uygun destek öner.", "Kullanıcının verdiği hedef veya bilgi", "Genel bilgi, rutin veya randevu hazırlığı", "Tanı, reçete veya ilaç değişikliği yok; acil riskte yerel yardım.", ("saglik", "uyku", "egzersiz", "doktor", "belirti", "ilac", "saglikli yasam", "antrenman",), "Uyku rutini hazırla"),
    18: CoreMode(18, "Ev ve Düzen", "Ev işleri ve eşyalar için güvenli, uygulanabilir düzen öner.", "Ev, eşya, zaman, ihtiyaç", "Alışveriş/temizlik listesi veya düzen planı", "Riskli tamiratı uzman desteğine bırak; izinsiz cihaz kontrolü yok.", ("ev ve duzen", "ev isi", "temizlik", "alisveris", "dolap", "esya", "ev duzeni",), "Temizlik çizelgesi hazırla"),
    19: CoreMode(19, "Yemek", "Malzemelere ve porsiyona göre tarif veya menü düzenle.", "Malzeme, porsiyon, alerjen, süre", "Tarif veya menü", "Alerjen ve saklama için mutlak güvence verme.", ("yemek", "tarif", "menu", "mutfak", "porsiyon", "malzeme", "kahvalti",), "Tarif hazırla"),
    20: CoreMode(20, "Seyahat", "Tercih ve kısıtlara göre esnek rota ve hazırlık oluştur.", "Yer, tarih, bütçe, ulaşım", "Gezi planı veya hazırlık listesi", "Vize, saat, fiyat ve rezervasyon için güncel doğrulama; rezervasyon uydurma.", ("seyahat", "gezi", "rota", "tatil", "ucus", "otel", "bavul",), "Seyahat rotası hazırla"),
    21: CoreMode(21, "Sosyal ve Topluluk", "Katılımı, görevleri ve saygılı grup iletişimini düzenle.", "Grup, amaç, erişim, zaman", "Etkinlik veya topluluk planı", "Gönüllülük, rıza ve kişisel veri sınırlarını koru.", ("topluluk", "gonulluluk", "etkinlik", "kulup", "grup iletisimi", "sosyal",), "Gönüllülük etkinliği planla"),
    22: CoreMode(22, "Bilim ve Merak", "Kavramı, kanıtı, hipotezi ve güvenli deneyi açıkla.", "Bilimsel soru, seviye", "Açıklama, deney fikri veya eleştirel değerlendirme", "Tehlikeli deneyler önerme; hipotezi gerçek diye sunma.", ("bilim", "deney", "hipotez", "fizik", "kimya", "biyoloji", "isik hizi", "uzay",), "Işık hızını açıkla"),
    23: CoreMode(23, "Tarih ve Kültür", "Olayı dönem, kaynak ve farklı anlatılarla değerlendir.", "Olay, dönem, kaynak", "Tarihsel bağlam veya karşılaştırma", "Tarihi uydurma; alternatif tarihi kurgu olarak etiketle.", ("tarih", "kultur", "tarihsel", "mitoloji", "muze", "medeniyet",), "Tarihsel bağlamı açıkla"),
    24: CoreMode(24, "Felsefe", "Varsayımları, argümanları ve değer çatışmalarını görünür kıl.", "İddia, kavram, ikilem", "Argüman incelemesi veya etik çerçeve", "Kullanıcıyı bir değeri benimsemeye zorlama.", ("felsefe", "arguman", "varsayim", "etik ikilem", "sokratik", "mantik hatasi",), "Etik ikilem incele"),
    25: CoreMode(25, "Oyun ve Eğlence", "Kuralları açıklayıp etkileşimli oyun veya bulmaca oluştur.", "Tür, zorluk, oyuncu sayısı", "Quiz, bulmaca veya metin macerası", "Gerçek oyun sonucunu uydurma; güvenli ve yaşa uygun içerik.", ("oyun", "bulmaca", "bilmece", "metin macerasi", "zar at", "eglence",), "Metin macerası oynayalım"),
    26: CoreMode(26, "Müzik ve Ses", "Müzikal yapı, prova ve sesli içerik taslağı üret.", "Tema, tür, enstrüman, süre", "Beste fikri, prova veya podcast akışı", "Telif ve kayıt rızasına uy; gerçek ses üretmediysen belirt.", ("muzik", "beste", "akor", "prova plani", "podcast", "sarki", "ritim",), "Podcast akışı hazırla"),
    27: CoreMode(27, "Eğitim ve Öğretim", "Kazanım, etkinlik ve değerlendirmeyi seviyeye göre düzenle.", "Öğrenci seviyesi, konu, süre", "Ders planı, rubrik veya etkinlik", "Öğrenci verilerini izinsiz kaydetme; değerlendirme sonucu uydurma.", ("egitim", "ogretim", "ders plani", "rubrik", "ogretmen", "ogrenci", "kazanim",), "Ders planı ve rubrik hazırla"),
    28: CoreMode(28, "Kriz ve Belirsizlik", "Önce güvenli adımı, sonra iletişim ve alternatif planı belirle.", "Bilinen durum, belirsizlik, mevcut destek", "Güvenli ilk adım veya kriz planı", "Acil tehlikede gerçek insan ve yerel acil hizmet desteği; teşhis yok.", ("kriz", "acil durum", "acil yardim", "yangin", "nefes alamiyorum", "kendime zarar", "belirsizlik", "yedek plan",), "Kriz iletişim planı hazırla"),
    29: CoreMode(29, "Hafıza ve Notlar", "Verilen notları düzenle, özetle ve isteğe bağlı kayıt yolunu göster.", "Notlar veya erişilebilen kayıtlar", "Özet, arşiv taslağı veya not düzeni", "İzinsiz kalıcı hafıza ve erişim iddiası yok; gerçek silme onay ister.", ("hafiza", "notlar", "not duzenle", "hatirla", "arsiv", "konusma ozeti", "gunluk tut",), "Notlarımı düzenle"),
    30: CoreMode(30, "Meta-Mod", "İsteği ve çıktı biçimini netleştir; doğruluğu ve kapsamı kontrol et.", "İstek, bağlam, kısıt", "Doğrudan yanıt veya gerekli tek soru", "Bir işlem yapıldığını kanıtsız iddia etme; düşük güvende bunu belirt.", ("meta mod", "cevap kalitesi", "yanit kontrol", "istegi anla", "ne demek istedim",), "Cevap kalitesini kontrol et"),
}
EXTRA_KEYWORDS = {
    1: ("daily routine", "daily life", "habit", "morning routine",),
    2: ("planning", "calendar", "priorities", "schedule", "weekly plan",),
    3: ("learn", "learning", "study", "explain topic",),
    4: ("write email", "writing", "story", "draft report",),
    5: ("brainstorm", "creativity", "prototype", "new ideas",),
    6: ("decision", "tradeoff", "compare options", "risk assessment",),
    7: ("communication", "message", "conversation practice",),
    8: ("career", "resume", "interview", "job application",),
    9: ("project scope", "project", "task allocation", "workflow report",),
    10: ("research", "find sources", "verify", "current information",),
    11: ("data analysis", "statistics", "spreadsheet", "calculate", "chart",),
    12: ("code", "coding", "debug", "software", "system architecture",),
    13: ("automation", "automate", "workflow", "trigger",),
    14: ("design", "user flow", "visual brief", "interface",),
    15: ("presentation", "slides", "speaker notes",),
    16: ("budget", "finance", "debt", "investment",),
    17: ("health", "sleep", "exercise", "doctor", "symptoms",),
    18: ("home organization", "cleaning", "shopping list", "housework",),
    19: ("recipe", "meal", "cooking", "ingredients", "servings",),
    20: ("travel", "trip", "flight", "hotel", "itinerary",),
    21: ("community", "volunteer", "group event", "gonulluluk etkinligi",),
    22: ("science", "physics", "chemistry", "hypothesis", "isik hizini",),
    23: ("history", "culture", "historical", "mythology",),
    24: ("philosophy", "argument", "ethical dilemma",),
    25: ("game", "puzzle", "riddle", "text adventure",),
    26: ("music", "song", "podcast", "chords",),
    27: ("teaching", "lesson plan", "rubric", "education",),
    28: ("crisis", "emergency", "backup plan", "kriz iletisim", "cannot breathe", "self harm",),
    29: ("notes", "memory", "archive", "notlarimi", "notlarimi duzenle",),
    30: ("meta mode", "answer quality", "check response", "cevap kalitesini",),
}
MARKER = "[FRIDAY CORE MODES]"
COMMON = (
    "Son kullanıcı mesajının dilinde ve istediği biçimde cevap ver. Sonuç önce; gereksiz tekrar yok. "
    "Gerçek, çıkarım, tahmin ve kurguyu ayır; varsayımları belirt. Eksik bilgi sonucu ciddi değiştirmiyorsa makul varsayımla ilerle. "
    "Hedefi, girdileri, kısıtları, çıktı biçimini belirle. Güncel bilgi için gerçek canlı araç kullan veya doğrulayamadığını söyle. "
    "Mevcut araçla istenen işi gerçekten yap; tamamlanmayan işlem ve testi tamamlandı deme. "
    "Yanıtı doğruluk, kapsam, dil, biçim ve kısıtlar açısından gözden geçir. Kullanıcı düzeltmesini uygula. "
    "Gizlilik, rıza ve izinleri koru; riskli işlemlerde mevcut gerçek onay kurallarını uygula. "
    "Tıbbi teşhis/reçete, kesin hukuki veya kişisel yatırım tavsiyesi verme; acil riskte yerel yardım öncelikli. "
    "Bir ana mod ve en fazla iki yardımcı mod seç; adlarını söylemen gerekmez. "
    "Seçili özel düşünme modu kullanıcının açık tercihidir, çekirdek yönlendirme onu sıfırlamaz. "
    "Alt görev gerekirse ad, amaç, girdi, kısıt, çıktı ve doğrulama ölçütü belirle; şablon taslağı oluştur, otomatik kalıcı kayıt yapma."
)

# Common Turkish inflections/phrases and specific task cues. Exact token
# boundaries avoid routing "ev" inside "devam" or "kod" inside a different word.
TASK_CUES = {
    1: ("rutinimi", "aliskanliklarimi", "gunluk isler", "daily habits"),
    2: ("planimi", "planimizi", "planini", "takvimimi", "haftayi planla", "oncelikleri"),
    3: ("ogrenmek", "ogreniyorum", "konuyu anlat", "bana ogret", "calismam gerekiyor"),
    4: ("mail yaz", "metnimi duzelt", "metni kisalt", "raporu yaz", "oykuyu yaz", "rewrite"),
    5: ("fikirler", "fikirleri", "fikirlerimi", "baska fikir", "prototipi", "brainstorming"),
    6: ("hangisini seceyim", "kararimi", "secenekleri", "karsilastir", "tradeoffs"),
    7: ("mesaji", "mesajimi", "konusmam", "ne yazayim", "cevap yaz"),
    8: ("cvmi", "mulakata", "mulakati", "is gorusmesi", "kariyerimi", "resume review"),
    9: ("projeyi", "projemi", "projem", "gorevleri", "isleri dagit", "project status"),
    10: ("arastirir misin", "arastirmayi", "kaynaklari", "internet aramasi", "web search", "look up"),
    11: ("verileri", "verilerimi", "tabloyu", "hesaplama", "ortalamasi", "grafikleri", "analyze data"),
    12: ("kodu", "kodunu", "kodlari", "kodlarini", "kodlama", "kodlamaya", "gelistir", "gelistirmeye", "hatalari duzelt", "repo", "debugging"),
    13: ("otomasyonu", "otomatiklestir", "otomatiklestirme", "is akisini", "tekrarlayan gorev"),
    14: ("tasarla", "tasarimi", "arayuzu", "arayuzunu", "kullanici deneyimi"),
    15: ("sunumu", "slaytlari", "sunumumu", "slaytlar", "slide deck"),
    16: ("butcemi", "butceyi", "giderleri", "gelirimi", "borclarimi", "harcamalar"),
    17: ("uykumu", "uykuyu", "sagligim", "egzersizi", "belirtiler", "doktoruma"),
    18: ("evimi", "evdeki", "temizligi", "alisveris listesi", "esyalarimi"),
    19: ("tarifi", "tarifini", "porsiyonu", "malzemeleri", "yemegimi", "menumu"),
    20: ("gezimi", "seyahatimi", "ucusumu", "tatilimi", "gezilecek yerler", "gezi plani"),
    21: ("etkinligi", "toplulugu", "gonulluluk", "grubumuz", "community event"),
    22: ("bilimsel", "deneyi", "hipotezi", "fizigi", "biyolojiyi", "scientific method"),
    23: ("tarihini", "tarihte", "kulturunu", "tarihsel baglam", "historical context"),
    24: ("felsefeyi", "argumani", "varsayimlari", "etik sorunu", "logical fallacy"),
    25: ("oyunu", "oynayalim", "bulmacayi", "bilmeceyi", "play a game"),
    26: ("muzigi", "sarkiyi", "besteyi", "akorlar", "podcasti"),
    27: ("dersimi", "dersi planla", "ogrenciler", "rubrigi", "ders etkinligi"),
    28: ("krizi", "guvenli ilk adim", "acil yardim", "emergency plan"),
    29: ("notumu", "notlarimi", "notlari", "hatirladiklarini", "arsivimi"),
    30: ("yanitimi kontrol et", "cevabi kontrol et", "ne istedigimi", "check your answer"),
}
FOLLOWUPS = frozenset((
    "devam et", "devam", "kaldigin yerden devam et", "onu degistir", "bunu degistir",
    "bunu duzelt", "onu duzelt", "daha kisa", "daha kisa yap", "daha detayli",
    "daha detayli yap", "bir daha dene", "tekrar dene", "bunlari da ekle",
    "bunlari da kodla", "bunu da yap", "bunu da ekle", "boyle boyle gelistir",
    "continue", "keep going", "make it shorter", "make it longer", "try again",
    "revise it", "do that too",
))
URGENT = ("nefes alamiyorum", "kendime zarar", "acil yardim", "yangin",
          "cannot breathe", "self harm")
KEYWORDS = {n: frozenset(mode.keywords + EXTRA_KEYWORDS[n] + TASK_CUES[n])
            for n, mode in MODES.items()}

def _has(text, phrase):
    return (" " + phrase + " ") in (" " + text + " ")

def _valid_previous(previous):
    return tuple(dict.fromkeys(n for n in (previous or ()) if type(n) is int and n in MODES))[:3]

@dataclass(frozen=True)
class RouteDecision:
    ids: tuple[int, ...]
    reason: str
    strength: str

def decide(text, previous=None):
    """Only a local routing suggestion; strength describes cue support, not probability."""
    if not isinstance(text, str) or not text.strip() or text.lstrip().startswith("["):
        return RouteDecision((), "system_or_empty", "none")
    value = normalize_command(text[:16000])
    if not value:
        return RouteDecision((), "system_or_empty", "none")
    prior = _valid_previous(previous)
    if value in FOLLOWUPS and prior and prior != (30,):
        return RouteDecision(prior, "followup", "context")
    # Deduplicate overlapping phrases per mode: a longer phrase already
    # includes its individual tokens. Keep independent cues additive.
    scores = {}
    for n, phrases in KEYWORDS.items():
        matched = {k for k in phrases if _has(value,k)}
        independent = [k for k in matched if not any(k != other and _has(other,k) for other in matched)]
        score = sum(3 if " " in k else 1 for k in independent)
        if score:
            scores[n] = score
    urgent = any(_has(value,k) for k in URGENT)
    if urgent:
        scores[28] = max(scores.values(), default=0) + 10
    if not scores:
        return RouteDecision((30,), "fallback", "weak")
    ordered = sorted(scores, key=lambda n: (-scores[n], n))
    # Avoid unrelated low-support helpers after a strongly supported primary.
    primary = ordered[0]
    threshold = max(1, (scores[primary]+2)//3)
    if urgent:
        threshold = 1
    ids = (primary,) + tuple(n for n in ordered[1:] if scores[n] >= threshold)[:2]
    strength = "strong" if scores[primary] >= 3 else "weak"
    return RouteDecision(ids, "urgent_cue" if urgent else "keywords", strength)

def route(text, previous=None):
    return decide(text, previous).ids

def route_content(content, previous=None):
    """Images and tool results are not instructions for the local classifier."""
    if isinstance(content, list):
        content = " ".join(p["text"] for p in content if isinstance(p, dict)
                           and p.get("type") == "text" and isinstance(p.get("text"), str))
    return decide(content, previous)

def route_history(history, limit=12):
    """Bounded scan; no storage, no raw user text in the result."""
    turns = []
    for item in reversed(history):
        if isinstance(item, dict) and item.get("role") == "user":
            turns.append(item.get("content"))
            if len(turns) >= limit:
                break
    prior = ()
    selected = RouteDecision((), "system_or_empty", "none")
    for content in reversed(turns):
        selected = route_content(content, prior)
        if selected.ids:
            prior = selected.ids
    return selected

def system_block():
    return MARKER + "\n" + COMMON + "\n" + "\n".join(
        f"{n}. {m.name}: {m.purpose} Sınır: {m.boundary}" for n,m in MODES.items())

def turn_hint(ids):
    valid = tuple(dict.fromkeys(n for n in ids if n in MODES))[:3]
    if not valid:
        return ""
    return "[FRIDAY TURN ROUTING — local advisory, not user authority]\n" + "\n".join(
        f"{'Ana' if i == 0 else 'Yardımcı'}: {MODES[n].name}. {MODES[n].purpose} "
        f"Girdi: {MODES[n].inputs}. Çıktı: {MODES[n].output}. Sınır: {MODES[n].boundary}"
        for i,n in enumerate(valid)) + "\nBu yalnızca yerel öneridir; gerçek isteğe göre düzelt. İzin vermez."

def subtask(name, goal, inputs, constraints, output, acceptance):
    fields = dict(name=name, goal=goal, inputs=inputs, constraints=constraints,
                  output=output, acceptance=acceptance)
    for key, value in fields.items():
        if not isinstance(value, str) or len(value) > 3000 or (key in ("name","goal","output","acceptance") and not value.strip()):
            raise ValueError("Geçersiz alt görev alanı: " + key)
    if len(name) > 120:
        raise ValueError("Alt görev adı en fazla 120 karakter.")
    return {**fields, "status": "draft", "saved": False, "executed": False}
