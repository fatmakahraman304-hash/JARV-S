"""The autonomous brain graph shows evidence while workers stay off Qt."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QLineEdit
from gui.second_brain import SecondBrainPanel
from memory import continuity


class Window(QWidget):
    _log_sig = pyqtSignal(str)
    _codejob_sig = pyqtSignal(object)


class SecondBrainUI(unittest.TestCase):
    def wait(self, app, panel):
        deadline = time.monotonic() + 3
        while panel.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        self.assertFalse(panel.busy)

    def test_graph_follows_real_phase_and_pausing_stops_flow(self):
        app = QApplication.instance() or QApplication([])
        entered, release = threading.Event(), threading.Event()
        data = {"enabled": True, "area": "memory", "phase": "Analiz",
                "events": [{"time": time.time(), "area": "memory", "phase": "Analiz",
                            "detail": "Hafıza kaynakları inceleniyor."}], "items": []}
        def snapshot():
            entered.set()
            release.wait(2)
            return data
        window = Window()
        window._brain_controller = Mock(snapshot=snapshot)
        window.show()
        panel = SecondBrainPanel(window)
        try:
            panel.show()
            app.processEvents()
            self.assertTrue(entered.wait(1))
            self.assertTrue(panel.busy)
            self.assertTrue(panel.isVisible())
            self.assertEqual(panel.findChildren(QLineEdit), [])
            release.set()
            self.wait(app, panel)
            self.assertEqual(panel.canvas._counts, {"memory": 1})
            self.assertIn("Hafıza kaynakları", panel.detail.toPlainText())
            panel.finished(dict(data, enabled=False))
            self.assertEqual(panel.canvas._counts, {})
            panel.hide()
            self.assertFalse(panel.animation.isActive())
        finally:
            release.set()
            panel.timer.stop()
            panel.animation.stop()
            panel.close()
            window.close()

    def test_dock_opens_in_center_and_returns_to_face(self):
        from gui.window import MainWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.object(continuity, "data_dir", return_value=Path(directory)):
            window = MainWindow("")
            try:
                window.show()
                self.assertEqual(window._brain_btn._kind, "brain")
                self.assertEqual(window._brain_btn.text(), "")
                window._brain_btn.click()
                panel = window._second_brain_panel
                self.wait(app, panel)
                self.assertIs(window._hud_cam_stack.currentWidget(), panel)
                self.assertFalse(panel.isWindow())
                panel.back_requested.emit()
                self.assertIs(window._hud_cam_stack.currentWidget(), window.hud)
                self.assertFalse(window._brain_btn.isChecked())
                window._brain_btn.click()
                self.wait(app, panel)
                window._set_control_center(True)
                self.assertFalse(window._brain_btn.isChecked())
                self.assertTrue(window._cc_btn.isChecked())
            finally:
                panel = window.__dict__.get("_second_brain_panel")
                if panel is not None:
                    panel.timer.stop()
                    panel.animation.stop()
                    self.wait(app, panel)
                window.close()
