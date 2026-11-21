"""
Televizyon ekranı — Mayk'ın TV'ye bir şey göstermesi.

TV, tarayıcısında Mayk'ın /tv sayfasını açmış ve telefondan eşlenmiş bir
ekrandır (ya da bilgisayara HDMI ile bağlı televizyon). Bu araç oraya YouTube
videosu, web sayfası, resim ya da yazı gönderir, ekranı kapatır, ya da
bilgisayarın kendi TV'sinde Mayk ekranını açar.
"""

import threading

PLUGIN = {
    "name": "tv_screen",
    "description": (
        "Show something on the TV / big screen paired with Mayk: play a YouTube "
        "video ('televizyonda X videosunu aç', 'TV'de şarkı aç'), open a web page, "
        "show a picture or a text, close what is on the TV, or open the Mayk "
        "screen on the TV plugged into this computer ('TV ekranını aç', 'Mayk'ı "
        "televizyona yansıt'). Use this only for the TV; for playing a video in "
        "Mayk's own window use the normal video tools."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "video | url | image | text | clear | open_screen",
            },
            "value": {
                "type": "STRING",
                "description": "For video: a search phrase or YouTube link. For url/image: the "
                               "address. For text: the words to show. Empty otherwise.",
            },
        },
        "required": ["action"],
    },
}


def _server():
    try:
        from dashboard import server
        return server.ACTIVE
    except Exception:
        return None


def _log(player, text: str) -> None:
    if player:
        try:
            player.write_log(f"TV: {text}")
        except Exception:
            pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str((parameters or {}).get("action") or "").strip().lower()
        value = str((parameters or {}).get("value") or "").strip()
        srv = _server()
        if srv is None:
            return "Telefon ve TV bağlantısı şu an kapalı; Mayk'ı yeniden başlatmayı dene."

        if action in ("open_screen", "open", "screen"):
            def _open():
                from core import remote_control
                port = 8001 if srv._ssl_enabled() else 8000
                scheme = "https" if srv._ssl_enabled() else "http"
                ok, msg = remote_control.open_screen_page(f"{scheme}://127.0.0.1:{port}/tv?local=1")
                _log(player, msg)
            threading.Thread(target=_open, daemon=True, name="tv-open").start()
            return "Mayk ekranını televizyonda açıyorum."

        if action in ("clear", "close", "kapat", "home"):
            return srv.send_to_screen("home")

        if action in ("video", "youtube"):
            if not value:
                return "Hangi videoyu açayım?"

            def _play():
                from core import remote_control
                vid, title = remote_control.youtube_id(value)
                if not vid:
                    _log(player, f"'{value}' için video bulunamadı.")
                    return
                _log(player, srv.send_to_screen("video", vid, title or value))
            if not srv._screen_ws:
                return srv.send_to_screen("video", "x")       # explains how to pair a TV
            threading.Thread(target=_play, daemon=True, name="tv-video").start()
            return f"'{value}' televizyonda açılıyor."

        if action in ("url", "web", "page"):
            if not value.startswith(("http://", "https://")):
                value = "https://" + value if value else ""
            if not value:
                return "Hangi adresi açayım?"
            return srv.send_to_screen("url", value)

        if action in ("image", "picture", "resim"):
            if not value.startswith(("http://", "https://")):
                return "Resim için bir internet adresi lazım."
            return srv.send_to_screen("image", value)

        if action in ("text", "yazi", "yazı"):
            if not value:
                return "Ekrana ne yazayım?"
            return srv.send_to_screen("text", value)

        return "Televizyon için ne yapacağımı anlayamadım."
    except Exception as exc:
        return f"Televizyona gönderilemedi: {exc}"
