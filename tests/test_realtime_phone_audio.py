import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from providers import realtime_recall as recall
from providers.realtime_settings import validate_settings
from providers.engine_realtime import RealtimeEngine

PCM = b"\x01\x00" * 4000


class PhoneAudioFormatTests(unittest.TestCase):
    def test_independent_default_off_permission_and_audio_only_event(self):
        cfg = {"api_key": "test-only", "cloud_consent": True, "phone_text": True}
        self.assertFalse(validate_settings(cfg)["phone_audio"])
        self.assertTrue(validate_settings(dict(cfg, phone_audio=True))["phone_audio"])
        event = recall.phone_audio_event(PCM)["response"]
        self.assertEqual(event["conversation"], "none")
        self.assertEqual(event["tools"], [])
        self.assertEqual(event["tool_choice"], "none")
        self.assertEqual(event["input"][0]["content"][0]["type"], "input_audio")

    def test_invalid_recordings_rejected(self):
        for pcm in (b"", b"x" * 8001, b"x" * 7998, b"x" * (recall.MAX_PHONE_BYTES + 2), "audio"):
            self.assertFalse(recall.valid_phone_pcm(pcm))
            with self.assertRaises(ValueError):
                recall.phone_audio_event(pcm)


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    def server(self):
        from dashboard.server import DashboardServer
        srv = object.__new__(DashboardServer)
        srv._realtime_active = lambda: True
        srv._valid = lambda token: token == "live"
        srv._phone_audio_allowed = lambda token: True
        srv._realtime_recording = False
        srv._realtime_phone_audio = Mock(return_value={"ok": True, "status": "pending_confirmation"})
        return srv

    def socket(self, events, scheme="wss"):
        ws = AsyncMock()
        ws.url = SimpleNamespace(scheme=scheme)
        ws.receive.side_effect = events
        return ws

    async def test_only_explicit_submit_routes_recording(self):
        srv = self.server()
        ws = self.socket([{"type": "websocket.receive", "bytes": PCM},
                          {"type": "websocket.receive", "text": "submit"}])
        await srv._record_realtime_phone(ws, "live")
        srv._realtime_phone_audio.assert_called_once_with("live", PCM)
        self.assertFalse(srv._realtime_recording)
        self.assertEqual(ws.send_json.await_args.args[0]["status"], "pending_confirmation")

    async def test_disconnect_oversize_and_insecure_transport_never_submit(self):
        for events, scheme in (
                ([{"type": "websocket.receive", "bytes": PCM}, {"type": "websocket.disconnect"}], "wss"),
                ([{"type": "websocket.receive", "bytes": b"x" * (recall.MAX_PHONE_BYTES + 2)}], "wss"),
                ([], "ws")):
            srv = self.server()
            await srv._record_realtime_phone(self.socket(events, scheme), "live")
            srv._realtime_phone_audio.assert_not_called()
            self.assertFalse(srv._realtime_recording)

    async def test_revocation_before_submit(self):
        srv = self.server()
        ws = self.socket([])
        allowed = True
        srv._phone_audio_allowed = lambda token: allowed
        async def receive():
            nonlocal allowed
            allowed = False
            return {"type": "websocket.receive", "text": "submit"}
        ws.receive.side_effect = receive
        await srv._record_realtime_phone(ws, "live")
        srv._realtime_phone_audio.assert_not_called()


class Session:
    def __init__(self):
        self.requests = []
    async def turn(self, **kwargs):
        self.requests.append(kwargs)
        if False:
            yield
    async def close(self):
        pass


class PhoneAudioEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_audio_stays_on_separate_path(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        await engine.send_approved_phone_audio(PCM, lambda: True)
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [{"phone_pcm": PCM}])

    async def test_revocation_before_generation(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        allowed = True
        await engine.send_approved_phone_audio(PCM, lambda: allowed)
        allowed = False
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [])
