"""Bounded multi-turn Realtime conversation adapter for FRIDAY Msg events.

One explicitly opened socket keeps the server-side conversation between turns.
The caller must consume/close each turn in its owning asyncio task. No tool
execution, persistent memory, background capture or automatic cloud fallback.
An interrupted or failed response invalidates the session rather than replaying
unconfirmed input. This is not yet an application Engine implementation.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
from contextlib import asynccontextmanager

from . import audio
from .base import Msg
from . import realtime_transport as rt
from . import realtime_tools as tools

MAX_TURNS = 12
MAX_TRANSCRIPT = 16_000
TURN_SECONDS = 60


class RealtimeSession:
    def __init__(self, ws, voice="marin", guide_enabled=None):
        self._ws = ws
        self._setup = rt.session_event(voice)
        self._guide_enabled = guide_enabled or (lambda: False)
        if self._guide_enabled():
            self._setup['session']['tools'] = [tools.declaration()]
            self._setup['session']['instructions'] += (
                " You may read the static FRIDAY guide with assistant_help, but cannot execute actions.")
        self._ready = False
        self._closed = False
        self._busy = False
        self._turns = 0

    async def _before(self, deadline, operation, *args):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise rt.RealtimeError("Realtime zaman sınırı aşıldı.")
        try:
            return await asyncio.wait_for(operation(*args), remaining)
        except TimeoutError:
            raise rt.RealtimeError("Realtime zaman sınırı aşıldı.") from None

    async def start(self):
        if self._closed or self._busy:
            raise rt.RealtimeError("Realtime oturumu kullanılamıyor.")
        if self._ready:
            return
        self._busy = True
        try:
            deadline = asyncio.get_running_loop().time() + 10
            await self._before(deadline, rt._send, self._ws, self._setup)
            for _ in range(64):
                event = await self._before(deadline, rt._receive, self._ws)
                if event["type"] == "session.updated":
                    self._ready = True
                    return
            raise rt.RealtimeError("Realtime oturum onayı alınamadı.")
        finally:
            self._busy = False
            if not self._ready:
                await self.close()

    async def turn(self, *, text=None, pcm=None):
        """Yield FRIDAY audio, one full output transcript, then turn-end."""
        if not self._ready or self._closed:
            raise rt.RealtimeError("Önce yeni bir Realtime oturumu açın.")
        if self._busy:
            raise rt.RealtimeError("Önceki Realtime yanıtı hâlâ çalışıyor.")
        if self._turns >= MAX_TURNS:
            raise rt.RealtimeError("Oturum tur sınırı doldu; yeni oturum açın.")
        item = rt.input_event(text=text, pcm=pcm)
        self._busy = True
        self._turns += 1
        finished = False
        deadline = asyncio.get_running_loop().time() + TURN_SECONDS
        response_id = None
        total = 0
        transcript = []
        transcript_len = 0
        seen = set()
        rounds = 0
        response_audio_start = 0
        try:
            await self._before(deadline, rt._send, self._ws, item)
            await self._before(deadline, rt._send, self._ws, {"type": "response.create"})
            for _ in range(rt.MAX_EVENTS):
                event = await self._before(deadline, rt._receive, self._ws)
                kind = event["type"]
                if kind == "response.created":
                    response = event.get("response")
                    candidate = response.get("id") if isinstance(response, dict) else None
                    if response_id is not None or not isinstance(candidate, str) or not candidate:
                        raise rt.RealtimeError("Realtime yanıt kimliği geçersiz.")
                    response_id = candidate
                elif kind in {"response.output_audio.delta", "response.output_audio_transcript.delta",
                              "response.output_audio_transcript.done"}:
                    if not response_id or event.get("response_id") != response_id:
                        raise rt.RealtimeError("Beklenmeyen Realtime yanıtı.")
                    if kind == "response.output_audio.delta":
                        try:
                            data = base64.b64decode(event.get("delta", ""), validate=True)
                        except (ValueError, TypeError, binascii.Error):
                            raise rt.RealtimeError("Realtime ses kodlaması geçersiz.") from None
                        total += len(data)
                        if len(data) % 2 or total > rt.MAX_OUTPUT:
                            raise rt.RealtimeError("Realtime ses boyutu geçersiz.")
                        for chunk in audio.chunk(data):
                            yield Msg.audio(chunk)
                    elif kind == "response.output_audio_transcript.delta":
                        piece = event.get("delta")
                        if not isinstance(piece, str) or transcript_len + len(piece) > MAX_TRANSCRIPT:
                            raise rt.RealtimeError("Realtime metin dökümü sınırı aşıldı.")
                        transcript.append(piece)
                        transcript_len += len(piece)
                    else:
                        full = event.get("transcript")
                        if not isinstance(full, str) or len(full) > MAX_TRANSCRIPT:
                            raise rt.RealtimeError("Realtime metin dökümü geçersiz.")
                        transcript = [full]
                        transcript_len = len(full)
                elif kind == "response.done":
                    response = event.get("response")
                    if (not response_id or not isinstance(response, dict)
                            or response.get("id") != response_id
                            or response.get("status") != "completed"):
                        raise rt.RealtimeError("Realtime yanıtı tamamlanmadı.")
                    # Only completed output items can request a tool; never
                    # execute partial arguments or undeclared functions.
                    has_calls = any(isinstance(item, dict) and item.get("type") == "function_call"
                                    for item in (response.get("output") or []))
                    if has_calls:
                        if rounds >= tools.MAX_ROUNDS:
                            raise rt.RealtimeError("Realtime araç tur sınırı aşıldı.")
                        output = tools.guide_output(
                            response, enabled=lambda: bool(self._setup["session"]["tools"])
                                and self._guide_enabled(), seen=seen)
                        if output is None:
                            raise rt.RealtimeError("Realtime araç sonucu geçersiz.")
                        line = "".join(transcript).strip()
                        if line:
                            yield Msg.said(line)
                        await self._before(deadline, rt._send, self._ws, output)
                        await self._before(deadline, rt._send, self._ws, {"type": "response.create"})
                        rounds += 1
                        response_id = None
                        response_audio_start = total
                        transcript = []
                        transcript_len = 0
                        continue
                    if total == response_audio_start:
                        raise rt.RealtimeError("Realtime ses döndürmedi.")
                    line = "".join(transcript).strip()
                    if line:
                        yield Msg.said(line)
                    finished = True
                    yield Msg.turn_end()
                    return
            raise rt.RealtimeError("Realtime olay sınırı aşıldı.")
        finally:
            self._busy = False
            if not finished:
                await self.close()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        self._ready = False
        try:
            await asyncio.wait_for(self._ws.close(), 4)
        except Exception:
            # The session remains invalid even if the remote close fails.
            pass


@asynccontextmanager
async def conversation(api_key: str, model=rt.MODELS[0], voice="marin", guide_enabled=None):
    """Explicit opt-in cloud connection; session history is not saved locally."""
    async with rt.open_realtime(api_key, model) as ws:
        session = RealtimeSession(ws, voice, guide_enabled=guide_enabled)
        try:
            await session.start()
            yield session
        finally:
            await session.close()
