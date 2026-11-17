import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import code_checks, codex_coding


class CodingModelTests(unittest.TestCase):
    def test_codex_answers_when_it_is_the_best_available(self):
        # The coding router picks the best installed model; with only Codex
        # installed and free, Codex answers and nothing else is called.
        from actions import dev_agent
        from core import coding_router
        from types import SimpleNamespace

        with patch.object(dev_agent, "_coding_provider", return_value=codex_coding.PROVIDER_ID), \
             patch.object(coding_router, "ladder", return_value=[codex_coding.PROVIDER_ID, ""]), \
             patch.object(codex_coding, "generate_content", return_value=SimpleNamespace(text="kod")) as gen, \
             patch.object(dev_agent.gemini, "call") as gem:
            self.assertEqual(dev_agent._get_model().generate_content("yaz").text, "kod")
        gen.assert_called_once_with("yaz")
        gem.assert_not_called()

    def test_codex_receives_context_through_stdin_and_returns_final_reply(self):
        def run(args, **options):
            self.assertIn("read-only", args)
            self.assertNotIn("project context", args)
            self.assertIn("project context", options["input"])
            destination = Path(args[args.index("--output-last-message") + 1])
            self.assertEqual(destination.parent, Path(options["cwd"]))
            destination.write_text("proposed source", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0)

        with patch.object(codex_coding, "_command", return_value=["codex"]), patch.object(
            codex_coding.subprocess, "run", side_effect=run
        ):
            self.assertEqual(codex_coding.generate_content("project context").text, "proposed source")

    def test_codex_auth_error_is_reported_without_cli_output(self):
        failed = subprocess.CompletedProcess([], 1, "", "401 Unauthorized: private response")
        with patch.object(codex_coding, "_command", return_value=["codex"]), patch.object(
            codex_coding.subprocess, "run", return_value=failed
        ):
            with self.assertRaisesRegex(RuntimeError, "^Codex oturumu doğrulanamadı") as error:
                codex_coding.generate_content("project context")
            self.assertNotIn("private response", str(error.exception))

    def test_failed_plan_is_shown_in_job_and_activity_log(self):
        from actions import dev_agent
        from unittest.mock import Mock

        player = Mock()
        with tempfile.TemporaryDirectory() as folder, patch.object(
            dev_agent, "_JOB", {}
        ), patch.object(dev_agent, "_player_ref", None), patch.object(
            dev_agent, "_plan_changes", side_effect=RuntimeError("Codex oturumu doğrulanamadı")
        ), patch.object(dev_agent, "_agent_ladder", return_value=[]
        ), patch.object(dev_agent, "_scan", return_value=(["readme.md"], {"readme.md": "Example"}, {})), patch.object(
            code_checks, "detect_stack", side_effect=ValueError("test scaffolding")
        ):
            root = Path(folder)
            dev_agent._new_job(root, "codex_cli", "Add a line", player)
            self.assertTrue(dev_agent._job_lock.acquire(False))
            with patch.object(dev_agent.threading, "Thread") as thread:
                dev_agent._run_job(lambda: dev_agent._improve_folder(root, "Add a line", player),
                                   root.name, "codex_cli", player=player)
                thread.call_args.kwargs["target"]()
            state = dev_agent._job_snapshot()
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["phase"], "planning")
            self.assertIn("Codex oturumu doğrulanamadı", state["result"])
            self.assertIn(state["result"], player.write_log.call_args.args[0])

    def test_local_runner_discovers_unittest_files_in_plain_tests_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / "tests").mkdir()
            (project / "tests" / "test_example.py").write_text(
                "import unittest\nclass Example(unittest.TestCase):\n"
                "    def test_run(self):\n        self.assertTrue(True)\n", encoding="utf-8"
            )
            with patch.object(code_checks, "_has_module", return_value=False):
                stack = code_checks.detect_stack(project)
            result = code_checks.run_tests(project, stack)
            self.assertTrue(result["ok"], result["output"])
            self.assertIn("Ran 1 test", result["output"])
