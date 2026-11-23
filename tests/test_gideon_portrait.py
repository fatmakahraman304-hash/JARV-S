"""Regression tests for the code-drawn Gideon portrait (never a bitmap)."""
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from core.gideon_portrait import face_layout, paint_portrait


class GideonPortraitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reference_proportions_are_not_old_tiny_dots(self):
        lay = face_layout(100, 50, 500, 700)
        self.assertGreater(lay["eye_w"], 150)
        self.assertGreater(lay["eye_h"], 60)
        self.assertAlmostEqual(lay["eyes_y"], 417.5)
        self.assertAlmostEqual(lay["mouth_y"], 621.2)
        self.assertAlmostEqual(lay["nose_y"], 549.8)
        self.assertLess(lay["brow_y"], lay["eyes_y"])
        self.assertGreater(lay["mouth_y"], lay["nose_y"])
        with self.assertRaises(ValueError):
            face_layout(0, 0, 0, 10)

    def render(self, eye_open=1.0, gaze=(0.0, 0.0), mouth=0.0):
        canvas = QImage(480, 550, QImage.Format.Format_ARGB32)
        canvas.fill(QColor("#020a1b"))
        painter = QPainter(canvas)
        try:
            paint_portrait(
                painter, 95.0, 30.0, 290.0, 435.0,
                eye_open=eye_open, gaze=gaze, mouth=mouth, energy=.4)
        finally:
            painter.end()
        data = canvas.bits()
        data.setsize(canvas.sizeInBytes())
        return np.frombuffer(data, dtype=np.uint8).copy()

    def test_live_blink_gaze_and_voice_mouth_change_pixels(self):
        open_eye = self.render(eye_open=1)
        blink = self.render(eye_open=0)
        gaze = self.render(gaze=(.90, -.50))
        speaking = self.render(mouth=.95)
        self.assertGreater(np.count_nonzero(open_eye != blink), 200)
        self.assertGreater(np.count_nonzero(open_eye != gaze), 100)
        self.assertGreater(np.count_nonzero(open_eye != speaking), 100)

    def test_no_image_assets_or_texture_readback(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "core" / "gideon_portrait.py").read_text(encoding="utf8")
        for forbidden in ("QPixmap", "QImage(", "texture2D", "drawImage(", "cv2.imread"):
            self.assertNotIn(forbidden, source)
        finish = (root / "core" / "hologram_finish.py").read_text(encoding="utf8")
        self.assertIn("from core.gideon_portrait import paint_portrait", finish)
        avatar = (root / "core" / "avatar.py").read_text(encoding="utf8")
        self.assertIn("gaze=tuple(self._gaze), mouth=self._mouth", avatar)


if __name__ == "__main__":
    unittest.main()
