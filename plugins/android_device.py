"""
Projeksiyon / Android TV kontrolü (Magcubic HY320 ve her Android TV kutusu):
uygulama aç, web sayfası aç, YouTube/Google'da ara, odaklı kutuya yazı yaz,
kumanda tuşları, ses, internete (Wi-Fi) bağla, ekranına bak (görüntü + Gemini
ne olduğunu anlatır), AETHER web uygulamasını üzerinde aç ve cihazı tanı.
Bağlantı Wi-Fi üzerinden ADB ile (core/adb_control.py).
"""

import base64
import json
import threading
import time
import urllib.request

PLUGIN = {
    "name": "android_device",
    "description": (
        "Projeksiyonu (HY320) ya da Android TV'yi kontrol et. action: "
        "setup (name, ip, kind projector|tv: bir kez — cihazı bağlar ve a'dan z'ye öğrenir) | info | "
        "app (app: youtube, netflix, chrome, spotify, ayarlar …) | url (url) | search (query, where: youtube|google) | "
        "type (text: odaklı kutuya yazar; enter true ise gönderir) | key (key: home, back, up, down, left, right, ok, "
        "volume_up, volume_down, mute, play_pause, power …; times) | wifi (ssid, password: internete bağlar) | "
        "look (ekranına bakar ve ne olduğunu söyler; question) | aether (AETHER'ı projeksiyonda açar: orada da dinler, "
        "konuşur, araştırır) | apps (yüklü uygulamalar). device: cihazın adı (boşsa son kullanılan)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING"},
            "device": {"type": "STRING", "description": "projeksiyon, salon tv … (boşsa son kullanılan)"},
            "name": {"type": "STRING", "description": "setup: cihaza verilecek ad"},
            "ip": {"type": "STRING", "description": "setup: cihazın IP adresi"},
            "kind": {"type": "STRING", "description": "setup: projector | tv"},
            "app": {"type": "STRING"}, "url": {"type": "STRING"}, "query": {"type": "STRING"},
            "where": {"type": "STRING"}, "text": {"type": "STRING"}, "enter": {"type": "BOOLEAN"},
            "key": {"type": "STRING"}, "times": {"type": "NUMBER"},
            "ssid": {"type": "STRING"}, "password": {"type": "STRING"}, "question": {"type": "STRING"},
        },
        "required": ["action"],
    },
}


def _log(player, text):
    if player:
        try:
            player.write_log(f"AETHER: {text}")
        except Exception:
            pass


def _describe(png: bytes, question: str) -> str:
    """Gemini looks at the projector's screen."""
    try:
        from core import gemini, aether_agent
        key = gemini.api_key()
        if not key:
            return ""
        prompt = ("Bu bir projeksiyon/TV ekranının görüntüsü. Türkçe, kısaca anlat: hangi uygulama açık, ne oynuyor "
                  "ya da ekranda ne var, seçili olan ne." + (f" Ayrıca şunu yanıtla: {question}" if question else ""))
        body = {"contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png).decode()}}, {"text": prompt}]}]}
        for model in aether_agent.gemini_models(key)[:4]:
            if "-pro" in model:
                continue
            try:
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    data=json.dumps(body).encode(), method="POST",
                    headers={"Content-Type": "application/json", "x-goog-api-key": key})
                with urllib.request.urlopen(req, timeout=60) as r:
                    js = json.loads(r.read().decode("utf-8"))
                parts = (js.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if text:
                    return text
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _look(device, question, player):
    from core import adb_control, image_studio
    png, info = adb_control.screenshot(device)
    if not png:
        _log(player, info)
        return
    path = image_studio.out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_projeksiyon.png"
    try:
        path.write_bytes(png)
        if player:
            player.show_image(str(path), f"{info} ekranı")
    except Exception:
        pass
    text = _describe(png, question)
    if player:
        try:
            if text and hasattr(player, "request_say"):
                player.request_say(f"[PROJECTOR SCREEN] {text} | Tell the user this in one or two Turkish sentences.")
            else:
                player.write_log(f"AETHER: {text or 'Ekran görüntüsü ekranda.'}")
        except Exception:
            pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import adb_control as A
        p = parameters or {}
        act = str(p.get("action") or "info").strip().lower()
        dev = str(p.get("device") or "")
        if act == "setup":
            ip = str(p.get("ip") or "").strip()
            if not ip:
                return ("Projeksiyonun IP adresi lazım: projeksiyonda Ayarlar → Ağ → bağlı Wi-Fi'ye gir, IP'yi oku. "
                        "Önce Ayarlar → Diğer Ayarlar → Geliştirici seçenekleri'nden USB/ADB hata ayıklamayı aç.")
            name = str(p.get("name") or ("Projeksiyon" if "tv" not in str(p.get("kind") or "") else "TV")).strip()
            ok, msg = A.learn(name, ip, "tv" if "tv" in str(p.get("kind") or "").lower() else "projector")
            return msg
        if act == "info":
            key, d = A.resolve(dev)
            if not d:
                return "Kayıtlı projeksiyon/TV yok; 'projeksiyonu kur' de ve IP adresini söyle."
            playing = A.now_playing(dev)
            return (f"{key}: {d.get('maker', '')} {d.get('model', '')}, Android {d.get('android', '')}, ekran {d.get('screen', '')}, "
                    f"IP {d.get('ip')}, {len(d.get('apps') or [])} uygulama" + (f"; şu an açık: {playing}" if playing else "") + ".")
        if act == "apps":
            key, d = A.resolve(dev)
            known = [w for w, c in A.APPS.items() if any(x in (d or {}).get("apps", []) for x in c)]
            return f"{key} üzerinde: " + (", ".join(known) or "bilinen uygulama yok") + f" (toplam {len((d or {}).get('apps') or [])})."
        if act == "app":
            return A.open_app(str(p.get("app") or ""), dev)[1]
        if act == "url":
            return A.open_url(str(p.get("url") or ""), dev)[1]
        if act == "search":
            return A.search(str(p.get("query") or ""), str(p.get("where") or "youtube"), dev)[1]
        if act == "type":
            return A.type_text(str(p.get("text") or ""), dev, bool(p.get("enter")))[1]
        if act == "key":
            return A.press(str(p.get("key") or ""), dev, int(p.get("times") or 1))[1]
        if act == "wifi":
            if not p.get("ssid"):
                return "Hangi Wi-Fi ağına? Adını ve şifresini söyle."
            return A.wifi(str(p["ssid"]), str(p.get("password") or ""), dev)[1]
        if act == "look":
            threading.Thread(target=_look, args=(dev, str(p.get("question") or ""), player), daemon=True,
                             name="adb-look").start()
            return "Projeksiyonun ekranına bakıyorum; görüntü birazdan ekranda, ne olduğunu söyleyeceğim."
        if act == "aether":
            from core import sync_hub
            key = ""
            try:
                from core import gemini
                key = gemini.api_key()
            except Exception:
                pass
            link = sync_hub.setup_link(key)
            ok, msg = A.open_url(link, dev)
            return ("AETHER projeksiyonda açılıyor: orada da konuşur, araştırır, resim çizer; bilgisayara iş de verebilir. "
                    "İlk açılışta mikrofon izni sorarsa kumandayla izin ver." if ok else msg)
        return "Bilinmeyen işlem."
    except Exception as exc:
        return f"Projeksiyon kontrolü başarısız: {exc}"
