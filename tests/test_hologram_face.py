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


    def test_default_hologram_is_not_blue_human_skin(self):
        from gui.hologram_glsl import FRAG_HOLOGRAM
        from gui.android_gl import _human_relief, AndroidGL
        from core.avatar_mesh import get_head_mesh
        from core.hologram_mesh import with_shoulders
        self.assertIn("float phase = p.y * frequency", FRAG_HOLOGRAM)
        self.assertIn("float rim", FRAG_HOLOGRAM)
        self.assertIn("vec3 neon", FRAG_HOLOGRAM)
        self.assertIn("u_mouth", FRAG_HOLOGRAM)
        self.assertIn("u_open", FRAG_HOLOGRAM)
        self.assertNotIn("vec3 iris", FRAG_HOLOGRAM)
        self.assertNotIn("float hairC", FRAG_HOLOGRAM)
        base = get_head_mesh()
        mesh = with_shoulders(base)
        gl = AndroidGL(mesh["faces"], mesh["face_group"], mesh["verts"],
                       np.ones(len(mesh["verts"]), np.float32), mesh["jaw"],
                       mesh["fade"], mesh["landmarks"], subdiv=0,
                       look="holographic")
        self.assertEqual(gl.look, "holographic")
        # No protruding human hair: the scalp stays the contour-model surface.
        self.assertAlmostEqual(
            float(gl._disp[0]),
            float(_human_relief(mesh["verts"][:1], with_hair=False)[0]),
            places=5)

    def test_projection_scanlines_remain_on_animated_mesh(self):
        from core.hologram_face import ProjectionFace
        from core.avatar_mesh import get_head_mesh
        from core.hologram_mesh import with_shoulders
        projection = ProjectionFace(with_shoulders(get_head_mesh()))
        self.assertEqual(len(projection.a), len(projection.b))
        self.assertGreater(len(projection.a), 600)
        self.assertTrue(np.isfinite(projection.w).all())

    def test_reference_halo_and_ears_draw_in_qpainter(self):
        from core.hologram_finish import bloom, details, _hull
        from core.avatar_mesh import get_head_mesh
        from core.hologram_mesh import with_shoulders
        mesh = with_shoulders(get_head_mesh())
        img = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#020a15"))
        glow = QImage(80, 80, QImage.Format.Format_ARGB32_Premultiplied)
        glow.fill(QColor(0, 0, 0, 0))
        gp = QPainter(glow)
        gp.setPen(QColor(45, 224, 255))
        gp.drawEllipse(20, 20, 40, 40)
        gp.end()
        p = QPainter(img)
        bloom(p, glow, 120, 100, 0.4)
        xs = 160 + 85 * mesh["verts"][:, 0]
        ys = 150 - 85 * mesh["verts"][:, 1]
        details(p, xs, ys, mesh["n_head"], mesh["landmarks"], 0.4)
        p.end()
        self.assertTrue(_hull([(0, 0), (1, 0), (1, 1), (0, 1)]))
        self.assertNotEqual(img.pixelColor(160, 100), QColor("#020a15"))

    def test_reference_bust_is_wider_and_never_mutates_base_mesh(self):
        from core.avatar_mesh import get_head_mesh
        from core.hologram_mesh import with_shoulders
        base = get_head_mesh()
        before = base["verts"].copy()
        mesh = with_shoulders(base)
        np.testing.assert_array_equal(before, base["verts"])
        self.assertGreater(float(np.max(np.abs(mesh["verts"][:, 0]))),
                           1.5 * float(np.max(np.abs(before[:, 0]))))
        self.assertGreater(float(np.max(mesh["verts"][:mesh["n_head"], 0])),
                           float(np.max(before[:base["n_head"], 0])))

    def test_shoulder_extension_preserves_base_and_has_no_neck_gap(self):
        from core.avatar_mesh import get_head_mesh
        from core.hologram_mesh import with_shoulders
        base = get_head_mesh()
        old_fade = base["fade"].copy()
        mesh = with_shoulders(base)
        np.testing.assert_array_equal(base["fade"], old_fade)
        np.testing.assert_allclose(mesh["fade"][base["n_head"]:len(base["verts"])], 1)
        np.testing.assert_allclose(mesh["jaw"][len(base["verts"]):], 0)
        self.assertTrue(np.isfinite(mesh["normals"]).all())
        self.assertEqual(len(mesh["faces"]), len(mesh["face_group"]))
