"""
core/image_studio.py — JARVIS draws and edits pictures itself.

No extra app, no ComfyUI, no download: Gemini's own image models ("Nano
Banana") make the picture from a description, and change an existing picture
from an instruction ("make the sky purple", "add a hat", "remove the text").
The same key the voice already uses; the same models the web app calls on the
phone and TV (web/app.js), so a picture can be made anywhere.

Every picture is saved under Pictures/JARVIS. The last one is remembered across
restarts (config/image_studio.json), so "change it" works the next day too.

Standard library only; nothing raises — callers get (path | None, message).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_STATE = BASE_DIR / "config" / "image_studio.json"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Best first. A model this key cannot use (404/403) or that is out of quota is
# skipped and the next one answers.
MODELS = ("gemini-3.1-flash-image", "gemini-3-pro-image", "gemini-3-pro-image-preview",
          "gemini-2.5-flash-image")
ASPECTS = ("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


def out_dir() -> Path:
    for base in (Path.home() / "Pictures", Path.home() / "Resimler", Path.home() / "Desktop", BASE_DIR):
        if base.exists():
            d = base / "JARVIS"
            try:
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                continue
    d = BASE_DIR / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key() -> str:
    try:
        from core import gemini
        return gemini.api_key()
    except Exception:
        try:
            return json.loads((BASE_DIR / "config" / "api_keys.json").read_text("utf-8")).get("gemini_api_key", "")
        except Exception:
            return ""


def last_image() -> Path | None:
    try:
        p = Path(json.loads(_STATE.read_text("utf-8")).get("last", ""))
        return p if p.is_file() else None
    except Exception:
        return None


def _remember(path: Path, prompt: str) -> None:
    try:
        data = json.loads(_STATE.read_text("utf-8")) if _STATE.exists() else {}
    except Exception:
        data = {}
    hist = [h for h in data.get("history", []) if isinstance(h, dict)][-19:]
    hist.append({"path": str(path), "prompt": prompt[:300], "ts": time.strftime("%Y-%m-%d %H:%M")})
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps({"last": str(path), "history": hist}, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def _slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "_", text.lower(), flags=re.UNICODE).strip("_")
    return (s[:40] or "resim")


def _call(model: str, key: str, parts: list, aspect: str) -> tuple[bytes | None, str, str]:
    """(image bytes, mime, text or error) from one model."""
    gen = {"responseModalities": ["TEXT", "IMAGE"]}
    if aspect in ASPECTS:
        gen["imageConfig"] = {"aspectRatio": aspect}
    body = json.dumps({"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}).encode()
    req = urllib.request.Request(API.format(model=model), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        ctx = None
        try:
            from core import tls
            ctx = tls.context()
        except Exception:
            ctx = None
        with urllib.request.urlopen(req, timeout=180, context=ctx) as r:
            js = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        return None, "", f"{e.code} {msg}"[:300]
    except Exception as exc:
        return None, "", str(exc)[:300]
    text = ""
    for cand in js.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data") and not part.get("thought"):
                return base64.b64decode(inline["data"]), inline.get("mimeType") or "image/png", text
            if part.get("text") and not part.get("thought"):
                text += part["text"]
        reason = cand.get("finishReason", "")
        if reason and reason not in ("STOP", "MAX_TOKENS"):
            text = text or f"model stopped: {reason}"
    block = (js.get("promptFeedback") or {}).get("blockReason")
    return None, "", text or (f"blocked: {block}" if block else "no image in the answer")


def _usable_error(err: str) -> bool:
    """Errors another model may get past (unknown model, quota, overload)."""
    e = err.lower()
    return any(w in e for w in ("404", "403", "429", "quota", "resource_exhausted", "not found",
                                "not supported", "unavailable", "503", "500", "overloaded",
                                "no image in the answer", "deadline", "timed out"))


def make(prompt: str, *, edit_from: str | Path | None = None, aspect: str = "",
         models=MODELS) -> tuple[Path | None, str]:
    """Draw a new picture, or change `edit_from` as `prompt` says.
    Returns (saved file | None, message)."""
    prompt = str(prompt or "").strip()
    if not prompt:
        return None, "Ne çizeyim? Bir tarif lazım."
    key = _key()
    if not key:
        return None, "Gemini anahtarı yok; resim için ayarlardan anahtar gir."
    parts: list = []
    if edit_from:
        src = Path(edit_from)
        if not src.is_file():
            return None, f"Değiştirilecek resim bulunamadı: {src}"
        mime = mimetypes.guess_type(src.name)[0] or "image/png"
        if not mime.startswith("image/"):
            return None, "Bu dosya bir resim değil."
        parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(src.read_bytes()).decode()}})
        parts.append({"text": "Edit this image: " + prompt + "\nKeep everything else the same unless asked."})
    else:
        parts.append({"text": prompt})
    errors = []
    for model in models:
        data, mime, info = _call(model, key, parts, aspect)
        if data:
            ext = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
            path = out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_{_slug(prompt)}{ext}"
            try:
                path.write_bytes(data)
            except OSError as exc:
                return None, f"Resim kaydedilemedi: {exc}"
            _remember(path, prompt)
            return path, info.strip()
        errors.append(f"{model}: {info}")
        if not _usable_error(info):
            break                 # a refusal or a bad request: another model would refuse too
    last = errors[-1] if errors else "bilinmeyen hata"
    if "blocked" in last or "SAFETY" in last.upper():
        return None, "Bu resmi çizemem; isteği güvenlik kuralları engelledi. Başka türlü tarif eder misin?"
    return None, "Resim üretilemedi: " + last[:240]
