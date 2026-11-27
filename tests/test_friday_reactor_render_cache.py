"""Native FRIDAY rendering reuse, without reducing detail or resolution."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication
from gui.reactor import Reactor3D, _N_ARC_PTS, _N_ARCS, _rz


class ReactorGeometryTests(unittest.TestCase):
    def test_cached_arc_geometry_matches_previous_formula(self):
        reactor = Reactor3D()
        for spin, angle, amp in ((0., 0., 0.), (2.1, 3.2, .45), (1000., 1720., 1.)):
            reactor.arc_spin = angle
            arcs = reactor._arc_paths(130., 120., 82., spin, amp)
            for arc, actual in zip(reactor._arcs, arcs):
                a = arc["phase"] + angle * arc["speed"] + np.linspace(0., arc["span"], _N_ARC_PTS)
                rad = arc["radius"] * (1. + .04 * amp)
                pts = np.vstack([np.cos(a) * rad, np.sin(a) * rad, np.zeros_like(a)])
                expected = reactor._project(_rz(spin * .3) @ arc["tilt"] @ pts, 130., 120., 82.)
                for got, want in zip(actual[:3], expected[:3]):
                    np.testing.assert_allclose(got, want, atol=1e-9, rtol=1e-10)

    def test_arc_segments_created_once_and_shared(self):
        from PyQt6.QtCore import QLineF
        reactor = Reactor3D()
        arcs = reactor._arc_paths(0., 0., 1., 0., .4)
        with patch("gui.reactor.QLineF", wraps=QLineF) as factory:
            segments = reactor._arc_segments(arcs)
            self.assertEqual(factory.call_count, _N_ARCS * (_N_ARC_PTS - 1))
        for (all_lines, back, front, width), (_, _, z, expected_width) in zip(segments, arcs):
            self.assertEqual(width, expected_width)
            self.assertEqual(len(all_lines), len(back) + len(front))
            self.assertEqual({id(x) for x in all_lines}, {id(x) for x in back + front})
            self.assertEqual(len(front), int(np.count_nonzero(z[:-1] + z[1:] >= 0)))

    def test_original_mesh_indices_are_preserved(self):
        reactor = Reactor3D()
        np.testing.assert_array_equal(reactor._mesh_indices[0], reactor._mesh_e[:, 0])
        np.testing.assert_array_equal(reactor._mesh_indices[1], reactor._mesh_e[:, 1])


class ReactorCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def render(self, reactor, radius, color):
        img = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#060b16"))
        painter = QPainter(img)
        try:
            reactor.paint(painter, 200., 175., radius, QColor(color), QColor("#b5a7ff"),
                          QColor("#e9f9ff"), .4, True, "FRIDAY")
        finally:
            painter.end()
        return img

    def test_font_and_glow_reused_without_stale_theme(self):
        reactor = Reactor3D()
        first = self.render(reactor, 75., "#67defa")
        font, glow = reactor._label_font, reactor._glow
        second = self.render(reactor, 75., "#ff9900")
        self.assertIs(reactor._label_font, font)
        self.assertIs(reactor._glow, glow)
        self.assertNotEqual(first, second)
        self.render(reactor, 120., "#ff9900")
        self.assertIsNot(reactor._label_font, font)
        self.assertIsNot(reactor._glow, glow)
