"""A locked SQLite source must not leave backup running indefinitely."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from memory import continuity as c


class BackupDeadlineTests(unittest.TestCase):
    def test_exclusive_source_lock_times_out_without_publishing_then_can_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "backup.sqlite3"
            with patch.object(c, "data_dir", return_value=root):
                c.record("Kullanıcı", "korunacak kayıt")
            source = root / "continuity.sqlite3"
            holder = sqlite3.connect(source)
            holder.execute("PRAGMA journal_mode=DELETE")
            holder.execute("BEGIN EXCLUSIVE")
            script = '''
import json,sys
from pathlib import Path
from memory import continuity as c
root=Path(sys.argv[1])
c.data_dir=lambda:root
c._BACKUP_TIMEOUT=.15
try:
    c.backup_history(root / "backup.sqlite3")
except TimeoutError as exc:
    print(json.dumps({"timeout":str(exc)}))
else:
    raise SystemExit("Expected backup timeout")
'''
            child = subprocess.Popen([sys.executable, "-c", script, str(root)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                try:
                    output, errors = child.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    self.fail("Locked backup did not enforce its deadline")
                self.assertEqual(child.returncode, 0, errors)
                self.assertIn("süre", json.loads(output)["timeout"])
                self.assertFalse(destination.exists())
                self.assertEqual(list(root.glob("tmp*")), [])
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
                holder.rollback()
                holder.close()
            with patch.object(c, "data_dir", return_value=root):
                self.assertEqual(c.recent()[0][2], "korunacak kayıt")
                c.backup_history(destination)
            with sqlite3.connect(destination) as restored:
                self.assertEqual(restored.execute("SELECT text FROM events").fetchall(),
                                 [("korunacak kayıt",)])

    def test_short_source_lock_finishes_within_the_deadline(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
                c, "data_dir", return_value=Path(folder)), patch.object(c, "_BACKUP_TIMEOUT", 2):
            root = Path(folder)
            c.record("Kullanıcı", "kısa kilit sonrası korunacak")
            holder = sqlite3.connect(root / "continuity.sqlite3", check_same_thread=False)
            holder.execute("PRAGMA journal_mode=DELETE")
            holder.execute("BEGIN EXCLUSIVE")
            release = threading.Timer(.15, holder.rollback)
            release.start()
            try:
                c.backup_history(root / "backup.sqlite3")
            finally:
                release.join(3)
                holder.close()
            with sqlite3.connect(root / "backup.sqlite3") as restored:
                self.assertEqual(restored.execute("SELECT text FROM events").fetchall(),
                                 [("kısa kilit sonrası korunacak",)])
