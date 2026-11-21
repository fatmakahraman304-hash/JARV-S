import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import dev_agent
from memory import continuity, memory_manager
from providers.engine_pipeline import PipelineEngine


class ConversationFollowups(unittest.TestCase):
    def test_large_request_and_its_tool_result_survive_budget(self):
        engine = PipelineEngine(None, history_chars=100)
        turn = [{"role": "user", "content": "Ekranı incele " + "a" * 150},
                {"role": "assistant", "tool_calls": [{"id": "call"}]},
                {"role": "tool", "tool_call_id": "call", "content": "unverified"}]
        engine._history = [{"role": "user", "content": "eski"}] + turn
        self.assertEqual(engine._trimmed(), turn)
        engine._history.append({"role": "user", "content": "Sıradaki konu"})
        self.assertEqual(engine._trimmed(), [engine._history[-1]])
        self.assertEqual(len(engine._history), 1)

    def test_question_with_possessive_recalls_fact_and_conversation(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with patch.object(continuity, "data_dir", return_value=folder), \
             patch.object(memory_manager, "load_memory", return_value={"projects": {"proje": "Atlas"}}), \
             patch.object(memory_manager, "_load_archive", return_value={}):
            continuity.record("Kullanıcı", "Proje Atlas olacak.")
            result = memory_manager.search_memory("Projemi hatırlıyor musun?")
            self.assertIn("proje: Atlas", result)
            self.assertIn("Proje Atlas olacak.", result)

    def test_text_agent_preserves_existing_and_unattributed_test_failures(self):
        failed = {"ok": False, "failed": ["case"], "output": "case failed"}
        with tempfile.TemporaryDirectory() as directory, \
             patch("core.code_checks.static_problems", return_value={}), \
             patch("core.code_checks.runtime_problems", return_value={}), \
             patch("core.code_checks.run_tests", return_value=failed):
            for baseline in (None, failed):
                with self.subTest(baseline=baseline):
                    result = dev_agent._test_and_fix(Path(directory), {"readme.md": "test"},
                        [], {}, "", "", None, {"test_cmd": ["test"], "test_name": "suite"},
                        baseline=baseline)
                    self.assertIn("(tests)", result)
