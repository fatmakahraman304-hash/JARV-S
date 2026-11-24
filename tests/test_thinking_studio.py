import unittest
from core import thinking_studio as studio
from plugins import thinking_studio as plugin


class ThinkingStudioTests(unittest.TestCase):
    def tearDown(self):
        studio.activate((0,))

    def test_complete_catalog(self):
        self.assertEqual(set(studio.FEATURES), set(range(1, 1001)))
        self.assertTrue(all(title and guide for title, guide in studio.FEATURES.values()))
        self.assertEqual(set(studio.MODES) | set(studio.POLICY) | set(studio.APP_FEATURES), set(range(1, 1001)))
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
        for command in ("karşı ben?", "karşı ben açma", "mod 1001", "mod 1",
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

    def test_zero_is_normal_mode(self):
        studio.activate((145,))
        self.assertEqual(studio.parse("mod 0"), (0,))
        studio.apply_command("mod 0")
        self.assertEqual(studio.active(), ())

    def test_extended_search_and_real_status(self):
        self.assertEqual([r[0] for r in studio.search_features("500")], [500])
        self.assertEqual(studio.parse("mini sınav"), (145,))
        self.assertEqual(studio.parse("mod 141 ve 410"), (141, 410))
        self.assertIsNone(studio.parse("mod 471"))
        self.assertIn("Feynman", plugin.run({"action": "guide", "number": 141}))
        self.assertIn("Durum:", plugin.run({"action": "guide", "number": 500}))

    def test_original_workflow_is_not_lost(self):
        self.assertEqual(set(studio.DETAILS), set(range(1, 141)))
        studio.activate((11,))
        from core.voice_commands import normalize_command
        self.assertIn("iyimser", normalize_command(studio.mode_prompt()))

    def test_all_app_features_and_policies_are_not_modes(self):
        self.assertFalse(set(studio.APP_FEATURES) & set(studio.MODES))
        self.assertTrue(all(studio.feature_status(n) for n in studio.FEATURES))

    def test_new_features(self):
        for n in (501, 578, 676, 804, 907, 932, 976, 996):
            self.assertEqual(studio.parse(f"mod {n}"), (n,))
        self.assertEqual([r[0] for r in studio.search_features("1000")], [1000])
        self.assertIsNone(studio.parse("mod 1000"))
        self.assertIn("studio_utilities", studio.workflow_for(804))
        self.assertIn("file_processor", studio.workflow_for(926))
        self.assertIn("reminder", studio.workflow_for(515))
        self.assertIn("Nihai ilke", plugin.run({"action": "guide", "number": 1000}))

    def test_catalog_pagination_covers_policies_app_and_workflows(self):
        import re
        seen=[]
        for first in range(1,1001,100):
            result=plugin.run({"action":"list","first":first,"last":1000})
            seen.extend(int(n) for n in re.findall(r"(?m)^(\d+)\. ",result))
            if first<901:
                self.assertIn(f"first={first+100}",result)
        self.assertEqual(seen,list(range(1,1001)))
        self.assertIn("Sürekli ilke",plugin.run({"action":"list","first":1,"last":1}))
        self.assertIn("Uygulama",plugin.run({"action":"list","first":471,"last":471}))
        self.assertIn("Sohbet yeteneği",plugin.run({"action":"list","first":145,"last":145}))

    def test_catalog_validates_all_inputs(self):
        for invalid in (True,0,1001,145.5,"9"*5000,[],{}):
            self.assertIn("Geçersiz",plugin.run({"action":"guide","number":invalid}))
            self.assertIn("Geçersiz",plugin.run({"action":"list","first":invalid}))
        self.assertIn("Geçersiz",plugin.run({"action":"list","first":20,"last":10}))
        self.assertIn("Geçersiz",plugin.run({"action":"search","query":"x"*301}))
        self.assertIn("Geçersiz",plugin.run({"action":"resolve","query":[]}))
        self.assertIn("Mini sınav",plugin.run({"action":"guide","number":"145"}))

    def test_search_pagination_and_real_app_status(self):
        result=plugin.run({"action":"search","query":"","first":470,"last":500})
        self.assertIn("31 eşleşme, 20 gösteriliyor",result)
        self.assertIn("first=490, last=500",result)
        self.assertIn("otomatik kaynak yakalama yok",plugin.run({"action":"guide","number":481}))
        self.assertIn("Uygulanmış olmayan işlemi yapılmış sayma",plugin.run({"action":"guide","number":481}))
        self.assertEqual(studio.active(),())
