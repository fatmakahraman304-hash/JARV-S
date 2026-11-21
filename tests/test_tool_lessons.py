"""Mayk learns from a failure that it fixed itself, and uses the cure the next time."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import tool_lessons as tl


class Lessons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(tl, "PATH", Path(self.tmp.name) / "l.json")
        self.p.start()
        tl._last_fail.clear()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_failure_then_fix_is_a_lesson(self):
        self.assertIsNone(tl.record("open_app", {"app_name": "spotfy"}, False, "status=failed app not found", now=100))
        lesson = tl.record("open_app", {"app_name": "Spotify"}, True, "status=done", now=130)
        self.assertEqual(lesson["good"], {"app_name": "Spotify"})
        self.assertIn('{"app_name": "Spotify"}', tl.hint("open_app", {"app_name": "spotfy"}))
        self.assertIn("[LESSONS FROM YOUR OWN MISTAKES", tl.prompt_block())

    def test_unrelated_or_late_success_is_not_a_lesson(self):
        tl.record("open_app", {"app_name": "x"}, False, "failed", now=100)
        self.assertIsNone(tl.record("open_app", {"app_name": "y"}, True, "done", now=100 + tl.WINDOW + 5))
        tl.record("open_app", {"app_name": "x"}, False, "failed", now=1000)
        self.assertIsNone(tl.record("open_app", {"app_name": "x"}, True, "done", now=1010))   # same args: a retry
        self.assertEqual(tl.load(), [])

    def test_main_uses_lessons(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("learned = tool_lessons.record(fc.name, args, ok_now, str(result))", src)
        self.assertIn("mem_str += tool_lessons.prompt_block()", src)


if __name__ == "__main__":
    unittest.main()
