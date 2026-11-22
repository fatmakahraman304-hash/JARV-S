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
        self.assertIn("AETHER", text)

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
        from tests._main_import import load_main
        main = load_main()
        added = []
        fake = types.SimpleNamespace(_awake=False, _last_user_speech=time.monotonic(),
                                     ui=mock.Mock(), _AWAY_KINDS=main.AetherLive._AWAY_KINDS,
                                     _AWAY_DROP=main.AetherLive._AWAY_DROP)
        fake._user_away = lambda: main.AetherLive._user_away(fake)
        fake._push_if_gone = lambda text, kind: None
        with mock.patch.object(away, "add", lambda t, kind, key: added.append((kind, key))):
            self.assertTrue(main.AetherLive._hold_for_later(fake, "[TOOL_LATE_RESULT] x"))
            fake._awake = True
            self.assertFalse(main.AetherLive._hold_for_later(fake, "[TOOL_LATE_RESULT] y"))
        self.assertEqual(added, [("result", "")])

    def test_care_note_dropped_not_kept(self):
        import types
        from tests._main_import import load_main
        main = load_main()
        added = []
        fake = types.SimpleNamespace(_awake=False, _last_user_speech=time.monotonic(), ui=mock.Mock(),
                                     _AWAY_KINDS=main.AetherLive._AWAY_KINDS, _AWAY_DROP=main.AetherLive._AWAY_DROP)
        fake._user_away = lambda: True
        fake._push_if_gone = lambda text, kind: None
        with mock.patch.object(away, "add", lambda t, kind, key: added.append(kind)):
            self.assertTrue(main.AetherLive._hold_for_later(fake, "[CARE_NOTE] 3 h"))
        self.assertEqual(added, [])


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


class PushTest(unittest.TestCase):
    def setUp(self):
        away._last_push["at"] = float("-inf")

    def test_phone_note(self):
        t, b = away.phone_note("[TOOL_LATE_RESULT] The 'blender_studio' tool you started earlier has just "
                               "finished. Tell the user... Result: Render saved to Desktop.", "result")
        self.assertEqual(t, "AETHER — blender studio tamamlandı")
        self.assertEqual(b, "Render saved to Desktop.")
        self.assertEqual(away.phone_note("[SYSTEM_ALERT] CPU 95%", "system")[1], "CPU 95%")
        self.assertIsNone(away.phone_note("x", "update"))

    def test_should_push(self):
        with mock.patch.object(away, "push_enabled", lambda: True):
            self.assertTrue(away.should_push("result", 3600, now=100))
            self.assertFalse(away.should_push("result", 30, now=100))     # at the desk, AETHER just asleep
            self.assertFalse(away.should_push("result", None, now=100))
            self.assertFalse(away.should_push("reminder", 3600, now=100)) # reminders push on their own
            away._last_push["at"] = 100
            self.assertFalse(away.should_push("system", 3600, now=200))   # not twice in ten minutes
            self.assertTrue(away.should_push("system", 3600, now=100 + away.PUSH_GAP))
        with mock.patch.object(away, "push_enabled", lambda: False):
            self.assertFalse(away.should_push("result", 3600, now=10 ** 6))

    def test_push_to_phones_skips_this_computer(self):
        from core import sync_hub
        sent = []
        with mock.patch.dict(sync_hub._state, {"push_subs": {"pc": {}, "phone": {}}}), \
             mock.patch.object(sync_hub, "device_id", lambda: "pc"), \
             mock.patch.object(sync_hub, "push_to", lambda d, t, b, tag: sent.append(d) or True):
            self.assertEqual(away.push_to_phones("t", "b"), 1)
        self.assertEqual(sent, ["phone"])


class MorningTest(unittest.TestCase):
    def test_morning_due(self):
        night = 8 * 3600
        self.assertTrue(away.morning_due("2026-11-20", 7, night, False, True, last="2026-11-19"))
        self.assertFalse(away.morning_due("2026-11-20", 7, night, False, True, last="2026-11-20"))  # once a day
        self.assertFalse(away.morning_due("2026-11-20", 15, night, False, True, last=""))          # afternoon
        self.assertFalse(away.morning_due("2026-11-20", 7, 1800, False, True, last=""))            # short break
        self.assertFalse(away.morning_due("2026-11-20", 7, night, True, True, last=""))            # woke with a command
        self.assertFalse(away.morning_due("2026-11-20", 7, night, False, False, last=""))          # briefing off

    def test_marker_round_trip(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(away, "BRIEFED_PATH", Path(d) / "b.json"):
            self.assertEqual(away.last_briefed(), "")
            away.mark_briefed("2026-11-20")
            self.assertEqual(away.last_briefed(), "2026-11-20")

    def test_overnight_extra(self):
        self.assertEqual(away.overnight_extra([]), "")
        text = away.overnight_extra([{"at": time.time(), "kind": "result", "text": "render done"}])
        self.assertIn("render done", text)
