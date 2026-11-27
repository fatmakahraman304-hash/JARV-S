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
        with patch.object(native, "collect", return_value=snapshot), patch.object(native, "model_sharing_enabled", return_value=False):
            text = action.native_diagnostics({})
        self.assertIn("status=unverified", text)
        self.assertNotIn("status=done", text)
        self.assertNotIn("<<<UNTRUSTED", text)

    def test_local_only_diagnostics_show_details_without_sending_them_to_model(self):
        snapshot = {"metrics": {"cpu_percent": 97, "memory": {"percent": 42}},
                    "windows_cim": {"serial": "secret-hardware"}, "errors": []}
        player = Mock()
        with patch.object(native, "collect", return_value=snapshot), patch.object(native, "model_sharing_enabled", return_value=False):
            result = action.native_diagnostics({}, player)
        self.assertIn("status=done", result)
        self.assertNotIn("secret-hardware", result)
        self.assertNotIn("97", result)
        self.assertIn("secret-hardware", player.show_content.call_args.args[1])
        self.assertIn("CPU kullanımı", player.show_content.call_args.args[1])

    def test_opted_in_metrics_are_minimized_for_both_model_paths(self):
        snapshot = {"metrics": {"cpu_percent": 97.123, "memory": {"percent": 42, "total_bytes": 12345},
                                "network_interfaces": [{"name": "private-wifi"}]},
                    "windows_cim": {"serial": "secret-hardware"}, "errors": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(native, "collect", return_value=snapshot), \
             patch.object(native, "model_sharing_enabled", return_value=True):
            tool = TaskTools(Path(directory), ["system_snapshot"], log=lambda _: None)
            for result in (action.native_diagnostics({}), tool.execute("system_snapshot", {})):
                self.assertIn("97.1", result)
                self.assertNotIn("secret-hardware", result)
                self.assertNotIn("private-wifi", result)
                self.assertNotIn("12345", result)

    def test_disabled_background_sharing_never_collects_metrics(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(native, "collect") as collect, \
             patch.object(native, "model_sharing_enabled", return_value=False):
            tool = TaskTools(Path(directory), ["system_snapshot"], log=lambda _: None)
            self.assertIn("status=failed", tool.execute("system_snapshot", {}))
            collect.assert_not_called()

    def test_revoking_sharing_during_collection_blocks_the_result(self):
        snapshot = {"metrics": {"cpu_percent": 97}, "errors": []}
        with tempfile.TemporaryDirectory() as directory, patch.object(native, "collect", return_value=snapshot), \
             patch.object(native, "model_sharing_enabled", side_effect=[True, False]):
            tool = TaskTools(Path(directory), ["system_snapshot"], log=lambda _: None)
            result = tool.execute("system_snapshot", {})
            self.assertIn("status=failed", result)
            self.assertNotIn("97", result)

    def test_model_sharing_requires_explicit_boolean_setting_and_fails_closed(self):
        from memory import config_manager
        for setting in ({}, {"hardware_model_sharing": "true"}, {"hardware_model_sharing": 1}):
            with patch.object(config_manager._storage, "read_document", return_value=setting):
                self.assertFalse(native.model_sharing_enabled())
        with patch.object(config_manager._storage, "read_document", return_value={"hardware_model_sharing": True}):
            self.assertTrue(native.model_sharing_enabled())
        with patch.object(config_manager._storage, "read_document", side_effect=OSError("bad config")):
            self.assertFalse(native.model_sharing_enabled())

    def test_corrupt_or_missing_primary_cannot_restore_old_backup_consent(self):
        from memory import config_manager
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "settings.json"
            backup = primary.with_name(primary.name + ".bak")
            backup.write_text('{"hardware_model_sharing": true}', encoding="utf-8")
            with patch.object(config_manager, "CONFIG_FILE", primary):
                self.assertFalse(config_manager.get_hardware_model_sharing())
                primary.write_text("{broken", encoding="utf-8")
                self.assertFalse(config_manager.get_hardware_model_sharing())
                primary.write_text('{"hardware_model_sharing": true}', encoding="utf-8")
                self.assertTrue(config_manager.get_hardware_model_sharing())

    def test_setting_updates_only_hardware_preference(self):
        from memory import config_manager
        with patch.object(config_manager, "_patch_config") as update:
            config_manager.save_hardware_model_sharing(True)
            update.assert_called_once_with(hardware_model_sharing=True)

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
