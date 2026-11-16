"""Local installation and command catalog for the pinned God's Eye View app."""

import json
import os
import re
import shutil
import threading
from pathlib import Path

REPOSITORY = "https://github.com/bilawalsidhu/gods-eye-view.git"
REVISION = "3d49ba588f00a497434db893087f5d4462eea988"
ROOT = Path.home() / "JarvisIntegrations" / "gods-eye-view"
CATALOG = ".jarvis-gods-eye.json"
VITE = Path("node_modules/vite/bin/vite.js")
SETUP_HINT = "Kurulum için JARVIS klasöründe python tools/setup_gods_eye.py çalıştır."


def executable(name):
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt" and (program_files := os.environ.get("ProgramFiles")):
        filename = "npm.cmd" if name == "npm" else name + ".exe"
        path = Path(program_files) / "nodejs" / filename
        if path.is_file():
            return str(path)
    return None


def read_catalog(root=None):
    root = ROOT if root is None else root
    try:
        stamp = json.loads((root / CATALOG).read_text(encoding="utf-8"))
        if stamp["revision"] == REVISION:
            tools = {tool["name"]: tool for tool in stamp["tools"]}
            if "fly_to_location" in tools and "get_current_view_state" in tools:
                return tools
    except (OSError, ValueError, TypeError, KeyError):
        pass
    raise ValueError(SETUP_HINT)


def globe_command_for_text(text):
    text = " ".join(text.replace("İ", "i").casefold().replace("’", "'").split()).rstrip(".!?")
    text = re.sub(r"^(?:jarvis|friday)[, ]+", "", text)
    match = re.fullmatch(
        r"(?:god'?s eye view(?:[' ]?[ıiuü])?|3d küre(?:yi)?|3d dünya(?:yı)?) (aç|kapat)", text
    )
    if match:
        return "open" if match[1] == "aç" else "close"
    return None


class Reply:
    """A bounded wait for tool callers; the GUI also logs late results."""

    def __init__(self):
        self._ready = threading.Event()
        self.message = ""

    def finish(self, message):
        self.message = message
        self._ready.set()

    def wait(self, timeout):
        return self.message if self._ready.wait(timeout) else ""
