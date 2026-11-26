"""Explicit Realtime preview settings; never share another provider's key."""
from __future__ import annotations

from .realtime_transport import MODELS, session_event

PROVIDER_ID = "openai_realtime"
VOICES = ("marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")


def enabled(value):
    return value is True or str(value).strip().lower() in ("1", "true")


def validate_settings(cfg):
    key = str(cfg.get("api_key") or "").strip()
    model = str(cfg.get("model") or MODELS[0]).strip()
    voice = str(cfg.get("voice_id") or VOICES[0]).strip()
    if not enabled(cfg.get("cloud_consent")):
        raise ValueError("Realtime bulut aktarım onayı gerekli.")
    if not key or any(c.isspace() for c in key):
        raise ValueError("Ayrı OpenAI API anahtarı gerekli.")
    if model not in MODELS:
        raise ValueError("Desteklenen Realtime modeli gerekli.")
    session_event(voice)
    return {"api_key": key, "model": model, "voice": voice,
            "microphone": enabled(cfg.get("microphone")),
            "volume_control": enabled(cfg.get("volume_control"))}


def check_dependency():
    from importlib.metadata import version, PackageNotFoundError
    from packaging.version import Version
    try:
        if Version(version("websockets")) >= Version("15"):
            return
    except PackageNotFoundError:
        pass
    raise RuntimeError("Realtime için websockets>=15 gerekli.")
