"""
Resim üret ve değiştir — Mayk'ın kendi çizimi.

"Bana gün batımında bir kartal çiz", sonra "gökyüzünü mor yap", "kartalın
üstüne bir taç koy". Ek bir uygulama yok: Gemini'nin resim modelleri çizer
(core/image_studio.py). Resim HUD'da açılır ve Resimler/JARVIS'e kaydedilir.
"""

import threading

PLUGIN = {
    "name": "generate_image",
    "description": (
        "Draw a NEW picture from a description, or CHANGE a picture: the last one Mayk drew, "
        "or a file the user gives / uploaded. Use mode='new' for 'çiz', 'resim yap', 'görsel "
        "oluştur', 'logo tasarla'; mode='edit' for changes to the picture just made or a given "
        "image ('rengini değiştir', 'arka planı sil', 'şunu ekle', 'yazıyı kaldır'). Write the "
        "prompt in English, detailed (subject, style, light, composition) and add the user's "
        "exact wording for any text that must appear. The picture opens on screen by itself."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "what to draw, or what to change (detailed)"},
            "mode": {"type": "STRING", "description": "new | edit"},
            "aspect_ratio": {"type": "STRING",
                             "description": "optional: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 21:9"},
            "image_path": {"type": "STRING",
                           "description": "edit only: a picture file to change; empty = the last one drawn "
                                          "or the file in the upload box"},
        },
        "required": ["prompt"],
    },
}

_busy = threading.Lock()


def _say(player, text: str) -> None:
    if player:
        try:
            player.write_log(f"Mayk: {text}")
        except Exception:
            pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import image_studio
        p = parameters or {}
        prompt = str(p.get("prompt") or "").strip()
        mode = str(p.get("mode") or "new").strip().lower()
        aspect = str(p.get("aspect_ratio") or "").strip()
        if not prompt:
            return "Ne çizmemi istersin?"
        source = None
        if mode == "edit":
            source = str(p.get("image_path") or "").strip()
            if not source and player is not None:
                try:
                    cur = player.current_file
                    if cur and str(cur).lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        source = cur
                except Exception:
                    pass
            if not source:
                last = image_studio.last_image()
                source = str(last) if last else ""
            if not source:
                return "Değiştireceğim bir resim yok; önce bir resim çizeyim mi?"
        if not _busy.acquire(blocking=False):
            return "Bir önceki resmi hâlâ çiziyorum, birazdan biter."

        def work():
            try:
                path, info = image_studio.make(prompt, edit_from=source, aspect=aspect)
                if path is None:
                    _say(player, info)
                    return
                if player:
                    try:
                        player.show_image(str(path), "Düzenlenen resim" if source else "Mayk çizdi")
                    except Exception:
                        pass
                _say(player, f"Resim hazır: {path}" + (f" — {info[:200]}" if info else ""))
                try:
                    from core import activity
                    activity.record("image", f"Resim {'değiştirildi' if source else 'çizildi'}: {prompt[:60]}", "info")
                except Exception:
                    pass
            finally:
                _busy.release()

        threading.Thread(target=work, daemon=True, name="generate-image").start()
        return ("Resmi değiştiriyorum; birkaç saniye içinde ekranda olacak."
                if source else "Çiziyorum; birkaç saniye içinde ekranda olacak.")
    except Exception as exc:
        return f"Resim üretilemedi: {exc}"
