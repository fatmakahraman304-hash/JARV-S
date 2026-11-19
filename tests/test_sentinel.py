"""Ambient awareness: the few changes worth a sentence, each said once."""
import unittest
from unittest import mock

from core import sentinel


class SentinelTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(sentinel, "RECENT_PATH", Path(self.tmp.name) / "recent.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_recent_keeps_paths_for_later(self):
        from pathlib import Path
        w = sentinel.DownloadWatch({}, Path("/home/u/Downloads"))
        w.feed({"a.zip": 2 << 20}); w.feed({"a.zip": 2 << 20})
        sentinel.diff_drives({}, {"E:\\": {"label": "KINGSTON", "total": 1}})
        self.assertEqual(sentinel.recent()[0]["kind"], "usb")
        self.assertEqual(sentinel.recent("download")[0]["path"], str(Path("/home/u/Downloads") / "a.zip"))
        from plugins import awareness
        out = awareness.run({"action": "recent", "kind": "downloads"})
        self.assertIn("a.zip", out)
        self.assertNotIn("KINGSTON", out)

    def test_drives(self):
        before = {"C:\\": {"label": "OS", "total": 1}}
        after = {**before, "E:\\": {"label": "KINGSTON", "total": 64 * 1024 ** 3}}
        notes = sentinel.diff_drives(before, after)
        self.assertEqual(len(notes), 1)
        self.assertIn("KINGSTON (64.0 GB", notes[0])
        self.assertIn("taken out", sentinel.diff_drives(after, before)[0])
        self.assertEqual(sentinel.diff_drives(after, after), [])

    def test_power(self):
        on = {"plugged": True, "percent": 80.0, "secsleft": -2}
        off = {"plugged": False, "percent": 79.6, "secsleft": 3 * 3600 + 600}
        self.assertIn("about 3 h 10 min left", sentinel.diff_power(on, off)[0])
        self.assertIn("plugged in", sentinel.diff_power(off, on)[0])
        self.assertEqual(sentinel.diff_power(on, on), [])
        self.assertEqual(sentinel.diff_power(None, on), [])          # a desktop has no battery

    def test_network_needs_confirmation_and_says_it_when_back(self):
        n = sentinel.NetWatch()
        self.assertEqual(n.feed(True, 0), [])
        self.assertEqual(n.feed(False, 10), [])                      # one miss is not an outage
        self.assertEqual(n.feed(True, 20), [])
        self.assertEqual(n.feed(False, 30), [])
        self.assertEqual(n.feed(False, 45), [])                      # confirmed down: nothing to say yet
        self.assertEqual(n.feed(True, 200), [])
        notes = n.feed(True, 215)
        self.assertEqual(len(notes), 1)
        self.assertIn("2 min", notes[0])

    def test_short_outage_not_worth_a_sentence(self):
        n = sentinel.NetWatch()
        n.feed(True, 0); n.feed(False, 1); n.feed(False, 2); n.feed(True, 3)
        self.assertEqual(n.feed(True, 4), [])

    def test_downloads(self):
        w = sentinel.DownloadWatch({"old.zip": 5 << 20})
        self.assertEqual(w.feed({"old.zip": 5 << 20, "movie.mp4.crdownload": 1 << 20}), [])
        self.assertEqual(w.feed({"old.zip": 5 << 20, "movie.mp4": 700 << 20}), [])    # first seen
        notes = w.feed({"old.zip": 5 << 20, "movie.mp4": 700 << 20})                 # size stable
        self.assertEqual(len(notes), 1)
        self.assertIn("movie.mp4 (700.0 MB)", notes[0])
        self.assertEqual(w.feed({"old.zip": 5 << 20, "movie.mp4": 700 << 20}), [])    # said once
        w.feed({"tiny.txt": 10}); self.assertEqual(w.feed({"tiny.txt": 10}), [])     # too small

    def test_tick_respects_switches(self):
        with mock.patch.object(sentinel, "removable_drives", side_effect=[{}, {"E:": {"label": "X", "total": 1}}]), \
             mock.patch.object(sentinel, "power", return_value=None), \
             mock.patch.object(sentinel, "online", return_value=True), \
             mock.patch.object(sentinel, "downloads_dir", return_value=None):
            s = sentinel.Sentinel()
            cfg = {k: True for k in sentinel.KINDS}
            cfg["usb"] = False
            self.assertEqual(s.tick(0, cfg), [])

    def test_instruction_and_plugin(self):
        self.assertTrue(sentinel.instruction(["x"]).startswith("[ENVIRONMENT]"))
        from plugins import awareness
        saved = {}
        with mock.patch("memory.config_manager.save_plugin_config",
                        lambda ns, vals: saved.setdefault(ns, {}).update(vals)), \
             mock.patch("memory.config_manager.get_plugin_config", lambda ns: saved.get(ns, {})):
            out = awareness.run({"action": "off", "kind": "usb"})
            self.assertIn("Off: USB drives", out)
            self.assertFalse(sentinel.settings()["usb"])
            self.assertIn("Unknown kind", awareness.run({"action": "off", "kind": "lamp"}))
            awareness.run({"action": "on", "kind": "all"})
            self.assertTrue(all(sentinel.settings().values()))


if __name__ == "__main__":
    unittest.main()


class StatusReportTest(unittest.TestCase):
    def test_own_state(self):
        from plugins import status_report
        with mock.patch("core.jobs.describe", return_value=["blender_studio (2 dk)"]), \
             mock.patch("core.quiet.is_on", return_value=True), \
             mock.patch("core.quiet.describe", return_value="Quiet mode is on for 30 more min."), \
             mock.patch("core.away.pending", return_value=[{}, {}]), \
             mock.patch("core.sentinel.recent", return_value=[]):
            out = status_report._own_state()
        self.assertIn("blender_studio", out)
        self.assertIn("Quiet mode", out)
        self.assertIn("2 gelişme", out)
