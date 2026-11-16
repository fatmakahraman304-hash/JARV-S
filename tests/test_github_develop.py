import json
import tempfile
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
    def test_git_failure_names_operation_without_echoing_command_output(self):
        with patch.object(g.subprocess, "run", return_value=g.subprocess.CompletedProcess(
            [], 128, "", "fatal: unable to auto-detect email address (private value)"
        )):
            with self.assertRaisesRegex(g.CommandFailure, r"git commit başarısız \(kod 128\)") as failure:
                g.command(["git", "-c", "user.name=Example", "commit", "-m", "A change"])
        self.assertTrue(failure.exception.missing_identity)
        self.assertNotIn("private value", str(failure.exception))

    def test_windows_finds_installed_cli_without_updated_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for variable, directory in (
                ("ProgramFiles", "GitHub CLI"),
                ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
            ):
                with self.subTest(variable=variable), patch.object(g.sys, "platform", "win32"), patch.object(
                    g.shutil, "which", return_value=None
                ), patch.dict(g.os.environ, {variable: folder}, clear=True):
                    executable = root / directory / "gh.exe"
                    executable.parent.mkdir(parents=True)
                    self.assertIsNone(g.find_github_cli())
                    executable.touch()
                    self.assertEqual(g.find_github_cli(), str(executable))

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
    def test_workspace_prefers_murat_and_keeps_a_matching_existing_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(g._development_workspace(root), root / "Murat")
            existing = root / "ExistingCheckout"
            (existing / ".git").mkdir(parents=True)
            (existing / "update_channel.json").write_text(json.dumps({"repository": g.REPO}))
            unrelated = root / "UnrelatedCheckout"
            (unrelated / ".git").mkdir(parents=True)
            (unrelated / "update_channel.json").write_text(json.dumps({"repository": "test/other"}))
            self.assertEqual(g._development_workspace(root), existing)
            (root / "Murat").mkdir()
            self.assertEqual(g._development_workspace(root), root / "Murat")

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


class PublishRecoveryTests(unittest.TestCase):
    def test_retry_commits_staged_files_with_github_identity_when_git_has_none(self):
        error = g.CommandFailure("git var", g.subprocess.CompletedProcess(
            [], 128, "", "Author identity unknown"
        ))
        with patch.object(g, "command", side_effect=[
            error, json.dumps({"login": "example-user", "id": 123}), "gui/book_panel.py\0", "",
        ]) as command:
            g._commit_selected(set(), {"gui/book_panel.py"}, "Book shortcuts")
        self.assertEqual(command.call_args.args[0], [
            "git", "-c", "user.name=example-user", "-c",
            "user.email=123+example-user@users.noreply.github.com", "commit", "-m", "Book shortcuts",
        ])

    def test_retry_pushes_existing_scoped_commit_and_reports_pending_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".git").mkdir()
            scope = ["gui/book_panel.py", "tests/test_book_panel.py"]
            files = "\0".join(scope) + "\0"
            with patch.object(g, "WORK", root), patch.object(g, "tests"), patch.object(
                g, "command", side_effect=[
                    "jarvis-dev/book", "", "", "base", files, "", "", "head", files, "",
                    '[{"number": 42}]',
                    json.dumps({"headRefOid": "head", "baseRefName": "main", "state": "OPEN",
                                "statusCheckRollup": [{"status": "IN_PROGRESS", "conclusion": None}],
                                "url": "https://github.com/example/example/pull/42"}),
                ]
            ) as command:
                result = g.workflow("publish", "Book shortcuts", scope)
            self.assertIn("/pull/42", result)
            self.assertTrue(any("head:refs/heads/jarvis-dev/book" in call.args[0]
                                for call in command.call_args_list))
            self.assertFalse(any("commit" in call.args[0] or "merge" in call.args[0]
                                 for call in command.call_args_list))
