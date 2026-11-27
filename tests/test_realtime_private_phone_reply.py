import asyncio
import base64
import io
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from providers.base import Msg
from providers.engine_realtime import RealtimeEngine
from providers.realtime_phone_reply import reply_message, MAX_REPLY_BYTES
from providers.realtime_settings import validate_settings

PCM = b"\x01\x00" * 20


class ReplyFormatTests(unittest.TestCase):
    def test_default_off_and_wav_format(self):
        cfg = {"api_key": "test-only", "cloud_consent": True}
        self.assertFalse(validate_settings(cfg)["phone_reply"])
        self.assertTrue(validate_settings(dict(cfg, phone_reply=True))["phone_reply"])
        message = reply_message(PCM)
        with wave.open(io.BytesIO(base64.b64decode(message["wav"])), "rb") as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
            self.assertEqual(wav.readframes(20), PCM)
        for data in (b"", b"x", b"x" * (MAX_REPLY_BYTES + 2)):
            with self.assertRaises(ValueError):
                reply_message(data)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_original_secure_socket_receives_audio(self):
        from dashboard.server import DashboardServer
        srv = object.__new__(DashboardServer)
        a, other, tv = [AsyncMock() for _ in range(3)]
        for ws in (a, other, tv):
            ws.url = SimpleNamespace(scheme="wss")
        srv._clients = {a: "a", other: "b", tv: "a"}
        srv._screen_ws = {tv: "screen"}
        srv._tokens = {"a": time.time(), "b": time.time()}
        srv._token_keys = {}
        srv._history = []
        self.assertTrue(await srv.deliver_private_phone_reply(a, "a", PCM, lambda: True))
        a.send_json.assert_awaited_once_with(reply_message(PCM))
        other.send_json.assert_not_called()
        tv.send_json.assert_not_called()
        self.assertEqual(srv._history, [])
        srv._clients.pop(a)
        srv._clients[other] = "a"
        self.assertFalse(await srv.deliver_private_phone_reply(a, "a", PCM, lambda: True))
        other.send_json.assert_not_called()

    async def test_duplicate_token_insecure_and_revocation_rejected(self):
        from dashboard.server import DashboardServer
        srv = object.__new__(DashboardServer)
        a, b = AsyncMock(), AsyncMock()
        a.url = b.url = SimpleNamespace(scheme="wss")
        srv._clients = {a: "a", b: "a"}
        srv._screen_ws = {}
        srv._tokens = {"a": time.time()}
        srv._token_keys = {}
        self.assertIsNone(srv.private_phone_socket("a"))
        srv._clients.pop(b)
        a.url = SimpleNamespace(scheme="ws")
        self.assertIsNone(srv.private_phone_socket("a"))
        a.url = SimpleNamespace(scheme="wss")
        self.assertFalse(await srv.deliver_private_phone_reply(a, "a", PCM, lambda: False))
        srv._tokens.clear()
        self.assertFalse(await srv.deliver_private_phone_reply(a, "a", PCM, lambda: True))
        a.send_json.assert_not_called()


class Session:
    def __init__(self, events):
        self.events = events
    async def turn(self, **kwargs):
        for event in self.events:
            yield event
    async def close(self):
        pass


class PrivateEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_audio_sent_without_desktop_queue(self):
        engine = RealtimeEngine(Session([Msg.audio(PCM), Msg.said("private"), Msg.turn_end()]))
        self.addAsyncCleanup(engine.close)
        sink = AsyncMock()
        await engine.send_approved_phone("hello", lambda: True, reply=sink)
        await asyncio.wait_for(engine._gen, 2)
        sink.assert_awaited_once_with(PCM)
        self.assertTrue(engine._queue.empty())

    async def test_incomplete_or_oversize_is_not_delivered(self):
        for events in ([Msg.audio(PCM)], [Msg.audio(b"x" * (MAX_REPLY_BYTES + 2)), Msg.turn_end()]):
            engine = RealtimeEngine(Session(events))
            self.addAsyncCleanup(engine.close)
            sink = AsyncMock()
            await engine.send_approved_phone("hello", lambda: True, reply=sink)
            await asyncio.wait_for(engine._gen, 2)
            sink.assert_not_called()
            self.assertTrue(engine._queue.empty())

    async def test_revoked_before_generation_no_delivery(self):
        engine = RealtimeEngine(Session([Msg.audio(PCM), Msg.turn_end()]))
        self.addAsyncCleanup(engine.close)
        sink = AsyncMock()
        allowed = True
        await engine.send_approved_phone("hello", lambda: allowed, reply=sink)
        allowed = False
        await asyncio.wait_for(engine._gen, 2)
        sink.assert_not_called()
        self.assertTrue(engine._queue.empty())
