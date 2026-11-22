"""
core/adb_control.py — AETHER drives an Android projector or TV over Wi-Fi.

The Magcubic HY320 (and any Android / Google TV box or projector) can be
controlled from this computer with ADB, Android's own remote-control channel:
open apps and web pages, type text, press the remote's keys, connect it to
Wi-Fi, take a picture of its screen so AETHER can see what is on it, and read
what it is (model, Android version, installed apps) so AETHER knows it.

One-time setup on the projector: Settings → Other settings → Developer
options → turn on USB debugging / ADB (on some models "Network ADB"). The
first connection shows "Allow USB debugging?" on the projector — accept it
with the remote ("Always allow").

`adb` comes from Google's platform-tools; if it is not on this computer it is
downloaded once into tools/platform-tools (Google's official zip).

No Qt; nothing raises — functions return (ok, text) or text.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TOOLS = BASE_DIR / "tools" / "platform-tools"
_STATE = BASE_DIR / "config" / "android_devices.json"
PT_URL = {"win32": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
          "darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
          "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"}
_NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}

KEYS = {"home": 3, "back": 4, "up": 19, "down": 20, "left": 21, "right": 22, "ok": 23, "enter": 66,
        "volume_up": 24, "volume_down": 25, "mute": 164, "power": 26, "sleep": 223, "wake": 224,
        "menu": 82, "play_pause": 85, "play": 126, "pause": 127, "stop": 86, "next": 87, "previous": 88,
        "rewind": 89, "fast_forward": 90, "settings": 176, "search": 84, "delete": 67, "tab": 61,
        "channel_up": 166, "channel_down": 167, "apps": 284}
KEY_WORDS = {"ev": "home", "ana ekran": "home", "geri": "back", "yukarı": "up", "aşağı": "down", "sol": "left",
             "sağ": "right", "tamam": "ok", "seç": "ok", "ses aç": "volume_up", "sesi aç": "volume_up",
             "ses kıs": "volume_down", "sesi kıs": "volume_down", "sessiz": "mute", "kapat": "power",
             "oynat": "play_pause", "durdur": "play_pause", "duraklat": "pause", "ileri": "fast_forward",
             "sonraki": "next", "önceki": "previous", "ayarlar": "settings", "menü": "menu", "sil": "delete"}

# well-known apps on Android TV boxes/projectors: words → package
APPS = {"youtube": ["com.google.android.youtube.tv", "com.google.android.youtube.tvkids", "com.google.android.youtube"],
        "netflix": ["com.netflix.ninja", "com.netflix.mediaclient"], "prime": ["com.amazon.amazonvideo.livingroom"],
        "disney": ["com.disney.disneyplus"], "chrome": ["com.android.chrome"], "spotify": ["com.spotify.tv.android", "com.spotify.music"],
        "play store": ["com.android.vending"], "ayarlar": ["com.android.tv.settings", "com.android.settings"],
        "settings": ["com.android.tv.settings", "com.android.settings"], "dosya": ["com.softwinner.TvdFileManager", "com.android.documentsui"],
        "miracast": ["com.softwinner.miracastReceiver"], "airplay": ["com.waxrain.airplaydmr", "com.ionitech.airscreen"],
        "galeri": ["com.android.gallery3d"], "müzik": ["com.android.music"], "tubi": ["com.tubitv"], "twitch": ["tv.twitch.android.app"]}


def _load() -> dict:
    try:
        d = json.loads(_STATE.read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")
    except OSError:
        pass


# ── adb itself ───────────────────────────────────────────────────────────────

def adb_path(download: bool = True) -> str:
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    found = shutil.which(exe)
    if found:
        return found
    local = TOOLS / exe
    if local.is_file():
        return str(local)
    if not download:
        return ""
    url = PT_URL.get("win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux")
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(TOOLS.parent)
        if sys.platform != "win32":
            os.chmod(local, 0o755)
        return str(local) if local.is_file() else ""
    except Exception:
        return ""


def _run(args: list[str], timeout: int = 20, binary: bool = False):
    exe = adb_path()
    if not exe:
        return 1, (b"" if binary else "adb indirilemedi (internet?)")
    try:
        r = subprocess.run([exe, *args], capture_output=True, timeout=timeout, **_NOWIN)
        if binary:
            return r.returncode, r.stdout
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, (b"" if binary else "zaman aşımı")
    except Exception as exc:
        return 1, (b"" if binary else str(exc))


# ── devices ──────────────────────────────────────────────────────────────────

def devices() -> dict:
    return _load().get("devices", {})


def resolve(name: str = "") -> tuple[str, dict] | tuple[None, None]:
    """('projeksiyon', {ip, ...}) for a name or kind; the only/last one when empty."""
    devs = devices()
    if not devs:
        return None, None
    n = str(name or "").casefold().strip()
    if n:
        for k, v in devs.items():
            if n in k.casefold() or k.casefold() in n or n in str(v.get("model", "")).casefold():
                return k, v
        kind = "tv" if any(w in n for w in ("tv", "televizyon")) else "projector" if "projek" in n else ""
        for k, v in devs.items():
            if kind and v.get("kind") == kind:
                return k, v
    last = _load().get("last")
    if last in devs:
        return last, devs[last]
    k = next(iter(devs))
    return k, devs[k]


def connect(ip: str) -> tuple[bool, str]:
    target = ip if ":" in ip else f"{ip}:5555"
    code, out = _run(["connect", target], timeout=15)
    ok = code == 0 and ("connected" in out.lower()) and "failed" not in out.lower() and "unable" not in out.lower()
    if ok:
        code2, state = _run(["-s", target, "get-state"], timeout=8)
        if "unauthorized" in state.lower() or code2 != 0:
            return False, ("Projeksiyonun ekranında 'USB hata ayıklamaya izin verilsin mi?' çıktı; kumandayla "
                           "'Her zaman izin ver'i işaretleyip Tamam'a bas, sonra tekrar dene.")
    return ok, out


def _target(name: str = "") -> tuple[str | None, str]:
    key, dev = resolve(name)
    if not dev:
        return None, ("Kayıtlı projeksiyon/TV yok. Önce kur: projeksiyonun IP adresini söyle "
                      "(Ayarlar → Ağ → bağlı Wi-Fi'de görünür).")
    target = dev["ip"] if ":" in dev["ip"] else f"{dev['ip']}:5555"
    state_code, state = _run(["-s", target, "get-state"], timeout=6)
    if state_code != 0 or "device" not in state:
        ok, msg = connect(dev["ip"])
        if not ok:
            return None, f"{key} bağlanamadı: {msg}"
    d = _load()
    d["last"] = key
    _save(d)
    return target, key


def shell(cmd: str, name: str = "", timeout: int = 20) -> tuple[bool, str]:
    target, info = _target(name)
    if not target:
        return False, info
    code, out = _run(["-s", target, "shell", cmd], timeout=timeout)
    return code == 0, out


def learn(name: str, ip: str, kind: str = "projector") -> tuple[bool, str]:
    """Connect and learn the device: model, maker, Android, screen, apps."""
    ok, msg = connect(ip)
    if not ok:
        return False, msg
    target = ip if ":" in ip else f"{ip}:5555"

    def sh(c):
        return _run(["-s", target, "shell", c], timeout=20)[1]
    info = {"ip": ip, "kind": kind, "model": sh("getprop ro.product.model"),
            "maker": sh("getprop ro.product.manufacturer"), "android": sh("getprop ro.build.version.release"),
            "chip": sh("getprop ro.board.platform") or sh("getprop ro.hardware"),
            "screen": sh("wm size").replace("Physical size:", "").strip()}
    pk = sh("pm list packages -3") + "\n" + sh("pm list packages -s")
    pkgs = sorted({ln.split(":", 1)[1].strip() for ln in pk.splitlines() if ln.startswith("package:")})
    info["apps"] = [p for p in pkgs if not p.startswith(("com.android.providers", "android.", "com.android.internal"))][:300]
    info["learned"] = time.strftime("%Y-%m-%d %H:%M")
    d = _load()
    d.setdefault("devices", {})[name] = info
    d["last"] = name
    _save(d)
    known = [w for w, cands in APPS.items() if any(c in info["apps"] for c in cands)]
    return True, (f"{name} öğrenildi: {info['maker']} {info['model']}, Android {info['android']}, işlemci {info['chip']}, "
                  f"ekran {info['screen']}, {len(info['apps'])} uygulama" + (f" (tanıdıklarım: {', '.join(known)})" if known else "") + ".")


# ── what AETHER does with it ─────────────────────────────────────────────────

def press(key: str, name: str = "", times: int = 1) -> tuple[bool, str]:
    k = KEY_WORDS.get(str(key).casefold().strip(), str(key).casefold().strip())
    code = KEYS.get(k)
    if code is None:
        return False, f"Bilinmeyen tuş: {key}"
    ok, out = True, ""
    for _ in range(max(1, min(20, int(times or 1)))):
        ok, out = shell(f"input keyevent {code}", name)
        if not ok:
            break
    return ok, (f"{k} tuşuna basıldı." if ok else out)


def _ascii(text: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    return str(text).translate(tr)


def type_text(text: str, name: str = "", enter: bool = False) -> tuple[bool, str]:
    """Type into the field that has focus (Turkish letters are written without
    their marks — Android's input tool takes plain letters only)."""
    t = _ascii(text)
    t = re.sub(r"([\\\"'`$&|;<>()*?!#~{}\[\]])", r"\\\1", t).replace(" ", "%s")
    ok, out = shell(f"input text \"{t}\"", name)
    if ok and enter:
        shell("input keyevent 66", name)
    return ok, ("Yazıldı." if ok else out)


def open_url(url: str, name: str = "") -> tuple[bool, str]:
    if not re.match(r"^https?://", url or ""):
        return False, "Geçerli bir adres değil."
    safe = url.replace("&", "\\&").replace("'", "%27")
    ok, out = shell(f"am start -a android.intent.action.VIEW -d '{safe}'", name)
    return ok and "Error" not in out, ("Açıldı." if ok and "Error" not in out else out)


def open_app(app: str, name: str = "") -> tuple[bool, str]:
    key, dev = resolve(name)
    apps = (dev or {}).get("apps") or []
    a = str(app).casefold().strip()
    cands = APPS.get(a) or next((v for k, v in APPS.items() if k in a), [])
    pkg = next((c for c in cands if not apps or c in apps), None)
    if not pkg:                                   # not a known one: look in what is installed
        pkg = next((p for p in apps if a.replace(" ", "") in p.casefold()), None)
    if not pkg:
        return False, f"'{app}' uygulaması bu cihazda bulunamadı."
    ok, out = shell(f"monkey -p {pkg} -c android.intent.category.LEANBACK_LAUNCHER 1", name)
    if not ok or "No activities" in out:
        ok, out = shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1", name)
    return ok and "No activities" not in out, (f"{app} açıldı." if ok and "No activities" not in out else out)


def search(query: str, where: str = "youtube", name: str = "") -> tuple[bool, str]:
    from urllib.parse import quote_plus
    w = str(where or "youtube").casefold()
    if "youtube" in w:
        key, dev = resolve(name)
        if "com.google.android.youtube.tv" in ((dev or {}).get("apps") or []):
            ok, out = shell("am start -a android.intent.action.SEARCH -n com.google.android.youtube.tv/"
                            f"com.google.android.apps.youtube.tv.activity.ShellActivity --es query '{_ascii(query)}'", name)
            if ok and "Error" not in out:
                return True, f"YouTube'da '{query}' aranıyor."
        return open_url(f"https://www.youtube.com/results?search_query={quote_plus(query)}", name)
    return open_url(f"https://www.google.com/search?q={quote_plus(query)}", name)


def wifi(ssid: str, password: str = "", name: str = "") -> tuple[bool, str]:
    sec = "wpa2" if password else "open"
    pw = f" '{password}'" if password else ""
    ok, out = shell(f"cmd wifi connect-network '{ssid}' {sec}{pw}", name, timeout=30)
    if ok and "rror" not in out:
        return True, f"'{ssid}' ağına bağlanıyor."
    shell("svc wifi enable", name)
    return False, f"Wi-Fi bağlanamadı: {out[:200]}"


def screenshot(name: str = "") -> tuple[bytes | None, str]:
    target, info = _target(name)
    if not target:
        return None, info
    code, data = _run(["-s", target, "exec-out", "screencap", "-p"], timeout=25, binary=True)
    if code != 0 or not data or not data.startswith(b"\x89PNG"):
        return None, "Ekran görüntüsü alınamadı."
    return data, info


def now_playing(name: str = "") -> str:
    ok, out = shell("dumpsys activity activities | grep -m1 -E 'mResumedActivity|topResumedActivity'", name)
    m = re.search(r"([a-z][\w.]+)/", out or "")
    return m.group(1) if m else ""
