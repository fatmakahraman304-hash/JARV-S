"""
core/remote_control.py — the phone's quick buttons for a computer.

Volume, media keys, lock and a screenshot, done directly rather than through
the language model: a button pressed on the phone should act at once and the
same way every time. No Qt here (this runs on the dashboard's worker thread),
and nothing raises — every action returns (ok, message).
"""

from __future__ import annotations

import base64
import io
import platform
import subprocess

# action -> (pyautogui key, Turkish label)
_KEYS = {
    "volume_up": ("volumeup", "Ses açıldı"),
    "volume_down": ("volumedown", "Ses kısıldı"),
    "mute": ("volumemute", "Ses kapatıldı/açıldı"),
    "play_pause": ("playpause", "Oynat / duraklat"),
    "next": ("nexttrack", "Sonraki parça"),
    "prev": ("prevtrack", "Önceki parça"),
}

ACTIONS = tuple(_KEYS) + ("lock", "screenshot")


def _run(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            print(f"[Remote] {' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()[:200]}")
        return r.returncode == 0
    except Exception as exc:
        print(f"[Remote] {' '.join(cmd)}: {exc}")
        return False


def _press(key: str, times: int) -> bool:
    try:
        import pyautogui
        for _ in range(max(1, times)):
            pyautogui.press(key)
        return True
    except Exception as exc:
        print(f"[Remote] key {key}: {exc}")
        return False


def _linux_key(action: str, times: int) -> bool:
    if action in ("volume_up", "volume_down", "mute"):
        arg = {"volume_up": ["set-sink-volume", "@DEFAULT_SINK@", f"+{2 * times}%"],
               "volume_down": ["set-sink-volume", "@DEFAULT_SINK@", f"-{2 * times}%"],
               "mute": ["set-sink-mute", "@DEFAULT_SINK@", "toggle"]}[action]
        return _run(["pactl", *arg])
    cmd = {"play_pause": "play-pause", "next": "next", "prev": "previous"}[action]
    return _run(["playerctl", cmd])


def _lock() -> bool:
    system = platform.system()
    if system == "Windows":
        return _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    if system == "Darwin":
        return _run(["pmset", "displaysleepnow"])
    return _run(["loginctl", "lock-session"]) or _run(["xdg-screensaver", "lock"])


def screenshot_jpeg(max_side: int = 1600, quality: int = 70) -> bytes | None:
    """The primary screen as JPEG bytes, or None."""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(mon)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()
    except Exception as exc:
        print(f"[Remote] screenshot: {exc}")
        return None


def perform(action: str, times: int = 1) -> tuple[bool, str, dict]:
    """Do one quick action. Returns (ok, message, extra)."""
    action = str(action or "").strip()
    times = max(1, min(int(times or 1), 10))
    if action in _KEYS:
        key, label = _KEYS[action]
        if platform.system() == "Linux":
            ok = _linux_key(action, times)
        else:
            ok = _press(key, times if action.startswith("volume_") else 1)
        return ok, (label if ok else "Tuşa basılamadı"), {}
    if action == "lock":
        ok = _lock()
        return ok, ("Bilgisayar kilitlendi" if ok else "Kilitlenemedi"), {}
    if action == "screenshot":
        data = screenshot_jpeg()
        if not data:
            return False, "Ekran görüntüsü alınamadı", {}
        return True, "Ekran görüntüsü", {"image": "data:image/jpeg;base64," + base64.b64encode(data).decode()}
    return False, "Bilinmeyen komut", {}


def open_screen_page(url: str, monitor: int = 0) -> tuple[bool, str]:
    """Open the JARVIS screen page full-screen on this computer — on the TV if
    one is plugged in. monitor: 0 = the last connected display (usually the TV),
    1 = the primary one."""
    left = top = 0
    try:
        import mss
        with mss.mss() as sct:
            mons = sct.monitors[1:]
        if mons:
            m = mons[-1] if monitor == 0 else mons[min(monitor, len(mons)) - 1]
            left, top = int(m["left"]), int(m["top"])
    except Exception:
        pass
    flags = [f"--app={url}", "--start-fullscreen", f"--window-position={left},{top}",
             "--autoplay-policy=no-user-gesture-required", "--new-window"]
    candidates: list[list[str]] = []
    system = platform.system()
    if system == "Windows":
        import os
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")):
            for rel in (r"Google\Chrome\Application\chrome.exe",
                        r"Microsoft\Edge\Application\msedge.exe"):
                if base:
                    candidates.append([os.path.join(base, rel)])
    elif system == "Darwin":
        candidates += [["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                       ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]]
    else:
        candidates += [["google-chrome"], ["chromium"], ["chromium-browser"], ["microsoft-edge"]]
    import os
    import shutil
    for cand in candidates:
        exe = cand[0]
        if not (os.path.isfile(exe) or shutil.which(exe)):
            continue
        try:
            subprocess.Popen([exe, *flags])
            return True, "Ekran sayfası açıldı"
        except Exception as exc:
            print(f"[Remote] {exe}: {exc}")
    try:
        import webbrowser
        if webbrowser.open(url):
            return True, "Ekran sayfası tarayıcıda açıldı (tam ekran için F11)"
    except Exception:
        pass
    return False, "Tarayıcı açılamadı"


def youtube_id(query: str) -> tuple[str, str]:
    """A YouTube video id (and title) from a link or a search phrase."""
    import re
    q = str(query or "").strip()
    if not q:
        return "", ""
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", q)
    if m:
        return m.group(1), ""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", q):
        return q, ""
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extract_flat": True, "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{q}", download=False)
        entries = (info or {}).get("entries") or []
        if entries:
            e = entries[0]
            return str(e.get("id") or ""), str(e.get("title") or "")
    except Exception as exc:
        print(f"[Remote] YouTube search: {exc}")
    return "", ""
