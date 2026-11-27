import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from providers.realtime_recall import phone_payload, response_event
from providers.realtime_settings import validate_settings
from providers.engine_realtime import RealtimeEngine


class PhoneTextTests(unittest.TestCase):
    def test_phone_consent_default_off_and_payload_has_no_history_or_tools(self):
        cfg = {"api_key": "test-only", "cloud_consent": True}
        self.assertFalse(validate_settings(cfg)["phone_text"])
        self.assertTrue(validate_settings(dict(cfg, phone_text=True))["phone_text"])
        payload = phone_payload("Merhaba")
        self.assertEqual(json.loads(payload)["historical_records"], "")
        self.assertEqual(json.loads(payload)["question"], "Merhaba")
        event = response_event(payload)["response"]
        self.assertEqual(event["conversation"], "none")
        self.assertEqual(event["tools"], [])
        self.assertEqual(event["tool_choice"], "none")

    def test_dashboard_auth_and_text_validation(self):
        from dashboard.server import DashboardServer
        srv = object.__new__(DashboardServer)
        srv._valid = lambda token: token == "live"
        srv._realtime_phone_command = Mock(return_value={"ok": True, "status": "pending_confirmation"})
        for token, text in (("old", "hello"), ("live", ""), ("live", None),
                            ("live", "x" * 4001)):
            self.assertFalse(srv._route_realtime_phone(token, text)["ok"])
        srv._realtime_phone_command.assert_not_called()
        self.assertTrue(srv._route_realtime_phone("live", " hello ")["ok"])
        srv._realtime_phone_command.assert_called_once_with("live", "hello")

    def test_hud_approval_is_required_and_revoked_token_blocks_send(self):
        from tests._main_import import load_main
        main = load_main()
        engine = Mock()
        dashboard = Mock()
        dashboard._valid.return_value = True
        loop = Mock()
        loop.is_running.return_value = True
        obj = SimpleNamespace(_engine=engine, session=engine, _dashboard=dashboard,
                              _loop=loop, _session_realtime=True, _awake=True,
                              _engine_mode=lambda: "realtime", ui=Mock())
        obj._phone_reply_target = lambda token, allowed: main.FridayLive._phone_reply_target(obj, token, allowed)
        cfg = {"cloud_consent": True, "phone_text": True}
        with patch("memory.config_manager.get_provider_config", return_value=cfg), patch(
                "core.confirm.pending_title", return_value=""), patch(
                "core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate:
            result = main.FridayLive._request_realtime_phone_text(obj, "live", "hello")
            self.assertEqual(result["status"], "pending_confirmation")
            engine.send_approved_phone.assert_not_called()
            obj.ui.show_content.assert_called_once()
            dashboard._valid.return_value = False
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            engine.send_approved_phone.assert_not_called()

    def test_disabled_or_busy_does_not_show_approval(self):
        from tests._main_import import load_main
        main = load_main()
        engine = Mock()
        dashboard = Mock()
        dashboard._valid.return_value = True
        loop = Mock()
        loop.is_running.return_value = True
        obj = SimpleNamespace(_engine=engine, session=engine, _dashboard=dashboard,
                              _loop=loop, _session_realtime=True, _awake=True,
                              _engine_mode=lambda: "realtime", ui=Mock())
        obj._phone_reply_target = lambda token, allowed: main.FridayLive._phone_reply_target(obj, token, allowed)
        with patch("memory.config_manager.get_provider_config",
                   return_value={"cloud_consent": True}), patch("core.confirm.request") as gate:
            self.assertFalse(main.FridayLive._request_realtime_phone_text(obj, "live", "hello")["ok"])
            gate.assert_not_called()
        with patch("memory.config_manager.get_provider_config",
                   return_value={"cloud_consent": True, "phone_text": True}), patch(
                   "core.confirm.pending_title", return_value="other"), patch("core.confirm.request") as gate:
            self.assertEqual(main.FridayLive._request_realtime_phone_text(obj, "live", "hello")["status"], "busy")
            gate.assert_not_called()


class Session:
    def __init__(self):
        self.requests = []
    async def turn(self, **kwargs):
        self.requests.append(kwargs)
        if False:
            yield
    async def close(self):
        pass


class PhoneEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_question_uses_read_only_path(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        await engine.send_approved_phone("hello", lambda: True)
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [{"recall_payload": phone_payload("hello")}])

    async def test_revoked_before_generation_does_not_send(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        allowed = True
        await engine.send_approved_phone("hello", lambda: allowed)
        allowed = False
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [])
