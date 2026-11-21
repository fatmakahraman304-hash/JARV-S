"""No-GUI restart scheduling tests. Never launch a real MAYK process."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.restart_manager import schedule_restart


class RestartManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "MAYK"
        self.root.mkdir()
        (self.root / "tools").mkdir()
        self.helper = self.root / "tools" / "restart_app.py"
        self.helper.write_text("# restart helper for test\n", encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "LOCALAPPDATA": self.tmp.name,
            "JARVIS_MANAGED_RESTART": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_helper_is_scheduled_before_gui_closes(self):
        proc = MagicMock()
        proc.poll.return_value = None
        with patch("core.restart_manager.subprocess.Popen", return_value=proc) as launch:
            kind = schedule_restart(self.root, 1234, executable=sys.executable)
        self.assertEqual(kind, "helper")
        launch.assert_called_once()
        args, kwargs = launch.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertTrue(Path(args[0][1]).samefile(self.helper))
        self.assertEqual(args[0][2], "1234")
        self.assertTrue(Path(args[0][3]).samefile(self.root))
        self.assertTrue(Path(kwargs["cwd"]).samefile(self.root))
        self.assertTrue((Path(self.tmp.name) / "Jarvis/logs/restart.log").is_file())

    def test_supervised_restart_does_not_launch_second_process(self):
        os.environ["JARVIS_MANAGED_RESTART"] = "1"
        self.helper.unlink()
        with patch("core.restart_manager.subprocess.Popen") as launch:
            self.assertEqual(schedule_restart(self.root, 1234), "managed")
            launch.assert_not_called()

    def test_missing_helper_prevents_unsafe_gui_shutdown(self):
        self.helper.unlink()
        with patch("core.restart_manager.subprocess.Popen") as launch:
            with self.assertRaises(FileNotFoundError):
                schedule_restart(self.root, 1234)
            launch.assert_not_called()

    def test_invalid_pid_rejected(self):
        with self.assertRaises(ValueError):
            schedule_restart(self.root, 0)

    def test_immediate_helper_failure_is_reported(self):
        proc = MagicMock()
        proc.poll.return_value = 1
        proc.returncode = 1
        with patch("core.restart_manager.subprocess.Popen", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "hemen sonlandı"):
                schedule_restart(self.root, 1234)


class LayoutContractTests(unittest.TestCase):
    """Source layout checks: these complement, not replace, a real Qt GUI test."""

    @classmethod
    def setUpClass(cls):
        cls.source = (
            Path(__file__).resolve().parents[1] / "gui/window.py"
        ).read_text(encoding="utf-8")

    def test_centre_is_full_width_with_floating_cards_and_dock(self):
        text = self.source
        beginning = text.index("        body = QHBoxLayout()")
        end = text.index("        self._dock.show()", beginning)
        layout = text[beginning:end]
        # Only the centre is in the body; the cards and the dock float above it.
        self.assertIn("body.addWidget(self._center_split", layout)
        self.assertNotIn("body.addWidget(self._left_panel", layout)
        self.assertNotIn("body.addWidget(self._right_panel", layout)
        self.assertLess(layout.index("self._left_panel = self._build_left_panel"),
                        layout.index("self._right_panel = self._build_right_panel"))
        self.assertIn("self._dock = self._build_dock()", layout)
        self.assertIn("card.setParent(central)", layout)

    def test_camera_overlay_avoids_conversation_card(self):
        self.assertEqual(
            self.source.count("cw.width() - self._right_inset() - pw - 22"), 2,
        )

    def test_floating_layer_is_laid_out_on_resize(self):
        text = self.source
        beginning = text.index("    def resizeEvent(self, event):")
        self.assertIn("self._fit_side_columns()", text[beginning:beginning + 200])
        fit = text[text.index("    def _fit_side_columns(self)"):
                   text.index("    def _set_card_open(self")]
        for item in ("self._dock.setGeometry", "self._left_panel.setGeometry",
                     "self._right_panel.setGeometry", "self._body_lay.setContentsMargins"):
            self.assertIn(item, fit)

    def test_dock_holds_command_line_and_voice_controls(self):
        text = self.source
        dock = text[text.index("    def _build_dock(self)"):
                    text.index("    def _build_quick_drawer(self)")]
        for item in ("self._build_input_row()", "self._mute_btn = IconButton",
                     "self._interrupt_btn = IconButton", "self._ctrl_btn = IconButton",
                     "self._sys_btn", "self._chat_btn"):
            self.assertIn(item, dock)

    def test_header_has_settings_state_and_clock_only(self):
        text = self.source
        beginning = text.index("    def _build_header(self)")
        end = text.index("    def _build_update_button(self)", beginning)
        header = text[beginning:end]
        self.assertIn("lay.addWidget(self._drawer_btn)", header)
        for item in ("_update_btn", "_fs_btn", "ÖZELLEŞTİR", "_ctrl_btn"):
            self.assertNotIn(item, header)
        self.assertIn("grid.addWidget(self._state_chip, 0, 1", header)
        self.assertIn("lay.addLayout(clock_col)", header)

    def test_update_auto_schedules_restart(self):
        text = self.source
        beginning = text.index("    def _update_done(self, changed, message)")
        end = text.index("    def _tick_clock(self)", beginning)
        restarter = text[beginning:end]
        self.assertIn("QTimer.singleShot(1500, self._restart_after_update)", restarter)
        self.assertIn("schedule_restart(project, os.getpid()", restarter)
        self.assertIn("self._restart_requested = True", restarter)
        self.assertIn("QApplication.instance().quit()", restarter)


if __name__ == "__main__":
    unittest.main()
