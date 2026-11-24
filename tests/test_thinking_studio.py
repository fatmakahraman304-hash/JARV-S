import unittest
from core import thinking_studio as studio
from plugins import thinking_studio as plugin


class ThinkingStudioTests(unittest.TestCase):
    def tearDown(self):
        studio.activate((0,))

    def test_complete_catalog(self):
        self.assertEqual(set(studio.FEATURES), set(range(1, 141)))
        self.assertTrue(all(title and guide for title, guide in studio.FEATURES.values()))
        self.assertEqual(set(studio.MODES) | set(studio.POLICY), set(range(1, 141)))
        self.assertTrue(set(studio.MODES).isdisjoint(studio.POLICY))

    def test_commands_and_reset(self):
        self.assertEqual(studio.parse("FRIDAY, karşı ben."), (13,))
        self.assertEqual(studio.parse("Jarvis, düşüncemi geri sar."), (12,))
        self.assertEqual(studio.parse("FRIDAY mod 11 ve 16"), (11, 16))
        self.assertEqual(studio.parse("FRIDAY kısa mod"), (-1,))
        self.assertEqual(studio.parse("FRIDAY fikrin DNA’sını çıkar"), (54,))
        studio.apply_command("FRIDAY mod 11 ve 16")
        self.assertEqual(studio.active(), (11, 16))
        self.assertIn("Hayat provası", studio.system_block())
        self.assertIn("Olasılık haritası", studio.mode_prompt())
        studio.apply_command("normal moda dön")
        self.assertEqual(studio.active(), ())

    def test_unsafe_or_ambiguous_inputs_do_not_activate(self):
        for command in ("karşı ben?", "karşı ben açma", "mod 999", "mod 1",
                        "mod 11 ve 16 ve 19 ve 20 ve 21",
                        '"karşı ben"', "karşı ben modu nedir"):
            self.assertIsNone(studio.parse(command), command)
        self.assertEqual(studio.active(), ())

    def test_read_only_plugin_cannot_change_state(self):
        self.assertIn("Karşı ben", plugin.run({"action": "guide", "number": 13}))
        plugin.run({"action": "select", "command": "karşı ben"})
        self.assertEqual(studio.active(), ())

    def test_every_mode_number_is_selectable(self):
        for n in studio.MODES:
            self.assertEqual(studio.parse(f"mod {n}"), (n,))
