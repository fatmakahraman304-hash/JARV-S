"""Engine lifecycle is separate from conversation and contains no credentials."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.engine_status import engine_status, PHASES
from PyQt6.QtWidgets import QApplication
from gui.control_center import ControlCenter


class EngineStatusTests(unittest.TestCase):
    def test_only_ready_is_green(self):
        for phase in PHASES:
            self.assertEqual(engine_status(phase, "realtime")[1] == "GREEN", phase == "ready")

    def test_unknown_identifiers_never_display_raw_data(self):
        self.assertEqual(engine_status("private error", "private key"),
                         ("BEKLEMEDE", "TEXT_DIM", "MOTOR"))

    def test_actual_session_modes_are_distinct(self):
        self.assertEqual(engine_status("ready", "realtime")[2], "OPENAI REALTIME")
        self.assertEqual(engine_status("ready", "gemini")[2], "GEMINI LIVE")
        self.assertEqual(engine_status("ready", "pipeline")[2], "PIPELINE")

    def test_publish_only_notifies_status_channel(self):
        from tests._main_import import load_main
        live = load_main().FridayLive
        ui = Mock()
        live._publish_engine_status(SimpleNamespace(ui=ui), "retry", "realtime")
        ui.set_engine_status.assert_called_once_with("retry", "realtime")
        ui.set_state.assert_not_called()


class EnginePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_tracks_lifecycle_without_altering_conversation_state(self):
        panel = ControlCenter()
        self.addCleanup(panel.close)
        panel.set_state("SLEEPING", False, True)
        panel.set_engine_status("ready", "realtime")
        self.assertEqual(panel._engine_status.text(), "OPENAI REALTIME · OTURUM HAZIR")
        panel.set_engine_status("error", "realtime")
        self.assertIn("BAĞLANTI HATASI", panel._engine_status.text())
        self.assertEqual(panel._state, ("SLEEPING", False, True))
