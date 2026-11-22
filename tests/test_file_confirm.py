"""File deletion requires a HUD decision bound to the displayed target."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from actions import file_controller as files
from core import confirm


class FileConfirmation(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.target = folder / "note.txt"
        self.target.write_text("original")
        self.banner = Mock()
        self.finished = threading.Event()
        self.trash = Mock(side_effect=lambda target: target.unlink() or "Moved to Trash")
        self.enterContext(patch.object(files, "_SAFE_ROOTS", [folder]))
        self.enterContext(patch.object(files, "_safe_trash", self.trash))
        self.enterContext(patch.object(files, "push_undo"))
        self.enterContext(patch.object(confirm, "_pending", None))
        self.enterContext(patch.object(confirm, "_show_cb", self.banner))
        self.enterContext(patch.object(confirm, "_log_cb",
            lambda msg: self.finished.set() if "Awaiting" not in msg else None))

    def request(self):
        result = files.file_controller({"action": "delete", "path": str(self.target), "confirmed": True})
        self.assertIn("CONFIRMATION_PENDING", result)
        self.assertTrue(self.target.exists())
        _, detail, token = self.banner.call_args.args
        self.assertEqual(detail, str(self.target))
        return token

    def test_only_matching_acceptance_moves_file(self):
        token = self.request()
        confirm.resolve(True, "stale")
        self.trash.assert_not_called()
        confirm.resolve(True, token)
        self.assertTrue(self.finished.wait(2))
        self.assertFalse(self.target.exists())
        self.trash.assert_called_once_with(self.target)

    def test_cancel_keeps_file(self):
        confirm.resolve(False, self.request())
        self.trash.assert_not_called()
        self.assertTrue(self.target.exists())

    def test_replaced_target_is_preserved(self):
        token = self.request()
        self.target.rename(self.target.with_suffix(".previous"))
        self.target.write_text("replacement")
        confirm.resolve(True, token)
        self.assertTrue(self.finished.wait(2))
        self.trash.assert_not_called()
        self.assertEqual(self.target.read_text(), "replacement")
