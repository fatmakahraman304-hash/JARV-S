"""The work journal: kept per day on disk, summarised for 'bu hafta neler yaptık'."""
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from core import journal


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(journal, "DIR", Path(self.tmp.name))
        self.p.start()
        journal._pruned["day"] = ""

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_record_and_summary(self):
        journal.record("blender_studio", "ok", "Render: masa")
        journal.record("web_search", "ok", "Web: hava")
        journal.record("web_search", "fail", "Yapılamadı: Web")
        journal.record("save_memory", "ok", "x")                      # self-lookups are not work
        out = journal.summary(date.today(), date.today())
        self.assertIn("2 tasks done", out)
        self.assertIn("1 failed", out)
        self.assertIn("Render: masa", out)
        self.assertNotIn("save memory", out)

    def test_week_spans_days_and_prunes(self):
        old = time.time() - (journal.KEEP_DAYS + 5) * 86400
        journal.record("web_search", "ok", "old", when=old)
        journal.record("web_search", "ok", "yesterday", when=time.time() - 86400)
        journal._pruned["day"] = ""
        journal.record("web_search", "ok", "today")                   # first record of the day prunes
        self.assertEqual(len(list(journal.DIR.glob("*.jsonl"))), 2)
        out = journal.summary(date.today() - timedelta(days=6), date.today())
        self.assertIn("over 2 day(s)", out)

    def test_activity_feeds_the_journal(self):
        from core import activity
        activity.record_tool("smart_home", {"action": "on"}, result="Done: Salon → turn on.")
        self.assertIn("smart home", journal.summary(date.today(), date.today()).lower().replace("akıllı ev komutu", "smart home"))

    def test_week_report_plugin(self):
        from plugins import day_report
        journal.record("blender_studio", "ok", "Render: ev")
        out = day_report.run({"period": "week"})
        self.assertIn("Render: ev", out)
