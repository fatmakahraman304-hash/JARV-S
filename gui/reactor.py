"""gui/reactor.py — the reactor core: the FRIDAY cyan orbital energy sphere.

A small white-hot core sits inside a geodesic wireframe sphere. Straight light
rays shoot out of the core in three dimensions, a handful of thick arc
segments orbit around it on tilted planes, and bands of particles swirl round
the whole thing like a small galaxy. Everything is projected from real 3-D
points through a perspective camera, so the far side is dimmer and smaller.

Sharpness: everything sharp is drawn straight onto the widget at the screen's
native resolution, so a 4K display gets 4K detail and line widths scale with
the size of the core. Glow: only the bright parts (the core, the rays and the
arcs) are drawn again, thick and soft, into a small offscreen image. That
image is shrunk once more for a wider blur and both are added back under the
sharp drawing. That is far cheaper than blurring a full-resolution frame.

Software QPainter only: no GPU, no new dependency. Everything that moves means
something: the spin rate is the assistant's state, and the core, the rays, the
arcs and the particles brighten and grow with the real audio level. The
palette is an electric cyan/ice-blue glow; muted uses the muted colour handed in
by the HUD. No downloaded pictures or image assets are involved.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPen,
                         QPolygonF, QRadialGradient)

_DISPLAY = ["Bahnschrift", "Segoe UI", "SF Pro Display", "Helvetica Neue",
            "Noto Sans", "DejaVu Sans"]

_CAM_D = 4.4            # perspective distance, in core radii
_MESH_R = 0.64          # radius of the wireframe sphere
_CORE_R = 0.12          # radius of the solid core
_N_RAYS = 24
_N_ARCS = 5
_N_ARC_PTS = 48
_N_BANDS = 5            # swirling particle bands
_N_BAND = 420           # particles per band
_N_SHELL = 600          # loose particles on the sphere's surface
_N_DUST = 260           # sparse outer dust
_GLOW_DIV = 4           # the glow image is this many times smaller than the widget

# Native FRIDAY palette: derive the glow from the live theme and state accent.
def _mix(a, b, amount):
    return QColor.fromRgbF(*(x + (y - x) * amount
                             for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))


def _energy_palette(main, acc, white, muted):
    if muted:
        return QColor(white), QColor(main), QColor(main), QColor(main)
    return (_mix(white, acc, .10), _mix(acc, white, .42),
            _mix(main, acc, .55), _mix(main, QColor("#060b16"), .60))


def _motion_targets(speaking, thinking, muted, state, amp):
    if muted:
        return .10, .42
    if speaking:
        return .82 + .30 * amp, .90 + .10 * amp
    if thinking:
        return 1.64, .92
    if state == "SLEEPING":
        return .12, .36
    if state in ("TEXT_READY", "PTT_READY", "IDLE", "ONLINE", "INITIALISING"):
        return .28, .64
    return .34 + .18 * amp, .72 + .28 * amp


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


def _icosphere(subdiv: int):
    """Vertices (3×N, unit length) and unique edges (M×2) of a geodesic sphere."""
    t = (1.0 + 5 ** 0.5) / 2.0
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
             (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    verts = [np.array(v, float) / np.linalg.norm(v) for v in verts]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
             (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
             (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(subdiv):
        cache = {}

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = verts[a] + verts[b]
                verts.append(m / np.linalg.norm(m))
                cache[key] = len(verts) - 1
            return cache[key]

        nf = []
        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = nf
    edges = set()
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add((min(u, v), max(u, v)))
    return np.array(verts).T, np.array(sorted(edges))


class Reactor3D:
    """State + renderer. `step()` advances it, `paint()` draws a frame."""

    # Vertical extent in core radii: the tip of the longest ray above the
    # centre, and the bottom of the name below it.
    TOP = 1.60
    BOTTOM = 1.85

    def __init__(self):
        rng = np.random.default_rng(57)

        # geodesic wireframe
        self._mesh_v, self._mesh_e = _icosphere(2)
        self._mesh_v = self._mesh_v * _MESH_R

        # rays: a direction in 3-D, a length, a width, a flicker phase and speed
        ang = (np.arange(_N_RAYS) + rng.uniform(-0.35, 0.35, _N_RAYS)) * (2 * math.pi / _N_RAYS)
        zr = rng.uniform(-0.35, 0.35, _N_RAYS)
        self._ray_dir = np.vstack([np.cos(ang), np.sin(ang), zr])
        self._ray_dir /= np.linalg.norm(self._ray_dir, axis=0)
        self._ray_len = rng.uniform(1.00, 1.55, _N_RAYS)
        self._ray_w = rng.uniform(0.7, 1.3, _N_RAYS)
        self._ray_ph = rng.uniform(0, 2 * math.pi, _N_RAYS)
        self._ray_sp = rng.uniform(0.8, 2.4, _N_RAYS)

        # thick arc segments on tilted planes, each turning round its own ring
        self._arcs = []
        for k_arc in range(_N_ARCS):
            tilt = (_rx(rng.uniform(-0.55, 0.55)) @ _ry(rng.uniform(-0.55, 0.55)))
            self._arcs.append(dict(
                tilt=tilt, radius=float(rng.uniform(0.80, 1.10)),
                span=float(rng.uniform(math.radians(50), math.radians(120))),
                speed=float(rng.uniform(0.5, 1.4)) * (1 if rng.uniform() < 0.5 else -1),
                phase=float((k_arc + rng.uniform(-0.25, 0.25)) * 2 * math.pi / _N_ARCS),
                width=float(rng.uniform(0.016, 0.030))))

        # Arc samples are fixed in each local plane; rotate the cached geometry.
        for arc in self._arcs:
            a = np.linspace(0.0, arc["span"], _N_ARC_PTS)
            arc["samples"] = np.vstack([np.cos(a), np.sin(a), np.zeros_like(a)])

        # swirling bands: particles on tilted rings, bunched into streams
        self._bands, self._band_ph, self._band_spd = [], [], []
        for _ in range(_N_BANDS):
            tilt = (_rz(rng.uniform(0, 2 * math.pi)) @ _rx(rng.uniform(0.0, 0.9))
                    @ _ry(rng.uniform(0, 2 * math.pi)))
            R = rng.uniform(0.80, 1.12)
            centres = rng.uniform(0, 2 * math.pi, 4)
            a = centres[rng.integers(0, 4, _N_BAND)] + rng.normal(0, 0.55, _N_BAND)
            rr = R + rng.normal(0, 0.05, _N_BAND)
            pts = np.vstack([np.cos(a) * rr, np.sin(a) * rr, rng.normal(0, 0.025, _N_BAND)])
            self._bands.append(tilt @ pts)
            self._band_ph.append(rng.uniform(0, 2 * math.pi, _N_BAND))
            self._band_spd.append(float(rng.uniform(0.4, 1.0)) * (1 if rng.uniform() < 0.5 else -1))

        # loose particles on the sphere and sparse dust outside it
        self._shell = _unit_vectors(rng, _N_SHELL) * rng.uniform(0.62, 0.98, _N_SHELL)
        self._shell_ph = rng.uniform(0, 2 * math.pi, _N_SHELL)
        self._dust = _unit_vectors(rng, _N_DUST) * rng.uniform(1.05, 1.45, _N_DUST)
        self._dust_ph = rng.uniform(0, 2 * math.pi, _N_DUST)

        self.spin = 0.0
        self.arc_spin = 0.0
        self.t = 0.0
        self._rate = .34
        self._energy = .72
        self._glow: QImage | None = None

    # ── motion ────────────────────────────────────────────────────────────────
    def step(self, dt: float, speaking: bool, thinking: bool, muted: bool,
             *, state: str = "", amp: float = 0.0) -> None:
        dt = min(0.10, max(0.0, dt))
        amp = 0.0 if muted or state in ("SLEEPING", "TEXT_READY") else max(0., min(1., amp))
        rate, energy = _motion_targets(speaking, thinking, muted, state, amp)
        # Smooth transitions, integrate angular velocity rather than multiplying
        # accumulated angle by the instantaneous volume (which teleports arcs).
        self._rate += (rate - self._rate) * (1.0 - math.exp(-dt / .22))
        self._energy += (energy - self._energy) * (1.0 - math.exp(-dt / .16))
        self.spin += dt * self._rate
        self.arc_spin += dt * self._rate * (1.0 + .6 * amp)
        self.t += dt

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _project(pts, cx, cy, r):
        s = _CAM_D / (_CAM_D - pts[2])
        return cx + pts[0] * s * r, cy - pts[1] * s * r, pts[2], s

    @staticmethod
    def _points(p, X, Y, alpha, col, size, levels=4):
        """A particle cloud, one drawPoints call per brightness level."""
        if len(X) == 0:
            return
        # Zero brightness means invisible; preserve the lowest nonzero bin.
        lv = np.clip(np.rint(alpha * levels).astype(np.int16), 0, levels)
        xs, ys = X.tolist(), Y.tolist()
        for k in range(1, levels + 1):
            idx = np.flatnonzero(lv == k).tolist()
            if not idx:
                continue
            pen = QPen(_with_alpha(col, k / levels), size * (0.8 + 0.15 * (k - 1)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPoints(QPolygonF([QPointF(xs[i], ys[i]) for i in idx]))

    def _arc_paths(self, cx, cy, r, spin, amp):
        """Projected points of every arc, with its depth and width."""
        out = []
        R_all = _rz(spin * 0.3)
        for arc in self._arcs:
            start = arc["phase"] + self.arc_spin * arc["speed"]
            rad = arc["radius"] * (1.0 + 0.04 * amp)
            pts = (R_all @ arc["tilt"] @ _rz(start)) @ arc["samples"] * rad
            X, Y, Z, _ = self._project(pts, cx, cy, r)
            out.append((X, Y, Z, arc["width"]))
        return out

    @staticmethod
    def _arc_segments(arcs):
        """Build each Qt line once; share it between glow and sharp passes."""
        result = []
        for X, Y, Z, width in arcs:
            xs, ys = X.tolist(), Y.tolist()
            front = ((Z[:-1] + Z[1:]) >= 0).tolist()
            lines = [QLineF(xs[k], ys[k], xs[k + 1], ys[k + 1])
                     for k in range(len(xs) - 1)]
            back_lines, front_lines = [], []
            for line, near in zip(lines, front):
                (front_lines if near else back_lines).append(line)
            result.append((lines, back_lines, front_lines, width))
        return result

    def _ray_tips(self, spin, amp):
        R = _rz(spin * 0.25) @ _ry(0.25 * math.sin(spin * 0.4))
        flick = 0.75 + 0.25 * np.sin(self.t * self._ray_sp + self._ray_ph)
        length = self._ray_len * (0.90 + 0.18 * amp) * flick
        return R @ (self._ray_dir * length), flick

    # ── glow: the bright parts, thick and soft, at a quarter resolution ───────
    def _draw_glow(self, cx, cy, r, box, pal, amp, dim, arcs, rays):
        hot, gold, orange, ember = pal
        w = max(8, int(box.width() / _GLOW_DIV))
        h = max(8, int(box.height() / _GLOW_DIV))
        if self._glow is None or self._glow.width() != w or self._glow.height() != h:
            self._glow = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img = self._glow
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        try:
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            q.scale(1.0 / _GLOW_DIV, 1.0 / _GLOW_DIV)
            q.translate(-box.left(), -box.top())
            (tx, ty, _tz, _), flick = rays
            for i in range(_N_RAYS):
                pen = QPen(_with_alpha(ember, 0.45 * dim * flick[i]), r * 0.045)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                q.setPen(pen)
                q.drawLine(QLineF(cx, cy, float(tx[i]), float(ty[i])))
            for lines, _back, _front, aw in arcs:
                pen = QPen(_with_alpha(ember, 0.55 * dim), r * aw * 3.0)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                q.setPen(pen)
                q.drawLines(lines)
            q.setPen(Qt.PenStyle.NoPen)
            gr = r * (0.55 + 0.20 * amp)
            g = QRadialGradient(cx, cy, gr)
            g.setColorAt(0.0, _with_alpha(gold, 0.85 * dim))
            g.setColorAt(0.25, _with_alpha(orange, 0.45 * dim))
            g.setColorAt(1.0, _with_alpha(ember, 0.0))
            q.setBrush(QBrush(g))
            q.drawEllipse(QPointF(cx, cy), gr, gr)
        finally:
            q.end()
        wide = img.scaled(max(2, w // 4), max(2, h // 4), Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        return img, wide

    # ── frame ─────────────────────────────────────────────────────────────────
    def paint(self, p: QPainter, cx: float, cy: float, r: float, main: QColor, acc: QColor,
              white: QColor, amp: float, live: bool, name: str = "",
              muted: bool = False) -> None:
        amp = 0.0 if muted else max(0.0, min(1.0, amp))
        pal = _energy_palette(main, acc, white, muted)
        dim = min(.50, self._energy) if muted else self._energy
        hot, gold, orange, ember = pal
        spin, t = self.spin, self.t
        energy = min(1.0, 0.80 + 0.35 * amp + (0.05 if live else 0.0))
        box = QRectF(cx - r * 1.9, cy - r * 1.9, r * 3.8, r * 3.8)

        arcs = self._arc_segments(self._arc_paths(cx, cy, r, spin, amp))
        tips3d, flick = self._ray_tips(spin, amp)
        rays = (self._project(tips3d, cx, cy, r), flick)
        glow, wide = self._draw_glow(cx, cy, r, box, pal, amp, dim, arcs, rays)

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        # 1. glow underneath everything
        p.setOpacity(0.70 + 0.20 * amp)
        p.drawImage(box, wide)
        p.setOpacity(0.50 + 0.20 * amp)
        p.drawImage(box, glow)
        p.setOpacity(1.0)

        R_mesh = _ry(spin * 0.5) @ _rx(spin * 0.17)

        # 2. particles: the swirling bands, the loose shell, the dust
        px = max(1.2, r * 0.0105)
        for i, pts in enumerate(self._bands):
            v = R_mesh @ _rz(spin * self._band_spd[i]) @ pts
            X, Y, Z, _ = self._project(v, cx, cy, r)
            tw = 0.45 + 0.55 * np.sin(self._band_ph[i] + t * 2.6) ** 2
            alpha = np.clip((0.30 + 0.70 * (Z + 1.3) / 2.6) * tw * dim * energy, 0, 1)
            self._points(p, X, Y, alpha, gold if i % 2 else orange, px)
        v = R_mesh @ self._shell
        X, Y, Z, _ = self._project(v, cx, cy, r)
        tw = 0.40 + 0.60 * np.sin(self._shell_ph + t * 3.1) ** 2
        alpha = np.clip((0.15 + 0.85 * (Z + 1.0) / 2.0) * tw * dim * energy, 0, 1)
        self._points(p, X, Y, alpha, orange, px * 0.9)
        v = _ry(spin * 0.2) @ self._dust
        X, Y, Z, _ = self._project(v, cx, cy, r)
        alpha = np.clip((0.25 + 0.45 * np.sin(self._dust_ph + t * 1.7) ** 2) * dim, 0, 1)
        self._points(p, X, Y, alpha, gold, px * 0.8, levels=3)

        # 3. geodesic wireframe, dimmer at the back
        v = R_mesh @ self._mesh_v
        X, Y, Z, _ = self._project(v, cx, cy, r)
        e0, e1 = self._mesh_e[:, 0], self._mesh_e[:, 1]
        zm = (Z[e0] + Z[e1]) / (2 * _MESH_R)
        lv = np.clip(((zm + 1.0) * 1.5).astype(np.int8), 0, 2).tolist()
        x0, y0, x1, y1 = X[e0].tolist(), Y[e0].tolist(), X[e1].tolist(), Y[e1].tolist()
        buckets = ([], [], [])
        for k, lvl in enumerate(lv):
            buckets[lvl].append(QLineF(x0[k], y0[k], x1[k], y1[k]))
        lw = max(0.9, r * 0.0050)
        for k, lines in enumerate(buckets):
            p.setPen(QPen(_with_alpha(orange, (0.32, 0.58, 0.90)[k] * dim * energy), lw))
            p.drawLines(lines)

        # 4. rays: straight, bright near the core, fading only near the tip
        (tx, ty, tz, _), flick = rays
        for i in range(_N_RAYS):
            x1r, y1r = float(tx[i]), float(ty[i])
            g = QLinearGradient(cx, cy, x1r, y1r)
            a = dim * float(flick[i]) * 0.85
            g.setColorAt(0.0, _with_alpha(hot, a))
            g.setColorAt(0.15, _with_alpha(gold, 0.95 * a))
            g.setColorAt(0.45, _with_alpha(orange, 0.90 * a))
            g.setColorAt(0.85, _with_alpha(ember, 0.70 * a))
            g.setColorAt(1.0, _with_alpha(ember, 0.0))
            pen = QPen(QBrush(g), max(1.0, r * 0.0095 * self._ray_w[i] * (1.0 + 0.4 * amp)))
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawLine(QLineF(cx, cy, x1r, y1r))

        # 5. thick arc segments: a cyan body with an ice-white line down the middle
        for _all, back, front, aw in arcs:
            for lines, k in ((back, 0.55), (front, 1.0)):
                if not lines:
                    continue
                for col, wmul, a in ((orange, 1.0, 0.90), (gold, 0.30, 0.70)):
                    pen = QPen(_with_alpha(col, a * k * dim * energy), max(1.5, r * aw * wmul))
                    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    p.setPen(pen)
                    p.drawLines(lines)

        # 6. the core: a solid white-hot ball with a crisp edge
        p.setPen(Qt.PenStyle.NoPen)
        cr = r * _CORE_R * (1.0 + 0.45 * amp)
        g = QRadialGradient(cx, cy, cr * 1.6)
        g.setColorAt(0.0, _with_alpha(hot, 1.0 * dim))
        g.setColorAt(0.45, _with_alpha(hot, 1.0 * dim))
        g.setColorAt(0.62, _with_alpha(gold, 0.95 * dim))
        g.setColorAt(1.0, _with_alpha(orange, 0.0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(cx, cy), cr * 1.6, cr * 1.6)

        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # the name, under the sphere
        if name:
            f = QFont()
            f.setFamilies(_DISPLAY)
            fpx = max(10, int(r * 0.11))
            f.setPixelSize(fpx)
            f.setWeight(QFont.Weight.Light)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(2.0, round(r * 0.035)))
            p.setFont(f)
            p.setPen(QPen(_with_alpha(white, 0.78 + 0.2 * min(1.0, amp * 2))))
            p.drawText(QRectF(cx - r * 1.6, cy + r * 1.50, r * 3.2, fpx * 1.8),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name)
        p.restore()
