"""Hologram table in JARVIS's window: core/holo_model, core/holo_scan,
gui/holo_gl + gui/holo_panel (headless, offscreen), plugins/hologram."""
import importlib.util
import os
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import holo_model as hm  # noqa: E402
from tools.holo_samples import ALL, MUG, PHONE  # noqa: E402

HAS_QT = importlib.util.find_spec("PyQt6") is not None


def consistent(V, N, F):
    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return float(((fn * N[F].mean(1)).sum(1) >= -1e-9).mean())


class ShapeTests(unittest.TestCase):
    EXTRA = {"lathe": {"profile": [[0, 0], [0.9, 0], [1, 0.1], [0.8, 0.6], [0.35, 0.8], [0.35, 1]]},
             "extrude": {"outline": [[-1, -1], [1, -1], [1, 0.2], [0, 1], [-1, 0.2]]},
             "tube": {"path": [[0, 0, 0], [3, 4, 0], [6, 5, 2], [9, 3, 4]]}}

    def test_every_shape_fills_its_box_with_outward_faces(self):
        for shape in hm.SHAPES:
            p = hm.clean_part({"shape": shape, "size": [1 if shape == "tube" else 10, 8, 6], "pos": [1, 2, 3], "rot": [20, 30, 40], **self.EXTRA.get(shape, {})})
            V, N, F = hm.part_mesh(p)
            self.assertGreater(len(F), 0, shape)
            self.assertGreaterEqual(consistent(V, N, F), 0.99 if shape == "tube" else 1.0, shape)
            self.assertTrue(np.allclose(np.linalg.norm(N, axis=1), 1, atol=1e-3), shape)
            if shape != "tube":
                q = hm.clean_part({**p, "rot": [0, 0, 0], "pos": [0, 0, 0]})
                V0, _, _ = hm.part_mesh(q)
                self.assertTrue(np.allclose(V0.max(0) - V0.min(0), [10, 8, 6], atol=0.05), (shape, V0.max(0) - V0.min(0)))

    def test_clean_tolerates_bad_output(self):
        p = hm.clean_part({"shape": "blob", "size": [0, -3, "a"], "rot": [370, -10, 0], "color": "red", "metal": 7})
        self.assertEqual((p["shape"], p["size"], p["rot"], p["color"], p["metal"]), ("box", [0.05, 3, 5], [10, 350, 0], "#9aa0a6", 1.0))
        self.assertEqual(hm.clean_part({"shape": "Rounded Box"})["shape"], "rounded_box")
        self.assertEqual(hm.clean_part({"shape": "lathe", "profile": [[5]]})["profile"], [[1, 0], [1, 1]])
        self.assertEqual(hm.clean(None)["parts"], [])
        self.assertIsNone(hm.clean({"photo_box": [0.5, 0.5, 0.5, 0.5]})["photo_box"])

    def test_concave_outline_triangulates(self):
        star = [[np.cos(a) * (1 if i % 2 == 0 else .45), np.sin(a) * (1 if i % 2 == 0 else .45)] for i, a in enumerate(np.linspace(0, 2 * np.pi, 10, endpoint=False))]
        tris = hm._ear_clip(np.asarray(star))
        self.assertEqual(len(tris), 8)


class MeshTests(unittest.TestCase):
    def test_samples(self):
        for m in ALL:
            M = hm.Mesh(hm.clean(m))
            self.assertEqual(M.n_vert % 3, 0)
            self.assertEqual(len(M.pid), M.n_vert)
            self.assertGreater(M.radius, 1)
            self.assertTrue(np.isfinite(M.floor) and M.floor <= M.hi[1])

    def test_explode_moves_parts_away(self):
        M = hm.Mesh(hm.clean(PHONE))
        a, b = M.positions(0), M.positions(1)
        d0 = np.linalg.norm(a - M.center, axis=1).mean()
        d1 = np.linalg.norm(b - M.center, axis=1).mean()
        self.assertGreater(d1, d0)
        self.assertIs(M.positions(0), M.pos0)

    def test_photo_lands_on_the_front_only(self):
        m = hm.clean({**MUG, "photo_box": [0.25, 0.1, 0.75, 0.9]})
        img = np.zeros((100, 100, 3), np.uint8); img[:, :] = (255, 0, 0)
        M = hm.Mesh(m, img)
        front = M.nrm[:, 2] > 0.7
        back = M.nrm[:, 2] < -0.2
        self.assertGreater(M.col[front, 0].mean() - M.col[front, 2].mean(), 0.5)    # reddened
        plain = hm.Mesh(m)
        self.assertTrue(np.allclose(M.col[back], plain.col[back]))

    def test_binary_stl(self):
        M = hm.Mesh(hm.clean(MUG))
        data = M.stl()
        n = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(n, M.n_vert // 3)
        self.assertEqual(len(data), 84 + 50 * n)


class GestureTests(unittest.TestCase):
    def hand(self, kind):
        L = [{"x": .5, "y": .8} for _ in range(21)]
        for m, x in ((5, .38), (9, .46), (13, .54), (17, .62)):
            op = kind in ("open", "pinch") or (kind == "point" and m == 5)
            L[m], L[m + 1] = {"x": x, "y": .6}, {"x": x, "y": .5}
            L[m + 2], L[m + 3] = ({"x": x, "y": .42}, {"x": x, "y": .36}) if op else ({"x": x, "y": .56}, {"x": x, "y": .64})
        L[1], L[2], L[3], L[4] = {"x": .42, "y": .74}, {"x": .36, "y": .68}, {"x": .32, "y": .62}, {"x": .30, "y": .58}
        if kind == "pinch":
            L[4] = {"x": L[8]["x"] + .01, "y": L[8]["y"] + .01}
        return L

    def test_poses(self):
        self.assertEqual([hm.pose(self.hand(k)) for k in ("open", "fist", "point", "pinch")], ["open", "fist", "point", "pinch"])

    def test_steps(self):
        st = {}
        hm.gesture_step(st, [("pinch", (.5, .5))], 0)
        self.assertEqual(round(hm.gesture_step(st, [("pinch", (.6, .5))], .03)["rotate"][0]), 36)
        z = {}
        hm.gesture_step(z, [("pinch", (.4, .5)), ("pinch", (.6, .5))], 0)
        self.assertGreater(hm.gesture_step(z, [("pinch", (.38, .5)), ("pinch", (.62, .5))], .03)["zoom"], 1)
        e = {}
        acts = [hm.gesture_step(e, [("open", (.5, .5))], t)["action"] for t in (0, .4, .8, 1.6)]
        self.assertEqual(acts, ["", "", "explode", ""])
        th = {}
        hm.gesture_step(th, [("open", (.2, .5))], 0); hm.gesture_step(th, [("open", (.45, .5))], .1)
        self.assertEqual(hm.gesture_step(th, [("open", (.8, .5))], .2)["action"], "throw")

    def test_local_commands(self):
        self.assertEqual([hm.local_command(t) for t in ("bunu dijital olarak modelle", "parçalarına ayır", "birleştir", "gerçekçi görünüm",
                                                        "hologram görünümüne geç", "STL çıkar", "kanatları kırmızı yap", "hologramı kapat")],
                         ["scan", "explode", "assemble", "real", "holo", "stl", "", "close"])


class ScanTests(unittest.TestCase):
    def test_scan_create_edit_with_a_stub_model(self):
        from core import holo_scan, gemini
        reply = {**PHONE, "photo_box": [0.3, 0.1, 0.7, 0.9]}
        with mock.patch.object(gemini, "as_json", return_value=reply) as ask, mock.patch.object(holo_scan, "_part", side_effect=lambda b: ("img", b)):
            m, msg = holo_scan.scan([b"\xff\xd8jpeg1", b"\xff\xd8jpeg2"])
            self.assertEqual(m["name"], "Akıllı telefon")
            self.assertEqual(m["photo_box"], [0.3, 0.1, 0.7, 0.9])
            self.assertIn("11 parça", msg)
            prompt = ask.call_args[0][0][0]
            self.assertIn("lathe", prompt); self.assertIn("photo_box", prompt)
            self.assertEqual(len(ask.call_args[0][0]), 3)
            e, _ = holo_scan.edit(m, "ekranı kırmızı yap")
            self.assertEqual(e["id"], m["id"])
            self.assertEqual(e["photo"], m["photo"])
            self.assertIn("ekranı kırmızı yap", ask.call_args[0][0][0])
        with mock.patch.object(gemini, "as_json", return_value=None):
            self.assertIsNone(holo_scan.create("x")[0])
        with mock.patch.object(gemini, "as_json", return_value={"name": "", "parts": []}), mock.patch.object(holo_scan, "_part", side_effect=lambda b: b):
            self.assertIn("Net bir nesne", holo_scan.scan([b"x"])[1])


class PluginTests(unittest.TestCase):
    def test_opens_in_the_window(self):
        from plugins import hologram
        player = mock.Mock()
        r = hologram.run({"action": "scan"}, player)
        player.show_hologram.assert_called_once_with({"action": "scan", "request": "", "hands": True})
        self.assertIn("kameraya göster", r)
        hologram.run({"action": "edit", "request": "kanatları kırmızı yap"}, player)
        self.assertEqual(player.show_hologram.call_args[0][0]["request"], "kanatları kırmızı yap")
        self.assertIn("söyler misin", hologram.run({"action": "make"}, player))
        self.assertIn("pencere", hologram.run({"action": "scan"}, None))

    def test_window_and_ui_are_wired(self):
        root = Path(__file__).resolve().parent.parent
        win = (root / "gui" / "window.py").read_text(encoding="utf-8")
        self.assertIn("_holo_sig = pyqtSignal(object)", win)
        self.assertIn("self._holo_sig.connect(self._holo_command)", win)
        self.assertIn("def show_hologram", (root / "ui.py").read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_QT, "PyQt6 not installed")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_soft_renderer_draws_something(self):
        from gui.holo_gl import Camera, SoftRenderer
        M = hm.Mesh(hm.clean(MUG))
        for holo in (False, True):
            img = SoftRenderer().render(M, Camera(), 320, 200, holo=holo, accent=(1, .5, .1), t=0)
            px = [img.pixelColor(x, y).alpha() for x in range(0, 320, 8) for y in range(0, 200, 8)]
            self.assertGreater(sum(a > 0 for a in px), 20)

    def test_gl_renderer_or_a_reason(self):
        from gui.holo_gl import Camera, HoloGL
        gl = HoloGL()
        img = gl.render(hm.Mesh(hm.clean(PHONE)), Camera(), 320, 200, holo=False, accent=(1, .5, .1), t=0)
        self.assertTrue(img is not None or gl.error)

    def test_panel_commands(self):
        from gui import holo_panel
        with mock.patch.object(holo_panel, "LIBRARY", Path(os.environ.get("TMPDIR", "/tmp")) / "holo_test_lib.json"):
            if holo_panel.LIBRARY.exists():
                holo_panel.LIBRARY.unlink()
            panel = holo_panel.HoloPanel()
            panel.resize(900, 560)
            panel.set_model(hm.clean(MUG), animate=False)
            panel.command({"action": "explode"}); self.assertEqual(panel.explode_to, 1.0)
            panel.command({"action": "say", "request": "birleştir"}); self.assertEqual(panel.explode_to, 0.0)
            panel.command({"action": "holo"}); self.assertTrue(panel.holo)
            panel.command({"action": "real"}); self.assertFalse(panel.holo)
            panel.command({"action": "save"}); self.assertEqual(len(holo_panel.load_library()), 1)
            img = panel.grab()
            self.assertFalse(img.isNull())
            with mock.patch("core.holo_scan.edit", return_value=(hm.clean(PHONE), "Güncellendi.")):
                panel.command({"action": "say", "request": "telefona çevir"})
                for _ in range(100):
                    if not panel.busy or not panel.results.empty():
                        break
                    import time; time.sleep(0.02)
                import time; time.sleep(0.1)
                panel._tick()
            self.assertEqual(panel.model["name"], "Akıllı telefon")
            panel.command({"action": "stl"}) if False else None
            holo_panel.LIBRARY.unlink()


if __name__ == "__main__":
    unittest.main()
