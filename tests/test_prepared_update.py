import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from core import app_updater
from tools import update_prepared_install as maintenance


class PreparedUpdate(unittest.TestCase):
    def test_target_runtime_and_resolver_proof_before_any_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target, package = root / 'target', root / 'package'
            target.mkdir()
            package.mkdir()
            channel = {'repository': app_updater.REPOSITORY, 'branch': 'main'}
            (target / 'update_channel.json').write_text(json.dumps(channel))
            for name in ('main.py', 'ui.py', 'requirements.txt'):
                (target / name).write_text('old')
            (package / 'requirements.txt').write_text('pip>=20\n')
            local = target / 'config/api_keys.json'
            local.parent.mkdir()
            local.write_bytes(b'private sentinel')
            def resolver(args, **kwargs):
                if '--report' in args:
                    Path(args[-1]).write_text(json.dumps({'install': installations}))
            def archive(requirements):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w') as out:
                    for name, data in {'main.py': b'new', 'gui/window.py': b'gui',
                                       'requirements.txt': requirements}.items():
                        out.writestr('repo/' + name, data)
                return buf.getvalue()
            with self.assertRaisesRegex(RuntimeError, 'venv'):
                maintenance.apply(target)
            with patch.object(sys, 'prefix', str(target / '.venv')), patch.object(
                    app_updater, 'ROOT', package), patch.object(maintenance.subprocess, 'run', side_effect=resolver):
                installations = [{}]
                with self.assertRaisesRegex(RuntimeError, 'hazır değil'):
                    maintenance.apply(target)
                installations = []
                remote = json.dumps({'sha': 'a' * 40}).encode()
                with patch.object(app_updater, '_get', side_effect=[remote, archive(b'pip>=21')]):
                    with self.assertRaisesRegex(RuntimeError, 'bağımlılıkları farklı'):
                        maintenance.apply(target)
                self.assertEqual((target / 'main.py').read_text(), 'old')
                with patch.object(app_updater, '_get', side_effect=[remote, archive(b'pip>=20\n')]):
                    self.assertTrue(maintenance.apply(target, progress=lambda _: None)[0])
            self.assertEqual((target / 'main.py').read_text(), 'new')
            self.assertEqual(local.read_bytes(), b'private sentinel')


def verify_installed_runtime():
    """Windows package acceptance runs this in the fully installed environment."""
    import os
    import subprocess
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory)
        # Keep the actual interpreter and installed files outside the disposable
        # target. A directory junction works without Windows Developer Mode.
        link = target / '.venv'
        if os.name == 'nt':
            subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), sys.prefix],
                           check=True)
        else:
            link.symlink_to(sys.prefix, target_is_directory=True)
        for name in ('main.py', 'ui.py', 'requirements.txt'):
            (target / name).write_bytes(b'old')
        (target / 'update_channel.json').write_text(json.dumps({
            'repository': app_updater.REPOSITORY, 'branch': 'main'}))
        private = target / 'config/personal.json'
        private.parent.mkdir()
        private.write_bytes(b'personal sentinel')
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as out:
            for name in ('main.py', 'gui/window.py', 'requirements.txt'):
                out.write(app_updater.ROOT / name, 'repo/' + name)
        remote = json.dumps({'sha': 'c' * 40}).encode()
        with patch.object(app_updater, '_get', side_effect=[remote, archive.getvalue()]):
            changed, _ = maintenance.apply(target)
        if not changed or (target / 'main.py').read_bytes() != (app_updater.ROOT / 'main.py').read_bytes():
            raise AssertionError('Prepared source update was not installed')
        app_updater.rollback_zip(target)
        if (target / 'main.py').read_bytes() != b'old' or private.read_bytes() != b'personal sentinel':
            raise AssertionError('Rollback or personal file preservation failed')


if __name__ == '__main__':
    verify_installed_runtime()
