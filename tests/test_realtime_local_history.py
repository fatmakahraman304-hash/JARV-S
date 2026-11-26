import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from memory import continuity as c


class RealtimeLocalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch.object(c, "data_dir", return_value=self.root))

    def test_separate_journal_survives_restart_and_is_excluded_from_shared_prompt(self):
        c.record("Kullanıcı", "shared example")
        c.record_realtime("Kullanıcı", "private example 50%")
        c.record_realtime("FRIDAY", "private response")
        c._ready.discard(str((self.root / "continuity.sqlite3").resolve()))
        self.assertIn("private example", c.realtime_history())
        self.assertIn("private response", c.realtime_history())
        self.assertNotIn("private", c.prompt_context())
        self.assertNotIn("private", c.search("private"))
        self.assertEqual(len(c.recent()), 1)

    def test_query_is_literal_and_bounded(self):
        c.record_realtime("Kullanıcı", "a 50% value")
        c.record_realtime("Kullanıcı", "a 500 value")
        c.record_realtime("FRIDAY", "literal _ symbol")
        self.assertIn("50% value", c.realtime_history("50%"))
        self.assertNotIn("500", c.realtime_history("50%"))
        self.assertIn("literal _", c.realtime_history("_"))
        self.assertNotIn("50%", c.realtime_history("_"))
        self.assertIn("kayıt bulunamadı", c.realtime_history("' OR 1=1 --"))
        with self.assertRaises(ValueError):
            c.record_realtime("system", "bad role")

    def test_existing_database_migrates_without_losing_rows(self):
        path = self.root / "continuity.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, time TEXT, role TEXT, text TEXT)")
            db.execute("INSERT INTO events(time,role,text) VALUES(?,?,?)",
                       ("2026-11-26T12:00:00", "Kullanıcı", "old history"))
        c.record_realtime("FRIDAY", "new history")
        self.assertIn("old history", c.resume_text())
        self.assertIn("new history", c.realtime_history())

    def test_backup_includes_both_journals(self):
        c.record("Kullanıcı", "shared")
        c.record_realtime("FRIDAY", "separate")
        backup = c.backup_history(self.root / "backup.sqlite3")
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute("SELECT text FROM events").fetchone()[0], "shared")
            self.assertEqual(db.execute("SELECT text FROM realtime_events").fetchone()[0], "separate")

    def test_old_backup_restore_reinitializes_schema(self):
        c.record("Kullanıcı", "existing")
        old = c.backup_history(self.root / "old.sqlite3")
        with sqlite3.connect(old) as db:
            db.execute("DROP TABLE realtime_events")
        target_dir = self.root / "restored"
        with patch.object(c, "data_dir", return_value=target_dir):
            target = target_dir / "continuity.sqlite3"
            c._ready.add(str(target.resolve()))
            c.restore_history(old)
            c.record_realtime("FRIDAY", "after restore")
            self.assertIn("existing", c.resume_text())
            self.assertIn("after restore", c.realtime_history())


class RealtimeMainHistoryTests(unittest.TestCase):
    def test_realtime_turn_does_not_use_shared_learner_or_sync(self):
        from tests._main_import import load_main
        main = load_main()
        instance = SimpleNamespace(_session_realtime=True, ui=Mock())
        with patch("memory.continuity.record_realtime") as separate, patch(
                "memory.continuity.record") as shared, patch(
                "memory.learner.turn") as learner, patch("core.sync_hub.note_turn") as sync:
            main.FridayLive._persist_turn(instance, "FRIDAY", "example")
            separate.assert_called_once_with("FRIDAY", "example")
            shared.assert_not_called()
            learner.assert_not_called()
            sync.assert_not_called()

    def test_local_recall_command_never_reaches_session(self):
        from tests._main_import import load_main
        main = load_main()
        instance = SimpleNamespace(_session_realtime=True, _engine_mode=lambda: "realtime",
                                   ui=Mock(), session=Mock())
        with patch("memory.continuity.realtime_history", return_value="local result") as history:
            main.FridayLive._on_text_command(instance, "/realtime-hafiza proje")
            history.assert_called_once_with("proje")
            instance.ui.show_content.assert_called_once_with(
                "Realtime — Yerel konuşma geçmişi", "local result")
            instance.session.send_client_content.assert_not_called()
