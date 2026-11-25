"""Deny removed services even when old settings use a custom provider ID."""
from urllib.parse import urlsplit

_IDS = frozenset({"abacus", "abacus_ai", "abacusai", "routellm", "route-llm"})


def is_retired_provider(provider_id="", settings=None):
    name = str(provider_id or "").strip().casefold().partition("@")[2] or str(provider_id or "").strip().casefold()
    if name in _IDS:
        return True
    if not isinstance(settings, dict):
        return False
    if str(settings.get("catalog") or "").strip().casefold() in _IDS:
        return True
    address = str(settings.get("base_url") or "").strip()
    try:
        host = (urlsplit(address if "://" in address else "https://" + address).hostname or "").rstrip(".").casefold()
    except ValueError:
        return False
    return host == "abacus.ai" or host.endswith(".abacus.ai")
