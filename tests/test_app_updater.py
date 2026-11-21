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

    def test_zip_preserves_existing_temporary_names(self):
        for name in ("main.py.jarvis-new", ".jarvis-update.tmp"):
            (self.root / name).write_bytes(b"local")
        u._apply_zip(self.root, self.files, self.sha, "main")
        for name in ("main.py.jarvis-new", ".jarvis-update.tmp"):
            self.assertEqual((self.root / name).read_bytes(), b"local")

    def test_same_second_same_size_python_update_runs_new_code(self):
        import os
        import py_compile
        import subprocess
        import sys
        import time
        module = self.root / "answer.py"
        module.write_bytes(b"result=1")
        # Exercise all common same-second write times without relying on
        # whether the test happened to start near a clock boundary.
        os.utime(module, (time.time(), int(time.time())))
        py_compile.compile(str(module), doraise=True)
        u._replace_bytes(module, b"result=2")
        out = subprocess.check_output([sys.executable, "-c", "from answer import result; print(result)"],
                                      cwd=self.root, text=True)
        self.assertEqual(out.strip(), "2")

    def test_locked_destination_does_not_block_rollback_of_earlier_files(self):
        (self.root / "main.py").write_bytes(b"old")
        original_replace = u.os.replace
        original_copy = u.shutil.copy2
        def replace(src, dst):
            if dst == self.root / "main.py":
                raise PermissionError("file locked")
            return original_replace(src, dst)
        def copy(src, dst):
            if dst == self.root / "main.py":
                raise PermissionError("file still locked")
            return original_copy(src, dst)
        with patch.object(u.os, "replace", side_effect=replace), patch.object(u.shutil, "copy2", side_effect=copy):
            with self.assertRaises(PermissionError):
                u._apply_zip(self.root, self.files, self.sha, "main")
        self.assertFalse((self.root / "gui/window.py").exists())
        self.assertEqual((self.root / "main.py").read_bytes(), b"old")

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

    def test_interrupted_read_only_phase_retries(self):
        (self.root / '.jarvis-update.lock').write_bytes(b'MAYK/1 checking')
        with patch.object(u, '_get', side_effect=[json.dumps({'sha': self.sha}).encode(), self.archive()]):
            self.assertTrue(u.update(self.root)[0])
        self.assertFalse((self.root / '.jarvis-update.lock').exists())

    def test_guard_blocks_a_second_process_and_releases_after_abrupt_exit(self):
        import subprocess
        import sys
        child = subprocess.Popen([sys.executable, '-c',
            "from core.app_updater import _update_guard; from pathlib import Path; import sys; "
            "g=_update_guard(Path(sys.argv[1])); g.__enter__(); print('ready', flush=True); sys.stdin.read()",
            str(self.root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            with self.assertRaisesRegex(RuntimeError, 'kilidi'):
                u.update(self.root)
        finally:
            child.kill()
            child.communicate()
        with u._update_guard(self.root):
            pass

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

    def test_eol_update_preserves_untracked_collision(self):
        self.git('reset', '--hard', self.new)
        personal = self.root / 'local.txt'
        personal.write_bytes(b'upstream')
        self.git('add', 'local.txt')
        self.git('commit', '-qm', 'add file')
        self.new = self.git('rev-parse', 'HEAD')
        self.git('reset', '--hard', self.old)
        personal.write_bytes(b'personal')
        (self.root / 'notes.py').write_bytes(b'a = 1\r\n')
        with self.assertRaises(RuntimeError):
            u.update(self.root)
        self.assertEqual(personal.read_bytes(), b'personal')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.old)


class InterruptedZipTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.old = {"main.py": b"old main", "gui/window.py": b"old hud",
                    "requirements.txt": b"test==1", "a-removed.py": b"old"}
        u._apply_zip(self.root, self.old, "a" * 40, "main")
        (self.root / "update_channel.json").write_text('{"branch":"main"}')
        self.private = self.root / "config/api_keys.json"
        self.private.parent.mkdir()
        self.private.write_bytes(b"local settings")

    def interrupt(self, stop_at):
        import subprocess
        import sys
        script = """
import io,json,os,sys,zipfile
from pathlib import Path
from unittest.mock import patch
from core import app_updater as u
root=Path(sys.argv[1])
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w') as z:
    for path,data in [('main.py',b'new main'),('gui/window.py',b'new hud'),
                      ('a-added.py',b'new file'),('requirements.txt',b'test==1')]:
        z.writestr('repo/'+path,data)
replace=u.os.replace
def stop(src,dst):
    replace(src,dst)
    if Path(dst)==root/sys.argv[2]:
        os._exit(79)
with patch.object(u.os,'replace',side_effect=stop), patch.object(u,'_get',side_effect=[
        json.dumps({'sha':'b'*40}).encode(),buf.getvalue()]):
    u.update(root)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.root), stop_at],
                               capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 79, child.stderr)
        self.assertTrue((self.root / ".jarvis-update.lock").exists())

    def recover(self):
        with patch.object(u, "_get", side_effect=AssertionError("recovery must be offline")):
            return u.update(self.root)

    def test_partial_update_restores_old_edited_added_and_removed_files(self):
        self.interrupt("main.py")
        self.assertTrue(self.recover()[0])
        self.assertFalse((self.root / "a-added.py").exists())
        for rel, data in self.old.items():
            self.assertEqual((self.root / rel).read_bytes(), data)
        self.assertEqual(self.private.read_bytes(), b"local settings")
        self.assertFalse((self.root / ".jarvis-update.lock").exists())

    def test_committed_update_survives_process_exit_before_unlock(self):
        self.interrupt(".jarvis-update.json")
        self.assertTrue(self.recover()[0])
        self.assertEqual((self.root / "main.py").read_bytes(), b"new main")
        self.assertFalse((self.root / "a-removed.py").exists())
        state = json.loads((self.root / ".jarvis-update.json").read_text())
        self.assertEqual(state["sha"], "b" * 40)

    def test_personal_edit_stops_recovery_before_any_files_are_changed(self):
        self.interrupt("main.py")
        (self.root / "main.py").write_bytes(b"personal edit")
        with self.assertRaisesRegex(RuntimeError, "Yerel içerik"):
            self.recover()
        self.assertEqual((self.root / "main.py").read_bytes(), b"personal edit")
        self.assertTrue((self.root / "a-added.py").exists())
        self.assertTrue((self.root / ".jarvis-update.lock").exists())

    def test_offline_command_can_be_run_twice_without_starting_the_hud(self):
        import subprocess
        import sys
        self.interrupt("main.py")
        core = self.root / "core"
        core.mkdir()
        (core / "__init__.py").touch()
        (core / "app_updater.py").write_bytes(Path(u.__file__).read_bytes())
        for message in ("Kurtarma doğrulandı", "Bekleyen ZIP kurtarması yok"):
            cmd = subprocess.run([sys.executable, "-X", "utf8", "-m", "core.app_updater", "--recover"],
                                 cwd=self.root, capture_output=True, timeout=15)
            self.assertEqual(cmd.returncode, 0, cmd.stderr)
            self.assertIn(message, cmd.stdout.decode("utf-8"))
        self.assertEqual((self.root / "main.py").read_bytes(), b"old main")

    def test_corrupt_backup_blocks_changes_and_keeps_marker(self):
        self.interrupt("main.py")
        marker = self.root / ".jarvis-update.lock"
        journal = json.loads(marker.read_bytes()[len(u._ZIP_MARKER):])
        (self.root / ".jarvis-backups" / journal["backup"] / "main.py").write_bytes(b"broken")
        with self.assertRaisesRegex(RuntimeError, "Yedek doğrulanamadı"):
            self.recover()
        self.assertTrue(marker.exists())
        self.assertEqual((self.root / "main.py").read_bytes(), b"new main")
        self.assertTrue((self.root / "a-added.py").is_file())
