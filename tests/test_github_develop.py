import unittest
from pathlib import Path
from unittest.mock import patch
from plugins import github_develop as g
class PublishGuards(unittest.TestCase):
    def test_secret_and_escape_rejected(self):
        for path in ['config/api_keys.json','../outside.py','.env','token.json']:
            with self.assertRaises(ValueError): g.selected_files([path])
    def test_source_allowed(self):
        self.assertEqual(g.selected_files(['gui/window.py']),['gui/window.py'])
    def test_empty_scope_rejected(self):
        with self.assertRaises(ValueError): g.selected_files([])


class TestOutput(unittest.TestCase):
    def test_discovered_cli_is_used_for_direct_commands_and_git_credentials(self):
        executable = str(Path.cwd() / "GitHub CLI" / "gh.exe")
        with patch.object(g, "find_github_cli", return_value=executable), patch.object(
            g.subprocess, "run", return_value=g.subprocess.CompletedProcess([], 0, "", "")
        ) as run:
            g.command(["gh", "auth", "status"])
            self.assertEqual(run.call_args.args[0], [executable, "auth", "status"])
            push = [*g._GH_GIT, "push"]
            g.command(push)
            self.assertEqual(run.call_args.args[0], push)
            self.assertEqual(
                run.call_args.kwargs["env"]["PATH"].split(g.os.pathsep)[0],
                str(Path(executable).parent),
            )

    def test_failed_suite_reports_filename_and_python_error(self):
        with patch.object(g.subprocess, "run") as run:
            run.return_value = g.subprocess.CompletedProcess(
                [], 1, "", "AssertionError: expected result"
            )
            with self.assertRaisesRegex(g.TestFailure, "test_example.py") as error:
                g.command(["python", "-m", "unittest"], test_name="test_example.py")
        self.assertIn("AssertionError: expected result", str(error.exception))
        self.assertEqual(run.call_args.kwargs["env"]["QT_QPA_PLATFORM"], "offscreen")


class LocalDevelopmentCommands(unittest.TestCase):
    def test_explicit_commands_work_with_turkish_caps_and_punctuation(self):
        self.assertEqual(g.local_command_mode("  GİTHUB geliştirme alanını main ile eşitle. "), "sync")
        self.assertEqual(g.local_command_mode("/git test"), "test")
        self.assertEqual(
            g.local_command_mode("GitHub geliştirme alanındaki testleri çalıştır ve sonucu göster"),
            "test",
        )

    def test_other_requests_are_not_local_commands(self):
        self.assertIsNone(g.local_command_mode("GitHub geliştirme alanını main ile eşitleme"))
        self.assertIsNone(g.local_command_mode("/git publish"))
