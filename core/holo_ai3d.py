"""core/holo_ai3d.py — real 3D models from a photo (or from words), by AI.

The parts model (core/holo_scan.py) is Gemini rebuilding an object from
boxes and curves: good for diagrams, never photo-real. This is the real thing:
open image-to-3D models — Microsoft TRELLIS.2, Tencent Hunyuan3D 2.1 / 2,
Stability Stable Fast 3D, VAST TripoSG — that turn one photo into a textured
mesh with the object's real shape, colours, faces and hands. They run on
Hugging Face's free GPUs; a free Hugging Face token gives a bigger daily quota
(memory/config_manager.get_hf_token). The first that answers wins.

  image_to_3d(path)   a photo → (glb bytes, provider, message)
  text_to_3d(text)    words → a product photo (core/image_studio) → image_to_3d
  measure(...)        Gemini's estimate of the real size and a name/summary

Everything here is slow (30–180 s) and runs on a worker thread.
"""
from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLB_DIR = ROOT / "memory" / "holo_glb"
STEP_TIMEOUT = 300


def _token() -> str:
    try:
        from memory.config_manager import get_hf_token
        return get_hf_token()
    except Exception:
        import os
        return os.environ.get("HF_TOKEN", "")


def _client_lib(log=print):
    try:
        import gradio_client  # noqa: F401
        return True
    except Exception:
        pass
    try:                                                 # first use: install the small client once
        from core.installer import _pip
        if _pip("gradio_client", log=log):
            import importlib
            importlib.invalidate_caches()
            import gradio_client  # noqa: F401
            return True
    except Exception as exc:
        log(f"[Hologram] gradio_client: {exc}")
    return False


def _find_file(res, exts=(".glb", ".gltf", ".obj")) -> str:
    """The model file in whatever shape a Space returned (str, dict, tuple)."""
    found = []

    def walk(x):
        if isinstance(x, str):
            if x.lower().endswith(exts) and Path(x).exists():
                found.append(x)
        elif isinstance(x, dict):
            for k in ("value", "path", "name", "url"):
                if k in x:
                    walk(x[k])
        elif isinstance(x, (list, tuple)):
            for y in x:
                walk(y)
    walk(res)
    if not found:
        return ""
    tex = [f for f in found if "textur" in f.lower()]
    return (tex or found)[-1]


def _call(client, api, timeout=STEP_TIMEOUT, **kw):
    return client.submit(api_name=api, **kw).result(timeout=timeout)


# each provider: (client, image path) -> glb path
def _trellis2(c, img, hf):
    try:
        _call(c, "/start_session", timeout=60)
    except Exception:
        pass
    pre = _call(c, "/preprocess_image", input=hf(img))
    pre = pre if isinstance(pre, str) else _find_file(pre, (".png", ".jpg", ".webp")) or img
    _call(c, "/image_to_3d", image=hf(pre))
    return _find_file(_call(c, "/extract_glb", decimation_target=300000, texture_size=2048))


def _hunyuan21(c, img, hf):
    return _find_file(_call(c, "/generation_all", image=hf(img), steps=30, octree_resolution=256))


def _hunyuan2(c, img, hf):
    return _find_file(_call(c, "/generation_all", caption=None, image=hf(img), steps=30, octree_resolution=256))


def _sf3d(c, img, hf):
    return _find_file(_call(c, "/run_button", input_image=hf(img), foreground_ratio=0.85, texture_size=1024))


def _triposg(c, img, hf):
    mesh = _find_file(_call(c, "/image_to_3d", image=hf(img), target_face_num=200000))
    if not mesh:
        return ""
    try:
        return _find_file(_call(c, "/run_texture", image=hf(img), mesh_path=hf(mesh))) or mesh
    except Exception:
        return mesh                                      # the shape alone is still worth having


PROVIDERS = [
    ("TRELLIS.2", "microsoft/TRELLIS.2", _trellis2),
    ("Hunyuan3D-2.1", "tencent/Hunyuan3D-2.1", _hunyuan21),
    ("Hunyuan3D-2", "tencent/Hunyuan3D-2", _hunyuan2),
    ("Stable Fast 3D", "stabilityai/stable-fast-3d", _sf3d),
    ("TripoSG", "VAST-AI/TripoSG", _triposg),
]


def image_to_3d(image_path: str, progress=None, only: str = "", log=print):
    """(glb bytes | None, provider name, message)."""
    if not _client_lib(log):
        return None, "", "Gerçek 3B için gradio_client kurulamadı."
    from gradio_client import Client, handle_file
    token = _token() or None
    errors = []
    for name, space, fn in PROVIDERS:
        if only and only.lower() != name.lower():
            continue
        if progress:
            progress(f"GERÇEK 3B MODEL — {name} (30–120 sn)…")
        t0 = time.time()
        try:
            try:
                c = Client(space, token=token, verbose=False)          # gradio_client ≥ 1.x
            except TypeError:
                c = Client(space, hf_token=token, verbose=False)       # older releases
            path = fn(c, image_path, handle_file)
            if path and Path(path).stat().st_size > 1000:
                data = Path(path).read_bytes()
                log(f"[Hologram] {name}: {len(data) // 1024} KB in {time.time() - t0:.0f} s")
                return data, name, f"{name} ile oluşturuldu."
            errors.append(f"{name}: dosya gelmedi")
        except Exception as exc:
            msg = f"{type(exc).__name__}: {str(exc)[:160]}"
            errors.append(f"{name}: {msg}")
            log(f"[Hologram] {name} failed: {msg}")
    quota = any("quota" in e.lower() or "zerogpu" in e.lower() for e in errors)
    hint = (" Ücretsiz Hugging Face günlük GPU kotası dolmuş olabilir; ücretsiz bir Hugging Face anahtarı (hf_token) "
            "eklersen kota büyür." if quota or not token else "")
    return None, "", "Gerçek 3B servislerinin hiçbiri yanıt vermedi." + hint


PHOTO_PROMPT = ("{what}. One single object, the whole thing fully visible and centred, three-quarter front view, "
                "plain light grey seamless studio background, soft even studio lighting, sharp focus, photorealistic, "
                "highly detailed, no text, no other objects.")
PERSON_PROMPT = ("{what}. Full body, standing straight in an A-pose (arms slightly away from the body), facing the camera, "
                 "whole figure visible from head to feet, detailed face and hands, plain light grey studio background, "
                 "soft even lighting, photorealistic.")
_PERSON = ("insan", "adam", "kadın", "kız", "erkek", "çocuk", "kişi", "person", "human", "man", "woman", "karakter", "asker",
           "doktor", "polis", "sporcu", "iron man", "süper kahraman")


def reference_image(text: str, edit_from: str = ""):
    """A clean product/figure photo to build the model from. (path | None, message)."""
    from core import image_studio
    t = text.casefold()
    tmpl = PERSON_PROMPT if any(w in t for w in _PERSON) else PHOTO_PROMPT
    prompt = text if edit_from else tmpl.format(what=text)
    path, msg = image_studio.make(prompt, edit_from=edit_from or None, aspect="1:1")
    return (str(path) if path else None), msg


def measure(text: str = "", image_jpeg: bytes = b"") -> dict:
    """Name, one-line summary and the real size (cm) Gemini estimates."""
    from core import gemini
    q = ("Name this object in Turkish, describe it in one Turkish sentence (material, notable details) and estimate its "
         "REAL size in centimetres. Return ONLY JSON: {\"name\": \"\", \"summary\": \"\", \"width_cm\": 0, \"height_cm\": 0, "
         "\"depth_cm\": 0}. Object: " + (text or "the main object in the photo"))
    parts = [q]
    if image_jpeg:
        try:
            from google.genai import types
            parts.append(types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg"))
        except Exception:
            pass
    data = gemini.as_json(parts, tier=gemini.FAST, timeout_ms=40_000) or {}
    return data if isinstance(data, dict) else {}


def save_glb(data: bytes, model_id: str) -> str:
    GLB_DIR.mkdir(parents=True, exist_ok=True)
    path = GLB_DIR / f"{model_id}.glb"
    path.write_bytes(data)
    return str(path)


def build(glb: bytes, provider: str, info: dict, source: str = "", prompt: str = "") -> dict:
    """The model record for the table (geometry stays in the .glb file)."""
    mid = f"h{int(time.time() * 1000):x}"
    path = save_glb(glb, mid)
    h = info.get("height_cm")
    try:
        h = float(h) if h else 0.0
    except (TypeError, ValueError):
        h = 0.0
    return {"name": str(info.get("name") or prompt or "3B model")[:60], "summary": str(info.get("summary") or "")[:400],
            "parts": [], "glb": path, "height_cm": h if 0.5 < h < 5000 else 0.0, "provider": provider,
            "source_image": source, "prompt": prompt, "id": mid, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
