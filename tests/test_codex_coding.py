import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import code_checks, codex_coding


class CodingModelTests(unittest.TestCase):
    def test_codex_is_selected_without_falling_back_to_another_model(self):
        from actions import dev_agent

        with patch.object(dev_agent, "_coding_provider", return_value=codex_coding.PROVIDER_ID):
            self.assertIs(dev_agent._get_model(), codex_coding)

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
