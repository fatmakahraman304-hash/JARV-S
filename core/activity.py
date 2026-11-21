"""core/activity.py — the live activity log behind the Control Centre.

Every tool call, every spoken turn and every typed command is recorded here as
one short event: which node of the network it belongs to (web, files, YouTube,
WhatsApp…), a line of text, and whether it worked. The Control Centre reads it
on a timer from the Qt thread; everything else only ever calls `record()`.

Thread safety is a lock around a bounded deque. `record()` is cheap and never
raises, so it can be called from the voice loop, a tool thread or a plugin
without anyone needing to guard it.

Nodes are a fixed catalogue so the network keeps its shape: five inner
capabilities around the core, and the apps and tools MAYK actually drives on
the outer ring. A node lights up and counts once something in this session has
gone through it — the count is real activity, never decoration.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

# (key, label, icon, ring). Ring 0 is the inner circle of capabilities.
NODES: tuple[tuple[str, str, str, int], ...] = (
    ("voice",     "Ses",          "mic",      0),
    ("chat",      "Sohbet",       "chat",     0),
    ("web",       "Web",          "globe",    0),
    ("files",     "Dosyalar",     "folder",   0),
    ("memory",    "Hafıza",       "brain",    0),
    ("youtube",   "YouTube",      "play",     1),
    ("whatsapp",  "WhatsApp",     "send",     1),
    ("instagram", "Instagram",    "camera",   1),
    ("telegram",  "Telegram",     "send",     1),
    ("messages",  "Mesajlar",     "chat",     1),
    ("reminders", "Hatırlatıcı",  "calendar", 1),
    ("weather",   "Hava",         "cloud",    1),
    ("computer",  "Bilgisayar",   "monitor",  1),
    ("vision",    "Ekran & Kamera", "eye",    1),
    ("code",      "Kod",          "code",     1),
    ("maps",      "Harita",       "map",      1),
    ("tasks",     "Görevler",     "grid",     1),
    ("gmail",     "Gmail",        "mail",     1),
    ("googlecalendar", "Google Takvim", "calendar", 1),
    ("googledrive", "Google Drive", "folder", 1),
    ("googledocs", "Google Docs",  "doc",      1),
    ("googlesheets", "Google Sheets", "sheet", 1),
    ("notion",    "Notion",       "doc",      1),
    ("apps",      "Diğer uygulamalar", "plus", 1),
)
NODE_LABEL = {k: label for k, label, _i, _r in NODES}

# Nodes that are apps reached through Composio, keyed by their toolkit slug.
# They are drawn grey until the user connects the account; "apps" stands for
# every other one of the 1000+ toolkits.
APP_NODES = {"gmail", "googlecalendar", "googledrive", "googledocs", "googlesheets", "notion"}

_TOOL_NODE = {
    "web_search": "web", "browser_control": "web", "flight_finder": "web",
    "file_controller": "files", "file_processor": "files",
    "save_memory": "memory", "recall_memory": "memory", "undo": "memory",
    "youtube_video": "youtube", "video_player": "youtube",
    "reminder": "reminders", "routines": "reminders",
    "weather_report": "weather",
    "computer_control": "computer", "computer_settings": "computer",
    "desktop_control": "computer", "open_app": "computer", "system_status": "computer",
    "manage_monitor": "computer", "game_updater": "computer",
    "screen_process": "vision", "close_camera": "vision", "camera_scan": "vision",
    "scan_research": "vision",
    "code_helper": "code", "dev_agent": "code", "github_develop": "code",
    "voice_prototype": "code",
    "map_route": "maps", "normal_map": "maps",
    "background_tasks": "tasks", "night_shift": "tasks", "workspace_mode": "tasks",
    "capacity_simulation": "tasks", "control_center": "tasks",
}

# Readable verbs for the feed, by tool. Anything missing falls back to the name.
_TOOL_TEXT = {
    "web_search": "Web araması", "browser_control": "Tarayıcı", "flight_finder": "Uçuş araması",
    "file_controller": "Dosya işlemi", "file_processor": "Dosya analizi",
    "save_memory": "Hafızaya kayıt", "recall_memory": "Hafızadan hatırlama", "undo": "Geri alma",
    "youtube_video": "YouTube", "video_player": "Video oynatma",
    "reminder": "Hatırlatıcı", "routines": "Rutin", "weather_report": "Hava durumu",
    "computer_control": "Bilgisayar kontrolü", "computer_settings": "Bilgisayar ayarı",
    "desktop_control": "Masaüstü", "open_app": "Uygulama açma", "system_status": "Sistem durumu",
    "manage_monitor": "Ekran ayarı", "game_updater": "Oyun güncellemesi",
    "screen_process": "Ekran / kamera görüntüsü", "close_camera": "Kamerayı kapatma",
    "camera_scan": "Kamera taraması", "scan_research": "Tarama araştırması",
    "code_helper": "Kod yardımı", "dev_agent": "Kodlama görevi", "github_develop": "GitHub geliştirme",
    "voice_prototype": "Prototip", "map_route": "Rota", "normal_map": "Harita",
    "background_tasks": "Arka plan görevi",
    "night_shift": "Gece vardiyası", "workspace_mode": "Çalışma modu",
    "capacity_simulation": "Kapasite simülasyonu",
    "send_message": "Mesaj", "control_center": "Kontrol Merkezi", "apps": "Uygulama",
}


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    node: str
    text: str
    status: str          # "ok" | "warn" | "fail" | "info"


_lock = threading.Lock()
_connected: set[str] = set()
_events: deque[Event] = deque(maxlen=400)
_counts: dict[str, int] = {}
_last_hit: dict[str, float] = {}
_seq = 0


def node_for_toolkit(toolkit: str) -> str:
    t = str(toolkit or "").strip().lower()
    return t if t in APP_NODES else "apps"


def node_for_tool(name: str, args: dict | None = None) -> str:
    """Which node a tool call belongs to."""
    name = str(name or "")
    if name == "apps":
        a = args or {}
        tk = str(a.get("toolkit") or "").strip()
        if not tk and a.get("tool_slug"):
            slug = str(a["tool_slug"]).lower()
            tk = next((n for n in APP_NODES if slug.startswith(n + "_")), "")
        return node_for_toolkit(tk)
    if name == "send_message":
        platform = str((args or {}).get("platform") or "").lower()
        for key, words in (("whatsapp", ("whatsapp", "wp", "wapp")),
                           ("instagram", ("instagram", "insta", "ig")),
                           ("telegram", ("telegram", "tg"))):
            if any(w in platform for w in words):
                return key
        return "messages"
    return _TOOL_NODE.get(name, "tasks")


def status_of(result) -> str:
    """'fail', 'warn' or 'ok' from a tool's result, using core.outcome's lines."""
    text = str(result or "").lstrip()
    if text.startswith("status=started "):
        return "info"
    if text.startswith("status=failed"):
        return "fail"
    if text.startswith(("status=unverified", "status=ask")):
        return "warn"
    low = text[:80].lower()
    if low.startswith(("error", "err:", "hata", "failed", "could not")):
        return "fail"
    if low.startswith("tool '") and "' failed:" in low:      # main.py's exception wrapper
        return "fail"
    return "ok"


def record(node: str, text: str, status: str = "ok", count: bool = True) -> None:
    """Add one event. Never raises.

    count=False lists the event without counting it as use of the node — for
    notes about a node (a login page opening, a missing key) that must not
    light it up as if it had done work."""
    global _seq
    try:
        node = node if node in NODE_LABEL else "tasks"
        now = time.time()
        with _lock:
            _seq += 1
            _events.append(Event(_seq, now, node, str(text or "")[:300], status))
            if count:
                _counts[node] = _counts.get(node, 0) + 1
                _last_hit[node] = now
    except Exception:
        pass


def record_tool(name: str, args: dict | None, result=None, error: BaseException | None = None) -> None:
    """Record a finished tool call with a readable line and its real outcome."""
    node = node_for_tool(name, args)
    base = _TOOL_TEXT.get(name, name.replace("_", " ").capitalize())
    detail = ""
    if name == "send_message":
        detail = str((args or {}).get("receiver") or "").strip()
        base = f"Mesaj → {detail}" if detail else base
        detail = ""
    elif name == "web_search":
        detail = str((args or {}).get("query") or "").strip()
    elif name == "apps":
        a = args or {}
        act = str(a.get("action") or "").lower()
        base = {"search": "Uygulama aracı arandı", "connect": "Bağlantı sayfası açıldı",
                "connected": "Bağlı uygulamalar okundu"}.get(act, "")
        slug = str(a.get("tool_slug") or "").strip()
        if act == "run" and slug:
            node = node_for_tool("apps", a)
            words = slug.lower()
            if node in APP_NODES and words.startswith(node + "_"):
                words = words[len(node) + 1:]
            elif node == "apps" and "_" in words:
                words = words.split("_", 1)[1]
            base = NODE_LABEL.get(node, "Uygulama") if node != "apps" else slug.split("_")[0].title()
            detail = words.replace("_", " ")[:60]
        else:
            base = base or "Uygulama"
            detail = str(a.get("toolkit") or a.get("use_case") or "").strip()[:60]
    elif name == "open_app":
        detail = str((args or {}).get("app_name") or (args or {}).get("app") or "").strip()
    if detail:
        base = f"{base}: {detail}"
    try:
        from core import journal                       # the record that outlives this run
        journal.record(name, "fail" if error is not None else status_of(result), base)
    except Exception:
        pass
    if error is not None:
        record(node, f"Yapılamadı: {base}", "fail")
        return
    st = status_of(result)
    if st == "fail":
        record(node, f"Yapılamadı: {base}", "fail")
    elif st == "warn":
        record(node, f"Doğrulanamadı: {base}", "warn")
    else:
        record(node, base, "ok")


def set_connected(slugs) -> None:
    """The toolkits Composio reports as connected (lower-case slugs)."""
    global _connected, _seq
    with _lock:
        new = {str(x).lower() for x in (slugs or ())}
        if new != _connected:
            _connected = new
            _seq += 1


def bump() -> None:
    """Mark a change that is not an event (e.g. new connections) so readers refresh."""
    global _seq
    with _lock:
        _seq += 1


def connected() -> set[str]:
    with _lock:
        return set(_connected)


def since(seq: int) -> list[Event]:
    with _lock:
        return [e for e in _events if e.seq > seq]


def recent(limit: int = 60) -> list[Event]:
    with _lock:
        return list(_events)[-limit:]


def counts() -> dict[str, int]:
    with _lock:
        return dict(_counts)


def last_hit() -> dict[str, float]:
    with _lock:
        return dict(_last_hit)


def last_seq() -> int:
    with _lock:
        return _seq
