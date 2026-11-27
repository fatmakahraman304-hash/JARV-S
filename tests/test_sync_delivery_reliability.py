"""Exercise retries against a simulated Gist, including ambiguous writes."""
from contextlib import ExitStack
import json
import time
import unittest
from unittest.mock import patch

from core import sync_hub as hub


class SyncDeliveryReliability(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        now = time.time()
        self.state = {"pending": [], "done": set(), "etag": "", "last_memory": now,
                      "last_beat": now, "last_projects": now, "turns": [], "rem_new": [],
                      "out_cmds": [], "img_new": [], "arch_queue": [], "devices": [],
                      "rem_known": set(), "on_reminder": None, "on_owner": None,
                      "owner": None, "push_gone": set(), "active": True, "claim": ""}
        self.stack.enter_context(patch.dict(hub._state, self.state))
        for name, value in (("settings", {"github_token": "t", "gist_id": "g"}),
                            ("device_id", "pc1"), ("device_name", "PC")):
            self.stack.enter_context(patch.object(hub, name, return_value=value))
        for name in ("_push_setup", "_push_inboxes", "_archive_flush", "_battery_watch",
                     "_push_due_reminders", "_save_known"):
            self.stack.enter_context(patch.object(hub, name))
        self.files = {"recent.json": "[]", "memory.json": "{}", "reminders.json": "[]",
                      "images.json": "[]", "inbox-tv.json": "[]", "outbox-pc1.json": "[]"}
        self.read = self.stack.enter_context(patch.object(
            hub, "read_gist", side_effect=lambda *_: (dict(self.files), "tag", "")))

    def queue_everything(self):
        now = time.time()
        hub._state["pending"].append({"id": "reply-1", "at": now, "reply": "Hazır"})
        hub._state["turns"].append({"sync_id": "turn-1", "text": "merhaba"})
        hub._state["out_cmds"].append(("tv", {"id": "cmd-1", "kind": "say", "text": "merhaba"}))
        hub._state["img_new"].append({"id": "img-1", "url": "https://example.test/i.png"})
        hub._state["rem_new"].append({"id": "rem-1", "text": "iş", "due": (now + 600) * 1000})

    def test_failure_retries_without_dropping_or_repeating_items(self):
        self.queue_everything()
        attempts = []
        def write(_token, _gid, files):
            attempts.append(dict(files))
            if len(attempts) == 1:
                return False
            self.files.update(files)
            return True
        with patch.object(hub, "write_files", side_effect=write), \
             patch.object(hub, "_merge_local_memory", return_value={}):
            hub._cycle()
            self.assertTrue(hub.status().startswith("hata:"))
            for name in ("pending", "turns", "out_cmds", "img_new", "rem_new"):
                self.assertEqual(len(hub._state[name]), 1, name)
            self.assertEqual(hub._state["etag"], "")
            hub._cycle()
        for name in ("pending", "turns", "out_cmds", "img_new", "rem_new"):
            self.assertFalse(hub._state[name], name)
        for name, key, expected in (("outbox-pc1.json", "id", "reply-1"),
                                    ("recent.json", "sync_id", "turn-1"),
                                    ("inbox-tv.json", "id", "cmd-1"),
                                    ("images.json", "id", "img-1"),
                                    ("reminders.json", "id", "rem-1")):
            self.assertEqual([item[key] for item in json.loads(self.files[name])], [expected])

    def test_ambiguous_write_deduplicates_after_server_already_accepted_it(self):
        self.queue_everything()
        count = 0
        def write(_token, _gid, files):
            nonlocal count
            count += 1
            self.files.update(files)  # response lost after the server applied it
            return count > 1
        with patch.object(hub, "write_files", side_effect=write), \
             patch.object(hub, "_merge_local_memory", return_value={}):
            hub._cycle()
            hub._cycle()
        for name in ("outbox-pc1.json", "recent.json", "inbox-tv.json", "images.json", "reminders.json"):
            self.assertEqual(len(json.loads(self.files[name])), 1, name)
        for name in ("pending", "turns", "out_cmds", "img_new", "rem_new"):
            self.assertFalse(hub._state[name], name)

    def test_full_or_invalid_remote_inbox_does_not_discard_queued_command(self):
        item = ("tv", {"id": "new", "kind": "say"})
        hub._state["out_cmds"].append(item)
        for raw in ("invalid", json.dumps([{"id": str(i)} for i in range(10)])):
            writes = {}
            self.assertEqual(hub._deliver_out({"inbox-tv.json": raw}, writes), [])
            self.assertNotIn("inbox-tv.json", writes)
            self.assertEqual(hub._state["out_cmds"], [item])

    def test_enqueue_during_write_is_not_acknowledged_with_previous_batch(self):
        first = ("tv", {"id": "first", "kind": "say"})
        second = ("tv", {"id": "second", "kind": "say"})
        hub._state["out_cmds"].append(first)
        def write(_token, _gid, _files):
            with hub._state["lock"]:
                hub._state["out_cmds"].append(second)
            return True
        with patch.object(hub, "write_files", side_effect=write):
            hub._cycle()
        self.assertEqual(hub._state["out_cmds"], [second])

    def test_same_millisecond_creates_unique_command_ids(self):
        with patch.object(hub.time, "time", return_value=100):
            hub._queue_to("tv", {"kind": "say"})
            hub._queue_to("tv", {"kind": "say"})
        ids = [item["id"] for _, item in hub._state["out_cmds"]]
        self.assertNotEqual(*ids)
