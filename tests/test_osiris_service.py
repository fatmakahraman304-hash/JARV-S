"""Service lifecycle checks; no network, node or external processes required."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import subprocess
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import start_with_osiris as service


class ServiceTests(unittest.TestCase):
    def test_unresponsive_owned_server_is_restarted_after_three_checks(self):
        class Process:
            def __init__(self):
                self.returncode = None
                self.terminated = False
            def poll(self):
                return self.returncode
            def terminate(self):
                self.terminated = True
                self.returncode = 0
            def wait(self, timeout=None):
                return self.returncode

        first, restarted = Process(), Process()
        jarvis = Mock()
        jarvis.poll.side_effect = [None] * 6 + [0, 0]
        now = [0]
        def clock():
            now[0] += 16
            return now[0]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'node_modules/next/dist/bin').mkdir(parents=True)
            (root / 'node_modules/next/dist/bin/next').touch()
            (root / '.next').mkdir()
            (root / '.next/BUILD_ID').touch()
            (root / '.next/jarvis-build.json').write_text('{"fingerprint":"test"}')
            with patch.object(sys, 'argv', ['start_with_osiris.py', directory]), \
                    patch.object(service, 'prepare'), patch.object(service, 'fingerprint', return_value='test'), \
                    patch.object(service.shutil, 'which', return_value='node'), \
                    patch.object(service.subprocess, 'check_output', return_value='v24.0.0'), \
                    patch.object(service.socket, 'socket'), patch.dict(service.os.environ, {'LOCALAPPDATA': directory}), \
                    patch.object(service.subprocess, 'Popen', side_effect=[first, jarvis, restarted]) as launch, \
                    patch.object(service, 'wait_ready') as ready, \
                    patch.object(service, 'health_ok', side_effect=[False, False, False, True, True, True]), \
                    patch.object(service.time, 'monotonic', side_effect=clock), patch.object(service.time, 'sleep'):
                service.main()
            self.assertTrue(first.terminated)
            self.assertEqual(launch.call_count, 3)
            self.assertEqual(ready.call_count, 2)
            self.assertIn('failed three health checks', (root / 'Jarvis/logs/osiris.log').read_text())

    def test_stopped_process_is_not_reported_ready(self):
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            service.wait_ready(process, "http://127.0.0.1:3010/", timeout=.1)

    def test_exact_health_payload_required(self):
        process = Mock()
        process.poll.return_value = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"jarvis_bridge":1}'
        opener = Mock()
        opener.open.return_value = response
        with patch.object(service, "build_opener", return_value=opener):
            service.wait_ready(process, "http://127.0.0.1:3010/", timeout=.1)
        response.read.assert_called_once_with(1024)

    def test_foreign_health_payload_times_out(self):
        process = Mock()
        process.poll.return_value = None
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"other_service":true}'
        opener = Mock()
        opener.open.return_value = response
        with patch.object(service, "build_opener", return_value=opener), patch.object(service.time,"sleep"):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                service.wait_ready(process,"http://127.0.0.1:3010/",timeout=.01)

    def test_completed_process_is_not_terminated(self):
        process=Mock()
        process.poll.return_value=0
        service.stop_owned(process)
        process.terminate.assert_not_called()

    def test_owned_stuck_process_is_killed_after_timeout(self):
        process=Mock()
        process.poll.return_value=None
        process.wait.side_effect=[subprocess.TimeoutExpired("node",8),0]
        service.stop_owned(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
