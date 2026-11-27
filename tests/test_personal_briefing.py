"""Personal briefing reports available reminders without inventing missing data."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from plugins import day_report
from core.routines import desktop
from core import sync_hub


class PersonalBriefingTest(unittest.TestCase):
    def test_local_and_shared_reminders_are_sorted_and_shared_copy_deduplicated(self):
        shared = {"reminders": [{"id": "one", "due": 120000, "text": "Doktor"}]}
        engine = SimpleNamespace(list=lambda: [
            {"source": "shared:one", "enabled": True, "next_ts": 120, "text": "Hatırlatma: Doktor"},
            {"source": "reminder", "enabled": True, "next_ts": 110, "text": "Ara"},
            {"source": "reminder", "enabled": False, "next_ts": 105, "text": "İptal"},
        ])
        with patch.object(sync_hub, "settings", return_value={"github_token": "x", "gist_id": "y"}), \
             patch.object(sync_hub, "_state", shared), patch.object(desktop, "engine", return_value=engine):
            reminders, issues = day_report.upcoming_reminders(now=100)
        self.assertEqual(len(reminders), 2)
        self.assertIn("Ara", reminders[0])
        self.assertIn("Doktor", reminders[1])
        self.assertTrue(any("güncellik doğrulanmadı" in x for x in issues))

    def test_unavailable_sources_are_reported(self):
        with patch.object(sync_hub, "settings", return_value={}), patch.object(desktop, "engine", return_value=None):
            reminders, issues = day_report.upcoming_reminders(now=100)
        self.assertEqual(reminders, [])
        self.assertTrue(any("bağlı değil" in x for x in issues))
        self.assertTrue(any("doğrulanamadı" in x for x in issues))

    def test_failed_todo_list_is_not_counted_as_a_task_or_empty(self):
        spoken, detail = day_report.build("Ekran süresi bilinmiyor.", (0, 0), "", "Görev listesi okunamadı.", [])
        self.assertNotIn("1 iş var", spoken)
        self.assertIn("okunamadı", detail)
        self.assertNotIn("Liste boş", detail)

    def test_active_focus_session_counts_elapsed_time(self):
        with patch.object(day_report.time, "time", return_value=1800):
            count, minutes = day_report.focus_today([{"start": 1200, "end": 0}], datetime.fromtimestamp(1200).date())
        self.assertEqual((count, minutes), (1, 10))


if __name__ == "__main__":
    unittest.main()
