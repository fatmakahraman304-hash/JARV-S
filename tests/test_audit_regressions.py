"""Regression tests for local state and Linux dashboard configuration."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from memory import memory_manager as memory


class MemoryTests(unittest.TestCase):
    def test_failed_replacement_preserves_previous_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long_term.json"
            with patch.object(memory, "MEMORY_PATH", path):
                memory.save_memory({"notes": {"one": "önce"}})
                old = path.read_bytes()
                with patch.object(memory.os, "replace", side_effect=OSError("disk failure")):
                    with self.assertRaises(OSError):
                        memory.save_memory({"notes": {"two": "sonra"}})
                self.assertEqual(path.read_bytes(), old)
                self.assertEqual(list(path.parent.iterdir()), [path])

    def test_concurrent_updates_share_a_single_transaction(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            memory, "MEMORY_PATH", Path(directory) / "long_term.json"
        ), contextlib.redirect_stdout(io.StringIO()):
            update = memory._recursive_update
            entered = threading.Event()
            proceed = threading.Event()

            def pause_first_write(target, changes):
                if "first" in changes and not entered.is_set():
                    entered.set()
                    proceed.wait(2)
                return update(target, changes)

            with patch.object(memory, "_recursive_update", side_effect=pause_first_write):
                first = threading.Thread(target=memory.update_memory, args=({"first": "one"},))
                second = threading.Thread(target=memory.update_memory, args=({"second": "two"},))
                first.start()
                try:
                    self.assertTrue(entered.wait(2))
                    second.start()
                    second.join(.2)
                    self.assertTrue(second.is_alive())
                finally:
                    proceed.set()
                    first.join(2)
                    if second.ident:
                        second.join(2)
            data = memory.load_memory()
            self.assertEqual(set(data) & {"first", "second"}, {"first", "second"})


class LocalStateTests(unittest.TestCase):
    def test_runtime_files_are_ignored(self):
        root = Path(__file__).resolve().parents[1]
        if not (root / ".git").exists():
            self.skipTest("Git checkout required")
        paths = ["config/api_keys.json", "config/api_keys.json.broken-1",
                 "config/certs/jarvis.key", "config/whatsapp_web/session",
                 "memory/tasks/job.json", "memory/routines.json", "reports/result.md"]
        ignored = subprocess.check_output(
            ["git", "check-ignore", "--no-index", "--", *paths], cwd=root, text=True
        )
        self.assertEqual(set(paths), set(ignored.splitlines()))


class FirewallTests(unittest.TestCase):
    def test_ufw_opens_each_dashboard_port(self):
        from dashboard import server

        def command(args, **kwargs):
            if args == ["ufw", "status"]:
                return subprocess.CompletedProcess(args, 0, "Status: active\n")
            return subprocess.CompletedProcess(args, 0, b"")

        with patch("sys.platform", "linux"), patch(
            "subprocess.run", side_effect=command
        ) as run, contextlib.redirect_stdout(io.StringIO()):
            server._ensure_network_access(8000, 8001)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["ufw", "status"],
            ["pkexec", "ufw", "allow", "8000/tcp"],
            ["pkexec", "ufw", "allow", "8001/tcp"],
        ])
