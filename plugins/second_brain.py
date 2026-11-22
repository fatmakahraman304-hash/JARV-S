"""Voice entry into AETHER's local improvement notebook."""
PLUGIN = {
    "name": "second_brain",
    "description": "Open the İkinci Beyin improvement panel or save the user's explicit AETHER improvement idea. The panel monitors local code-job failures and lets the user select isolated code development.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["open", "add"]},
        "idea": {"type": "STRING"}}, "required": ["action"]}
}


def run(parameters, player=None, session_memory=None):
    try:
        from core import second_brain
        if parameters.get("action") == "add":
            second_brain.add(parameters.get("idea") or "")
            message = "Geliştirme fikri İkinci Beyin’e kaydedildi."
        elif parameters.get("action") == "open":
            message = "İkinci Beyin açılıyor."
        else:
            return "İkinci Beyin işlemi geçersiz."
        show = getattr(player, "show_second_brain", None)
        if callable(show):
            show()
            return message
        return message if parameters.get("action") == "add" else "İkinci Beyin paneli için AETHER masaüstü arayüzünü açın."
    except Exception as exc:
        return f"İkinci Beyin işlemi tamamlanamadı: {exc}"
