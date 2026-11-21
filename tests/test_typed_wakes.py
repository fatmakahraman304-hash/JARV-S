"""A typed command wakes MAYK instead of being refused while it sleeps."""
import unittest
from pathlib import Path


class TypedWakes(unittest.TestCase):
    def test_source(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn('self.wake(reason="yazılı komut")', src)
        self.assertNotIn("I'm asleep — say 'Hey MAYK' or tap WAKE NOW first.", src)


if __name__ == "__main__":
    unittest.main()
