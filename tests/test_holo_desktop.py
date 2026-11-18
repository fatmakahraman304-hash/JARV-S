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
             "tube": {"path": [[0, 0, 0], [3, 4, 0], [6, 5, 2], [9, 3, 4]]},
             "loft": {"sections": [[0, 0.6, 0.8, 0, 0], [0.4, 1, 1, 0, 0], [0.8, 0.7, 0.9, 0, 0], [1, 0.3, 0.4, 0, 0]], "round": 3}}

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


class ExpandTests(unittest.TestCase):
    def test_array_radial_mirror(self):
        m = hm.clean({"parts": [
            {"name": "kanat", "shape": "box", "size": [1, 4, 0.3], "pos": [2, 2, 5], "array": {"count": 10, "step": [0, 0, -0.6]}, "mirror": "x"},
            {"name": "civata", "shape": "cylinder", "size": [0.5, 0.5, 0.5], "pos": [6, 1, 0], "radial": {"count": 8, "axis": "y", "center": [0, 1, 0]}},
            {"name": "rampa", "shape": "wedge", "size": [3, 2, 1], "pos": [3, 1, 0], "rot": [0, 30, 0], "mirror": "x"}]})
        M = hm.Mesh(m)
        self.assertEqual(M.pieces, 20 + 8 + 2)
        self.assertEqual(sorted(M.part_center), [0, 1, 2])
        c = np.array(M.inst_center)
        self.assertTrue(np.allclose(sorted(np.round(c[20:28, 0], 2)), sorted(np.round(6 * np.cos(np.arange(8) * np.pi / 4), 2)), atol=0.05))
        w = c[28:30]
        self.assertAlmostEqual(w[0, 0], -w[1, 0], places=4)            # the mirrored wedge is a true mirror image
        self.assertTrue(np.allclose(w[0, 1:], w[1, 1:], atol=1e-4))
        V, N, F = hm.part_mesh(hm.expand(m)[-1][1])
        self.assertEqual(consistent(V, N, F), 1.0)

    def test_finish_and_limits(self):
        p = hm.clean_part({"finish": "Carbon", "array": {"count": 500}, "radial": {"count": 1}})
        self.assertEqual(p["finish"], "carbon")
        self.assertEqual(p["array"]["count"], 64)
        self.assertNotIn("radial", p)
        self.assertEqual(hm.clean_part({"finish": "lava"})["finish"], "none")
        many = hm.clean({"parts": [{"shape": "box", "array": {"count": 64}, "radial": {"count": 72}}]})
        self.assertEqual(len(hm.expand(many)), hm.MAX_INSTANCES)

    def test_rounded_box_stays_light(self):
        V, N, F = hm.part_mesh(hm.clean_part({"shape": "rounded_box", "size": [2, 1, 2], "radius": 0.25}))
        self.assertLess(len(F), 4000)


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
                                                        "hologram görünümüne geç", "STL çıkar", "kanatları kırmızı yap", "hologramı kapat",
                                                        "daha fazla ayrıntı ekle", "kesit göster", "ölçüleri göster", "hepsini göster")],
                         ["scan", "explode", "assemble", "real", "holo", "stl", "", "close", "detail", "cut", "measure", "show_all"])


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
            self.assertEqual(len(ask.call_args[0][0]), 2)          # last pass: prompt + one photo
            e, _ = holo_scan.edit(m, "ekranı kırmızı yap")
            self.assertEqual(e["id"], m["id"])
            self.assertEqual(e["photo"], m["photo"])
            self.assertIn("ekranı kırmızı yap", ask.call_args[0][0][0])
        more = {**reply, "parts": PHONE["parts"] + [{"name": "Vida", "shape": "cylinder", "size": [0.2, 0.1, 0.2], "pos": [0, 0.05, 0]}]}
        with mock.patch.object(gemini, "as_json", side_effect=[reply, more, more]) as ask, mock.patch.object(holo_scan, "_part", side_effect=lambda b: b):
            steps = []
            m, _ = holo_scan.scan([b"a", b"b"], progress=steps.append)
            self.assertEqual(len(m["parts"]), 12)                       # the detail pass added a part
            self.assertEqual(steps, ["AYRINTILANDIRILIYOR…"] * 2)        # thin model: two detail passes
            self.assertIn("ADD 30 to 90 new part entries", ask.call_args[0][0][0])
        with mock.patch.object(gemini, "as_json", side_effect=[reply, {"parts": []}, {"parts": []}]), mock.patch.object(holo_scan, "_part", side_effect=lambda b: b):
            self.assertEqual(len(holo_scan.scan([b"a"])[0]["parts"]), 11)  # a failed detail pass keeps the first model
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
            panel.command({"action": "cut"}); self.assertEqual(panel.cut, 0.5)
            panel.command({"action": "measure"}); self.assertTrue(panel.measure)
            panel.command({"action": "say", "request": "sadece kulpu göster"}); self.assertEqual(panel.iso, 1)
            panel.command({"action": "say", "request": "hepsini göster"}); self.assertEqual(panel.iso, -1)
            img = panel.grab(); self.assertFalse(img.isNull())
            panel.command({"action": "cut", "on": False}); self.assertIsNone(panel.cut)
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


class RealEngineTests(unittest.TestCase):
    def _glb(self, tmp):
        from core import glb
        V1, N1, F1 = hm.part_mesh(hm.clean_part({"shape": "sphere", "size": [2, 2, 2], "pos": [0, 1, 0]}))
        V2, N2, F2 = hm.part_mesh(hm.clean_part({"shape": "box", "size": [1, 1, 1], "pos": [3, 0.5, 0]}))
        data = glb.write([{"V": np.vstack([V1, V2]), "N": np.vstack([N1, N2]), "F": np.vstack([F1, F2 + len(V1)]),
                           "color": [0.8, 0.2, 0.1, 1], "name": "gövde"}])
        p = Path(tmp) / "m.glb"
        p.write_bytes(data)
        return str(p), data

    def test_glb_roundtrip_and_scan_mesh(self):
        import tempfile
        from core import glb
        with tempfile.TemporaryDirectory() as t:
            path, data = self._glb(t)
            prims = glb.load(data)
            self.assertEqual(len(prims), 1)
            m = hm.clean({"glb": path, "height_cm": 50, "name": "test", "parts": []})
            M = hm.build_mesh(m)
            self.assertEqual(M.pieces, 2)                           # the sphere and the box come apart
            self.assertAlmostEqual(float(M.size[1]), 50.0, places=3)  # scaled to the real height
            self.assertAlmostEqual(float(M.floor), 0.0, places=4)
            self.assertEqual([p["name"] for p in m["parts"]], ["gövde 1", "gövde 2"])
            self.assertGreater(np.linalg.norm(M.positions(1.0) - M.pos0), 0)
            self.assertEqual(len(M.stl()), 84 + 50 * (M.n_vert // 3))
            m["upright"] = 1; m["parts"] = []
            self.assertAlmostEqual(float(hm.build_mesh(m).size[1]), 50.0, places=3)
        with self.assertRaises(glb.GlbError):
            glb.load(b"not a glb at all, sorry")

    def test_strays_are_dropped(self):
        parts = [{"shape": "box", "size": [10, 10, 10], "pos": [i * 5, 5, 0]} for i in range(8)] + \
                [{"shape": "box", "size": [0.5, 0.5, 0.5], "pos": [3, 600, 4]}]
        self.assertEqual(len(hm.clean({"parts": parts})["parts"]), 8)

    def test_providers_fall_back(self):
        import sys as _s
        import tempfile
        import types
        from core import holo_ai3d
        calls = []

        class FakeJob:
            def __init__(self, v): self.v = v
            def result(self, timeout=None):
                if isinstance(self.v, Exception):
                    raise self.v
                return self.v

        with tempfile.TemporaryDirectory() as t:
            good = Path(t) / "textured_mesh.glb"; good.write_bytes(b"glTF" + b"\0" * 2000)

            class FakeClient:
                def __init__(self, space, token=None, verbose=False):
                    self.space = space; calls.append(space)
                def submit(self, api_name=None, **kw):
                    if self.space.startswith("microsoft"):
                        return FakeJob(RuntimeError("You have exceeded your GPU quota (ZeroGPU)"))
                    return FakeJob((str(Path(t) / "white.glb"), {"value": str(good)}, "<html>", {}, 1))

            fake = types.ModuleType("gradio_client")
            fake.Client, fake.handle_file = FakeClient, (lambda p: p)
            with mock.patch.dict(_s.modules, {"gradio_client": fake}):
                data, prov, msg = holo_ai3d.image_to_3d(str(good))
            self.assertEqual(prov, "Hunyuan3D-2.1")
            self.assertTrue(data.startswith(b"glTF"))
            self.assertEqual(calls[:2], ["microsoft/TRELLIS.2", "tencent/Hunyuan3D-2.1"])

            class DeadClient(FakeClient):
                def submit(self, api_name=None, **kw):
                    return FakeJob(RuntimeError("ZeroGPU quota exceeded"))
            fake.Client = DeadClient
            with mock.patch.dict(_s.modules, {"gradio_client": fake}), mock.patch.object(holo_ai3d, "_token", return_value=""):
                data, prov, msg = holo_ai3d.image_to_3d(str(good))
            self.assertIsNone(data)
            self.assertIn("Hugging Face", msg)

    def test_engine_commands(self):
        self.assertEqual([hm.local_command(t) for t in ("modeli doğrult", "parça modeli kullan", "gerçek 3B yap")],
                         ["upright", "parts_engine", "real_engine"])

    def test_hf_token_action(self):
        from plugins import hologram
        with mock.patch("memory.config_manager.save_hf_token") as save:
            self.assertIn("kaydettim", hologram.run({"action": "hf_token", "request": "hf_" + "a" * 30}, None))
            save.assert_called_once()
            self.assertIn("benzemiyor", hologram.run({"action": "hf_token", "request": "abc"}, None))


class PanelHelperTests(unittest.TestCase):
    def test_sharpest_frame(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("opencv not installed")
        rng = np.random.default_rng(1)
        sharp = (rng.random((120, 160)) * 255).astype(np.uint8)
        blur = cv2.GaussianBlur(sharp, (15, 15), 6)
        enc = lambda im: cv2.imencode(".jpg", im)[1].tobytes()
        frames = [enc(blur), enc(sharp), enc(blur)]
        if not HAS_QT:
            self.skipTest("PyQt6 not installed")
        from gui.holo_panel import sharpest
        self.assertEqual(sharpest(frames), frames[1])

    def test_new_commands(self):
        self.assertEqual([hm.local_command(t) for t in ("dönen video çek", "iptal et")], ["video", "cancel"])


class ExportTests(unittest.TestCase):
    def test_obj_and_glb_round_trip(self):
        from core import glb
        model = hm.clean({"name": "Kupa", "parts": [{"name": "gövde", "shape": "cylinder", "size": [8, 10, 8], "color": "#ff0000", "metal": 0.2}]})
        mesh = hm.build_mesh(model)
        obj = hm.export_obj(mesh).decode()
        self.assertEqual(obj.count("\nv "), mesh.n_vert)
        self.assertEqual(obj.count("\nf "), mesh.n_vert // 3)
        prims = glb.load(hm.export_glb(mesh, model))
        self.assertEqual(sum(len(p["F"]) for p in prims), mesh.n_vert // 3)
        self.assertAlmostEqual(prims[0]["color"][0], 1.0, places=2)

    def test_gallery_commands(self):
        self.assertEqual(hm.local_command("galeriyi aç"), "lib")
        self.assertEqual(hm.local_command("dışa aktar"), "stl")


@unittest.skipUnless(HAS_QT, "PyQt6 not installed")
class DraftFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_quota_failure_gives_photo_draft_and_asks_for_key(self):
        import tempfile
        from unittest import mock
        from core import holo_ai3d, holo_scan
        from gui.holo_panel import HoloPanel
        with tempfile.TemporaryDirectory() as t:
            ref = Path(t) / "ref.jpg"
            ref.write_bytes(b"\xff\xd8fake")
            panel = HoloPanel()
            draft = hm.clean({"name": "Kask", "parts": [{"shape": "sphere", "size": [20, 20, 20]}]})
            with mock.patch.object(holo_ai3d, "reference_image", return_value=(str(ref), "")), \
                 mock.patch.object(holo_ai3d, "GLB_DIR", Path(t)), \
                 mock.patch.object(holo_ai3d, "measure", return_value={}), \
                 mock.patch.object(holo_ai3d, "image_to_3d", return_value=(None, "", "Kota dolmuş; hf_token ekle.")), \
                 mock.patch.object(holo_scan, "scan", return_value=(draft, "Kask hazır.")) as scan, \
                 mock.patch.object(holo_scan, "create") as create:
                m, msg = panel._make("bir Iron Man kaskı")
            self.assertTrue(m["draft"])
            self.assertIn("TASLAK", msg)
            scan.assert_called_once()                       # modelled from the photoreal picture, not from text
            create.assert_not_called()
            self.assertTrue(panel._need_key)
            self.assertEqual(panel._retry[1], "bir Iron Man kaskı")
            self.assertTrue(hm.clean(m)["draft"])
