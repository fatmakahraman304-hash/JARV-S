import json
import unittest
from unittest.mock import patch

from providers import realtime_tools as tools
from providers.realtime_transport import RealtimeError
from providers.realtime_settings import validate_settings
from providers.realtime_session import RealtimeSession


def response(raw='{"percent":30}', cid="call_1"):
    return {"output": [{"type": "function_call", "name": "request_volume",
                        "status": "completed", "call_id": cid, "arguments": raw}]}


class ConfirmedVolumeTests(unittest.TestCase):
    def test_default_disabled_and_opt_in(self):
        cfg = {"cloud_consent": True, "api_key": "test-only"}
        self.assertFalse(validate_settings(cfg)["volume_control"])
        self.assertTrue(validate_settings(dict(cfg, volume_control="1"))["volume_control"])
        session = RealtimeSession(object())
        self.assertEqual(session._setup["session"]["tools"], [])
        session = RealtimeSession(object(), volume_enabled=lambda: True)
        self.assertEqual(session._setup["session"]["tools"], [tools.volume_declaration()])

    def test_request_only_human_callback_can_change_volume(self):
        with patch("core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, \
                patch("actions.computer_settings.computer_settings", return_value="done") as action:
            result = tools.tool_output(response(), guide_enabled=lambda: False,
                                       volume_enabled=lambda: True, seen=set())
            action.assert_not_called()
            self.assertEqual(json.loads(result["item"]["output"])["status"], "pending_confirmation")
            self.assertEqual(gate.call_args.kwargs["title"], "Hoparlör sesini %30 yap")
            self.assertEqual(gate.call_args.kwargs["run"](), "done")
            action.assert_called_once_with({"action": "volume_set", "value": 30})

    def test_revoked_permission_blocks_pending_callback(self):
        allowed = True
        with patch("core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, \
                patch("actions.computer_settings.computer_settings") as action:
            tools.tool_output(response(), guide_enabled=lambda: False,
                              volume_enabled=lambda: allowed, seen=set())
            allowed = False
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            action.assert_not_called()

    def test_invalid_disabled_and_replayed_requests_do_not_open_confirmation(self):
        with patch("core.confirm.request") as gate:
            for raw in ('{"percent":-1}', '{"percent":101}', '{"percent":true}',
                        '{"percent":"30"}', '{"percent":30.0}', '{"percent":30,"confirmed":true}',
                        '{"percent":30,"percent":50}', '{}'):
                with self.subTest(raw=raw), self.assertRaises(RealtimeError):
                    tools.tool_output(response(raw), guide_enabled=lambda: False,
                                      volume_enabled=lambda: True, seen=set())
            for enabled, seen in ((False, set()), (True, {"call_1"})):
                with self.assertRaises(RealtimeError):
                    tools.tool_output(response(), guide_enabled=lambda: False,
                                      volume_enabled=lambda: enabled, seen=seen)
            gate.assert_not_called()

    def test_unavailable_gate_reports_not_executed(self):
        with patch("core.confirm.request", return_value="UI unavailable"):
            result = tools.tool_output(response(), guide_enabled=lambda: False,
                                       volume_enabled=lambda: True, seen=set())
        self.assertEqual(json.loads(result["item"]["output"])["status"], "not_executed")
