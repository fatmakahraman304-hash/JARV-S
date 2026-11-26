"""
core/image_studio.py — FRIDAY draws and edits pictures itself.

No extra app, no ComfyUI, no download: Gemini's own image models ("Nano
Banana") make the picture from a description, and change an existing picture
from an instruction ("make the sky purple", "add a hat", "remove the text").
The same key the voice already uses; the same models the web app calls on the
phone and TV (web/app.js), so a picture can be made anywhere.

Gemini's image models have NO free quota (Google answers "429 ... limit: 0"
until billing is turned on for the key). So when they cannot draw, FRIDAY
still draws: Gemini's free text model turns the request into a detailed
English picture description and a free, keyless image service (Pollinations,
FLUX) paints it. An edit on that path re-paints the same scene from the same
seed with the change worked into the description. While Gemini says "no
quota" it is not asked again for a few hours, so pictures come quickly.

Every picture is saved under Pictures/FRIDAY. The last one is remembered across
restarts (config/image_studio.json), so "change it" works the next day too.

Standard library only; nothing raises — callers get (path | None, message).
"""

from __future__ import annotations

import base64
import json
import random
import mimetypes
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_STATE = BASE_DIR / "config" / "image_studio.json"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Best first. A model this key cannot use (404/403) or that is out of quota is
# skipped and the next one answers.
MODELS = ("gemini-3.1-flash-image", "gemini-3-pro-image", "gemini-3-pro-image-preview",
          "gemini-2.5-flash-image")
FREE_API = "https://image.pollinations.ai/prompt/{prompt}"
NO_QUOTA_REST = 6 * 3600          # don't re-ask a key with no image quota for 6 hours
ASPECTS = ("1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


def out_dir() -> Path:
    for base in (Path.home() / "Pictures", Path.home() / "Resimler", Path.home() / "Desktop", BASE_DIR):
        if base.exists():
            d = base / "FRIDAY"
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


def _state() -> dict:
    try:
        data = json.loads(_STATE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(data: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def last_image() -> Path | None:
    try:
        p = Path(_state().get("last", ""))
        return p if p.is_file() else None
    except Exception:
        return None


def _remember(path: Path, prompt: str, **extra) -> None:
    data = _state()
    hist = [h for h in data.get("history", []) if isinstance(h, dict)][-19:]
    entry = {"path": str(path), "prompt": prompt[:300], "ts": time.strftime("%Y-%m-%d %H:%M")}
    entry.update({k: v for k, v in extra.items() if v not in (None, "")})
    hist.append(entry)
    data.update({"last": str(path), "history": hist})
    _save_state(data)


def _entry_for(path: str | Path) -> dict:
    want = str(path)
    for h in reversed(_state().get("history", [])):
        if isinstance(h, dict) and h.get("path") == want:
            return h
    return {}


def gemini_resting() -> bool:
    """True while the key is known to have no Gemini image quota."""
    try:
        return float(_state().get("gemini_no_quota_until", 0)) > time.time()
    except (TypeError, ValueError):
        return False


def _rest_gemini(on: bool) -> None:
    data = _state()
    if on:
        data["gemini_no_quota_until"] = time.time() + NO_QUOTA_REST
    else:
        data.pop("gemini_no_quota_until", None)
    _save_state(data)


def _no_quota(err: str) -> bool:
    """The key has no image quota at all (free tier "limit: 0") or the model is
    not open to it — not a passing per-minute limit."""
    e = err.lower()
    return ("limit: 0" in e or "free_tier" in e or "billing" in e
            or e.startswith(("403", "404")) or ": 403" in e or ": 404" in e)


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


def _size(aspect: str) -> tuple[int, int]:
    try:
        a, b = (int(x) for x in aspect.split(":"))
        if a <= 0 or b <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        return 1024, 1024
    if a >= b:
        w, h = 1024, 1024 * b / a
    else:
        w, h = 1024 * a / b, 1024
    return int(round(w / 64) * 64) or 64, int(round(h / 64) * 64) or 64


def describe(prompt: str, base: str = "") -> str:
    """Gemini's free text model writes the English picture description the
    free painter understands best. `base` is the description of the picture
    being changed. Falls back to the user's own words."""
    if base:
        ask = ("You rewrite image-generation prompts. Here is the prompt of an existing picture:\n"
               f"{base}\n\nThe user wants this change (any language): {prompt}\n"
               "Write the full new prompt in English: keep everything about the picture the same "
               "(subject, composition, style, colours, lighting) except what the change asks. "
               "Answer with the prompt only, at most 90 words.")
    else:
        ask = ("Turn this picture request (any language) into one vivid English prompt for an image "
               "generator: subject, setting, style, lighting, composition. Keep any text the user "
               "wants written in the picture exactly as given, in quotes. Answer with the prompt "
               f"only, at most 80 words.\n\nRequest: {prompt}")
    try:
        from core import gemini
        out = gemini.text(ask, timeout_ms=30000, default="")
    except Exception:
        out = ""
    out = re.sub(r"^(prompt|new prompt)\s*:\s*", "", (out or "").strip().strip('"'), flags=re.I)
    if 10 <= len(out) <= 1500:
        return out
    return f"{base}. Change: {prompt}" if base else prompt


def free_url(prompt_en: str, aspect: str, seed: int) -> str:
    """The free painter's address for this picture. The same prompt, size and
    seed give the same picture, so other devices can open it from this link."""
    w, h = _size(aspect)
    q = urllib.parse.urlencode({"width": w, "height": h, "seed": seed, "model": "flux",
                                "nologo": "true", "enhance": "false", "referrer": "aether"})
    return FREE_API.format(prompt=urllib.parse.quote(prompt_en[:1500], safe="")) + "?" + q


def history_entry(path: str | Path) -> dict:
    """What is remembered about a saved picture (prompt, and for the free
    painter its link and seed)."""
    return dict(_entry_for(path))


def _free_call(prompt_en: str, aspect: str, seed: int) -> tuple[bytes | None, str, str]:
    """(image bytes, mime, error) from the free, keyless painter."""
    url = free_url(prompt_en, aspect, seed)
    req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY/1.0", "Accept": "image/*"})
    ctx = None
    try:
        from core import tls
        ctx = tls.context()
    except Exception:
        ctx = None
    err = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=150, context=ctx) as r:
                mime = (r.headers.get("Content-Type") or "").split(";")[0].strip()
                data = r.read()
            if mime.startswith("image/") and len(data) > 1000:
                return data, mime, ""
            err = f"no picture came back ({mime or 'unknown'})"
        except urllib.error.HTTPError as e:
            err = f"{e.code} {e.reason}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except Exception as exc:
            err = str(exc)[:200]
        time.sleep(16 if "429" in err else 4)   # anonymous use: one picture every ~15 s
    return None, "", err


def make(prompt: str, *, edit_from: str | Path | None = None, aspect: str = "",
         models=MODELS) -> tuple[Path | None, str]:
    """Draw a new picture, or change `edit_from` as `prompt` says.
    Returns (saved file | None, message)."""
    prompt = str(prompt or "").strip()
    if not prompt:
        return None, "Ne çizeyim? Bir tarif lazım."
    src = None
    if edit_from:
        src = Path(edit_from)
        if not src.is_file():
            return None, f"Değiştirilecek resim bulunamadı: {src}"
        mime = mimetypes.guess_type(src.name)[0] or "image/png"
        if not mime.startswith("image/"):
            return None, "Bu dosya bir resim değil."

    key = _key()
    errors: list[str] = []
    if key and models and not gemini_resting():
        if src:
            parts = [{"inlineData": {"mimeType": mime, "data": base64.b64encode(src.read_bytes()).decode()}},
                     {"text": "Edit this image: " + prompt + "\nKeep everything else the same unless asked."}]
        else:
            parts = [{"text": prompt}]
        for model in models:
            data, mime_out, info = _call(model, key, parts, aspect)
            if data:
                _rest_gemini(False)
                path = _save(data, mime_out, prompt)
                if not path:
                    return None, "Resim kaydedilemedi."
                _remember(path, prompt, engine=model)
                return path, info.strip()
            errors.append(f"{model}: {info}")
            if not _usable_error(info):
                break             # a refusal or a bad request: another model would refuse too
        last = errors[-1] if errors else ""
        if "blocked" in last or "SAFETY" in last.upper():
            return None, "Bu resmi çizemem; isteği güvenlik kuralları engelledi. Başka türlü tarif eder misin?"
        if errors and all(_no_quota(e) for e in errors):
            _rest_gemini(True)    # "limit: 0": this key has no image quota; stop asking for a while
        print("[Resim] Gemini çizemedi, ücretsiz ressama geçiliyor: " + last[:160].encode("ascii", "replace").decode())

    # ── free path: Gemini (text, free) describes, the keyless painter draws ──
    note = ""
    base, seed = "", random.randint(1, 2_000_000_000)
    if src:
        old = _entry_for(src)
        if old.get("en"):
            base = old["en"]
            seed = int(old.get("seed") or seed)
        else:
            base = old.get("prompt", "")
            note = "Ücretsiz ressam yüklenen bir resmi doğrudan düzenleyemiyor; tarifinle yeniden çizdim."
    prompt_en = describe(prompt, base) if (key or base) else prompt
    data, mime_out, err = _free_call(prompt_en, aspect, seed)
    if not data:
        why = "; ".join(errors[-1:] + [f"ücretsiz ressam: {err}"])
        return None, "Resim üretilemedi (" + why[:240] + "). Biraz sonra tekrar deneyeyim mi?"
    path = _save(data, mime_out, prompt)
    if not path:
        return None, "Resim kaydedilemedi."
    full_prompt = (_entry_for(src).get("prompt", "") + " → " + prompt) if src else prompt
    _remember(path, full_prompt, en=prompt_en, seed=seed, engine="free", url=free_url(prompt_en, aspect, seed))
    try:
        from core import sync_hub           # into the gallery every device sees
        sync_hub.add_image(full_prompt, free_url(prompt_en, aspect, seed), en=prompt_en, seed=seed)
    except Exception:
        pass
    return path, note


def _save(data: bytes, mime: str, prompt: str) -> Path | None:
    ext = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
    path = out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_{_slug(prompt)}{ext}"
    if path.exists():
        path = path.with_name(path.stem + f"_{random.randint(100, 999)}" + ext)
    try:
        path.write_bytes(data)
        return path
    except OSError:
        return None
