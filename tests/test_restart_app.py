import os
from pathlib import Path
import tempfile
import unittest
import subprocess
import time
from types import SimpleNamespace
from unittest.mock import patch

import psutil
from tools.restart_app import restart


class RestartTests(unittest.TestCase):
    def test_waits_for_exit_before_launch(self):
        events = []
        def launch(*args, **kwargs):
            events.append("launch")
            Path(kwargs["env"]["AETHER_RESTART_RECEIPT"]).touch()
            return SimpleNamespace(poll=lambda: None)
        with patch('tools.restart_app.psutil.Process') as process, patch('tools.restart_app.subprocess.Popen', side_effect=launch):
            process.return_value.wait.side_effect = lambda **kw: events.append('exit')
            self.assertEqual(restart(123, '.'), 0)
        self.assertEqual(events, ['exit', 'launch'])

    def test_child_exit_before_hud_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "main.py").write_text("raise SystemExit(12)")
            with patch('tools.restart_app.psutil.Process') as process:
                process.return_value.wait.return_value = None
                self.assertEqual(restart(os.getpid(), directory), 1)

    def test_timeout_never_launches_second_instance(self):
        with patch('tools.restart_app.psutil.Process') as process, patch('tools.restart_app.subprocess.Popen') as launch:
            process.return_value.wait.side_effect = psutil.TimeoutExpired(120)
            self.assertEqual(restart(123, '.'), 1)
            launch.assert_not_called()

    def launch_receipted_child(self, ending, wait_for_exit=False):
        children = []
        real_launch = subprocess.Popen
        with tempfile.TemporaryDirectory() as directory:
            source = ("import os,time\nfrom pathlib import Path\n"
                      "Path(os.environ['AETHER_RESTART_RECEIPT']).touch()\n" + ending)
            (Path(directory) / "main.py").write_text(source, encoding="utf-8")
            def launch(*args, **kwargs):
                child = real_launch(*args, **kwargs)
                children.append(child)
                if wait_for_exit:
                    child.wait(timeout=5)
                else:
                    receipt = Path(kwargs["env"]["AETHER_RESTART_RECEIPT"])
                    deadline = time.monotonic() + 5
                    while not receipt.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(.005)
                    self.assertTrue(receipt.exists())
                return child
            try:
                with patch('tools.restart_app.psutil.Process') as process, \
                        patch('tools.restart_app.subprocess.Popen', side_effect=launch):
                    process.return_value.wait.return_value = None
                    return restart(os.getpid(), directory)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=5)

    def test_receipt_from_already_exited_child_cannot_report_success(self):
        self.assertEqual(self.launch_receipted_child("raise SystemExit(12)\n", wait_for_exit=True), 1)

    def test_child_exiting_just_after_receipt_cannot_report_success(self):
        self.assertEqual(self.launch_receipted_child("time.sleep(.2)\nraise SystemExit(13)\n"), 1)

    def test_receipt_and_child_remaining_alive_are_accepted(self):
        self.assertEqual(self.launch_receipted_child("time.sleep(10)\n"), 0)
