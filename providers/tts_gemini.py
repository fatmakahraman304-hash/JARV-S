"""Optional Gemini 3.8 TTS over the documented Interactions REST API.

Uses a dedicated key and sends only the text to speak. No automatic cloud
fallback, no SDK upgrade, no changes to the Gemini Live session.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import wave
from importlib.util import find_spec

from .base import DEFAULT_CAPS, Field

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELS = ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts")
VOICES = ("Kore", "Aoede", "Charon", "Puck", "Zephyr", "Leda", "Orus", "Sulafat")
MAX_TEXT = 4000
MAX_PCM = 24_000 * 2 * 300
MAX_RESPONSE = 24 * 1024 * 1024


def _decode_audio(payload: dict) -> bytes:
    """Read the last audio output; validate WAV before exposing samples."""
    data = None
    for step in payload.get("steps", []):
        if isinstance(step, dict) and step.get("type") == "model_output":
            for part in step.get("content", []):
                if isinstance(part, dict) and part.get("type") == "audio":
                    data = part.get("data")
    if not isinstance(data, str) or not data or len(data) > MAX_RESPONSE:
        raise RuntimeError("Gemini ses verisi yok veya boyutu geçersiz.")
    try:
        raw = base64.b64decode(data, validate=True)
        with wave.open(io.BytesIO(raw), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, "NONE"):
                raise ValueError("Unexpected WAV format")
            frames = wav.getnframes()
            if not 0 < frames * 2 <= MAX_PCM:
                raise ValueError("Invalid WAV size")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError("Truncated WAV")
    except (wave.Error, EOFError, ValueError, binascii.Error) as exc:
        raise RuntimeError("Gemini geçerli 24 kHz mono PCM/WAV döndürmedi.") from None
    return pcm


class GeminiTTS:
    def __init__(self, cfg: dict):
        self.key = str(cfg.get("api_key") or "").strip()
        self.model = str(cfg.get("model") or MODELS[0]).strip()
        self.voice_id = str(cfg.get("voice_id") or "Kore").strip()
        self.caps = dict(DEFAULT_CAPS, audio_out=True)

    def _payload(self, text: str, voice: str = "") -> dict:
        chosen = (voice or self.voice_id).strip()
        if self.model not in MODELS or chosen not in VOICES:
            raise ValueError("Desteklenen Gemini TTS modelini ve sesini seçin.")
        if not text or len(text) > MAX_TEXT:
            raise ValueError("Gemini TTS metin sınırı 1–4000 karakter.")
        return {
            "model": self.model,
            "input": [{"type": "user_input", "content": [
                {"type": "text", "text": text}
            ]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": chosen}]},
        }

    def _headers(self) -> dict:
        if not self.key:
            raise RuntimeError("Gemini TTS API anahtarı gerekli.")
        return {"x-goog-api-key": self.key}

    @staticmethod
    def _status(response):
        if not 200 <= response.status_code < 300:
            # Never echo provider response bodies, credentials or transcript.
            raise RuntimeError(f"Gemini TTS HTTP {response.status_code}")

    @staticmethod
    def _parse(raw: bytes) -> bytes:
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Invalid response")
            return _decode_audio(payload)
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError("Gemini TTS yanıt biçimi geçersiz.") from None

    async def speak(self, text: str, voice: str = ""):
        import httpx

        text = (text or "").strip()
        if not text:
            return
        payload, headers = self._payload(text, voice), self._headers()
        raw = bytearray()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5),
                                         follow_redirects=False, trust_env=False) as client:
                async with client.stream("POST", URL, json=payload, headers=headers) as response:
                    self._status(response)
                    async for part in response.aiter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_RESPONSE:
                            raise RuntimeError("Gemini TTS yanıt boyutu sınırı aşıldı.")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gemini TTS bağlantı hatası ({type(exc).__name__}).") from None
        pcm = self._parse(raw)
        for offset in range(0, len(pcm), 2400):
            yield pcm[offset:offset + 2400]

    def probe(self) -> tuple[bool, str]:
        import httpx

        try:
            raw = bytearray()
            with httpx.Client(timeout=httpx.Timeout(20, connect=5),
                              follow_redirects=False, trust_env=False) as client:
                with client.stream("POST", URL, json=self._payload("Merhaba."),
                                   headers=self._headers()) as response:
                    self._status(response)
                    for part in response.iter_bytes():
                        raw.extend(part)
                        if len(raw) > MAX_RESPONSE:
                            raise RuntimeError("Yanıt boyutu sınırı aşıldı.")
            pcm = self._parse(raw)
            return True, f"Gemini TTS: {len(pcm) / 48000:.2f} saniye ses alındı; hoparlör test edilmedi."
        except Exception as exc:
            return False, f"Gemini TTS testi başarısız ({type(exc).__name__}). API anahtarı, kota ve model erişimini kontrol edin."


PROVIDER = {
    "id": "gemini_tts",
    "kind": "tts",
    "label": "Gemini 3.8 TTS",
    "hint": "Bulut ses üretimi; metin Google'a gönderilir. Kota/ücret hesabınıza bağlıdır.",
    "requires": ("httpx",),
    "catalog": (
        {"id": "gemini_tts", "label": "Gemini 3.8 TTS", "local": False,
         "note": "Google bulut · kendi API anahtarınız", "values": {}},
    ),
    "needs": (
        Field("api_key", "Gemini API anahtarı", kind="secret"),
        Field("model", "Model", kind="choice", choices=MODELS, default=MODELS[0]),
        Field("voice_id", "Ses", kind="choice", choices=VOICES, default="Kore"),
    ),
    "caps": {"audio_out": True},
    "factory": GeminiTTS,
}


def available() -> bool:
    return find_spec("httpx") is not None
