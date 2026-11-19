"""A broken settings file never costs the user their API key: the last good copy comes back."""
import json
import tempfile
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

    def test_key_survives_a_broken_file(self):
        cm.save_api_keys("AIza-test-key-1234")
        cm.save_hf_token("hf_" + "a" * 30)                     # second write: the first becomes the backup
        self.file.write_text('{"gemini_api_key": "AIza', encoding="utf-8")   # cut off mid-write
        self.assertEqual(cm.load_api_keys().get("gemini_api_key"), "AIza-test-key-1234")
        cm.save_hf_token("hf_" + "b" * 30)                     # a setter after the break keeps the key too
        data = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(data["gemini_api_key"], "AIza-test-key-1234")
        self.assertTrue(list(Path(self.tmp.name).glob("api_keys.json.broken-*")))


if __name__ == "__main__":
    unittest.main()
