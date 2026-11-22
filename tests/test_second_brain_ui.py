"""Qt event loop remains responsive while the improvement scanner is waiting."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget
from gui.second_brain import SecondBrainPanel
from memory import continuity


class Window(QWidget):
    _log_sig = pyqtSignal(str)
    _codejob_sig = pyqtSignal(object)


class SecondBrainUI(unittest.TestCase):
    def test_background_scan_add_and_reopen_preserve_queue(self):
        app = QApplication.instance() or QApplication([])
        entered, release = threading.Event(), threading.Event()
        with tempfile.TemporaryDirectory() as directory, patch.object(continuity, "data_dir", return_value=Path(directory)):
            window = Window()
            window.show()
            with patch("core.second_brain.scan", side_effect=lambda: (entered.set(), release.wait(2))):
                panel = SecondBrainPanel(window)
                panel.show()
                self.assertTrue(entered.wait(1))
                app.processEvents()
                self.assertTrue(panel.isVisible())
                self.assertTrue(panel.busy)
                panel.input.setText("Konuşma akışını iyileştir")
                panel.add()
                self.assertEqual(panel.list.count(), 1)
                release.set()
                deadline = time.monotonic() + 3
                while panel.busy and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                self.assertFalse(panel.busy)
            panel.timer.stop()
            panel.close()
            restored = SecondBrainPanel(window)
            deadline = time.monotonic() + 3
            while restored.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            self.assertEqual(restored.list.count(), 1)
            self.assertFalse(restored.auto_plan.isChecked())
            restored.timer.stop()
            restored.close()
            window.close()


    def test_dock_opens_in_center_and_returns_to_face(self):
        from gui.window import MainWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.object(continuity, "data_dir", return_value=Path(directory)):
            window = MainWindow("")
            try:
                window.show()
                window._brain_btn.click()
                panel = window._second_brain_panel
                app.processEvents()
                self.assertIs(window._hud_cam_stack.currentWidget(), panel)
                self.assertFalse(panel.isWindow())
                self.assertTrue(window._brain_btn.isChecked())
                panel.back_requested.emit()
                self.assertIs(window._hud_cam_stack.currentWidget(), window.hud)
                self.assertFalse(window._brain_btn.isChecked())
                window._brain_btn.click()
                self.assertIs(window._second_brain_panel, panel)
                window._set_control_center(True)
                self.assertFalse(window._brain_btn.isChecked())
                self.assertTrue(window._cc_btn.isChecked())
            finally:
                panel = window.__dict__.get("_second_brain_panel")
                if panel is not None:
                    panel.timer.stop()
                    deadline = time.monotonic() + 3
                    while panel.busy and time.monotonic() < deadline:
                        app.processEvents()
                        time.sleep(.01)
                window.close()
