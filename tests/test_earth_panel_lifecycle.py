"""Qt lifecycle tests without loading WebGL or a remote map service."""
import os
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton
from gui.earth_panel import EarthPanel


class EarthPanelLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = EarthPanel.__new__(EarthPanel)
        QWidget.__init__(self.panel)
        self.panel.view = Mock()
        self.panel._loaded = False
        self.panel._pending = None
        self.panel._search_generation = 0
        self.panel.status = QLabel(self.panel)
        self.panel.query = QLineEdit(self.panel)
        self.panel.search_button = QPushButton(self.panel)
        self.panel._search_done.connect(self.panel._finish_search)
        self.addCleanup(self.panel.close)

    def test_hidden_load_does_not_restart_rendering(self):
        self.assertFalse(self.panel.isVisible())
        self.panel._ready(True)
        self.panel.view.page().runJavaScript.assert_any_call("window.fridayEarth?.setActive(false)")

    def test_loading_failure_keeps_pending_destination_and_explains_fallback(self):
        self.panel.go_to(35.12, 33.94, 19)
        self.panel._ready(False)
        self.assertEqual(self.panel._pending["zoom"], 19)
        self.assertIn("Normal haritayı", self.panel.status.text())
        self.panel._ready(True)
        calls = self.panel.view.page().runJavaScript.call_args_list
        self.assertTrue(any("goTo(" in call.args[0] for call in calls))

    def test_import_failure_reports_error_and_reenables_search_on_qt_thread(self):
        self.panel.query.setText("synthetic city")
        with patch.dict(sys.modules, {"plugins.normal_map": None}):
            self.panel.search()
            deadline = time.monotonic() + 3
            while not self.panel.search_button.isEnabled() and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
        self.assertTrue(self.panel.search_button.isEnabled())
        self.assertIn("ulaşılamadı", self.panel.status.text())

    def test_stale_search_result_cannot_move_current_view(self):
        self.panel._search_generation = 3
        self.panel._finish_search(2, [{"name":"stale", "lat":0, "lon":0}], "")
        self.assertIsNone(self.panel._pending)
        self.panel.view.page().runJavaScript.assert_not_called()
