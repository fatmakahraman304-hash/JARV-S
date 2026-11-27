"""FRIDAY is procedural cyan 3D, with a selectable feminine hologram."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]


class AetherVisuals(unittest.TestCase):
    def test_reactor_is_animated_cyan_geometry_not_an_embedded_picture(self):
        from gui.reactor import Reactor3D, _energy_palette
        from gui.theme import C
        _, gold, orange, _ = _energy_palette(QColor(C.PRI), QColor(C.PRI_DIM), QColor(C.WHITE), False)
        self.assertGreater(orange.blue(), orange.red())
        self.assertGreater(gold.blue(), 200)
        p = (ROOT / "gui" / "reactor.py").read_text(encoding="utf8")
        self.assertNotIn("QPixmap", p)
        self.assertNotIn("aether-core.webp", p)
        app = QApplication.instance() or QApplication([])
        reactor = Reactor3D()
        img = QImage(320, 320, QImage.Format.Format_ARGB32)
        img.fill(QColor("#030915"))
        painter = QPainter(img)
        try:
            reactor.step(.06, speaking=True, thinking=False, muted=False)
            reactor.paint(painter, 160, 140, 62,
                          QColor("#26d9ff"), QColor("#a3efff"),
                          QColor("#e9f9ff"), .5, True, "FRIDAY")
        finally:
            painter.end()
        self.assertNotEqual(img.pixelColor(160, 140), QColor("#030915"))

    def test_both_web_surfaces_share_procedural_renderer(self):
        desktop = (ROOT / "dashboard/static/reactor.js").read_text(encoding="utf8")
        web = (ROOT / "web/reactor.js").read_text(encoding="utf8")
        self.assertEqual(web, desktop)
        for part in ("icosphere(", "const rays = []", "const arcs = []",
                     "const shell = []", "FridayReactor"):
            self.assertIn(part, web)
        self.assertNotIn("new Image(", web)
        self.assertNotIn("aether-core.webp", web)
        server = (ROOT / "dashboard/server.py").read_text(encoding="utf8")
        self.assertNotIn('"aether-core.webp": "image/webp"', server)
        for path in ("web/aether-core.webp", "dashboard/static/aether-core.webp",
                     "gui/assets/aether-core.webp"):
            self.assertFalse((ROOT / path).exists(), path)

    def test_switchable_hud_persists_selected_view(self):
        from memory import config_manager as cm
        self.assertEqual(set(cm.HUD_STYLES), {"face", "core"})
        with patch.object(cm, "load_api_keys", return_value={"hud_style": "face"}):
            self.assertEqual(cm.get_hud_style(), "face")
        with patch.object(cm, "load_api_keys", return_value={}):
            self.assertEqual(cm.get_hud_style(), "core")
        with patch.object(cm, "_save_flag") as save:
            cm.save_hud_style("face")
            save.assert_called_once_with("hud_style", "face")

    def test_feminine_mesh_is_live_and_safe_for_visemes(self):
        from core.avatar_mesh import get_head_mesh, _sculpt_feminine_face
        from core.hologram_mesh import with_shoulders
        sample = np.array([[0.4, -0.72, 0.38], [-0.4, -0.72, 0.38],
                           [0.3, 0.2, 0.38]], dtype=np.float64)
        sculpted = _sculpt_feminine_face(sample, len(sample))
        self.assertLess(abs(sculpted[0, 0]), abs(sample[0, 0]))
        self.assertLess(abs(sculpted[1, 0]), abs(sample[1, 0]))
        base = get_head_mesh()
        verts_before = base["verts"].copy()
        holo = with_shoulders(base)
        np.testing.assert_array_equal(base["verts"], verts_before)
        self.assertEqual(len(holo["verts"]), len(holo["jaw"]))
        self.assertEqual(len(holo["faces"]), len(holo["face_group"]))
        self.assertTrue(np.isfinite(holo["normals"]).all())
        self.assertTrue(np.isfinite(holo["verts"]).all())
        self.assertGreater(float(np.max(holo["jaw"])), 0.0)
        self.assertIn("lips_out", holo["landmarks"])
        self.assertNotIn("QPixmap", (ROOT / "core/hologram_finish.py").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
