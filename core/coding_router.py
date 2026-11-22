"""AETHER kodlama sırası: NVIDIA Build → Gemini.

Eski Claude Code ve Codex CLI kodlama rotasında bulunmaz.
Kota veya bağlantı hatasında sıradaki model devralır; dinlenme süreleri
geçtiğinde ilk tercih tekrar denenebilir. Teknik sağlayıcı kimlikleri korunur.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core import aether_agent

BASE_DIR = Path(__file__).resolve().parent.parent
_COOL_FILE = BASE_DIR / "config" / "coding_cooldown.json"
LIMIT_REST = 60 * 60           # usage limit: try the best again after an hour
DOWN_REST = 15 * 60            # signed out / not installed / would not start
GEMINI = ""                    # the Gemini ladder (never rests)

AGENTS = (aether_agent.PROVIDER_ID,)
NAMES = {aether_agent.PROVIDER_ID: "AETHER kod ajanı (NVIDIA → Gemini)",
         GEMINI: "Gemini"}

_lock = threading.Lock()


def name(provider: str) -> str:
    return NAMES.get(provider) or provider.partition("@")[2] or provider or "Gemini"


def _load() -> dict:
    try:
        data = json.loads(_COOL_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        _COOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOL_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def resting(provider: str, now: float | None = None) -> float:
    """Seconds left of this provider's rest, or 0."""
    if provider == GEMINI:
        return 0.0
    now = time.time() if now is None else now
    with _lock:
        until = float((_load().get(provider) or {}).get("until", 0))
    return max(0.0, until - now)


def is_limit(err) -> bool:
    s = str(err).casefold()
    return any(w in s for w in ("kullanım sınır", "usage limit", "rate limit", "429", "quota",
                                "resource_exhausted", "too many requests", "limit reached",
                                "insufficient balance", "402", "bakiye yetersiz",
                                "limitine", "sınırına ulaş"))


def is_unavailable(err) -> bool:
    s = str(err).casefold()
    return any(w in s for w in ("oturum", "not logged in", "login", "401", "bulunamadı",
                                "başlatılamadı", "not found", "unauthorized", "sürümü eski",
                                "desteklemiyor", "zaman aşımı", "süre sınırını", "timeout",
                                "404", "403", "500", "502", "503", "504",
                                "server overloaded", "network", "bağlantı hatası",
                                "ulaşılamadı", "kullanılamadı", "boş yanıt",
                                "yanıt vermedi", "every model on the ladder failed"))


def should_switch(err) -> bool:
    """Is this a failure another model can get past (as opposed to a bad request)?"""
    return is_limit(err) or is_unavailable(err)


def rest(provider: str, err) -> float:
    """Put a provider to rest after `err`. Returns the seconds it rests."""
    if provider == GEMINI:
        return 0.0
    secs = LIMIT_REST if is_limit(err) else DOWN_REST
    with _lock:
        data = _load()
        data[provider] = {"until": time.time() + secs, "why": str(err)[:200]}
        _save(data)
    return secs


def ladder(chosen: str = "", installed=None) -> list[str]:
    """NVIDIA destekli AETHER kod ajanı ilk sırada; eski CLI ajanları yok."""
    if installed is None:
        from core import agent_coding
        installed = agent_coding.available
    order = [p for p in AGENTS if installed(p) and not resting(p)]
    # Kullanıcı alternatif bir API modeli seçmişse yedek olarak kullanılabilir,
    # ancak kaldırılan eski abonelik/CLI kod ajanları geri yüklenmez.
    old_agents = {"claude_code", "codex_cli", "openai_compat@deepseek"}
    if chosen and chosen not in old_agents and chosen not in AGENTS and chosen != "auto":
        if chosen not in order and not resting(chosen):
            order.append(chosen)
    return order + [GEMINI]


def status_line(chosen: str = "") -> str:
    """Model bekleme süreleri; kalan API bakiyesi gizli tutulur."""
    parts = []
    for p in list(AGENTS) + ([chosen] if chosen and chosen not in AGENTS else []):
        if p in {"claude_code", "codex_cli", "openai_compat@deepseek"}:
            continue
        left = resting(p)
        if left:
            parts.append(f"{name(p)} (sınır nedeniyle {int(left // 60) + 1} dk beklemede)")
    return ", ".join(parts)
