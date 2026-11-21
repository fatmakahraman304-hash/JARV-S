"""
Bilgisayardan başka bir cihaza gönder: "bu resmi televizyonda göster", "haritayı
telefonuma aç", "kodu tablete at", "telefona 'çıkıyorum' yaz".

Gönderilen şey ortak gist'teki o cihazın gelen kutusuna gider (core/sync_hub.
send_to_device); telefondaki/TV'deki MAYK sayfası birkaç saniye içinde alır ve
açar, gösterir ya da söyler (web/app.js runInbox).
"""

import base64
import mimetypes
from pathlib import Path

PLUGIN = {
    "name": "send_to_device",
    "description": (
        "Bilgisayardan telefona, tablete, TV'ye, projeksiyona ya da saate bir şey gönder veya orada aç: "
        "'resmi televizyonda göster', 'bu videoyu TV'de aç', 'kodu telefonuma gönder', 'tablete yaz', "
        "'telefona söyle'. what: open (bağlantı/video/harita, url gerekli) | image (son çizilen ya da "
        "verilen resim) | code | text | say (o cihaz sesli söylesin) | ring (\'telefonumu bul\': o cihaz yüksek sesle çalar) | guard_on / guard_off (o cihazın "
        "kamerası güvenlik modunda odayı izlesin; hareket olunca fotoğraf gelir). device: cihazın adı ya da türü."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "device": {"type": "STRING", "description": "telefon, tablet, tv, projeksiyon, saat ya da cihazın adı"},
            "what": {"type": "STRING", "description": "open | image | code | text | say | ring | guard_on | guard_off"},
            "url": {"type": "STRING", "description": "open için adres"},
            "text": {"type": "STRING", "description": "code / text / say için içerik"},
            "title": {"type": "STRING", "description": "kısa başlık ya da dosya adı"},
            "image_path": {"type": "STRING", "description": "image için dosya; boşsa son çizilen resim"},
        },
        "required": ["device", "what"],
    },
}

MAX_IMAGE_BYTES = 2_500_000


def _image_cmd(path_text: str, title: str) -> tuple[dict | None, str]:
    from core import image_studio
    path = Path(path_text) if path_text else image_studio.last_image()
    if not path or not Path(path).is_file():
        return None, "Gönderilecek bir resim yok; önce bir resim çizeyim mi?"
    entry = image_studio.history_entry(path)
    cmd = {"kind": "image", "title": title or entry.get("prompt", "")[:80], "prompt": entry.get("prompt", ""),
           "en": entry.get("en", ""), "seed": entry.get("seed", 0)}
    if entry.get("url"):                       # free painter: the link is enough, and small
        cmd.update(url=entry["url"], mime="image/jpeg")
        return cmd, ""
    data = Path(path).read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        return None, "Resim göndermek için çok büyük (2,5 MB üstü)."
    cmd.update(data=base64.b64encode(data).decode(), mime=mimetypes.guess_type(str(path))[0] or "image/png")
    return cmd, ""


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        p = parameters or {}
        device = str(p.get("device") or "").strip()
        what = str(p.get("what") or "open").strip().lower()
        title = str(p.get("title") or "").strip()
        text = str(p.get("text") or "")
        if not device:
            return "Hangi cihaza göndereyim?"
        if what == "image":
            cmd, err = _image_cmd(str(p.get("image_path") or "").strip(), title)
            if cmd is None:
                return err
        elif what == "open":
            url = str(p.get("url") or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                return "Açmak için geçerli bir adres lazım."
            cmd = {"kind": "open", "url": url, "title": title}
        elif what in ("ring", "find", "bul"):
            cmd = {"kind": "ring"}
        elif what in ("guard_on", "guard_off", "guard"):
            cmd = {"kind": "guard", "on": what != "guard_off"}
        elif what in ("code", "text", "say"):
            if not text.strip():
                return "Ne göndereyim?"
            cmd = {"kind": what, "text": text[:200_000], "title": title, "filename": title or ("kod.txt" if what == "code" else "not.txt")}
        else:
            return "Ne göndereceğimi anlamadım: open, image, code, text, say, guard_on ya da guard_off olmalı."
        ok, msg = sync_hub.send_to_device(device, cmd)
        if player and ok:
            try:
                player.write_log(f"MAYK: {msg}")
            except Exception:
                pass
        return msg
    except Exception as exc:
        return f"Cihaza gönderemedim: {exc}"
