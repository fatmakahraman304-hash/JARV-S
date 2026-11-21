"""NVIDIA Build / NIM API: MAYK'ın güvenli kodlama yedeği.

Ücretsiz API anahtarı bir kullanım kotası garantisi değildir. NVIDIA Build
deneme erişimindeki sınırlar model/hesaba göre değişir; sayısal kota veya
kalan kredi miktarı bu kod tarafından uydurulmaz. 429/402/403 yanıtında
MAYK sıradaki modele geçebilir.

Gizli anahtar yalnızca kullanıcının yerel kayıtlı sağlayıcı ayarlarından
veya ortam değişkeninden okunur; GitHub, günlükler ve model istemleri
içine hiçbir zaman yerleştirilmez.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

BASE_URL = "https://integrate.api.nvidia.com/v1"
# NVIDIA Build üzerinde ücretsiz uç noktası doğrulanmış, kodlama ve araç
# çağrısı için uygun modeller. Gerçekte kullanılabilir modeller API'den
# ayrıca kontrol edilir; bir hesapta bulunmayan model zorlanmaz.
PREFERRED_MODELS = (
    "z-ai/glm-5.3-flash",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "stepfun-ai/step-5-preview",
)
_CACHE_TTL = 30 * 60
_LOCK = threading.Lock()
_CACHE: dict = {"key": None, "at": 0., "models": None, "reason": None}


def api_key() -> str:
    """Önce MAYK'ın kayıtlı NVIDIA sağlayıcısı, sonra gizli ortam anahtarı."""
    from memory.config_manager import get_plugin_config, get_providers
    config = get_plugin_config("coding")
    key = str(config.get("nvidia_key") or "").strip()
    if key:
        return key
    creds = get_providers().get("creds") or {}
    if isinstance(creds, dict):
        for provider_id, value in creds.items():
            if not isinstance(value, dict):
                continue
            if provider_id == "openai_compat@nvidia" or (
                provider_id == "openai_compat" and value.get("catalog") == "nvidia"
            ):
                found = str(value.get("api_key") or "").strip()
                if found:
                    return found
    return (os.environ.get("NVIDIA_API_KEY") or
            os.environ.get("NVIDIA_NIM_API_KEY") or "").strip()


def _get_models(key: str, *, refresh: bool = False) -> tuple[list[str] | None, str]:
    """NVIDIA /models sonucu. None = ağ/izin hatası; [] = boş liste."""
    if not key:
        return [], "missing"
    now = time.monotonic()
    with _LOCK:
        if (not refresh and _CACHE["key"] == key
                and _CACHE["models"] is not None
                and now - _CACHE["at"] < _CACHE_TTL):
            return list(_CACHE["models"]), str(_CACHE["reason"])
    req = urllib.request.Request(
        f"{BASE_URL}/models", method="GET",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            result = json.loads(response.read(512_000).decode("utf-8"))
        items = result.get("data", []) if isinstance(result, dict) else []
        if not isinstance(items, list):
            raise ValueError("Geçersiz model listesi")
        names = [str(item.get("id") or "").strip() for item in items
                 if isinstance(item, dict) and item.get("id")]
        models, reason = list(dict.fromkeys(names)), "ok"
    except urllib.error.HTTPError as exc:
        models, reason = None, ({
            401: "unauthorized", 403: "unauthorized",
            402: "quota", 429: "limit", 404: "unavailable",
        }.get(exc.code, "unavailable"))
    except (OSError, ValueError, TypeError):
        models, reason = None, "unavailable"
    with _LOCK:
        # Geçici hatayı belleğe kalıcı olarak önbellekleme; sonraki iş deneyebilir.
        _CACHE.update(key=key, at=now,
                      models=models if models is not None else None,
                      reason=reason)
    return (list(models) if models is not None else None), reason


def available_models(key: str | None = None, *, refresh: bool = False) -> list[str]:
    """Seçili kodlama modelleri; gerçek model listesi varsa ona göre süzülür."""
    key = (key if key is not None else api_key()).strip()
    if not key:
        return []
    from memory.config_manager import get_plugin_config, get_provider_config
    coding = get_plugin_config("coding")
    selected = coding.get("nvidia_models")
    if isinstance(selected, str):
        selected = [selected]
    chosen = [str(m).strip() for m in selected] if isinstance(selected, (list, tuple)) else []
    configured = str(get_provider_config("openai_compat@nvidia").get("model") or "").strip()
    preferred = list(dict.fromkeys(
        [m for m in chosen + ([configured] if configured else []) + list(PREFERRED_MODELS)
         if re.fullmatch(r"[A-Za-z0-9_.:/+-]{3,120}", m)
    ))
    listing, reason = _get_models(key, refresh=refresh)
    if listing is not None:
        allowed = set(listing)
        preferred = [model for model in preferred if model in allowed]
        # Yeni/yeniden adlandırılan kodlama modellerini katalogda bul.
        if not preferred and listing:
            coding_hints = ("coder", "glm", "nemotron", "kimi", "step", "mistral")
            discovered = [x for x in listing
                          if any(hint in x.casefold() for hint in coding_hints)
                          and re.fullmatch(r"[A-Za-z0-9_.:/+-]{3,120}", x)]
            preferred = discovered[:3]
        return preferred[:3]
    # 401/403/402/429: başarılı olamayacak isteği üretme. Ağ geçici olarak
    # kapalıysa daha önce doğrulanmış katalogdaki modeller denenebilir.
    if reason in ("unauthorized", "quota", "limit"):
        return []
    return preferred[:3]


def status_text() -> str:
    key = api_key()
    if not key:
        return ("NVIDIA API anahtarı henüz MAYK'a eklenmedi. "
                "Motor ve Sağlayıcılar → Kodlama → NVIDIA alanından ekleyin.")
    listing, reason = _get_models(key, refresh=True)
    if reason == "unauthorized":
        return "NVIDIA anahtarı reddedildi. Yerel ayarlardaki anahtarı kontrol edin."
    if reason == "quota":
        return "NVIDIA deneme kotası/erişim hakkı yetersiz. Gemini yedek olarak kullanılacak."
    if reason == "limit":
        return "NVIDIA API hız sınırında (429). Sınır yenilenene kadar Gemini kullanılacak."
    if reason != "ok":
        return "NVIDIA anahtarı kayıtlı, ancak API bağlantısı şu anda doğrulanamıyor."
    selected = available_models(key)
    if not selected:
        return "NVIDIA bağlantısı başarılı, ancak kodlamaya uygun model seçilemedi."
    return ("NVIDIA API erişimi doğrulandı. Kodlama modelleri: " +
            " → ".join(selected) +
            ". Kalan ücretsiz istek sayısı NVIDIA tarafından bu uç noktada sağlanmıyor.")


def complete_text(prompt: str, *, model: str | None = None) -> str:
    """MAYK'ın araçsız kodlama yolu için OpenAI uyumlu NVIDIA isteği."""
    key = api_key()
    if not key:
        raise RuntimeError("NVIDIA API anahtarı bulunamadı.")
    models = available_models(key)
    chosen = model or (models[0] if models else "")
    if not chosen:
        raise RuntimeError("NVIDIA 429 veya erişilebilir kodlama modeli bulunamadı.")
    payload = {
        "model": chosen,
        "messages": [
            {"role": "system", "content":
             "Sen MAYK'ın kodlama asistanısın. Kod üret, gerekçelendir ve Türkçe yanıt ver."},
            {"role": "user", "content": str(prompt)},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            answer = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        explanation = {
            401: "Anahtar geçersiz", 403: "İzin reddedildi",
            402: "Deneme kotası yetersiz", 404: "Model kullanılamıyor",
            429: "Kullanım sınırı", 500: "Sunucu hatası",
            502: "Sunucu hatası", 503: "Sunucu meşgul",
            504: "Zaman aşımı",
        }.get(exc.code, "İstek başarısız")
        # API'nin gönderdiği ham hata gövdesini göstermeyerek anahtar sızıntısını engelle.
        raise RuntimeError(f"NVIDIA {exc.code}: {explanation}") from None
    except (OSError, ValueError, TypeError):
        raise RuntimeError("NVIDIA API yanıtına ulaşılamadı.") from None
    options = answer.get("choices") or []
    text = (options[0].get("message") or {}).get("content") if options else None
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("NVIDIA API boş yanıt verdi.")
    return text.strip()
