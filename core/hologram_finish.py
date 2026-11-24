"""Finishing passes for the Gideon-inspired cyan female hologram.

The OpenGL shader provides real 3D, mouth animation, gaze and head rotation.
This layer adds the soft blue halo and curved silhouette of the reference
without adding a photographed human face or replacing the live 3D rig.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QBrush, QLinearGradient


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
        for div, margin, opacity in ((19, 31.0, .40), (7, 12.0, .17)):
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
            energy: float = 0.0, *, eye_open: float = 1.0,
            gaze=(0.0, 0.0), mouth: float = 0.0, face_features: bool = True) -> None:
    """Smooth blue face rim and two actual ear-shaped loops in screen space.

    They follow the 3D vertex projections every frame rather than sitting
    on a static face image. A high-detail vector overlay supplies the eyes,
    lips and brows, using the existing audio- and gaze-driven animation.
    """
    if len(xs) < n_head or n_head < 3:
        return
    head = _hull(zip(xs[:n_head], ys[:n_head]))
    if len(head) < 3:
        return
    outer = _smooth_hull(head)
    _neon_path(painter, outer, (.72 if face_features else .16) + .04 * energy)
    if not face_features:
        return

    left = min(x for x, _ in head)
    right = max(x for x, _ in head)
    top = min(y for _, y in head)
    bottom = max(y for _, y in head)
    half = (right - left) * 0.5
    height = max(1.0, bottom - top)
    center = 0.5 * (left + right)

    # A subtle swept-back hairline, drawn entirely with animated QPainter
    # curves. It follows this frame's projected 3D silhouette and never
    # replaces the live eyelids, lips, face mesh or head rotation with a photo.
    hairline = QPainterPath(QPointF(center - half * .72, top + height * .31))
    hairline.cubicTo(center - half * .55, top + height * .12,
                     center + half * .15, top + height * .13,
                     center + half * .68, top + height * .27)
    _neon_path(painter, hairline, .29 + .05 * energy)
    for side in (-1.0, 1.0):
        sweep = QPainterPath(QPointF(center + side * half * .63,
                                     top + height * .31))
        sweep.cubicTo(center + side * half * .83, top + height * .20,
                      center + side * half * .76, top + height * .11,
                      center + side * half * .43, top + height * .07)
        _neon_path(painter, sweep, .16 + .04 * energy)


    # Ear shells: compact, anatomically placed translucent forms with the
    # same fine glowing horizontal contours as the face. Previous C loops
    # floated outside the head like headphones.
    for idx in (234, 454):
        if idx >= len(xs):
            continue
        side = -1.0 if float(xs[idx]) < center else 1.0
        ex = float(xs[idx])
        ey = float(ys[idx])
        ear = QPainterPath(QPointF(ex, ey - height * .064))
        ear.cubicTo(ex + side * half * .22, ey - height * .12,
                    ex + side * half * .26, ey + height * .065,
                    ex + side * half * .08, ey + height * .110)
        ear.cubicTo(ex + side * half * .025, ey + height * .106,
                    ex - side * half * .010, ey - height * .003,
                    ex, ey - height * .064)
        painter.save()
        # Light passes through the ear; no solid skin or dark plastic fill.
        painter.setPen(Qt.PenStyle.NoPen)
        tint = QLinearGradient(QPointF(ex, ey - height * .13),
                               QPointF(ex + side * half * .25,
                                       ey + height * .12))
        tint.setColorAt(0.0, QColor(4, 112, 200, 48))
        tint.setColorAt(0.65, QColor(2, 46, 105, 78))
        tint.setColorAt(1.0, QColor(3, 153, 221, 30))
        painter.setBrush(QBrush(tint))
        painter.drawPath(ear)
        painter.setClipPath(ear)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        step = max(2.0, height / 120.0)
        row = ey - height * .12
        while row < ey + height * .13:
            painter.setPen(QPen(QColor(41, 188, 248, 73), .55))
            painter.drawLine(QPointF(ex - half * .35, row),
                             QPointF(ex + half * .35, row))
            row += step
        painter.restore()
        _neon_path(painter, ear, .53)

        inner = QPainterPath(QPointF(ex + side * half * .055,
                                    ey - height * .053))
        inner.cubicTo(ex + side * half * .165, ey - height * .047,
                      ex + side * half * .16, ey + height * .020,
                      ex + side * half * .068, ey + height * .063)
        _neon_path(painter, inner, .29)

    # Visual source of truth: a feminine, expressive face with properly sized
    # almond eyes and full lips. This is animated Qt vector drawing, not an
    # imported/generated picture, and uses the same moving projected 3D head.
    from core.gideon_portrait import paint_portrait
    paint_portrait(painter, left, top, right - left, height,
                   eye_open=eye_open, gaze=gaze, mouth=mouth, energy=energy)
