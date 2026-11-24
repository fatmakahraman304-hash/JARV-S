import json
import tempfile
import unittest
from pathlib import Path
from core.studio_workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "studio.sqlite3"
        self.store = Workspace(self.path)

    def test_persistence_edit_and_delete(self):
        rid = self.store.save(kind="idea", title="İlk fikir", body="önce", tags="oyun", project="A")
        self.assertEqual(Workspace(self.path).list("ilk")[0]["id"], rid)
        self.store.save(kind="idea", title="İkinci", body="sonra", project="A", record_id=rid)
        self.assertEqual(self.store.versions(rid)[0]["body"], "önce")
        self.assertTrue(self.store.delete(rid))
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.store.versions(rid), [])

    def test_project_filter_and_relationships(self):
        self.store.save(kind="idea", title="A", project="P1", tags="oyun")
        self.store.save(kind="decision", title="B", project="P1", tags="tasarım")
        self.store.save(kind="source", title="C", project="P2")
        self.assertEqual(len(self.store.list(project="P1")), 2)
        nodes, edges = self.store.relationships()
        self.assertEqual(len(nodes), 3)
        self.assertEqual(len(edges), 1)

    def test_backup_import_merge_and_invalid_input(self):
        rid = self.store.save(kind="note", title="Not")
        backup = self.store.export()
        other = Workspace(Path(self.tmp.name) / "other.sqlite3")
        self.assertEqual(other.import_backup(backup), 1)
        self.assertEqual(other.import_backup(backup), 0)
        self.assertEqual(other.list()[0]["id"], rid)
        invalid = json.loads(backup)
        invalid["records"].append({"id": "bad"})
        empty = Workspace(Path(self.tmp.name) / "empty.sqlite3")
        with self.assertRaises(ValueError):
            empty.import_backup(json.dumps(invalid))
        self.assertEqual(empty.list(), [])

    def test_task_dates_priority_and_overview(self):
        self.store.save(kind="task",title="Gecikmiş",due="2026-11-23",priority="Acil",project="P")
        self.store.save(kind="task",title="Bugün",due="2026-11-24",project="P")
        done = self.store.save(kind="task",title="Tamam",stage="Tamamlandı",due="2026-11-23",project="P")
        self.store.save(kind="task",title="Başka",project="Q")
        counts, rows = self.store.task_overview(project="P",today="2026-11-24")
        self.assertEqual(counts,{"open":2,"overdue":1,"today":1,"completed":1,"archived":0})
        self.assertEqual([r["title"] for r in rows],["Gecikmiş","Bugün","Tamam"])
        self.store.save(kind="task",title="Tamam güncel",record_id=done,stage="Tamamlandı",project="P")
        self.assertEqual(self.store.versions(done)[0]["due"],"2026-11-23")
        other = Workspace(Path(self.tmp.name)/"copy.sqlite3")
        self.assertEqual(other.import_backup(self.store.export()),4)
        self.assertEqual(other.task_overview("P","2026-11-24")[0],counts)

    def test_task_validation_and_legacy_schema(self):
        import sqlite3
        self.store.save(kind="note",title="Eski kayıt")
        task = self.store.save(kind="task",title="Yeni görev",due="2026-11-30")
        from contextlib import closing
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(len(list(db.execute("PRAGMA table_info(records)"))),10)
            self.assertEqual(db.execute("SELECT count(*) FROM records").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM tasks").fetchone()[0],1)
        for due in ("2026-02-30","20261124"):
            with self.assertRaises(ValueError):
                self.store.save(kind="task",title="Hatalı",due=due)
        with self.assertRaises(ValueError):
            self.store.save(kind="note",title="Hatalı",record_id=task)
        self.assertTrue(self.store.delete(task))
        self.assertEqual(self.store.list(kind="task"),[])

    def test_restore_version_and_stale_edit_protection(self):
        rid = self.store.save(kind="task",title="İlk",body="eski",due="2026-11-30",priority="Acil")
        first = self.store.get(rid)
        self.store.save(kind="task",title="İkinci",body="yeni",record_id=rid,expected_updated=first["updated"])
        current = self.store.get(rid)
        history = self.store.versions(rid)
        self.assertEqual(history[0]["title"],"İlk")
        with self.assertRaises(ValueError):
            self.store.save(kind="task",title="Çakışma",record_id=rid,expected_updated=first["updated"])
        with self.assertRaises(ValueError):
            self.store.restore_version(rid,history[0]["version_seq"],first["updated"])
        restored = self.store.restore_version(rid,history[0]["version_seq"],current["updated"])
        self.assertEqual(restored["body"],"eski")
        self.assertEqual(restored["due"],"2026-11-30")
        self.assertEqual(restored["priority"],"Acil")
        self.assertEqual(self.store.versions(rid)[0]["body"],"yeni")
        self.assertEqual(self.store.get(rid),restored)

    def test_bounded_relationships_and_backup_limit(self):
        from unittest.mock import patch
        for i in range(4):
            self.store.save(kind="idea",title=str(i),project="P")
        nodes, edges = self.store.relationships(project="P",limit=2)
        self.assertEqual((len(nodes),len(edges)),(2,1))
        with self.assertRaises(ValueError):
            self.store.relationships(limit=201)
        with patch("core.studio_workspace.MAX_BACKUP",1):
            with self.assertRaises(ValueError):
                self.store.export()
        self.assertEqual(len(self.store.list()),4)
