"""gui/reactor.py — the reactor core: a burning particle star.

A white-hot heart sits inside a shell of glowing particles. A tangle of orbit
lines winds through the shell on random axes, a dusty ring of sparks circles
it face-on, and long light rays shoot out from the centre. Everything is
projected from real 3-D points through a perspective camera, so particles and
orbits on the far side are dimmer and smaller than the ones in front.

It is software QPainter only (no GPU, no new dependency). Light is added with
the Plus composition mode, so overlapping particles and rays brighten each
other the way real glow does. Everything that moves means something: the spin
rate is the assistant's state, and the heart, the rays and the sparks swell
with the real audio level.

The palette is a fixed fire-orange so the core always looks like a star; when
the assistant is muted it falls back to the muted colour handed in by the HUD.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF,
                         QRadialGradient)

_DISPLAY = ["Bahnschrift", "Segoe UI", "SF Pro Display", "Helvetica Neue",
            "Noto Sans", "DejaVu Sans"]

_CAM_D = 4.2            # perspective distance, in core radii
_N_ORBIT = 96           # points on an orbit line
_N_SHELL = 700          # particles in the spherical shell
_N_DUST = 700           # particles in the outer ring
_N_ORBITS = 16          # tangled orbit lines
_N_RAYS = 24            # light rays

# fire palette
_HOT = QColor("#fff6d8")
_GOLD = QColor("#ffb43a")
_ORANGE = QColor("#ff8414")
_EMBER = QColor("#ff5200")


def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _with_alpha(col: QColor, a: float) -> QColor:
    c = QColor(col)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _unit_vectors(rng, n):
    v = rng.normal(size=(3, n))
    return v / np.linalg.norm(v, axis=0)


class Reactor3D:
    """State + renderer. `step()` advances it, `paint()` draws a frame."""

    # Vertical extent in core radii: the tip of the longest ray above the
    # centre, and the bottom of the name below it.
    TOP = 1.45
    BOTTOM = 1.80

    def __init__(self):
        rng = np.random.default_rng(57)

        # the shell: mostly near the surface, a few deeper inside
        u = rng.uniform(0.0, 1.0, _N_SHELL)
        rad = 0.58 + 0.40 * np.sqrt(u)
        self._shell = _unit_vectors(rng, _N_SHELL) * rad
        self._shell_ph = rng.uniform(0, 2 * math.pi, _N_SHELL)
        self._shell_sp = rng.uniform(1.5, 5.0, _N_SHELL)

        # the dust ring: a thin, slightly puffy disc around the shell
        a = rng.uniform(0, 2 * math.pi, _N_DUST)
        rr = 0.96 + 0.24 * rng.beta(2.0, 3.0, _N_DUST)
        self._dust = np.vstack([np.cos(a) * rr, np.sin(a) * rr,
                                rng.normal(0.0, 0.035, _N_DUST)])
        self._dust_ph = rng.uniform(0, 2 * math.pi, _N_DUST)

        # tangled orbit lines on random axes
        t = np.linspace(0.0, 2 * math.pi, _N_ORBIT, endpoint=False)
        circle = np.vstack([np.cos(t), np.sin(t), np.zeros_like(t)])
        self._orbits = []
        for _ in range(_N_ORBITS):
            R = (_rz(rng.uniform(0, 2 * math.pi)) @ _rx(rng.uniform(0, math.pi))
                 @ _ry(rng.uniform(0, 2 * math.pi)))
            sx, sy = rng.uniform(0.62, 0.98), rng.uniform(0.62, 0.98)
            pts = circle.copy()
            pts[0] *= sx
            pts[1] *= sy
            self._orbits.append((R @ pts, float(rng.uniform(-0.5, 0.5)),
                                 float(rng.uniform(0.25, 0.65))))

        # rays: angle on screen, base length, width, flicker phase/speed
        self._rays = [(float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(0.85, 1.45)),
                       float(rng.uniform(1.8, 3.4)), float(rng.uniform(0, 2 * math.pi)),
                       float(rng.uniform(0.8, 2.6)))
                      for _ in range(_N_RAYS)]

        self.spin = 0.0
        self.t = 0.0

    # ── motion ────────────────────────────────────────────────────────────────
    def step(self, dt: float, speaking: bool, thinking: bool, muted: bool) -> None:
        dt = min(0.10, max(0.0, dt))
        rate = 0.10 if muted else 0.32 + (1.3 if thinking else 0.0) + (0.6 if speaking else 0.0)
        self.spin += dt * rate
        self.t += dt

    # ── projection ────────────────────────────────────────────────────────────
    @staticmethod
    def _project(pts, cx, cy, r):
        s = _CAM_D / (_CAM_D - pts[2])
        return cx + pts[0] * s * r, cy - pts[1] * s * r, pts[2], s

    @staticmethod
    def _points(p, X, Y, alpha, size, col, buckets=4):
        """Draw a cloud of dots, grouped into brightness buckets so each group
        is one drawPoints call."""
        if len(X) == 0:
            return
        lv = np.clip((alpha * buckets).astype(np.int16), 0, buckets - 1)
        for k in range(buckets):
            idx = np.flatnonzero(lv == k)
            if idx.size == 0:
                continue
            poly = QPolygonF([QPointF(x, y) for x, y in zip(X[idx].tolist(), Y[idx].tolist())])
            pen = QPen(_with_alpha(col, (k + 1) / buckets), size * (0.75 + 0.25 * k))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(poly)

    @staticmethod
    def _polyline(p, X, Y, Z, col, a, width):
        """A closed orbit, dimmer where it runs behind the centre."""
        zm = (Z + np.roll(Z, -1)) * 0.5
        xs, ys = X.tolist(), Y.tolist()
        xe, ye = np.roll(X, -1).tolist(), np.roll(Y, -1).tolist()
        back, front = [], []
        for i, z in enumerate(zm.tolist()):
            (front if z >= 0 else back).append(QLineF(xs[i], ys[i], xe[i], ye[i]))
        for lines, k in ((back, 0.35), (front, 1.0)):
            if lines:
                pen = QPen(_with_alpha(col, a * k), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLines(lines)

    # ── frame ─────────────────────────────────────────────────────────────────
    def paint(self, p: QPainter, cx: float, cy: float, r: float, main: QColor, acc: QColor,
              white: QColor, amp: float, live: bool, name: str = "",
              muted: bool = False) -> None:
        spin, t = self.spin, self.t
        amp = max(0.0, min(1.0, amp))
        if muted:
            hot, gold, orange, ember = QColor(white), QColor(main), QColor(main), QColor(main)
            dim = 0.55
        else:
            hot, gold, orange, ember = _HOT, _GOLD, _ORANGE, _EMBER
            dim = 1.0
        energy = 0.75 + 0.55 * amp + (0.1 if live else 0.0)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # 1. the atmosphere: a wide soft body of light behind everything
        p.setPen(Qt.PenStyle.NoPen)
        halo = QRadialGradient(cx, cy, r * 1.35)
        halo.setColorAt(0.0, _with_alpha(orange, 0.30 * dim * energy))
        halo.setColorAt(0.40, _with_alpha(ember, 0.12 * dim * energy))
        halo.setColorAt(1.0, _with_alpha(ember, 0.0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(QPointF(cx, cy), r * 1.35, r * 1.35)

        # 2. rays shooting out of the heart
        rot = spin * 0.15
        for ang, ln, w, ph, sp in self._rays:
            flick = 0.65 + 0.35 * math.sin(t * sp + ph)
            L = r * ln * (0.80 + 0.45 * amp) * (0.85 + 0.25 * flick)
            a = ang + rot
            ca, sa = math.cos(a), math.sin(a)
            x0, y0 = cx + ca * r * 0.08, cy + sa * r * 0.08
            x1, y1 = cx + ca * L, cy + sa * L
            g = QLinearGradient(x0, y0, x1, y1)
            g.setColorAt(0.0, _with_alpha(gold, 0.80 * dim * flick))
            g.setColorAt(0.25, _with_alpha(orange, 0.75 * dim * flick))
            g.setColorAt(0.75, _with_alpha(ember, 0.40 * dim * flick))
            g.setColorAt(1.0, _with_alpha(ember, 0.0))
            pen = QPen(QBrush(g), w * (0.9 + 0.4 * amp))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawLine(QLineF(x0, y0, x1, y1))

        # 3. tangled orbit lines winding through the shell
        R_all = _ry(spin * 0.55) @ _rx(spin * 0.21)
        for pts, own, a in self._orbits:
            v = R_all @ _rz(spin * own) @ pts
            X, Y, Z, _ = self._project(v, cx, cy, r)
            self._polyline(p, X, Y, Z, orange, a * dim * energy, 1.1)

        # 4. the particle shell, twinkling, dimmer at the back
        v = R_all @ self._shell
        X, Y, Z, s = self._project(v, cx, cy, r)
        tw = 0.55 + 0.45 * np.sin(self._shell_ph + t * self._shell_sp)
        alpha = np.clip((0.25 + 0.75 * (Z + 1.0) * 0.5) * tw * dim * min(1.0, energy), 0, 1)
        self._points(p, X, Y, alpha, max(1.4, r * 0.012), orange)

        # 5. the dust ring, face-on and gently tilted, turning about its axis
        Rd = _rx(0.28 + 0.06 * math.sin(spin * 0.3)) @ _ry(0.18) @ _rz(spin * 0.35)
        v = Rd @ self._dust
        X, Y, Z, _ = self._project(v, cx, cy, r)
        tw = 0.5 + 0.5 * np.sin(self._dust_ph + t * 2.2)
        alpha = np.clip((0.40 + 0.6 * tw) * dim * min(1.0, energy), 0, 1)
        self._points(p, X, Y, alpha, max(1.2, r * 0.010), gold)

        # 6. the heart: white-hot, swelling with the voice
        hr = r * (0.30 + 0.18 * amp)
        heart = QRadialGradient(cx, cy, hr)
        heart.setColorAt(0.0, _with_alpha(hot, 1.0 * dim))
        heart.setColorAt(0.22, _with_alpha(hot, 0.95 * dim))
        heart.setColorAt(0.45, _with_alpha(gold, 0.70 * dim))
        heart.setColorAt(1.0, _with_alpha(orange, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(heart))
        p.drawEllipse(QPointF(cx, cy), hr, hr)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # the name, under the star
        if name:
            f = QFont()
            f.setFamilies(_DISPLAY)
            px = max(10, int(r * 0.11))
            f.setPixelSize(px)
            f.setWeight(QFont.Weight.Light)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(2.0, round(r * 0.035)))
            p.setFont(f)
            p.setPen(QPen(_with_alpha(white, 0.78 + 0.2 * min(1.0, amp * 2))))
            p.drawText(QRectF(cx - r * 1.6, cy + r * 1.42, r * 3.2, px * 1.8),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name)
        p.restore()
