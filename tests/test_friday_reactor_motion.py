"""Native FRIDAY reactor motion and theme regressions."""
import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication
from gui.reactor import Reactor3D, _motion_targets, _energy_palette


class ReactorMotionTests(unittest.TestCase):
    def test_distinct_native_conversation_states(self):
        idle = _motion_targets(False, False, False, "TEXT_READY", 0.)
        sleep = _motion_targets(False, False, False, "SLEEPING", 0.)
        listen = _motion_targets(False, False, False, "LISTENING", .5)
        think = _motion_targets(False, True, False, "THINKING", 0.)
        speak = _motion_targets(True, False, False, "SPEAKING", .5)
        self.assertLess(sleep[0], idle[0])
        self.assertLess(idle[0], listen[0])
        self.assertLess(listen[0], speak[0])
        self.assertLess(speak[0], think[0])
        self.assertLess(sleep[1], idle[1])
        self.assertLess(idle[1], speak[1])

    def test_rotation_accelerates_smoothly_and_clamps_elapsed_time(self):
        reactor = Reactor3D()
        initial = reactor._rate
        reactor.step(.016, False, True, False, state="THINKING")
        self.assertGreater(reactor._rate, initial)
        self.assertLess(reactor._rate, 1.64)
        for _ in range(80):
            reactor.step(.016, False, True, False, state="THINKING")
        self.assertAlmostEqual(reactor._rate, 1.64, places=2)
        old_spin = reactor.spin
        reactor.step(60., False, True, False)
        self.assertLessEqual(reactor.spin - old_spin, .165)

    def test_volume_does_not_multiply_accumulated_arc_angle(self):
        reactor = Reactor3D()
        reactor.spin = 1000.
        reactor.arc_spin = 1000.
        a = reactor._arc_paths(0., 0., 1., reactor.spin, 0.)
        b = reactor._arc_paths(0., 0., 1., reactor.spin, 1.)
        # Only radius changes, not the angular position of the orbital arc.
        for (x1, y1, _, _), (x2, y2, _, _) in zip(a, b):
            np.testing.assert_allclose(np.arctan2(y1, x1), np.arctan2(y2, x2), atol=1e-10)
        before = reactor.arc_spin
        reactor.step(.016, True, False, False, state="SPEAKING", amp=1.)
        self.assertLess(reactor.arc_spin - before, .05)

    def test_sleep_and_muted_ignore_audio_energy(self):
        for muted, state in ((True, "LISTENING"), (False, "SLEEPING"), (False, "TEXT_READY")):
            a, b = Reactor3D(), Reactor3D()
            a.step(.1, False, False, muted, state=state, amp=0.)
            b.step(.1, False, False, muted, state=state, amp=1.)
            self.assertEqual((a.spin, a.arc_spin, a._energy), (b.spin, b.arc_spin, b._energy))

    def test_theme_and_state_change_palette_not_geometry(self):
        main, white = QColor("#67defa"), QColor("#e9f9ff")
        listening = _energy_palette(main, QColor("#5ef0a8"), white, False)
        speaking = _energy_palette(main, QColor("#b5a7ff"), white, False)
        custom = _energy_palette(QColor("#ff9900"), QColor("#b5a7ff"), white, False)
        self.assertNotEqual(listening[2], speaking[2])
        self.assertNotEqual(speaking[3], custom[3])
        muted = _energy_palette(main, QColor("#b5a7ff"), white, True)
        self.assertEqual(muted[1:], (main, main, main))

    def test_zero_brightness_particles_are_not_drawn(self):
        painter = Mock()
        Reactor3D._points(painter, np.array([1., 2.]), np.array([1., 2.]),
                          np.array([0., 0.]), QColor("cyan"), 1.)
        painter.drawPoints.assert_not_called()


class ReactorRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_states_paint_with_native_geometry(self):
        reactor = Reactor3D()
        main, acc, white = QColor("#67defa"), QColor("#b5a7ff"), QColor("#e9f9ff")
        for state in ("SLEEPING", "TEXT_READY", "LISTENING", "THINKING", "SPEAKING", "MUTED"):
            with self.subTest(state=state):
                speaking, thinking, muted = state == "SPEAKING", state == "THINKING", state == "MUTED"
                reactor.step(.1, speaking, thinking, muted, state=state, amp=.5)
                img = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(QColor("#060b16"))
                painter = QPainter(img)
                try:
                    reactor.paint(painter, 160, 140, 75, main, acc, white, .5, speaking, "FRIDAY", muted)
                finally:
                    painter.end()
                self.assertNotEqual(img.pixelColor(160, 140), QColor("#060b16"))
