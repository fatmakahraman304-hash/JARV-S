import webbrowser
from urllib.parse import quote_plus


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
) -> str:
    city     = parameters.get("city")
    when     = parameters.get("time", "today")  

    if not city or not isinstance(city, str) or not city.strip():
        msg = "Sir, the city is missing for the weather report."
        _log(msg, player)
        return msg

    city = city.strip()
    when = (when or "today").strip().lower()
    days = 7 if any(w in when for w in ("hafta", "week", "7")) else 3
    # Real numbers to say aloud (Open-Meteo, free, no key); the browser only
    # when the service cannot be reached.
    from core import open_data
    msg = open_data.weather(city=city, days=days)
    if msg.startswith("Hava durumu alınamadı"):
        try:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(f'weather in {city} {when}')}")
            msg += " Tarayıcıda açtım."
        except Exception:
            pass
    _log(msg.splitlines()[0], player)
    return msg


def _log(message: str, player=None) -> None:
    try:
        print(f"[Weather] {message}")
    except Exception:                      # a Windows console that cannot print Turkish letters
        print(f"[Weather] {message}".encode("ascii", "replace").decode())
    if player:
        try:
            player.write_log(f"Mayk: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "weather_report",
    "description": "Hava durumu: şu anki sıcaklık ve gökyüzü, önümüzdeki günlerin en düşük/en yüksek "
                   "sıcaklığı ve yağış ihtimali (gerçek veri). time: today | tomorrow | week.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "City name"
            },
            "time": {"type": "STRING", "description": "today | tomorrow | week"}
        },
        "required": [
            "city"
        ]
    },
    "handler": weather_action,
}
