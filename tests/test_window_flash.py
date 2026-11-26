"""Regression tests for fleeting-window records without live desktop access."""
from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

from core import window_flash


class FlashRecorderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "trace.log"
        self.time_now = [10.0]
        self.events = []
        self.rec = window_flash.FlashRecorder(
            clock=lambda: self.time_now[0],
            notify=self.events.append,
            destination=self.log,
        )

    def test_short_window_is_recorded_with_process_only(self):
        self.rec.show(("win", 123), "Windows konsolu: cmd.exe [ConsoleWindowClass]")
        self.time_now[0] += .25
        report = self.rec.hide(("win", 123))
        self.assertIn("cmd.exe", report)
        self.assertIn("0.2 sn", report)
        self.assertEqual(len(self.events), 1)
        self.assertIn("cmd.exe", self.log.read_text(encoding="utf-8"))
        self.assertEqual(self.rec.hide(("win", 123)), None)

    def test_normal_long_lived_windows_are_not_noise(self):
        self.rec.show("dialog", "FRIDAY paneli: SetupOverlay")
        self.time_now[0] += 5
        self.assertIsNone(self.rec.hide("dialog"))
        self.assertEqual(self.events, [])
        self.assertFalse(self.log.exists())

    def test_same_popup_is_rate_limited(self):
        self.rec.show(1, "FRIDAY paneli: QDialog")
        self.time_now[0] += .2
        self.assertIsNotNone(self.rec.hide(1))
        self.rec.show(2, "FRIDAY paneli: QDialog")
        self.time_now[0] += .2
        self.assertIsNone(self.rec.hide(2))
        self.time_now[0] += 13
        self.rec.show(3, "FRIDAY paneli: QDialog")
        self.time_now[0] += .3
        self.assertIsNotNone(self.rec.hide(3))
        self.assertEqual(len(self.events), 2)

    def test_log_size_capped_and_recent_returns_last_events(self):
        self.log.write_text("old log\n" * 16000, encoding="utf-8")
        self.rec.show(1, "FRIDAY paneli: SettingsOverlay")
        self.time_now[0] += .2
        self.rec.hide(1)
        self.assertLess(self.log.stat().st_size, window_flash._MAX_BYTES)
        with mock.patch.object(window_flash, "trace_path", return_value=self.log):
            data = window_flash.recent(3)
        self.assertIn("SettingsOverlay", data[-1])
        self.assertLessEqual(len(data), 3)

    def test_plugin_reads_record_after_popup_disappears(self):
        from plugins import window_flash as plugin
        self.rec.show("x", "Windows konsolu: conhost.exe")
        self.time_now[0] += .18
        self.rec.hide("x")
        with mock.patch.object(window_flash, "trace_path", return_value=self.log):
            result = plugin.run({"limit": 1})
        self.assertIn("conhost.exe", result)
        self.assertIn("FRIDAY tarafından", result)

    def test_non_windows_platform_never_imports_gui_or_starts_hook(self):
        if sys.platform != "win32":
            self.assertIsNone(window_flash.start(None, None))
            

if __name__ == "__main__":
    unittest.main()
