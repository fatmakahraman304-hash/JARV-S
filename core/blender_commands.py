"""Direct routing for explicit Turkish Blender scene creation requests."""
import re
import unicodedata


def scene_command(text):
    original = text.strip()
    if original.startswith("["):
        return None
    explicit = original.split(maxsplit=1)
    shortcut = bool(explicit and explicit[0].lower() == "/blender")
    if shortcut:
        if len(explicit) < 2:
            return None
        original = explicit[1]

    folded = unicodedata.normalize("NFKD", original.casefold().replace("ı", "i"))
    words = "".join(c for c in folded if not unicodedata.combining(c))
    editing = bool(re.search(r"\b(duzenle|degistir|buyut|kucult|dondur|tasi|ekle|kaldir|uzat|kisalt)\b", words))
    project_ref = bool(re.search(r"\b(mevcut|son|bu) (blender )?(proje\w*|sahne\w*)\b", words))
    action = "edit" if editing or project_ref else "new"
    create = re.search(r"\b(olustur|modelle|insa et|tasarla|yap)\b", words)
    if create and not project_ref:
        action = "new"
    if not shortcut:
        # Keep app launches and general questions in the conversation.
        if re.search(r"\?|\b(nasil|nedir|ornegin|ornek komut)\b", words):
            return None
        context = re.search(r"\b(blender|3b|3d)\b", words) or (
            re.search(r"\b(mahalle\w*|sehir|sahne\w*|bina\w*|ev)\b", words)
            and re.search(r"\brender\w*\b", words))
        if not ((create or editing) and context):
            return None

    render = bool(re.search(r"\brender(?:i|ini)?\s+(?:ac|al|goster)\b", words))
    project = bool(re.search(r"\bprojeyi\s+(?:(?:ve\s+)?render(?:i|ini)?\s+)?(?:ac|goster)\b", words))
    result = "both" if project and render else "open" if project else "render" if render else "save"
    return {"action": action, "request": original, "result": result}
