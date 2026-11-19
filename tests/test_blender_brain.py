"""JARVIS's Blender brain: lessons, script checks, the fix-and-retry loop, and
(with a real Blender on PATH) scripts, self-study and the hologram studio render."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import _blender_brain as brain
from plugins import blender_studio as studio

GOOD = """import bpy
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 1))
obj = bpy.context.active_object
obj.name = "Küre"
mat = bpy.data.materials.new("Krom")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Metallic"].default_value = 1.0
bsdf.inputs["Roughness"].default_value = 0.15
obj.data.materials.append(mat)
cam = bpy.data.objects.new("Kamera", bpy.data.cameras.new("Kamera"))
bpy.context.collection.objects.link(cam)
cam.location = (4, -4, 3)
bpy.context.scene.camera = cam
(OUT / "not.txt").write_text("tamam")
"""
BROKEN = GOOD.replace('inputs["Roughness"]', 'inputs["Specular"]')          # a 3.x socket name: KeyError in 4.x


class Lessons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(brain, "LESSONS", Path(self.tmp.name) / "lessons.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_remember_and_recall_closest(self):
        brain.remember("recipe", "kırmızı bir araba modelle", [{"op": "create", "kind": "cube", "name": "Gövde"}])
        brain.remember("script", "ahşap bir masa yap", "import bpy\n")
        brain.remember("tip", "Cam malzemede Transmission Weight 1 olsun", "Cam malzemede Transmission Weight 1 olsun")
        got = brain.recall("mavi bir araba yap")
        self.assertEqual(got[0]["request"], "kırmızı bir araba modelle")
        text = brain.lessons_prompt("cam bardak")
        self.assertIn("Tip from the user", text)
        brain.remember("tip", "Cam malzemede Transmission Weight 1 olsun", "Cam malzemede Transmission Weight 1 olsun")
        self.assertEqual(len(brain.load()), 3)                     # the same lesson is kept once
        self.assertIn("1 tarif", brain.summary())

    def test_code_checks(self):
        self.assertEqual(brain.clean_code("```python\nimport bpy\nx = 1\n```"), "import bpy\nx = 1\n")
        self.assertEqual(brain.check_code(GOOD), "")
        self.assertIn("izin verilmeyen", brain.check_code("import bpy\nimport subprocess\nsubprocess.run('x')"))
        self.assertIn("SyntaxError", brain.check_code("import bpy\nif True print(1)"))
        self.assertIn("bpy", brain.check_code("print(1)"))

    def test_fix_loop_learns_script_and_fix(self):
        from core import gemini
        calls = []

        def execute(code):
            calls.append(code)
            if 'inputs["Specular"]' in code:
                raise ValueError("Traceback...\nKeyError: 'bpy_prop_collection[key]: key \"Specular\" not found'")
        with patch.object(gemini, "text", side_effect=[BROKEN, GOOD]) as model:
            code, tries = brain.run_with_fixes("krom bir küre", {"objects": []}, "4.2", execute, log=lambda m: None)
        self.assertEqual((code, tries), (GOOD, 2))
        self.assertIn("Specular", model.call_args_list[1].args[0])          # the error went back to the model
        kinds = [i["kind"] for i in brain.load()]
        self.assertEqual(sorted(kinds), ["fix", "script"])
        self.assertIn("Specular", brain.recall("krom küre", kinds=("fix",))[0]["error"])
        # next time the fix is in the prompt
        with patch.object(gemini, "text", return_value=GOOD) as model:
            brain.run_with_fixes("krom küre yap", {"objects": []}, "4.2", lambda c: None, log=lambda m: None)
        self.assertIn("was fixed with", model.call_args.args[0])

    def test_gives_up_after_max_tries(self):
        from core import gemini
        with patch.object(gemini, "text", return_value="print('no bpy')"):
            with self.assertRaisesRegex(ValueError, "denemede"):
                brain.run_with_fixes("x", {}, "4.2", lambda c: None, log=lambda m: None)

    def test_plugin_teach_and_lessons(self):
        out = studio.run({"action": "teach", "request": "Ürün çekimlerinde 85 mm lens kullan"})
        self.assertIn("öğrendim", out)
        self.assertIn("ipucu", studio.run({"action": "lessons"}))
        self.assertEqual(brain.load()[-1]["kind"], "tip")


class Install(unittest.TestCase):
    def test_success_text_and_late_found_path_is_saved(self):
        import subprocess
        from types import SimpleNamespace
        done = SimpleNamespace(returncode=0, stdout="Found Blender\nSuccessfully installed", stderr="")
        exe = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
        with patch.object(studio, "_windows", return_value=True), patch.object(studio.shutil, "which", return_value="winget"), \
             patch.object(studio, "executable", side_effect=[ValueError("yok"), ValueError("yok"), ValueError("yok"), exe]), \
             patch.object(subprocess, "run", return_value=done), patch.object(studio.time, "sleep"), \
             patch("memory.config_manager.save_plugin_config") as save:
            out = studio.install()
        self.assertIn("kuruldu ve hazır", out)
        save.assert_called_once_with("blender_studio", {"executable": exe})

    def test_installed_but_not_found_says_so(self):
        import subprocess
        from types import SimpleNamespace
        done = SimpleNamespace(returncode=0, stdout="Successfully installed", stderr="")
        with patch.object(studio, "_windows", return_value=True), patch.object(studio.shutil, "which", return_value="winget"), \
             patch.object(studio, "executable", side_effect=ValueError("yok")), patch.object(studio, "deep_search", return_value=None), \
             patch.object(subprocess, "run", return_value=done), patch.object(studio.time, "sleep"):
            out = studio.install()
        self.assertIn("kuruldu ama", out)
        self.assertNotIn("bitmedi", out)


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class RealBlender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [patch.object(brain, "LESSONS", Path(self.tmp.name) / "lessons.json"),
                  patch.object(studio, "ROOT", Path(self.tmp.name) / "Blender")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_script_fixes_itself_in_blender(self):
        from core import gemini
        with patch.object(gemini, "text", side_effect=[BROKEN, GOOD]):
            out = studio.process("script", "krom bir küre ve kamera", None)
        self.assertIn("hazır", out)
        project = studio.project_path(None)
        report = studio.invoke(studio.executable(), project, Path(self.tmp.name), "inspect")
        names = {o["name"] for o in report["details"]}
        self.assertIn("Küre", names)
        self.assertEqual(sorted(i["kind"] for i in brain.load()), ["fix", "script"])
        self.assertIn("Specular", brain.load()[-1]["error"] + brain.load()[0]["error"])

    def test_unsupported_plan_falls_back_to_script(self):
        from core import gemini
        with patch.object(gemini, "as_json", return_value={"unsupported": "adım dili bunu yapamaz"}), \
             patch.object(gemini, "text", return_value=GOOD):
            studio.process("new", "krom küre, özel betik gerekir", None)
        report = studio.invoke(studio.executable(), studio.project_path(None), Path(self.tmp.name), "inspect")
        self.assertIn("Küre", {o["name"] for o in report["details"]})

    def test_wrong_subject_is_rebuilt(self):
        from core import gemini
        bird = 'import bpy\nclear()\nsphere("OiseauVolant", 0.1, (0, 0, 0.1))\n'
        with patch.object(gemini, "as_json", side_effect=[{"ok": False, "wrong": "Masa yerine kuş yapılmış"}, {"ok": True}]), \
             patch.object(gemini, "text", side_effect=[bird, GOOD]) as model, patch.object(brain, "look", return_value={}):
            studio.process("new", "ahşap bir masa", None)
        self.assertIn("kuş yapılmış", model.call_args.args[0])                    # told what went wrong
        report = studio.invoke(studio.executable(), studio.project_path(None), Path(self.tmp.name), "inspect")
        names = {o["name"] for o in report["details"]}
        self.assertIn("Küre", names)
        self.assertNotIn("OiseauVolant", names)
        self.assertTrue(any(i["kind"] == "fix" for i in brain.load()))

    def test_looks_at_its_work_and_fixes_floating_legs(self):
        from core import gemini
        bad = """import bpy
clear()
top_ = box("Tabla", (1.2, 0.7, 0.04), (0, 0, 0.9))
for i, (x, y) in enumerate([(-1.8, -0.8), (1.8, -0.8), (-1.8, 0.8), (1.8, 0.8)], 1):
    cylinder(f"Masa ayağı {i}", 0.025, 0.7, (x, y, 0.35))
assign(top_, wood("Ceviz"))
studio(samples=8)
"""
        good = """import bpy
top_ = bpy.data.objects["Tabla"]
top_.location.z = 0.73
for i, (x, y) in enumerate([(-0.54, -0.29), (0.54, -0.29), (-0.54, 0.29), (0.54, 0.29)], 1):
    leg = bpy.data.objects[f"Masa ayağı {i}"]
    leg.location = (x, y, 0.0)
    on_floor(leg)
    touch(top_, leg)
"""
        looks = [{"score": 3.0, "subject_ok": True, "problems": ["Ayaklar tablanın altında değil, uzakta duruyor"]},
                 {"score": 9.0, "subject_ok": True, "problems": []}]
        logs = []
        player = type("P", (), {"write_log": lambda self, m: logs.append(m)})()
        with patch.object(gemini, "text", side_effect=[bad, good]) as model, \
             patch.object(gemini, "as_json", return_value={"ok": True}), \
             patch.object(brain, "look", side_effect=looks) as eye:
            studio.process("new", "ahşap bir masa", None, player=player)
        self.assertEqual(eye.call_count, 2)
        self.assertTrue(eye.call_args_list[0].args[0].startswith(b"\x89PNG"))          # it really looked at a picture
        self.assertIn("hiçbir parçaya değmiyor", " ".join(eye.call_args_list[0].args[2]))   # and measured the gaps
        self.assertIn("Ayaklar tablanın altında değil", model.call_args.args[0])          # the critique went into the fix
        self.assertEqual(eye.call_args_list[1].args[2], [])                               # fixed: nothing floats any more
        self.assertTrue(any("9/10" in m for m in logs), logs)

    def test_study_keeps_only_verified_knowledge(self):
        from core import gemini
        notes = {"notes": "- bsdf.inputs['Roughness'] sets roughness", "demo": BROKEN}
        with patch.object(gemini, "as_json", return_value=notes), patch.object(gemini, "text", return_value=GOOD):
            out = studio.process("study", "Principled BSDF malzemeleri", None, topic="material")
        self.assertIn("doğruladım", out)
        self.assertEqual(brain.load()[-1]["kind"], "tip")
        with patch.object(gemini, "as_json", return_value=notes), patch.object(gemini, "text", return_value=BROKEN):
            with self.assertRaisesRegex(ValueError, "kaydetmedim"):
                studio.process("study", "yanlış konu", None, topic="material")

    def test_user_can_stop_a_running_job(self):
        import time
        from core import gemini, jobs
        from plugins import job_control
        slow = "import bpy, time\ntime.sleep(120)\n"
        with patch.object(gemini, "text", return_value=slow):
            studio.run({"action": "script", "request": "çok uzun süren bir sahne yap"})
            for _ in range(100):
                if jobs.current() and studio._procs:
                    break
                time.sleep(0.2)
            t0 = time.time()
            self.assertIn("Durdurdum", job_control.run({"action": "cancel", "which": "blender"}))
            for _ in range(100):
                if not studio._lock.locked():
                    break
                time.sleep(0.2)
        self.assertLess(time.time() - t0, 15)                        # stopped, not waited out
        self.assertIn("durdurdum", studio._status)
        self.assertEqual(jobs.current(), [])

    def test_hologram_studio_render(self):
        from core import holo_model as hm
        model = hm.clean({"name": "Kupa", "parts": [
            {"name": "gövde", "shape": "cylinder", "size": [8, 10, 8], "pos": [0, 5, 0], "color": "#d8d4cc", "rough": 0.25},
            {"name": "kulp", "shape": "torus", "size": [5, 5, 1.2], "pos": [5, 5, 0], "rot": [90, 0, 0], "color": "#d8d4cc"}]})
        glb = Path(self.tmp.name) / "kupa.glb"
        glb.write_bytes(hm.export_glb(hm.build_mesh(model), model))
        out = studio.hologram_render(studio.executable(), str(glb), w=480, h=270, samples=16, height_m=0.1)
        self.assertTrue(out.read_bytes().startswith(b"\x89PNG"))
        self.assertTrue((out.parent / "scene.blend").is_file())
        frame = json.loads((out.parent / "frame.json").read_text())
        (x0, x1), (y0, y1) = frame["ndc_x"], frame["ndc_y"]
        self.assertTrue(0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0, frame)     # all of it in the picture
        self.assertGreater(max(x1 - x0, y1 - y0), 0.7, frame)                      # and filling it
        self.assertLess(abs((x0 + x1) / 2 - 0.5), 0.06, frame)                     # centred
        self.assertLess(abs((y0 + y1) / 2 - 0.5), 0.06, frame)
        keep = os.environ.get("BLENDER_RENDER_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            shutil.copy(out, Path(keep) / "studio_mug.png")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.name == "nt", "Windows only")
class WindowsSearch(unittest.TestCase):
    def test_candidates_and_deep_search_run(self):
        paths = list(studio.windows_candidates())
        self.assertTrue(all(isinstance(p, Path) for p in paths))
        studio.deep_search()
