"""Live, resolution-independent Gideon-style facial features.

This is NOT a portrait texture. The eye lenses, eyelids, brows, nose highlights,
cheeks and lips are drawn as vector paths every frame, with blinking, gaze,
speaking-mouth and head-pose data fed from HoloAvatar. The existing animated
3D mesh supplies the head, shoulders and scanline hologram surface.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QBrush, QLinearGradient, QPainter, QPainterPath, QPen,
    QRadialGradient,
)


CYAN = QColor(70, 225, 255)
ICE = QColor(178, 249, 255)


def face_layout(left: float, top: float, width: float, height: float) -> dict:
    """Stable facial proportions independent of window size or display DPI.

    The previous eye height was a fraction of the mesh eyelid aperture and
    appeared as two tiny dots. These eye proportions follow the requested
    refined portrait's much taller almond-shaped eyes.
    """
    if width <= 0 or height <= 0:
        raise ValueError("non-positive hologram face bounds")
    cx = left + width * 0.5
    return {
        "cx": cx,
        "eyes_y": top + height * 0.485,
        "eyes_x": (cx - width * 0.247, cx + width * 0.247),
        "eye_w": width * 0.276,
        "eye_h": height * 0.105,
        "brow_y": top + height * 0.389,
        "nose_y": top + height * 0.667,
        "mouth_y": top + height * 0.772,
        "mouth_w": width * 0.314,
        "mouth_h": height * 0.055,
        "cheek_y": top + height * 0.613,
    }


def _stroke(p: QPainter, path: QPainterPath, alpha: float = 1.0,
            scale: float = 1.0) -> None:
    """Crisp neon center surrounded by restrained additive scattering."""
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for thick, opacity in ((7.0, 17), (3.0, 48), (1.0, 195)):
        p.setPen(QPen(QColor(86, 235, 255, min(255, int(opacity * alpha))),
                      thick * scale, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
    p.restore()


def _eye_path(cx: float, cy: float, width: float, height: float,
              openness: float, side: int) -> tuple[QPainterPath, QPainterPath]:
    """Tear-duct taper, long curved upper lid and gentler lower eye contour."""
    x0, x1 = cx - width * .5, cx + width * .5
    hh = height * max(.015, min(1.0, openness))
    # Inner corners are lower than outer corners; mirror the two eyes.
    outer_y = cy - height * .075
    inner_y = cy + height * .105
    ya, yb = (outer_y, inner_y) if side < 0 else (inner_y, outer_y)

    upper = QPainterPath(QPointF(x0, ya))
    upper.cubicTo(x0 + width * .23, cy - hh * .75,
                  x0 + width * .70, cy - hh * .83,
                  x1, yb)
    lower = QPainterPath(QPointF(x1, yb))
    lower.cubicTo(x0 + width * .74, cy + hh * .53,
                  x0 + width * .28, cy + hh * .57,
                  x0, ya)
    aperture = QPainterPath(upper)
    aperture.connectPath(lower)
    aperture.closeSubpath()
    return upper, aperture


def _eyes(p: QPainter, layout: dict, openness: float,
          gaze: tuple[float, float], energy: float) -> None:
    eye_y = layout["eyes_y"]
    ew = layout["eye_w"]
    eh = layout["eye_h"]
    for side, ex in zip((-1, 1), layout["eyes_x"]):
        upper, opening = _eye_path(ex, eye_y, ew, eh, openness, side)
        if opening.isEmpty():
            continue
        # Dark translucent chamber creates depth behind neon eyelashes. No
        # white human eyeball and no PNG/photo overlay.
        bg = QLinearGradient(ex, eye_y - eh, ex, eye_y + eh)
        bg.setColorAt(0, QColor(6, 33, 77, 200))
        bg.setColorAt(.5, QColor(16, 126, 186, 130))
        bg.setColorAt(1, QColor(2, 23, 57, 190))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawPath(opening)

        p.save()
        p.setClipPath(opening)
        px = ex + float(gaze[0]) * ew * .115
        py = eye_y - float(gaze[1]) * eh * .14
        radius = min(ew * .235, eh * .49)
        iris = QRadialGradient(QPointF(px, py), radius)
        iris.setColorAt(0, QColor(0, 17, 40, 255))
        iris.setColorAt(.32, QColor(5, 52, 125, 250))
        iris.setColorAt(.57, QColor(14, 134, 219, 255))
        iris.setColorAt(.83, QColor(111, 238, 255, 245))
        iris.setColorAt(1, QColor(10, 113, 198, 90))
        p.setBrush(QBrush(iris))
        p.drawEllipse(QPointF(px, py), radius, radius)

        rings = ((.92, QColor(184, 251, 255, 225), 1.8),
                 (.66, QColor(37, 211, 252, 190), 1.0),
                 (.47, QColor(155, 240, 255, 115), .7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for fraction, color, thickness in rings:
            p.setPen(QPen(color, max(.6, thickness * max(.65, radius / 19))))
            p.drawEllipse(QPointF(px, py), radius * fraction, radius * fraction)

        p.setPen(QPen(QColor(159, 247, 255, 145), max(.5, radius * .028)))
        for i in range(36):
            angle = math.tau * i / 36.0
            ux, uy = math.cos(angle), math.sin(angle)
            p.drawLine(QPointF(px + ux * radius * .47, py + uy * radius * .47),
                       QPointF(px + ux * radius * .79, py + uy * radius * .79))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(1, 13, 35, 255))
        p.drawEllipse(QPointF(px, py), radius * .36, radius * .36)
        p.setBrush(QColor(214, 254, 255, 246))
        p.drawEllipse(QPointF(px - radius * .31, py - radius * .32),
                      max(1.0, radius * .16), max(1.0, radius * .16))
        p.setBrush(QColor(129, 244, 255, 185))
        p.drawEllipse(QPointF(px + radius * .35, py + radius * .28),
                      max(.5, radius * .085), max(.5, radius * .085))
        p.restore()

        _stroke(p, opening, .85 + energy * .11)
        _stroke(p, upper, 1.12, 1.05)

        # Upper lashes follow the upper Bezier's actual local tangent. Small
        # strokes, never giant cartoon fans.
        if openness > .3:
            for i in range(9):
                t = .12 + .72 * i / 8.0
                q = upper.pointAtPercent(t)
                # Pull away from the temple; lashes grow toward outer corner.
                away = (1.0 - t) if side < 0 else t
                length = eh * (.045 + .12 * away)
                lash = QPainterPath(q)
                lash.quadTo(q.x() + (-side) * length * .55,
                            q.y() - length * .85,
                            q.x() + (-side) * length * .75,
                            q.y() - length)
                _stroke(p, lash, .28 + .22 * away, .65)

        # Anatomical lid crease and softer sculpted brow. No straight, floating
        # underscore eyebrows.
        crease = QPainterPath(QPointF(ex - ew * .48, eye_y - eh * .63))
        crease.cubicTo(ex - ew * .10, eye_y - eh * 1.02,
                       ex + ew * .20, eye_y - eh * 1.05,
                       ex + ew * .48, eye_y - eh * .61)
        _stroke(p, crease, .30)
        brow_y = layout["brow_y"]
        brow = QPainterPath(QPointF(ex - ew * .57, brow_y + eh * .10))
        brow.cubicTo(ex - ew * .22, brow_y - eh * .37,
                     ex + ew * .19, brow_y - eh * .30,
                     ex + ew * .59, brow_y + eh * .12)
        _stroke(p, brow, .59, 1.1)


def _face_volume(p: QPainter, layout: dict, height: float, width: float) -> None:
    """Luminous nose anatomy and soft cheekbones without opaque skin."""
    cx = layout["cx"]
    nose = layout["nose_y"]
    cheek_y = layout["cheek_y"]
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for side in (-1, 1):
        center = QPointF(cx + side * width * .26, cheek_y)
        rad = width * .19
        light = QRadialGradient(center, rad)
        light.setColorAt(0, QColor(18, 146, 207, 30))
        light.setColorAt(.45, QColor(11, 125, 185, 13))
        light.setColorAt(1, QColor(4, 74, 134, 0))
        p.setBrush(QBrush(light))
        p.drawEllipse(center, rad, height * .13)
    p.restore()

    # Nose bridge, paired side relief and rounded nostril wings. The model
    # already provides the 3-D protrusion and scanline lighting beneath this.
    bridge = QPainterPath(QPointF(cx - width * .016, nose - height * .13))
    bridge.cubicTo(cx - width * .028, nose - height * .065,
                   cx - width * .017, nose - height * .023,
                   cx - width * .009, nose + height * .003)
    _stroke(p, bridge, .30)
    other = QPainterPath(QPointF(cx + width * .016, nose - height * .13))
    other.cubicTo(cx + width * .027, nose - height * .055,
                  cx + width * .028, nose - height * .019,
                  cx + width * .014, nose + height * .004)
    _stroke(p, other, .29)

    tip = QPainterPath(QPointF(cx - width * .064, nose - height * .005))
    tip.cubicTo(cx - width * .049, nose + height * .031,
                cx + width * .045, nose + height * .030,
                cx + width * .064, nose - height * .007)
    _stroke(p, tip, .61)
    for side in (-1.0, 1.0):
        wing = QPainterPath(QPointF(cx + side * width * .052, nose + height * .010))
        wing.quadTo(cx + side * width * .083, nose + height * .017,
                    cx + side * width * .071, nose + height * .034)
        _stroke(p, wing, .22)


def _lips(p: QPainter, layout: dict, mouth: float, energy: float) -> None:
    """Cupid's bow and full lower lip, with voice-driven viseme opening."""
    cx, cy = layout["cx"], layout["mouth_y"]
    w, h = layout["mouth_w"], layout["mouth_h"]
    left, right = cx - w * .5, cx + w * .5
    opened = max(0., min(1., float(mouth)))
    gap = h * .65 * opened
    corner_y = cy - h * .07
    top = QPainterPath(QPointF(left, corner_y))
    top.cubicTo(cx - w * .29, cy - h * .76,
                cx - w * .12, cy - h * .65,
                cx, cy - h * .39)
    top.cubicTo(cx + w * .12, cy - h * .65,
                cx + w * .29, cy - h * .76,
                right, corner_y)

    lower = QPainterPath(QPointF(right, corner_y))
    lower.cubicTo(cx + w * .34, cy + h * .91 + gap * .34,
                  cx - w * .34, cy + h * .96 + gap * .34,
                  left, corner_y)
    shape = QPainterPath(top)
    shape.connectPath(lower)
    shape.closeSubpath()
    ink = QLinearGradient(cx, cy - h, cx, cy + h * 1.25 + gap)
    ink.setColorAt(0, QColor(26, 156, 211, 138))
    ink.setColorAt(.42, QColor(7, 66, 123, 176))
    ink.setColorAt(.80, QColor(5, 102, 168, 146))
    ink.setColorAt(1, QColor(3, 49, 110, 48))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(ink))
    p.drawPath(shape)

    # Central speaking slit opens independently of the softly smiling outer
    # lip silhouette. At rest it is a naturally curved line, not a fish oval.
    slit = QPainterPath(QPointF(left, corner_y))
    slit.cubicTo(cx - w * .28, cy + gap * .12,
                 cx + w * .28, cy + gap * .12,
                 right, corner_y)
    if opened > .07:
        cavity = QPainterPath(slit)
        cavity.cubicTo(cx + w * .28, cy + gap * .9,
                       cx - w * .28, cy + gap * .9,
                       left, corner_y)
        cavity.closeSubpath()
        p.setBrush(QColor(0, 7, 24, int(140 + 70 * opened)))
        p.drawPath(cavity)
        _stroke(p, cavity, .36)
    _stroke(p, top, .63 + energy * .12)
    _stroke(p, lower, .61)
    _stroke(p, slit, .56)

    # Lower lip specular roll (highly reduced when speaking).
    shine = QPainterPath(QPointF(cx - w * .20, cy + h * .57 + gap * .20))
    shine.cubicTo(cx - w * .06, cy + h * .79 + gap * .2,
                  cx + w * .09, cy + h * .78 + gap * .2,
                  cx + w * .21, cy + h * .54 + gap * .20)
    _stroke(p, shine, (.28 - .14 * opened))


def paint_portrait(p: QPainter, left: float, top: float,
                   width: float, height: float, *,
                   eye_open: float = 1.0, gaze: tuple = (0., 0.),
                   mouth: float = 0., energy: float = 0.) -> None:
    """A frame of the face. Never reads an image file or caches a bitmap.

    This intentionally operates on the projected moving head bounds; there is
    no static portrait texture to lose lip sync or rotate incorrectly.
    """
    if width < 20 or height < 30:
        return
    layout = face_layout(left, top, width, height)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _face_volume(p, layout, height, width)
    _eyes(p, layout, max(0., min(1., float(eye_open))), gaze, energy)
    _lips(p, layout, mouth, energy)
    p.restore()
