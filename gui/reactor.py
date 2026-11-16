"""gui/reactor.py — the reactor core: a burning particle star.

A white-hot heart sits inside a shell of glowing particles. Comet-like orbit
trails wind through the shell on random axes, a dusty ring of sparks circles
it, tapered light rays shoot out of the centre and an anamorphic flare cuts
across it. Everything is projected from real 3-D points through a perspective
camera, so the far side is dimmer and smaller than the near side.

What makes it look like light and not like dots is the bloom pass: the star is
drawn sharp into an offscreen image, that image is shrunk twice with smooth
filtering (which is a cheap, wide blur) and the blurred copies are added back
under the sharp one. Every bright thing then glows the way it would through a
camera lens. All of it is software QPainter: no GPU, no new dependency.

Everything that moves means something: the spin rate is the assistant's state,
and the heart, the rays, the trails and the sparks swell with the real audio
level. The palette is a fixed fire-orange; muted falls back to the muted
colour handed in by the HUD.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPen,
                         QPolygonF, QRadialGradient)

_DISPLAY = ["Bahnschrift", "Segoe UI", "SF Pro Display", "Helvetica Neue",
            "Noto Sans", "DejaVu Sans"]

_CAM_D = 4.2            # perspective distance, in core radii
_N_ORBIT = 120          # points on an orbit trail
_N_SHELL = 1100         # particles in the spherical shell
_N_CORONA = 260         # fast, hot particles close to the heart
_N_DUST = 900           # particles in the outer ring
_N_ORBITS = 18          # orbit trails
_N_RAYS = 26            # light rays
_MAX_BUF = 1500         # longest side of the offscreen image, in device pixels

# fire palette, hottest first
_HOT = QColor("#fff8e6")
_GOLD = QColor("#ffc04d")
_ORANGE = QColor("#ff8a1c")
_EMBER = QColor("#ff5400")


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


def _classes(rng, n, hot_share, gold_share):
    """Per-particle colour (0 hot, 1 gold, 2 orange) and size (0 fine .. 2 big)."""
    c = rng.uniform(size=n)
    col = np.where(c < hot_share, 0, np.where(c < hot_share + gold_share, 1, 2))
    s = rng.uniform(size=n)
    size = np.where(s < 0.70, 0, np.where(s < 0.94, 1, 2))
    return col.astype(np.int16), size.astype(np.int16)


class Reactor3D:
    """State + renderer. `step()` advances it, `paint()` draws a frame."""

    # Vertical extent in core radii: the tip of the longest ray above the
    # centre, and the bottom of the name below it.
    TOP = 1.45
    BOTTOM = 1.80

    def __init__(self):
        rng = np.random.default_rng(57)

        # the shell: dense near the surface, thinner inside
        u = rng.uniform(0.0, 1.0, _N_SHELL)
        rad = 0.50 + 0.48 * u ** 0.45
        self._shell = _unit_vectors(rng, _N_SHELL) * rad
        self._shell_ph = rng.uniform(0, 2 * math.pi, _N_SHELL)
        self._shell_sp = rng.uniform(1.2, 4.5, _N_SHELL)
        self._shell_col, self._shell_size = _classes(rng, _N_SHELL, 0.10, 0.35)

        # the corona: small and hot, close to the heart
        self._corona = _unit_vectors(rng, _N_CORONA) * rng.uniform(0.10, 0.42, _N_CORONA)
        self._corona_ph = rng.uniform(0, 2 * math.pi, _N_CORONA)
        self._corona_col, self._corona_size = _classes(rng, _N_CORONA, 0.45, 0.45)

        # the dust ring: a thin, slightly puffy band around the shell
        a = rng.uniform(0, 2 * math.pi, _N_DUST)
        rr = 0.95 + 0.26 * rng.beta(2.0, 3.0, _N_DUST)
        self._dust = np.vstack([np.cos(a) * rr, np.sin(a) * rr,
                                rng.normal(0.0, 0.03, _N_DUST)])
        self._dust_ph = rng.uniform(0, 2 * math.pi, _N_DUST)
        self._dust_col, self._dust_size = _classes(rng, _N_DUST, 0.08, 0.40)

        # orbit trails on random axes, each with a head that runs round it
        t = np.linspace(0.0, 2 * math.pi, _N_ORBIT, endpoint=False)
        circle = np.vstack([np.cos(t), np.sin(t), np.zeros_like(t)])
        self._orbits = []
        for _ in range(_N_ORBITS):
            R = (_rz(rng.uniform(0, 2 * math.pi)) @ _rx(rng.uniform(0, math.pi))
                 @ _ry(rng.uniform(0, 2 * math.pi)))
            sx, sy = rng.uniform(0.58, 0.98), rng.uniform(0.58, 0.98)
            pts = circle.copy()
            pts[0] *= sx
            pts[1] *= sy
            direction = 1.0 if rng.uniform() < 0.5 else -1.0
            self._orbits.append((R @ pts, float(rng.uniform(-0.5, 0.5)),
                                 float(rng.uniform(0.45, 0.95)),
                                 float(rng.uniform(0.6, 1.6)) * direction,
                                 float(rng.uniform(0, 1))))

        # rays: angle on screen, length, width, flicker phase and speed
        self._rays = [(float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(0.90, 1.55)),
                       float(rng.uniform(0.6, 1.4)), float(rng.uniform(0, 2 * math.pi)),
                       float(rng.uniform(0.8, 2.6)))
                      for _ in range(_N_RAYS)]

        self.spin = 0.0
        self.t = 0.0
        self._buf: QImage | None = None

    # ── motion ────────────────────────────────────────────────────────────────
    def step(self, dt: float, speaking: bool, thinking: bool, muted: bool) -> None:
        dt = min(0.10, max(0.0, dt))
        rate = 0.10 if muted else 0.32 + (1.3 if thinking else 0.0) + (0.6 if speaking else 0.0)
        self.spin += dt * rate
        self.t += dt

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _project(pts, cx, cy, r):
        s = _CAM_D / (_CAM_D - pts[2])
        return cx + pts[0] * s * r, cy - pts[1] * s * r, pts[2], s

    @staticmethod
    def _points(p, X, Y, alpha, col_idx, size_idx, cols, base):
        """Draw a particle cloud, one drawPoints call per colour × size × brightness."""
        lv = np.clip((alpha * 3).astype(np.int16), 0, 2)
        key = col_idx * 9 + size_idx * 3 + lv
        xs, ys = X.tolist(), Y.tolist()
        order = np.argsort(key, kind="stable")
        bounds = np.flatnonzero(np.diff(key[order])) + 1
        for grp in np.split(order, bounds):
            if grp.size == 0:
                continue
            k = int(key[grp[0]])
            c, sz, lvl = k // 9, (k // 3) % 3, k % 3
            pen = QPen(_with_alpha(cols[c], (lvl + 1) / 3.0), base * (1.0, 1.7, 2.6)[sz])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(QPolygonF([QPointF(xs[i], ys[i]) for i in grp.tolist()]))

    @staticmethod
    def _trail(p, X, Y, Z, head, col, a, width):
        """A closed orbit drawn as a comet: bright at its head, fading behind it,
        dimmer where it runs behind the centre."""
        n = len(X)
        age = ((head - np.arange(n)) % n) / n           # 0 at the head, ~1 just ahead of it
        zm = (Z + np.roll(Z, -1)) * 0.5
        bright = (1.0 - age) ** 1.8 * np.where(zm >= 0, 1.0, 0.40)
        lv = np.minimum((bright * 4).astype(np.int8), 3).tolist()
        keep = (bright > 0.03).tolist()
        xs, ys = X.tolist(), Y.tolist()
        xe, ye = np.roll(X, -1).tolist(), np.roll(Y, -1).tolist()
        buckets = ([], [], [], [])
        for i in range(n):
            if keep[i]:
                buckets[lv[i]].append(QLineF(xs[i], ys[i], xe[i], ye[i]))
        for k, lines in enumerate(buckets):
            if lines:
                pen = QPen(_with_alpha(col, a * (k + 1) / 4.0), width * (0.7 + 0.15 * k))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLines(lines)

    def _ensure_buf(self, w: int, h: int, dpr: float) -> QImage:
        if self._buf is None or self._buf.width() != w or self._buf.height() != h:
            self._buf = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self._buf.setDevicePixelRatio(dpr)
        self._buf.fill(Qt.GlobalColor.transparent)
        return self._buf

    # ── the star itself, drawn sharp ──────────────────────────────────────────
    def _draw_star(self, q: QPainter, cx, cy, r, pal, amp, live, dim):
        hot, gold, orange, ember = pal
        cols = (hot, gold, orange)
        spin, t = self.spin, self.t
        energy = 0.85 + 0.30 * amp + (0.1 if live else 0.0)
        e1 = min(1.0, energy)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # atmosphere
        q.setPen(Qt.PenStyle.NoPen)
        halo = QRadialGradient(cx, cy, r * 1.30)
        halo.setColorAt(0.0, _with_alpha(orange, 0.26 * dim * energy))
        halo.setColorAt(0.35, _with_alpha(ember, 0.10 * dim * energy))
        halo.setColorAt(1.0, _with_alpha(ember, 0.0))
        q.setBrush(QBrush(halo))
        q.drawEllipse(QPointF(cx, cy), r * 1.30, r * 1.30)

        # tapered rays
        rot = spin * 0.12
        for ang, ln, w, ph, sp in self._rays:
            flick = 0.6 + 0.4 * math.sin(t * sp + ph)
            L = r * ln * (0.85 + 0.30 * amp) * (0.85 + 0.25 * flick)
            a = ang + rot
            ca, sa = math.cos(a), math.sin(a)
            half = r * 0.013 * w * (0.9 + 0.3 * amp)
            nx, ny = -sa * half, ca * half
            x0, y0 = cx + ca * r * 0.04, cy + sa * r * 0.04
            x1, y1 = cx + ca * L, cy + sa * L
            g = QLinearGradient(x0, y0, x1, y1)
            g.setColorAt(0.0, _with_alpha(hot, 0.85 * dim * flick))
            g.setColorAt(0.18, _with_alpha(gold, 0.75 * dim * flick))
            g.setColorAt(0.55, _with_alpha(orange, 0.40 * dim * flick))
            g.setColorAt(1.0, _with_alpha(ember, 0.0))
            q.setBrush(QBrush(g))
            q.drawPolygon(QPolygonF([QPointF(x0 + nx, y0 + ny), QPointF(x1, y1),
                                     QPointF(x0 - nx, y0 - ny)]))

        # orbit trails
        R_all = _ry(spin * 0.55) @ _rx(spin * 0.21)
        lw = max(1.0, r * 0.0085)
        for pts, own, a, sp, off in self._orbits:
            v = R_all @ _rz(spin * own) @ pts
            X, Y, Z, _ = self._project(v, cx, cy, r)
            head = ((off + spin * sp * 0.35) % 1.0) * _N_ORBIT
            self._trail(q, X, Y, Z, head, gold, a * dim * e1, lw)

        base = max(1.1, r * 0.0075)

        # the particle shell: breathing with the voice, twinkling, dimmer at the back
        breathe = 1.0 + 0.05 * amp * np.sin(self._shell_ph * 3 + t * 6.0)
        v = R_all @ (self._shell * breathe)
        X, Y, Z, _ = self._project(v, cx, cy, r)
        tw = 0.45 + 0.55 * np.sin(self._shell_ph + t * self._shell_sp) ** 2
        alpha = np.clip((0.20 + 0.80 * (Z + 1.0) * 0.5) * tw * dim * e1, 0, 1)
        self._points(q, X, Y, alpha, self._shell_col, self._shell_size, cols, base)

        # the dust ring
        Rd = _rx(0.30 + 0.06 * math.sin(spin * 0.3)) @ _ry(0.16) @ _rz(spin * 0.35)
        v = Rd @ self._dust
        X, Y, Z, _ = self._project(v, cx, cy, r)
        tw = 0.40 + 0.60 * np.sin(self._dust_ph + t * 2.0) ** 2
        alpha = np.clip((0.35 + 0.65 * tw) * (0.55 + 0.45 * (Z + 1.3) / 2.6) * dim * e1, 0, 1)
        self._points(q, X, Y, alpha, self._dust_col, self._dust_size, cols, base * 0.9)

        # the corona: fast and hot around the heart
        v = _ry(spin * 2.2) @ _rx(spin * 1.1) @ self._corona
        X, Y, Z, _ = self._project(v, cx, cy, r)
        alpha = np.clip((0.55 + 0.45 * np.sin(self._corona_ph + t * 5.0)) * dim, 0, 1)
        self._points(q, X, Y, alpha, self._corona_col, self._corona_size, cols, base * 0.9)

        # the heart: a white core inside a gold glow
        q.setPen(Qt.PenStyle.NoPen)
        hr = r * (0.32 + 0.08 * amp)
        g = QRadialGradient(cx, cy, hr)
        g.setColorAt(0.0, _with_alpha(gold, 0.70 * dim))
        g.setColorAt(0.35, _with_alpha(orange, 0.30 * dim))
        g.setColorAt(1.0, _with_alpha(ember, 0.0))
        q.setBrush(QBrush(g))
        q.drawEllipse(QPointF(cx, cy), hr, hr)
        cr = r * (0.10 + 0.03 * amp)
        g = QRadialGradient(cx, cy, cr)
        g.setColorAt(0.0, _with_alpha(hot, 1.0 * dim))
        g.setColorAt(0.55, _with_alpha(hot, 0.85 * dim))
        g.setColorAt(1.0, _with_alpha(gold, 0.0))
        q.setBrush(QBrush(g))
        q.drawEllipse(QPointF(cx, cy), cr, cr)

        # anamorphic flare: a thin horizontal streak through the heart
        q.save()
        q.translate(cx, cy)
        q.scale(1.0, 0.045)
        fr = r * (1.25 + 0.35 * amp)
        g = QRadialGradient(0.0, 0.0, fr)
        g.setColorAt(0.0, _with_alpha(hot, 0.55 * dim))
        g.setColorAt(0.25, _with_alpha(gold, 0.22 * dim))
        g.setColorAt(1.0, _with_alpha(ember, 0.0))
        q.setBrush(QBrush(g))
        q.drawEllipse(QPointF(0.0, 0.0), fr, fr)
        q.restore()

    # ── frame ─────────────────────────────────────────────────────────────────
    def paint(self, p: QPainter, cx: float, cy: float, r: float, main: QColor, acc: QColor,
              white: QColor, amp: float, live: bool, name: str = "",
              muted: bool = False) -> None:
        amp = max(0.0, min(1.0, amp))
        if muted:
            pal = (QColor(white), QColor(main), QColor(main), QColor(main))
            dim = 0.50
        else:
            pal = (_HOT, _GOLD, _ORANGE, _EMBER)
            dim = 1.0

        dev = p.device()
        dpr = float(dev.devicePixelRatioF()) if dev is not None else 1.0
        box = QRectF(cx - r * 1.60, cy - r * 1.55, r * 3.20, r * 3.10)
        scale = min(dpr, _MAX_BUF / max(1.0, box.width()))
        w, h = max(8, int(box.width() * scale)), max(8, int(box.height() * scale))

        buf = self._ensure_buf(w, h, scale)
        q = QPainter(buf)
        try:
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.translate(-box.left(), -box.top())
            self._draw_star(q, cx, cy, r, pal, amp, live, dim)
        finally:
            q.end()

        # bloom: two smooth shrinks are a wide, cheap blur
        mode = Qt.TransformationMode.SmoothTransformation
        aspect = Qt.AspectRatioMode.IgnoreAspectRatio
        b1 = buf.scaled(max(2, w // 5), max(2, h // 5), aspect, mode)
        b2 = b1.scaled(max(2, w // 18), max(2, h // 18), aspect, mode)
        b1.setDevicePixelRatio(1.0)
        b2.setDevicePixelRatio(1.0)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        glow = 0.70 + 0.20 * amp
        p.setOpacity(min(1.0, glow))
        p.drawImage(box, b2)
        p.drawImage(box, b2)
        p.setOpacity(min(1.0, 0.75 * glow))
        p.drawImage(box, b1)
        p.setOpacity(1.0)
        p.drawImage(box, buf)
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
