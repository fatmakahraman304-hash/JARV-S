"""Window names are data, never executable shell source or log payloads."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from actions import computer_control as computer


class CommandBoundaries(unittest.TestCase):
    def test_windows_title_is_passed_as_environment_data(self):
        title = '\"); $(Write-Output private); #'
        with patch.object(computer, "_get_os", return_value="windows"), \
             patch.object(computer.subprocess, "run", return_value=Mock(returncode=0)) as run, \
             patch.object(computer.time, "sleep"):
            computer._focus_window(title)
        args, kwargs = run.call_args
        self.assertNotIn(title, " ".join(args[0]))
        self.assertIn("$env:FRIDAY_FOCUS_TITLE", args[0][-1])
        self.assertEqual(kwargs["env"]["FRIDAY_FOCUS_TITLE"], title)
        self.assertFalse(kwargs.get("shell", False))

    def test_mac_title_is_an_argument_not_applescript_source(self):
        title = 'x\"; do shell script \"echo unsafe\"'
        with patch.object(computer, "_get_os", return_value="mac"), \
             patch.object(computer.subprocess, "run", return_value=Mock(returncode=0)) as run, \
             patch.object(computer.time, "sleep"):
            computer._focus_window(title)
        command = run.call_args.args[0]
        self.assertNotIn(title, command[2])
        self.assertEqual(command[3], title)
        self.assertIn("item 1 of argv", command[2])

    def test_private_typed_text_is_not_printed_in_dispatch_log(self):
        output = io.StringIO()
        with redirect_stdout(output), patch.object(computer, "_type", return_value="requested"):
            computer._computer_control({"action": "type", "text": "synthetic-private-value"})
        self.assertNotIn("synthetic-private-value", output.getvalue())
