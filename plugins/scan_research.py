"""Research a book or item selected from the latest camera scan."""

PLUGIN = {
    "name": "scan_research",
    "description": (
        "After an explicit request to research an object in the latest camera scan, "
        "show its web research in the HUD. For 'bu kitabı araştır' or 'kitabı yansıt', "
        "omit subject to use the selected title from the scan. For a different item "
        "pass its visible name and set book=false. Use only when the user asks to research."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "subject": {"type": "STRING"},
        "book": {"type": "BOOLEAN"},
    }},
}


def run(parameters, player=None, session_memory=None):
    request = getattr(player, "research_scan", None)
    if not callable(request):
        return "Araştırma için JARVIS masaüstü arayüzü gerekli."
    subject = parameters.get("subject") or ""
    if not isinstance(subject, str) or len(subject) > 180:
        return "Araştırılacak başlığı kısalt."
    request(subject, bool(parameters.get("book", True)))
    return "Araştırma isteği HUD’a gönderildi."
