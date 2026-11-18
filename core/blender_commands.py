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
    if not shortcut:
        # A request to launch the app, a question or an edit belongs to the usual dispatcher.
        if re.search(r"\?|\b(nasil|nedir|ornegin|ornek komut|mevcut|son projede|ekle|degistir)\b", words):
            return None
        create = re.search(r"\b(olustur|modelle|insa et|tasarla|yap)\b", words)
        context = re.search(r"\b(blender|3b|3d)\b", words) or (
            re.search(r"\b(mahalle\w*|sehir|sahne\w*|bina\w*|ev)\b", words)
            and re.search(r"\brender\w*\b", words))
        if not (create and context):
            return None

    render = bool(re.search(r"\brender(?:i|ini)?\s+(?:ac|al|goster)\b", words))
    project = bool(re.search(r"\bprojeyi\s+(?:(?:ve\s+)?render(?:i|ini)?\s+)?(?:ac|goster)\b", words))
    result = "both" if project and render else "open" if project else "render" if render else "save"
    return {"action": "new", "request": original, "result": result}
