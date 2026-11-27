"""GÜNCELLE lifecycle regressions without launching or replacing a live app."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class UpdateRestartStateTests(unittest.TestCase):
    def test_second_update_blocked_during_restart_delay(self):
        from gui.window import MainWindow
        window = SimpleNamespace(_updating=True, _update_btn=Mock(), _log=Mock(),
                                 _restart_after_update=Mock())
        with patch("gui.window.QTimer.singleShot") as timer, patch("gui.window.threading.Thread") as worker:
            MainWindow._update_done(window, True, "installed")
            self.assertFalse(window._updating)
            self.assertTrue(window._update_restart_pending)
            MainWindow._start_update(window)
            worker.assert_not_called()
            timer.assert_called_once_with(1500, window._restart_after_update)

    def test_restart_scheduled_once_even_if_remote_request_repeats(self):
        from gui.window import MainWindow
        window = SimpleNamespace(_update_btn=Mock(), _log=Mock(), _update_restart_pending=True)
        window._restart_after_update = lambda: MainWindow._restart_after_update(window)
        with patch("core.restart_manager.schedule_restart") as restart, patch(
                "PyQt6.QtWidgets.QApplication.instance") as app, patch("gui.window.threading.Thread") as worker:
            window._restart_after_update()
            MainWindow._start_update(window)
            window._restart_after_update()
            restart.assert_called_once()
            app.return_value.quit.assert_called_once()
            worker.assert_not_called()

    def test_restart_cannot_run_during_active_transaction(self):
        from gui.window import MainWindow
        window = SimpleNamespace(_updating=True)
        with patch("core.restart_manager.schedule_restart") as restart:
            MainWindow._restart_after_update(window)
            restart.assert_not_called()

    def test_restart_failure_retains_pending_state_and_retries_only_restart(self):
        from gui.window import MainWindow
        window = SimpleNamespace(_update_btn=Mock(), _log=Mock())
        window._restart_after_update = lambda: MainWindow._restart_after_update(window)
        with patch("core.restart_manager.schedule_restart", side_effect=[OSError("busy"), "helper"]) as restart, patch(
                "PyQt6.QtWidgets.QMessageBox.warning"), patch(
                "PyQt6.QtWidgets.QApplication.instance") as app, patch("gui.window.threading.Thread") as worker:
            window._restart_after_update()
            self.assertTrue(window._update_restart_pending)
            self.assertTrue(window._retry_update_restart)
            self.assertFalse(window._restart_in_progress)
            app.return_value.quit.assert_not_called()
            MainWindow._start_update(window)
            self.assertEqual(restart.call_count, 2)
            worker.assert_not_called()
            app.return_value.quit.assert_called_once()


class RestartHelperTests(unittest.TestCase):
    def test_even_immediate_zero_exit_cannot_confirm_scheduling(self):
        import os
        import sys
        import tempfile
        from pathlib import Path
        from core.restart_manager import schedule_restart
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools/restart_app.py").write_text("# test")
            child = Mock()
            child.poll.return_value = 0
            with patch.dict(os.environ, {"LOCALAPPDATA": directory, "AETHER_MANAGED_RESTART": "0"}), patch(
                    "core.restart_manager.subprocess.Popen", return_value=child):
                with self.assertRaisesRegex(RuntimeError, "hemen sonlandı"):
                    schedule_restart(root, 1234, executable=sys.executable)
