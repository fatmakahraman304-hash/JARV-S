"""The architecture engine: plans are checked before building; with a real
Blender, buildings come out exact (nothing floating, real openings), and the
self-review revises the plan rather than guessing coordinates."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins import _blender_brain as brain
from plugins import blender_studio as studio

APARTMENT = {
    "name": "Apartman", "width": 16, "depth": 11, "floors": 4, "floor_height": 3.0,
    "rooms": [
        {"name": "Merdiven holü", "rect": [-1.5, -5.25, 1.5, 5.25]},
        {"name": "Daire A salon", "rect": [-7.75, -5.25, -1.5, 0.5]},
        {"name": "Daire A yatak", "rect": [-7.75, 0.5, -4.5, 5.25]},
        {"name": "Daire A mutfak", "rect": [-4.5, 0.5, -1.5, 5.25]},
        {"name": "Daire B salon", "rect": [1.5, -5.25, 7.75, 0.5]},
        {"name": "Daire B yatak", "rect": [4.5, 0.5, 7.75, 5.25]},
        {"name": "Daire B mutfak", "rect": [1.5, 0.5, 4.5, 5.25]}],
    "windows": {"width": 1.4, "height": 1.5, "sill": 0.9, "spacing": 3.2},
    "entrance": {"side": "front", "x": 0.0, "width": 1.6, "height": 2.5},
    "balconies": {"side": "front", "width": 3.4, "depth": 1.4, "from_floor": 1, "positions": [-4.6, 4.6], "rail": "glass"},
    "stairs": {"rect": [-1.2, 1.0, 1.2, 5.0]},
    "roof": {"type": "gable", "pitch": 30, "overhang": 0.5},
    "style": {"facade": "plaster", "facade_color": [0.85, 0.8, 0.7]},
}
HOUSE = {
    "name": "Müstakil ev", "width": 10, "depth": 8, "floors": 2, "floor_height": 2.9,
    "rooms": [{"name": "Salon", "rect": [-4.75, -3.75, 1.0, 1.0]}, {"name": "Mutfak", "rect": [1.0, -3.75, 4.75, 1.0]},
              {"name": "Hol", "rect": [-4.75, 1.0, 4.75, 3.75]}],
    "entrance": {"side": "front", "x": 2.5, "width": 1.1, "height": 2.3},
    "stairs": {"rect": [2.6, 1.05, 4.7, 3.7]},
    "roof": {"type": "hip", "pitch": 28, "overhang": 0.6},
    "style": {"facade": "brick", "roof_color": [0.2, 0.2, 0.22]},
}


class PlanChecks(unittest.TestCase):
    def test_good_plans_pass(self):
        self.assertEqual(brain.check_plan(APARTMENT), [])
        self.assertEqual(brain.check_plan(HOUSE), [])

    def test_mistakes_are_found(self):
        bad = json.loads(json.dumps(APARTMENT))
        bad["rooms"][1]["rect"] = [-9, -5.25, -1.5, 0.5]          # out of the walls
        bad["rooms"].append({"name": "Fazla", "rect": [2, -4, 6, 0]})  # on top of B salon
        bad["stairs"] = {}
        bad["balconies"]["positions"] = [7.5]
        problems = " ".join(brain.check_plan(bad))
        for word in ("taşıyor", "üst üste", "merdiven yok", "Balkon konumu"):
            self.assertIn(word, problems)

    def test_subjects(self):
        self.assertTrue(brain.is_building("4 katlı bir apartman yap"))
        self.assertTrue(brain.is_building("bahçeli müstakil ev"))
        self.assertFalse(brain.is_building("ahşap bir masa"))
        self.assertFalse(brain.is_building("On bir bina, park ve çevresi"))
        self.assertFalse(brain.is_building("3 katlı evler olan bir sokak"))
        self.assertTrue(brain.is_building("3 katlı bir ev"))
        self.assertTrue(brain.is_building("10 katlı apartman"))
        self.assertTrue(brain.is_big("bir köprü"))

    def test_bad_plan_is_sent_back_until_right(self):
        from core import gemini
        bad = dict(APARTMENT, stairs={})
        with patch.object(gemini, "as_json", side_effect=[bad, APARTMENT]) as model:
            plan = brain.make_plan("4 katlı apartman")
        self.assertEqual(plan, APARTMENT)
        self.assertIn("merdiven yok", model.call_args.args[0])


POOL = """import bpy
pool = box("Havuz", (4.0, 2.5, 0.3), (0, -7.5, 0.15), bevel=0.02)
assign(pool, stone("Havuz kenarı", (0.85, 0.85, 0.82)))
water = box("Havuz suyu", (3.6, 2.1, 0.02), (0, -7.5, 0.29), bevel=0)
assign(water, glass("Su", (0.6, 0.85, 0.95), 0.02))
"""


class UserDirected(unittest.TestCase):
    def test_edit_keeps_rules_and_changes_only_what_was_said(self):
        from core import gemini
        start = dict(HOUSE, user_rules=["Balkon olmasın"])
        edited = json.loads(json.dumps(HOUSE))
        edited["rooms"] = [r for r in edited["rooms"] if r["name"] != "Salon"]
        with patch.object(gemini, "as_json", return_value=edited) as model:
            out = brain.edit_plan(start, "Salonu sil")
        self.assertNotIn("Salon", [r["name"] for r in out["rooms"]])
        self.assertEqual(out["user_rules"], ["Balkon olmasın"])                   # the user's decision survives
        prompt = model.call_args.args[0]
        self.assertIn("Salonu sil", prompt)
        self.assertIn("keep EVERYTHING else identical", prompt)

    def test_prompts_forbid_unrequested_features(self):
        self.assertIn("Never add balconies", brain.PLAN_DOC)
        self.assertIn("never suggest features", brain.LOOK)


@unittest.skipUnless(shutil.which("blender"), "Blender binary required")
class Buildings(unittest.TestCase):
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

    def build(self, plan, name):
        folder = Path(self.tmp.name) / name
        folder.mkdir()
        studio.building_project(studio.executable(), folder, "bina", plan)
        views = Path(self.tmp.name) / f"{name}-v"
        views.mkdir()
        report = studio.invoke(studio.executable(), folder / "scene.blend", views, "views")
        keep = os.environ.get("BLENDER_RENDER_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            shutil.copy(report["views"][0][1], Path(keep) / f"{name}.png")
        return report

    def test_apartment_is_exact(self):
        report = self.build(APARTMENT, "apartman")
        self.assertEqual(report["issues"], [])                                       # nothing floats, nothing loose
        names = [o[0] for o in report["objects"]]
        self.assertGreaterEqual(sum(n.endswith("cam") for n in names), 40)          # real windows with glass
        self.assertEqual(sum(n.startswith("Merdiven ") for n in names), 3)          # stairs between 4 floors
        self.assertTrue(any(n.startswith("Balkon") for n in names))
        self.assertIn("Giriş kapısı", names)

    def test_house_with_hip_roof(self):
        report = self.build(HOUSE, "ev")
        self.assertEqual(report["issues"], [])
        self.assertTrue(any("çatısı" in o[0] for o in report["objects"]))

    def test_user_deletes_a_room_and_adds_a_pool(self):
        from core import gemini
        with patch.object(brain, "make_plan", return_value=HOUSE), patch.object(brain, "look", return_value={"score": 9.0, "problems": []}), \
             patch.object(gemini, "as_json", return_value={"ok": True}):
            studio.process("new", "iki katlı tuğla ev", None)
        before = self.names()
        edited = json.loads(json.dumps(HOUSE))
        edited["rooms"] = [r for r in edited["rooms"] if r["name"] != "Salon"]
        edited["extras"] = [{"name": "Havuz", "code": POOL.replace("glass(", "glas(")}]  # broken
        edited["user_rules"] = ["Balkon olmasın"]
        with patch.object(brain, "edit_plan", return_value=edited), patch.object(gemini, "text", return_value=POOL), \
             patch.object(brain, "look", return_value={"score": 9.0, "problems": []}):
            studio.process("edit", "Salonu sil, evin önüne havuz yap", None)
        after = self.names()
        self.assertIn("Havuz", after)                                   # the broken pool script was repaired and built
        self.assertIn("Havuz suyu", after)
        self.assertLess(sum(n.startswith("İç duvar") for n in after), sum(n.startswith("İç duvar") for n in before))
        self.assertEqual(sum(n.startswith("Pencere") and n.endswith("cam") for n in after),
                         sum(n.startswith("Pencere") and n.endswith("cam") for n in before))   # facade untouched
        plan = json.loads((studio.project_path(None).parent / "plan.json").read_text(encoding="utf8"))
        self.assertEqual(plan["user_rules"], ["Balkon olmasın"])

    def names(self):
        folder = Path(tempfile.mkdtemp(dir=self.tmp.name))
        rep = studio.invoke(studio.executable(), studio.project_path(None), folder, "inspect")
        return rep["names"]

    def test_new_building_pipeline_revises_the_plan(self):
        from core import gemini
        taller = dict(HOUSE, floors=3)
        looks = [{"score": 5.0, "subject_ok": True, "problems": ["Ev çok basık, bir kat daha olmalı"]},
                 {"score": 9.0, "subject_ok": True, "problems": []}]
        with patch.object(brain, "make_plan", side_effect=[HOUSE, taller]) as planner, \
             patch.object(brain, "look", side_effect=looks), patch.object(gemini, "as_json", return_value={"ok": True}):
            studio.process("new", "iki katlı tuğla müstakil ev", None)
        self.assertEqual(planner.call_args_list[1].args[1], HOUSE)                 # revised from the old plan …
        self.assertIn("bir kat daha", " ".join(planner.call_args_list[1].args[2]))  # … with the critique
        plan = json.loads((studio.project_path(None).parent / "plan.json").read_text(encoding="utf8"))
        self.assertEqual(plan["floors"], 3)


if __name__ == "__main__":
    unittest.main()
