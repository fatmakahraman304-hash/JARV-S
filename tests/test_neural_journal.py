import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.neural_journal import JournalError, NeuralJournal, QUEUES
from core import sync_hub
from memory import config_manager


def empty():
    return {name: [] for name in QUEUES}


class NeuralJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_crash_preserves_encrypted_queues_and_claim(self):
        script = r'''
import os, sys
from pathlib import Path
from core.neural_journal import NeuralJournal, QUEUES
j = NeuralJournal(Path(sys.argv[1]), 'gist')
rows = {name: [] for name in QUEUES}
rows['turns'].append({'text': 'VERY_PRIVATE_CONTENT_123'})
rows['out_cmds'].append(['tv', {'id': 'private-command-id', 'text': 'secret action'}])
rows['pending'].append({'id': 'private-command-id', 'reply': None, 'at': 0})
assert j.claim('pc', 'private-command-id', rows)
os._exit(33)
'''
        proc = subprocess.run([sys.executable, "-c", script, str(self.root)], capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 33, proc.stderr)
        database = (self.root / "neural_sync.sqlite3").read_bytes()
        for secret in (b"VERY_PRIVATE_CONTENT_123", b"private-command-id", b"secret action"):
            self.assertNotIn(secret, database)
        journal = NeuralJournal(self.root, "gist")
        self.addCleanup(journal.close)
        rows = journal.load()
        self.assertEqual(rows["turns"][0]["text"], "VERY_PRIVATE_CONTENT_123")
        self.assertEqual(rows["pending"][0]["id"], "private-command-id")
        self.assertFalse(journal.claim("pc", "private-command-id"))
        self.assertTrue(journal.claim("pc", "new-command"))

    def test_missing_key_does_not_create_a_replacement(self):
        journal = NeuralJournal(self.root, "gist")
        journal.save(empty())
        journal.close()
        key = self.root / "neural_sync.key"
        key.unlink()
        before = (self.root / "neural_sync.sqlite3").read_bytes()
        with self.assertRaises(JournalError):
            NeuralJournal(self.root, "gist")
        self.assertFalse(key.exists())
        self.assertEqual((self.root / "neural_sync.sqlite3").read_bytes(), before)

    def test_changed_account_cannot_take_another_accounts_queued_data(self):
        journal = NeuralJournal(self.root, "gist-a")
        data = empty()
        data["turns"].append({"text": "private"})
        journal.save(data)
        journal.close()
        other = NeuralJournal(self.root, "gist-b")
        with self.assertRaises(JournalError):
            other.load()
        other.close()
        original = NeuralJournal(self.root, "gist-a")
        self.assertEqual(original.load()["turns"][0]["text"], "private")
        original.close()

    def test_second_process_cannot_open_same_journal(self):
        journal = NeuralJournal(self.root, "gist")
        self.addCleanup(journal.close)
        script = '''import sys\nfrom pathlib import Path\nfrom core.neural_journal import NeuralJournal\nNeuralJournal(Path(sys.argv[1]), "gist")'''
        proc = subprocess.run([sys.executable, "-c", script, str(self.root)], capture_output=True, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"JournalError", proc.stderr)

    def test_tampered_ciphertext_is_not_overwritten(self):
        journal = NeuralJournal(self.root, "gist")
        journal.save(empty())
        with journal._connection:
            journal._connection.execute("UPDATE checkpoint SET data=?", (b"bad ciphertext",))
        with self.assertRaises(JournalError):
            journal.load()
        self.assertEqual(journal._connection.execute("SELECT data FROM checkpoint").fetchone()[0], b"bad ciphertext")
        journal.close()

    def test_claim_and_pending_checkpoint_roll_back_together(self):
        import sqlite3
        journal = NeuralJournal(self.root, "gist")
        self.addCleanup(journal.close)
        journal.save(empty())
        journal._connection.execute("CREATE TRIGGER refuse_checkpoint BEFORE INSERT ON checkpoint BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        journal._connection.commit()
        rows = empty()
        rows["pending"] = [{"id": "cmd", "at": 0, "reply": None}]
        with self.assertRaises(sqlite3.DatabaseError):
            journal.claim("pc", "cmd", rows)
        journal._connection.execute("DROP TRIGGER refuse_checkpoint")
        journal._connection.commit()
        self.assertEqual(journal.load(), empty())
        self.assertTrue(journal.claim("pc", "cmd", rows))
        self.assertEqual(journal.load()["pending"][0]["id"], "cmd")

    def test_changed_account_during_running_sync_does_not_send_old_queue(self):
        journal = NeuralJournal(self.root, "old-gist")
        self.addCleanup(journal.close)
        state = {name: [] for name in QUEUES}
        state.update({"journal": journal})
        state["out_cmds"] = [("tv", {"id": "private"})]
        with patch.dict(sync_hub._state, state), \
             patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "new-gist"}), \
             patch.object(sync_hub, "read_gist") as read:
            sync_hub._cycle()
            read.assert_not_called()
            self.assertEqual(sync_hub._state["out_cmds"][0][1]["id"], "private")

    def test_enqueue_failure_does_not_claim_success_in_memory(self):
        with patch.dict(sync_hub._state, {"out_cmds": [], "journal": Mock()}):
            sync_hub._state["journal"].save.side_effect = OSError("disk full")
            with sync_hub._state["lock"], self.assertRaises(OSError):
                sync_hub._enqueue_locked("out_cmds", ("tv", {"id": "a"}))
            self.assertEqual(sync_hub._state["out_cmds"], [])

    def test_failed_journal_start_does_not_fall_back_to_volatile_queue(self):
        state = {name: [] for name in QUEUES}
        state.update({"journal": None, "journal_required": False, "thread": None,
                      "stop": threading.Event(), "done": set()})
        with patch.dict(sync_hub._state, state), \
             patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "gist"}), \
             patch("core.neural_journal.NeuralJournal", side_effect=OSError("key unavailable")):
            self.assertFalse(sync_hub.start(lambda _: None))
            with sync_hub._state["lock"], self.assertRaises(RuntimeError):
                sync_hub._enqueue_locked("out_cmds", ("tv", {"id": "a"}))
            self.assertEqual(sync_hub._state["out_cmds"], [])

    def test_start_restores_pending_queues_and_marks_unknown_outcome(self):
        journal = NeuralJournal(self.root, "gist")
        data = empty()
        data["pending"].append({"id": "cmd", "at": 0, "reply": None})
        data["out_cmds"].append(["tv", {"id": "msg"}])
        journal.save(data)
        journal.close()
        state = {name: [] for name in QUEUES}
        state.update({"journal": None, "thread": None, "stop": threading.Event(), "done": set()})
        worker = Mock()
        worker.is_alive.return_value = True
        with patch.dict(sync_hub._state, state), \
             patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "gist"}), \
             patch.object(config_manager, "CONFIG_DIR", self.root), \
             patch.object(sync_hub.threading, "Thread", return_value=worker):
            self.assertTrue(sync_hub.start(lambda _: None))
            self.assertIn("sonucu doğrulanamadı", sync_hub._state["pending"][0]["reply"])
            self.assertEqual(sync_hub._state["out_cmds"][0][1]["id"], "msg")
            sync_hub._state["journal"].close()

    def test_already_claimed_command_is_not_executed_after_restart(self):
        journal = NeuralJournal(self.root, "gist")
        self.assertTrue(journal.claim("pc1", "cmd-1"))
        state = {name: [] for name in QUEUES}
        state.update({"journal": journal, "done": set(), "etag": "", "last_memory": 10**12,
                      "last_beat": 10**12, "last_projects": 10**12, "devices": [], "owner": None,
                      "push_gone": set(), "active": True, "claim": "", "rem_known": set()})
        files = {"inbox-pc1.json": json.dumps([{"id": "cmd-1", "text": "quick:mute"}]),
                 "recent.json": "[]", "reminders.json": "[]", "images.json": "[]"}
        with patch.dict(sync_hub._state, state), \
             patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "gist"}), \
             patch.object(sync_hub, "device_id", return_value="pc1"), \
             patch.object(sync_hub, "read_gist", return_value=(files, "", "")), \
             patch.object(sync_hub, "write_files", return_value=True), \
             patch.object(sync_hub, "_run_command") as run, \
             patch.object(sync_hub, "_push_setup"), patch.object(sync_hub, "_push_inboxes"), \
             patch.object(sync_hub, "_archive_flush"), patch.object(sync_hub, "_battery_watch"), \
             patch.object(sync_hub, "_push_due_reminders"):
            sync_hub._cycle()
            run.assert_not_called()
        journal.close()

    def test_command_reply_survives_failed_write_and_is_not_reexecuted(self):
        journal = NeuralJournal(self.root, "gist")
        state = {name: [] for name in QUEUES}
        state.update({"journal": journal, "done": set(), "etag": "", "last_memory": 10**12,
                      "last_beat": 10**12, "last_projects": 10**12, "devices": [], "owner": None,
                      "push_gone": set(), "active": True, "claim": "", "rem_known": set()})
        files = {"inbox-pc1.json": json.dumps([{"id": "cmd-2", "text": "quick:mute"}]),
                 "recent.json": "[]", "reminders.json": "[]", "images.json": "[]"}
        actions = []
        def run(cid, _text, _sender):
            actions.append(cid)
            sync_hub._reply(cid, "İşlem yanıtı")
        patches = (patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "gist"}),
                   patch.object(sync_hub, "device_id", return_value="pc1"),
                   patch.object(sync_hub, "read_gist", return_value=(files, "", "")),
                   patch.object(sync_hub, "_run_command", side_effect=run),
                   patch.object(sync_hub, "_push_setup"), patch.object(sync_hub, "_push_inboxes"),
                   patch.object(sync_hub, "_archive_flush"), patch.object(sync_hub, "_battery_watch"),
                   patch.object(sync_hub, "_push_due_reminders"),
                   patch.object(sync_hub, "_merge_local_memory", return_value={}))
        from contextlib import ExitStack
        with patch.dict(sync_hub._state, state), ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            writer = stack.enter_context(patch.object(sync_hub, "write_files", return_value=False))
            sync_hub._cycle()
            self.assertEqual(actions, ["cmd-2"])
            journal.close()
            journal = NeuralJournal(self.root, "gist")
            saved = journal.load()
            self.assertEqual(saved["pending"][0]["reply"], "İşlem yanıtı")
            sync_hub._state.update(saved, journal=journal, done=set())
            writer.return_value = True
            sync_hub._cycle()
            self.assertEqual(actions, ["cmd-2"])
            self.assertEqual(json.loads(writer.call_args.args[2]["outbox-pc1.json"])[0]["reply"], "İşlem yanıtı")
            self.assertFalse(journal.load()["pending"])
        journal.close()
