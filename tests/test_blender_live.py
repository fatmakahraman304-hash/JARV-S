"""The live link: a real Blender runs the add-on; MAYK reads the selection
and changes the open scene in place ("bunu kırmızı yap")."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import _blender_brain as brain
from plugins import _blender_live as live

ROOT = Path(__file__).resolve().parent.parent
HARNESS = """
import sys, time, bpy
from pathlib import Path
args = sys.argv[sys.argv.index("--") + 1:]
root, token, stop = args
env = {"__name__": "jarvis_live"}
code = Path(root, "plugins", "_blender_live_addon.py").read_text(encoding="utf8").replace("__JARVIS_DIR__", root)
exec(compile(code, "jarvis_live", "exec"), env)
env["_token"] = lambda: token
end = time.time() + 400
while time.time() < end and not Path(stop).exists():
    time.sleep(env["serve_once"]())
"""

RED = """import bpy
for o in bpy.context.selected_objects:
    assign(o, paint("Kırmızı", (0.8, 0.02, 0.02)))
"""


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class LiveLink(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.token = "test-token-123"
        cls.stop = Path(cls.tmp.name) / "stop"
        harness = Path(cls.tmp.name) / "harness.py"
        harness.write_text(HARNESS, encoding="utf8")
        cls.proc = subprocess.Popen([shutil.which("blender"), "-b", "--factory-startup", "--python", str(harness), "--",
                                     str(ROOT), cls.token, str(cls.stop)],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cls.p = [patch.object(live, "token", return_value=cls.token),
                 patch.object(brain, "LESSONS", Path(cls.tmp.name) / "lessons.json")]
        for p in cls.p:
            p.start()
        for _ in range(120):
            if live.available():
                break
            time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.stop.write_text("x")
        try:
            cls.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        for p in cls.p:
            p.stop()
        cls.tmp.cleanup()

    def test_1_state_and_selection(self):
        self.assertTrue(live.available())
        st = live.state()
        self.assertIn("Cube", [o["name"] for o in st["objects"]])
        live.run("import bpy\nfor o in bpy.context.view_layer.objects: o.select_set(o.name == 'Cube')\n")
        self.assertEqual(live.state()["selected"], ["Cube"])

    def test_2_this_means_the_selection(self):
        from core import gemini
        live.run("import bpy\nfor o in bpy.context.view_layer.objects: o.select_set(o.name == 'Cube')\n")
        with patch.object(gemini, "text", return_value=RED) as model, patch.object(brain, "look", return_value={}):
            out = live.edit("bunu kırmızı yap")
        self.assertIn("Yaptım", out)
        self.assertIn("['Cube']", model.call_args.args[0])                 # it knew what "bunu" was
        cube = next(o for o in live.state()["objects"] if o["name"] == "Cube")
        self.assertEqual(cube["materials"], ["Kırmızı"])
        others = [o for o in live.state()["objects"] if o["name"] != "Cube"]
        self.assertTrue(all("Kırmızı" not in o["materials"] for o in others))   # nothing else touched

    def test_3_errors_come_back_to_be_fixed(self):
        from core import gemini
        broken = RED.replace("paint(", "pant(")
        with patch.object(gemini, "text", side_effect=[broken, RED]) as model:
            live.edit("bunu kırmızı yap")
        self.assertIn("pant", model.call_args_list[1].args[0])               # the traceback went back

    def test_3b_it_means_what_jarvis_changed_last(self):
        from core import gemini
        live.run("import bpy\nfor o in bpy.context.view_layer.objects: o.select_set(o.name == 'Cube')\n", "seç")
        with patch.object(gemini, "text", return_value=RED), patch.object(brain, "look", return_value={}):
            live.edit("bunu kırmızı yap")
        live.run("import bpy\nfor o in bpy.context.view_layer.objects: o.select_set(False)\n", "seç")
        grow = "import bpy\nbpy.data.objects['Cube'].scale = (2, 2, 2)\n"
        with patch.object(gemini, "text", return_value=grow) as model, patch.object(brain, "look", return_value={}):
            live.edit("onu iki kat büyüt")
        self.assertIn("refer to when nothing is selected: ['Cube']", model.call_args.args[0])
        self.assertEqual(live.last_change()["changed"], ["Cube"])

    def test_3c_preview_and_render_from_a_copy(self):
        shown = []
        player = type("P", (), {"show_image": lambda self, path, title="": shown.append(path), "write_log": lambda self, m: None})()
        png, issues = live.preview(player)
        self.assertTrue(png.startswith(b"\x89PNG"))
        live.run("import bpy\nsc = bpy.context.scene\nsc.render.engine = 'CYCLES'\nsc.cycles.samples = 4\n"
                 "sc.render.resolution_x, sc.render.resolution_y = 320, 180\n", "ayar")
        from plugins import blender_studio as studio
        with patch.object(studio, "ROOT", Path(self.tmp.name) / "Blender"):
            out = live.render(player)
        self.assertTrue(out.read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(len(shown), 2)

    def test_3d_live_review_fixes_real_defects(self):
        from core import gemini
        live.run("import bpy\nfor o in bpy.context.view_layer.objects: o.select_set(o.name == 'Cube')\n", "seç")
        lift = "import bpy\nbpy.data.objects['Cube'].location.z = 0\n"
        looks = [{"score": 4.0, "problems": ["Küp zeminin içine gömülmüş"]}, {"score": 9.0, "problems": []}]
        with patch.object(gemini, "text", side_effect=[RED, lift]) as model, patch.object(brain, "look", side_effect=looks):
            out = live.edit("bunu kırmızı yap")
        self.assertIn("gömülmüş", model.call_args.args[0])
        self.assertIn("9/10", out)

    def test_4_wrong_token_is_refused(self):
        with patch.object(live, "token", return_value="wrong"):
            with self.assertRaises(ConnectionError):
                live.state()

    def test_5_undo_does_not_crash(self):
        try:
            live.undo()
        except ValueError:
            pass                                                            # no undo history in background mode


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class Install(unittest.TestCase):
    def test_addon_goes_to_blenders_startup_folder(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"HOME": home, "APPDATA": home}):
            target = live.install(shutil.which("blender"))
            self.assertEqual(target.name, "jarvis_live.py")
            self.assertEqual(target.parent.name, "startup")
            text = target.read_text(encoding="utf8")
            self.assertNotIn("__JARVIS_DIR__", text)
            self.assertIn(str(ROOT), text.replace("\\\\", "\\"))


if __name__ == "__main__":
    unittest.main()
