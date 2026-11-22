"""The default male projection animates from the existing voice-driven rig."""
import os
import unittest
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QImage, QPainter
from core.avatar import HoloAvatar


class HologramFace(unittest.TestCase):
    def test_default_projection_draws_and_audio_changes_mouth_without_gpu(self):
        app = QApplication.instance() or QApplication([])
        avatar = HoloAvatar()
        self.assertEqual(avatar.style, "holographic")
        avatar.style = "projection"
        frames = []
        with patch.object(avatar, "_paint_android") as skin:
            for mouth in (0.0, 0.8):
                avatar._mouth = mouth
                image = QImage(480, 540, QImage.Format.Format_ARGB32)
                image.fill(QColor("#020a15"))
                painter = QPainter(image)
                avatar.paint(painter, 240, 235, 175, QColor("#ff9900"), QColor("#ffffff"))
                painter.end()
                pointer = image.bits()
                pointer.setsize(image.sizeInBytes())
                frames.append(np.frombuffer(pointer, dtype=np.uint8).copy())
            skin.assert_not_called()
        self.assertFalse(np.array_equal(frames[0], frames[1]))
        self.assertGreater(np.count_nonzero(frames[0] != np.tile([21, 10, 2, 255], 480 * 540)), 1000)


    def test_default_face_routes_to_smooth_3d_surface(self):
        app = QApplication.instance() or QApplication([])
        avatar = HoloAvatar()
        image = QImage(480, 540, QImage.Format.Format_ARGB32)
        image.fill(QColor("#020a15"))
        painter = QPainter(image)
        try:
            with patch.object(avatar, "_paint_android", return_value=True) as render:
                avatar.paint(painter, 240, 235, 175, QColor("#ffffff"), QColor("#ffffff"))
            render.assert_called_once()
            self.assertEqual(avatar.style, "holographic")
            self.assertLess(float(avatar._v0[:, 1].min()), -1.5)
            self.assertGreater(float(avatar._v0[:, 0].max()), 1.1)
        finally:
            painter.end()
