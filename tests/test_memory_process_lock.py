"""Independent processes must not overwrite each other's local facts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch


SETUP = '''
import sys, time
from pathlib import Path
from memory import memory_manager as m
root = Path(sys.argv[1])
m.MEMORY_PATH = root / "long_term.json"
m.BACKUP_PATH = root / "long_term.json.bak"
m.ARCHIVE_PATH = root / "archive.json"
m._LEGACY_MEMORY_PATH = root / "missing.json"
'''


class MemoryProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "long_term.json").write_text('{"notes":{}}')

    def start(self, script, *args):
        child = subprocess.Popen([sys.executable, "-c", SETUP + script,
                                  str(self.root), *args], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        self.addCleanup(cleanup)
        return child

    def test_simultaneous_read_modify_write_preserves_both_facts(self):
        script = '''
from unittest.mock import patch
name, other = sys.argv[2:]
while not (root / "go").exists():
    time.sleep(.01)
load = m.load_memory
def delayed_read():
    data = load()
    (root / ("read-" + name)).touch()
    deadline = time.monotonic() + .7
    while not (root / ("read-" + other)).exists() and time.monotonic() < deadline:
        time.sleep(.01)
    return data
with patch.object(m, "load_memory", side_effect=delayed_read):
    m.remember(name, "fact " + name)
'''
        children = [self.start(script, "one", "two"), self.start(script, "two", "one")]
        (self.root / "go").touch()
        for child in children:
            _, err = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, err)
        memory = json.loads((self.root / "long_term.json").read_text(encoding="utf-8"))
        self.assertEqual(set(memory["notes"]), {"one", "two"})

    def test_crashed_owner_releases_the_kernel_lock(self):
        owner = self.start('''
with m._lock:
    (root / "held").touch()
    sys.stdin.read()
''')
        deadline = time.monotonic() + 5
        while not (self.root / "held").exists() and time.monotonic() < deadline:
            self.assertIsNone(owner.poll())
            time.sleep(.01)
        self.assertTrue((self.root / "held").exists())
        writer = self.start('(root / "writer-started").touch()\nm.remember("after", "survives crash")\n')
        deadline = time.monotonic() + 5
        while not (self.root / "writer-started").exists() and time.monotonic() < deadline:
            self.assertIsNone(writer.poll())
            time.sleep(.01)
        self.assertTrue((self.root / "writer-started").exists())
        # The writer must remain blocked until the actual owner terminates.
        with self.assertRaises(subprocess.TimeoutExpired):
            writer.wait(timeout=.25)
        owner.kill()
        owner.communicate(timeout=5)
        _, err = writer.communicate(timeout=10)
        self.assertEqual(writer.returncode, 0, err)
        data = json.loads((self.root / "long_term.json").read_text(encoding="utf-8"))
        self.assertIn("after", data["notes"])

    def test_lock_timeout_preserves_data_and_can_be_retried(self):
        from memory.process_lock import FileRLock
        owner = self.start('''
with m._lock:
    (root / "held").touch()
    sys.stdin.read()
''')
        deadline = time.monotonic() + 5
        while not (self.root / "held").exists() and time.monotonic() < deadline:
            self.assertIsNone(owner.poll())
            time.sleep(.01)
        self.assertTrue((self.root / "held").exists())
        before = (self.root / "long_term.json").read_bytes()
        lock = FileRLock(lambda: self.root / "long_term.json.lock", timeout=.1)
        with self.assertRaisesRegex(TimeoutError, "başka bir süreç"):
            with lock:
                self.fail("Cannot acquire a lock held by another process")
        self.assertEqual((self.root / "long_term.json").read_bytes(), before)
        owner.kill()
        owner.communicate(timeout=5)
        with lock:
            with lock:  # reentrant, including after an acquisition failure
                self.assertEqual((self.root / "long_term.json").read_bytes(), before)

    def test_empty_lock_file_is_initialized_only_after_kernel_lock(self):
        from memory import process_lock
        acquired = False
        testcase = self
        class WindowsFile(io.BytesIO):
            def fileno(self):
                return 123
            def write(self, data):
                testcase.assertTrue(acquired, "Writing before the kernel lock races on Windows")
                return super().write(data)
        handle = WindowsFile()
        path = Mock()
        path.open.return_value = handle
        def kernel_lock(fd, mode, size):
            nonlocal acquired
            acquired = True
        api = SimpleNamespace(LK_NBLCK=1, locking=kernel_lock)
        with patch.object(process_lock.os, "name", "nt"), patch.dict(sys.modules, {"msvcrt": api}):
            with process_lock.FileRLock(lambda: path):
                self.assertEqual(handle.getvalue(), b"\0")
        self.assertTrue(handle.closed)
