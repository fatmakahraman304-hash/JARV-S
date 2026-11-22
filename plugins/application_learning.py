"""Learn missing application controls through the checked coding workflow."""
PLUGIN = {
    "name": "application_learning",
    "description": "Research and build missing controls for a user-selected installed application. Use learn for explicit app integration requests or missing capabilities in an app the user has asked to extend. This starts coding, not execution of the app task. status lists real progress. publish=true only with standing or current user authorization to test, publish to main and update. Never assert full control, successful messages or call audio without evidence.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["learn", "status"]},
        "name": {"type": "STRING"}, "goal": {"type": "STRING"},
        "publish": {"type": "BOOLEAN"}}, "required": ["action"]}}


def run(parameters, player=None, session_memory=None):
    try:
        from core.application_learning import start, report
        if parameters.get("action") == "status":
            return report()
        if parameters.get("action") != "learn":
            return "Geçersiz işlem."
        name = str(parameters.get("name") or "")
        goal = str(parameters.get("goal") or "")
        if parameters.get("publish") is True:
            from core import confirm
            return confirm.request("application_learning", "Geliştir, main dalına yayınla ve güncelle",
                                   f"Uygulama: {name}\nİstenen değişiklik: {goal}",
                                   lambda: start(name, goal, player, publish=True))
        return start(name, goal, player)
    except Exception as exc:
        return f"Uygulama geliştirmesi başlatılamadı: {exc}"
