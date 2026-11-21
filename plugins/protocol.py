"""
Protokoller — Iron Man'deki gibi tek komutla birçok iş: "çalışma protokolü",
"film modu", "uyku protokolü", "günaydın".

Bir protokol, sırayla yapılacak adımların listesidir. Çalıştırınca Mayk
adımları kendi araçlarıyla tek tek yapar: uygulama açar, sesi ayarlar, TV'ye ya
da telefona gönderir (send_to_device), hatırlatıcı kurar, listeyi okur…
Protokoller ortak hafızada (preferences / "protokol: <ad>") durur, yani
telefonda kaydedilen bir protokolü bilgisayar da bilir; web uygulamasındaki
`protocol` aracı aynı biçimi ve aynı hazır protokolleri kullanır (web/app.js
PROTOCOLS). İleride akıllı ampul/priz eklenince adımlara onlar da yazılır.
"""

PLUGIN = {
    "name": "protocol",
    "description": (
        "Protokoller: tek komutla sırayla birçok iş (Iron Man tarzı). 'çalışma protokolünü başlat', "
        "'film moduna geç', 'uyku protokolü', 'günaydın protokolü', 'protokollerim neler', "
        "'yeni protokol kaydet: eve geldim = ...'. action: run | list | save | delete. "
        "run sonucu bir adım listesi döner: o adımları sırayla kendi araçlarınla yap."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "run | list | save | delete"},
            "name": {"type": "STRING", "description": "protokolün adı: çalışma, film, uyku, sabah …"},
            "steps": {"type": "ARRAY", "items": {"type": "STRING"},
                      "description": "save için sırayla yapılacak adımlar, her biri tek cümle"},
        },
        "required": ["action"],
    },
}

PREFIX = "protokol: "
MAX_TEXT = 370          # shared memory keeps up to 380 characters a value

# Ready-made protocols. Same names and steps as PROTOCOLS in web/app.js.
DEFAULTS = {
    "sabah": [
        "Günaydın de; bugünün tarihini ve Google aramasıyla bulunduğun yerin hava durumunu kısaca söyle",
        "Bugünün hatırlatıcılarını ve yapılacaklar listesini oku",
        "Yarım kalan proje varsa durumunu tek cümleyle söyle",
    ],
    "çalışma": [
        "Bilgisayarda çalan müziği durdur ve sesi yüzde 20'ye indir",
        "Yapılacaklar listesini oku ve hangisiyle başlamak istediğini sor",
        "45 dakika sonrasına 'mola ver' hatırlatıcısı kur",
    ],
    "film": [
        "Televizyonda YouTube'u aç (send_to_device, open); ne izlemek istediğini sor",
        "Bilgisayarda çalan müziği durdur",
        "Film bitince haber vermek için süre isterse hatırlatıcı kur",
    ],
    "akşam": [
        "Bugün bütün cihazlarda neler konuştuğumuzu ve yapılanları arşivden kısaca özetle",
        "Biten yapılacakları sor, bitenleri listeden çıkar",
        "Yarının hatırlatıcılarını söyle ve eklenecek bir şey var mı sor",
    ],
    "uyku": [
        "Yarının hatırlatıcılarını ve yapılacakları kısaca söyle",
        "Sabah için hatırlatıcı/alarm isteyip istemediğini sor, isterse kur",
        "İyi geceler de ve bilgisayarı kilitle",
    ],
}

_ALIASES = {"günaydın": "sabah", "sabah": "sabah", "çalış": "çalışma", "iş": "çalışma", "odak": "çalışma",
            "akşam": "akşam", "gün sonu": "akşam", "film": "film", "sinema": "film", "dizi": "film", "uyku": "uyku", "gece": "uyku", "yat": "uyku"}


def _norm(name: str) -> str:
    n = " ".join(str(name or "").casefold().replace("protokolü", "").replace("protokol", "")
                 .replace("moduna", "").replace("modu", "").split())
    return n.strip(" -:")


def _saved() -> dict[str, list[str]]:
    from memory.memory_manager import load_memory
    prefs = (load_memory() or {}).get("preferences", {}) or {}
    out = {}
    for k, v in prefs.items():
        if isinstance(k, str) and k.startswith(PREFIX):
            val = v.get("value", "") if isinstance(v, dict) else str(v)
            out[k[len(PREFIX):]] = [s.strip() for s in str(val).split("|") if s.strip()]
    return out


def find(name: str) -> tuple[str, list[str]] | None:
    n = _norm(name)
    if not n:
        return None
    saved = _saved()
    if n in saved:
        return n, saved[n]
    for key, steps in saved.items():
        if n in key or key in n:
            return key, steps
    base = _ALIASES.get(n) or next((v for k, v in _ALIASES.items() if k in n), None)
    if base:
        return base, saved.get(base) or DEFAULTS[base]
    return None


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from memory import memory_manager as mm
        p = parameters or {}
        action = str(p.get("action") or "run").strip().lower()
        name = str(p.get("name") or "").strip()
        if action == "list":
            names = dict.fromkeys(list(DEFAULTS) + list(_saved()))
            return "Protokoller: " + ", ".join(names) + ". Hangisini başlatayım?"
        if action == "save":
            steps = [str(s).strip() for s in (p.get("steps") or []) if str(s).strip()]
            key = _norm(name)
            if not key or not steps:
                return "Protokolün adı ve adımları lazım."
            text = " | ".join(steps)
            if len(text) > MAX_TEXT:
                return "Bu protokol çok uzun; adımları kısalt ya da ikiye böl (en fazla 370 harf)."
            mm.remember(PREFIX + key, text, "preferences")
            return f"'{key}' protokolü kaydedildi ({len(steps)} adım); bütün cihazlar biliyor."
        if action == "delete":
            key = _norm(name)
            if key in _saved():
                mm.forget(PREFIX + key, "preferences")
                return f"'{key}' protokolü silindi." + (" Hazır sürümü yine kullanılabilir." if key in DEFAULTS else "")
            return "Böyle kayıtlı bir protokol yok."
        hit = find(name)
        if not hit:
            return (f"'{name}' diye bir protokol yok. Var olanlar: {', '.join(dict.fromkeys(list(DEFAULTS) + list(_saved())))}. "
                    "İstersen adımlarını söyle, kaydedeyim.")
        key, steps = hit
        if player:
            try:
                player.write_log(f"Mayk: {key.upper()} PROTOKOLÜ başladı")
            except Exception:
                pass
        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        return (f"{key.upper()} PROTOKOLÜ BAŞLADI. Şimdi bu adımları sırayla, kendi araçlarınla yap; "
                f"yapamadığın adımı atla ve sonunda kullanıcıya ne yaptığını kısaca söyle:\n{numbered}")
    except Exception as exc:
        return f"Protokol çalıştırılamadı: {exc}"
