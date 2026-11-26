"""FRIDAY's Blender knowledge: this Blender's whole API, the official manual,
and the search that feeds both into every Blender prompt."""
import gzip
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import _blender_knowledge as know

PAGE = b"""<html><head><title>Bevel Modifier \xe2\x80\x94 Blender Manual</title></head><body>
<nav>Navigation stuff</nav><div class="body"><h1>Bevel Modifier</h1>
<p>The Bevel modifier bevels the edges of the mesh it is applied to, with some control of how and where the bevel is
applied to the mesh. Amount: the size of the bevel. Segments: the number of edge loops added along the bevel's face.</p>
<p>Limit Method: None, Angle, Weight, Vertex Group. Harden Normals: match normals of new faces to adjacent faces.</p>
""" + b"<p>filler text about bevels and edges.</p>" * 10 + b"</div></body></html>"


class Offline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = Path(self.tmp.name)
        self.p = [patch.object(know, "STORE", store), patch.object(know, "API", store / "api.json.gz"),
                  patch.object(know, "MANUAL", store / "manual.json.gz")]
        for p in self.p:
            p.start()
        know._cache.clear()
        api = {"version": "5.0.0", "operators": [
            {"id": "bpy.ops.mesh.bevel", "name": "Bevel", "d": "Cut into selected items at an angle to create bevel",
             "p": [{"n": "offset", "t": "FLOAT"}, {"n": "segments", "t": "INT"}, {"n": "affect", "t": "ENUM", "e": ["VERTICES", "EDGES"]}]},
            {"id": "bpy.ops.object.light_add", "name": "Add Light", "d": "Add a light object", "p": []}],
            "types": [{"id": "BevelModifier", "base": "Modifier", "d": "Bevel modifier to make edges and vertices more rounded",
                       "p": [{"n": "width", "t": "FLOAT"}, {"n": "segments", "t": "INT"}], "f": []}],
            "nodes": [{"id": "ShaderNodeBsdfPrincipled", "label": "Principled BSDF", "tree": "ShaderNodeTree",
                       "in": ["Base Color:RGBA", "Metallic:VALUE"], "out": ["BSDF:SHADER"], "p": []}]}
        with gzip.open(know.API, "wt", encoding="utf8") as f:
            json.dump(api, f)
        with gzip.open(know.MANUAL, "wt", encoding="utf8") as f:
            json.dump({"source": "x", "chunks": know._chunks("modeling/modifiers/generate/bevel.html", PAGE)}, f)

    def tearDown(self):
        for p in self.p:
            p.stop()
        know._cache.clear()
        self.tmp.cleanup()

    def test_manual_page_becomes_clean_sections(self):
        chunks = know._chunks("x.html", PAGE)
        self.assertEqual(chunks[0]["title"], "Bevel Modifier")
        self.assertIn("Segments", chunks[0]["text"])
        self.assertNotIn("Navigation stuff", chunks[0]["text"])

    def test_turkish_request_finds_the_right_api_and_manual(self):
        from core import gemini
        with patch.object(know, "keywords", return_value=["bevel", "modifier", "edges", "segments"]):
            block = know.prompt("kenarları pahla, 3 segment olsun")
        self.assertIn("bpy.ops.mesh.bevel(offset:FLOAT, segments:INT, affect:ENUM[VERTICES|EDGES])", block)
        self.assertIn("bpy.types.BevelModifier", block)
        self.assertIn("[Bevel Modifier]", block)
        self.assertNotIn("light_add", block)

    def test_knowledge_reaches_the_script_prompt(self):
        from core import gemini
        from plugins import _blender_brain as brain
        with patch.object(know, "keywords", return_value=["bevel"]), \
             patch.object(gemini, "text", return_value="import bpy\n") as model:
            brain.write_script("kenarları pahla", {}, "5.0")
        self.assertIn("Exact API of the user's Blender 5.0.0", model.call_args.args[0])

    def test_rst_source_becomes_sections(self):
        rst = (b"*************\nBevel Modifier\n*************\n\n.. figure:: /images/bevel.png\n   :width: 300px\n\n"
               b"The Bevel modifier bevels the edges of the mesh. See :ref:`Limit Method <bpy.types.BevelModifier>`.\n\n"
               b"Segments\n   The number of edge loops added along the bevel's face. " + b"More words about bevels. " * 20)
        chunks = know._rst_chunks("blender-manual/manual/modeling/modifiers/generate/bevel.rst", rst)
        self.assertEqual(chunks[0]["title"], "Bevel Modifier")
        self.assertEqual(chunks[0]["page"], "modeling/modifiers/generate/bevel.html")
        self.assertIn("See Limit Method.", chunks[0]["text"])
        self.assertNotIn("figure", chunks[0]["text"])

    def test_status(self):
        self.assertIn("2 komut", know.status())
        self.assertIn("kılavuzdan 1 bölüm", know.status())


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class RealBlender(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store = Path(self.tmp.name)
        self.p = [patch.object(know, "STORE", store), patch.object(know, "API", store / "api.json.gz"),
                  patch.object(know, "MANUAL", store / "manual.json.gz")]
        for p in self.p:
            p.start()
        know._cache.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        know._cache.clear()
        self.tmp.cleanup()

    def test_whole_api_of_this_blender(self):
        from plugins import blender_studio as studio
        got = know.build_api(studio.executable(), studio.invoke)
        print("API:", got)
        self.assertGreater(got["operators"], 1500)
        self.assertGreater(got["types"], 1500)
        self.assertGreater(got["nodes"], 150)
        api = know._load("api")
        ops = {o["id"] for o in api["operators"]}
        self.assertIn("bpy.ops.mesh.primitive_cube_add", ops)
        principled = next(n for n in api["nodes"] if n["id"] == "ShaderNodeBsdfPrincipled")
        self.assertIn("Base Color:RGBA", principled["in"])
        bevel = next(t for t in api["types"] if t["id"] == "BevelModifier")
        self.assertIn("segments", [p["n"] for p in bevel["p"]])
        from core import gemini
        with patch.object(know, "keywords", return_value=["bevel", "modifier", "segments"]):
            self.assertIn("BevelModifier", know.prompt("kenarları pahla"))

    @unittest.skipUnless(os.environ.get("BLENDER_MANUAL_TEST"), "downloads the 250 MB manual")
    def test_official_manual(self):
        got = know.build_manual(os.environ.get("BLENDER_MANUAL_VERSION", ""))
        print("Manual:", got)
        self.assertGreater(got["sections"], 1000)
        from core import gemini
        with patch.object(know, "keywords", return_value=["bevel", "modifier"]):
            found = know.search("pah modifier", 0, 3)["manual"]
        self.assertTrue(any("Bevel" in c["title"] for c in found), [c["title"] for c in found])


if __name__ == "__main__":
    unittest.main()
