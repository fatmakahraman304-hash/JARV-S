"""Open the real Qt HUD from a ZIP installation after rollback and after commit."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from core import app_updater


class UpdatedHudTests(unittest.TestCase):
    def test_zip_rollback_then_update_reopens_personalized_hud(self):
        # Read only tracked Python sources. Never copy local settings or keys.
        repo = Path(__file__).resolve().parents[1]
        paths = subprocess.check_output(
            ["git", "ls-files", "-z", "*.py"], cwd=repo
        ).decode("utf-8").split("\0")
        sources = {p: (repo / p).read_bytes() for p in paths if p and not p.startswith("tests/")}
        sources["requirements.txt"] = (repo / "requirements.txt").read_bytes()
        def archive(version):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p, data in sources.items():
                    z.writestr("repo/" + p, data)
                z.writestr("repo/acceptance_version.py", f"version={version}")
            return buf.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_bytes(sources["requirements.txt"])
            (root / "update_channel.json").write_text('{"branch":"main"}')
            cfg = root / "config/api_keys.json"
            cfg.parent.mkdir()
            cfg.write_text('{"assistant_name":"MAYK test"}')
            def update(version):
                sha = str(version) * 40
                with patch.object(app_updater, "_get", side_effect=[
                        json.dumps({"sha": sha}).encode(), archive(version)]):
                    self.assertTrue(app_updater.update(root)[0])

            def launch(version):
                script = (
                    "from acceptance_version import version\n"
                    "from ui import MaykUI\n"
                    "from PyQt6.QtCore import QTimer\n"
                    "from PyQt6.QtWidgets import QTextEdit\n"
                    "from core import confirm\n"
                    "ui = MaykUI('')\n"
                    "assert ui._win._assistant_name == 'MAYK test'\n"
                    "confirm.bind(ui.show_confirm, ui.hide_confirm)\n"
                    "detail = '<b>literal</b>' * 60\n"
                    "confirm.request('test', 'Onay', detail, lambda: 'ok')\n"
                    "ui._app.processEvents()\n"
                    "overlay = ui._win._confirm_overlay\n"
                    "assert overlay.findChild(QTextEdit).toPlainText() == detail\n"
                    "overlay.answered.emit(False)\n"
                    "assert not confirm.pending_title()\n"
                    "QTimer.singleShot(0, ui._app.quit)\n"
                    "assert ui._app.exec() == 0\n"
                    "print('HUD_READY', version)\n"
                )
                proc = subprocess.run([sys.executable, "-c", script], cwd=root,
                                      env=dict(os.environ, QT_QPA_PLATFORM="windows" if sys.platform == "win32" else "offscreen", PYTHONPATH=""),
                                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(f"HUD_READY {version}", proc.stdout)

            update(1)
            replace = os.replace
            def disk_failure(src, dst):
                if Path(dst) == root / "ui.py":
                    raise OSError("simulated write failure")
                return replace(src, dst)
            with patch.object(app_updater.os, "replace", side_effect=disk_failure):
                with self.assertRaisesRegex(OSError, "simulated"):
                    update(2)
            launch(1)
            update(2)
            launch(2)
            self.assertEqual(json.loads(cfg.read_text())["assistant_name"], "MAYK test")
