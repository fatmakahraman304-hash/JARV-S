import hashlib
import tempfile
import unittest
from pathlib import Path

from plugins import plugin_review


class PluginReviewTests(unittest.TestCase):
    def test_metadata_and_digest(self):
        source = b"PLUGIN = {'name': 'test'}\ndef run(parameters):\n    return 'ok'\n"
        report = plugin_review.inspect_source(source)
        self.assertTrue(report["plugin_dict"])
        self.assertTrue(report["run_function"])
        self.assertEqual(report["sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(report["flags"], [])

    def test_flags_and_relative_dependencies(self):
        report = plugin_review.inspect_source(
            b"import requests, subprocess\nfrom . import _helper\nexec('pass')\n")
        for expected in ("Ağ erişimi", "Sistem veya süreç erişimi",
                         "Dinamik kod yürütme", "Bağımlı eklenti dosyaları ayrıca incelenmeli"):
            self.assertIn(expected, report["flags"])

    def test_review_does_not_execute_or_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            marker = folder / "executed"
            plugin = folder / "demo.py"
            source = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            plugin.write_text(source, encoding="utf-8")
            result = plugin_review.run({"path": str(plugin)})
            self.assertIn("SHA-256:", result)
            self.assertIn("güvenlik garantisi", result)
            self.assertFalse(marker.exists())
            self.assertEqual(plugin.read_text(encoding="utf-8"), source)

    def test_refuses_oversize_and_invalid_syntax(self):
        with self.assertRaises(ValueError):
            plugin_review.inspect_source(b" " * (plugin_review.MAX_BYTES + 1))
        with self.assertRaises(SyntaxError):
            plugin_review.inspect_source(b"def :")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.py"
            path.write_text("SECRET_TOKEN = !", encoding="utf-8")
            result = plugin_review.run({"path": str(path)})
            self.assertIn("SyntaxError", result)
            self.assertNotIn("SECRET_TOKEN", result)

    def test_refuses_non_python_and_relative_paths(self):
        self.assertIn("Tam yerel dosya", plugin_review.run({"path": "plugin.py"}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.txt"
            path.write_text("not code", encoding="utf-8")
            self.assertIn("Normal bir yerel", plugin_review.run({"path": str(path)}))


if __name__ == "__main__":
    unittest.main()
