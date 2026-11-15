"""Prepare the user's explicit dictation for their selected web chat."""

from core.social_sites import CHAT_DRAFT_LIMIT, CHAT_HOSTS, site_for_name

PLUGIN = {
    "name": "chat_draft",
    "description": (
        "Use only when the user explicitly asks to write or dictate text into the ChatGPT "
        "or Claude web chat. Examples: 'Claude’a şunu yaz: ...', "
        "'ChatGPT’ye yaz: ...', 'buraya yaz: ...' when they mean the active web chat. "
        "Preserve the user's dictated text verbatim. This prepares a draft without sending it. "
        "For browser-based ChatGPT, the draft goes to the clipboard for the user to paste. "
        "For opening a site without dictation, use open_app."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "site": {"type": "STRING", "enum": ["chatgpt", "claude", "active"]},
            "text": {"type": "STRING", "description": "The exact user-dictated text."},
        },
        "required": ["site", "text"],
    },
}


def run(parameters, player=None, session_memory=None):
    target = parameters.get("site", "active")
    text = parameters.get("text")
    if not isinstance(target, str) or not isinstance(text, str) or not text.strip():
        return "Yazılacak metni ve sohbeti belirt."
    if len(text) > CHAT_DRAFT_LIMIT:
        return "Sohbet taslağı en fazla 8.000 karakter olabilir."
    site = "" if target == "active" else site_for_name(target)
    if site is None or (site and site not in CHAT_HOSTS):
        return "ChatGPT veya Claude seç."
    draft = getattr(player, "write_chat_draft", None)
    if not callable(draft):
        return "Sohbet kutusuna yazmak için JARVIS masaüstü arayüzü gerekli."
    draft(site, text)
    return "Sohbet taslağı isteği alındı. Durumu JARVIS’te görebilirsin."
