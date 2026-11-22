"""Animated male face projection made from scan contours, without a GPU."""
import numpy as np
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QColor, QPen, QPolygonF, QBrush
from PyQt6.QtCore import Qt


class ProjectionFace:
    def __init__(self, mesh):
        rest, faces = mesh["verts"], mesh["faces"]
        # Precompute barycentric contour endpoints once. Posed coordinates
        # animate the same stencil, including the audio-driven jaw.
        starts, ends, weights = [], [], []
        triangles = rest[faces]
        for level in np.linspace(-1.20, 1.02, 115):
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
        self.faces = faces
        self.a = np.asarray(starts, dtype=np.int32)
        self.b = np.asarray(ends, dtype=np.int32)
        self.w = np.asarray(weights, dtype=np.float32)
        self.fade = mesh["fade"]
        self.landmarks = mesh["landmarks"]

    def paint(self, painter, xs, ys, normals, vertices, scan, amplitude, eye_open):
        # Translucent light facets make the nose, brow and jaw readable
        # through the scan lines. There is no skin or hair material.
        faces = self.faces
        normal = normals[faces].mean(1)
        visible_faces = np.flatnonzero(normal[:, 2] > .02)
        visible_faces = visible_faces[np.argsort(vertices[faces[visible_faces], 2].mean(1))]
        painter.setPen(Qt.PenStyle.NoPen)
        for face_id in visible_faces:
            ids = faces[face_id]
            fade = float(self.fade[ids].mean())
            key = max(0.0, float(normal[face_id] @ np.array([-.4, .5, .75])))
            painter.setBrush(QBrush(QColor(93, 211, 255, int((12 + 48 * key) * fade))))
            painter.drawPolygon(QPolygonF([QPointF(float(xs[i]), float(ys[i])) for i in ids]))
        w = self.w
        ix = xs[self.a] * (1 - w) + xs[self.b] * w
        iy = ys[self.a] * (1 - w) + ys[self.b] * w
        nz = normals[self.a, 2] * (1 - w) + normals[self.b, 2] * w
        fade = self.fade[self.a] * (1 - w) + self.fade[self.b] * w
        height = vertices[self.a, 1] * (1 - w) + vertices[self.b, 1] * w
        energy = np.exp(-((height - scan) / .10) ** 2)
        strength = np.clip((.30 + .38 * np.maximum(nz, 0) + .45 * energy) *
                           fade * (.85 + .15 * amplitude), 0, 1).reshape(-1, 2).mean(1)
        visible = nz.reshape(-1, 2).mean(1) > -.08
        lines = np.stack((ix[::2], iy[::2], ix[1::2], iy[1::2]), axis=1)
        buckets = np.clip((strength * 6).astype(int), 0, 5)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for bucket in range(6):
            selected = lines[visible & (buckets == bucket)]
            segments = [QLineF(*map(float, row)) for row in selected]
            if not segments:
                continue
            glow = QColor(54, 172, 255, 12 + bucket * 3)
            painter.setPen(QPen(glow, 3.0))
            painter.drawLines(segments)
            painter.setPen(QPen(QColor(137, 232, 255, 35 + bucket * 33), .75))
            painter.drawLines(segments)

        # Measured eye and lip outlines stay part of the moving face.
        for name in ("eye_l", "eye_r", "lips_out", "lips_in", "brow_l", "brow_r"):
            ids = self.landmarks[name]
            if float(normals[ids, 2].mean()) < 0:
                continue
            x, y = xs[ids], ys[ids].copy()
            if name.startswith("eye"):
                y = y.mean() + (y - y.mean()) * max(0.02, eye_open)
            points = [QPointF(float(xx), float(yy)) for xx, yy in zip(x, y)]
            if name.startswith(("eye", "lips")):
                points.append(points[0])
            painter.setPen(QPen(QColor(162, 241, 255, 210 if name.startswith("eye") else 150), 1.0))
            painter.drawPolyline(QPolygonF(points))
