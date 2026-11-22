"""Autonomous audit, cooldown, pause, and restart use a real local SQLite journal."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import second_brain as brain
from core import second_brain_service as service
from memory import continuity


class AutonomousBrain(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(continuity, "data_dir", return_value=self.root / "data"))
        self.controller = service.Controller(Mock())
        from actions import dev_agent
        from plugins import github_develop
        self.github = github_develop
        self.enterContext(patch.object(dev_agent, "_job_lock", threading.Lock()))
        self.enterContext(patch.object(github_develop, "_LOCK", threading.Lock()))

    def test_automatic_cycle_launches_without_user_idea_and_tracks_result(self):
        found = {"title": "Hafıza hatası", "detail": "Tekrarlanabilir hata", "source": "audit:memory:abc"}
        def start(parameters, player):
            self.request = parameters
            return "MAYK kod değişikliği için ayrı geliştirme alanı hazırlanıyor."
        with patch.object(service, "discover", return_value=found), patch.object(brain, "analyze"), \
             patch.object(self.github, "run", side_effect=start):
            self.controller.cycle(now=100)
        self.assertEqual(self.request["mode"], "self_edit")
        self.assertIn("[SECOND_BRAIN:", self.request["instruction"])
        self.assertEqual(brain.items()[0]["state"], "requested")
        pid = continuity.project_start("improve", "MAYK", "/checkout", self.request["instruction"])
        continuity.project_update(pid, status="bitti", note="Unittest geçti.")
        self.controller.reconcile()
        self.assertEqual(brain.items()[0]["state"], "verified")
        self.assertIn("Unittest geçti.", self.controller.snapshot()["events"][0]["detail"])

    def test_pause_and_cooldown_persist_across_controller_instances(self):
        service.set_enabled(False)
        with patch.object(service, "discover") as audit:
            self.controller.cycle(now=100)
            audit.assert_not_called()
        service.set_enabled(True)
        with patch.object(service, "discover", return_value=None) as audit:
            self.controller.cycle(now=100)
            service.Controller(Mock()).cycle(now=101)
            self.assertEqual(audit.call_count, 1)
        self.assertGreater(service.settings()["due"], 101)

    def test_pause_during_analysis_prevents_code_launch(self):
        found = {"title": "Ses", "detail": "Hata", "source": "audit:voice:abc"}
        with patch.object(service, "discover", return_value=found), \
             patch.object(brain, "analyze", side_effect=lambda _: service.set_enabled(False)), \
             patch.object(brain, "develop") as develop:
            self.controller.cycle(now=100)
        develop.assert_not_called()

    def test_source_audit_rejects_invented_evidence_and_deduplicates(self):
        path = "core/wake_word.py"
        source = self.root / path
        source.parent.mkdir()
        source.write_text("value = 1")
        result = {"title": "Test", "detail": "Repro", "evidence": [path]}
        with patch.object(service, "ROOT", self.root), patch("core.gemini.as_json", return_value=result) as model:
            found = service.discover(0)
            self.assertIn("value = 1", model.call_args.args[0])
            brain.add(found["title"], found["detail"], found["source"])
            self.assertIsNone(service.discover(0))
            self.assertEqual(model.call_count, 1)
            source.write_text("value = 2")
            model.return_value = dict(result, evidence=["config/api_keys.json"])
            with self.assertRaises(ValueError):
                service.discover(0)

    def test_worker_starts_cycle_without_opening_panel(self):
        reached = threading.Event()
        def cycle():
            reached.set()
            self.controller.stop()
        with patch.object(self.controller, "cycle", side_effect=cycle), \
             patch.object(self.controller, "reconcile"):
            self.controller.start(delay=0)
            self.assertTrue(reached.wait(2))
            self.controller.thread.join(2)
        self.assertFalse(self.controller.thread.is_alive())


    def test_first_setup_does_not_spend_model_quota(self):
        controller = service.Controller(Mock(), ready=lambda: False)
        with patch.object(service, "discover") as discover:
            controller.cycle(now=100)
            discover.assert_not_called()
        self.assertEqual(service.settings()["due"], 0)

    def test_claim_is_atomic_between_concurrent_auditors(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(service._claim, [100] * 4))
        self.assertEqual(sum(value is not None for value in claims), 1)


    def test_model_unavailability_is_not_reported_as_a_clean_audit(self):
        source = self.root / "core/wake_word.py"
        source.parent.mkdir()
        source.write_text("value = 1")
        def unavailable(*args, **kwargs):
            return kwargs["default"]
        with patch.object(service, "ROOT", self.root), \
             patch("core.gemini.as_json", side_effect=unavailable):
            with self.assertRaisesRegex(ValueError, "modeli yanıt vermedi"):
                service.discover(0)
