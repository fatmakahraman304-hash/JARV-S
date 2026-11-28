import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from actions import background_tasks
from core import confirm
from core.neural_journal import JournalError
from core.tasks.agents import AgentProfile
from core.tasks.engine import TaskEngine
from core.tasks import secure_checkpoint as checkpoint


class SecureTaskCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = TaskEngine(self.root / "tasks", self.root / "reports", [], autostart=False, log=lambda *_: None)
        self.engine._agents = {"general": AgentProfile("general", tools=["notes", "write_file"], minutes=1)}
        self.task = self.engine.start("PRIVATE TASK", agent="general", deliver="silent")
        self.tid = self.task["id"]
        self.engine.store.save_turns(self.tid, [{"role": "user", "text": "PRIVATE TURN"}])
        work = self.engine.store.workdir(self.tid)
        work.mkdir(parents=True, exist_ok=True)
        (work / "notes.md").write_text("PRIVATE NOTE", encoding="utf-8")
        (work / "pages").mkdir()
        (work / "pages" / "page.txt").write_text("PRIVATE PAGE", encoding="utf-8")
        (work / "files").mkdir()
        (work / "files" / "out.txt").write_text("EXCLUDED OUTPUT", encoding="utf-8")
        (work / "inputs").mkdir()
        (work / "inputs" / "in.txt").write_text("EXCLUDED INPUT", encoding="utf-8")
        self.backup = self.engine.store.root / "_encrypted_checkpoint"

    def test_encrypted_snapshot_preserves_task_turns_and_notes_without_copying_outputs(self):
        info = checkpoint.checkpoint(self.engine)
        self.assertGreaterEqual(info["files"], 4)
        self.assertEqual(checkpoint.verify(self.engine)["files"], info["files"])
        raw = (self.backup / "neural_sync.sqlite3").read_bytes()
        for secret in (b"PRIVATE TASK", b"PRIVATE TURN", b"PRIVATE NOTE", b"PRIVATE PAGE"):
            self.assertNotIn(secret, raw)
        with checkpoint.TaskCheckpoint(self.backup) as archive:
            saved = archive.load()
        files = {x["path"]: base64.b64decode(x["data"]) for x in saved["files"]}
        self.assertIn(f"{self.tid}.json", files)
        self.assertIn(f"{self.tid}.turns.json", files)
        self.assertEqual(files[f"{self.tid}/notes.md"], b"PRIVATE NOTE")
        self.assertEqual(files[f"{self.tid}/pages/page.txt"], b"PRIVATE PAGE")
        self.assertNotIn(f"{self.tid}/files/out.txt", files)
        self.assertNotIn(f"{self.tid}/inputs/in.txt", files)
        self.assertTrue((self.engine.store.root / f"{self.tid}.json").exists())

    def test_running_worker_refuses_without_replacing_previous_snapshot(self):
        before = checkpoint.checkpoint(self.engine)
        self.engine._workers["active"] = Mock(is_alive=lambda: True)
        with self.assertRaisesRegex(ValueError, "running"):
            checkpoint.checkpoint(self.engine)
        self.assertEqual(checkpoint.verify(self.engine)["files"], before["files"])

    def test_invalid_live_json_and_symlink_do_not_replace_previous_snapshot(self):
        checkpoint.checkpoint(self.engine)
        original = checkpoint.verify(self.engine)
        (self.engine.store.root / "broken.json").write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid"):
            checkpoint.checkpoint(self.engine)
        self.assertEqual(checkpoint.verify(self.engine)["files"], original["files"])
        (self.engine.store.root / "broken.json").unlink()
        link = self.engine.store.root / "escape.json"
        try:
            link.symlink_to(self.root / "outside")
        except (OSError, NotImplementedError):
            self.skipTest("symbolic link creation is unavailable")
        with self.assertRaisesRegex(ValueError, "regular"):
            checkpoint.checkpoint(self.engine)
        self.assertEqual(checkpoint.verify(self.engine)["files"], original["files"])

    def test_tampering_and_missing_key_never_overwrite_the_checkpoint(self):
        checkpoint.checkpoint(self.engine)
        with checkpoint.TaskCheckpoint(self.backup) as archive:
            archive._db.execute("UPDATE task_snapshot SET data=? WHERE id=1", (b"tampered",))
            archive._db.commit()
        with self.assertRaises(JournalError):
            checkpoint.verify(self.engine)
        with self.assertRaises(JournalError):
            checkpoint.checkpoint(self.engine)
        with checkpoint.TaskCheckpoint(self.backup) as archive:
            self.assertEqual(archive._db.execute("SELECT data FROM task_snapshot WHERE id=1").fetchone()[0], b"tampered")
        (self.backup / "neural_sync.key").unlink()
        with self.assertRaises(JournalError):
            checkpoint.verify(self.engine)
        self.assertFalse((self.backup / "neural_sync.key").exists())

    def test_process_exit_mid_transaction_keeps_previous_checkpoint(self):
        before = checkpoint.checkpoint(self.engine)
        script = ("import os,sys; from core.tasks.secure_checkpoint import TaskCheckpoint; "
                  "j=TaskCheckpoint(sys.argv[1]); j._db.execute('BEGIN IMMEDIATE'); "
                  "j._db.execute('UPDATE task_snapshot SET data=? WHERE id=1',(b'bad',)); os._exit(23)")
        result = subprocess.run([sys.executable, "-c", script, str(self.backup)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 23, result.stderr.decode(errors="replace"))
        self.assertEqual(checkpoint.verify(self.engine)["files"], before["files"])

    def test_missing_table_fails_closed_without_recreating_it(self):
        checkpoint.checkpoint(self.engine)
        with checkpoint.TaskCheckpoint(self.backup) as archive:
            archive._db.execute("DROP TABLE task_snapshot")
            archive._db.commit()
        database = self.backup / "neural_sync.sqlite3"
        before = database.read_bytes()
        with self.assertRaises(JournalError):
            checkpoint.checkpoint(self.engine)
        self.assertEqual(database.read_bytes(), before)

    def test_missing_database_does_not_silently_reset_checkpoint(self):
        checkpoint.checkpoint(self.engine)
        (self.backup / "neural_sync.sqlite3").unlink()
        with self.assertRaises(JournalError):
            checkpoint.checkpoint(self.engine)
        self.assertFalse((self.backup / "neural_sync.sqlite3").exists())
        self.assertTrue((self.backup / "neural_sync.key").exists())

    def test_symbolic_link_backup_directory_is_rejected(self):
        target = self.root / "target"
        target.mkdir()
        try:
            self.backup.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic link creation is unavailable")
        with self.assertRaises(JournalError):
            checkpoint.checkpoint(self.engine)
        self.assertEqual(list(target.iterdir()), [])

    def test_recovery_requires_human_confirmation_and_never_changes_live_store(self):
        checkpoint.checkpoint(self.engine)
        self.engine.store.update(self.tid, title="LIVE MODIFIED")
        player, tokens = Mock(), []
        confirm.bind(lambda _title, _detail, token: tokens.append(token), lambda: None)
        self.addCleanup(lambda: confirm.bind(None, None))
        with patch("core.tasks.desktop.ensure", return_value=self.engine), \
             patch("core.identity.data_home", return_value=self.root / "user"):
            answer = background_tasks.background_tasks({"action": "task_checkpoint_recover"}, player=player)
            self.assertIn("CONFIRMATION_PENDING", answer)
            confirm.resolve(True, "forged")
            self.assertFalse((self.root / "user" / "task_recovery").exists())
            confirm.resolve(True, tokens[0])
            deadline = time.monotonic() + 5
            while not player.show_content.called and time.monotonic() < deadline:
                time.sleep(0.01)
        folder = Path(player.show_content.call_args.args[1])
        self.assertTrue((folder / f"{self.tid}.json").is_file())
        self.assertIn("PRIVATE TASK", (folder / f"{self.tid}.json").read_text(encoding="utf-8"))
        self.assertEqual(self.engine.get(self.tid)["title"], "LIVE MODIFIED")
        self.assertNotEqual(folder.parent, self.engine.store.root)

    def test_untrusted_restore_paths_are_rejected(self):
        for value in ("../outside", "/absolute", "C:/outside", "a\\..\\x", ".", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checkpoint._safe_path(value)
