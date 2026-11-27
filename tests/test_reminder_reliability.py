"""Reminder registration must preserve separate tasks and valid OS commands."""
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from actions import reminder


class ReminderReliability(unittest.TestCase):
    def test_same_time_reminders_get_distinct_system_jobs(self):
        due = datetime.now() + timedelta(days=1)
        base = {"date": due.strftime("%Y-%m-%d"), "time": due.strftime("%H:%M")}
        names = []
        with patch.object(reminder, "_get_os", return_value="windows"), \
             patch.object(reminder, "_mirror_to_cloud", return_value=""), \
             patch.object(reminder, "_share_with_devices", return_value=""), \
             patch.object(reminder, "_add_spoken_routine", return_value=""), \
             patch.object(reminder, "_write_notify_script", side_effect=lambda name, *a: Path(name)), \
             patch.object(reminder, "_schedule_windows", side_effect=lambda dt, name, *a: names.append(name) or name):
            reminder.reminder({**base, "message": "İlk"})
            reminder.reminder({**base, "message": "İkinci"})
        self.assertEqual(len(names), 2)
        self.assertNotEqual(names[0], names[1])

    def test_windows_xml_escapes_special_characters_in_script_path(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(reminder, "_scripts_dir", return_value=Path(directory)):
            def create(args, **kwargs):
                xml_path = Path(args[args.index("/XML") + 1])
                root = ElementTree.fromstring(xml_path.read_text(encoding="utf-16"))
                ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
                self.assertIn("Me & You", root.find(".//t:Arguments", ns).text)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            with patch.object(reminder.subprocess, "run", side_effect=create):
                job = reminder._schedule_windows(datetime(2030, 1, 1), "job", Path(directory) / "Me & You.py", "x")
        self.assertEqual(job, "job")

    def test_linux_at_quotes_paths_with_spaces(self):
        calls = []
        def which(name):
            return "/bin/at" if name == "at" else None
        def run(args, **kwargs):
            calls.append(kwargs["input"])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        with patch.object(reminder.shutil, "which", side_effect=which), \
             patch.object(reminder.sys, "executable", "/some dir/python"), \
             patch.object(reminder.subprocess, "run", side_effect=run):
            reminder._schedule_linux(datetime(2030, 1, 1), "job", Path("/some dir/task.py"))
        self.assertEqual(calls, ["'/some dir/python' '/some dir/task.py'\n"])


if __name__ == "__main__":
    unittest.main()
