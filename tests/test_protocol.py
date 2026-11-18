import json
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.mem = {"preferences": {}}

        def remember(key, value, category="notes"):
            self.mem.setdefault(category, {})[key] = {"value": value}

        def forget(key, category="notes"):
            self.mem.get(category, {}).pop(key, None)
        self._p = [mock.patch("memory.memory_manager.load_memory", side_effect=lambda: self.mem),
                   mock.patch("memory.memory_manager.remember", side_effect=remember),
                   mock.patch("memory.memory_manager.forget", side_effect=forget)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_ready_made_by_alias(self):
        from plugins import protocol
        out = protocol.run({"action": "run", "name": "film moduna"})
        self.assertIn("FİLM PROTOKOLÜ".replace("İ", "I"), out.replace("İ", "I"))
        self.assertIn("1. Televizyonda", out)
        self.assertIn("SABAH", protocol.run({"action": "run", "name": "günaydın"}))

    def test_save_overrides_and_delete(self):
        from plugins import protocol
        self.assertIn("kaydedildi", protocol.run({"action": "save", "name": "eve geldim",
                                                  "steps": ["Hoş geldin de", "Müzik aç"]}))
        self.assertEqual(self.mem["preferences"]["protokol: eve geldim"]["value"], "Hoş geldin de | Müzik aç")
        self.assertIn("2. Müzik aç", protocol.run({"action": "run", "name": "eve geldim protokolü"}))
        self.assertIn("eve geldim", protocol.run({"action": "list"}))
        self.assertIn("silindi", protocol.run({"action": "delete", "name": "eve geldim"}))
        self.assertIn("yok", protocol.run({"action": "run", "name": "eve geldim"}))
        self.assertIn("uzun", protocol.run({"action": "save", "name": "x", "steps": ["a" * 400]}))

    def test_web_has_the_same_ready_made_protocols(self):
        from plugins import protocol
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        m = re.search(r"const PROTOCOLS = (\{.*?\});\n", js)
        self.assertEqual(json.loads(m.group(1)), protocol.DEFAULTS)
        self.assertIn("'protokol: '", js)


if __name__ == "__main__":
    unittest.main()
