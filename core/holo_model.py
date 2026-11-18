"""core/holo_model.py — the models on JARVIS's hologram table, as geometry.

A model is what Gemini rebuilds from camera photos (core/holo_scan.py): a list
of parts in centimetres, y up, origin at the bottom centre, +z toward the
camera of the first photo. Parts are not toy blocks: besides boxes, cylinders
and spheres there are rounded boxes (devices, cases), lathe profiles (bottles,
cups, lamps, wheels), extruded outlines (phones, brackets, logos, silhouettes)
and tubes along a path (cables, handles, frames), each with a real material —
colour, metalness, roughness, glow, transparency. The photo itself is
projected onto the front of the model, so a scanned mug wears its own print.

This file is numpy only (no Qt), so the tests build every shape headless.
gui/holo_gl.py draws the result.
"""
from __future__ import annotations

import math
import re
import struct

import numpy as np
from pathlib import Path

EXPLODE = 0.85                    # how far apart "parçala" pushes the parts (× their distance from the centre)
SHAPES = ("box", "rounded_box", "cylinder", "cone", "sphere", "hemisphere", "capsule", "torus",
          "wedge", "lathe", "extrude", "tube", "loft")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# surface finishes the shader draws procedurally (index = id in the vertex data)
FINISHES = ("none", "brushed", "carbon", "leather", "fabric", "wood", "knurl", "rubber", "paint", "matte", "concrete", "glass")
MAX_PARTS, MAX_INSTANCES = 500, 3000


# ── cleaning what the model returns ───────────────────────────────────────────

def _num(v, d):
    try:
        f = float(v)
        return f if math.isfinite(f) else d
    except (TypeError, ValueError):
        return d


def _vec(a, d):
    a = a if isinstance(a, (list, tuple)) else []
    return [_num(a[i] if i < len(a) else None, d[i]) for i in range(3)]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _points2(a, lo=-1.0, hi=1.0, limit=200):
    out = []
    for p in (a if isinstance(a, (list, tuple)) else [])[:limit]:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = _num(p[0], None), _num(p[1], None)
            if x is not None and y is not None:
                out.append([_clamp(x, lo, hi), _clamp(y, lo, hi)])
    return out


def clean_part(p, i: int = 0) -> dict:
    p = p if isinstance(p, dict) else {}
    shape = str(p.get("shape") or "box").lower().strip()
    shape = {"roundedbox": "rounded_box", "rounded box": "rounded_box", "ellipsoid": "sphere",
             "revolve": "lathe", "extrusion": "extrude", "pipe": "tube", "cuboid": "box"}.get(shape, shape)
    if shape not in SHAPES:
        shape = "box"
    size = [_clamp(abs(v), 0.05, 2000.0) for v in _vec(p.get("size"), [5, 5, 5])]
    out = {
        "name": str(p.get("name") or f"parça {i + 1}")[:48],
        "shape": shape, "size": size,
        "pos": [_clamp(v, -4000, 4000) for v in _vec(p.get("pos"), [0, size[1] / 2, 0])],
        "rot": [((v % 360) + 360) % 360 for v in _vec(p.get("rot"), [0, 0, 0])],
        "color": p.get("color") if _HEX.match(str(p.get("color") or "")) else "#9aa0a6",
        "metal": _clamp(_num(p.get("metal"), 0.0), 0.0, 1.0),
        "rough": _clamp(_num(p.get("rough"), 0.5), 0.04, 1.0),
        "emissive": _clamp(_num(p.get("emissive"), 0.0), 0.0, 1.0),
        "opacity": _clamp(_num(p.get("opacity"), 1.0), 0.08, 1.0),
        "finish": str(p.get("finish") or "none").lower() if str(p.get("finish") or "none").lower() in FINISHES else "none",
    }
    mir = str(p.get("mirror") or "").lower()
    if mir in ("x", "z", "xz"):
        out["mirror"] = mir
    arr = p.get("array")
    if isinstance(arr, dict):
        n = int(_clamp(_num(arr.get("count"), 1), 1, 64))
        if n > 1:
            out["array"] = {"count": n, "step": [_clamp(v, -500, 500) for v in _vec(arr.get("step"), [size[0] * 1.2, 0, 0])],
                            **({"rot": [_clamp(v, -180, 180) for v in _vec(arr.get("rot"), [0, 0, 0])]} if arr.get("rot") else {})}
    rad = p.get("radial")
    if isinstance(rad, dict):
        n = int(_clamp(_num(rad.get("count"), 1), 1, 72))
        if n > 1:
            ax = str(rad.get("axis") or "y").lower()
            out["radial"] = {"count": n, "axis": ax if ax in ("x", "y", "z") else "y",
                             "center": [_clamp(v, -4000, 4000) for v in _vec(rad.get("center"), [0, out["pos"][1], 0])]}
    if shape == "rounded_box":
        out["radius"] = _clamp(_num(p.get("radius"), min(size) * 0.15), 0.0, min(size) / 2)
    if shape == "lathe":
        prof = _points2(p.get("profile"), 0.0, 1.0)
        out["profile"] = prof if len(prof) >= 2 else [[1, 0], [1, 1]]
    if shape == "extrude":
        pts = _points2(p.get("outline"))
        out["outline"] = pts if len(pts) >= 3 else [[-1, -1], [1, -1], [1, 1], [-1, 1]]
        out["bevel"] = _clamp(_num(p.get("bevel"), 0.0), 0.0, min(size) / 3)
    if shape == "loft":
        secs = []
        for q in (p.get("sections") if isinstance(p.get("sections"), list) else [])[:40]:
            if isinstance(q, (list, tuple)) and len(q) >= 3:
                v = [_num(x, 0.0) for x in list(q)[:5]] + [0.0] * (5 - min(5, len(q)))
                secs.append([_clamp(v[0], 0, 1), _clamp(v[1], 0, 1), _clamp(v[2], 0, 1), _clamp(v[3], -1, 1), _clamp(v[4], -1, 1)])
        secs.sort(key=lambda r: r[0])
        out["sections"] = secs if len(secs) >= 2 else [[0, 1, 1, 0, 0], [1, 1, 1, 0, 0]]
        out["round"] = _clamp(_num(p.get("round"), 2.0), 1.2, 10.0)
    if shape == "tube":
        path = []
        for q in (p.get("path") if isinstance(p.get("path"), list) else [])[:120]:
            v = _vec(q, [None, None, None])
            if None not in v:
                path.append([_clamp(c, -4000, 4000) for c in v])
        out["path"] = path if len(path) >= 2 else [[0, -size[1] / 2, 0], [0, size[1] / 2, 0]]
    return out


def _drop_strays(parts: list) -> list:
    """Parts far away from the rest are mistakes (wrong units, a position given
    relative to another part): they make the model 6 m tall and float around it
    as specks. Keep what sits with the main body."""
    if len(parts) < 6:
        return parts
    c = np.array([p["pos"] for p in parts], float)
    r = np.array([max(p["size"]) / 2 for p in parts], float)
    big = r >= np.percentile(r, 40)                          # the body: the larger half of the parts
    lo = np.percentile(c[big] - r[big, None], 10, axis=0)
    hi = np.percentile(c[big] + r[big, None], 90, axis=0)
    span = max(float(np.max(hi - lo)), 1.0)
    keep = [p for p, ci in zip(parts, c) if np.all(ci > lo - span * 0.6) and np.all(ci < hi + span * 0.6)]
    return keep if len(keep) >= len(parts) * 0.6 else parts


def clean(m) -> dict:
    m = m if isinstance(m, dict) else {}
    if m.get("glb"):                                         # a real scanned mesh: the geometry is in the file
        return {k: m.get(k) for k in ("name", "summary", "glb", "height_cm", "provider", "source_image", "prompt", "id", "created", "upright")} | \
               {"parts": m.get("parts") if isinstance(m.get("parts"), list) else [], "photo": "", "photo_box": None,
                "name": str(m.get("name") or "3B model")[:60], "summary": str(m.get("summary") or "")[:500]}
    parts = [clean_part(p, i) for i, p in enumerate((m.get("parts") if isinstance(m.get("parts"), list) else [])[:MAX_PARTS])]
    parts = _drop_strays(parts)
    box = m.get("photo_box")
    box = [_clamp(_num(v, 0), 0, 1) for v in box[:4]] if isinstance(box, list) and len(box) >= 4 else None
    if box and (box[2] - box[0] < 0.02 or box[3] - box[1] < 0.02):
        box = None
    return {"name": str(m.get("name") or "Model")[:60], "summary": str(m.get("summary") or "")[:500],
            "parts": parts, "id": str(m.get("id") or ""), "created": str(m.get("created") or ""),
            "photo": m.get("photo") if isinstance(m.get("photo"), str) and len(m.get("photo")) < 1_500_000 else "",
            "photo_box": box, "draft": bool(m.get("draft"))}


# ── surfaces: (V, N | None, F) in part space, real centimetres ─────────────

def catmull(points, per: int = 6, closed: bool = False) -> np.ndarray:
    """Smooth a polyline through its points (Catmull-Rom), `per` samples a span."""
    P = np.asarray(points, np.float64)
    if len(P) < 3:
        return P
    ext = np.vstack([P[-1:], P, P[:2]]) if closed else np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    spans = len(P) if closed else len(P) - 1
    for i in range(spans):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        for k in range(per):
            t = k / per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return np.asarray(out)


def _grid_faces(rows: int, cols: int, wrap: bool) -> np.ndarray:
    """Triangles of a rows×cols vertex grid (cols wraps around when wrap)."""
    f = []
    cmax = cols if wrap else cols - 1
    for r in range(rows - 1):
        for c in range(cmax):
            a, b = r * cols + c, r * cols + (c + 1) % cols
            d, e = a + cols, b + cols
            f.append((a, b, e)); f.append((a, e, d))
    return np.asarray(f, np.int32).reshape(-1, 3)


def _fan(n: int, offset: int, reverse: bool) -> list:
    tri = [(offset, offset + i, offset + i + 1) for i in range(1, n - 1)]
    return [(a, c, b) for a, b, c in tri] if reverse else tri


def _lathe(profile, rx: float, rz: float, y0: float, h: float, seg: int = 96, corner_deg: float = 42.0, smooth: bool = True,
           caps: bool = True):
    """profile: [[r 0..1, y 0..1]] bottom → top. Smooth runs between sharp
    corners, flat caps where the profile ends away from the axis."""
    pr = [(float(r), float(y)) for r, y in profile]
    # split at sharp corners
    runs, cur = [], [pr[0]]
    for i in range(1, len(pr)):
        cur.append(pr[i])
        if 0 < i < len(pr) - 1:
            a = (pr[i][0] - pr[i - 1][0], pr[i][1] - pr[i - 1][1])
            b = (pr[i + 1][0] - pr[i][0], pr[i + 1][1] - pr[i][1])
            la, lb = math.hypot(*a), math.hypot(*b)
            if la > 1e-9 and lb > 1e-9:
                cosang = (a[0] * b[0] + a[1] * b[1]) / (la * lb)
                if cosang < math.cos(math.radians(corner_deg)):
                    runs.append(cur); cur = [pr[i]]
    runs.append(cur)
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    out = []
    for run in runs:
        if len(run) < 2:
            continue
        if len(run) >= 3 and smooth:
            run = [(max(0.0, r), y) for r, y in catmull(run, 8)]
        rows = len(run)
        V = np.zeros((rows * seg, 3), np.float32)
        for k, (r, y) in enumerate(run):
            V[k * seg:(k + 1) * seg, 0] = ca * r * rx
            V[k * seg:(k + 1) * seg, 1] = y0 + y * h
            V[k * seg:(k + 1) * seg, 2] = sa * r * rz
        F = _grid_faces(rows, seg, True)
        # outward winding: flip when the profile goes downward
        out.append((V, None, F[:, ::-1].copy()))
    for (r, y), top in ((pr[0], False), (pr[-1], True)):
        if caps and r > 1e-4:
            V = np.zeros((seg + 1, 3), np.float32)
            V[0] = (0, y0 + y * h, 0)
            V[1:, 0], V[1:, 1], V[1:, 2] = ca * r * rx, y0 + y * h, sa * r * rz
            F = np.asarray([(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)], np.int32)
            out.append((V, np.tile([0, 1 if top else -1, 0], (seg + 1, 1)).astype(np.float32), F if not top else F[:, ::-1].copy()))
    return out


def _sphere_profile(a0: float, a1: float, steps: int, y_lo=0.0, y_hi=1.0):
    pts = []
    for i in range(steps + 1):
        t = a0 + (a1 - a0) * i / steps
        r = math.cos(t)
        pts.append([0.0 if abs(r) < 1e-6 else r, y_lo + (math.sin(t) - math.sin(a0)) / (math.sin(a1) - math.sin(a0)) * (y_hi - y_lo)])
    return pts


def _box(sx, sy, sz):
    h = np.array([sx, sy, sz], np.float32) / 2
    out = []
    for axis in range(3):
        for sgn in (-1, 1):
            u, v = [(1, 2), (2, 0), (0, 1)][axis]
            V = np.zeros((4, 3), np.float32)
            for k, (a, b) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
                V[k, axis] = sgn * h[axis]; V[k, u] = a * h[u]; V[k, v] = b * h[v]
            F = np.asarray([(0, 1, 2), (0, 2, 3)], np.int32)
            n = np.zeros(3, np.float32); n[axis] = sgn
            out.append((V, np.tile(n, (4, 1)), F if sgn > 0 else F[:, ::-1].copy()))
    return out


def _rounded_box(sx, sy, sz, r, n: int = 12):
    h = np.array([sx, sy, sz], np.float64) / 2
    r = min(r, *(h * 0.999))
    if r < 1e-3:
        return _box(sx, sy, sz)
    inner = h - r
    # samples only where the surface bends: the flat middle of each face is one
    # span, the round-over gets n steps (per axis: its own edge fraction)
    def axis_samples(j):
        c = inner[j] / h[j]
        ramp = c + (1 - c) * np.sin(np.linspace(0, np.pi / 2, n // 2 + 2))
        return np.unique(np.round(np.concatenate([-ramp[::-1], ramp]), 6))
    S3 = [axis_samples(j) for j in range(3)]
    out = []
    for axis in range(3):
        for sgn in (-1, 1):
            u, v = [(1, 2), (2, 0), (0, 1)][axis]
            su, sv = S3[u], S3[v]
            G = np.zeros((len(su) * len(sv), 3))
            uu, vv = np.meshgrid(su, sv, indexing="ij")
            G[:, axis] = sgn * h[axis]
            G[:, u] = uu.ravel() * h[u]
            G[:, v] = vv.ravel() * h[v]
            core = np.clip(G, -inner, inner)
            d = G - core
            ln = np.linalg.norm(d, axis=1, keepdims=True)
            N = np.where(ln > 1e-9, d / np.maximum(ln, 1e-9), 0)
            N[ln[:, 0] <= 1e-9, axis] = sgn
            V = core + N * r
            F = _grid_faces(len(su), len(sv), False)
            if (sgn > 0) == (axis == 1):
                F = F[:, ::-1]
            out.append((V.astype(np.float32), N.astype(np.float32), F.copy()))
    # fix winding per surface by checking against the normals
    fixed = []
    for V, N, F in out:
        tri = V[F]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        if (fn * N[F].mean(1)).sum() < 0:
            F = F[:, ::-1].copy()
        fixed.append((V, N, F))
    return fixed


def _torus(sx, sy, sz, n1=96, n2=32):
    R, r = 0.35, 0.15
    a = np.linspace(0, 2 * np.pi, n1, endpoint=False)[:, None]
    b = np.linspace(0, 2 * np.pi, n2, endpoint=False)[None, :]
    x = np.cos(a) * (R + r * np.cos(b)); z = np.sin(a) * (R + r * np.cos(b)); y = np.sin(b) * 0.5 + 0 * a
    V = np.stack([x.ravel() * sx, y.ravel() * sy, z.ravel() * sz], 1).astype(np.float32)
    F = []
    for i in range(n1):
        for j in range(n2):
            p, q = i * n2 + j, ((i + 1) % n1) * n2 + j
            p2, q2 = i * n2 + (j + 1) % n2, ((i + 1) % n1) * n2 + (j + 1) % n2
            F += [(p, p2, q2), (p, q2, q)]
    return [(V, None, np.asarray(F, np.int32))]


def _wedge(sx, sy, sz):
    h = np.array([sx, sy, sz]) / 2
    P = np.array([[-1, -1, -1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [-1, 1, 1]], float) * h
    faces = [[0, 2, 1], [3, 4, 5], [0, 1, 4, 3], [0, 3, 5, 2], [1, 2, 5, 4]]
    out = []
    for f in faces:
        V = P[f].astype(np.float32)
        out.append((V, None, np.asarray(_fan(len(f), 0, False), np.int32)))
    return out


def _ear_clip(poly: np.ndarray) -> list:
    """Triangles of a simple polygon (counter-clockwise), by ear clipping."""
    idx = list(range(len(poly)))
    area = 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in idx)
    if area < 0:
        idx.reverse()
    tris, guard = [], 0

    def inside(p, a, b, c):
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2)); idx.pop(k)
            break
        else:
            break                                   # self-intersecting: fan the rest
    if len(idx) >= 3:
        tris += [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
    return tris


def _extrude(outline, sx, sy, sz, smooth_deg: float = 32.0):
    P = np.asarray(outline, np.float64) * [sx / 2, sy / 2]
    keep = [0] + [i for i in range(1, len(P)) if np.linalg.norm(P[i] - P[i - 1]) > 1e-6]
    P = P[keep]
    if len(P) > 3 and np.linalg.norm(P[0] - P[-1]) < 1e-6:
        P = P[:-1]
    if len(P) < 3:
        return _box(sx, sy, sz)
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    if area < 0:
        P = P[::-1]
    tris = _ear_clip(P)
    z = sz / 2
    out = []
    for zz, nz in ((z, 1), (-z, -1)):
        V = np.column_stack([P[:, 0], P[:, 1], np.full(len(P), zz)]).astype(np.float32)
        F = np.asarray(tris, np.int32) if nz > 0 else np.asarray(tris, np.int32)[:, ::-1].copy()
        out.append((V, np.tile([0, 0, nz], (len(P), 1)).astype(np.float32), F))
    # sides: smooth across gentle turns, hard at corners
    n = len(P)
    edge_n = []
    for i in range(n):
        d = P[(i + 1) % n] - P[i]
        nn = np.array([d[1], -d[0]]); edge_n.append(nn / (np.linalg.norm(nn) or 1))
    edge_n = np.asarray(edge_n)
    start = 0
    for i in range(n):                              # rotate so a corner comes first
        a, b = edge_n[i - 1], edge_n[i]
        if a @ b < math.cos(math.radians(smooth_deg)):
            start = i; break
    order = [(start + i) % n for i in range(n)]
    runs, cur = [], [order[0]]
    for k in range(1, n + 1):
        i = order[k % n]
        cur.append(i)
        a, b = edge_n[(i - 1) % n], edge_n[i]
        if a @ b < math.cos(math.radians(smooth_deg)) or k == n:
            runs.append(cur); cur = [i]
    for run in runs:
        m = len(run)
        V = np.zeros((m * 2, 3), np.float32); N = np.zeros((m * 2, 3), np.float32)
        for k, i in enumerate(run):
            if k == 0:
                nn = edge_n[i]
            elif k == m - 1:
                nn = edge_n[(i - 1) % n]
            else:
                nn = edge_n[(i - 1) % n] + edge_n[i]; nn = nn / (np.linalg.norm(nn) or 1)
            V[k] = (P[i][0], P[i][1], -z); V[m + k] = (P[i][0], P[i][1], z)
            N[k] = N[m + k] = (nn[0], nn[1], 0)
        F = []
        for k in range(m - 1):
            F += [(k, k + 1, m + k + 1), (k, m + k + 1, m + k)]
        out.append((V, N, np.asarray(F, np.int32)))
    return out


def _tube(path, radius, seg: int = 32):
    P = catmull(path, 14) if len(path) >= 3 else np.asarray(path, np.float64)
    if len(P) < 2:
        return []
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    ref = np.array([0, 1, 0]) if abs(T[0][1]) < 0.9 else np.array([1, 0, 0])
    Nn = np.cross(T[0], ref); Nn /= np.linalg.norm(Nn) or 1
    frames = []
    for i in range(len(P)):                          # parallel transport
        if i:
            Nn = Nn - T[i] * (Nn @ T[i]); Nn /= np.linalg.norm(Nn) or 1
        frames.append((Nn, np.cross(T[i], Nn)))
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    V = np.zeros((len(P) * seg, 3)); N = np.zeros_like(V)
    for i, (a, b) in enumerate(frames):
        ring = np.outer(np.cos(ang), a) + np.outer(np.sin(ang), b)
        N[i * seg:(i + 1) * seg] = ring
        V[i * seg:(i + 1) * seg] = P[i] + ring * radius
    F = _grid_faces(len(P), seg, True)
    out = [(V.astype(np.float32), N.astype(np.float32), F)]
    for i, sgn in ((0, -1), (len(P) - 1, 1)):        # end caps
        Vc = np.vstack([P[i], V[i * seg:(i + 1) * seg]]).astype(np.float32)
        Fc = np.asarray([(0, 1 + k, 1 + (k + 1) % seg) for k in range(seg)], np.int32)
        out.append((Vc, np.tile(T[i] * sgn, (seg + 1, 1)).astype(np.float32), Fc if sgn < 0 else Fc[:, ::-1].copy()))
    return out


def _loft(sections, rnd, sx, sy, sz, seg: int = 96):
    """A body through cross-sections stacked along y: [[y, width, depth, dx, dz]]
    (fractions of the part's size), each a superellipse — 2 round, 4+ boxy."""
    S = np.asarray(sections, np.float64)
    if len(S) >= 3:
        S = catmull(S, 10)
        S[:, 1:3] = np.clip(S[:, 1:3], 0, None)
    t = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    ct, st = np.cos(t), np.sin(t)
    e = 2.0 / rnd
    ux, uz = np.sign(ct) * np.abs(ct) ** e, np.sign(st) * np.abs(st) ** e
    rows = len(S)
    V = np.zeros((rows * seg, 3), np.float32)
    for k, (y, w, d, dx, dz) in enumerate(S):
        V[k * seg:(k + 1) * seg, 0] = dx * sx / 2 + ux * w * sx / 2
        V[k * seg:(k + 1) * seg, 1] = -sy / 2 + y * sy
        V[k * seg:(k + 1) * seg, 2] = dz * sz / 2 + uz * d * sz / 2
    out = [(V, None, _grid_faces(rows, seg, True)[:, ::-1].copy())]
    for k, top in ((0, False), (rows - 1, True)):
        if S[k][1] > 1e-3 and S[k][2] > 1e-3:
            ring = V[k * seg:(k + 1) * seg]
            Vc = np.vstack([ring.mean(0), ring]).astype(np.float32)
            Fc = np.asarray([(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)], np.int32)
            out.append((Vc, np.tile([0, 1 if top else -1, 0], (seg + 1, 1)).astype(np.float32), Fc))
    return out


def surfaces(p: dict) -> list:
    """The part's surfaces in its own frame (centred, not yet rotated)."""
    sx, sy, sz = p["size"]
    s = p["shape"]
    if s == "box":
        return _box(sx, sy, sz)
    if s == "rounded_box":
        return _rounded_box(sx, sy, sz, p.get("radius", min(sx, sy, sz) * 0.15))
    if s == "cylinder":
        return _lathe([[1, 0], [1, 1]], sx / 2, sz / 2, -sy / 2, sy)
    if s == "cone":
        return _lathe([[1, 0], [0, 1]], sx / 2, sz / 2, -sy / 2, sy)
    if s == "sphere":
        return _lathe(_sphere_profile(-math.pi / 2, math.pi / 2, 48), sx / 2, sz / 2, -sy / 2, sy, corner_deg=80, smooth=False)
    if s == "hemisphere":
        return _lathe(_sphere_profile(0, math.pi / 2, 24), sx / 2, sz / 2, -sy / 2, sy, corner_deg=80, smooth=False)
    if s == "capsule":
        cap = min(0.5, (sx / 2) / max(sy, 1e-6))
        prof = [[r, y * cap] for r, y in _sphere_profile(-math.pi / 2, 0, 16)] + \
               [[r, 1 - cap + y * cap] for r, y in _sphere_profile(0, math.pi / 2, 16)]
        return _lathe(prof, sx / 2, sz / 2, -sy / 2, sy, corner_deg=80, smooth=False)
    if s == "torus":
        return _torus(sx, sy, sz)
    if s == "wedge":
        return _wedge(sx, sy, sz)
    if s == "lathe":                                 # open where the profile does not reach the axis (rims, tyres, rings)
        return _lathe(p["profile"], sx / 2, sz / 2, -sy / 2, sy, caps=False)
    if s == "extrude":
        return _extrude(p["outline"], sx, sy, sz)
    if s == "tube":
        return _tube(p["path"], sx / 2)
    if s == "loft":
        return _loft(p["sections"], p.get("round", 2.0), sx, sy, sz)
    return _box(sx, sy, sz)


# ── maths ─────────────────────────────────────────────────────────────────────

def rot_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """Degrees, applied X then Y then Z."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    X = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Y = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Z = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Z @ Y @ X


def vertex_normals(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    N = np.zeros_like(V, dtype=np.float64)
    if len(F):
        tri = V[F].astype(np.float64)
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])     # area weighted
        for k in range(3):
            np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1, keepdims=True)
    return (N / np.maximum(ln, 1e-12)).astype(np.float32)


_SURF_CACHE: dict = {}


def _cached_surfaces(p: dict):
    key = (p["shape"], tuple(round(v, 4) for v in p["size"]), p.get("radius"), str(p.get("profile")), str(p.get("outline")),
           str(p.get("path")), str(p.get("sections")), p.get("round"))
    hit = _SURF_CACHE.get(key)
    if hit is None:
        if len(_SURF_CACHE) > 400:
            _SURF_CACHE.clear()
        hit = _SURF_CACHE[key] = surfaces(p)
    return hit


def part_mesh(p: dict):
    """(V, N, F) of one part in model space."""
    Vs, Ns, Fs, off = [], [], [], 0
    flip = p.get("_flip")
    for V, N, F in _cached_surfaces(p):
        if flip:                                     # a mirror copy: reflect, keep the faces outward
            j = "xyz".index(flip)
            V = V.copy(); V[:, j] = -V[:, j]
            if N is not None:
                N = N.copy(); N[:, j] = -N[:, j]
            F = F[:, ::-1].copy()
        if N is None:
            N = vertex_normals(V, F)
        elif len(F):                                # winding must agree with the given normals
            tri = V[F]
            fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            if ((fn * N[F].mean(1)).sum(1) < 0).mean() > 0.5:
                F = F[:, ::-1].copy()
        Vs.append(V); Ns.append(N); Fs.append(F + off); off += len(V)
    if not Vs:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)
    V, N, F = np.vstack(Vs), np.vstack(Ns), np.vstack(Fs)
    R = rot_matrix(*p["rot"])
    V = V @ R.T + np.asarray(p["pos"])
    N = N @ R.T
    return V.astype(np.float32), N.astype(np.float32), F.astype(np.int32)


def _axis_rot(axis: str, deg: float) -> np.ndarray:
    return rot_matrix(deg if axis == "x" else 0, deg if axis == "y" else 0, deg if axis == "z" else 0)


def _euler(R: np.ndarray) -> list:
    """Degrees (X, then Y, then Z) of a rotation matrix — inverse of rot_matrix."""
    sy = -R[2, 0]
    sy = max(-1.0, min(1.0, sy))
    y = math.asin(sy)
    if abs(sy) < 0.9999:
        x = math.atan2(R[2, 1], R[2, 2]); z = math.atan2(R[1, 0], R[0, 0])
    else:
        x = math.atan2(-R[1, 2], R[1, 1]); z = 0.0
    return [math.degrees(v) % 360 for v in (x, y, z)]


def expand(model: dict) -> list:
    """Every piece to draw: (part index, part) with arrays, radial copies and
    mirrors applied — so "12 vent slats" or "8 bolts round the rim" or "the
    left and right ear cups" cost the model one line each."""
    out = []
    for i, p in enumerate(model["parts"]):
        base = {k: v for k, v in p.items() if k not in ("mirror", "array", "radial")}
        copies = [base]
        if p.get("array"):
            a = p["array"]
            copies = []
            for k in range(a["count"]):
                q = dict(base)
                q["pos"] = [base["pos"][j] + a["step"][j] * k for j in range(3)]
                if a.get("rot"):
                    q["rot"] = [(base["rot"][j] + a["rot"][j] * k) % 360 for j in range(3)]
                copies.append(q)
        if p.get("radial"):
            r = p["radial"]
            c = np.asarray(r["center"], float)
            more = []
            for q in copies:
                for k in range(r["count"]):
                    R = _axis_rot(r["axis"], 360.0 * k / r["count"])
                    qq = dict(q)
                    qq["pos"] = list(R @ (np.asarray(q["pos"], float) - c) + c)
                    qq["rot"] = _euler(R @ rot_matrix(*q["rot"]))
                    more.append(qq)
            copies = more
        if p.get("mirror"):
            more = list(copies)
            for ax in p["mirror"]:
                j = "xyz".index(ax)
                for q in list(more):
                    qq = dict(q)
                    qq["pos"] = list(q["pos"]); qq["pos"][j] = -qq["pos"][j]
                    rx, ry, rz = q["rot"]
                    qq["rot"] = [rx, (-ry) % 360, (-rz) % 360] if ax == "x" else [(-rx) % 360, (-ry) % 360, rz]
                    qq["_flip"] = ax
                    more.append(qq)
            copies = more
        for q in copies:
            out.append((i, q))
            if len(out) >= MAX_INSTANCES:
                return out
    return out


def hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


class Mesh:
    """The whole model as flat arrays, ready for the GPU: positions (exploded
    as asked), normals, colours, materials, and which part each vertex is."""

    def __init__(self, model: dict, photo: np.ndarray | None = None):
        self.model = model
        parts = []
        self.instances = expand(model)
        for i, p in self.instances:
            V, N, F = part_mesh(p)
            if len(F):
                parts.append((i, V, N, F, p))
        self.parts = parts
        allv = np.vstack([q[1] for q in parts]) if parts else np.zeros((1, 3), np.float32)
        self.lo, self.hi = allv.min(0), allv.max(0)
        self.center = (self.lo + self.hi) / 2
        self.size = self.hi - self.lo
        self.radius = float(max(1.0, np.linalg.norm(self.size) / 2))
        self.floor = float(self.lo[1])
        acc: dict = {}
        for i, V, *_ in parts:
            acc.setdefault(i, []).append(V.mean(0))
        self.part_center = {i: np.mean(v, 0) for i, v in acc.items()}          # a group's centre
        self.inst_center = [V.mean(0) for _, V, *_ in parts]                     # each piece's own
        n_tri = sum(len(q[3]) for q in parts)
        self.n_vert = n_tri * 3
        # flat triangle arrays (non-indexed: simplest for the shader and STL)
        self.pos0 = np.zeros((self.n_vert, 3), np.float32)
        self.nrm = np.zeros((self.n_vert, 3), np.float32)
        self.col = np.zeros((self.n_vert, 3), np.float32)
        self.mat = np.zeros((self.n_vert, 4), np.float32)      # metal, rough, emissive, opacity
        self.pid = np.zeros(self.n_vert, np.float32)
        self.uv = np.zeros((self.n_vert, 2), np.float32)
        self.draws = [(0, self.n_vert, None)]                                 # (first, count, texture index)
        self.textures: list = []
        self.fin = np.zeros(self.n_vert, np.float32)                          # finish id
        self.ao = np.ones(self.n_vert, np.float32)                            # baked ambient occlusion
        k = 0
        for i, V, N, F, p in parts:
            m = len(F) * 3
            idx = F.reshape(-1)
            self.pos0[k:k + m] = V[idx]
            self.nrm[k:k + m] = N[idx]
            self.col[k:k + m] = hex_rgb(p["color"])
            self.mat[k:k + m] = (p["metal"], p["rough"], p["emissive"], p["opacity"])
            self.pid[k:k + m] = i
            self.fin[k:k + m] = FINISHES.index(p.get("finish", "none"))
            k += m
        if photo is not None and model.get("photo_box"):
            self._project_photo(photo, model["photo_box"])

    def _project_photo(self, img: np.ndarray, box) -> None:
        """Wear the photo on the front (+z) of the model: each front-facing
        vertex takes the colour of the photo pixel in front of it."""
        h, w = img.shape[:2]
        x0, y0, x1, y1 = box
        u = (self.pos0[:, 0] - self.lo[0]) / max(self.size[0], 1e-6)
        v = (self.hi[1] - self.pos0[:, 1]) / max(self.size[1], 1e-6)
        px = np.clip(((x0 + u * (x1 - x0)) * (w - 1)).astype(int), 0, w - 1)
        py = np.clip(((y0 + v * (y1 - y0)) * (h - 1)).astype(int), 0, h - 1)
        sample = img[py, px, :3].astype(np.float32) / 255.0
        facing = np.clip((self.nrm[:, 2] - 0.05) / 0.45, 0, 1) ** 1.5
        wgt = (facing * 0.82)[:, None]
        self.col = (self.col * (1 - wgt) + sample * wgt).astype(np.float32)

    def positions(self, explode: float = 0.0) -> np.ndarray:
        if explode <= 1e-4 or not self.parts:
            return self.pos0
        out = self.pos0.copy()
        k = 0
        for n, (i, V, N, F, _p) in enumerate(self.parts):
            m = len(F) * 3
            out[k:k + m] += (self.inst_center[n] - self.center) * explode * EXPLODE
            k += m
        return out

    @property
    def pieces(self) -> int:
        return len(self.parts)

    def stl(self) -> bytes:
        """Binary STL in millimetres, z up (what slicers expect)."""
        tri = self.pos0.reshape(-1, 3, 3)[:, :, [0, 2, 1]] * 10.0
        tri[:, :, 1] *= -1                          # keep it right-handed after the swap
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        head = b"JARVIS hologram STL".ljust(80, b" ")
        rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        rec["n"], rec["v"] = n, tri
        return head + struct.pack("<I", len(tri)) + rec.tobytes()


def export_obj(mesh) -> bytes:
    """Wavefront OBJ (centimetres, y up) with per-vertex colours — opens in
    Blender, Windows 3D Viewer and most CAD tools."""
    P, C = mesh.pos0, np.clip(mesh.col, 0, 1)
    head = "# JARVIS hologram export\n"
    v = "".join(f"v {x:.4f} {y:.4f} {z:.4f} {r:.3f} {g:.3f} {b:.3f}\n" for (x, y, z), (r, g, b) in zip(P.tolist(), C.tolist()))
    n_tri = len(P) // 3
    f = "".join(f"f {3 * t + 1} {3 * t + 2} {3 * t + 3}\n" for t in range(n_tri))
    return (head + v + f).encode("ascii")


def export_glb(mesh, model: dict) -> bytes:
    """The model as .glb: a real (AI) model is its own file, untouched; a parts
    model becomes one mesh per piece with its colour, metal and roughness."""
    from core import glb
    src = model.get("glb")
    if src:
        try:
            return Path(src).read_bytes()
        except OSError:
            pass
    prims = []
    for _i, V, N, F, p in getattr(mesh, "parts", []) or []:
        r, g, b = (c ** 2.2 for c in hex_rgb(p.get("color", "#cccccc")))       # glTF colour factors are linear
        prims.append({"V": V, "N": N, "F": F, "name": p.get("name", ""), "color": [r, g, b, float(p.get("opacity", 1.0))],
                      "metal": float(p.get("metal", 0.0)), "rough": float(p.get("rough", 0.5))})
    if not prims:                                                 # a scanned mesh without parts: one soup
        F = np.arange(len(mesh.pos0), dtype=np.uint32).reshape(-1, 3)
        prims.append({"V": mesh.pos0, "N": mesh.nrm, "F": F, "name": model.get("name", "model")})
    return glb.write(prims)


def decode_photo(b64: str):
    """The model's stored photo as an RGB array, or None."""
    if not b64:
        return None
    try:
        import base64
        import io
        from PIL import Image
        return np.asarray(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))
    except Exception:
        return None


# ── hand gestures (MediaPipe landmarks: objects or dicts with x, y) ──────────

def _xy(p):
    return (p["x"], p["y"]) if isinstance(p, dict) else (p.x, p.y)


def _d(a, b):
    (ax, ay), (bx, by) = _xy(a), _xy(b)
    return math.hypot(ax - bx, ay - by)


def pose(L) -> str:
    if not L or len(L) < 21:
        return "none"
    scale = _d(L[0], L[9]) or 0.1
    ext = lambda tip, pip: _d(L[0], L[tip]) > _d(L[0], L[pip]) * 1.15
    f = [ext(8, 6), ext(12, 10), ext(16, 14), ext(20, 18)]
    if _d(L[4], L[8]) < scale * 0.35:
        return "pinch"
    if all(f):
        return "open"
    if not any(f):
        return "fist"
    if f[0] and not any(f[1:]):
        return "point"
    return "other"


def anchor(L, kind: str) -> tuple:
    if kind == "pinch":
        (ax, ay), (bx, by) = _xy(L[4]), _xy(L[8])
        return ((ax + bx) / 2, (ay + by) / 2)
    return _xy(L[8]) if kind == "point" else _xy(L[9])


def gesture_step(st: dict, hands: list, t: float) -> dict:
    """hands: [(pose, (x, y))] mirrored like the preview, t in seconds.
    Returns rotate (deg), zoom factor, pan, action, cursor."""
    out = {"rotate": (0.0, 0.0), "zoom": 1.0, "pan": (0.0, 0.0), "action": "", "cursor": None}
    pinches = [h for h in hands if h[0] == "pinch"]
    if len(pinches) >= 2:
        (_, a), (_, b) = pinches[:2]
        dist, mid = math.hypot(a[0] - b[0], a[1] - b[1]), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if st.get("two"):
            out["zoom"] = _clamp(dist / max(0.02, st["two"][0]), 0.8, 1.25)
            out["pan"] = (mid[0] - st["two"][1][0], mid[1] - st["two"][1][1])
        st["two"], st["one"] = (dist, mid), None
    elif len(pinches) == 1:
        p = pinches[0][1]
        if st.get("one"):
            out["rotate"] = ((p[0] - st["one"][0]) * 360, (p[1] - st["one"][1]) * 240)
        st["one"], st["two"] = p, None
    else:
        st["one"] = st["two"] = None
    held = hands[0][0] if len(hands) == 1 else (hands[0][0] + "2" if len(hands) == 2 and hands[0][0] == hands[1][0] else "")
    if held != st.get("held"):
        st["held"], st["since"], st["fired"] = held, t, False
    if not st.get("fired") and t - st.get("since", t) > 0.7:
        if held in ("open", "open2"):
            out["action"], st["fired"] = "explode", True
        elif held in ("fist", "fist2"):
            out["action"], st["fired"] = "reset", True
    open_h = next((h for h in hands if h[0] == "open"), None)
    if open_h:
        trail = [q for q in st.get("trail", []) if t - q[0] < 0.35] + [(t, open_h[1][0])]
        if len(trail) >= 3 and abs(trail[-1][1] - trail[0][1]) > 0.45:
            out["action"], trail, st["fired"] = "throw", [], True
        st["trail"] = trail
    else:
        st["trail"] = []
    pt = next((h for h in hands if h[0] == "point"), None)
    if pt:
        out["cursor"] = pt[1]
    return out


_CMDS = (
    ("blender", r"blender"),
    ("scan", r"^(tara|modelle|dijitalleştir)\b|(bunu|şunu|kameradakini|elimdekini) (dijital olarak )?(modelle|tara|dijitalleştir)"),
    ("explode", r"parçala|parçalara ayır|patlat|içini göster"),
    ("assemble", r"birleştir|topla|parçaları kapat"),
    ("reset", r"sıfırla|ortala|başa al"),
    ("real", r"gerçekçi|gerçek görünüm|normal görünüm|katı model"),
    ("holo", r"hologram görünüm|hologram moduna|tel kafes|holografik"),
    ("save", r"^kaydet$|modeli kaydet"),
    ("stl", r"\bstl\b|3 ?d yazıcı|yazdırılabilir|dışa aktar"),
    ("throw", r"çöpe at|modeli sil|fırlat"),
    ("close", r"hologramı kapat|masayı kapat|hologramdan çık"),
    ("detail", r"detaylandır|daha fazla (ayrıntı|detay|parça)|ayrıntı ekle|detay ekle"),
    ("cut", r"kesit|kesip göster|içini kes"),
    ("measure", r"ölç|ölçüleri göster|boyutlarını göster"),
    ("show_all", r"hepsini göster|tümünü göster"),
    ("upright", r"doğrult|dik çevir|yan yatmış|ters duruyor"),
    ("parts_engine", r"parça (modeli|motoru)"),
    ("real_engine", r"gerçek (3 ?b|motor|model)"),
    ("video", r"video(su)? (çek|al|kaydet|yap)|dönen video|turntable"),
    ("lib", r"galeri|kütüphane|kayıtlı modeller|modellerimi göster"),
    ("stl", r"dışa aktar|export|obj (olarak )?kaydet|glb (olarak )?kaydet"),
    ("cancel", r"iptal|vazgeç|dur$"),
)


def local_command(text: str) -> str:
    t = str(text or "").casefold().replace("i̇", "i").strip()
    for name, pat in _CMDS:
        if re.search(pat, t):
            return name
    return ""


# ── real scanned meshes (.glb from core/holo_ai3d) ────────────────────────────

def _components(V: np.ndarray, F: np.ndarray, max_parts: int = 40):
    """Split a mesh into its separate pieces (wheels, body, glass…): weld the
    vertices UV seams split, then flood labels across shared edges."""
    q = np.round((V - V.min(0)) / max(float(np.ptp(V, 0).max()), 1e-9) * 2e5).astype(np.int64)
    _, weld = np.unique(q, axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    Fw = weld[F]
    n = int(weld.max()) + 1
    lab = np.arange(n)
    a = np.concatenate([Fw[:, 0], Fw[:, 1], Fw[:, 2]])
    b = np.concatenate([Fw[:, 1], Fw[:, 2], Fw[:, 0]])
    for _ in range(2000):
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]                                     # pointer jumping: converges fast
        if np.array_equal(new, lab):
            break
        lab = new
    face_lab = lab[Fw[:, 0]]
    ids, counts = np.unique(face_lab, return_counts=True)
    order = ids[np.argsort(-counts)]
    keep = order[:max_parts - 1]
    remap = {int(k): i for i, k in enumerate(keep)}
    other = len(keep)
    return np.array([remap.get(int(x), other) for x in face_lab]), len(keep) + (1 if len(order) > len(keep) else 0)


class ScanMesh(Mesh):
    """A real, textured mesh from an image-to-3D model, in the same arrays the
    renderer and the table use for parts models."""

    def __init__(self, model: dict, prims: list, upright: int = 0):
        self.model = model
        allV = np.vstack([p["V"] for p in prims])
        R = rot_matrix(-90 * upright, 0, 0) if upright else np.eye(3)
        lo, hi = (allV @ R.T).min(0), (allV @ R.T).max(0)
        size = hi - lo
        h = float(model.get("height_cm") or 0)
        k = h / max(float(size[1]), 1e-9) if h > 0 else 30.0 / max(float(size.max()), 1e-9)
        tris = sum(len(p["F"]) for p in prims)
        self.n_vert = tris * 3
        self.pos0 = np.zeros((self.n_vert, 3), np.float32)
        self.nrm = np.zeros((self.n_vert, 3), np.float32)
        self.col = np.ones((self.n_vert, 3), np.float32)
        self.mat = np.zeros((self.n_vert, 4), np.float32)
        self.pid = np.zeros(self.n_vert, np.float32)
        self.uv = np.zeros((self.n_vert, 2), np.float32)
        self.fin = np.zeros(self.n_vert, np.float32)
        self.ao = np.ones(self.n_vert, np.float32)
        self.textures, self.draws, self.parts, names = [], [], [], []
        off, pid = 0, 0
        for p in prims:
            V = ((p["V"] @ R.T) - [(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]) * k
            F = p["F"]
            N = (p["N"] @ R.T) if p.get("N") is not None else vertex_normals(V.astype(np.float32), F)
            labels, n_parts = _components(V, F) if len(prims) == 1 else (np.zeros(len(F), int), 1)
            order = np.argsort(labels, kind="stable")
            F, labels = F[order], labels[order]
            m = len(F) * 3
            idx = F.reshape(-1)
            sl = slice(off, off + m)
            self.pos0[sl], self.nrm[sl] = V[idx], N[idx]
            col = np.array(p["color"][:3], np.float32)
            self.col[sl] = (p["C"][idx, :3] * col) if p.get("C") is not None else col
            maps = p.get("maps") or {}
            emis = float(max(p.get("emissive") or [0.0]))
            if "mr" in maps:                                   # the texture carries the real metal/roughness
                self.mat[sl] = (p["metal"], p["rough"], emis, 1.0)
            else:                                              # factors only: services leave them at 1 — tame them
                self.mat[sl] = (min(p["metal"], 0.6), max(p["rough"], 0.35), emis, 1.0)
            if p.get("UV") is not None:
                self.uv[sl] = p["UV"][idx]
            ti = None
            if p.get("texture") is not None or maps:
                self.textures.append({"base": p.get("texture"), **maps, "normal_scale": p.get("normal_scale", 1.0)})
                ti = len(self.textures) - 1
            self.draws.append((off, m, ti))
            for j in range(n_parts):
                fs = np.nonzero(labels == j)[0]
                if not len(fs):
                    continue
                a, b = off + fs[0] * 3, off + (fs[-1] + 1) * 3
                self.pid[a:b] = pid
                Vp = self.pos0[a:b]
                self.parts.append((pid, Vp, None, np.zeros((len(fs), 3)), {}))
                names.append(f"{p['name']} {j + 1}" if n_parts > 1 else p["name"])
                pid += 1
            off += m
        self.lo, self.hi = self.pos0.min(0), self.pos0.max(0)
        self.center = (self.lo + self.hi) / 2
        self.size = self.hi - self.lo
        self.radius = float(max(1.0, np.linalg.norm(self.size) / 2))
        self.floor = float(self.lo[1])
        self.inst_center = [q[1].mean(0) for q in self.parts]
        self.part_center = {q[0]: c for q, c in zip(self.parts, self.inst_center)}
        self.instances = [(q[0], {}) for q in self.parts]
        if not model.get("parts"):
            model["parts"] = [{"name": nm, "shape": "mesh", "size": [round(float(x), 1) for x in np.ptp(q[1], 0)]}
                              for nm, q in zip(names, self.parts)]


def build_mesh(model: dict, photo=None):
    """The right mesh for a model record: a scanned .glb or the parts."""
    if model.get("glb"):
        from core import glb as _glb
        data = open(model["glb"], "rb").read()
        return ScanMesh(model, _glb.load(data), int(model.get("upright") or 0))
    return Mesh(model, photo)
