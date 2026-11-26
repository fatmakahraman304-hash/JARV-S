"""
FRIDAY her cihazda — telefon, tablet, TV, projeksiyon, saat.

Kurulum: kullanıcının GitHub hesabında gizli bir gist açılır (ortak hafıza ve
cihazlar arası posta kutusu, core/sync_hub.py), sonra diğer cihazları tek
dokunuşla kuran bir bağlantı ve karekod üretilir. Web FRIDAY (web/, GitHub
Pages) o bağlantıyla açılınca beyni Gemini olur ve bu bilgisayar kapalıyken de
konuşur, dinler, görür, kod yazar, hafızayı kullanır.
"""

import os
import threading
from pathlib import Path

PLUGIN = {
    "name": "aether_everywhere",
    "description": (
        "Set up or manage FRIDAY on the user's other devices (phone, tablet, TV, projector, "
        "smart watch) so they work on their own even when this computer is off, with the "
        "same memory. action='setup' with the user's GitHub token (gist permission) creates "
        "the shared memory and shows the one-tap setup link and QR code; action='link' shows "
        "the link/QR again; action='status' tells whether syncing works; action='update_all' "
        "updates FRIDAY on every device at once (phones, tablets, TVs, watches reload, other "
        "computers press GÜNCELLE, then this one). Trigger phrases: "
        "'FRIDAY'ı telefona/tablete/televizyona kur', 'her cihazda çalışsın', 'kurulum linki', "
        "'bütün cihazları güncelle'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "setup | link | status | update_all"},
            "github_token": {"type": "STRING",
                             "description": "GitHub personal access token with the 'gist' scope "
                                            "(only for setup, when the user gives one)"},
        },
        "required": ["action"],
    },
}

_HOWTO = (
    "1) github.com/settings/tokens/new?scopes=gist&description=FRIDAY adresini aç.\n"
    "2) Süreyi 'No expiration' seç, sadece 'gist' kutusu işaretli olsun, 'Generate token'a bas.\n"
    "3) Çıkan ghp_ ile başlayan anahtarı FRIDAY'ın yazı kutusuna şöyle yaz:\n"
    "   token ghp_xxxxxxxx — kur"
)


def _show(player, title: str, text: str) -> None:
    if player:
        try:
            player.show_content(title, text)
        except Exception:
            pass


def _qr_file(link: str) -> Path | None:
    try:
        import qrcode
        from core.sync_hub import settings  # noqa: F401  (ensures config is importable)
        base = Path(__file__).resolve().parent.parent / "config"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "aether_kurulum_qr.png"
        img = qrcode.make(link, box_size=8, border=3)
        img.save(path)
        return path
    except Exception as exc:
        print(f"[Everywhere] QR: {exc}")
        return None


def _open(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))          # noqa: S606 — opens the user's own image viewer
        else:
            import webbrowser
            webbrowser.open(path.as_uri())
    except Exception as exc:
        print(f"[Everywhere] open: {exc}")


def _link_text(link: str, qr: Path | None) -> str:
    return (
        "Diğer cihazlarda FRIDAY'ı açmak için:\n\n"
        "• Telefon / tablet: karekodu kamerayla okut ya da bağlantıyı kendine gönderip aç.\n"
        "• Televizyon / projeksiyon: tarayıcısında bağlantıyı aç (ya da telefonda açıp "
        "  Ayarlar → 'Bu cihazı TV yap').\n"
        "• Akıllı saat (Wear OS): saatin tarayıcısında bağlantıyı aç.\n"
        "Açılınca 'Ana ekrana ekle' de, uygulama gibi durur.\n\n"
        f"Bağlantı (gizli tut — içinde anahtarların var):\n{link}\n\n"
        + (f"Karekod: {qr}" if qr else "Karekod üretilemedi; bağlantıyı kullan.")
    )


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        from memory.config_manager import get_gemini_key
        action = str((parameters or {}).get("action") or "status").strip().lower()
        token = str((parameters or {}).get("github_token") or "").strip()

        if action in ("update_all", "update"):
            sent = sync_hub.request_update_all()
            if player and hasattr(player, "start_update"):
                try:
                    player.start_update()
                except Exception:
                    pass
            if sent:
                return ("Bütün cihazlara güncelleme gönderdim; açık olanlar yenileniyor, "
                        "bu bilgisayar da güncelleniyor.")
            return ("Ortak hafıza kurulu olmadığı için sadece bu bilgisayarı güncelliyorum. "
                    "Telefon ve TV'de ⬆ Güncelle'ye basabilirsin.")

        if action == "status":
            s = sync_hub.settings()
            if not s.get("gist_id"):
                _show(player, "FRIDAY her cihazda — kurulum", _HOWTO)
                return "Henüz kurulmadı. GitHub anahtarını ekrana yazdığım adımlarla alıp bana ver."
            return f"Ortak hafıza durumu: {sync_hub.status()}."

        if action == "setup":
            s = sync_hub.settings()
            if not token:
                token = s.get("github_token", "")
            if not token:
                _show(player, "FRIDAY her cihazda — kurulum", _HOWTO)
                return "Bir GitHub anahtarı lazım; nasıl alacağını ekrana yazdım."
            gist_id = s.get("gist_id", "")
            if gist_id:
                files, _tag, err = sync_hub.read_gist(token, gist_id)
                if err:
                    gist_id = ""
            if not gist_id:
                gist_id, err = sync_hub.create_gist(token)
                if not gist_id:
                    return f"Kurulamadı: {err}"
            sync_hub.save_settings(github_token=token, gist_id=gist_id)
            sync_hub.start(sync_hub._state.get("inject"))
            action = "link"

        if action == "link":
            if not sync_hub.settings().get("gist_id"):
                _show(player, "FRIDAY her cihazda — kurulum", _HOWTO)
                return "Önce kurulum gerekiyor; adımları ekrana yazdım."
            link = sync_hub.setup_link(get_gemini_key() or "")
            qr = _qr_file(link)
            _show(player, "FRIDAY her cihazda", _link_text(link, qr))
            if qr:
                threading.Thread(target=_open, args=(qr,), daemon=True).start()
            return ("Hazır. Karekodu ekranda açtım; telefonla, tabletle okut. "
                    "TV ve saat için bağlantı ekranda.")

        return "Ne yapacağımı anlayamadım: kur, bağlantı ya da durum diyebilirsin."
    except Exception as exc:
        return f"FRIDAY her cihazda kurulamadı: {exc}"
