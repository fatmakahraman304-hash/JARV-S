"""'Neler yapabilirsin?' — everything JARVIS can do, grouped, with things to say.

Built from the tools that are really installed and enabled right now (so a new
plugin shows up by itself), arranged in groups a person thinks in, each with a
couple of example sentences.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN = {
    "name": "capabilities",
    "description": (
        "Everything JARVIS can do, grouped (computer, files, messages and devices, media, 3D and design, planning, "
        "coding, JARVIS itself …) with example sentences — from the tools installed right now. Use for 'neler "
        "yapabilirsin?', 'ne işe yararsın?', 'yardım', 'hangi komutları biliyorsun?', 'Blender'da neler yaparsın?' "
        "(topic=…)."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "topic": {"type": "STRING", "description": "Optional: one area ('Blender', 'dosya', 'mesaj', 'bilgisayar' …)"},
    }},
}

GROUPS = [
    ("Bilgisayarı yönetme", ["open_app", "apps", "computer_control", "computer_settings", "desktop", "control_center",
                             "focus_mode", "workspace_mode", "night_shift", "screen_time", "laptop_battery",
                             "network_check", "system_alerts", "clipboard_bridge", "pc_extra", "browser_control"]),
    ("Dosyalar", ["file_controller", "file_processor", "disk_cleanup", "search_history"]),
    ("Mesajlar ve cihazlar", ["send_message", "send_to_device", "file_to_device", "android_device", "tv_screen",
                              "wake_lan", "jarvis_everywhere"]),
    ("Bilgi ve araştırma", ["web_search", "weather_report", "currency", "flight_finder", "map_route", "scan_research"]),
    ("Medya ve görsel", ["youtube_video", "video_player", "generate_image", "gallery", "normal_map"]),
    ("3B ve tasarım", ["blender_studio", "camera_scan", "capacity_simulation"]),
    ("Plan ve rutin", ["reminder", "routines", "todo_list", "day_report", "background_tasks", "protocol", "proactive"]),
    ("Kod ve geliştirme", ["dev_agent", "code_helper", "github_develop", "coding_setup", "application_learning",
                           "voice_prototype"]),
    ("Oyun", ["chess", "game_updater"]),
    ("JARVIS'in kendisi", ["self_check", "self_update", "work_status", "job_control", "status_report", "capabilities"]),
]

EXAMPLES = {
    "open_app": ["Spotify'ı aç", "Chrome'u kapat"],
    "computer_settings": ["Sesi yüzde 30 yap", "Parlaklığı düşür"],
    "file_controller": ["İndirilenler'deki PDF'leri Belgeler'e taşı", "Bunu geri al"],
    "file_processor": ["Bu PDF'i özetle", "Bu Excel'den grafik çıkar"],
    "disk_cleanup": ["Diski temizle"],
    "send_message": ["Anneme WhatsApp'tan 'akşam geliyorum' yaz"],
    "send_to_device": ["Bunu telefonuma gönder"],
    "tv_screen": ["Ekranı televizyona yansıt"],
    "web_search": ["Bugünün haberlerini söyle", "Euro kaç lira?"],
    "weather_report": ["Yarın hava nasıl?"],
    "map_route": ["Lefkoşa'dan Girne'ye yol tarifi"],
    "youtube_video": ["YouTube'da Interstellar müziğini aç"],
    "generate_image": ["Gün batımında bir kale resmi çiz"],
    "blender_studio": ["Blender'da ahşap bir masa yap", "Şunu kırmızı yap", "3 katlı balkonsuz bir ev yap",
                       "Render al", "Geri al"],
    "reminder": ["Yarın 9'da beni toplantı için uyar"],
    "routines": ["Akşam modu diye bir rutin yap: ışığı kıs, müzik aç", "Akşam modu"],
    "todo_list": ["Yapılacaklara süt almayı ekle"],
    "background_tasks": ["Arka planda elektrikli arabalar hakkında rapor hazırla"],
    "dev_agent": ["Kendine şu özelliği ekle", "Bu hatayı düzelt"],
    "chess": ["Satranç oynayalım"],
    "self_check": ["Kendini kontrol et", "Son hataları göster"],
    "self_update": ["Yeni sürüm var mı?", "Kendini güncelle"],
    "work_status": ["Bitti mi?", "Ne yaptın?"],
    "job_control": ["Dur", "Blender'daki işi iptal et"],
    "screen_process": ["Ekranda ne var?"],
}

CORE = {  # tools built into main.py (not plugins/actions)
    "screen_process": "Ekranı ya da kamerayı görür",
    "save_memory": "Seni ve tercihlerini hatırlar",
    "recall_memory": "Hatırladıklarını arar",
    "undo": "Yaptığı değişiklikleri geri alır",
}


def _declared(path: Path) -> tuple[str, str] | None:
    """name and description of a plugin/action file, read from its source — never imported again here:
    a second copy of a running module would have its own state (locks, queues) and break it."""
    import ast
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(
                isinstance(t, ast.Name) and t.id in ("PLUGIN", "TOOL") for t in node.targets):
            fields = {}
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value in ("name", "description"):
                    try:
                        fields[k.value] = ast.literal_eval(v)
                    except ValueError:
                        pass
            if fields.get("name"):
                return str(fields["name"]), str(fields.get("description") or "")
    return None


def installed() -> dict[str, str]:
    """name → first sentence of its description, for every enabled tool."""
    root = Path(__file__).resolve().parent.parent
    out = dict(CORE)
    try:
        from memory.config_manager import get_plugin_enabled
    except Exception:
        get_plugin_enabled = lambda _n: True
    for folder in ("actions", "plugins"):
        for f in sorted((root / folder).glob("*.py")):
            if f.name.startswith("_"):
                continue
            got = _declared(f)
            if got and (folder == "actions" or get_plugin_enabled(got[0])):
                out[got[0]] = got[1].split(". ")[0][:140]
    return out


def overview(topic: str = "") -> str:
    tools = installed()
    t = topic.lower().strip()
    lines, placed = [], set()
    for label, names in GROUPS:
        here = [n for n in names if n in tools]
        placed |= set(here)
        if not here:
            continue
        if t and t not in label.lower() and not any(t in n or t in tools[n].lower()
                                                     or any(t in e.lower() for e in EXAMPLES.get(n, [])) for n in here):
            continue
        ex = [e for n in here for e in EXAMPLES.get(n, [])][:6]
        lines.append(f"■ {label} ({len(here)} araç)" + (": " + " · ".join(f"«{e}»" for e in ex) if ex else ""))
    others = [n for n in tools if n not in placed and n not in CORE]
    if others and not t:
        lines.append("■ Diğer: " + ", ".join(sorted(others)))
    head = f"Şu an {len(tools)} yeteneğim var" + (f" ('{topic}' ile ilgili olanlar)" if t else "") + ":"
    return head + "\n" + "\n".join(lines)


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        text = overview(str((parameters or {}).get("topic") or ""))
        if player is not None and hasattr(player, "show_content"):
            player.show_content("JARVIS — neler yapabilirim", text)
        return text + ("\n(Kullanıcıya kısaca söyle: ana grupları ve birkaç örnek; tam liste ekranda. Sonunda bir "
                       "tane denemesini öner.)")
    except Exception as exc:
        return f"Yeteneklerimi listeleyemedim: {exc}"
