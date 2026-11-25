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
        data = {"enabled": True, "area": "memory", "phase": "Deneniyor",
                "events": [{"time": time.time(), "area": "memory", "status": "running",
                            "detail": "Hafıza kaynakları inceleniyor."}], "results": []}
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

    def test_report_copy_error_filter_and_visible_scope(self):
        app = QApplication.instance() or QApplication([])
        window = Window()
        window._brain_controller = Mock()
        panel = SecondBrainPanel(window)
        rows = [{'area': 'voice', 'status': 'failed', 'detail': 'PCM fixture mismatch',
                 'location': 'feature_checks.py:10', 'duration_ms': 3, 'updated': time.time()},
                {'area': 'memory', 'status': 'passed', 'detail': 'Memory fixture passed',
                 'location': '', 'duration_ms': 2, 'updated': time.time()}]
        try:
            panel.finished({'enabled': True, 'phase': 'Hata', 'area': 'voice',
                            'results': rows, 'events': []})
            self.assertIn('Hata: 1', panel.summary.text())
            self.assertIn('PCM fixture mismatch', panel.detail.toPlainText())
            panel.errors.setChecked(True)
            self.assertNotIn('Memory fixture passed', panel.detail.toPlainText())
            panel.copy.click()
            copied = QApplication.clipboard().text()
            self.assertIn('PCM fixture mismatch', copied)
            self.assertIn('Mikrofon, hoparlör ve canlı ses denenmedi', copied)
            self.assertIn('feature_checks.py:10', copied)
        finally:
            panel.close()
            window.close()

    def test_real_controller_probe_keeps_qt_responsive(self):
        from core.second_brain_service import Controller
        from PyQt6.QtCore import QTimer
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory, patch.object(continuity, 'data_dir', return_value=Path(directory)):
            window = Window()
            controller = Controller(Mock())
            window._brain_controller = controller
            panel = SecondBrainPanel(window)
            ticks = []
            timer = QTimer()
            timer.setInterval(10)
            timer.timeout.connect(lambda: ticks.append(True))
            worker = threading.Thread(target=lambda: controller.cycle(now=100))
            try:
                timer.start()
                worker.start()
                deadline = time.monotonic() + 10
                while worker.is_alive() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.005)
                worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertGreater(len(ticks), 0)
                snapshot = controller.snapshot()
                self.assertEqual(snapshot['results'][0]['status'], 'passed')
                panel.finished(snapshot)
                self.assertIn('Geçti: 1', panel.summary.text())
            finally:
                controller.stop()
                worker.join(3)
                timer.stop()
                panel.close()
                window.close()
