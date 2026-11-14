"""Official platform destinations and explicit open commands."""

import re

SITES = {
    "whatsapp": ("WhatsApp", "https://web.whatsapp.com/", {"web.whatsapp.com"}),
    "facebook": ("Facebook", "https://www.facebook.com/", {"facebook.com", "www.facebook.com", "m.facebook.com"}),
    "tiktok": ("TikTok", "https://www.tiktok.com/", {"tiktok.com", "www.tiktok.com"}),
    "instagram": ("Instagram", "https://www.instagram.com/", {"instagram.com", "www.instagram.com"}),
    "github": ("GitHub", "https://github.com/", {"github.com", "www.github.com"}),
    "claude": ("Claude", "https://claude.ai/", {"claude.ai", "www.claude.ai"}),
    "chatgpt": ("ChatGPT", "https://chatgpt.com/", {"chatgpt.com", "www.chatgpt.com", "auth.openai.com"}),
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
    match = _OPEN_COMMAND.fullmatch(words)
    if not match:
        return None
    name = match[1]
    site = site_for_name(name)
    if site:
        return site
    return site_for_name(re.sub(r"(?:['’]y?[ıiuü]|[ıiuü])$", "", name))
