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


class VoiceOwnerTest(unittest.TestCase):
    """One voice: phone first, then the computer, then the rest; a device the
    user just turned to wins for a while."""

    def _d(self, id_, kind, active=True, age=5, claim_age=None):
        now = 1_800_000_000
        iso = lambda a: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - a))
        return {"id": id_, "kind": kind, "active": active, "seen": iso(age),
                "claim": iso(claim_age) if claim_age is not None else ""}

    def test_priority(self):
        now = 1_800_000_000
        devs = [self._d("tv", "tv"), self._d("pc", "pc"), self._d("ph", "phone"), self._d("w", "watch")]
        self.assertEqual(sync_hub.voice_owner(devs, now), "ph")
        devs[2]["active"] = False                       # phone put away
        self.assertEqual(sync_hub.voice_owner(devs, now), "pc")
        devs[1] = self._d("pc", "pc", age=120)          # laptop closed (no heartbeat)
        self.assertEqual(sync_hub.voice_owner(devs, now), "tv")
        self.assertIsNone(sync_hub.voice_owner([], now))

    def test_claim_wins_then_expires(self):
        now = 1_800_000_000
        devs = [self._d("ph", "phone"), self._d("pc", "pc", claim_age=30)]
        self.assertEqual(sync_hub.voice_owner(devs, now), "pc")
        devs[1] = self._d("pc", "pc", claim_age=sync_hub.CLAIM_SECONDS + 5)
        self.assertEqual(sync_hub.voice_owner(devs, now), "ph")


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


class UpdateAllTest(unittest.TestCase):
    def test_update_file_triggers_once_but_not_on_first_look(self):
        calls = []
        sync_hub._state.update(pending=[], done=set(), etag="", last_memory=time.time(),
                               last_beat=time.time(), turns=[], on_update=lambda: calls.append(1))
        sync_hub._state.pop("update_seen", None)
        files = {"update.json": json.dumps({"ts": "2026-11-18T10:00:00Z", "by": "Telefon"}), "memory.json": "{}"}
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "g"}), \
             mock.patch.object(sync_hub, "device_id", return_value="pc1"), \
             mock.patch.object(sync_hub, "write_files", return_value=True), \
             mock.patch.object(sync_hub, "read_gist", return_value=(files, "", "")):
            sync_hub._cycle()                       # an old request: remembered, not obeyed
            self.assertEqual(calls, [])
            files["update.json"] = json.dumps({"ts": "2026-11-18T10:05:00Z", "by": "Telefon"})
            sync_hub._cycle()
            sync_hub._cycle()
        self.assertEqual(calls, [1])

    def test_update_command_from_mailbox(self):
        calls = []
        sync_hub._state.update(pending=[], on_update=lambda: calls.append(1))
        sync_hub._run_command("u1", "update:", "Telefon")
        self.assertEqual(calls, [1])
        self.assertIn("Güncelleme başladı", sync_hub._state["pending"][0]["reply"])


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
