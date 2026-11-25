"""Source candidate isolation, integrity, and hostile archive regressions."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import release_package as release


class ReleasePackage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'FRIDAY test')
        self.git('config', 'user.email', 'test@example.invalid')
        for name in release.REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('committed ' + name).encode())
        self.commit()
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.archive = self.base / 'candidate.zip'

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.PIPE)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')

    def build(self):
        return release.build(self.root, self.archive)

    def rewrite(self, change):
        with zipfile.ZipFile(self.archive) as original:
            entries = [(item, original.read(item)) for item in original.infolist()]
        with zipfile.ZipFile(self.archive, 'w') as modified:
            for item, data in entries:
                modified.writestr(item, change(item.filename, data))

    def test_repeatable_archive_checksums_and_exact_commit(self):
        self.build()
        other = self.base / 'other.zip'
        release.build(self.root, other)
        self.assertEqual(self.archive.read_bytes(), other.read_bytes())
        result = release.verify(self.archive, self.sha, self.base / 'extracted')
        self.assertEqual(result['source_commit'], self.sha)
        self.assertFalse(result['full_product_ready'])
        self.assertEqual((self.base / 'extracted/LICENSE').read_bytes(), (self.root / 'LICENSE').read_bytes())
        checksum = self.archive.with_suffix('.zip.sha256').read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_working_tree_keys_memory_and_dirty_source_are_never_copied(self):
        (self.root / 'main.py').write_text('uncommitted change')
        (self.root / '.env').write_text('private local value')
        private = self.root / 'memory/long_term.json'
        private.parent.mkdir()
        private.write_text('personal memory')
        self.build()
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(archive.read('main.py'), b'committed main.py')
            self.assertNotIn('.env', archive.namelist())
            self.assertNotIn('memory/long_term.json', archive.namelist())

    def test_committed_signing_and_runtime_files_are_excluded_without_deletion(self):
        for name in ('android-receiver/app/aether-alici.jks', 'config/api_keys.json', 'memory/data.db-wal'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('sensitive fixture')
        self.commit()
        manifest = self.build()
        for name in manifest['excluded_paths']:
            self.assertTrue((self.root / name).is_file())
            self.assertNotIn(name, manifest['files'])
        self.assertEqual(len(manifest['excluded_paths']), 3)

    def test_credential_in_tracked_source_blocks_build_without_printing_value(self):
        value = 'AIza' + 'x' * 35
        (self.root / 'unsafe.py').write_text(value)
        self.commit()
        with self.assertRaises(ValueError) as error:
            self.build()
        self.assertNotIn(value, str(error.exception))
        self.assertFalse(self.archive.exists())

    def test_changed_source_is_rejected_before_extraction(self):
        self.build()
        self.rewrite(lambda name, data: b'tampered' if name == 'main.py' else data)
        target = self.base / 'extract'
        with self.assertRaises(ValueError):
            release.verify(self.archive, self.sha, target)
        self.assertFalse(target.exists())

    def test_wrong_commit_is_rejected(self):
        self.build()
        with self.assertRaises(ValueError):
            release.verify(self.archive, '0' * 40)

    def test_missing_license_or_undeclared_file_is_rejected(self):
        self.build()
        with zipfile.ZipFile(self.archive, 'a') as archive:
            archive.writestr('extra.py', b'undeclared')
        with self.assertRaises(ValueError):
            release.verify(self.archive)
        def remove_license(name, data):
            if name == release.MANIFEST:
                manifest = json.loads(data)
                del manifest['files']['LICENSE']
                return json.dumps(manifest).encode()
            return data
        self.rewrite(remove_license)
        with self.assertRaises(ValueError):
            release.verify(self.archive)

    def test_private_paths_and_windows_paths_are_rejected(self):
        for name in ('../outside', '/absolute', 'C:/drive', 'dir\\file', 'CON.txt',
                     'a/../file', 'a//file', 'file. ', 'config/api_keys.json',
                     'memory/continuity.sqlite3', 'x/private.pem', '.env.production'):
            with self.subTest(name=name):
                payload = io.BytesIO()
                with zipfile.ZipFile(payload, 'w') as archive:
                    archive.writestr(name, b'bad')
                self.archive.write_bytes(payload.getvalue())
                with self.assertRaises((ValueError, KeyError)):
                    release.verify(self.archive, destination=self.base / 'bad')
                self.assertFalse((self.base / 'bad').exists())

    def test_symlink_entry_and_case_collision_are_rejected(self):
        for symlink in (True, False):
            with zipfile.ZipFile(self.archive, 'w') as archive:
                if symlink:
                    item = zipfile.ZipInfo('link')
                    item.create_system = 3
                    item.external_attr = 0o120777 << 16
                    archive.writestr(item, '../outside')
                else:
                    archive.writestr('main.py', b'one')
                    archive.writestr('MAIN.py', b'two')
            with self.assertRaises(ValueError):
                release.verify(self.archive)

    def test_existing_installation_and_candidate_are_never_overwritten(self):
        self.build()
        before = self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.archive.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            release.verify(self.archive, destination=self.root)
        self.assertEqual((self.root / 'main.py').read_text(), 'committed main.py')

    def test_oversized_archive_is_rejected_before_read(self):
        self.build()
        with patch.object(release, 'MAX_TOTAL', 1):
            with self.assertRaises(ValueError):
                release.verify(self.archive)

    def test_missing_required_asset_blocks_build(self):
        (self.root / 'LICENSE').unlink()
        self.commit()
        with self.assertRaises(ValueError):
            self.build()


class LicenseInventory(unittest.TestCase):
    def test_installed_versions_and_license_texts_are_preserved_without_compliance_claim(self):
        from email.message import Message
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text = b'upstream copyright and license text'
            file = Path('example.dist-info/licenses/LICENSE')
            path = root / file
            path.parent.mkdir(parents=True)
            path.write_bytes(text)
            other = Path('example.dist-info/licenses/vendor/LICENSE')
            (root / other).parent.mkdir(parents=True)
            (root / other).write_bytes(b'distinct upstream license')
            metadata = Message()
            metadata['Name'] = 'example'
            metadata['License-Expression'] = 'MIT'
            distribution = SimpleNamespace(metadata=metadata, version='1.2.3', files=[file, other],
                                           locate_file=lambda value: root / value)
            with patch.object(release.importlib.metadata, 'distributions', return_value=[distribution]):
                self.assertEqual(release.inventory(root / 'inventory'), 1)
            report = json.loads((root / 'inventory/dependencies.json').read_text())
            self.assertEqual(report['compatibility_review'], 'UNVERIFIED')
            self.assertEqual(report['distributions'][0]['version'], '1.2.3')
            with zipfile.ZipFile(root / 'inventory/dependency-licenses.zip') as archive:
                self.assertEqual(archive.read('0/example.dist-info/licenses/LICENSE'), text)
                self.assertEqual(archive.read('0/example.dist-info/licenses/vendor/LICENSE'), b'distinct upstream license')
