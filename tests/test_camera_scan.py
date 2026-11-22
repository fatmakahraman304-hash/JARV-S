import importlib.util
from io import BytesIO
import unittest
from unittest.mock import Mock, patch

from core import camera_scan
from plugins import camera_scan as command


class ScanCommandTests(unittest.TestCase):
    def test_explicit_command_and_negation(self):
        self.assertTrue(camera_scan.is_scan_command("AETHER, verileri aktar ve yansıt!"))
        self.assertTrue(camera_scan.is_scan_command("AETHER kamerayı tara."))
        self.assertFalse(camera_scan.is_scan_command("kamerayı tarama"))
        self.assertFalse(camera_scan.is_scan_command("verileri aktar ve yansıt diyebilir miyim"))

    def test_tool_requests_one_desktop_scan(self):
        player = Mock()
        command.run({}, player)
        player.scan_camera.assert_called_once()

    def test_busy_scan_does_not_start_another_analysis(self):
        with camera_scan._lock:
            with self.assertRaises(camera_scan.ScanBusy):
                camera_scan.analyze(b"", "Test")


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ("cv2", "PIL", "qrcode", "google.genai")),
                     "Photo, QR and model SDK dependencies required")
class PhotoScanTests(unittest.TestCase):
    def test_real_qr_is_read_when_model_cannot_reply(self):
        import qrcode

        photo = BytesIO()
        qrcode.make("https://example.org/item").save(photo, format="PNG")
        with patch.object(camera_scan.gemini, "as_json", return_value=None):
            jpeg, report = camera_scan.analyze(photo.getvalue(), "Telefon kamerası")
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        self.assertEqual(report["qr"], ["https://example.org/item"])
        self.assertTrue(report["notice"])
