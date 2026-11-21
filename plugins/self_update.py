"""MAYK's own updates: "yeni sürüm var mı?", "neler yeni?", "kendini güncelle".

check: asks GitHub (read-only) and lists what the new version changes.
update: the same updater as the GÜNCELLE button — a backup branch first, then the
update, then a restart. Also the background watcher in main.py uses check().
"""
from __future__ import annotations

PLUGIN = {
    "name": "self_update",
    "description": (
        "MAYK's own software updates from GitHub. action=check: is there a newer version and what changed ('yeni sürüm "
        "var mı?', 'neler yeni?', 'güncelleme var mı?'). action=update: update and restart MAYK now ('kendini güncelle', "
        "'güncelle', 'evet güncelle' after you offered an update). action=auto_on / auto_off: update automatically when idle."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "check | update | auto_on | auto_off"},
    }, "required": ["action"]},
}


def summary(info: dict) -> str:
    if info.get("ahead"):
        if info.get("behind"):
            return "Yerel dal ile GitHub dalı ayrı ayrı ilerlemiş. Güncellemek için önce commitleri birleştirmek gerekiyor."
        return "Yerel dal GitHub sürümünün ilerisinde. Alınacak güncelleme yok."
    if not info.get("newer"):
        return f"MAYK güncel (sürüm {info.get('current', '')[:8]})."
    ch = info.get("changes") or []
    lines = "\n".join(f"- {c}" for c in ch[:10])
    count = f", {info['behind']} değişiklik" if info.get('behind') else ""
    return (f"Yeni bir MAYK sürümü var ({info.get('sha', '')[:8]}{count}).\n{lines}\n"
            "(Kullanıcıya en önemli yenilikleri bir iki cümleyle anlat ve şimdi güncelleyip yeniden başlatayım mı diye sor.)")


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = str((parameters or {}).get("action") or "check").lower().strip()
        if action in ("auto_on", "auto_off"):
            from memory.config_manager import save_plugin_config
            save_plugin_config("self_update", {"auto": action == "auto_on"})
            return ("Tamam, yeni sürümleri boştayken kendim kurup yeniden başlayacağım." if action == "auto_on"
                    else "Tamam, yeni sürüm çıkınca önce sana soracağım.")
        if action == "update":
            if player is None or not hasattr(player, "start_update"):
                return "Güncellemeyi başlatamadım: MAYK penceresi yok."
            player.start_update()
            return "Güncellemeyi başlattım: önce yedek alıyorum, sonra kurup yeniden başlayacağım."
        from core import app_updater
        return summary(app_updater.check())
    except Exception as exc:
        return f"GitHub'a ulaşıp sürümü kontrol edemedim: {exc}"
