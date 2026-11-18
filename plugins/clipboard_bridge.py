"""Bilgisayarın panosundakini telefona/tablete/TV'ye gönder: bağlantıysa orada
açılır, yazıysa ekranda görünür."""
from __future__ import annotations

import re

PLUGIN = {
    "name": "clipboard_bridge",
    "description": (
        "Bilgisayarda kopyalanan şeyi başka cihaza gönder: 'panodakini telefona gönder', 'kopyaladığım linki "
        "TV'de aç', 'bunu tablete at'. device: cihazın adı ya da türü (varsayılan telefon). "
        "Bağlantı o cihazda açılır; yazı ya da kod ekranında gösterilir."
    ),
    "parameters": {"type": "OBJECT", "properties": {"device": {"type": "STRING"}}},
}

URL = re.compile(r"^\s*(https?://\S+)\s*$", re.I)
CODE_HINT = re.compile(r"(def |class |function |import |#include|\{\s*$|;\s*$|=>)", re.M)


def command_for(text: str) -> dict | None:
    """What to send for this clipboard text."""
    text = (text or "").strip()
    if not text:
        return None
    m = URL.match(text)
    if m:
        return {"kind": "open", "url": m.group(1), "title": "Panodaki bağlantı"}
    kind = "code" if CODE_HINT.search(text) and "\n" in text else "text"
    return {"kind": kind, "text": text[:200_000], "title": "Bilgisayarın panosu",
            "filename": "pano.txt" if kind == "text" else "kod.txt"}


def read_clipboard() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        from plugins import pc_extra
        out = pc_extra.clipboard("read", "")
        return out[len("Panoda: "):] if out.startswith("Panoda: ") else ""


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        device = str((parameters or {}).get("device") or "telefon").strip()
        cmd = command_for(read_clipboard())
        if cmd is None:
            return "Pano boş; önce bir şey kopyala."
        ok, msg = sync_hub.send_to_device(device, cmd)
        if not ok:
            return msg
        what = "bağlantıyı" if cmd["kind"] == "open" else "kodu" if cmd["kind"] == "code" else "yazıyı"
        return f"Panodaki {what} gönderdim: {msg}"
    except Exception as exc:
        return f"Panoyu gönderemedim: {exc}"
