"""Wake activation must reflect the detector and serialize requests from both panels."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests._main_import import load_main


class WakeSettings(unittest.TestCase):
    def test_failed_detector_is_not_enabled(self):
        main = load_main()
        live = Mock()
        live._ensure_wake_detector.return_value = False
        with patch.object(main, "wake_is_ready", return_value=True), patch.object(main, "save_wake_word_enabled") as save:
            self.assertEqual(main.AetherLive._ui_wake_toggle(live, True), "failed")
        self.assertFalse(live._wake_enabled)
        save.assert_called_once_with(False)
        live.sleep.assert_not_called()

    def test_second_click_cannot_start_another_install(self):
        from gui.window import MainWindow
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        def install(**kwargs):
            entered.set()
            return release.wait(3), "kuruldu"
        signal = Mock()
        signal.emit.side_effect = lambda *_: done.set()
        owner = SimpleNamespace(_wake_busy=False, _wake_state=lambda: {"enabled": False, "ready": False},
                                _refresh_wake_btns=Mock(), on_wake_toggle=Mock(return_value="failed"),
                                _wake_dl_sig=signal, _log_sig=Mock())
        with patch("core.wake_word.install_and_download", side_effect=install) as download:
            MainWindow._toggle_wake_word(owner)
            try:
                self.assertTrue(entered.wait(2))
                MainWindow._toggle_wake_word(owner)
            finally:
                release.set()
            self.assertTrue(done.wait(2))
            download.assert_called_once()
        owner.on_wake_toggle.assert_called_once_with(True)
        ok, message = signal.emit.call_args.args
        self.assertFalse(ok)
        MainWindow._on_wake_install_done(owner, ok, message)
        self.assertFalse(owner._wake_busy)
        self.assertEqual(owner._wake_feedback, message)


class WakeAudioTests(unittest.TestCase):
    def test_reset_discards_frames_already_in_flight(self):
        import json
        import numpy as np
        from core.wake_word import WakeWordDetector
        detected = Mock()
        detector = WakeWordDetector(detected)
        model = Mock()
        detector._running = True
        def recognize(_pcm):
            detector.reset()
            return True
        model.AcceptWaveform.side_effect = recognize
        model.Result.return_value = json.dumps({"result": [{"word": w, "conf": 1} for w in ("hey", "mike")]})
        detector.feed(np.zeros(64, dtype=np.int16))
        detector.feed(np.zeros(64, dtype=np.int16))
        detector._queue.put_nowait(None)
        detector._loop(detector._queue, model)
        detected.assert_not_called()
        model.AcceptWaveform.assert_called_once()
