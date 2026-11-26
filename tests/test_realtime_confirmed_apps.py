import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from providers import realtime_apps as apps, realtime_tools as tools
from providers.realtime_session import RealtimeSession
from providers.realtime_settings import validate_settings
from providers.realtime_transport import RealtimeError


def request(raw='{"app":"calculator"}', allowed=lambda: True, seen=None):
    return tools.tool_output(
        {"output": [{"type": "function_call", "name": "request_open_app",
                     "status": "completed", "call_id": "call_1", "arguments": raw}]},
        guide_enabled=lambda: False, volume_enabled=lambda: False,
        app_enabled=allowed, seen=set() if seen is None else seen)


class ConfirmedAppTests(unittest.TestCase):
    def test_independent_permission_and_windows_only_declaration(self):
        cfg = {"cloud_consent": True, "api_key": "test-only"}
        self.assertFalse(validate_settings(cfg)["app_control"])
        self.assertTrue(validate_settings(dict(cfg, app_control="1"))["app_control"])
        for supported in (True, False):
            with patch.object(apps, "supported", return_value=supported):
                self.assertEqual(RealtimeSession(object(), app_enabled=lambda: True)
                                 ._setup["session"]["tools"],
                                 [tools.app_declaration()] if supported else [])
                self.assertEqual(RealtimeSession(object())._setup["session"]["tools"], [])

    def test_only_confirmed_callback_invokes_fixed_app(self):
        with patch.object(apps, "supported", return_value=True), patch(
                "core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, patch.object(
                apps, "launch", return_value="requested") as launch:
            result = request()
            launch.assert_not_called()
            self.assertEqual(json.loads(result["item"]["output"])["status"], "pending_confirmation")
            self.assertEqual(gate.call_args.kwargs["title"], "Hesap Makinesi aç")
            self.assertEqual(gate.call_args.kwargs["run"](), "requested")
            launch.assert_called_once_with("calculator")

    def test_revocation_and_unavailable_platform(self):
        allowed = True
        with patch.object(apps, "supported", return_value=True), patch(
                "core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate, patch.object(
                apps, "launch") as launch:
            request(allowed=lambda: allowed)
            allowed = False
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            launch.assert_not_called()
        with patch.object(apps, "supported", return_value=False), patch("core.confirm.request") as gate:
            with self.assertRaises(RealtimeError):
                request()
            gate.assert_not_called()

    def test_invalid_and_replayed_arguments_never_prompt(self):
        with patch.object(apps, "supported", return_value=True), patch("core.confirm.request") as gate:
            for raw in ('{}', '{"app":"cmd"}', '{"app":"powershell"}', '{"app":"https://example.org"}',
                        '{"app":"../calc.exe"}', '{"app":"calculator","args":"x"}',
                        '{"app":"calculator","confirmed":true}', '{"app":"calculator","app":"paint"}'):
                with self.subTest(raw=raw), self.assertRaises(RealtimeError):
                    request(raw)
            with self.assertRaises(RealtimeError):
                request(seen={"call_1"})
            gate.assert_not_called()

    def test_launcher_uses_absolute_fixed_executable_without_shell(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            target = directory / "calc.exe"
            target.touch()
            with patch.object(apps, "supported", return_value=True), patch.object(
                    apps, "_system_directory", return_value=directory), patch(
                    "providers.realtime_apps.subprocess.Popen") as start:
                self.assertIn("doğrulanmadı", apps.launch("calculator"))
                self.assertEqual(start.call_args.args, ([str(target)],))
                self.assertFalse(start.call_args.kwargs["shell"])
                self.assertEqual(start.call_args.kwargs["cwd"], str(directory))
                self.assertIn("NOT EXECUTED", apps.launch("paint"))
                self.assertIn("NOT EXECUTED", apps.launch("../calc.exe"))
                self.assertEqual(start.call_count, 1)

    def test_launcher_rejects_resolved_path_outside_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve() / "system"
            directory.mkdir()
            outside = directory.parent / "calc.exe"
            outside.touch()
            try:
                (directory / "calc.exe").symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with patch.object(apps, "supported", return_value=True), patch.object(
                    apps, "_system_directory", return_value=directory), patch(
                    "providers.realtime_apps.subprocess.Popen") as start:
                self.assertIn("NOT EXECUTED", apps.launch("calculator"))
                start.assert_not_called()
