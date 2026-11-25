"""Actual subprocess probes, failure evidence, source isolation and cancellation."""
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from core import feature_checks as checks


class ProbeRunner(unittest.TestCase):
    def fixture(self, code):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'core').mkdir()
        (root / 'core/__init__.py').touch()
        shutil.copy(checks.ROOT / 'core/feature_checks.py', root / 'core/feature_checks.py')
        (root / 'providers').mkdir()
        (root / 'providers/__init__.py').touch()
        (root / 'providers/schema.py').write_text(code, encoding='utf-8')
        return root

    def test_all_fixed_probes_execute_against_actual_components(self):
        for area, *_ in checks.AREAS:
            with self.subTest(area=area):
                result = checks.run_check(area, threading.Event())
                self.assertEqual(result['status'], 'passed', result)
                self.assertGreaterEqual(result['duration_ms'], 0)

    def test_private_files_environment_and_working_tree_are_isolated(self):
        root = self.fixture('''import os
from pathlib import Path
def to_openai(items):
    assert not Path('config/api_keys.json').exists()
    assert not Path('memory/long_term.json').exists()
    assert 'FRIDAY_PRIVATE_TOKEN' not in os.environ
    Path('probe-marker').write_text('temporary only')
    return [{'function': {'name': 'monitor_fixture', 'parameters': {'type': 'object'}}}]
''')
        for name in ('config/api_keys.json', 'memory/long_term.json', '.env'):
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('private sentinel')
        before = {str(file.relative_to(root)): file.read_bytes() for file in root.rglob('*') if file.is_file()}
        with patch.dict('os.environ', {'FRIDAY_PRIVATE_TOKEN': 'private sentinel'}):
            result = checks.run_check('models', threading.Event(), root=root)
        self.assertEqual(result['status'], 'passed', result)
        after = {str(file.relative_to(root)): file.read_bytes() for file in root.rglob('*') if file.is_file()}
        self.assertEqual(before, after)

    def test_reproducible_failure_is_reported_with_source_location(self):
        root = self.fixture("def to_openai(items):\n    raise AssertionError('fixture mismatch')\n")
        result = checks.run_check('models', threading.Event(), root=root)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('fixture mismatch', result['detail'])
        self.assertIn('schema.py:2', result['location'])

    def test_missing_dependency_is_not_a_pass(self):
        root = self.fixture("raise ModuleNotFoundError('synthetic dependency')\n")
        self.assertEqual(checks.run_check('models', threading.Event(), root=root)['status'], 'unverified')

    def test_timeout_terminates_the_owned_process(self):
        root = self.fixture('import time\ndef to_openai(items):\n    time.sleep(100)\n')
        with patch.object(checks, 'TIMEOUT', .2):
            result = checks.run_check('models', threading.Event(), root=root)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('zaman aşımı', result['detail'])

    def test_cancellation_never_reports_pass(self):
        stopped = threading.Event()
        stopped.set()
        result = checks.run_check('models', stopped)
        self.assertEqual(result['status'], 'cancelled')

    def test_arbitrary_probe_names_are_rejected(self):
        with self.assertRaises(ValueError):
            checks.run_check('run_shell', threading.Event())

    def test_external_network_attempt_is_blocked(self):
        root = self.fixture("import socket\ndef to_openai(items):\n    socket.create_connection(('example.com', 443))\n")
        result = checks.run_check('models', threading.Event(), root=root)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('PermissionError', result['detail'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows pythonw result-file acceptance')
    def test_pythonw_returns_a_result_without_console_stdout(self):
        interpreter = Path(sys.executable).with_name('pythonw.exe')
        self.assertTrue(interpreter.is_file())
        with patch.object(checks.sys, 'executable', str(interpreter)):
            result = checks.run_check('voice', threading.Event())
        self.assertEqual(result['status'], 'passed', result)

    def test_direct_child_entry_cannot_touch_the_actual_user_store(self):
        import json
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'FRIDAY_FEATURE_CHECK_ROOT': ''}), \
             patch.object(checks, '_memory') as memory:
            output = Path(directory) / 'result.json'
            checks._child('memory', output)
            self.assertEqual(json.loads(output.read_text())['status'], 'unverified')
            memory.assert_not_called()
