from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from actions import background_tasks
from core.tasks.agents import AgentProfile
from core.tasks.cognitive_review import review_node
from core.tasks.engine import TaskEngine


class CognitiveReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = TaskEngine(root / "tasks", root / "reports", [], autostart=False, log=lambda *_: None)
        self.permission = patch("memory.config_manager.get_cognitive_review_sharing", return_value=True)
        self.permission.start()
        self.addCleanup(self.permission.stop)
        self.engine._agents = {"general": AgentProfile("general", tools=["write_file"], minutes=1)}
        self.doc = self.engine.cognitive.create("Goal", [{"id": "a", "task": "Write a file"}], "silent")
        self.engine.cognitive.advance()
        self.tid = self.doc["nodes"][0]["task_id"]
        self.folder = self.engine.store.workdir(self.tid) / "files"
        self.folder.mkdir(parents=True)
        (self.folder / "output.txt").write_text("original", encoding="utf-8")
        self.engine.store.save_turns(self.tid, [
            {"role": "model", "calls": [{"id": "c", "name": "write_file", "args": {"path": "output.txt", "content": "original"}}]},
            {"role": "tool", "results": [{"id": "c", "name": "write_file", "result": "status=done action=write_file"}]}])
        self.engine._finish(self.tid, "done", result="Here is the result.")
        self.engine.cognitive.advance()

    def test_actual_file_rechecked_and_opinion_never_becomes_fact(self):
        prompts = []
        def ask(prompt):
            prompts.append(prompt)
            return {"verdict": "supported", "reason": "The answer appears relevant."}
        review = review_node(self.engine, self.doc["id"], "a", ask=ask)
        self.assertEqual(review["file_counts"]["verified"], 1)
        self.assertFalse(review["truth_verified"])
        self.assertFalse(review["model_independent"])
        self.assertIn("<<<UNTRUSTED source=answer>>>", prompts[0])
        self.assertNotIn(str(self.folder), prompts[0])
        saved = self.engine.cognitive.get(self.doc["id"])
        self.assertEqual(saved["status"], "finished_unverified")
        self.assertEqual(saved["nodes"][0]["review"]["opinion"], "supported")

    def test_changed_file_is_not_claimed_verified(self):
        (self.folder / "output.txt").write_text("changed", encoding="utf-8")
        review = review_node(self.engine, self.doc["id"], "a",
                             ask=lambda _: {"verdict": "supported", "reason": "Possible."})
        self.assertEqual(review["file_counts"]["changed"], 1)
        self.assertEqual(review["file_counts"]["verified"], 0)
        self.assertFalse(review["truth_verified"])

    def test_long_answer_is_explicitly_marked_as_truncated(self):
        self.engine.store.update(self.tid, result="a" * 5000)
        prompts = []
        review = review_node(self.engine, self.doc["id"], "a",
                             ask=lambda prompt: (prompts.append(prompt) or {"verdict": "uncertain", "reason": "partial"}))
        self.assertTrue(review["result_truncated"])
        self.assertIn("Answer truncated: true", prompts[0])

    def test_file_change_during_model_call_discards_review(self):
        def ask(_):
            (self.folder / "output.txt").write_text("changed during review", encoding="utf-8")
            return {"verdict": "supported", "reason": "Possible."}
        with self.assertRaisesRegex(ValueError, "changed during review"):
            review_node(self.engine, self.doc["id"], "a", ask=ask)
        self.assertNotIn("review", self.engine.cognitive.get(self.doc["id"])["nodes"][0])

    def test_failed_model_or_invalid_verdict_does_not_save(self):
        for response in (None, {"verdict": "verified", "reason": "done"},
                         {"verdict": "supported", "reason": "ok", "extra": "x"}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                review_node(self.engine, self.doc["id"], "a", ask=lambda _: response)
        self.assertNotIn("review", self.engine.cognitive.get(self.doc["id"])["nodes"][0])

    def test_uncertain_task_is_not_reviewed_as_completed(self):
        self.engine.store.update(self.tid, cognitive_ledger={"x": {"status": "started", "tool": "write_file"}})
        with self.assertRaisesRegex(ValueError, "uncertain"):
            review_node(self.engine, self.doc["id"], "a", ask=lambda _: self.fail("must not call model"))

    def test_conversation_action_reports_opinion_and_real_evidence(self):
        with patch("core.tasks.desktop.ensure", return_value=self.engine), \
             patch("core.gemini.as_json", return_value={"verdict": "uncertain", "reason": "Insufficient evidence."}):
            result = background_tasks.background_tasks({"action": "cognitive_review", "workflow_id": self.doc["id"], "node_id": "a"})
        self.assertIn("status=unverified", result)
        self.assertIn("files_verified=1", result)
        self.assertIn("opinion=uncertain", result)
        self.assertIn("<<<UNTRUSTED source=review-opinion>>>", result)

    def test_disabled_review_never_sends_task_to_model(self):
        with patch("memory.config_manager.get_cognitive_review_sharing", return_value=False):
            with self.assertRaisesRegex(ValueError, "disabled"):
                review_node(self.engine, self.doc["id"], "a", ask=lambda _: self.fail("must not send"))

    def test_private_memory_or_hardware_node_is_blocked_even_with_review_consent(self):
        for tool in ("recall_memory", "system_snapshot", "windows_power_status"):
            with self.subTest(tool=tool):
                self.engine._agents["private"] = AgentProfile("private", tools=[tool], minutes=1)
                doc = self.engine.cognitive.create("Goal", [{"id": "p", "task": "Private", "agent": "private"}], "silent")
                self.engine.cognitive.advance()
                self.engine._finish(doc["nodes"][0]["task_id"], "done", result="PRIVATE")
                self.engine.cognitive.advance()
                with self.assertRaisesRegex(ValueError, "private"):
                    review_node(self.engine, doc["id"], "p", ask=lambda _: self.fail("must not send"))

    def test_revoked_consent_discards_late_review(self):
        with patch("memory.config_manager.get_cognitive_review_sharing", side_effect=[True, True, False]):
            with self.assertRaisesRegex(ValueError, "disabled during"):
                review_node(self.engine, self.doc["id"], "a", ask=lambda _: {"verdict": "supported", "reason": "ok"})
        self.assertNotIn("review", self.engine.cognitive.get(self.doc["id"])["nodes"][0])

    def test_corrupt_primary_does_not_restore_old_review_consent(self):
        from memory import config_manager
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "settings.json"
            primary.with_name(primary.name + ".bak").write_text('{"cognitive_review_sharing":true}', encoding="utf-8")
            # Stop the setUp mock to exercise the real preference reader.
            self.permission.stop()
            with patch.object(config_manager, "CONFIG_FILE", primary):
                self.assertFalse(config_manager.get_cognitive_review_sharing())
                primary.write_text("{broken", encoding="utf-8")
                self.assertFalse(config_manager.get_cognitive_review_sharing())
                primary.write_text('{"cognitive_review_sharing":true}', encoding="utf-8")
                self.assertTrue(config_manager.get_cognitive_review_sharing())
