"""Official platform destinations and explicit open commands."""

import re

SITES = {
    "whatsapp": ("WhatsApp", "https://web.whatsapp.com/", {"web.whatsapp.com"}),
    "facebook": ("Facebook", "https://www.facebook.com/", {"facebook.com", "www.facebook.com", "m.facebook.com"}),
    "tiktok": ("TikTok", "https://www.tiktok.com/", {"tiktok.com", "www.tiktok.com"}),
    "instagram": ("Instagram", "https://www.instagram.com/", {"instagram.com", "www.instagram.com"}),
    "github": ("GitHub", "https://github.com/", {"github.com", "www.github.com"}),
    "claude": ("Claude", "https://claude.ai/", {"claude.ai", "www.claude.ai"}),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/", {
        "chatgpt.com", "www.chatgpt.com", "chat.openai.com",
        "auth.openai.com", "auth0.openai.com", "setup.auth.openai.com",
    }),
}

_ALIASES = {
    "wp": "whatsapp",
    "whats": "whatsapp",
    "whatsab": "whatsapp",
    "ig": "instagram",
    "chatgbt": "chatgpt",
}
_OPEN_COMMAND = re.compile(
    r"(.+?)(?: (?:ortada|jarvis['’]te|jarvis içinde))? aç"
)


def site_for_name(name: str) -> str | None:
    key = re.sub(r"[\s.'’\-]", "", name.replace("İ", "i").casefold())
    key = _ALIASES.get(key, key)
    return key if key in SITES else None


def site_for_command(text: str) -> str | None:
    words = " ".join(text.strip().replace("İ", "i").casefold().split()).rstrip(".!")
    words = re.sub(r"^(?:jarvis|friday)[, ]+", "", words)
    match = _OPEN_COMMAND.fullmatch(words)
    if not match:
        return None
    name = match[1]
    site = site_for_name(name)
    if site:
        return site
    return site_for_name(re.sub(r"['’]?y?[ıiuü]$", "", name))


CHAT_HOSTS = {
    "chatgpt": frozenset({"chatgpt.com", "www.chatgpt.com"}),
    "claude": frozenset({"claude.ai", "www.claude.ai"}),
}
CHAT_DRAFT_LIMIT = 8000
_CHAT_DRAFT_COMMAND = re.compile(
    r"(?:(?:jarvis|friday)[, ]+)?"
    r"(?:(chat\s*g[pb]t|claude)(?:['’]?(?:ye|ya|e|a))?\s+|buraya\s+)"
    r"(?:şunu\s+)?yaz(?:\s*:\s*|\s+)(.+)",
    re.IGNORECASE | re.DOTALL,
)


def chat_draft_command(text: str) -> tuple[str, str] | None:
    match = _CHAT_DRAFT_COMMAND.fullmatch(text.strip())
    if match:
        target, draft = match.groups()
        return (site_for_name(target) if target else "", draft.strip())
    return None
