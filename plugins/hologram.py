"""Iron Man 2'deki gibi: "Jarvis, bunu dijital olarak modelle" — tarayıcıda
JARVIS'in hologram masasını açar (web/hologram.html): kamera nesneyi tarar,
3B holografik model çıkar, eller kameraya gösterilerek döndürülür, büyütülür,
parçalara ayrılır."""
from __future__ import annotations

import base64
import json
import webbrowser
from urllib.parse import urlencode

PLUGIN = {
    "name": "hologram",
    "description": (
        "Iron Man tarzı hologram masası: kameraya gösterilen nesneyi 3B holografik modele çevirir; kullanıcı "
        "elleriyle (kameraya göstererek) döndürür, büyütür, parçalarına ayırır, savurup atar. 'bunu dijital olarak "
        "modelle', 'kameradakini tara', 'hologramı aç', 'bana bir Iron Man kaskı modelle' (request), "
        "'elimle kontrol edeyim'. action: scan | make | open. Tarayıcıda açılır."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "scan | make | open"},
        "request": {"type": "STRING", "description": "make için: ne modellenecek"},
        "hands": {"type": "BOOLEAN", "description": "el kontrolü hemen açılsın mı (varsayılan evet)"},
    }, "required": ["action"]},
}


def build_url(action: str, request: str = "", hands: bool = True, setup: dict | None = None) -> str:
    from core import sync_hub
    q = {}
    action = (action or "scan").lower()
    if action == "make" and request.strip():
        q["make"] = request.strip()[:300]
    elif action != "open":
        q["scan"] = "1"
    if hands:
        q["hands"] = "1"
    url = sync_hub.WEB_URL + "hologram.html" + ("?" + urlencode(q) if q else "")
    if setup and setup.get("g"):
        blob = base64.urlsafe_b64encode(json.dumps(setup).encode("utf-8")).decode().rstrip("=")
        url += "#s=" + blob          # the fragment never leaves the browser
    return url


def _setup() -> dict:
    try:
        from core import sync_hub
        from memory.config_manager import get_gemini_key
        s = sync_hub.settings()
        return {"g": get_gemini_key() or "", "t": s.get("github_token", ""), "i": s.get("gist_id", ""), "n": sync_hub._assistant_name()}
    except Exception:
        return {}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        action = str(p.get("action") or "scan")
        url = build_url(action, str(p.get("request") or ""), p.get("hands") is not False, _setup())
        if not webbrowser.open(url):
            return "Tarayıcı açılamadı."
        if player:
            try:
                player.write_log("JARVIS: Hologram masası tarayıcıda açıldı.")
            except Exception:
                pass
        if action.lower() == "make":
            return "Hologram masasını açtım, modeli tasarlıyorum."
        if action.lower() == "open":
            return "Hologram masası açık."
        return ("Hologram masası açılıyor. Kameraya izin ver, nesneyi kameraya göster; geri sayımdan sonra tarayacağım. "
                "Sonra elinle çimdikleyip döndürebilir, avucunu açarak parçalarına ayırabilirsin.")
    except Exception as exc:
        return f"Hologram açılamadı: {exc}"
