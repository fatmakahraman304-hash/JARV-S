"""Hidden animation work pauses while audio schedules retain their meaning."""
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor
from gui.hud import HudCanvas
from core.avatar import HoloAvatar


class HudPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.enterContext(patch.object(HudCanvas, "paintEvent", lambda *_: None))
        self.enterContext(patch("memory.config_manager.get_hud_style", return_value="face"))
        self.widget = HudCanvas("")
        self.widget._avatar = Mock()
        self.addCleanup(self.widget.close)
        self.addCleanup(self.widget._tmr.stop)

    def test_hidden_canvas_does_not_advance_avatar_or_request_paint(self):
        with patch.object(self.widget, "update") as update:
            for _ in range(3):
                self.widget._step()
        self.widget._avatar.step.assert_not_called()
        update.assert_not_called()
        self.assertGreaterEqual(self.widget._tmr.interval(), 200)

    def test_show_resumes_fast_timer_and_current_voice_schedule(self):
        self.widget.hide()
        frames = [(0.2, 0.1, 0.0), (0.8, 0.7, 0.1), (0.4, 0.2, 0.0)]
        self.widget.push_visemes(frames, .02, 100.0)
        self.widget.speaking = True
        self.widget.show()
        self.assertEqual(self.widget._tmr.interval(), 16)
        with patch("gui.hud.time.time", return_value=100.025):
            self.widget._step()
        self.widget._avatar.step.assert_called_once()
        self.assertEqual(self.widget._avatar.step.call_args.kwargs["v_open"], .7)
        self.assertTrue(self.widget.speaking)

    def test_minimized_canvas_also_skips_animation_work(self):
        self.widget.show()
        with patch.object(self.widget, "_on_screen", return_value=False):
            self.widget._step()
        self.widget._avatar.step.assert_not_called()
        self.assertGreaterEqual(self.widget._tmr.interval(), 200)

    def test_expired_visemes_are_not_replayed_after_restore(self):
        self.widget.push_visemes([(1., 1., 0.)], .02, 10.0)
        self.widget.show()
        with patch("gui.hud.time.time", return_value=100.0):
            self.widget._step()
        self.assertIsNone(self.widget._visemes)
        self.assertIsNone(self.widget._avatar.step.call_args.kwargs["v_seq"])


class RenderAllocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_small_pose_changes_reuse_buffer_buckets_without_downscaling(self):
        avatar = HoloAvatar()
        sizes = []
        class Renderer:
            def render(self, verts, norms, xs, ys, w, h, **kwargs):
                sizes.append((w, h))
                self.assert_geometry = (float(xs.max()) < w, float(ys.max()) < h)
                image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(0)
                return image
        avatar._gl = renderer = Renderer()
        image = QImage(560, 560, QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        try:
            for yaw in (.0, .001, .002, .003, .004):
                avatar._yaw = yaw
                avatar.paint(painter, 280, 240, 168, QColor("cyan"), QColor("white"))
        finally:
            painter.end()
        self.assertTrue(all(renderer.assert_geometry))
        self.assertLess(len(set(sizes)), 5)
        self.assertTrue(all(w % 32 == 0 and h % 32 == 0 for w, h in sizes))
        self.assertTrue(all(w <= 4096 and h <= 4096 for w, h in sizes))
