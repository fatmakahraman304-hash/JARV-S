"""MAYK kodlama ajanı için DeepSeek anahtarı ve bakiye durumu.

Anahtar günlük, hata veya ekranda gösterilmez.
Kodlama ayarı, DeepSeek sağlayıcısı veya ortam değişkeni desteklenir.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"
_BALANCE_TTL = 60
_lock = threading.Lock()
_cache = {"key": None, "at": 0.0, "result": None}


def api_key() -> str:
    """Kullanıcının bilgisayarındaki kayıtlı DeepSeek anahtarını bul."""
    from memory.config_manager import get_plugin_config, get_providers, load_api_keys
    coding = get_plugin_config("coding")
    direct = str(coding.get("deepseek_key") or "").strip()
    if direct:
        return direct
    creds = get_providers().get("creds") or {}
    if isinstance(creds, dict):
        for pid, cfg in creds.items():
            if not isinstance(cfg, dict):
                continue
            if pid == "openai_compat@deepseek" or (
                pid == "openai_compat" and cfg.get("catalog") == "deepseek"
            ):
                saved = str(cfg.get("api_key") or "").strip()
                if saved:
                    return saved
    legacy = load_api_keys()
    key = str(legacy.get("deepseek_api_key") or legacy.get("deepseek_key") or "").strip()
    return key or os.environ.get("DEEPSEEK_API_KEY", "").strip()


def balance_status(key: str | None = None, *, refresh: bool = False) -> dict:
    """Bakiye durumunu gizli anahtarı göstermeden denetle.

    available=True kullanılabilir; False yetersiz/geçersiz;
    None ağ veya servis hatasında bilinmiyor.
    """
    key = (key if key is not None else api_key()).strip()
    if not key:
        return {"available": False, "reason": "missing", "balances": []}
    now = time.monotonic()
    with _lock:
        if (not refresh and _cache["key"] == key and _cache["result"] is not None
                and now - _cache["at"] < _BALANCE_TTL):
            return dict(_cache["result"])
    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            body = json.loads(response.read(32768).decode("utf-8"))
        if not isinstance(body, dict) or not isinstance(body.get("is_available"), bool):
            result = {"available": None, "reason": "invalid_response", "balances": []}
        else:
            balances = []
            for item in body.get("balance_infos", []):
                if isinstance(item, dict):
                    balances.append({
                        "currency": str(item.get("currency", ""))[:8],
                        "total": str(item.get("total_balance", ""))[:24],
                    })
            result = {"available": body["is_available"],
                      "reason": "ok" if body["is_available"] else "empty",
                      "balances": balances}
    except urllib.error.HTTPError as exc:
        reason = "unauthorized" if exc.code in (401, 403) else (
            "empty" if exc.code == 402 else "unavailable")
        available = False if exc.code in (401, 402, 403) else None
        result = {"available": available, "reason": reason, "balances": []}
    except (OSError, ValueError, TypeError):
        result = {"available": None, "reason": "unavailable", "balances": []}
    with _lock:
        _cache.update(key=key, at=now, result=result)
    return dict(result)


def status_text() -> str:
    key = api_key()
    if not key:
        return "DeepSeek API anahtarı bulunamadı. Kodlamada Gemini kullanılacak."
    info = balance_status(key)
    if info["reason"] == "unauthorized":
        return "DeepSeek anahtarı reddedildi. Anahtarı kontrol edin; Gemini kullanılacak."
    if info["available"] is False:
        return "DeepSeek bakiyesi yetersiz. Bakiye yenilenene kadar Gemini kullanılacak."
    if info["available"] is None:
        return "DeepSeek anahtarı kayıtlı ancak bakiye şu anda doğrulanamadı. İlk kodlama isteğinde bağlantı denenir."
    amounts = ", ".join(f"{x['total']} {x['currency']}" for x in info["balances"] if x["total"])
    return ("DeepSeek kullanılabilir. Kalan bakiye: " + amounts + "."
            if amounts else "DeepSeek kullanılabilir; bakiye tutarı sağlayıcıdan alınamadı.")
