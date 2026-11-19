"""While you were away: announcements nobody could hear are kept and told once on return."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import away


class AwayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p1 = mock.patch.object(away, "DIGEST_PATH", d / "digest.json")
        self.p2 = mock.patch.object(away, "_LAST_PATH", d / "last.json")
        self.p1.start(); self.p2.start()

    def tearDown(self):
        self.p1.stop(); self.p2.stop(); self.tmp.cleanup()

    def test_presence_rules(self):
        self.assertTrue(away.is_away(False, 1, 1))              # asleep: nothing it says is heard
        self.assertFalse(away.is_away(True, 1000, 5))            # hand on the mouse: here
        self.assertFalse(away.is_away(True, 5, 2000))            # talking by voice: here
        self.assertTrue(away.is_away(True, 1000, 1000))
        self.assertFalse(away.is_away(True, 1000, None))         # unknown input: silence alone, longer
        self.assertTrue(away.is_away(True, 2000, None))
        self.assertTrue(away.is_back(True, 2, None))
        self.assertTrue(away.is_back(True, 900, 3))
        self.assertFalse(away.is_back(False, 0, 0))

    def test_ready_to_tell(self):
        self.assertFalse(away.ready_to_tell(True, True, False, 30, 1))   # mid-sentence
        self.assertFalse(away.ready_to_tell(True, False, True, 30, 1))   # a job running
        self.assertFalse(away.ready_to_tell(True, False, False, 2, 1))   # user still talking
        self.assertTrue(away.ready_to_tell(True, False, False, 10, None))
        self.assertTrue(away.ready_to_tell(True, False, False, 900, 5))
        self.assertFalse(away.ready_to_tell(True, False, False, 900, None))

    def test_told_exactly_once_and_kept_across_restarts(self):
        away.add("[TOOL_LATE_RESULT] render done", kind="result")
        away.add("battery 20%", kind="system", key="system")
        away.add("battery 15%", kind="system", key="system")     # same key: only the latest
        texts = [i["text"] for i in away.pending()]
        self.assertEqual(texts, ["[TOOL_LATE_RESULT] render done", "battery 15%"])
        items = away.take()
        self.assertEqual(len(items), 2)
        self.assertEqual(away.take(), [])
        self.assertEqual(len(away.last_told()["items"]), 2)

    def test_old_news_dropped(self):
        away.add("old")
        import json
        items = json.loads(away.DIGEST_PATH.read_text(encoding="utf-8"))
        items[0]["at"] = time.time() - away.KEEP_FOR - 10
        away.DIGEST_PATH.write_text(json.dumps(items), encoding="utf-8")
        self.assertEqual(away.pending(), [])

    def test_welcome_text(self):
        away.add("render done", kind="result")
        text = away.welcome_instruction(away.pending(), away_for=3700)
        self.assertTrue(text.startswith("[AWAY_DIGEST]"))
        self.assertIn("render done", text)
        self.assertIn("1 h 1 min", text)
        self.assertIn("J.A.R.V.I.S.", text)

    def test_plugin(self):
        from plugins import while_away
        self.assertIn("Nothing came up", while_away.run({}))
        away.add("render done", kind="result")
        self.assertIn("render done", while_away.run({}))
        self.assertIn("last welcome-back", while_away.run({}))

    def test_prompt_knows_the_tag(self):
        prompt = (Path(__file__).resolve().parent.parent / "core" / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("[AWAY_DIGEST]", prompt)
        self.assertIn("while_away", prompt)


if __name__ == "__main__":
    unittest.main()


class HoldTest(unittest.TestCase):
    def test_late_result_held_when_asleep(self):
        import types
        try:
            import main
        except BaseException as exc:      # heavy deps missing in this environment
            self.skipTest(str(exc))
        added = []
        fake = types.SimpleNamespace(_awake=False, _last_user_speech=time.monotonic(),
                                     ui=mock.Mock(), _AWAY_KINDS=main.JarvisLive._AWAY_KINDS)
        fake._user_away = lambda: main.JarvisLive._user_away(fake)
        with mock.patch.object(away, "add", lambda t, kind, key: added.append((kind, key))):
            self.assertTrue(main.JarvisLive._hold_for_later(fake, "[TOOL_LATE_RESULT] x"))
            fake._awake = True
            self.assertFalse(main.JarvisLive._hold_for_later(fake, "[TOOL_LATE_RESULT] y"))
        self.assertEqual(added, [("result", "")])


class WelcomeTest(unittest.TestCase):
    def test_should_welcome(self):
        with mock.patch.object(away, "welcome_enabled", lambda: True):
            self.assertTrue(away.should_welcome(3 * 3600, False))
            self.assertFalse(away.should_welcome(3 * 3600, True))     # woke with a command: that first
            self.assertFalse(away.should_welcome(1800, False))        # a short absence: no ceremony
        with mock.patch.object(away, "welcome_enabled", lambda: False):
            self.assertFalse(away.should_welcome(5 * 3600, False))

    def test_greeting_text(self):
        text = away.greeting_instruction(3 * 3600, 20)
        self.assertTrue(text.startswith("[WELCOME_BACK]"))
        self.assertIn("evening", text)
        self.assertIn("3 h", text)

    def test_plugin_toggle(self):
        from plugins import while_away
        saved = {}
        with mock.patch("memory.config_manager.save_plugin_config",
                        lambda ns, vals: saved.setdefault(ns, {}).update(vals)), \
             mock.patch("memory.config_manager.get_plugin_config", lambda ns: saved.get(ns, {})):
            while_away.run({"action": "welcome_off"})
            self.assertFalse(away.welcome_enabled())
            while_away.run({"action": "welcome_on"})
            self.assertTrue(away.welcome_enabled())
