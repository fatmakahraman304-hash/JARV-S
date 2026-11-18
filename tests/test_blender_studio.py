import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import blender_studio as studio


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class BlenderWorkflow(unittest.TestCase):
    def test_create_edit_recover_export_render(self):
        from core import gemini

        steps = [
            {"op": "create", "kind": "cube", "name": "Gövde"},
            {"op": "material", "name": "Gövde", "rgb": [0.9, 0.2, 0.1]},
            {"op": "modifier", "name": "Gövde", "type": "BEVEL", "settings": {"width": 0.1}},
            {"op": "create", "kind": "camera", "name": "Kamera", "location": [4, -5, 3]},
            {"op": "aim", "name": "Kamera", "target": [0, 0, 0]},
            {"op": "create", "kind": "light", "name": "Işık", "location": [0, 0, 4]},
            {"op": "keyframe", "name": "Gövde", "frame": 1, "rotation": [0, 0, 0]},
            {"op": "keyframe", "name": "Gövde", "frame": 30, "rotation": [0, 0, 90]},
            {"op": "geometry_nodes", "name": "Gövde",
             "nodes": [{"id": "in", "type": "NodeGroupInput"}, {"id": "out", "type": "NodeGroupOutput"}],
             "links": [["in", "Geometry", "out", "Geometry"]]},
            {"op": "shader_nodes", "name": "Gövde",
             "nodes": [{"id": "paint", "type": "ShaderNodeBsdfPrincipled",
                        "inputs": {"Base Color": [0.9, 0.2, 0.1, 1]}},
                       {"id": "out", "type": "ShaderNodeOutputMaterial"}],
             "links": [["paint", "BSDF", "out", "Surface"]]},
            {"op": "mesh_edit", "name": "Gövde", "tool": "smart_project"},
            {"op": "create", "name": "Rig", "kind": "armature",
             "bones": [{"name": "Kol", "head": [0, 0, 0], "tail": [0, 0, 1]}]},
            {"op": "skin", "name": "Gövde", "rig": "Rig", "groups": {"Kol": [0, 1]}},
            {"op": "pose", "name": "Rig", "bone": "Kol", "rotation": [0, 20, 0], "frame": 5},
            {"op": "render_settings", "resolution_x": 32, "resolution_y": 32},
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, "ROOT", Path(tmp)):
            with patch.object(gemini, "as_json", return_value={"steps": steps}):
                studio.process("new", "Kırmızı bir küpü döndür", None)
            with tempfile.TemporaryDirectory() as temp:
                info = studio.invoke(studio.executable(), None, Path(temp), "reference", query="uv unwrap")
                self.assertIn("uv.unwrap", [row[0] for row in info["operators"]])
            original = studio.project_path(None)
            original_bytes = original.read_bytes()
            self.assertIn("4 nesne", studio.process("inspect", "", None))
            invalid = {"steps": [{"op": "transform", "name": "Eksik"}]}
            fixed = {"steps": [{"op": "duplicate", "name": "Kopya", "source": "Gövde"}]}
            with patch.object(gemini, "as_json", side_effect=[invalid, fixed]):
                studio.process("edit", "Bir kopya ekle", str(original))
            self.assertNotEqual(original, studio.project_path(None))
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertIn("5 nesne", studio.process("inspect", "", None))
            studio.process("glb", "", None)
            self.assertEqual(next(Path(tmp).rglob("*.glb")).read_bytes()[:4], b"glTF")
            studio.process("render", "", None)
            self.assertTrue(next(Path(tmp).rglob("*.png")).read_bytes().startswith(b"\x89PNG"))
