import ast
import asyncio
import json
from pathlib import Path
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core import hardware_privacy as privacy


class HardwarePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"cpu_percent": 87.25, "ram_percent": 61.2,
                         "cpu_temp_c": 80, "ram_total_gb": 64,
                         "serial": "PRIVATE-SERIAL", "network": "PRIVATE-WIFI"}
        self.player = Mock()

    def test_disabled_shows_local_details_but_sends_no_measurement(self):
        with patch.object(privacy, "model_sharing_enabled", return_value=False):
            result = privacy.system_status_result(self.snapshot, self.player)
        self.assertIn("status=done", result)
        for value in ("PRIVATE-SERIAL", "PRIVATE-WIFI", "87.25", "61.2"):
            self.assertNotIn(value, result)
        self.assertIn("PRIVATE-SERIAL", self.player.show_content.call_args.args[1])

    def test_opted_in_result_uses_allowlist_and_rechecks_revocation(self):
        with patch.object(privacy, "model_sharing_enabled", return_value=True):
            result = privacy.system_status_result(self.snapshot, self.player)
        self.assertIn("87.2", result)
        self.assertIn("61.2", result)
        for value in ("PRIVATE-SERIAL", "PRIVATE-WIFI", "ram_total_gb", "cpu_temp_c"):
            self.assertNotIn(value, result)
        with patch.object(privacy, "model_sharing_enabled", side_effect=[True, False]):
            self.assertNotIn("87.2", privacy.system_status_result(self.snapshot, self.player))

    def test_invalid_metrics_and_failed_settings_do_not_leak(self):
        with patch.object(privacy, "model_sharing_enabled", return_value=True):
            result = privacy.system_status_result({"cpu_percent": float("nan"), "ram_percent": True})
        self.assertIn('"cpu_percent": null', result)
        self.assertIn('"ram_percent": null', result)
        with patch("memory.config_manager.get_hardware_model_sharing", side_effect=OSError):
            self.assertFalse(privacy.model_sharing_enabled())


class MonitorRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_alert_is_local_only_without_consent(self):
        send, player = AsyncMock(), Mock()
        with patch.object(privacy, "model_sharing_enabled", return_value=False):
            sent = await privacy.route_monitor_alert("CPU 99% secret", player, send)
        self.assertFalse(sent)
        send.assert_not_awaited()
        self.assertIn("CPU 99% secret", player.write_log.call_args.args[0])

    async def test_authorized_model_gets_generic_not_original_alert(self):
        send, player = AsyncMock(), Mock()
        with patch.object(privacy, "model_sharing_enabled", return_value=True):
            sent = await privacy.route_monitor_alert("GPU 99% PRIVATE", player, send)
        self.assertTrue(sent)
        self.assertNotIn("99", send.await_args.args[0])
        self.assertNotIn("PRIVATE", send.await_args.args[0])

    async def test_actual_monitor_loop_obeys_local_only_policy(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "FridayLive")
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_system_monitor")
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        stub_asyncio = SimpleNamespace(sleep=sleep, to_thread=asyncio.to_thread)
        namespace = {"asyncio": stub_asyncio, "time": SimpleNamespace(monotonic=lambda: 100)}
        exec(compile(module, str(source), "exec"), namespace)
        player, send = Mock(), AsyncMock()
        instance = SimpleNamespace(_sys_monitor=SimpleNamespace(check=lambda: "CPU 99%"), ui=player,
                    session=SimpleNamespace(send_client_content=send), _awake=True,
                    _user_away=lambda: False, _quiet=lambda: False, _speaking_lock=threading.Lock(),
                    _is_speaking=False, _last_user_speech=0)
        with patch.object(privacy, "model_sharing_enabled", return_value=False):
            with self.assertRaises(asyncio.CancelledError):
                await namespace["_run_system_monitor"](instance)
        player.write_log.assert_called_once()
        send.assert_not_awaited()
