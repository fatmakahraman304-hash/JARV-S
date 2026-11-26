"""
Ortak resim galerisi: hangi cihazda çizilmiş olursa olsun son resimler
("dünkü resmi göster", "telefonda çizdiğin resmi aç", "galerimde ne var").
Liste ortak gist'teki images.json'dan gelir (core/sync_hub.gallery); web
uygulamasındaki `gallery` aracı aynı listeyi kullanır.
"""

import threading
import time
import urllib.request

PLUGIN = {
    "name": "gallery",
    "description": (
        "Bütün cihazlarda çizilen resimlerin ortak galerisi: 'galerimde ne var', 'dünkü resmi göster', "
        "'telefonda çizdiğin aslan resmini aç', 'üçüncü resmi televizyona gönder'. action: list | show | send. "
        "number: listedeki sıra (1 = en yeni) ya da query: resmin ne olduğu. send için device."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | show | send"},
            "number": {"type": "NUMBER", "description": "1 = en yeni"},
            "query": {"type": "STRING", "description": "resimde ne vardı (aslan, logo …)"},
            "device": {"type": "STRING", "description": "send için hedef cihaz"},
        },
        "required": ["action"],
    },
}


def _pick(items: list[dict], number, query: str) -> dict | None:
    newest = list(reversed(items))
    q = (query or "").casefold().strip()
    if q:
        return next((g for g in newest if q in str(g.get("prompt", "")).casefold()), None)
    try:
        n = int(number or 1)
    except (TypeError, ValueError):
        n = 1
    return newest[n - 1] if 1 <= n <= len(newest) else None


def _show(g: dict, player) -> None:
    try:
        from core import image_studio
        req = urllib.request.Request(g["url"], headers={"User-Agent": "FRIDAY/1.0"})
        with urllib.request.urlopen(req, timeout=150) as r:
            data = r.read()
        path = image_studio.out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_galeri.jpg"
        path.write_bytes(data)
        image_studio._remember(path, g.get("prompt", ""), en=g.get("en", ""), seed=g.get("seed") or None,
                               url=g["url"], engine="free")
        if player:
            player.show_image(str(path), g.get("prompt", "")[:80])
    except Exception as exc:
        if player:
            try:
                player.write_log(f"FRIDAY: Galerideki resim açılamadı: {exc}")
            except Exception:
                pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        p = parameters or {}
        items = sync_hub.gallery()
        if not items:
            return "Galeri boş (ya da cihazlar henüz eşitlenmedi). Bir resim çizeyim mi?"
        action = str(p.get("action") or "list").lower()
        if action == "list":
            newest = list(reversed(items))[:10]
            return "Galeri (en yeni önce):\n" + "\n".join(
                f"{i}. {g.get('prompt', '')[:70]} — {g.get('from', '?')}, {str(g.get('ts', ''))[:16].replace('T', ' ')}"
                for i, g in enumerate(newest, 1))
        g = _pick(items, p.get("number"), str(p.get("query") or ""))
        if not g:
            return "Galeride öyle bir resim bulamadım."
        if action == "send":
            ok, msg = sync_hub.send_to_device(str(p.get("device") or ""), {
                "kind": "image", "url": g["url"], "mime": "image/jpeg", "prompt": g.get("prompt", ""),
                "en": g.get("en", ""), "seed": g.get("seed", 0), "title": g.get("prompt", "")[:80]})
            return msg
        threading.Thread(target=_show, args=(g, player), daemon=True, name="gallery-show").start()
        return f"Açıyorum: {g.get('prompt', '')[:80]} ({g.get('from', '?')} çizmişti)."
    except Exception as exc:
        return f"Galeri açılamadı: {exc}"
