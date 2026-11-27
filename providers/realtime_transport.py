"""Opt-in OpenAI Realtime transport prototype; not yet a registered engine.

A single explicitly supplied text or recorded PCM utterance becomes one audio
response. No microphone capture, tool execution, history, or automatic fallback.
The caller owns consent, credentials and playback. Uses the Realtime GA API.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from . import audio

MODELS = ("gpt-realtime-2.1-mini", "gpt-realtime-2.1")
URL = "wss://api.openai.com/v1/realtime"
MAX_INPUT = 30 * 24000 * 2
MAX_OUTPUT = 120 * 24000 * 2
MAX_EVENT = 4 * 1024 * 1024
MAX_EVENTS = 10000


class RealtimeError(RuntimeError):
    pass


def session_event(voice: str = "marin") -> dict:
    if voice not in {"marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"}:
        raise ValueError("Desteklenen Realtime sesi seçin.")
    return {"type": "session.update", "session": {
        "type": "realtime", "output_modalities": ["audio"],
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": 24000},
                      "turn_detection": None},
            "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": voice},
        },
        "tools": [],
        "instructions": "Answer the user's request in their language. Do not claim to have used tools.",
    }}


def input_event(*, text: str | None = None, pcm: bytes | None = None) -> dict:
    if (text is None) == (pcm is None):
        raise ValueError("Tek bir metin veya PCM girdisi gerekli.")
    if text is not None:
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("Metin 1–4000 karakter olmalı.")
        content = {"type": "input_text", "text": text}
    else:
        # Input is FRIDAY microphone-format PCM16LE mono, at 16 kHz.
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % 2 or len(pcm) > 30 * 16000 * 2:
            raise ValueError("Geçerli 16 kHz PCM gerekli (en fazla 30 saniye).")
        data = audio.resample(pcm, 16000, 24000)
        if len(data) > MAX_INPUT:
            raise ValueError("PCM boyutu sınırı aşıldı.")
        content = {"type": "input_audio", "audio": base64.b64encode(data).decode("ascii")}
    return {"type": "conversation.item.create", "item": {
        "type": "message", "role": "user", "content": [content]}}


async def _send(ws, event: dict) -> None:
    await ws.send(json.dumps(event, ensure_ascii=False))


async def _receive(ws) -> dict:
    raw = await ws.recv()
    if not isinstance(raw, str) or len(raw) > MAX_EVENT:
        raise RealtimeError("Realtime olay biçimi veya boyutu geçersiz.")
    try:
        event = json.loads(raw)
    except (ValueError, RecursionError):
        raise RealtimeError("Realtime JSON olayı geçersiz.") from None
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise RealtimeError("Realtime olay türü geçersiz.")
    if event["type"] == "error":
        # Do not return arbitrary provider error content, input, or secrets.
        raise RealtimeError("Realtime sunucusu isteği reddetti.")
    return event


async def exchange(ws, *, text=None, pcm=None, voice="marin"):
    """Yield ordered PCM chunks; caller must consume or close the generator."""
    setup = session_event(voice)
    item = input_event(text=text, pcm=pcm)
    async with asyncio.timeout(60):
        await _send(ws, setup)
        for _ in range(64):
            event = await _receive(ws)
            if event["type"] == "session.updated":
                break
        else:
            raise RealtimeError("Realtime oturum onayı alınamadı.")
        await _send(ws, item)
        await _send(ws, {"type": "response.create"})
        total = 0
        for _ in range(MAX_EVENTS):
            event = await _receive(ws)
            kind = event["type"]
            if kind == "response.output_audio.delta":
                try:
                    data = base64.b64decode(event.get("delta", ""), validate=True)
                except (ValueError, TypeError, binascii.Error):
                    raise RealtimeError("Realtime PCM kodlaması geçersiz.") from None
                total += len(data)
                if len(data) % 2 or total > MAX_OUTPUT:
                    raise RealtimeError("Realtime PCM boyutu geçersiz.")
                for chunk in audio.chunk(data):
                    yield chunk
            elif kind == "response.done":
                response = event.get("response")
                if not isinstance(response, dict) or response.get("status") != "completed":
                    raise RealtimeError("Realtime yanıtı tamamlanmadı.")
                if not total:
                    raise RealtimeError("Realtime ses döndürmedi.")
                return
        raise RealtimeError("Realtime olay sınırı aşıldı.")


@asynccontextmanager
async def open_realtime(api_key: str, model: str = MODELS[0]):
    """Explicit connection to the fixed API origin; never forward credentials."""
    if (not isinstance(api_key, str) or not api_key
            or any(not 33 <= ord(c) <= 126 for c in api_key)):
        raise ValueError("Geçerli OpenAI API anahtarı gerekli.")
    if model not in MODELS:
        raise ValueError("Desteklenen Realtime modelini seçin.")
    from websockets.asyncio.client import connect

    class DirectConnect(connect):
        def process_redirect(self, exc):
            # websockets >=15 may follow a redirect with the original headers.
            # Returning an exception (not a URI) forbids every redirect.
            return RealtimeError("Realtime bağlantı el sıkışması tamamlanamadı.")

    # Suppress the transport's raw HTTP header and frame debug logs even when
    # the application's root logger is configured for verbose diagnostics.
    quiet = logging.Logger("friday.realtime.transport")
    quiet.disabled = True
    quiet.propagate = False
    async with AsyncExitStack() as stack:
        try:
            ws = await stack.enter_async_context(DirectConnect(
                f"{URL}?model={model}",
                additional_headers={"Authorization": f"Bearer {api_key}"},
                proxy=None, open_timeout=10, close_timeout=3,
                max_size=MAX_EVENT, max_queue=16, logger=quiet))
        except Exception:
            # Never include a handshake body, header, URI, or raw credentials.
            raise RealtimeError("Realtime bağlantısı kurulamadı.") from None
        yield ws
