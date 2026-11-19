"""Keeping watch: one remark after a long stretch or in the small hours, grounded in real activity."""
import unittest
from datetime import datetime
from unittest import mock

from core import vigil

CFG = {"enabled": True, "stretch_hours": 3.0, "late_night": True}
DAY = datetime(2026, 11, 19, 15, 0)


def run_for(v, start, minutes, wall=DAY, idle=10.0, cfg=CFG):
    """Tick once a minute for `minutes` while the user is working; return the notes that came due."""
    notes = []
    for m in range(minutes + 1):
        now = start + m * 60
        note = v.due(now, wall, idle, 9999, cfg)
        if note:
            v.mark(note, now, wall)
            notes.append((m, note))
    return notes


class VigilTest(unittest.TestCase):
    def test_long_stretch_said_once(self):
        v = vigil.Vigil()
        notes = run_for(v, 0, 6 * 60)
        self.assertEqual(len(notes), 1)
        m, note = notes[0]
        self.assertEqual((m, note["kind"]), (180, "stretch"))

    def test_a_real_break_starts_a_new_stretch(self):
        v = vigil.Vigil()
        run_for(v, 0, 150)
        for m in range(1, 25):                       # 24 minutes away: input idle grows
            self.assertIsNone(v.due(150 * 60 + m * 60, DAY, m * 60.0 + 400, 9999, CFG))
        notes = run_for(v, 175 * 60, 170)
        self.assertEqual(notes, [])                  # 170 min since the break: not yet 3 h
        self.assertEqual(len(run_for(v, 345 * 60 + 60, 20)), 1)

    def test_small_hours_once_a_night(self):
        v = vigil.Vigil()
        late = datetime(2026, 11, 20, 2, 10)
        notes = run_for(v, 0, 120, wall=late)
        self.assertEqual([n["kind"] for _, n in notes], ["late"])
        self.assertEqual(notes[0][0], 30)
        self.assertIn("02:10", vigil.instruction(notes[0][1]))

    def test_off_and_idle(self):
        v = vigil.Vigil()
        self.assertEqual(run_for(v, 0, 300, cfg={**CFG, "enabled": False}), [])
        self.assertIsNone(vigil.Vigil().due(0, DAY, 3600, 9999, CFG))   # nobody working

    def test_speech_counts_as_working(self):
        v = vigil.Vigil()
        notes = [v.due(m * 60, DAY, None, 10, CFG) for m in range(200)]
        self.assertTrue(any(notes))

    def test_instruction_text(self):
        text = vigil.instruction({"kind": "stretch", "minutes": 195, "clock": "15:00"})
        self.assertTrue(text.startswith("[CARE_NOTE]"))
        self.assertIn("3 h 15 min", text)
        self.assertIn("care_notes", text)

    def test_plugin_saves_choice(self):
        from plugins import care_notes
        saved = {}
        with mock.patch("memory.config_manager.save_plugin_config",
                        lambda ns, vals: saved.setdefault(ns, {}).update(vals)), \
             mock.patch("memory.config_manager.get_plugin_config", lambda ns: saved.get(ns, {})):
            self.assertIn("off", care_notes.run({"action": "off"}))
            self.assertFalse(vigil.settings()["enabled"])
            out = care_notes.run({"action": "set", "hours": 4, "late_night": False})
            self.assertIn("4 h", out)
            self.assertEqual(vigil.settings()["stretch_hours"], 4.0)
            self.assertFalse(vigil.settings()["late_night"])

    def test_prompt_knows_the_tag(self):
        from pathlib import Path
        p = (Path(__file__).resolve().parent.parent / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("[CARE_NOTE]", p)


if __name__ == "__main__":
    unittest.main()
