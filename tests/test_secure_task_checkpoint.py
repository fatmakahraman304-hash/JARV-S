import base64
import json
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

    def test_personal_agenda_persists_and_completes_through_desktop_tool(self):
        display = Mock()
        def invoke(action, **args):
            with patch("core.tasks.desktop.ensure", return_value=self.engine):
                return background_tasks.background_tasks(dict(action=action, **args), display)
        title = "PRIVATE EDUCATION TASK"
        result = invoke("agenda_add", day="2026-12-01", task=title)
        ident = result.split()[-1]
        self.assertEqual(len(ident), 32)
        self.assertNotIn(title.encode(), (self.backup / "neural_sync.sqlite3").read_bytes())
        self.assertNotIn(title, invoke("agenda_day", day="2026-12-01"))
        self.assertIn("Bekliyor · " + title, display.show_content.call_args.args[1])
        self.assertIn("complete", invoke("agenda_complete", task_id=ident))
        invoke("agenda_day", day="2026-12-01")
        self.assertIn("Tamamlandı · " + title, display.show_content.call_args.args[1])
        invoke("agenda_day", day="2026-12-02")
        self.assertNotIn(title, display.show_content.call_args.args[1])

    def test_plan_conflict_reschedule_and_versioned_personal_recovery(self):
        display = Mock()
        def invoke(action, **args):
            with patch("core.tasks.desktop.ensure", return_value=self.engine):
                return background_tasks.background_tasks(dict(action=action, **args), display)
        day = "2026-12-01"
        first = invoke("agenda_add", task="Ders", day=day, start_time="09:00", duration=60,
                       priority="high").split()[-1]
        second = invoke("agenda_add", task="Proje", day=day, start_time="09:30", duration=30).split()[-1]
        invoke("agenda_day", day=day)
        panel = display.show_content.call_args.args[1]
        self.assertLess(panel.index("Ders"), panel.index("Proje"))
        self.assertIn("Öneri 10:00", panel)
        checkpoint.checkpoint(self.engine)
        invoke("agenda_reschedule", task_id=second, start_time="10:00", duration=30)
        invoke("agenda_complete", task_id=first)
        invoke("agenda_day", day=day)
        self.assertNotIn("Çakışma", display.show_content.call_args.args[1])
        invoke("agenda_week", day=day)
        self.assertIn("2 görevin 1", display.show_content.call_args.args[1])
        checkpoint.checkpoint(self.engine)
        old = checkpoint.history(self.engine)[0]["id"]
        with patch("core.identity.data_home", return_value=self.root):
            prior = checkpoint.recover_to_isolated_folder(self.engine, old)
            latest = checkpoint.recover_to_isolated_folder(self.engine)
        record = Path("personal_agenda") / (second + ".json")
        self.assertEqual(json.loads((prior / record).read_bytes())["start"], 570)
        self.assertEqual(json.loads((latest / record).read_bytes())["start"], 600)

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

    def test_history_retains_and_recovers_previous_encrypted_version(self):
        checkpoint.checkpoint(self.engine)
        self.engine.store.save_turns(self.tid, [{"role": "user", "text": "NEW PRIVATE TURN"}])
        checkpoint.checkpoint(self.engine)
        versions = checkpoint.history(self.engine)
        self.assertEqual(len(versions), 1)
        version = versions[0]["id"]
        self.assertEqual(checkpoint.verify(self.engine, version)["files"], checkpoint.verify(self.engine)["files"])
        with patch("core.identity.data_home", return_value=self.root):
            folder = checkpoint.recover_to_isolated_folder(self.engine, version)
        self.assertIn("PRIVATE TURN", (folder / f"{self.tid}.turns.json").read_text())
        self.assertNotIn("NEW PRIVATE TURN", (folder / f"{self.tid}.turns.json").read_text())
        self.assertNotIn(b"PRIVATE TURN", (self.backup / "neural_sync.sqlite3").read_bytes())
        self.assertIn("NEW PRIVATE TURN", str(self.engine.store.load_turns(self.tid)))

    def test_history_missing_or_tampered_version_fails_closed(self):
        checkpoint.checkpoint(self.engine)
        checkpoint.checkpoint(self.engine)
        version = checkpoint.history(self.engine)[0]["id"]
        with checkpoint.TaskCheckpoint(self.backup) as archive:
            archive._db.execute("UPDATE task_snapshot_history SET data=? WHERE id=?", (b"corrupt", version))
            archive._db.commit()
        with self.assertRaises(JournalError):
            checkpoint.verify(self.engine, version)
        with self.assertRaises(JournalError):
            checkpoint.verify(self.engine, 99999)
        checkpoint.verify(self.engine)

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


class ModelEvaluationTests(unittest.TestCase):
    def test_exact_score_and_unavailable(self):
        from tools.evaluate_task_brain import evaluate
        answers = iter(['{"bitis":"10:35"}', '', '{"tekrar":0}'])
        rows = list(evaluate(lambda *a, **k: next(answers), 'fast'))
        self.assertIsNone(rows[1]["elapsed_ms"])
        from types import SimpleNamespace
        response = SimpleNamespace(text='{"bitis":"10:35"}', model_version="fixture",
                                   usage_metadata=SimpleNamespace(prompt_token_count=20, candidates_token_count=9))
        sample = next(evaluate(lambda *a, **k: response, "smart"))
        self.assertEqual((sample["input_tokens"], sample["output_tokens"]), (20, 9))
        self.assertIsNone(sample["cost_usd"])
        self.assertEqual([row["status"] for row in rows], ["passed", "unavailable", "failed"])
