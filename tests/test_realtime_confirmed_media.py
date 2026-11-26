import json
import unittest
from unittest.mock import patch

from providers import realtime_tools as tools
from providers.realtime_settings import validate_settings
from providers.realtime_session import RealtimeSession
from providers.realtime_transport import RealtimeError


def request(raw='{"operation":"next"}', allowed=lambda: True, seen=None):
    return tools.tool_output(
        {"output": [{"type": "function_call", "name": "request_media",
                     "status": "completed", "call_id": "call_1", "arguments": raw}]},
        guide_enabled=lambda: False, volume_enabled=lambda: False,
        media_enabled=allowed, seen=set() if seen is None else seen)


class ConfirmedMediaTests(unittest.TestCase):
    def test_independent_default_off_permission(self):
        cfg = {"cloud_consent": True, "api_key": "test-only", "volume_control": "1"}
        self.assertFalse(validate_settings(cfg)["media_control"])
        self.assertTrue(validate_settings(dict(cfg, media_control="1"))["media_control"])
        self.assertEqual(RealtimeSession(object())._setup["session"]["tools"], [])
        self.assertEqual(RealtimeSession(object(), media_enabled=lambda: True)
                         ._setup["session"]["tools"], [tools.media_declaration()])

    def test_only_confirmed_fixed_action_is_executed(self):
        for op, action in (("play_pause", "media_play_pause"), ("next", "media_next"),
                           ("previous", "media_previous"), ("stop", "media_stop")):
            with self.subTest(op=op), patch("core.confirm.request",
                    return_value="[CONFIRMATION_PENDING]") as gate, patch(
                    "actions.computer_settings.computer_settings", return_value="sent") as run:
                result = request(json.dumps({"operation": op}))
                run.assert_not_called()
                self.assertEqual(json.loads(result["item"]["output"])["status"], "pending_confirmation")
                self.assertEqual(gate.call_args.kwargs["run"](), "sent")
                run.assert_called_once_with({"action": action})

    def test_revocation_blocks_pending_request(self):
        allowed = True
        with patch("core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, patch(
                "actions.computer_settings.computer_settings") as run:
            request(allowed=lambda: allowed)
            allowed = False
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            run.assert_not_called()

    def test_invalid_extra_and_replayed_arguments_never_open_gate(self):
        with patch("core.confirm.request") as gate:
            for raw in ('{}', '{"operation":"shutdown"}', '{"operation":true}',
                        '{"operation":"play"}', '{"operation":"pause"}',
                        '{"operation":"next","times":100}', '{"operation":"next","confirmed":true}',
                        '{"operation":"next","operation":"stop"}'):
                with self.subTest(raw=raw), self.assertRaises(RealtimeError):
                    request(raw)
            with self.assertRaises(RealtimeError):
                request(allowed=lambda: False)
            with self.assertRaises(RealtimeError):
                request(seen={"call_1"})
            gate.assert_not_called()

    def test_no_confirmation_interface_reports_not_executed(self):
        with patch("core.confirm.request", return_value="UI unavailable"):
            result = request()
        self.assertEqual(json.loads(result["item"]["output"])["status"], "not_executed")
