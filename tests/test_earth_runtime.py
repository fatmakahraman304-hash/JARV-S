"""Exercise the shipped JavaScript rather than checking source substrings."""
import shutil
import subprocess
import unittest
from pathlib import Path


class EarthRuntime(unittest.TestCase):
    def test_visibility_and_replaced_layer_requests(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required by the documented regression environment")
        result = subprocess.run([node, "--test", str(Path(__file__).with_name("earth_runtime.cjs"))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
