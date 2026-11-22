"""Habits: the same command on several days at the same time is noticed and offered once."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from core import habits


class Habits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [patch.object(habits, "LOG", d / "h.jsonl"), patch.object(habits, "OFFERED", d / "o.json")]
        for p in self.p:
            p.start()
        self.now = datetime(2026, 11, 19, 22, 0)

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def at(self, days_ago, hh, mm, tool="open_app", args=None):
        t = (self.now - timedelta(days=days_ago)).replace(hour=hh, minute=mm).timestamp()
        habits.record(tool, args if args is not None else {"app_name": "Spotify"}, when=t)

    def test_same_command_same_time_is_a_habit(self):
        for d, (h, m) in zip(range(1, 6), [(21, 0), (21, 10), (20, 50), (21, 20), (21, 5)]):
            self.at(d, h, m)
        self.at(2, 9, 0, "weather_report", {"city": "Lefkoşa"})            # once: not a habit
        got = habits.suggestions(self.now.timestamp())
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["sig"], "open_app: spotify")
        self.assertEqual(got[0]["time"], "21:05")
        self.assertEqual(got[0]["days"], 5)
        self.assertIn("routines(action=add", habits.offer_text(got[0]))
        habits.mark_offered(got[0]["sig"])
        self.assertEqual(habits.suggestions(self.now.timestamp()), [])        # offered once

    def test_scattered_times_are_not_a_habit(self):
        for d, h in zip(range(1, 7), [8, 12, 15, 19, 22, 10]):
            self.at(d, h, 0)
        self.assertEqual(habits.suggestions(self.now.timestamp()), [])

    def test_around_midnight_still_groups(self):
        for d, (h, m) in zip(range(1, 5), [(23, 50), (0, 5), (23, 40), (0, 10)]):
            self.at(d, h, m)
        got = habits.suggestions(self.now.timestamp())
        self.assertEqual(len(got), 1)
        self.assertIn(got[0]["time"], ("23:55", "00:00", "23:50"))

    def test_aether_own_tools_are_not_habits(self):
        for d in range(1, 6):
            self.at(d, 21, 0, "self_check", {})
        self.assertEqual(habits.suggestions(self.now.timestamp()), [])


if __name__ == "__main__":
    unittest.main()
