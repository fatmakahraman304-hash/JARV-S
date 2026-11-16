import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import dev_agent
from core import claude_coding


class ClaudeCodingTests(unittest.TestCase):
    def test_selected_coding_provider_uses_local_cli_without_running_tools(self):
        completed = subprocess.CompletedProcess(
            [], 0, json.dumps({"is_error": False, "result": "new source"}), "",
        )
        with patch.object(dev_agent, "_coding_provider", return_value=claude_coding.PROVIDER_ID), patch.object(
            claude_coding, "_executable", return_value="claude"
        ), patch.object(claude_coding.subprocess, "run", return_value=completed) as run:
            reply = dev_agent._get_model().generate_content("project context")

        self.assertEqual(reply.text, "new source")
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--no-session-persistence", args)
        self.assertNotIn("project context", args)
        self.assertEqual(run.call_args.kwargs["input"], "project context")

    def test_windows_find_official_native_install_when_path_is_stale(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            claude_coding.sys, "platform", "win32"
        ), patch.object(claude_coding.shutil, "which", return_value=None), patch.object(
            Path, "home", return_value=Path(folder)
        ):
            executable = Path(folder) / ".local" / "bin" / "claude.exe"
            executable.parent.mkdir(parents=True)
            executable.touch()
            self.assertEqual(claude_coding._executable(), str(executable))

    def test_cli_error_explains_login_without_echoing_provider_output(self):
        completed = subprocess.CompletedProcess([], 1, "", "Not logged in. Internal response.")
        with patch.object(claude_coding, "_executable", return_value="claude"), patch.object(
            claude_coding.subprocess, "run", return_value=completed
        ):
            with self.assertRaisesRegex(RuntimeError, "claude auth login") as error:
                claude_coding.generate_content("project context")
            self.assertNotIn("Internal response", str(error.exception))
