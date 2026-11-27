"""Opt-in FRIDAY Engine adapter for a pre-opened RealtimeSession.

Explicit push-to-talk is the default; local turn detection is opt-in.
The future UI integration must gate microphone capture and obtain consent
before opening the cloud connection. No tool, vision or background routing.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing

from .base import DEFAULT_CAPS, Msg
from .realtime_local_turns import LocalTurns

MAX_MIC_BYTES = 30 * 16000 * 2
QUEUE_SIZE = 128


class RealtimeEngine:
    def __init__(self, session, log=None, *, explicit_only=False, capture_allowed=None, reconnect=None):
        self._session = session
        self._explicit_only = explicit_only
        self._capture_allowed = capture_allowed or (lambda: True)
        self._reconnect = reconnect or (lambda: None)
        self._log = log or (lambda message: None)
        self.caps = dict(DEFAULT_CAPS, audio_out=True)
        self._mic = bytearray()
        self.auto_turn = False
        self._local_turns = LocalTurns()
        self._overflow = False
        self._queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._gen = None
        self._closed = False
        self._invalid = False
        self._loop = asyncio.get_running_loop()

    async def warmup(self):
        # The conversation context already performed session setup.
        return None

    async def send_realtime_input(self, *, audio):
        if not self._capture_allowed():
            self.discard_capture()
            return
        if self._closed or self._invalid or self._overflow:
            return
        data = audio if isinstance(audio, bytes) else getattr(audio, "data", None)
        if not isinstance(data, bytes) or not data or len(data) % 2:
            return
        if self.auto_turn:
            if len(data) > MAX_MIC_BYTES:
                self.discard_capture()
                return
            if self._gen is not None and not self._gen.done():
                self.discard_capture()
                return
            for clip in self._local_turns.feed(data):
                self._start(pcm=clip)
            return
        if len(self._mic) + len(data) > MAX_MIC_BYTES:
            self._mic.clear()
            self._overflow = True
            return
        self._mic.extend(data)

    def discard_capture(self):
        """Discard unsubmitted audio when mute, sleep or capture mode changes."""
        self._mic.clear()
        self._overflow = False
        self._local_turns.reset()

    async def flush_microphone(self, sample_rate=16000):
        if not self._capture_allowed():
            self.discard_capture()
            return ""
        if self.auto_turn:
            self.discard_capture()
            return ""
        pcm = bytes(self._mic)
        self._mic.clear()
        overflow, self._overflow = self._overflow, False
        if self._closed:
            return ""
        if overflow or sample_rate != 16000:
            self._log("SYS: Realtime mikrofon girdisi sınırı veya biçimi geçersiz; gönderilmedi.")
            return ""
        if pcm:
            self._start(pcm=pcm)
        # No input transcription capability is configured yet.
        return ""

    async def send_client_content(self, *, turns, turn_complete=True):
        if self._explicit_only:
            return  # main's shared background/injection channel is not consent
        await self.send_user_content(turns=turns, turn_complete=turn_complete)

    async def send_user_content(self, *, turns, turn_complete=True):
        if self._closed:
            return
        parts = turns.get("parts") if isinstance(turns, dict) else None
        if (not turn_complete or not isinstance(parts, list) or not parts
                or any(not isinstance(p, dict) or not isinstance(p.get("text"), str)
                       or set(p) != {"text"} for p in parts)):
            self._log("SYS: Realtime yalnızca tamamlanmış metin girişlerini kabul ediyor.")
            return
        text = "\n".join(p["text"] for p in parts).strip()
        if not text or len(text) > 4000:
            self._log("SYS: Realtime metin sınırı 1–4000 karakter; gönderilmedi.")
            return
        self._start(text=text)

    async def send_approved_recall(self, payload, allowed):
        """Only the local HUD approval path may call this; recheck before sending."""
        if not allowed():
            self._log("SYS: Realtime hafıza aktarımı iptal edildi.")
            return
        self._start(recall_payload=payload, _recall_allowed=allowed)

    async def send_approved_phone(self, text, allowed):
        """Submit one locally approved remote question; no normal tool access."""
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 4000 or not allowed():
            return
        from .realtime_recall import phone_payload
        self._start(recall_payload=phone_payload(text), _recall_allowed=allowed)

    def _start(self, **request):
        if self._closed or ("pcm" in request and not self._capture_allowed()):
            return
        if self._invalid:
            self._log("SYS: Realtime oturumu geçersiz; yeniden bağlantı gerekli.")
            return
        if self._gen is not None and not self._gen.done():
            self._log("SYS: Realtime yanıtı sürüyor; yeni giriş gönderilmedi.")
            return
        self._gen = self._loop.create_task(self._generate(request))

    async def _generate(self, request):
        try:
            allowed = request.pop("_recall_allowed", None)
            if "recall_payload" in request and (allowed is None or not allowed()):
                return
            if "pcm" in request and not self._capture_allowed():
                return
            async with aclosing(self._session.turn(**request)) as events:
                async for event in events:
                    if self._closed or self._invalid:
                        return
                    await self._queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._invalid = True
            if not self._closed:
                # Avoid leaking provider error bodies or user input to logs.
                self._log(f"SYS: Realtime yanıtı tamamlanmadı ({type(exc).__name__}).")
                await self._queue.put(Msg.turn_end())
                self._reconnect()

    async def send_tool_response(self, *, function_responses):
        # This adapter never declares tools and must not replay a tool result.
        self._log("SYS: Realtime araç kullanımı bu aşamada desteklenmiyor.")

    async def receive(self):
        while not (self._closed and self._queue.empty()):
            event = await self._queue.get()
            if event is None:
                return
            yield event

    def interrupt(self):
        # Can arrive from the push-to-talk hotkey thread.
        try:
            self._loop.call_soon_threadsafe(self._interrupt_on_loop)
        except RuntimeError:
            if not self._loop.is_closed():
                raise

    def _interrupt_on_loop(self):
        self.discard_capture()
        if self._closed or self._gen is None or self._gen.done():
            return
        self._invalid = True
        self._gen.cancel()
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(Msg.turn_end())
        # A cancelled task may not have entered the session generator.
        self._closing = self._loop.create_task(self._session.close())
        self._reconnect()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        self.discard_capture()
        task = self._gen
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        closing = getattr(self, "_closing", None)
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await self._session.close()
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(None)
