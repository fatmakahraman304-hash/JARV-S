import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from memory import continuity
from core import second_brain as brain


class SecondBrainTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(continuity, "data_dir", return_value=root))

    def test_failures_are_collected_once_and_dismissal_is_preserved(self):
        pid = continuity.project_start("improve", "FRIDAY", "/code", "test")
        continuity.project_update(pid, status="başarısız", note="test failed")
        brain.scan()
        brain.scan()
        self.assertEqual(len(brain.items()), 1)
        item = brain.items()[0]
        brain.update(item["id"], state="dismissed")
        brain.scan()
        self.assertEqual(brain.items()[0]["state"], "dismissed")

    def test_legacy_develop_entry_cannot_start_code_work(self):
        brain.add("Eski kayıt")
        item = brain.items()[0]
        with patch('plugins.github_develop.run') as develop:
            with self.assertRaisesRegex(ValueError, "kod yazmaz"):
                brain.develop(item['id'], Mock())
        develop.assert_not_called()
        self.assertEqual(brain._get(item['id'])['state'], 'idea')

    def test_failed_analysis_does_not_replace_existing_plan(self):
        brain.add("Konuşma")
        item = brain.items()[0]
        brain.update(item["id"], analysis="Eski plan")
        with patch("core.gemini.as_json", return_value=None):
            with self.assertRaises(ValueError):
                brain.analyze(item["id"])
        self.assertEqual(brain._get(item["id"])["analysis"], "Eski plan")

    def test_legacy_analysis_cannot_call_a_model_or_replace_history(self):
        brain.add("Ses sistemi")
        item = brain.items()[0]
        brain.update(item['id'], analysis='Önceki plan')
        with patch('core.gemini.as_json') as model:
            with self.assertRaisesRegex(ValueError, "yalnızca özellik"):
                brain.analyze(item['id'])
        model.assert_not_called()
        self.assertEqual(brain._get(item['id'])['analysis'], 'Önceki plan')

    def test_completion_is_found_beyond_recent_project_history(self):
        brain.add("Eski geliştirme")
        item = brain.items()[0]
        brain.update(item["id"], state="running")
        pid = continuity.project_start("improve", "FRIDAY", "/code", f"[SECOND_BRAIN:{item['id']}]")
        continuity.project_update(pid, status="bitti", note="Proje testleri geçti.")
        with continuity.connect() as db:
            db.executemany("INSERT INTO projects(title,status,instruction) VALUES(?,?,?)",
                           [("Yeni iş", "bitti", "başka istek")] * 205)
        brain.scan()
        saved = brain._get(item["id"])
        self.assertEqual(saved["state"], "verified")
        self.assertIn("testleri geçti", saved["result"])

    def test_pending_work_is_checked_even_when_the_display_is_full(self):
        brain.add("Hazırlanan geliştirme")
        item = brain.items()[0]
        brain.update(item["id"], state="requested")
        for i in range(105):
            brain.add(f"Yeni fikir {i}")
        with continuity.connect() as db:
            db.execute("UPDATE improvements SET updated=? WHERE id=?", ("2020-01-01T00:00:00+00:00", item["id"]))
        self.assertNotIn(item["id"], [row["id"] for row in brain.items()])
        brain.scan()
        self.assertEqual(brain._get(item["id"])["state"], "unverified")

    def test_lost_job_record_cannot_stay_running_forever(self):
        brain.add("Kaydı kaybolmuş geliştirme")
        item = brain.items()[0]
        brain.update(item["id"], state="running")
        with continuity.connect() as db:
            db.execute("UPDATE improvements SET updated=? WHERE id=?", ("2020-01-01T00:00:00+00:00", item["id"]))
        brain.scan()
        self.assertEqual(brain._get(item["id"])["state"], "unverified")
        self.assertIn("kaydı bulunamadı", brain._get(item["id"])["result"])
