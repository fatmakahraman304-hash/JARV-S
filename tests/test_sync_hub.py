"""JARVIS everywhere: memory merge, setup link, remote commands, web page wiring."""
import base64
import json
import re
import time
import unittest
from pathlib import Path
from unittest import mock

from core import sync_hub

ROOT = Path(__file__).resolve().parent.parent


class MergeTest(unittest.TestCase):
    def test_newer_wins_and_union(self):
        a = {"notes": {"x": {"value": "eski", "updated": "2026-01-01"}, "only_a": "düz"}}
        b = {"notes": {"x": {"value": "yeni", "updated": "2026-02-01T10:00:00Z"}},
             "preferences": {"çay": {"value": "şekersiz", "updated": "2026-02-01"}}}
        m = sync_hub.merge_memory(a, b)
        self.assertEqual(m["notes"]["x"]["value"], "yeni")
        self.assertEqual(m["notes"]["only_a"]["value"], "düz")
        self.assertEqual(m["preferences"]["çay"]["value"], "şekersiz")

    def test_tombstone_removes_older_entry(self):
        a = {"notes": {"x": {"value": "v", "updated": "2026-01-01"}}}
        b = {"notes": {}, "_deleted": {"notes/x": "2026-01-02T00:00:00Z"}}
        m = sync_hub.merge_memory(a, b)
        self.assertNotIn("x", m["notes"])
        self.assertIn("notes/x", m["_deleted"])
        # re-added later: the newer entry survives the old tombstone
        a2 = {"notes": {"x": {"value": "geri", "updated": "2026-03-01T00:00:00Z"}}}
        self.assertEqual(sync_hub.merge_memory(a2, b)["notes"]["x"]["value"], "geri")


class SetupLinkTest(unittest.TestCase):
    def test_link_carries_settings(self):
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "ghp_x", "gist_id": "abc"}), \
             mock.patch.object(sync_hub, "_assistant_name", return_value="JARVIS"):
            link = sync_hub.setup_link("AIzaKEY")
        self.assertTrue(link.startswith(sync_hub.WEB_URL + "#s="))
        blob = link.split("#s=", 1)[1]
        data = json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
        self.assertEqual(data, {"g": "AIzaKEY", "t": "ghp_x", "i": "abc", "n": "JARVIS"})


class CommandTest(unittest.TestCase):
    def setUp(self):
        sync_hub._state["pending"] = []
        sync_hub._state["inject"] = None

    def test_command_goes_to_session_and_waits_for_reply(self):
        got = []
        sync_hub._state["inject"] = got.append
        sync_hub._run_command("c1", "sunumu aç", "Telefon")
        self.assertEqual(got, ["[Telefon cihazından komut] sunumu aç"])
        self.assertIsNone(sync_hub._state["pending"][0]["reply"])
        sync_hub.note_reply("Sunumu açtım.")
        self.assertEqual(sync_hub._state["pending"][0]["reply"], "Sunumu açtım.")

    def test_quick_action_runs_directly(self):
        with mock.patch("core.remote_control.perform", return_value=(True, "Ses açıldı", {})) as perf:
            sync_hub._run_command("c2", "quick:volume_up", "Saat")
        perf.assert_called_once_with("volume_up")
        self.assertEqual(sync_hub._state["pending"][0]["reply"], "Ses açıldı")

    def test_no_session(self):
        sync_hub._run_command("c3", "merhaba", "Tablet")
        self.assertIn("açık değil", sync_hub._state["pending"][0]["reply"])


class CycleTest(unittest.TestCase):
    def test_inbox_is_processed_and_answer_written(self):
        sync_hub._state.update(pending=[], done=set(), etag="", last_memory=time.time(),
                               last_beat=time.time(), turns=[])
        got = []
        sync_hub._state["inject"] = got.append
        files = {"inbox-pc1.json": json.dumps([{"id": "k1", "text": "ekranda ne var", "from": "Telefon"}]),
                 "memory.json": "{}", "recent.json": "[]"}
        writes = []
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "g"}), \
             mock.patch.object(sync_hub, "device_id", return_value="pc1"), \
             mock.patch.object(sync_hub, "read_gist", return_value=(files, "e1", "")), \
             mock.patch.object(sync_hub, "write_files", side_effect=lambda t, g, f: writes.append(f) or True):
            sync_hub._cycle()
            self.assertEqual(got, ["[Telefon cihazından komut] ekranda ne var"])
            self.assertEqual(writes[-1]["inbox-pc1.json"], "[]")
            sync_hub.note_reply("Ekranda bir kod düzenleyici açık.")
            sync_hub._cycle()
        out = json.loads(writes[-1]["outbox-pc1.json"])
        self.assertEqual(out[-1]["id"], "k1")
        self.assertIn("kod düzenleyici", out[-1]["reply"])


class WebPageWiringTest(unittest.TestCase):
    def test_ids_exist(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', html))
        used = set(re.findall(r"\$\('([^']+)'\)", js))
        self.assertFalse(used - ids, f"missing: {sorted(used - ids)}")
        for name in ("manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png", "icon.svg"):
            self.assertTrue((ROOT / "web" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
