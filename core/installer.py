"""
JARVIS — Dependency auto-installer.

Called automatically on first launch and after engine reconfiguration.
Installs only the packages that are actually missing, then exits cleanly.
"""
from __future__ import annotations

import importlib.util
import platform
import subprocess
import sys
from typing import Callable

# ── Package lists ─────────────────────────────────────────────────────────
# Each entry: (import_name, pip_package_name)

_CORE: list[tuple[str, str]] = [
    ("psutil",             "psutil"),
    ("PIL",                "pillow"),
    ("sounddevice",        "sounddevice"),
    ("numpy",              "numpy"),
    ("requests",           "requests"),
    ("bs4",                "beautifulsoup4"),
    ("ddgs",               "ddgs"),
    ("pyautogui",          "pyautogui"),
    ("pyperclip",          "pyperclip"),
    ("pygetwindow",        "pygetwindow"),
    ("mss",                "mss"),
    ("cv2",                "opencv-python"),
    ("soundfile",          "soundfile"),
    ("miniaudio",          "miniaudio"),
    ("send2trash",         "send2trash"),
    ("pptx",               "python-pptx"),
    ("youtube_transcript_api", "youtube-transcript-api"),
]

# Windows-only (pywinauto, pycaw, win10toast, comtypes)
_WINDOWS: list[tuple[str, str]] = [
    ("comtypes",   "comtypes"),
    ("pycaw",      "pycaw"),
    ("win10toast", "win10toast"),
    ("pywinauto",  "pywinauto"),
]

# STT engine packages
_STT: dict[str, list[tuple[str, str]]] = {
    "whisper": [("faster_whisper", "faster-whisper")],
    "vosk":    [("vosk",           "vosk")],
}

# TTS engine packages
_TTS: dict[str, list[tuple[str, str]]] = {
    "edgetts":    [("edge_tts", "edge-tts")],
    # kokoro>=0.9 dropped AlbertModel/AutoModel from transformers — version pin is critical
    "kokoro":     [("kokoro",   "kokoro>=0.9"), ("soundfile", "soundfile")],
    "elevenlabs": [],   # uses only requests, already in core
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _available(module: str) -> bool:
    """Return True if the module can be imported (no actual import)."""
    return importlib.util.find_spec(module) is not None


def _pip(package: str, log: Callable | None = None) -> bool:
    if log:
        log(f"SYS: pip install {package} …")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "install", package,
            "--quiet", "--disable-pip-version-check",
        ],
        capture_output=True,
    )
    ok = result.returncode == 0
    if not ok and log:
        stderr = result.stderr.decode(errors="replace").strip()
        log(f"ERR: {package} install failed — {stderr[:140]}")
    return ok


# ── Public API ────────────────────────────────────────────────────────────

def install_for_config(config: dict, log: Callable | None = None) -> None:
    """
    Install all missing packages required by *config*.

    Blocking — always call from a background thread.
    Progress is reported via the optional *log* callback (receives a str).
    """
    stt = config.get("stt_engine", "whisper").lower()
    tts = config.get("tts_engine", "edgetts").lower()

    needed: list[tuple[str, str]] = list(_CORE)
    needed += _STT.get(stt, [])
    needed += _TTS.get(tts, [])
    if platform.system() == "Windows":
        needed += _WINDOWS

    # Deduplicate (preserve order, key = pip name)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for mod, pkg in needed:
        if pkg not in seen:
            seen.add(pkg)
            unique.append((mod, pkg))

    missing = [(mod, pkg) for mod, pkg in unique if not _available(mod)]

    if not missing:
        if log:
            log("SYS: All dependencies already installed ✓")
        return

    pkg_names = ", ".join(p for _, p in missing)
    if log:
        log(f"SYS: Installing {len(missing)} package(s): {pkg_names}")

    for _mod, pkg in missing:
        _pip(pkg, log)

    # Playwright: install the package + download Chromium browser
    if not _available("playwright"):
        _pip("playwright", log)
        if log:
            log("SYS: Downloading Playwright browser (Chromium, ~150 MB — one-time)…")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
        )
        if log:
            log("SYS: Playwright browser ready.")

    if log:
        log("SYS: All dependencies ready ✓")


# ── Missing packages found while working ──────────────────────────────────
# A tool that fails because a library is missing says "pip install X". JARVIS
# offers to install it — but only a package JARVIS itself depends on (the lists
# above or requirements.txt): a tool result is text, and text must never be able
# to make the assistant install an arbitrary package.

def known_packages() -> set[str]:
    import re
    from pathlib import Path
    names = {pkg for _m, pkg in _CORE + _WINDOWS}
    for group in (_STT, _TTS):
        for items in group.values():
            names |= {pkg for _m, pkg in items}
    try:
        req = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8")
        for line in req.splitlines():
            m = re.match(r"\s*([A-Za-z0-9_.\-\[\]]+)", line.split("#")[0])
            if m:
                names.add(m.group(1))
    except OSError:
        pass
    return {_base(n) for n in names}


def _base(pkg: str) -> str:
    import re
    return re.split(r"[<>=!~\[ ]", pkg.strip().lower(), maxsplit=1)[0].replace("_", "-")


def missing_package(text: str) -> str:
    """The package a tool result asks for ('pip install pyautogui'), if JARVIS may install it; else ''."""
    import re
    m = re.search(r"pip install ([A-Za-z0-9_.\-\[\]<>=]+)", str(text or ""))
    if not m:
        return ""
    pkg = m.group(1).strip(".,;:'\"")
    return pkg if _base(pkg) in known_packages() else ""


def install(pkg: str, log: Callable | None = None) -> tuple[bool, str]:
    if _base(pkg) not in known_packages():
        return False, f"'{pkg}' JARVIS'in kendi paketlerinden değil; güvenlik için kurmuyorum."
    ok = _pip(pkg, log)
    importlib.invalidate_caches()
    return ok, (f"'{pkg}' kuruldu." if ok else f"'{pkg}' kurulamadı (pip hata verdi).")
