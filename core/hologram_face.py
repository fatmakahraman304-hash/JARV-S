"""Animated feminine face projection made from 3D scan contours, without a GPU."""
import numpy as np
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QColor, QPen, QPolygonF, QBrush, QPainterPath, QRadialGradient, QPainter
from PyQt6.QtCore import Qt


class ProjectionFace:
    def __init__(self, mesh):
        rest, faces = mesh["verts"], mesh["faces"]
        # Precompute barycentric contour endpoints once. Posed coordinates
        # animate the same stencil, including the audio-driven jaw.
        starts, ends, weights = [], [], []
        triangles = rest[faces]
        for level in np.linspace(-1.62, 1.02, 185):
            candidates = np.flatnonzero((triangles[:, :, 1].min(1) <= level) &
                                         (triangles[:, :, 1].max(1) > level))
            for face in faces[candidates]:
                crossings = []
                for i, j in ((0, 1), (1, 2), (2, 0)):
                    a, b = int(face[i]), int(face[j])
                    ya, yb = rest[a, 1], rest[b, 1]
                    if (ya <= level < yb) or (yb <= level < ya):
                        crossings.append((a, b, float((level - ya) / (yb - ya))))
                if len(crossings) == 2:
                    for a, b, w in crossings:
                        starts.append(a)
                        ends.append(b)
                        weights.append(w)
        self.head = rest[:, 1] >= -1.01
        self.faces = faces
        self.a = np.asarray(starts, dtype=np.int32)
        self.b = np.asarray(ends, dtype=np.int32)
        self.w = np.asarray(weights, dtype=np.float32)
        self.fade = mesh["fade"]
        self.landmarks = mesh["landmarks"]

    @staticmethod
    def _hull(points):
        points = sorted(set(points))
        def cross(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        def half(sequence):
            out = []
            for point in sequence:
                while len(out) > 1 and cross(out[-2], out[-1], point) <= 0:
                    out.pop()
                out.append(point)
            return out
        return half(points)[:-1] + half(reversed(points))[:-1]

    @staticmethod
    def _light_path(painter, path, strength=1.0, width=1.0):
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for thickness, alpha in ((26, 3), (12, 7), (4, 28), (1.2, 180)):
            painter.setPen(QPen(QColor(88, 222, 255, int(alpha * strength)),
                               thickness * width, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        painter.restore()

    def _bust(self, painter, xs, ys, amplitude):
        hull = self._hull(list(zip(xs[self.head].tolist(), ys[self.head].tolist())))
        left, right = min(x for x, y in hull), max(x for x, y in hull)
        top, chin = min(y for x, y in hull), float(ys[152])
        half, height = (right - left) * .5, chin - top
        cx = (left + right) * .5
        # The shoulder silhouette stays quiet while the voice rig moves the jaw.
        bust = QPainterPath(QPointF(cx - half * .50, chin - height * .08))
        bust.cubicTo(cx - half * .50, chin + height * .11,
                     cx - half * 1.15, chin + height * .13,
                     cx - half * 1.85, chin + height * .25)
        bust.quadTo(cx, chin + height * .29, cx + half * 1.85, chin + height * .25)
        bust.cubicTo(cx + half * 1.15, chin + height * .13,
                     cx + half * .50, chin + height * .11,
                     cx + half * .50, chin - height * .08)
        bust.closeSubpath()
        glow = QRadialGradient(QPointF(cx, chin), height * .65)
        glow.setColorAt(0, QColor(22, 174, 237, 60))
        glow.setColorAt(1, QColor(15, 109, 195, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawPath(bust)
        painter.save()
        painter.setClipPath(bust)
        for yy in np.arange(chin - height * .06, chin + height * .29, max(2.0, height / 125)):
            painter.setPen(QPen(QColor(88, 217, 255, 42), .65))
            painter.drawLine(QLineF(cx - half * 1.9, yy, cx + half * 1.9, yy))
        painter.restore()
        self._light_path(painter, bust, .58, .80)

        outline = QPainterPath()
        first = ((hull[-1][0] + hull[0][0]) * .5, (hull[-1][1] + hull[0][1]) * .5)
        outline.moveTo(*first)
        for i, point in enumerate(hull):
            following = hull[(i + 1) % len(hull)]
            outline.quadTo(point[0], point[1],
                           (point[0] + following[0]) * .5, (point[1] + following[1]) * .5)
        outline.closeSubpath()
        self._light_path(painter, outline, .90 + .10 * amplitude)

        # Ears are translucent light loops behind the face, aligned to the
        # measured outer eye/temple landmarks rather than a painted photograph.
        for landmark, side in ((234, -1), (454, 1)):
            ex, ey = float(xs[landmark]), float(ys[landmark])
            ear = QPainterPath(QPointF(ex, ey - height * .085))
            ear.cubicTo(ex + side * half * .23, ey - height * .15,
                        ex + side * half * .23, ey + height * .09,
                        ex + side * half * .06, ey + height * .12)
            ear.quadTo(ex - side * half * .03, ey + height * .04, ex, ey - height * .085)
            self._light_path(painter, ear, .48, .55)
            inner = QPainterPath(QPointF(ex + side * half * .06, ey - height * .07))
            inner.quadTo(ex + side * half * .15, ey + height * .01,
                         ex + side * half * .04, ey + height * .07)
            self._light_path(painter, inner, .38, .45)

    def paint(self, painter, xs, ys, normals, vertices, scan, amplitude, eye_open, gaze=(0.0, 0.0)):
        self._bust(painter, xs, ys, amplitude)
        # A transparent surface supplies depth beneath finer scan contours.
        faces = self.faces
        normal = normals[faces].mean(1)
        visible_faces = np.flatnonzero(normal[:, 2] > .02)
        visible_faces = visible_faces[np.argsort(vertices[faces[visible_faces], 2].mean(1))]
        painter.setPen(Qt.PenStyle.NoPen)
        light = np.array([-.4, .5, .75])
        for face_id in visible_faces:
            ids = faces[face_id]
            fade = float(self.fade[ids].mean())
            key = max(0.0, float(normal[face_id] @ light))
            # Keep only a dark, translucent 3D volume below the luminous
            # horizontal contours; never paint a solid blue human face.
            shade = 0.20 + 0.80 * key
            face_alpha = int(np.clip((17 + 35 * shade) * fade, 0, 70))
            painter.setBrush(QBrush(QColor(int(3 + 18 * shade),
                                          int(25 + 70 * shade),
                                          int(54 + 106 * shade), face_alpha)))
            painter.drawPolygon(QPolygonF([QPointF(float(xs[i]), float(ys[i])) for i in ids]))
        w = self.w
        ix = xs[self.a] * (1 - w) + xs[self.b] * w
        iy = ys[self.a] * (1 - w) + ys[self.b] * w
        nz = normals[self.a, 2] * (1 - w) + normals[self.b, 2] * w
        fade = self.fade[self.a] * (1 - w) + self.fade[self.b] * w
        height = vertices[self.a, 1] * (1 - w) + vertices[self.b, 1] * w
        energy = np.exp(-((height - scan) / .10) ** 2)
        rim = (1 - np.clip(nz, 0, 1)) ** 2
        strength = np.clip((.45 + .40 * rim + .13 * energy) *
                           fade * (.92 + .08 * amplitude), 0, 1).reshape(-1, 2).mean(1)
        visible = nz.reshape(-1, 2).mean(1) > -.08
        lines = np.stack((ix[::2], iy[::2], ix[1::2], iy[1::2]), axis=1)
        buckets = np.clip((strength * 8).astype(int), 0, 7)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for bucket in range(8):
            segments = [QLineF(*map(float, row)) for row in lines[visible & (buckets == bucket)]]
            if not segments:
                continue
            painter.setPen(QPen(QColor(60, 210, 255, 18 + bucket * 13), .70))
            painter.drawLines(segments)

        for name in ("eye_l", "eye_r", "lips_in", "brow_l", "brow_r"):
            ids = self.landmarks[name]
            if float(normals[ids, 2].mean()) < 0:
                continue
            x, y = xs[ids], ys[ids].copy()
            if name.startswith("eye"):
                y = y.mean() + (y - y.mean()) * max(0.02, eye_open)
            # Eyes are hollow hologram outlines; never add human pupils.
            points = [QPointF(float(xx), float(yy)) for xx, yy in zip(x, y)]
            if name.startswith(("eye", "lips")):
                points.append(points[0])
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            strength = .56 if name.startswith("eye") else .28 if name.startswith("brow") else .47
            self._light_path(painter, path, strength, .75)
        # Bridge, nostrils and nose wings remain tied to the real face mesh.
        for ids in ((193, 122, 196, 3, 51, 45, 44), (417, 351, 419, 248, 281, 275, 274),
                    (49, 48, 64, 98, 97, 2), (279, 278, 294, 327, 326, 2)):
            path = QPainterPath(QPointF(float(xs[ids[0]]), float(ys[ids[0]])))
            for i in ids[1:]:
                path.lineTo(float(xs[i]), float(ys[i]))
            self._light_path(painter, path, .50, .6)
