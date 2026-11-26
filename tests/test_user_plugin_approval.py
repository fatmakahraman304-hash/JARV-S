import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import user_plugin_approval as approvals
from core.plugin_loader import discover_plugins


class UserPluginApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "user"
        self.root.mkdir()
        self.builtin = base / "builtins"
        self.marker = base / "executed"
        self.source = (
            "from pathlib import Path\n"
            "PLUGIN = {'name': 'demo', 'description': 'demo'}\n"
            f"Path({str(self.marker)!r}).touch()\n"
            "def run(parameters):\n    return 'working'\n"
        ).encode()

    def approve(self, raw=None):
        raw = self.source if raw is None else raw
        _, digest = approvals.inspect_bytes(raw)
        return approvals.approve(self.root, raw, digest, set())

    def discover(self, enabled=True, reserved=None):
        with patch("core.plugin_loader.get_plugin_enabled", return_value=enabled):
            return discover_plugins(self.builtin, reserved or set(),
                                    logger=lambda msg: None, user_plugins_dir=self.root)

    def test_unapproved_never_imports(self):
        (self.root / "demo.py").write_bytes(self.source)
        registry = self.discover()
        self.assertFalse(self.marker.exists())
        self.assertFalse(registry.has("demo"))

    def test_approval_matches_exact_bytes(self):
        self.approve()
        self.assertFalse(self.marker.exists())
        self.assertEqual(approvals.approved_source(self.root, "demo"), self.source)
        (self.root / "demo.py").write_bytes(self.source + b"# changed")
        with self.assertRaises(ValueError):
            approvals.approved_source(self.root, "demo")
        self.assertFalse(self.discover().has("demo"))
        self.assertFalse(self.marker.exists())

    def test_approved_import_and_changed_dispatch(self):
        self.approve()
        registry = self.discover()
        self.assertTrue(self.marker.exists())
        self.assertTrue(registry.has("demo"))
        with patch("core.plugin_loader.get_plugin_enabled", return_value=True):
            self.assertIn("working", registry.run("demo", {}))
            (self.root / "demo.py").write_bytes(self.source + b"# changed")
            self.assertIn("onaylanmam", registry.run("demo", {}))
            self.assertEqual(registry.get_tool_declarations(), [])

    def test_disabled_does_not_import_even_if_approved(self):
        self.approve()
        registry = self.discover(enabled=False)
        self.assertFalse(self.marker.exists())
        self.assertTrue(registry.has("demo"))
        with patch("core.plugin_loader.get_plugin_enabled", return_value=True):
            self.assertEqual(registry.get_tool_declarations(), [])
            self.assertIn("yeniden başlatma", registry.run("demo", {}))

    def test_reserved_names_block_before_import(self):
        _, digest = approvals.inspect_bytes(self.source)
        with self.assertRaises(ValueError):
            approvals.approve(self.root, self.source, digest, {"DEMO"})
        self.approve()
        self.assertFalse(self.discover(reserved={"demo"}).has("demo"))
        self.assertFalse(self.marker.exists())

    def test_rejects_mismatched_review_digest(self):
        with self.assertRaises(ValueError):
            approvals.approve(self.root, self.source, "0" * 64, set())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
