"""Process supervisor integration tests for Code Agent background commands."""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from core import agent_process, jarvis_agent


class AgentProcessTests(unittest.TestCase):
    def tearDown(self):
        jarvis_agent.reset_cancel()

    def test_running_python_test_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "slow.py").write_text("import time\ntime.sleep(15)\n")
            ws = jarvis_agent.Workspace(root, log=lambda _: None)
            timer = threading.Timer(.30, jarvis_agent.request_cancel)
            started = time.monotonic()
            timer.start()
            try:
                with self.assertRaises(jarvis_agent.AgentCancelled):
                    ws.t_run("python slow.py", timeout=25)
            finally:
                timer.join(timeout=2)
            self.assertLess(time.monotonic() - started, 6.0)
            self.assertFalse(ws.test_passed)

    def test_timeout_stops_background_test_process(self):
        with tempfile.TemporaryDirectory() as temp:
            started = time.monotonic()
            with self.assertRaises(agent_process.CommandTimedOut):
                agent_process.execute(
                    [sys.executable, "-c", "import time;time.sleep(10)"],
                    Path(temp), timeout=.35, cancel_check=lambda: None,
                )
            self.assertLess(time.monotonic() - started, 5.0)

    def test_large_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(agent_process.CommandOutputLimit):
                agent_process.execute(
                    [sys.executable, "-c", "print('x'*4000000)"],
                    Path(temp), timeout=10, cancel_check=lambda: None,
                )

    def test_command_output_does_not_require_unbounded_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            code, out, err = agent_process.execute(
                [sys.executable, "-c", "print('x'*20000);print('PASS')"],
                Path(temp), timeout=10, cancel_check=lambda: None,
            )
            self.assertEqual(code, 0)
            self.assertTrue(out.endswith("PASS\n"))
            self.assertLessEqual(len(out), agent_process.MAX_CAPTURE)
            self.assertEqual(err, "")

    @unittest.skipIf(os.name == "nt", "Nested child termination checked on Windows acceptance separately")
    def test_cancel_kills_child_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "child-still-running"
            (root / "child.py").write_text(
                "import time\nfrom pathlib import Path\n"
                "time.sleep(1.5)\nPath('child-still-running').write_text('leak')\n"
            )
            (root / "parent.py").write_text(
                "import subprocess,sys,time\n"
                "subprocess.Popen([sys.executable,'child.py'])\n"
                "time.sleep(15)\n"
            )
            timer = threading.Timer(.3, jarvis_agent.request_cancel)
            timer.start()
            try:
                with self.assertRaises(jarvis_agent.AgentCancelled):
                    agent_process.execute(
                        [sys.executable, "parent.py"], root, timeout=20,
                        cancel_check=jarvis_agent._check_cancel,
                    )
            finally:
                timer.join(timeout=2)
            time.sleep(1.7)
            self.assertFalse(marker.exists(), "A subprocess escaped the cancelled test job")


if __name__ == "__main__":
    unittest.main()
