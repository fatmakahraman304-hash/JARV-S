import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from plugins import blender_studio as studio


class BlenderDiscovery(unittest.TestCase):
    def test_running_blender_and_launcher_in_portable_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Blender Portable 5.3"
            folder.mkdir()
            binary = folder / "blender.exe"
            binary.touch()
            for name in ("blender-launcher.exe", "blender.exe"):
                process = Mock(info={"name": name, "exe": str(folder / name)})
                with patch("psutil.process_iter", return_value=[process]):
                    self.assertEqual(next(studio.windows_candidates()), binary)

    def test_missing_binary_is_returned_directly_without_launching_worker(self):
        with patch.object(studio, "executable", side_effect=ValueError("Blender bulunamadı")), \
             patch.object(studio.threading, "Thread") as worker:
            result = studio.run({"action": "new", "request": "Ev yap"})
            self.assertIn("başlamadı", result)
            self.assertEqual(studio.run({"action": "status"}), result)
            worker.assert_not_called()

    def test_late_failure_reaches_voice_and_status(self):
        spoken = threading.Event()
        player = Mock()
        player.request_say.side_effect = lambda message: spoken.set()
        with patch.object(studio, "executable", return_value="blender"), \
             patch.object(studio, "process", side_effect=ValueError("Kamera yok")):
            studio.run({"action": "render"}, player)
            self.assertTrue(spoken.wait(3))
            self.assertIn("Kamera yok", studio.run({"action": "status"}))
            self.assertIn("Kamera yok", player.request_say.call_args.args[0])
