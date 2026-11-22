"""AETHER's own voice level, softer at night."""
import unittest
from datetime import datetime
from unittest import mock

import numpy as np

from core import voice_level


class VoiceLevelTest(unittest.TestCase):
    CFG = {"level": 100, "night": True, "night_level": 55, "night_from": 23, "night_to": 7}

    def test_night_window_wraps_midnight(self):
        self.assertTrue(voice_level.is_night(23, 23, 7))
        self.assertTrue(voice_level.is_night(3, 23, 7))
        self.assertFalse(voice_level.is_night(7, 23, 7))
        self.assertFalse(voice_level.is_night(15, 23, 7))
        self.assertTrue(voice_level.is_night(14, 13, 15))
        self.assertFalse(voice_level.is_night(5, 5, 5))

    def test_gain(self):
        self.assertEqual(voice_level.gain(datetime(2026, 1, 1, 15), self.CFG), 1.0)
        self.assertEqual(voice_level.gain(datetime(2026, 1, 1, 2), self.CFG), 0.55)
        self.assertEqual(voice_level.gain(datetime(2026, 1, 1, 2), {**self.CFG, "night": False}), 1.0)
        self.assertEqual(voice_level.gain(datetime(2026, 1, 1, 2), {**self.CFG, "level": 40}), 0.4)  # never louder at night

    def test_apply_clips(self):
        pcm = np.array([1000, -1000, 30000], dtype=np.int16).tobytes()
        out = np.frombuffer(voice_level.apply(pcm, 0.5), dtype=np.int16)
        self.assertEqual(list(out), [500, -500, 15000])
        loud = np.frombuffer(voice_level.apply(pcm, 1.5), dtype=np.int16)
        self.assertEqual(int(loud[2]), 32767)
        self.assertIs(voice_level.apply(pcm, 1.0), pcm)

    def test_plugin(self):
        from plugins import voice_volume
        saved = {}
        with mock.patch("memory.config_manager.save_plugin_config",
                        lambda ns, vals: saved.setdefault(ns, {}).update(vals)), \
             mock.patch("memory.config_manager.get_plugin_config", lambda ns: saved.get(ns, {})):
            voice_volume.run({"action": "softer"})
            self.assertEqual(voice_level.settings()["level"], 80)
            voice_volume.run({"action": "set", "level": 500})
            self.assertEqual(voice_level.settings()["level"], 150)
            out = voice_volume.run({"action": "night_off"})
            self.assertIn("the same at night", out)


if __name__ == "__main__":
    unittest.main()
