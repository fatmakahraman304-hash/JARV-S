"""'Neler yapabilirsin?' — the installed tools, grouped, with example sentences."""
import unittest

from core import intent
from plugins import capabilities as cap


class Capabilities(unittest.TestCase):
    def test_every_installed_tool_is_counted_and_grouped(self):
        tools = cap.installed()
        self.assertGreater(len(tools), 50)
        text = cap.overview()
        self.assertIn(f"Şu an {len(tools)} yeteneğim var", text)
        for label in ("Bilgisayarı yönetme", "3B ve tasarım", "Mayk'ın kendisi"):
            self.assertIn(label, text)
        self.assertIn("«Blender'da ahşap bir masa yap»", text)

    def test_topic(self):
        text = cap.overview("Blender")
        self.assertIn("3B ve tasarım", text)
        self.assertNotIn("Oyun", text)

    def test_never_blocked_by_the_intent_guard(self):
        self.assertEqual(intent.guard("capabilities", {}, "neler yapabilirsin?"), "")


if __name__ == "__main__":
    unittest.main()
