"""Failed installs must never be reported as a ready runtime."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from core import installer


class InstallerResults(unittest.TestCase):
    def run_install(self, available, pip=True, processes=None):
        logs = []
        with patch.object(installer, '_CORE', [('example', 'example')]), \
             patch.object(installer, '_STT', {}), patch.object(installer, '_TTS', {}), \
             patch.object(installer.platform, 'system', return_value='Linux'), \
             patch.object(installer, '_available', side_effect=available), \
             patch.object(installer, '_pip', return_value=pip), \
             patch.object(installer.subprocess, 'run', side_effect=processes) as run:
            result = installer.install_for_config({}, logs.append)
        return result, logs, run

    def test_failed_pip_returns_false_without_a_success_message(self):
        result, logs, _ = self.run_install(lambda name: name == 'playwright', pip=False,
                                         processes=lambda *a, **k: SimpleNamespace(returncode=0))
        self.assertFalse(result)
        self.assertFalse(any(line.startswith('SYS:') and ('ready' in line or 'already installed' in line) for line in logs))

    def test_pip_zero_exit_without_the_module_is_not_success(self):
        result, logs, _ = self.run_install(lambda name: name == 'playwright',
                                         processes=lambda *a, **k: SimpleNamespace(returncode=0))
        self.assertFalse(result)
        self.assertTrue(any('example' in line and 'ERR:' in line for line in logs))

    def test_failed_browser_download_is_not_ready(self):
        seen = set()
        def available(name):
            if name == 'example': return True
            if name in seen: return True
            seen.add(name)
            return False
        result, logs, _ = self.run_install(available, processes=lambda *a, **k: SimpleNamespace(returncode=1, stderr=b'download failed'))
        self.assertFalse(result)
        self.assertFalse(any(line.startswith('SYS:') and 'ready' in line for line in logs))

    def test_existing_package_with_missing_browsers_is_not_ready(self):
        result, logs, _ = self.run_install(lambda name: True, processes=lambda *a, **k: SimpleNamespace(returncode=1, stderr=b'missing executable'))
        self.assertFalse(result)
        self.assertFalse(any(line.startswith('SYS:') and ('ready' in line or 'already installed' in line) for line in logs))

    def test_process_timeout_is_reported_and_does_not_raise(self):
        result, logs, _ = self.run_install(lambda name: True,
            processes=installer.subprocess.TimeoutExpired('browser probe', 60))
        self.assertFalse(result)
        self.assertTrue(any('ERR:' in line for line in logs))

    def test_ready_only_after_packages_and_real_browser_probe(self):
        result, logs, run = self.run_install(lambda name: True, processes=lambda *a, **k: SimpleNamespace(returncode=0))
        self.assertTrue(result)
        self.assertTrue(any(line.startswith('SYS:') and 'ready' in line for line in logs))
        self.assertIn('launch', run.call_args.args[0][-1])
        self.assertIn('firefox', run.call_args.args[0][-1])


class PipDeadline(unittest.TestCase):
    def test_pip_timeout_returns_failure_with_a_log(self):
        logs = []
        with patch.object(installer.subprocess, 'run',
                          side_effect=installer.subprocess.TimeoutExpired('pip', 300)) as run:
            self.assertFalse(installer._pip('pillow', logs.append))
        self.assertEqual(run.call_args.kwargs['timeout'], 300)
        self.assertTrue(any('ERR:' in line for line in logs))
