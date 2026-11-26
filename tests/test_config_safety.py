"""A broken settings file never costs the user their API key: the last good copy comes back."""
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import config_manager as cm


class ConfigSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "api_keys.json"
        self.p = patch.object(cm, "CONFIG_FILE", self.file)
        self.p.start()
        self.p2 = patch.object(cm, "ensure_config_dir", lambda: None)
        self.p2.start()

    def tearDown(self):
        self.p.stop()
        self.p2.stop()
        self.tmp.cleanup()

    def test_legacy_assistant_name_becomes_friday(self):
        for old in ("FRIDAY", "FRIDAY.", "Friday", "aether", "LegacyAssistant", "Custom"):
            self.file.write_text(json.dumps({"assistant_name": old, "user_name": "Ada"}))
            self.assertEqual(cm.get_assistant_name(), "FRIDAY")
            self.assertEqual(cm.get_user_name(), "Ada")
        self.file.write_text(json.dumps({"assistant_name": "Friday"}))
        self.assertEqual(cm.get_assistant_name(), "FRIDAY")

    def test_key_survives_a_broken_file(self):
        cm.save_api_keys("AIza-test-key-1234")
        cm.save_wake_word_enabled(True)                     # second write: the first becomes the backup
        self.file.write_text('{"gemini_api_key": "AIza', encoding="utf-8")   # cut off mid-write
        self.assertEqual(cm.load_api_keys().get("gemini_api_key"), "AIza-test-key-1234")
        cm.save_wake_word_enabled(False)                     # a setter after the break keeps the key too
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(data["gemini_api_key"], "AIza-test-key-1234")
        self.assertTrue(list(Path(self.tmp.name).glob("api_keys.json.broken-*")))

    def test_invalid_root_shapes_recover_settings_instead_of_erasing_backup(self):
        good = {"gemini_api_key": "synthetic-key", "voice_name": "Aoede", "user_name": "Test"}
        for damaged in ("[]", "null", '"wrong root"'):
            with self.subTest(damaged=damaged):
                cm._backup_file().write_text(json.dumps(good), encoding="utf-8")
                self.file.write_text(damaged, encoding="utf-8")
                self.assertEqual(cm.load_api_keys().get("gemini_api_key"), "synthetic-key")
                cm.save_wake_word_enabled(True)
                saved = json.loads(self.file.read_text(encoding="utf-8"))
                self.assertEqual({key: saved[key] for key in good}, good)
                self.assertIsInstance(json.loads(cm._backup_file().read_text()), dict)

    def test_missing_primary_recovers_backup_on_read_and_next_setting_change(self):
        good = {"gemini_api_key": "synthetic-key", "voice_name": "Aoede"}
        cm._backup_file().write_text(json.dumps(good))
        self.assertEqual(cm.load_api_keys().get("gemini_api_key"), "synthetic-key")
        self.assertFalse(self.file.exists())  # reading does not publish a new file
        cm.save_wake_word_enabled(True)
        self.assertEqual(cm.get_gemini_key(), "synthetic-key")
        self.assertEqual(cm.get_voice(), "Aoede")

    def test_atomic_writes_preserve_fixed_temporary_names(self):
        names = [self.file.with_name(self.file.name + ".tmp"),
                 cm._backup_file().with_name(cm._backup_file().name + ".tmp")]
        for path in names:
            path.write_bytes(b"existing local file")
        cm.save_api_keys("synthetic-key")
        cm.save_wake_word_enabled(True)
        for path in names:
            self.assertEqual(path.read_bytes(), b"existing local file")

    def test_flush_failure_keeps_primary_backup_and_cleans_staging_file(self):
        cm.save_api_keys("synthetic-key")
        cm.save_wake_word_enabled(True)
        old = {path: path.read_bytes() for path in (self.file, cm._backup_file())}
        before = set(self.file.parent.iterdir())
        with patch.object(cm.os, "fsync", side_effect=OSError("flush error")):
            with self.assertRaisesRegex(OSError, "flush error"):
                cm.save_voice("Kore")
        for path, content in old.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(set(self.file.parent.iterdir()), before)

    def test_backup_flush_failure_does_not_publish_new_settings(self):
        cm.save_api_keys("synthetic-key")
        cm.save_wake_word_enabled(True)
        old = {path: path.read_bytes() for path in (self.file, cm._backup_file())}
        before = set(self.file.parent.iterdir())
        with patch.object(cm.os, "fsync", side_effect=[None, OSError("backup flush error")]):
            with self.assertRaisesRegex(OSError, "backup flush"):
                cm.save_voice("Kore")
        for path, content in old.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(set(self.file.parent.iterdir()), before)

    def test_locked_backup_preserves_settings_and_cleans_temporary_files(self):
        cm.save_api_keys("synthetic-key")
        cm.save_wake_word_enabled(True)
        old = {path: path.read_bytes() for path in (self.file, cm._backup_file())}
        before = set(self.file.parent.iterdir())
        with patch.object(cm.os, "replace", side_effect=PermissionError("file locked")), \
                patch.object(cm.time, "sleep"):
            with self.assertRaises(PermissionError):
                cm.save_voice("Kore")
        for path, content in old.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(set(self.file.parent.iterdir()), before)

    def test_two_processes_preserve_distinct_setting_changes(self):
        self.file.write_text('{"gemini_api_key":"synthetic-key"}')
        script = '''
import sys,time
from pathlib import Path
from unittest.mock import patch
from memory import config_manager as c
root=Path(sys.argv[1]);name,other=sys.argv[2:]
c.CONFIG_FILE=root/"api_keys.json"
c.ensure_config_dir=lambda:None
read=c._read_for_write
def delayed_read():
    data=read()
    (root/("read-"+name)).touch()
    deadline=time.monotonic()+.6
    while not (root/("read-"+other)).exists() and time.monotonic()<deadline:
        time.sleep(.01)
    return data
while not (root/"go").exists():
    time.sleep(.01)
with patch.object(c,"_read_for_write",side_effect=delayed_read):
    c._save_flag(name,True)
'''
        children = [subprocess.Popen([sys.executable, "-c", script, self.tmp.name, name, other],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for name, other in (("setting_one", "setting_two"), ("setting_two", "setting_one"))]
        try:
            (self.file.parent / "go").touch()
            for child in children:
                _, errors = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, errors)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
        data = cm.load_api_keys()
        self.assertTrue(data.get("setting_one"))
        self.assertTrue(data.get("setting_two"))
        self.assertEqual(data["gemini_api_key"], "synthetic-key")


if __name__ == "__main__":
    unittest.main()
