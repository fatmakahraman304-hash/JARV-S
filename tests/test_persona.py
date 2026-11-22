"""AETHER speaks like the films: 'efendim', the 'siz' forms, dry wit, calm reports — overridable by the user."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Persona(unittest.TestCase):
    def test_prompt_carries_the_film_manner(self):
        p = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("[ADDRESS AND MANNER — AETHER]", p)
        for must in ('"efendim"', '"siz"', "Never in every sentence", "STANDING INSTRUCTIONS FROM THE USER",
                     "Never during a failure", "No exclamation marks, no emoji"):
            self.assertIn(must, p)
        self.assertLess(p.index("[ADDRESS AND MANNER"), p.index("[ACKNOWLEDGE BEFORE A SILENCE]"))

    def test_greeting_follows_it(self):
        m = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("in your usual style: calm, polite, faintly dry", m)
        self.assertNotIn('f" Address the user as {name}."', m)

    def test_prompt_renders(self):
        p = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
        import re
        tokens = set(re.findall(r"\{([a-z_]+)\}", p))
        self.assertTrue(tokens <= {"assistant_name", "platform", "capabilities", "limits", "braces"}, tokens)


if __name__ == "__main__":
    unittest.main()
