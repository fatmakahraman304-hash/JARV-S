"""Local Kokoro-FastAPI speech provider (24 kHz signed little-endian PCM).

The server is installed and started separately by the user. Only numeric
loopback addresses are accepted, and no credentials, proxy or redirect are used.
The server itself is not sandboxed by FRIDAY.
"""
from __future__ import annotations

from importlib.util import find_spec
from urllib.parse import urlsplit

from .base import DEFAULT_CAPS, Field

DEFAULT_ADDRESS = "http://127.0.0.1:8880/v1"
MAX_INPUT = 4000
MAX_AUDIO = 24_000 * 2 * 300
_CHUNK = 2400
_TYPES = {"audio/pcm", "audio/x-pcm", "audio/raw", "application/octet-stream"}


def _endpoint(address: str) -> str:
    parts = urlsplit(address.strip())
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "::1"}
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or parts.path.rstrip("/") not in {"", "/v1"}):
        raise ValueError("Kokoro için http://127.0.0.1:8880/v1 gibi yerel bir adres gerekli.")
    port = parts.port
    if port is None or not 1 <= port <= 65535:
        raise ValueError("Kokoro sunucu portu gerekli.")
    host = "[::1]" if parts.hostname == "::1" else "127.0.0.1"
    return f"http://{host}:{port}/v1/audio/speech"


def _check_response(response) -> None:
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Kokoro HTTP {response.status_code}")
    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in _TYPES:
        raise RuntimeError("Kokoro PCM yerine beklenmeyen yanıt biçimi döndürdü.")


class KokoroTTS:
    def __init__(self, cfg: dict):
        self.url = _endpoint(str(cfg.get("base_url") or DEFAULT_ADDRESS))
        self.voice_id = str(cfg.get("voice_id") or "af_heart").strip()
        self.caps = dict(DEFAULT_CAPS, audio_out=True)

    def _payload(self, text: str, voice: str = "") -> dict:
        if len(text) > MAX_INPUT:
            raise ValueError("Kokoro metni 4000 karakter sınırını aşıyor.")
        selected = (voice or self.voice_id).strip()
        if not selected or len(selected) > 128:
            raise ValueError("Geçersiz Kokoro ses adı.")
        return {"model": "kokoro", "input": text, "voice": selected, "response_format": "pcm"}

    async def speak(self, text: str, voice: str = ""):
        import httpx

        text = (text or "").strip()
        if not text:
            return
        payload = self._payload(text, voice)
        buf = bytearray()
        total = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=3),
                                     trust_env=False, follow_redirects=False) as client:
            async with client.stream("POST", self.url, json=payload) as response:
                _check_response(response)
                async for part in response.aiter_bytes(chunk_size=_CHUNK):
                    total += len(part)
                    if total > MAX_AUDIO:
                        raise RuntimeError("Kokoro ses boyutu sınırı aşıldı.")
                    buf.extend(part)
                    while len(buf) >= _CHUNK:
                        yield bytes(buf[:_CHUNK])
                        del buf[:_CHUNK]
        if len(buf) % 2 or total == 0:
            raise RuntimeError("Kokoro boş veya eksik PCM döndürdü.")
        if buf:
            yield bytes(buf)

    def probe(self) -> tuple[bool, str]:
        """Send only a fixed test phrase, never the user's conversation."""
        import httpx
        try:
            with httpx.Client(timeout=httpx.Timeout(10, connect=2),
                              trust_env=False, follow_redirects=False) as client:
                with client.stream("POST", self.url, json=self._payload("Hello.")) as response:
                    _check_response(response)
                    count = 0
                    for piece in response.iter_bytes(chunk_size=_CHUNK):
                        count += len(piece)
                        if count > MAX_AUDIO:
                            raise RuntimeError("Kokoro ses boyutu sınırı aşıldı.")
            if count and count % 2 == 0:
                return True, f"Kokoro PCM yanıtı: {count / 48000:.2f} saniye (çalma test edilmedi)."
            return False, "Kokoro boş veya eksik PCM döndürdü."
        except Exception as exc:
            return False, f"Kokoro bağlantı/ses testi başarısız ({type(exc).__name__})."


PROVIDER = {
    "id": "kokoro",
    "kind": "tts",
    "label": "Kokoro-FastAPI (yerel)",
    "hint": "Yerel ses sunucusu; ayrıca kurup başlatın. Türkçe desteğini seçili seste doğrulayın.",
    "requires": ("httpx",),
    "catalog": (
        {"id": "local", "label": "Kokoro-FastAPI (yerel)", "local": True,
         "note": "ayrı yerel sunucu · API anahtarı yok", "values": {}},
    ),
    "needs": (
        Field("base_url", "Yerel API adresi", default=DEFAULT_ADDRESS),
        Field("voice_id", "Ses adı", default="af_heart",
              hint="Sunucuda kurulu ses adı; varsayılan İngilizce ses."),
    ),
    "caps": {"audio_out": True},
    "factory": KokoroTTS,
}


def available() -> bool:
    return find_spec("httpx") is not None
