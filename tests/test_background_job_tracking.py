"""AETHER arka plan kodlama görevleri: canlı durum, geçmiş, başlatma doğrulaması."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from actions import dev_agent
from plugins import job_control, work_status


class BackgroundJobTrackingTests(unittest.TestCase):
    def tearDown(self):
        with dev_agent._state_lock:
            dev_agent._JOB = {}
        dev_agent._player_ref = None

    def _new(self, pid=42):
        dev_agent._new_job(
            Path("hesap_makinesi"), "NVIDIA", "Python hesap makinesi yap",
            None, kind="build", journal_id=pid,
        )

    def test_work_status_reads_active_coding_agent_not_missing_method(self):
        self._new()
        dev_agent._update("planning", worker_started=True)
        result = work_status.run({"about": "kodlama"})
        self.assertIn("Kodlama ajanı:", result)
        self.assertIn("hesap_makinesi", result)
        self.assertIn("çalışıyor", result)
        self.assertNotIn("Kayıtlı bir kodlama görevi yok", result)

    def test_project_journal_updates_when_phase_changes(self):
        self._new(pid=321)
        with mock.patch.object(dev_agent, "_journal") as journal:
            dev_agent._update("writing", worker_started=True)
            dev_agent._log(None, "main.py hazırlanıyor")
        calls = [c for c in journal.call_args_list if c.args and c.args[0] == 321]
        self.assertTrue(calls)
        self.assertTrue(any(c.kwargs.get("status") == "çalışıyor" for c in calls))
        self.assertTrue(any("main.py" in c.kwargs.get("note", "") for c in calls))
        self.assertEqual(dev_agent._job_snapshot()["phase"], "writing")

    def test_history_is_not_mistaken_for_an_active_worker(self):
        from memory import continuity
        historical = [{
            "id": 123, "title": "hesap_makinesi", "folder": "/tmp/hesap_makinesi",
            "status": "çalışıyor", "note": "planlandı", "stage": 1,
            "updated": "2026-11-21T14:00:00+00:00",
        }]
        with mock.patch.object(continuity, "projects", return_value=historical):
            status = dev_agent.status_text()
        self.assertIn("iş parçacığı doğrulanamadı", status)
        self.assertIn("kayıt geçmişidir", status)
        self.assertNotIn("ŞU AN SÜRÜYOR", status)

    def test_missing_history_does_not_invent_running_work(self):
        from memory import continuity
        with mock.patch.object(continuity, "projects", return_value=[]):
            status = dev_agent.status_text()
        self.assertIn("başlatılmış işlem doğrulanamadı", status)

    def test_failed_thread_start_never_returns_started(self):
        self._new(pid=42)
        self.assertTrue(dev_agent._job_lock.acquire(blocking=False))
        try:
            with mock.patch.object(dev_agent.threading, "Thread") as thread, \
                 mock.patch.object(dev_agent, "_journal"):
                thread.return_value.start.side_effect = RuntimeError("thread unavailable")
                result = dev_agent._run_job(
                    lambda: "yapıldı", "hesap_makinesi", "NVIDIA", pid=42,
                )
            self.assertIn("başlatılamadı", result)
            self.assertNotIn("[STARTED]", result)
            self.assertFalse(dev_agent._job_lock.locked())
            self.assertEqual(dev_agent._job_snapshot()["status"], "failed")
        finally:
            if dev_agent._job_lock.locked():
                dev_agent._job_lock.release()

    def test_panel_shows_actual_brain_not_just_initial_choice(self):
        self._new()
        dev_agent._agent_progress(None, "  AETHER ajanı: NVIDIA (coding-model)")
        attempted = dev_agent._job_snapshot()
        self.assertEqual(attempted["model_attempt"], "NVIDIA (coding-model)")
        self.assertIsNone(attempted.get("model_used"))
        dev_agent._agent_progress(None,
                                  "  Kodlama modeli yanıt verdi: NVIDIA (coding-model)")
        answered = dev_agent._job_snapshot()
        self.assertEqual(answered["model_used"], "NVIDIA (coding-model)")
        dev_agent._agent_progress(None,
                                  "  Yedek kodlama modeline geçildi: Gemini (flash)")
        switched = dev_agent._job_snapshot()
        self.assertEqual(switched["model_attempt"], "Gemini (flash)")
        self.assertIsNone(switched.get("model_used"))
        dev_agent._agent_progress(None,
                                  "  Kodlama modeli yanıt verdi: Gemini (flash)")
        self.assertEqual(dev_agent._job_snapshot()["model_used"],
                         "Gemini (flash)")

    def test_cancel_command_reaches_running_code_agent(self):
        from core import aether_agent
        self._new()
        self.assertTrue(dev_agent._job_lock.acquire(blocking=False))
        try:
            with mock.patch.object(job_control, "_tasks", return_value=(None, [])), \
                 mock.patch("core.jobs.cancel", return_value=[]):
                message = job_control.run({"action": "cancel", "which": "kod ajanı"})
            self.assertIn("iptal isteği gönderildi", message)
            self.assertTrue(aether_agent.cancel_requested())
            snapshot = dev_agent._job_snapshot()
            self.assertEqual(snapshot["status"], "cancelling")
            self.assertIsNone(snapshot["finished"])
        finally:
            dev_agent._job_lock.release()
            aether_agent.reset_cancel()

    def test_cancel_does_not_claim_worker_has_stopped(self):
        from core import aether_agent
        self._new()
        self.assertTrue(dev_agent._job_lock.acquire(blocking=False))
        try:
            self.assertTrue(dev_agent.request_code_agent_cancel())
            self.assertTrue(dev_agent._job_lock.locked())
            self.assertIsNone(dev_agent._job_snapshot()["finished"])
        finally:
            dev_agent._job_lock.release()
            aether_agent.reset_cancel()

    def test_job_control_list_includes_running_code_agent(self):
        self._new()
        dev_agent._update("planning", worker_started=True)
        self.assertTrue(dev_agent._job_lock.acquire(blocking=False))
        try:
            with mock.patch.object(job_control, "_tasks", return_value=(None, [])):
                output = job_control.run({"action": "list"})
            self.assertIn("ŞU AN SÜRÜYOR: Kodlama", output)
            self.assertIn("hesap_makinesi", output)
        finally:
            dev_agent._job_lock.release()


if __name__ == "__main__":
    unittest.main()
