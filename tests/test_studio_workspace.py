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
