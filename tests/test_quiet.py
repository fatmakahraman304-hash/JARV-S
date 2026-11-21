"""Quiet mode: Mayk volunteers nothing, reminders still come, held items told once it ends."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import away, quiet


class QuietTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [mock.patch.object(quiet, "STATE_PATH", d / "quiet.json"),
                        mock.patch.object(away, "DIGEST_PATH", d / "digest.json"),
                        mock.patch.object(away, "_LAST_PATH", d / "last.json")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_timed_quiet_ends_by_itself(self):
        quiet.start(60, "meeting", now=1000)
        self.assertTrue(quiet.is_on(now=1000 + 59 * 60))
        self.assertFalse(quiet.is_on(now=1000 + 61 * 60))
        self.assertIn("meeting", quiet.describe(now=1000 + 30 * 60))

    def test_open_quiet_has_a_ceiling(self):
        quiet.start(None, now=0)
        self.assertTrue(quiet.is_on(now=quiet.MAX_HOURS * 3600 - 1))
        self.assertFalse(quiet.is_on(now=quiet.MAX_HOURS * 3600 + 1))
        self.assertIn("until the user ends it", quiet.describe(now=10))

    def test_reminders_pass(self):
        quiet.start(30)
        self.assertTrue(quiet.holds("result"))
        self.assertTrue(quiet.holds("note"))
        self.assertFalse(quiet.holds("reminder"))
        quiet.stop()
        self.assertFalse(quiet.holds("result"))

    def test_plugin(self):
        from plugins import quiet_mode
        self.assertIn("Quiet mode is on for", quiet_mode.run({"action": "on", "minutes": 45}))
        away.add("render done", kind="result")
        self.assertIn("1 held item", quiet_mode.run({"action": "off"}))
        self.assertIn("was not on", quiet_mode.run({"action": "off"}))
        self.assertIn("until the user ends it", quiet_mode.run({"action": "on"}))

    def test_ended_instruction(self):
        away.add("render done", kind="result")
        text = quiet.ended_instruction(away.pending(), away.describe)
        self.assertTrue(text.startswith("[QUIET_ENDED]"))
        self.assertIn("render done", text)

    def test_prompt(self):
        p = (Path(__file__).resolve().parent.parent / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("quiet_mode(action=on", p)
        self.assertIn("[QUIET_ENDED]", p)


if __name__ == "__main__":
    unittest.main()


class GuardTest(unittest.TestCase):
    def test_a_failing_watcher_does_not_cancel_the_group(self):
        import asyncio
        from tests._main_import import load_main
        main = load_main()
        done = []

        async def bad():
            raise RuntimeError("boom")

        async def good():
            await asyncio.sleep(0.05)
            done.append(True)

        async def go():
            async with asyncio.TaskGroup() as tg:
                tg.create_task(main.MaykLive._guarded(object(), bad))
                tg.create_task(good())
        asyncio.run(go())
        self.assertEqual(done, [True])


class MeetingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(quiet, "STATE_PATH", Path(self.tmp.name) / "q.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_meeting_stops_listening(self):
        from plugins import quiet_mode
        player = mock.Mock()
        out = quiet_mode.run({"action": "on", "minutes": 60, "reason": "toplantı", "listen": False}, player=player)
        player.request_sleep.assert_called_once()
        self.assertIn("not listening", out)
        self.assertTrue(quiet.last_listen_off())

    def test_film_keeps_listening(self):
        from plugins import quiet_mode
        player = mock.Mock()
        quiet_mode.run({"action": "on", "minutes": 120, "reason": "film"}, player=player)
        player.request_sleep.assert_not_called()
        self.assertFalse(quiet.last_listen_off())


class ChipTest(unittest.TestCase):
    def test_chip_note(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(quiet, "STATE_PATH", Path(d) / "q.json"):
            self.assertEqual(quiet.chip_note(), "")
            quiet.start(30)
            self.assertEqual(quiet.chip_note(), "SESSİZ MOD")
            quiet.start(30, listen=False)
            self.assertEqual(quiet.chip_note(), "TOPLANTI")

    def test_state_chip_shows_note(self):
        try:
            import os
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            self.skipTest(str(exc))
        app = QApplication.instance() or QApplication([])
        from gui.widgets import StateChip
        chip = StateChip()
        chip.set_note("sessiz mod")
        self.assertEqual(chip._note, "SESSİZ MOD")
        chip.grab()                              # paints without error
