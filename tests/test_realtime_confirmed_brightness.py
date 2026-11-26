import json
import unittest
from unittest.mock import patch

from providers import realtime_tools as tools
from providers.realtime_transport import RealtimeError
from providers.realtime_settings import validate_settings
from providers.realtime_session import RealtimeSession


def response(raw='{"percent":40}', cid="call_1"):
    return {"output": [{"type": "function_call", "name": "request_brightness",
                        "status": "completed", "call_id": cid, "arguments": raw}]}


def request(raw='{"percent":40}', allowed=lambda: True, seen=None):
    return tools.tool_output(response(raw), guide_enabled=lambda: False,
                             volume_enabled=lambda: False, brightness_enabled=allowed,
                             seen=set() if seen is None else seen)


class ConfirmedBrightnessTests(unittest.TestCase):
    def test_permission_is_independent_and_off_by_default(self):
        cfg = {"cloud_consent": True, "api_key": "test-only", "volume_control": "1"}
        self.assertFalse(validate_settings(cfg)["brightness_control"])
        self.assertTrue(validate_settings(dict(cfg, brightness_control="1"))["brightness_control"])
        session = RealtimeSession(object(), volume_enabled=lambda: True)
        self.assertEqual(session._setup["session"]["tools"], [tools.volume_declaration()])
        session = RealtimeSession(object(), brightness_enabled=lambda: True)
        self.assertEqual(session._setup["session"]["tools"], [tools.brightness_declaration()])

    def test_only_hud_callback_invokes_fixed_brightness_action(self):
        with patch("core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, \
                patch("actions.computer_settings.computer_settings", return_value="done") as action:
            result = request()
            action.assert_not_called()
            self.assertEqual(json.loads(result["item"]["output"])["status"], "pending_confirmation")
            self.assertEqual(gate.call_args.kwargs["title"], "Ekran parlaklığını %40 yap")
            self.assertEqual(gate.call_args.kwargs["run"](), "done")
            action.assert_called_once_with({"action": "brightness_set", "value": 40})

    def test_revoke_blocks_queued_confirmation(self):
        allowed = True
        with patch("core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, \
                patch("actions.computer_settings.computer_settings") as action:
            request(allowed=lambda: allowed)
            allowed = False
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            action.assert_not_called()

    def test_reject_out_of_range_and_injected_fields(self):
        with patch("core.confirm.request") as gate:
            for raw in ('{"percent":0}', '{"percent":9}', '{"percent":101}',
                        '{"percent":true}', '{"percent":40.0}', '{"percent":"40"}',
                        '{"percent":40,"action":"shutdown"}',
                        '{"percent":40,"confirmed":true}', '{"percent":40,"percent":90}'):
                with self.subTest(raw=raw), self.assertRaises(RealtimeError):
                    request(raw)
            with self.assertRaises(RealtimeError):
                request(allowed=lambda: False)
            with self.assertRaises(RealtimeError):
                request(seen={"call_1"})
            gate.assert_not_called()

    def test_boundary_values_and_unavailable_gate(self):
        with patch("core.confirm.request", return_value="UI unavailable") as gate:
            for target in (10, 100):
                result = request(json.dumps({"percent": target}))
                self.assertEqual(json.loads(result["item"]["output"])["status"], "not_executed")
            self.assertEqual(gate.call_count, 2)
