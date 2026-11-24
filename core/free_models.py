"""Opt-in multi-provider pool for background text and the built-in code agent.

Only fixed, documented endpoints and model IDs are used automatically. A
provider's free account/credit settings still determine actual billing.
Credentials stay in config_manager; no prompts or secrets are kept in metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
import re

PREFIX = "prov:free:"
BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "aether": "https://api.aetherapi.dev/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}
FAST = (
    ("groq", "openai/gpt-oss-20b"),
    ("cloudflare", "@cf/openai/gpt-oss-20b"),
    ("groq", "qwen/qwen3.8-27b"),
    ("groq", "openai/gpt-oss-120b"),
    ("aether", "qwen3.8-35b-a3b-free"),
    ("openrouter", "openrouter/free"),
)
SMART = (
    ("groq", "openai/gpt-oss-120b"),
    ("cloudflare", "@cf/openai/gpt-oss-120b"),
    ("groq", "qwen/qwen3.8-27b"),
    ("aether", "qwen3.8-27b-free"),
    ("groq", "openai/gpt-oss-20b"),
    ("openrouter", "openrouter/free"),
)
CODING = (
    ("groq", "openai/gpt-oss-120b"),
    ("cloudflare", "@cf/openai/gpt-oss-120b"),
    ("groq", "qwen/qwen3.8-27b"),
    ("aether", "minimax-m3-free"),
    ("openrouter", "openrouter/free"),
)
GEMINI_TEXT = ("gemini-4-hydrogen", "gemini-3.8-flash",
               "gemini-3.5-flash-lite", "gemini-3.5-flash",
               "gemini-3.1-flash-lite", "gemini-2.5-flash",
               "gemini-2.5-flash-lite")


def cloudflare_base(value):
    """Accept only the official account-specific API base (or account ID)."""
    value = str(value or "").strip().rstrip("/")
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        value = "https://api.cloudflare.com/client/v4/accounts/" + value + "/ai/v1"
    if re.fullmatch(r"https://api\.cloudflare\.com/client/v4/accounts/[0-9a-fA-F]{32}/ai/v1", value):
        return value
    return ""


def settings():
    from memory.config_manager import get_providers
    return get_providers()


def enabled(block=None):
    if block is None:
        block = settings()
    return block.get("free_multi") is True


def specs(role="smart", block=None):
    """(provider, model, endpoint, key) in role order; never discover paid IDs."""
    if block is None:
        block = settings()
    if not enabled(block):
        return []
    creds = block.get("creds") or {}
    out = []
    for provider, model in {"fast": FAST, "coding": CODING}.get(role, SMART):
        cfg = creds.get("openai_compat@" + provider) or {}
        key = str(cfg.get("api_key") or "").strip()
        if provider == "cloudflare":
            base = cloudflare_base(cfg.get("base_url"))
        else:
            base = str(cfg.get("base_url") or BASES[provider]).rstrip("/")
            if base != BASES[provider]:
                base = ""
        if key and base:
            out.append((provider, model, base, key))
    cfg = creds.get("openai_compat@ollama") or {}
    base = str(cfg.get("base_url") or BASES["ollama"]).rstrip("/")
    model = str(cfg.get("model") or "").strip()
    if model and base == BASES["ollama"]:
        out.append(("ollama", model, base, ""))
    return out


def rung(spec):
    return PREFIX + spec[0] + ":" + spec[1]


def text_only(contents):
    # Conservative: do not route binary, image, or SDK content objects to
    # text-only models. Existing Gemini path retains its media capabilities.
    return isinstance(contents, str) or (
        isinstance(contents, (list, tuple)) and
        all(isinstance(item, str) for item in contents))


_lock = threading.Lock()
_day = ""
_usage = {}


def record_usage(base, model, usage):
    if not isinstance(usage, dict):
        return
    provider = ("cloudflare" if cloudflare_base(base) else
                next((p for p, url in BASES.items() if url == base), None))
    if provider is None:
        return
    def count(key):
        try:
            return max(0, int(usage.get(key) or 0))
        except (TypeError, ValueError, OverflowError):
            return 0
    total = count("total_tokens") or count("prompt_tokens") + count("completion_tokens")
    with _lock:
        _roll_day()
        row = _usage.setdefault(provider + ":" + model, {"requests": 0, "tokens": 0})
        row["requests"] += 1
        row["tokens"] += total


def _roll_day():
    global _day
    today = datetime.now(timezone.utc).date().isoformat()
    if _day != today:
        _usage.clear()
        _day = today


def usage_report():
    """Provider-reported tokens in this process since UTC midnight."""
    with _lock:
        _roll_day()
        return {key: dict(value) for key, value in _usage.items()}
