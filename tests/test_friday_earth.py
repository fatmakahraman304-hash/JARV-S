"""Requested identity upgrade and bounded Earth input/resource permissions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QUrl
from gui.earth_panel import EARTH_ROOT, allowed_resource, destination
from memory import config_manager as cfg

ROOT = Path(__file__).resolve().parent.parent


class FridayEarth(unittest.TestCase):
    def test_voice_and_name_upgrade_preserves_secrets_and_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "api_keys.json"
            data = {"assistant_name":"FRIDAY", "voice_name":"Charon", "user_name":"Murat",
                    "gemini_api_key":"local-test", "providers":{"mode":"pipeline"},
                    "whatsapp_assistant":{"messages_enabled":True,"secret":"saved-locally"}}
            file.write_text(json.dumps(data))
            with patch.object(cfg, "CONFIG_FILE", file):
                self.assertEqual(cfg.get_assistant_name(), "FRIDAY")
                self.assertEqual(cfg.get_voice(), "Aoede")
                self.assertEqual(cfg.get_user_name(), "Murat")
                self.assertEqual(cfg.get_gemini_key(), "local-test")
                self.assertEqual(cfg.get_provider_mode(), "pipeline")
            self.assertEqual(json.loads(file.read_text(encoding="utf-8")), data)

    def test_earth_resource_boundary(self):
        for url in ("https://cesium.com/a.js", "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/1/0/0",
                    QUrl.fromLocalFile(str(EARTH_ROOT / "earth.js")).toString()):
            self.assertTrue(allowed_resource(QUrl(url)), url)
        for url in ("https://cesium.com.evil.test/a", "http://cesium.com/a", "https://cesium.com:8443/a",
                    "https://user@cesium.com/a", "http://127.0.0.1:8769/", "file:///etc/passwd",
                    QUrl.fromLocalFile(str(ROOT / "config/api_keys.json")).toString()):
            self.assertFalse(allowed_resource(QUrl(url)), url)

    def test_destinations_are_bounded_not_script(self):
        self.assertEqual(destination(35.12,33.94,19)["height"], 120)
        self.assertLessEqual(destination(0,0,-300)["height"],24000000)
        for lat,lon in [(float("nan"),0),(0,float("inf")),(91,0),(0,181),("');evil();//",0)]:
            with self.assertRaises((TypeError,ValueError)):
                destination(lat,lon)

    def test_removed_business_server_cannot_start_on_boot(self):
        self.assertFalse((ROOT / "core/whatsapp_assistant.py").exists())
        self.assertNotIn("whatsapp_assistant", (ROOT / "ui.py").read_text(encoding="utf-8"))
        settings = (ROOT / "gui/settings_page.py").read_text(encoding="utf-8")
        self.assertNotIn("WhatsApp Business", settings)
        self.assertNotIn("Kişiselleştirme", settings)

    def test_friday_wake_and_explicit_close_use_current_identity(self):
        from core.wake_word import KEYPHRASES
        from core.voice_commands import is_close_command
        self.assertIn("hey friday", KEYPHRASES)
        self.assertNotIn("hey aether", KEYPHRASES)
        self.assertFalse(is_close_command("Aether uygulamasını kapat"))
        self.assertTrue(is_close_command("FRIDAY uygulamasını kapat"))
        self.assertFalse(is_close_command("FRIDAY bilgisayarı kapat"))
