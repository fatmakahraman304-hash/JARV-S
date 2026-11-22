import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import psutil
from tools.restart_app import restart


class RestartTests(unittest.TestCase):
    def test_waits_for_exit_before_launch(self):
        events = []
        def launch(*args, **kwargs):
            events.append("launch")
            Path(kwargs["env"]["MAYK_RESTART_RECEIPT"]).touch()
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
