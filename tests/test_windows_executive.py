import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from actions import windows_power
from core import confirm, windows_executive as win
from core.executive_journal import ExecutiveJournal
from core.neural_journal import JournalError
from core.tasks.tools import TaskTools


class WindowsExecutiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.before = win.SCHEMES["balanced"]
        self.target = win.SCHEMES["power_saver"]
        self.active = self.before
        self.calls = []
        self.journal_path = patch.object(win, "journal_directory", return_value=self.path)
        self.journal_path.start()
        self.addCleanup(self.journal_path.stop)

    def fake_run(self, *args):
        self.calls.append(args)
        if args == ("/getactivescheme",):
            return "Active GUID: " + self.active
        if args == ("/list",):
            return "\n".join(win.SCHEMES.values())
        if len(args) == 2 and args[0] == "/setactive":
            self.active = args[1]
            return ""
        raise AssertionError("unexpected command")

    def test_reversible_operation_uses_real_before_after_and_encrypted_ledger(self):
        with patch.object(win, "_run", side_effect=self.fake_run):
            record = win.set_plan("power_saver", self.path)
            self.assertEqual(self.active, self.target)
            with ExecutiveJournal(self.path) as journal:
                self.assertEqual(journal.get(record["operation_id"])["status"], "done")
            self.assertEqual(win.undo(record["operation_id"], self.path)["status"], "undone")
            self.assertEqual(self.active, self.before)
        raw = (self.path / "neural_sync.sqlite3").read_bytes()
        self.assertNotIn(self.before.encode(), raw)
        self.assertNotIn(self.target.encode(), raw)

    def test_external_change_prevents_undo_overwriting_user(self):
        with patch.object(win, "_run", side_effect=self.fake_run):
            record = win.set_plan("power_saver", self.path)
            self.active = win.SCHEMES["high_performance"]
            before = list(self.calls)
            with self.assertRaisesRegex(win.ExecutiveError, "changed"):
                win.undo(record["operation_id"], self.path)
            self.assertEqual(self.active, win.SCHEMES["high_performance"])
            self.assertNotIn(("/setactive", self.before), self.calls[len(before):])

    def test_change_during_undo_preparation_is_not_overwritten(self):
        with patch.object(win, "_run", side_effect=self.fake_run):
            record = win.set_plan("power_saver", self.path)
        count = 0
        def changed(*args):
            nonlocal count
            if args == ("/getactivescheme",):
                count += 1
                if count == 2:
                    self.active = win.SCHEMES["high_performance"]
            return self.fake_run(*args)
        previous = len(self.calls)
        with patch.object(win, "_run", side_effect=changed):
            with self.assertRaisesRegex(win.ExecutiveError, "changed before undo"):
                win.undo(record["operation_id"], self.path)
        self.assertFalse(any(c[0] == "/setactive" for c in self.calls[previous:]))
        with ExecutiveJournal(self.path) as journal:
            self.assertEqual(journal.get(record["operation_id"])["status"], "done")

    def test_unknown_outcome_blocks_replay_until_real_user_acknowledges(self):
        def interrupted(*args):
            if args[0] == "/setactive":
                self.calls.append(args)
                self.active = args[1]
                raise subprocess.TimeoutExpired("powercfg", 10)
            return self.fake_run(*args)
        with patch.object(win, "_run", side_effect=interrupted):
            with self.assertRaises(win.UnknownOutcome) as unknown:
                win.set_plan("power_saver", self.path)
            ident = unknown.exception.operation_id
            with self.assertRaises(JournalError):
                win.set_plan("high_performance", self.path)
        self.assertEqual(sum(c[0] == "/setactive" for c in self.calls), 1)
        seen = []
        confirm.bind(lambda _title, _detail, token: seen.append(token), lambda: None)
        self.addCleanup(lambda: confirm.bind(None, None))
        with patch.object(windows_power.platform, "system", return_value="Windows"):
            reply = windows_power.windows_power({"action": "review", "operation_id": ident}, player=Mock())
            self.assertIn("CONFIRMATION_PENDING", reply)
            confirm.resolve(True, "forged")
            self.assertEqual(len(win.pending_operations(self.path)), 1)
            confirm.resolve(True, seen[0])
            deadline = time.monotonic() + 5
            while win.pending_operations(self.path) and time.monotonic() < deadline:
                time.sleep(0.02)
        self.assertEqual(win.pending_operations(self.path), [])
        with ExecutiveJournal(self.path) as journal:
            self.assertEqual(journal.get(ident)["status"], "acknowledged")

    def test_failed_verification_remains_unknown_and_does_not_repeat(self):
        def no_effect(*args):
            if args[0] == "/setactive":
                self.calls.append(args)
                return ""
            return self.fake_run(*args)
        with patch.object(win, "_run", side_effect=no_effect):
            with self.assertRaises(win.UnknownOutcome) as error:
                win.set_plan("power_saver", self.path)
        self.assertEqual(win.pending_operations(self.path)[0]["id"], error.exception.operation_id)
        self.assertEqual(sum(c[0] == "/setactive" for c in self.calls), 1)

    def test_changed_before_execution_is_not_overwritten(self):
        count = 0
        def changed(*args):
            nonlocal count
            if args == ("/getactivescheme",):
                count += 1
                if count == 2:
                    self.active = win.SCHEMES["high_performance"]
            return self.fake_run(*args)
        with patch.object(win, "_run", side_effect=changed):
            with self.assertRaisesRegex(win.ExecutiveError, "changed before"):
                win.set_plan("power_saver", self.path)
        self.assertFalse(any(c[0] == "/setactive" for c in self.calls))
        self.assertEqual(win.pending_operations(self.path), [])

    def test_interrupted_process_preserves_pending_record_without_plaintext(self):
        script = ("import os,sys; from pathlib import Path; "
                  "from core.executive_journal import ExecutiveJournal; "
                  "j=ExecutiveJournal(Path(sys.argv[1])); j.begin('power_plan','PRIVATE_BEFORE','PRIVATE_TARGET'); os._exit(23)")
        run = subprocess.run([sys.executable, "-c", script, str(self.path)], capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 23, run.stderr.decode(errors="replace"))
        with ExecutiveJournal(self.path) as journal:
            self.assertEqual(len(journal.pending()), 1)
            with self.assertRaises(JournalError):
                journal.begin("power_plan", "x", "y")
        raw = (self.path / "neural_sync.sqlite3").read_bytes()
        self.assertNotIn(b"PRIVATE_BEFORE", raw)
        self.assertNotIn(b"PRIVATE_TARGET", raw)

    def test_missing_key_or_tampering_stops_without_replacement(self):
        with ExecutiveJournal(self.path) as journal:
            doc = journal.begin("power_plan", "before", "target")
            journal._db.execute("UPDATE executive_ops SET data=? WHERE id=?", (b"broken", doc["id"]))
            journal._db.commit()
            with self.assertRaises(JournalError):
                journal.pending()
        (self.path / "neural_sync.key").unlink()
        with self.assertRaises(JournalError):
            ExecutiveJournal(self.path)
        self.assertFalse((self.path / "neural_sync.key").exists())

    def test_missing_database_does_not_silently_reset_history(self):
        with ExecutiveJournal(self.path) as journal:
            journal.begin("power_plan", "before", "target")
        (self.path / "neural_sync.sqlite3").unlink()
        with self.assertRaises(JournalError):
            ExecutiveJournal(self.path)
        self.assertFalse((self.path / "neural_sync.sqlite3").exists())
        self.assertTrue((self.path / "neural_sync.key").exists())

    def test_missing_operation_table_is_not_silently_recreated(self):
        with ExecutiveJournal(self.path) as journal:
            journal.begin("power_plan", "before", "target")
            journal._db.execute("DROP TABLE executive_ops")
            journal._db.commit()
        database = self.path / "neural_sync.sqlite3"
        before = database.read_bytes()
        with self.assertRaises(JournalError):
            ExecutiveJournal(self.path)
        self.assertEqual(database.read_bytes(), before)

    def test_symbolic_link_journal_directory_is_rejected(self):
        target = self.path / "target"
        target.mkdir()
        link = self.path / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic link creation is unavailable")
        with self.assertRaises(JournalError):
            ExecutiveJournal(link)
        self.assertEqual(list(target.iterdir()), [])

    def test_action_requires_desktop_and_only_accepts_fixed_modes(self):
        with patch.object(windows_power.platform, "system", return_value="Windows"), \
             patch.object(win, "set_plan") as set_plan:
            self.assertIn("status=failed", windows_power.windows_power({"action": "set", "mode": "balanced"}))
            set_plan.assert_not_called()
        with self.assertRaises(ValueError):
            win.set_plan("balanced & whoami", self.path)

    def test_foreground_action_switches_and_restores_through_encrypted_journal(self):
        from core import undo
        self.addCleanup(undo.clear)
        player = Mock()
        with patch.object(windows_power.platform, "system", return_value="Windows"), \
             patch.object(win, "_run", side_effect=self.fake_run), \
             patch("core.hardware_privacy.model_sharing_enabled", return_value=False):
            result = windows_power.windows_power({"action": "set", "mode": "power_saver"}, player)
            self.assertIn("status=done", result)
            self.assertEqual(self.active, self.target)
            status = windows_power.windows_power({"action": "status"}, player)
            self.assertNotIn("power_saver", status)
            self.assertIn("power_saver", player.show_content.call_args.args[1])
            self.assertIn("Undone", undo.undo_last())
            self.assertEqual(self.active, self.before)

    def test_two_threads_serialize_changes_and_both_are_journaled(self):
        results, errors = [], []
        barrier = threading.Barrier(2)
        def worker(mode):
            try:
                barrier.wait(timeout=5)
                results.append(win.set_plan(mode, self.path))
            except Exception as exc:
                errors.append(exc)
        with patch.object(win, "_run", side_effect=self.fake_run):
            threads = [threading.Thread(target=worker, args=(mode,)) for mode in ("power_saver", "high_performance")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
        self.assertFalse(errors)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["status"] == "done" for r in results))
        self.assertEqual(len(win.operation_history(self.path)), 2)

    def test_command_runner_uses_fixed_executable_no_shell_and_timeout(self):
        process = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        with patch.object(win, "_executable", return_value=Path("powercfg.exe")), \
             patch.object(win.subprocess, "run", return_value=process) as run:
            self.assertEqual(win._run("/list"), "ok")
        self.assertEqual(run.call_args.args[0], ["powercfg.exe", "/list"])
        self.assertFalse(run.call_args.kwargs["shell"])
        self.assertGreater(run.call_args.kwargs["timeout"], 0)

    def test_cognitive_status_requires_permission_and_never_gets_web(self):
        with tempfile.TemporaryDirectory() as directory:
            guarded = TaskTools(Path(directory), ["search_web", "windows_power_status"], log=lambda _: None)
            self.assertNotIn("windows_power_status", guarded.names)
            guarded = TaskTools(Path(directory), ["windows_power_status"], log=lambda _: None)
            with patch("core.hardware_privacy.model_sharing_enabled", return_value=False), \
                 patch.object(win, "status") as status:
                self.assertIn("status=failed", guarded.execute("windows_power_status", {}))
                status.assert_not_called()
            with patch("core.hardware_privacy.model_sharing_enabled", return_value=True), \
                 patch.object(win, "status", return_value={"current": "balanced", "available": ["balanced"]}):
                self.assertIn("balanced", guarded.execute("windows_power_status", {}))

    def test_background_workflows_cannot_call_the_mutating_power_action(self):
        from core.tasks.cognitive_tools import CognitiveTools
        underlying = Mock(names=["windows_power"])
        underlying.names = ["windows_power"]
        guarded = CognitiveTools(Mock(), "task", underlying)
        self.assertIn("status=failed", guarded.execute("windows_power", {"action": "set", "mode": "balanced"}))
        underlying.execute.assert_not_called()

    def test_cloud_never_treats_server_power_as_user_laptop(self):
        from core import cloud
        runtime = cloud.Runtime.__new__(cloud.Runtime)
        runtime.tasks, runtime.toolbox, runtime.log = Mock(), Mock(), Mock()
        runtime.tasks.store.workdir.return_value = Path("task")
        with patch.object(cloud, "cloud_task_tools") as build:
            runtime._task_tools({"id": "x"}, Mock(mode="", tools=["windows_power_status", "notes"]))
        self.assertEqual(build.call_args.args[1], ["notes"])

    def test_cloud_manifest_can_instantiate_task_engine_in_isolation(self):
        from core import cloud
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in cloud.MANIFEST:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(repo / name, dest)
            self.assertNotIn("actions/windows_power.py", cloud.MANIFEST)
            self.assertNotIn("core/windows_executive.py", cloud.MANIFEST)
            script = ("import sys,tempfile; from pathlib import Path; sys.path.insert(0,str(Path.cwd())); "
                      "from core.tasks.engine import TaskEngine; import memory.config_manager, memory.memory_manager; "
                      "d=tempfile.TemporaryDirectory(); p=Path(d.name); "
                      "e=TaskEngine(p/'tasks',p/'reports',[Path('agents')],autostart=False); "
                      "assert 'general' in e.agents() and 'researcher' in e.agents(); e.shutdown()")
            result = subprocess.run([sys.executable, "-I", "-c", script], cwd=root,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_cloud_telegram_plugin_is_not_reported_as_missing_token(self):
        from core.cloud import TelegramFront
        front = TelegramFront(Mock(), Mock())
        self.assertEqual(front.start(), "Telegram plugin unavailable on this server")

    @unittest.skipUnless(os.name == "nt", "requires Windows")
    def test_real_windows_powercfg_reads_actual_state(self):
        self.assertIn(win.active_guid(), win.available_guids())

    @unittest.skipUnless(os.name == "nt" and os.environ.get("FRIDAY_ALLOW_POWER_TEST") == "1",
                         "requires an isolated Windows CI runner")
    def test_real_windows_change_and_restore_when_supported(self):
        initial = win.active_guid()
        available = win.available_guids()
        mode = next((name for name, guid in win.SCHEMES.items() if guid in available and guid != initial), None)
        if mode is None:
            self.skipTest("No second built-in power plan is available")
        try:
            record = win.set_plan(mode, self.path)
            self.assertEqual(win.active_guid(), win.SCHEMES[mode])
            win.undo(record["operation_id"], self.path)
            self.assertEqual(win.active_guid(), initial)
        finally:
            if win.active_guid() != initial:
                win._run("/setactive", initial)
            self.assertEqual(win.active_guid(), initial)
