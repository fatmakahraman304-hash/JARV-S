"""core/android_render.py — start-up data for the android head (no Qt).

The head itself is drawn on the GPU by gui/android_gl.py. What it needs from
the mesh that is cheaper to compute once on the CPU lives here: a per-vertex
cavity term that darkens eye sockets, nostrils, the lip line and the jaw seam
like ambient occlusion would.
"""
from __future__ import annotations

import numpy as np


def bake_cavity(verts: np.ndarray, normals: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Per-vertex occlusion from concavity: eye sockets, nostrils, the lip line
    and the jaw seam darken, ridges stay bright. Done once at start-up."""
    n = len(verts)
    nb = [set() for _ in range(n)]
    for a, b, c in faces:
        nb[a].update((b, c))
        nb[b].update((a, c))
        nb[c].update((a, b))
    cav = np.zeros(n, np.float32)
    for i in range(n):
        if not nb[i]:
            continue
        idx = np.fromiter(nb[i], dtype=np.int32)
        d = verts[idx] - verts[i]
        el = np.linalg.norm(d, axis=1).mean() + 1e-6
        cav[i] = float((d @ normals[i]).mean() / el)
    ao = np.clip(1.0 - 2.2 * np.maximum(cav, 0.0), 0.35, 1.0)
    for _ in range(2):                     # soften so it reads as light, not dots
        ao = np.array([0.5 * ao[i] + 0.5 * ao[list(nb[i])].mean() if nb[i] else ao[i]
                       for i in range(n)], np.float32)
    return ao
