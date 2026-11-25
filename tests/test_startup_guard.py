"""Exercise the actual entry point before audio, Qt or settings are imported."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class StartupGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copy(source / "main.py", self.root / "main.py")
        (self.root / "core").mkdir()
        for name in ("__init__.py", "app_updater.py", "startup_guard.py"):
            path = source / "core" / name
            if path.exists():
                shutil.copy(path, self.root / "core" / name)
        (self.root / "sounddevice.py").write_text(
            'raise RuntimeError("APPLICATION_IMPORT_REACHED")\n', encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config/api_keys.json").write_bytes(b"private sentinel")

    def launch(self):
        return subprocess.run([sys.executable, "main.py"], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=15)

    def test_pending_transactions_block_before_application_imports(self):
        for marker in (b"AETHER/2 zip\n{}", b"AETHER/2 rollback\n{}",
                       b"AETHER/1 applying", b"unknown", b""):
            with self.subTest(marker=marker):
                (self.root / ".aether-update.lock").write_bytes(marker)
                result = self.launch()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Açılış durduruldu", result.stderr)
                self.assertNotIn("APPLICATION_IMPORT_REACHED", result.stderr)
                self.assertEqual((self.root / ".aether-update.lock").read_bytes(), marker)
                self.assertEqual((self.root / "config/api_keys.json").read_bytes(), b"private sentinel")

    def test_clean_start_reaches_application_without_creating_update_files(self):
        self.assertIn("APPLICATION_IMPORT_REACHED", self.launch().stderr)
        self.assertFalse((self.root / ".aether-update.guard").exists())

    def test_interrupted_read_only_check_does_not_block_startup(self):
        (self.root / ".aether-update.lock").write_bytes(b"AETHER/1 checking")
        self.assertIn("APPLICATION_IMPORT_REACHED", self.launch().stderr)
        self.assertEqual((self.root / ".aether-update.lock").read_bytes(), b"AETHER/1 checking")

    def test_active_updater_blocks_even_before_transaction_marker(self):
        from core.app_updater import _update_guard
        with _update_guard(self.root):
            result = self.launch()
        self.assertIn("Açılış durduruldu", result.stderr)
        self.assertNotIn("APPLICATION_IMPORT_REACHED", result.stderr)
        self.assertIn("güncelleme", result.stderr)

    def test_killed_update_blocks_then_offline_recovery_allows_launch(self):
        script = '''
import os
from pathlib import Path
from unittest.mock import patch
from core import app_updater as u
root = Path.cwd()
marker = root / ".aether-update.lock"
marker.write_bytes(b"AETHER/1 checking")
replace = u.os.replace
def stop(src, dst):
    replace(src, dst)
    if Path(dst) == root / "a-added.py":
        os._exit(79)
with patch.object(u.os, "replace", side_effect=stop):
    u._apply_zip(root, {"main.py": (root / "main.py").read_bytes(),
                       "a-added.py": b"new file"}, "b" * 40, "main", marker=marker)
'''
        killed = subprocess.run([sys.executable, "-c", script], cwd=self.root,
                                capture_output=True, timeout=15)
        self.assertEqual(killed.returncode, 79, killed.stderr)
        self.assertIn("--recover", self.launch().stderr)
        recovery = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "core.app_updater", "--recover"],
            cwd=self.root, capture_output=True, timeout=15)
        self.assertEqual(recovery.returncode, 0, recovery.stderr)
        self.assertFalse((self.root / "a-added.py").exists())
        self.assertFalse((self.root / ".aether-update.lock").exists())
        self.assertIn("APPLICATION_IMPORT_REACHED", self.launch().stderr)
        self.assertEqual((self.root / "config/api_keys.json").read_bytes(), b"private sentinel")


if __name__ == "__main__":
    unittest.main()
