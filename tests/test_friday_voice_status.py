"""FRIDAY native HUD status and voice permission regression tests."""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.voice_status import presentation, realtime_mic_permitted


class VoicePresentationTests(unittest.TestCase):
    def test_default_realtime_has_no_cloud_microphone(self):
        self.assertFalse(realtime_mic_permitted({}))
        self.assertFalse(realtime_mic_permitted({"microphone": True}))
        self.assertFalse(realtime_mic_permitted({"cloud_consent": True, "microphone": "false"}))
        self.assertTrue(realtime_mic_permitted({"cloud_consent": "1", "microphone": True}))
        self.assertEqual(presentation("LISTENING", realtime=True, mic_permitted=False),
                         ("TEXT_READY", ("SES AKTARIMI · KAPALI", "MUTED_C")))

    def test_microphone_permission_is_not_connection_or_capture_status(self):
        state, mic = presentation("SLEEPING", realtime=True)
        self.assertEqual(state, "SLEEPING")
        self.assertEqual(mic, ("SES AKTARIMI · BEKLEMEDE", "PRI"))
        state, mic = presentation("LISTENING", realtime=True, ptt=True)
        self.assertEqual(state, "PTT_READY")
        self.assertEqual(mic, ("MİKROFON · BAS-KONUŞ", "PRI"))
        self.assertEqual(presentation("LISTENING", realtime=True)[1][0], "SES AKTARIMI · İZİNLİ")

    def test_text_only_preserves_thinking_and_speech_states(self):
        for state in ("INITIALISING", "THINKING", "PROCESSING", "SPEAKING", "SLEEPING"):
            self.assertEqual(presentation(state, realtime=True, mic_permitted=False)[0], state)

    def test_muted_and_legacy_engine_states(self):
        self.assertEqual(presentation("LISTENING", realtime=True, muted=True)[0], "MUTED")
        self.assertEqual(presentation("LISTENING", realtime=False),
                         ("LISTENING", ("MİKROFON · AÇIK", "GREEN")))
        self.assertEqual(presentation("MUTED", realtime=False, muted=True),
                         ("MUTED", ("MİKROFON · KAPALI", "MUTED_C")))


class NativeHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_status_chip_uses_friday_palette_and_turkish_names(self):
        from gui.widgets import StateChip
        self.assertEqual(StateChip._TR["TEXT_READY"], "YAZILI KOMUT")
        self.assertEqual(StateChip._TR["PTT_READY"], "BAS-KONUŞ")
        self.assertEqual(StateChip._COLOURS["TEXT_READY"], "PRI")

    def test_text_only_hud_does_not_react_to_local_mic_peaks(self):
        from gui.hud import HudCanvas
        with patch.object(HudCanvas, "paintEvent", lambda *_: None), patch(
                "memory.config_manager.get_hud_style", return_value="face"):
            hud = HudCanvas("")
            self.addCleanup(hud.close)
            self.addCleanup(hud._tmr.stop)
            hud._avatar = Mock()
            hud.show()
            hud.state = "TEXT_READY"
            hud.set_audio_level(0.8)
            hud._step()
            self.assertEqual(hud._amp_disp, 0.0)
            self.assertEqual(hud._live_amp, 0.0)
            hud.state = "SPEAKING"
            hud.speaking = True
            hud.set_audio_level(0.8)
            hud._step()
            self.assertGreater(hud._amp_disp, 0.0)

    def test_realtime_only_configuration_is_accepted_without_gemini(self):
        from gui.window import MainWindow
        cfg = {"os_system": "windows", "providers": {"mode": "realtime"}}
        with patch("gui.window._read_full_config", return_value=cfg), patch(
                "memory.config_manager.get_provider_config",
                return_value={"api_key": "test-key", "cloud_consent": True}):
            self.assertTrue(MainWindow._check_config(None))
        with patch("gui.window._read_full_config", return_value=cfg), patch(
                "memory.config_manager.get_provider_config",
                return_value={"api_key": "test-key", "cloud_consent": False}):
            self.assertFalse(MainWindow._check_config(None))
