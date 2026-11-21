import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core import app_updater as u


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'requirements.txt').write_text('test==1\n')
        (self.root / 'update_channel.json').write_text('{"branch":"feature/osiris-world-command"}')
        self.files = {'main.py': b'new', 'requirements.txt': b'test==1\n', 'gui/window.py': b'window'}
        self.sha = 'a' * 40

    def archive(self, extra=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            for name, data in {**self.files, **(extra or {})}.items():
                z.writestr('repo/' + name, data)
        return buf.getvalue()

    def test_zip_update_then_current(self):
        with patch.object(u, '_get', side_effect=[json.dumps({'sha': self.sha}).encode(), self.archive()]):
            self.assertTrue(u.update(self.root)[0])
        self.assertEqual((self.root / 'main.py').read_bytes(), b'new')
        with patch.object(u, '_get', return_value=json.dumps({'sha': self.sha}).encode()) as get:
            self.assertFalse(u.update(self.root)[0])
            self.assertEqual(get.call_count, 1)
        self.assertFalse((self.root / '.jarvis-update.lock').exists())

    def test_zip_check_accepts_empty_commit_message(self):
        with patch.object(u, '_get', return_value=json.dumps({'sha': self.sha, 'commit': {'message': ''}}).encode()):
            result = u.check(self.root)
        self.assertTrue(result['newer'])
        self.assertEqual(result['changes'], [])

    def test_git_fast_forward_and_backup(self):
        import subprocess
        def git(*args):
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            return subprocess.check_output(
                ['git', '-C', str(self.root), *args], text=True, creationflags=flags
            ).strip()
        git('init', '-b', 'main')
        git('config', 'user.email', 'tests@example.invalid')
        git('config', 'user.name', 'Updater tests')
        (self.root / 'main.py').write_bytes(b'old')
        git('add', '.')
        git('commit', '-m', 'old')
        old = git('rev-parse', 'HEAD')
        (self.root / 'main.py').write_bytes(b'new')
        git('commit', '-am', 'new')
        new = git('rev-parse', 'HEAD')
        git('reset', '--hard', old)
        real_git = u._git
        def local_fetch(root, *args):
            if args[0] == 'fetch':
                return real_git(root, 'fetch', '--no-tags', str(root), new)
            return real_git(root, *args)
        with patch.object(u, '_git', side_effect=local_fetch), patch.object(
                u, '_get', side_effect=AssertionError('Git update must not use the HTTP API')):
            self.assertTrue(u.update(self.root)[0])
        self.assertEqual(git('rev-parse', 'HEAD'), new)
        self.assertIn('jarvis-backup/', git('branch', '--list'))
        self.assertEqual((self.root / 'main.py').read_bytes(), b'new')

    def test_personal_data_untouched(self):
        config = self.root / 'config/api_keys.json'
        config.parent.mkdir()
        config.write_text('private')
        files = u._archive(self.archive({'config/api_keys.json': b'overwrite', 'memory/long_term.json': b'overwrite'}))
        u._apply_zip(self.root, files, self.sha, 'main')
        self.assertEqual(config.read_text(), 'private')
        self.assertNotIn('memory/long_term.json', files)

    def test_zip_updates_gitignore_but_leaves_runtime_files(self):
        runtime = {'uploads/photo.jpg': b'photo', 'reports/report.md': b'report',
                   'memory/tasks/scratch.py': b'local script'}
        files = u._archive(self.archive({**runtime, '.gitignore': b'/uploads/\n'}))
        self.assertTrue(runtime.keys().isdisjoint(files))
        u._apply_zip(self.root, files, self.sha, 'main')
        self.assertEqual((self.root / '.gitignore').read_bytes(), b'/uploads/\n')

    def test_path_traversal_rejected(self):
        with self.assertRaises(RuntimeError):
            u._archive(self.archive({'../../outside': b'bad'}))

    def test_local_edit_blocks_second_update(self):
        u._apply_zip(self.root, self.files, self.sha, 'main')
        (self.root / 'main.py').write_text('custom')
        with self.assertRaisesRegex(RuntimeError, 'Yerel değişiklik'):
            u._apply_zip(self.root, self.files, 'b' * 40, 'main')
        self.assertEqual((self.root / 'main.py').read_text(), 'custom')

    def test_new_release_file_cannot_overwrite_personal_file(self):
        u._apply_zip(self.root, self.files, self.sha, 'main')
        local = self.root / 'custom.py'
        local.write_bytes(b'personal')
        with self.assertRaisesRegex(RuntimeError, 'custom.py'):
            u._apply_zip(self.root, {**self.files, 'custom.py': b'upstream'}, 'b' * 40, 'main')
        self.assertEqual(local.read_bytes(), b'personal')
        self.assertEqual(json.loads((self.root / '.jarvis-update.json').read_text())['sha'], self.sha)

    def test_removed_tracked_file_deleted_custom_file_kept(self):
        u._apply_zip(self.root, {**self.files, 'obsolete.py': b'old'}, self.sha, 'main')
        (self.root / 'custom.py').write_text('keep')
        u._apply_zip(self.root, self.files, 'b' * 40, 'main')
        self.assertFalse((self.root / 'obsolete.py').exists())
        self.assertTrue((self.root / 'custom.py').exists())

    def test_write_failure_rolls_back(self):
        (self.root / 'main.py').write_bytes(b'original')
        real = u.os.replace
        def fail(source, target):
            if str(target).endswith('main.py'):
                raise OSError('disk failure')
            return real(source, target)
        with patch.object(u.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                u._apply_zip(self.root, self.files, self.sha, 'main')
        self.assertEqual((self.root / 'main.py').read_bytes(), b'original')
        self.assertFalse((self.root / 'gui/window.py').exists())
        self.assertFalse((self.root / '.jarvis-update.json').exists())

    def test_network_failure_unlocks(self):
        with patch.object(u, '_get', side_effect=TimeoutError('offline')):
            with self.assertRaises(TimeoutError):
                u.update(self.root)
        self.assertFalse((self.root / '.jarvis-update.lock').exists())

    def test_dependency_removal_does_not_block_zip_update(self):
        (self.root / 'requirements.txt').write_text('test==1\nold-package>=1\n')
        with patch.object(u, '_get', side_effect=[json.dumps({'sha': self.sha}).encode(), self.archive()]):
            self.assertTrue(u.update(self.root)[0])
        self.assertEqual((self.root / 'requirements.txt').read_text(), 'test==1\n')

    def test_changed_constraint_or_removed_pip_option_needs_install(self):
        self.assertTrue(u._needs_dependency_install('pkg>=1', 'pkg>=2'))
        self.assertTrue(u._needs_dependency_install('-c constraints.txt\npkg', 'pkg'))

    def test_inline_package_comments_do_not_require_reinstallation(self):
        self.assertFalse(u._needs_dependency_install('certifi>=2024  # old', 'certifi>=2024  # new'))
        self.assertTrue(u._needs_dependency_install('pkg @ https://example.org/a#sha256=1',
                                                   'pkg @ https://example.org/a#sha256=2'))

    def test_dependency_change_does_not_modify_source(self):
        self.files['requirements.txt'] = b'new-dependency==2\n'
        with patch.object(u, '_get', side_effect=[json.dumps({'sha': self.sha}).encode(), self.archive()]):
            with self.assertRaisesRegex(RuntimeError, 'bağımlılıklar'):
                u.update(self.root)
        self.assertFalse((self.root / 'main.py').exists())

    def test_lock_prevents_concurrent_update(self):
        (self.root / '.jarvis-update.lock').touch()
        with self.assertRaisesRegex(RuntimeError, 'Başka bir güncelleme'):
            u.update(self.root)
        self.assertTrue((self.root / '.jarvis-update.lock').exists())

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / 'gui').symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('symlinks not permitted')
            with self.assertRaises(RuntimeError):
                u._apply_zip(self.root, self.files, self.sha, 'main')
            self.assertFalse((Path(outside) / 'window.py').exists())


if __name__ == '__main__':
    unittest.main()


class GitLocalChangesTests(unittest.TestCase):
    """The updater on a real git checkout with local differences."""

    def setUp(self):
        import subprocess
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sp = subprocess

        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()
        self.git = git
        git('init', '-q', '-b', 'main')
        git('config', 'user.email', 'tests@example.invalid')
        git('config', 'user.name', 'Updater tests')
        git('config', 'core.autocrlf', 'false')
        (self.root / 'requirements.txt').write_text('test==1\n')
        (self.root / 'main.py').write_bytes(b'line one\nline two\n')
        (self.root / 'notes.py').write_bytes(b'a = 1\n')
        git('add', '.')
        git('commit', '-qm', 'old')
        self.old = git('rev-parse', 'HEAD')
        (self.root / 'main.py').write_bytes(b'line one\nline two\nline three\n')
        git('commit', '-qam', 'new')
        self.new = git('rev-parse', 'HEAD')
        git('reset', '-q', '--hard', self.old)
        real_git = u._git

        def local_fetch(root, *args):
            if args[0] == 'fetch':
                return real_git(root, 'fetch', '-q', '--no-tags', str(root), self.new)
            return real_git(root, *args)
        self.patch = patch.object(u, '_git', side_effect=local_fetch)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_line_ending_only_difference_does_not_block(self):
        (self.root / 'main.py').write_bytes(b'line one\r\nline two\r\n')    # Windows CRLF, same text
        (self.root / 'notes.py').write_bytes(b'a = 1\r\n')
        self.assertEqual(u._local_changes(self.root), ([], True))
        ok, msg = u.update(self.root)
        self.assertTrue(ok, msg)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.new)
        self.assertIn(b'line three', (self.root / 'main.py').read_bytes())
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=no'), '')

    def test_staged_rename_survives_update(self):
        self.git('mv', 'notes.py', 'renamed.py')
        ok, msg = u.update(self.root)
        self.assertTrue(ok, msg)
        self.assertEqual((self.root / 'renamed.py').read_bytes(), b'a = 1\n')
        self.assertFalse((self.root / 'notes.py').exists())

    def test_real_edit_is_kept_and_reapplied(self):
        (self.root / 'notes.py').write_bytes(b'a = 2  # my change\n')
        self.assertEqual(u._local_changes(self.root), (['notes.py'], False))
        ok, msg = u.update(self.root)
        self.assertTrue(ok, msg)
        self.assertIn('yeniden uygulandı', msg)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.new)
        self.assertEqual((self.root / 'notes.py').read_bytes(), b'a = 2  # my change\n')
        self.assertIn(b'line three', (self.root / 'main.py').read_bytes())
        self.assertEqual(self.git('stash', 'list'), '')

    def test_conflicting_edit_is_left_in_stash_not_lost(self):
        (self.root / 'main.py').write_bytes(b'line one\nMY VERSION\n')
        ok, msg = u.update(self.root)
        self.assertTrue(ok, msg)
        self.assertIn('stash', msg)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.new)
        self.assertIn(b'line three', (self.root / 'main.py').read_bytes())
        self.assertIn('jarvis-update', self.git('stash', 'list'))
        self.assertIn('MY VERSION', self.git('stash', 'show', '-p', 'stash@{0}'))
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=no'), '')
