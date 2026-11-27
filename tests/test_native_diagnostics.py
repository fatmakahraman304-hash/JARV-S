import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from actions import native_diagnostics as action
from core import native_diagnostics as native
from core.tasks.tools import TaskTools


class NativeDiagnosticsTests(unittest.TestCase):
    def test_cim_uses_fixed_read_only_command_and_checks_output(self):
        payload = {"operating_system": {"Caption": "Windows test"}, "processors": [], "graphics": [], "bios": []}
        process = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(native.subprocess, "run", return_value=process) as run:
            self.assertEqual(native._windows_cim(), payload)
        args = run.call_args.args[0]
        self.assertIn("-NoProfile", args)
        self.assertIn("-NonInteractive", args)
        self.assertIn("Get-CimInstance", args[-1])
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_failed_or_malformed_cim_is_not_reported_as_success(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(native.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="denied")):
            with self.assertRaisesRegex(RuntimeError, "denied"):
                native._windows_cim()
        with patch.object(Path, "is_file", return_value=True), \
             patch.object(native.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="{}", stderr="")):
            with self.assertRaises(ValueError):
                native._windows_cim()

    def test_incomplete_sources_are_honestly_reported(self):
        snapshot = {"errors": ["Windows CIM: timed out"], "metrics": {"battery": None}, "windows_cim": None}
        with patch.object(native, "collect", return_value=snapshot):
            text = action.native_diagnostics({})
        self.assertIn("status=unverified", text)
        self.assertNotIn("status=done", text)
        self.assertIn("<<<UNTRUSTED source=local-system-data>>>", text)

    def test_private_diagnostics_cannot_coexist_with_web_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = TaskTools(Path(directory), ["search_web", "system_snapshot", "recall_memory"], log=lambda _: None)
            self.assertEqual(tools.names, ["search_web"])
            self.assertIn("status=failed", tools.execute("system_snapshot", {}))
            local = TaskTools(Path(directory), ["system_snapshot", "notes"], log=lambda _: None)
            self.assertIn("system_snapshot", [x["name"] for x in local.declarations()])

    def test_cloud_does_not_confuse_server_hardware_with_users_computer(self):
        from core import cloud
        runtime = cloud.Runtime.__new__(cloud.Runtime)
        runtime.tasks = Mock()
        runtime.tasks.store.workdir.return_value = Path("task")
        runtime.toolbox = Mock()
        runtime.log = Mock()
        profile = Mock(mode="", tools=["system_snapshot", "notes"])
        with patch.object(cloud, "cloud_task_tools") as build:
            runtime._task_tools({"id": "x"}, profile)
        self.assertEqual(build.call_args.args[1], ["notes"])

    def test_real_local_snapshot_has_no_invented_measurements(self):
        result = native.collect()
        self.assertIn("observed_at", result)
        self.assertIn("errors", result)
        self.assertIn("cpu_percent", result["metrics"])
        self.assertNotIn("temperature", result["metrics"])

    @unittest.skipUnless(os.name == "nt", "requires native Windows CIM")
    def test_real_windows_cim_query(self):
        result = native._windows_cim(timeout=30)
        self.assertTrue(result["operating_system"].get("Caption"))
        self.assertIsInstance(result["processors"], list)
        self.assertIsInstance(result["graphics"], list)


if __name__ == "__main__":
    unittest.main()
