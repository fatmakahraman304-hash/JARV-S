"""First in-place update of a verified source package, including live SQLite."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core import app_updater as updater
from tools import release_package as release


class PackageFirstUpdate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        repo = base / "repo"
        repo.mkdir()

        def git(*args):
            return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

        git("init", "-q")
        git("config", "user.email", "tests@example.invalid")
        git("config", "user.name", "FRIDAY tests")
        self.files = {name: ("old " + name).encode() for name in release.REQUIRED}
        self.files.update({"gui/window.py": b"old window",
                           "requirements.txt": b"pip>=20\n",
                           "update_channel.json": json.dumps({
                               "repository": updater.REPOSITORY, "branch": "main"}).encode(),
                           "obsolete.py": b"old obsolete"})
        for name, data in self.files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        git("add", ".")
        git("commit", "-qm", "source fixture")
        self.sha = git("rev-parse", "HEAD")
        archive = base / "source.zip"
        release.build(repo, archive)
        self.root = base / "installed"
        release.verify(archive, self.sha, self.root)
        self.next_sha = "a" * 40
        self.next_files = {**self.files, "main.py": b"new main", "new_module.py": b"upstream"}
        del self.next_files["obsolete.py"]

    def update(self, extra=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name, data in {**self.next_files, **(extra or {})}.items():
                archive.writestr("repo/" + name, data)
        with patch.object(updater, "_get", side_effect=[
                json.dumps({"sha": self.next_sha}).encode(), buf.getvalue()]), patch.object(
                updater, "_publisher_files", return_value=None):
            return updater.update(self.root)

    def test_first_update_recognizes_installed_commit(self):
        with patch.object(updater, "_get", return_value=json.dumps({"sha": self.sha}).encode()) as get:
            self.assertFalse(updater.check(self.root)["newer"])
            self.assertFalse(updater.update(self.root)[0])
            self.assertEqual(get.call_count, 2)
        self.assertFalse((self.root / ".aether-update.json").exists())

    def test_first_update_rejects_edited_source_and_untracked_collision(self):
        main = self.root / "main.py"
        main.write_bytes(b"personal edit")
        with self.assertRaisesRegex(RuntimeError, "Yerel değişiklik"):
            self.update()
        self.assertEqual(main.read_bytes(), b"personal edit")
        main.write_bytes(self.files["main.py"])
        collision = self.root / "new_module.py"
        collision.write_bytes(b"personal module")
        with self.assertRaisesRegex(RuntimeError, "çakışıyor"):
            self.update()
        self.assertEqual(collision.read_bytes(), b"personal module")
        self.assertFalse((self.root / ".aether-update.json").exists())
        self.assertFalse((self.root / ".aether-backups").exists())

    def test_first_update_and_rollback_preserve_database_and_config(self):
        config = self.root / "config" / "api_keys.json"
        config.parent.mkdir(exist_ok=True)
        config.write_bytes(b"private sentinel")
        db = self.root / "history.sqlite3"
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE events (message TEXT)")
            conn.execute("INSERT INTO events VALUES ('remember me')")
            conn.commit()
            wal = self.root / "history.sqlite3-wal"
            original = wal.read_bytes()
            self.assertTrue(self.update({"history.sqlite3-wal": b"foreign bytes",
                                         "config/api_keys.json": b"foreign settings"})[0])
            self.assertEqual(wal.read_bytes(), original)
            self.assertEqual(config.read_bytes(), b"private sentinel")
            self.assertFalse((self.root / "obsolete.py").exists())
            updater.rollback_zip(self.root, progress=lambda _: None)
            self.assertEqual(wal.read_bytes(), original)
            self.assertEqual(config.read_bytes(), b"private sentinel")
            self.assertEqual((self.root / "main.py").read_bytes(), self.files["main.py"])
            self.assertEqual((self.root / "obsolete.py").read_bytes(), b"old obsolete")
            self.assertFalse((self.root / "new_module.py").exists())
            self.assertEqual(updater._zip_state(self.root)["sha"], self.sha)
        with closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone(), ("ok",))
            self.assertEqual(conn.execute("SELECT message FROM events").fetchone(), ("remember me",))

    def test_invalid_initial_inventory_fails_before_download_or_write(self):
        (self.root / release.MANIFEST).write_text('{"schema":1,"files":{}}')
        with patch.object(updater, "_get") as get:
            with self.assertRaisesRegex(RuntimeError, "başlangıç dosya listesi"):
                updater.update(self.root)
            get.assert_not_called()
        self.assertEqual((self.root / "main.py").read_bytes(), self.files["main.py"])
        self.assertFalse((self.root / ".aether-backups").exists())
