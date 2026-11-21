"""Mayk Alıcı (android-receiver/): the files it shares with the other
devices must match what web/app.js and core/sync_hub.py use."""
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "android-receiver" / "app" / "src" / "main"


class AliciTest(unittest.TestCase):
    def java(self, name):
        return (SRC / "java" / "com" / "jarvis" / "alici" / name).read_text(encoding="utf-8")

    def test_same_files_and_commands_as_the_web(self):
        svc = self.java("ReceiverService.java")
        for f in ('"inbox-" + me + ".json"', '"outbox-" + me + ".json"', '"device-" + me + ".json"'):
            self.assertIn(f, svc)
        self.assertIn('.put("kind", "receiver")', svc)
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        ops = set(re.findall(r'case "(\w+)":', svc))
        for op in ("key", "app", "url", "search", "type", "look", "wifi", "jarvis"):
            self.assertIn(op, ops)
        self.assertIn("sendToReceiver(rx, { op", js)
        self.assertIn("jarvisalici://setup?s=", js)
        self.assertIn('android:scheme="jarvisalici"', (SRC / "AndroidManifest.xml").read_text(encoding="utf-8"))

    def test_receivers_are_not_normal_targets(self):
        from core import sync_hub
        devs = [{"id": "rx1", "name": "Projeksiyon (alıcı)", "kind": "receiver", "seen": sync_hub._now()},
                {"id": "w-p", "name": "Projeksiyon", "kind": "projector", "seen": sync_hub._now()}]
        self.assertEqual(sync_hub.find_device("projeksiyon", devs)["id"], "w-p")

    def test_build_is_published(self):
        wf = (ROOT / ".github" / "workflows" / "android-receiver.yml").read_text(encoding="utf-8")
        self.assertIn("gh release upload alici out/jarvis-alici.apk", wf)
        self.assertTrue((ROOT / "android-receiver" / "app" / "jarvis-alici.jks").is_file())


if __name__ == "__main__":
    unittest.main()
