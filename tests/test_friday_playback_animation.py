"""Regression tests for FRIDAY's native playback-driven HUD timeline."""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from gui.hud import HudCanvas


class PlaybackAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.enterContext(patch.object(HudCanvas, "paintEvent", lambda *_: None))
        self.enterContext(patch("memory.config_manager.get_hud_style", return_value="face"))
        self.hud = HudCanvas("")
        self.hud._avatar = Mock()
        self.hud.show()
        self.hud.speaking = True
        self.addCleanup(self.hud.close)
        self.addCleanup(self.hud._tmr.stop)

    def test_interrupt_clears_timeline_and_rejects_stale_epoch(self):
        self.hud.push_visemes([(1., .8, .1)], .02, 100., epoch=1)
        self.hud.set_audio_level(.8)
        self.hud.clear_voice_animation(2)
        self.hud.push_visemes([(1., .8, .1)], .02, 100., epoch=1)
        self.assertIsNone(self.hud._visemes)
        self.assertEqual(self.hud._live_amp, 0.)
        self.hud.push_visemes([(.3, .2, .1)], .02, 101., epoch=2)
        self.assertEqual(self.hud._visemes[0], [(.3, .2, .1)])

    def test_first_frame_does_not_animate_before_audible_time(self):
        self.hud.push_visemes([(1., .8, .1)], .02, 100.)
        with patch("gui.hud.time.time", return_value=99.995):
            self.hud._step()
        self.assertEqual(self.hud._avatar.step.call_args.kwargs["v_open"], 0.)
        self.assertEqual(self.hud._amp_disp, 0.)
        self.assertIsNone(self.hud._vis_i)

    def test_missing_single_frame_becomes_silence_not_early_speech(self):
        first, last = (.4, .3, .1), (.8, .7, .2)
        with patch("gui.hud.time.time", return_value=100.):
            self.hud.push_visemes([first], .02, 100.)
            self.hud.push_visemes([last], .02, 100.04)
        self.assertEqual(self.hud._visemes[0], [first, (0., 0., 0.), last])

    def test_restore_does_not_replay_long_animation_backlog(self):
        self.hud.push_visemes([(.4, .3, .1)] * 100, .02, 100.)
        with patch("gui.hud.time.time", return_value=100.005):
            self.hud._step()
        with patch("gui.hud.time.time", return_value=101.5):
            self.hud._step()
        recent = self.hud._avatar.step.call_args.kwargs["v_seq"]
        self.assertEqual(len(recent), 5)

    def test_epoch_change_replaces_previous_schedule(self):
        self.hud.push_visemes([(1., .8, .1)], .02, 100., epoch=3)
        self.hud.push_visemes([(.2, .1, 0.)], .02, 100.02, epoch=4)
        self.assertEqual(self.hud._visemes[0], [(.2, .1, 0.)])
        self.assertEqual(self.hud._viseme_epoch, 4)
