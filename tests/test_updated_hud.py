"""Open the real Qt HUD from a ZIP installation after rollback and after commit."""
import io
import hashlib
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
    def test_restart_failure_enables_retry_without_reinstalling(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from gui.window import MainWindow
        window = SimpleNamespace(_update_btn=Mock(), _log=Mock())
        window._restart_after_update = lambda: MainWindow._restart_after_update(window)
        with patch('core.restart_manager.schedule_restart', side_effect=[OSError('busy'), None]) as restart, patch(
                'PyQt6.QtWidgets.QMessageBox.warning'), patch('PyQt6.QtWidgets.QApplication.instance') as app:
            window._restart_after_update()
            window._update_btn.setEnabled.assert_called_with(True)
            MainWindow._start_update(window)
            self.assertEqual(restart.call_count, 2)
            app.return_value.quit.assert_called_once()
            self.assertFalse(window._retry_update_restart)

    def test_zip_rollback_then_update_reopens_personalized_hud(self):
        # Read only tracked/manifested Python sources. A release installation
        # has no Git metadata, and must not accidentally use a parent checkout
        # or sweep its .venv / runtime files into the simulated update.
        repo = Path(__file__).resolve().parents[1]
        from tools.release_package import MANIFEST, safe_name, private_path
        manifest_path = repo / MANIFEST
        if manifest_path.is_file():
            declared = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]
            paths = [name for name in declared if name.endswith(".py")]
            for name in paths:
                self.assertTrue(safe_name(name) and not private_path(name))
                data = (repo / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), declared[name]["sha256"])
                self.assertEqual(len(data), declared[name]["bytes"])
        else:
            paths = subprocess.check_output(
                ["git", "ls-files", "-z", "*.py"], cwd=repo
            ).decode("utf-8").split("\0")
        sources = {p: (repo / p).read_bytes() for p in paths if p and not p.startswith("tests/")}
        self.assertTrue({"main.py", "ui.py", "gui/window.py"} <= sources.keys())
        sources["requirements.txt"] = (repo / "requirements.txt").read_bytes()
        def archive(version):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for p, data in sources.items():
                    if version == 3 and p == "main.py":
                        data = b"raise SystemExit(23)"
                    z.writestr("repo/" + p, data)
                z.writestr("repo/acceptance_version.py", f"version={version}")
            return buf.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_bytes(sources["requirements.txt"])
            (root / "update_channel.json").write_text('{"branch":"main"}')
            cfg = root / "config/api_keys.json"
            cfg.parent.mkdir()
            cfg.write_text('{"assistant_name":"FRIDAY test"}')
            def update(version):
                sha = str(version) * 40
                with patch.object(app_updater, "_get", side_effect=[
                        json.dumps({"sha": sha}).encode(), archive(version)]):
                    self.assertTrue(app_updater.update(root)[0])

            def launch(version):
                script = (
                    "from acceptance_version import version\n"
                    "from ui import FridayUI\n"
                    "import os\n"
                    "from pathlib import Path\n"
                    "receipt = Path('hud-ready')\n"
                    "os.environ['AETHER_RESTART_RECEIPT'] = str(receipt.resolve())\n"
                    "from PyQt6.QtCore import QTimer\n"
                    "from PyQt6.QtWidgets import QTextEdit\n"
                    "from core import confirm\n"
                    "ui = FridayUI('')\n"
                    "assert ui._win._assistant_name == 'FRIDAY'\n"
                    "confirm.bind(ui.show_confirm, ui.hide_confirm)\n"
                    "detail = '<b>literal</b>' * 60\n"
                    "confirm.request('test', 'Onay', detail, lambda: 'ok')\n"
                    "ui._app.processEvents()\n"
                    "assert receipt.is_file()\n"
                    "receipt.unlink()\n"
                    "overlay = ui._win._confirm_overlay\n"
                    "assert overlay.findChild(QTextEdit).toPlainText() == detail\n"
                    "overlay.answered.emit(False)\n"
                    "assert not confirm.pending_title()\n"
                    "from unittest.mock import patch\n"
                    "from threading import Event\n"
                    "entered, release = Event(), Event()\n"
                    "def hold_update(**kwargs):\n"
                    "    entered.set()\n"
                    "    release.wait(5)\n"
                    "    return False, 'test'\n"
                    "with patch('core.app_updater.update', side_effect=hold_update):\n"
                    "    ui._win._start_update()\n"
                    "    assert entered.wait(2)\n"
                    "    assert ui._win._update_worker.is_alive()\n"
                    "    QTimer.singleShot(0, ui._app.quit)\n"
                    "    assert ui._app.exec() == 0\n"
                    "    release.set()\n"
                    "    ui._win._update_worker.join(5)\n"
                    "    assert not ui._win._update_worker.is_alive()\n"
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
            update(3)
            previous = subprocess.Popen([sys.executable, "-c", "pass"])
            previous.wait(timeout=10)
            restart = subprocess.run([sys.executable, "-X", "utf8", str(root / "tools/restart_app.py"),
                                      str(previous.pid), str(root)], cwd=root, capture_output=True,
                                     timeout=30, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            self.assertEqual(restart.returncode, 1, restart.stderr)
            self.assertIn("kod 23", restart.stdout)
            rollback = subprocess.run([sys.executable, "-m", "core.app_updater", "--rollback"],
                                      cwd=root, capture_output=True, timeout=30,
                                      env=dict(os.environ, PYTHONIOENCODING="cp1252:strict"))
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertIn("doğrulandı", rollback.stdout.decode("utf-8"))
            launch(2)
            app_updater.rollback_zip(root)
            launch(1)
            self.assertEqual(json.loads((root / ".aether-update.json").read_text())["sha"], "1" * 40)
            self.assertEqual(json.loads(cfg.read_text())["assistant_name"], "FRIDAY test")
