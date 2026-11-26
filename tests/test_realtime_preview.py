"""Regression coverage for explicit Realtime preview consent and input isolation."""
import asyncio
import unittest
from unittest.mock import patch

from providers import realtime_settings as rs
from providers.engine_realtime import RealtimeEngine
from providers.base import Msg
from memory import config_manager as cm


class RealtimeSettingsTests(unittest.TestCase):
    def test_consent_and_separate_key_required(self):
        for cfg in ({}, {"api_key": "test-only"}, {"cloud_consent": True},
                    {"cloud_consent": True, "api_key": "bad key"}):
            with self.subTest(cfg=cfg.keys()), self.assertRaises(ValueError):
                rs.validate_settings(cfg)
        cfg = rs.validate_settings({"cloud_consent": True, "api_key": "test-only"})
        self.assertFalse(cfg["microphone"])
        self.assertEqual(cfg["model"], rs.MODELS[0])

    def test_opt_in_and_model_validation(self):
        cfg = {"cloud_consent": "1", "api_key": "test-only", "microphone": "1"}
        self.assertTrue(rs.validate_settings(cfg)["microphone"])
        for extra in ({"model": "unknown"}, {"voice_id": "unknown"}):
            with self.assertRaises(ValueError):
                rs.validate_settings(dict(cfg, **extra))

    def test_realtime_mode_and_default(self):
        for saved, expected in (("realtime", "realtime"), ("pipeline", "pipeline"),
                                ("gemini", "gemini"), ("", "gemini")):
            with patch.object(cm, "get_providers", return_value={"mode": saved}):
                self.assertEqual(cm.get_provider_mode(), expected)

    def test_retired_pipeline_settings_do_not_change_realtime_mode(self):
        block = {"mode": "realtime", "pipeline": {"llm": "openai_compat@deepseek"},
                 "creds": {"openai_realtime": {"api_key": "test-only"}}}
        clean = cm._without_deepseek(block)
        self.assertEqual(clean["mode"], "realtime")
        self.assertEqual(clean["pipeline"]["llm"], "")
        self.assertEqual(clean["creds"]["openai_realtime"]["api_key"], "test-only")


class FakeSession:
    def __init__(self):
        self.requests = []
    async def turn(self, **request):
        self.requests.append(request)
        yield Msg.turn_end()
    async def close(self):
        pass


class RealtimePreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_channel_cannot_transmit(self):
        session = FakeSession()
        engine = RealtimeEngine(session, explicit_only=True)
        self.addAsyncCleanup(engine.close)
        await engine.send_client_content(turns={"parts": [{"text": "private system notification"}]})
        self.assertIsNone(engine._gen)
        await engine.send_user_content(turns={"parts": [{"text": "Merhaba"}]})
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [{"text": "Merhaba"}])

    async def test_disabled_capture_discards_pending_pcm(self):
        session = FakeSession()
        allowed = True
        engine = RealtimeEngine(session, capture_allowed=lambda: allowed)
        self.addAsyncCleanup(engine.close)
        await engine.send_realtime_input(audio=b"\x01\x00")
        allowed = False
        await engine.flush_microphone()
        self.assertEqual(len(engine._mic), 0)
        self.assertIsNone(engine._gen)
        await engine.send_realtime_input(audio=b"\x02\x00")
        self.assertEqual(len(engine._mic), 0)
        allowed = True
        await engine.flush_microphone()
        self.assertEqual(session.requests, [])

    async def test_permission_is_rechecked_before_scheduled_request(self):
        session = FakeSession()
        allowed = True
        engine = RealtimeEngine(session, capture_allowed=lambda: allowed)
        self.addAsyncCleanup(engine.close)
        await engine.send_realtime_input(audio=b"\x01\x00")
        await engine.flush_microphone()
        allowed = False
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [])
