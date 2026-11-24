import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
from memory import continuity as c
from memory import memory_manager as m


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = patch.object(c, 'data_dir', return_value=self.root)
        self.p.start()
        self.enterContext(patch.object(m, "BACKUP_PATH", self.root / "memory.json.bak"))
    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()
    def test_restart_and_concurrent_writes(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: c.record('Kullanıcı', f'görev {i}'), range(24)))
        self.assertEqual(len(c.recent(100)), 24)
        self.assertIn('görev', c.prompt_context())
        self.assertEqual(len(c.recent(100)), 24)  # reading is not consuming
    def test_recall_matches_reordered_turkish_terms_and_preserves_exact_lookup(self):
        c.record("Kullanıcı", "Kanatları mor olan bir tasarım istiyorum.")
        c.record("Kullanıcı", "Mor bir lamba tasarla.")
        c.record("Kullanıcı", "Bir park çiz.")
        found = c.search("MOR KANAT", limit=1)
        self.assertIn("Kanatları mor", found)
        self.assertNotIn("lamba", found)
        self.assertIn("Bir park çiz", c.search("park çiz", limit=1))
        self.assertEqual(c.search("zeplin"), "")

    def test_fact_recall_ranks_distinct_turkish_clues(self):
        facts = {"preferences": {"ışık": "Bahçede sarı",
                                 "çalışma_odası": "Mor ışıkları seviyorum",
                                 "çalışma_saatleri": "Sabah"}}
        with patch.object(m, "load_memory", return_value=facts):
            result = m.search_memory("benim ISIK calisma", limit=1)
            self.assertIn("Mor ışıkları seviyorum", result)
            self.assertNotIn("Bahçede", result)
            self.assertNotIn("Sabah", result)
            self.assertIn("Bahçede", m.search_memory("IŞIK", limit=1))
            self.assertIn("Bahçede", m.search_memory(""))
            self.assertNotIn("Bahçede", m.search_memory("benim"))

    def test_interrupted_jobs_are_not_replayed(self):
        c.set_application('CapCut', 'geliştiriliyor', 'test bekliyor')
        c.recover_jobs()
        self.assertEqual(c.applications()[0][1], 'yarıda kaldı')
    def test_migration_and_summary_survive_repeated_reads(self):
        old = self.root / 'old.json'
        old.write_text('{"notes":{"test":{"value":"hatırla"}}}', encoding='utf8')
        with patch.object(m, 'MEMORY_PATH', self.root/'new.json'), patch.object(m, '_LEGACY_MEMORY_PATH', old):
            self.assertEqual(m.load_memory()['notes']['test']['value'], 'hatırla')
            m.save_session_summary('CapCut üzerinde çalışıyorduk')
            self.assertEqual(m.pop_last_session(), m.pop_last_session())
        self.assertTrue(old.exists())

    def test_windows_console_encoding_does_not_break_save(self):
        import io
        output = io.BytesIO()
        stream = io.TextIOWrapper(output, encoding='cp1252')
        with patch.object(m, 'MEMORY_PATH', self.root/'memory.json'), patch.object(m.sys, 'stdout', stream):
            m.save_session_summary('Türkçe konuşma ve emoji 🌍')
            self.assertIn('Türkçe', m.pop_last_session()['summary'])
        stream.flush()
        self.assertTrue(output.getvalue())
        with patch.object(m, 'MEMORY_PATH', self.root/'memory.json'), patch.object(m.sys, 'stdout', None):
            m.save_session_summary('pythonw ile çalışıyor')
            self.assertEqual(m.pop_last_session()['summary'], 'pythonw ile çalışıyor')

    def test_day_history_uses_local_midnight_not_last_100(self):
        from datetime import datetime, timezone, timedelta
        tz=timezone(timedelta(hours=3))
        with c.connect() as db:
            rows=[("2026-11-23T20:59:59+00:00","Kullanıcı","previous")]
            rows += [("2026-11-23T21:00:00+00:00","Kullanıcı",f"event {i}") for i in range(120)]
            rows += [("2026-11-24T20:59:59+00:00","FRIDAY","last"),
                     ("2026-11-24T21:00:00+00:00","Kullanıcı","next")]
            db.executemany("INSERT INTO events(time,role,text) VALUES(?,?,?)",rows)
        result=c.day_history("2026-11-24",tz)
        self.assertEqual(result["total"],121)
        self.assertEqual(result["omitted"],0)
        self.assertEqual(result["rows"][0][2],"event 0")
        self.assertEqual(result["rows"][-1][2],"last")
        limited=c.day_history("2026-11-24",tz,limit=10)
        self.assertEqual(limited["omitted"],111)
        self.assertEqual(len(limited["rows"]),10)
        text_limited=c.day_history("2026-11-24",tz,max_chars=100)
        self.assertGreater(text_limited["omitted"],0)
        self.assertEqual(text_limited["rows"][-1][2],"last")
        with self.assertRaises(ValueError):
            c.day_history("2026-11-24",tz,limit=True)

    def test_history_export_protects_data_and_existing_text(self):
        c.record("Kullanıcı","Türkçe içerik")
        for target in (self.root/"continuity.sqlite3",self.root/"export.txt"):
            with self.assertRaises(ValueError):
                c.export_recent_text(target)
        with tempfile.TemporaryDirectory() as outside:
            target=Path(outside)/"history.txt"
            self.assertEqual(c.export_recent_text(target),1)
            old=target.read_text(encoding="utf-8")
            self.assertIn("Türkçe içerik",old)
            c.record("FRIDAY","yeni")
            with patch.object(c.os,"replace",side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    c.export_recent_text(target)
            self.assertEqual(target.read_text(encoding="utf-8"),old)
            self.assertEqual(list(target.parent.glob(".friday-history-*.tmp")),[])
        self.assertEqual(len(c.recent()),2)


class ApplicationTests(unittest.TestCase):
    def test_plugin_validates_without_starting(self):
        from plugins.application_learning import run
        self.assertIn('Geçersiz', run({'action':'invalid'}))
        self.assertIn('uygulama adı', run({'action':'learn', 'name':''}, player=Mock()))
    def test_failed_research_never_codes_or_releases(self):
        from core import application_learning as app
        from plugins import github_develop as gh
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target=target
            def start(self): self.target()
        with patch.object(app, 'set_application') as state, patch.object(app, 'record'), patch('actions.web_search._ddg_search', return_value=[]), patch.object(gh, 'self_release') as release, patch.object(app.threading, 'Thread', ImmediateThread):
            app.start('CapCut', 'kurgu', Mock(), True)
            release.assert_not_called()
            self.assertEqual(state.call_args.args[1], 'durduruldu')
            self.assertFalse(app._LOCK.locked())
            self.assertFalse(gh._LOCK.locked())
    def test_success_is_persisted_before_update(self):
        from core import application_learning as app
        from plugins import github_develop as gh
        events=[]
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target=target
            def start(self): self.target()
        player=Mock()
        player.request_app_update.side_effect=lambda:events.append('update')
        with patch.object(app, 'set_application', side_effect=lambda *a:events.append(a[1])), patch.object(app, 'record'), patch('actions.web_search._ddg_search', return_value=[{'href':'https://example.org/docs'}]), patch.object(gh, 'self_release', return_value='merged'), patch.object(app.threading, 'Thread', ImmediateThread):
            app.start('CapCut', 'kurgu', player, True)
        self.assertEqual(events[-1], 'update')
        self.assertIn("main'e alındı", events[-2])

if __name__ == '__main__':
    unittest.main()


class ContinuitySetupTests(unittest.TestCase):
    def test_tables_come_back_after_the_file_is_deleted(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import memory.continuity as cont
        with tempfile.TemporaryDirectory() as tmp, patch.object(cont, 'data_dir', lambda: Path(tmp)):
            cont.record('Kullanıcı', 'ilk')
            for extra in ('', '-wal', '-shm'):
                p = Path(tmp) / f'continuity.sqlite3{extra}'
                if p.exists():
                    p.unlink()
            cont.record('Kullanıcı', 'ikinci')
            self.assertEqual([r[2] for r in cont.recent()], ['ikinci'])

    def test_many_threads_write_without_losing_events(self):
        import tempfile
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        from unittest.mock import patch
        import memory.continuity as cont
        with tempfile.TemporaryDirectory() as tmp, patch.object(cont, 'data_dir', lambda: Path(tmp)):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda i: cont.record('Kullanıcı', f'olay {i}'), range(80)))
            self.assertEqual(len(cont.recent(100)), 80)


class HistoryBackupTests(unittest.TestCase):
    def test_online_backup_restores_committed_wal_and_job_state(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            backup = base / "saved" / "history.sqlite3"
            with patch.object(c, "data_dir", return_value=base / "original"):
                with c.connect() as live:
                    c.record("Kullanıcı", "İlk kayıt")
                    pid = c.project_start("test", "AETHER", "proje", "ister")
                    c.backup_history(backup)
                    c.record("Kullanıcı", "Sonraki kayıt")
                    self.assertEqual(live.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)
                with self.assertRaises(FileExistsError):
                    c.restore_history(backup)
            with patch.object(c, "data_dir", return_value=base / "restored"):
                c.restore_history(backup)
                self.assertEqual([r[2] for r in c.recent()], ["İlk kayıt"])
                self.assertEqual(c.project(pid)["title"], "AETHER")
                c.record("Kullanıcı", "Geri dönüşten sonra")
                self.assertEqual(len(c.recent()), 2)

    def test_invalid_backup_or_leftover_wal_never_publishes_a_database(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder, patch.object(c, "data_dir", return_value=Path(folder)):
            base = Path(folder)
            bad = base / "bad.db"
            bad.write_bytes(b"not sqlite")
            with self.assertRaises(sqlite3.Error):
                c.restore_history(bad)
            target = base / "continuity.sqlite3"
            self.assertFalse(target.exists())
            wal = base / "continuity.sqlite3-wal"
            wal.write_bytes(b"pending")
            with self.assertRaises(FileExistsError):
                c.restore_history(bad)
            self.assertEqual(wal.read_bytes(), b"pending")
            self.assertFalse(target.exists())
