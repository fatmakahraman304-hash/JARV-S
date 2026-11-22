"""Finishing passes for the reference-style cyan male hologram.

The OpenGL shader provides real 3D, mouth animation, gaze and head rotation.
This layer adds the soft blue halo and curved silhouette of the reference
without adding a photographed human face or replacing the live 3D rig.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


def _hull(points):
    """Monotone-chain screen-space silhouette, deterministic for animated rigs."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def half(seq):
        out = []
        for point in seq:
            while len(out) > 1 and cross(out[-2], out[-1], point) <= 0:
                out.pop()
            out.append(point)
        return out[:-1]

    return half(pts) + half(reversed(pts))


def _smooth_hull(points):
    if len(points) < 3:
        return QPainterPath()
    points = [(float(x), float(y)) for x, y in points]
    a, b = points[-1], points[0]
    path = QPainterPath(QPointF((a[0] + b[0]) * .5, (a[1] + b[1]) * .5))
    for i, pt in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        path.quadTo(QPointF(*pt), QPointF((pt[0] + nxt[0]) * .5,
                                         (pt[1] + nxt[1]) * .5))
    path.closeSubpath()
    return path


def _neon_path(painter, path, intensity=1.0):
    """Layered additive scattering around a thin sharply defined cyan edge."""
    if path.isEmpty():
        return
    painter.save()
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for width, alpha in ((23, 10), (12, 20), (6, 37), (2.8, 85), (1.0, 170)):
        painter.setPen(QPen(QColor(24, 207, 255,
                                 min(255, int(alpha * intensity))), width,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
    painter.restore()


def bloom(painter: QPainter, image: QImage, x0: float, y0: float,
          energy: float = 0.0) -> None:
    """Software bloom over the real GPU render, with no expensive Gaussian pass.

    Downsampled smooth QImage gives large diffused blue light around the
    contour. Draw it first, then the full resolution image, so the thin 3D
    scanlines remain crisp. Work in logical pixels to respect high-DPI.
    """
    if image.isNull():
        return
    dpr = max(1.0, float(image.devicePixelRatio()))
    w, h = image.width() / dpr, image.height() / dpr
    if w < 10 or h < 10:
        return
    painter.save()
    try:
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        for div, margin, opacity in ((17, 20.0, .26), (6, 8.0, .12)):
            low = image.scaled(max(2, image.width() // div),
                               max(2, image.height() // div),
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            painter.setOpacity(min(.56, opacity * (1.0 + .20 * energy)))
            painter.drawImage(QRectF(x0 - margin, y0 - margin,
                                     w + 2 * margin, h + 2 * margin), low)
    finally:
        painter.restore()


def details(painter: QPainter, xs, ys, n_head: int, landmarks,
            energy: float = 0.0) -> None:
    """Smooth blue face rim and two actual ear-shaped loops in screen space.

    They follow the 3D vertex projections at every frame rather than sitting
    on a static face image. The scanline shader still owns lips and eyelids.
    """
    if len(xs) < n_head or n_head < 3:
        return
    head = _hull(zip(xs[:n_head], ys[:n_head]))
    if len(head) < 3:
        return
    outer = _smooth_hull(head)
    _neon_path(painter, outer, .80 + .11 * energy)

    left = min(x for x, _ in head)
    right = max(x for x, _ in head)
    top = min(y for _, y in head)
    bottom = max(y for _, y in head)
    half = (right - left) * 0.5
    height = max(1.0, bottom - top)
    center = 0.5 * (left + right)

    # Explicit ears avoid the vertical square side protrusions of the old
    # simple canonical head: narrow C-shaped helix, darker center, thin rim.
    for idx in (234, 454):
        if idx >= len(xs):
            continue
        side = -1.0 if float(xs[idx]) < center else 1.0
        ex = float(xs[idx])
        ey = float(ys[idx])
        ear = QPainterPath(QPointF(ex, ey - height * .10))
        ear.cubicTo(ex + side * half * .27, ey - height * .14,
                    ex + side * half * .29, ey + height * .10,
                    ex + side * half * .07, ey + height * .16)
        ear.cubicTo(ex - side * half * .015, ey + height * .14,
                    ex + side * half * .035, ey - height * .01,
                    ex, ey - height * .10)
        _neon_path(painter, ear, .64)

        inner = QPainterPath(QPointF(ex + side * half * .08,
                                    ey - height * .07))
        inner.cubicTo(ex + side * half * .16, ey - height * .02,
                      ex + side * half * .16, ey + height * .05,
                      ex + side * half * .07, ey + height * .09)
        _neon_path(painter, inner, .33)
