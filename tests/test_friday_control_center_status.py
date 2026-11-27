"""Control Centre: honest outcomes and consistent local status."""
import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import activity
from PyQt6.QtWidgets import QApplication
from gui.control_center import ControlCenter


class ActivitySnapshotTests(unittest.TestCase):
    def test_snapshot_is_consistent_and_detached(self):
        start = activity.last_seq()
        activity.record("web", "snapshot example", "warn")
        snap = activity.snapshot(start)
        self.assertEqual(snap.seq, snap.events[-1].seq)
        self.assertEqual(snap.events[-1].status, "warn")
        self.assertGreater(snap.counts["web"], 0)
        self.assertEqual(snap.hits["web"], snap.events[-1].ts)
        self.assertIsNone(activity.snapshot(snap.seq))
        activity.record("web", "next example", "ok")
        self.assertEqual(snap.events[-1].text, "snapshot example")
        self.assertEqual(activity.snapshot(snap.seq).counts["web"], snap.counts["web"] + 1)

    def test_started_outcome_is_not_marked_done(self):
        with patch("core.journal.record"):
            activity.record_tool("dev_agent", {}, "status=started action=build")
        ev = activity.recent(1)[0]
        self.assertEqual(ev.status, "info")
        self.assertIn("Başlatıldı", ev.text)


class ControlCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = ControlCenter()
        self.addCleanup(self.widget.close)
        self.addCleanup(self.widget._tmr.stop)

    def test_summary_counts_outcomes_and_neural_node_status(self):
        events = (
            activity.Event(1, 1., "web", "done", "ok"),
            activity.Event(2, 2., "web", "failed", "fail"),
            activity.Event(3, 3., "voice", "pending", "info"),
            activity.Event(4, 4., "computer", "unverified", "warn"))
        snap = activity.ActivitySnapshot(4, events, {"web": 2}, {"web": 2.}, frozenset())
        with patch.object(activity, "connected", return_value=set()), patch.object(
                activity, "snapshot", return_value=snap):
            self.widget._refresh(force=True)
        self.assertIn("1 tamamlandı", self.widget._summary.text())
        self.assertIn("1 başarısız", self.widget._summary.text())
        self.assertIn("1 doğrulanamadı", self.widget._summary.text())
        self.assertEqual(self.widget.network._outcomes["web"], "fail")
        self.assertEqual(self.widget.feed._events, list(events))

    def test_unchanged_snapshot_does_not_rebuild_feed(self):
        self.widget._next_age_refresh = float("inf")
        with patch.object(activity, "connected", return_value=set()), patch.object(
                activity, "snapshot", return_value=None), patch.object(
                self.widget.feed, "set_events") as set_events, patch.object(
                self.widget.feed, "update") as update:
            self.widget._refresh()
            set_events.assert_not_called()
            update.assert_not_called()

    def test_missing_hardware_is_not_shown_as_zero(self):
        self.widget.set_system_metrics({"cpu": 12, "mem": 45, "gpu": -1, "tmp": float("nan")})
        self.assertIn("CPU 12%", self.widget._system_status.text())
        self.assertIn("RAM 45%", self.widget._system_status.text())
        self.assertIn("GPU —", self.widget._system_status.text())
        self.assertIn("SICAKLIK —", self.widget._system_status.text())

    def test_hidden_panel_skips_animation_and_polling(self):
        self.widget.hide()
        with patch.object(self.widget, "_check_connections") as check, patch.object(
                self.widget.network, "advance") as advance:
            self.widget._tick()
            check.assert_not_called()
            advance.assert_not_called()
