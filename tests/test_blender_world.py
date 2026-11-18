import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import blender_studio as studio


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class WorldWorkflow(unittest.TestCase):
    def test_district_build_edit_animation(self):
        from core import gemini

        plan = [
            {"op": "district", "name": "Liman", "rows": 3, "columns": 4,
             "parks": [[2, 2]], "seed": 9, "max_floors": 4},
            {"op": "landscape", "name": "Tepeler", "size": 150, "height": 5, "location": [0, 110, 0]},
            {"op": "wall", "name": "Duvar", "start": [-5, -34], "end": [5, -34],
             "openings": [{"offset": 1, "width": 1, "height": 2},
                          {"offset": 6, "width": 2, "height": 1.2, "sill": 1}]},
            {"op": "lathe", "name": "Vazo", "profile": [[0, 0], [1, 0], [.7, 2], [.5, 2], [0, .2]]},
            {"op": "cable", "name": "Kablo", "points": [[1, 2, 3], [2, 4, 2], [5, 2, 3]]},
            {"op": "physics", "name": "Vazo", "type": "ACTIVE"},
            {"op": "physics", "name": "Duvar", "type": "PASSIVE"},
            {"op": "create", "kind": "plane", "name": "Kumaş", "location": [0, 0, 10]},
            {"op": "mesh_edit", "name": "Kumaş", "tool": "subdivide", "settings": {"number_cuts": 5}},
            {"op": "physics", "name": "Kumaş", "type": "CLOTH"},
            {"op": "physics", "name": "Duvar", "type": "COLLISION"},
            {"op": "create", "kind": "camera", "name": "Kamera", "location": [66, -90, 70], "lens": 36},
            {"op": "aim", "name": "Kamera", "target": [0, 4, 0]},
            {"op": "create", "kind": "light", "name": "Güneş", "type": "SUN", "energy": 3,
             "rotation": [25, -20, 25]},
            {"op": "render_settings", "resolution_x": 128, "resolution_y": 96},
            {"op": "timeline", "start": 1, "end": 2},
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, "ROOT", Path(tmp)):
            with patch.object(gemini, "as_json", side_effect=[
                    {"phases": ["Mahalle", "Çevre ve kamera"]},
                    {"steps": plan[:1]}, {"steps": plan[1:]}]) as planner:
                studio.process("new", "On bir bina, park ve çevresi", None)
            self.assertIn("Liman Park 2-2", planner.call_args.args[0])
            original = studio.project_path(None)
            with patch.object(gemini, "as_json", side_effect=[
                    {"phases": ["Bir nesne ekle", "Son işlem"]},
                    {"steps": [{"op": "create", "kind": "cube", "name": "Geçici"}]},
                    {"unsupported": "Son aşama desteklenmiyor"}]):
                with self.assertRaisesRegex(ValueError, "Son aşama"):
                    studio.process("edit", "İki aşamalı düzenle", None)
            self.assertEqual(studio.project_path(None), original)
            report = studio.invoke(studio.executable(), original, Path(tmp), "inspect")
            details = {o["name"]: o for o in report["details"]}
            self.assertEqual(sum(n.startswith("Liman Bina ") for n in details), 11)
            self.assertEqual(details["Liman Park 2-2"]["location"], [-10, 0, 0])
            self.assertIn("CLOTH", details["Kumaş"]["modifiers"])
            self.assertIn("COLLISION", details["Duvar"]["modifiers"])
            self.assertAlmostEqual(details["Duvar"]["dimensions"][0], 10)
            self.assertIn("Kablo", details)
            with patch.object(gemini, "as_json", return_value={"steps": [
                    {"op": "transform", "name": "Liman Bina 1-2", "location": [-10, -20, 2]}]}):
                studio.process("edit", "Binayı yükselt", None)
            self.assertNotEqual(original, studio.project_path(None))
            studio.process("animation", "", None)
            frames = sorted(Path(tmp).glob("*/frames/*.png"))
            self.assertEqual([p.name for p in frames], ["frame_0001.png", "frame_0002.png"])
            for path in frames:
                self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))
