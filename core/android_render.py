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


def loop_subdivision(faces: np.ndarray, n_verts: int, levels: int = 2):
    """Loop subdivision as a fixed linear stencil over the base vertices.

    Returns (sub_faces, idx, w, parent): every subdivided vertex is
    sum(w[i, k] * base[idx[i, k]]), so the animated (posed) base mesh can be
    smoothed every frame with one gather, and per-vertex attributes (rest
    position, occlusion, jaw weight, fade) follow the same way. `parent` maps
    each subdivided face to the base face it came from. Boundary edges and
    vertices use the boundary rules, so open edges (the neck stub) stay put."""
    stencils = [{i: 1.0} for i in range(n_verts)]
    f = [tuple(int(x) for x in t) for t in faces]
    parent = list(range(len(f)))

    def combine(terms):
        out = {}
        for weight, st in terms:
            for k, v in st.items():
                out[k] = out.get(k, 0.0) + weight * v
        return out

    for _ in range(levels):
        n = len(stencils)
        edge_faces = {}
        nbrs = [set() for _ in range(n)]
        for fi, (a, b, c) in enumerate(f):
            for u, v, o in ((a, b, c), (b, c, a), (c, a, b)):
                edge_faces.setdefault((min(u, v), max(u, v)), []).append(o)
                nbrs[u].add(v)
                nbrs[v].add(u)
        boundary_nb = [[] for _ in range(n)]
        for (u, v), opp in edge_faces.items():
            if len(opp) != 2:
                boundary_nb[u].append(v)
                boundary_nb[v].append(u)
        new = []
        for i in range(n):
            if boundary_nb[i]:
                bn = boundary_nb[i][:2]
                if len(bn) == 2:
                    new.append(combine([(0.75, stencils[i]), (0.125, stencils[bn[0]]),
                                        (0.125, stencils[bn[1]])]))
                else:
                    new.append(dict(stencils[i]))
            else:
                k = len(nbrs[i])
                if k == 0:
                    new.append(dict(stencils[i]))
                    continue
                beta = 3.0 / (8.0 * k) if k > 3 else 3.0 / 16.0
                new.append(combine([(1.0 - k * beta, stencils[i])]
                                   + [(beta, stencils[j]) for j in nbrs[i]]))
        edge_id = {}
        for (u, v), opp in edge_faces.items():
            if len(opp) == 2:
                st = combine([(0.375, stencils[u]), (0.375, stencils[v]),
                              (0.125, stencils[opp[0]]), (0.125, stencils[opp[1]])])
            else:
                st = combine([(0.5, stencils[u]), (0.5, stencils[v])])
            edge_id[(u, v)] = len(new)
            new.append(st)
        nf, npar = [], []
        for fi, (a, b, c) in enumerate(f):
            ab = edge_id[(min(a, b), max(a, b))]
            bc = edge_id[(min(b, c), max(b, c))]
            ca = edge_id[(min(c, a), max(c, a))]
            nf += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
            npar += [parent[fi]] * 4
        # drop negligible weights so the stencils stay short
        stencils = [{k: v for k, v in st.items() if abs(v) > 1e-4} for st in new]
        f, parent = nf, npar

    width = max(len(st) for st in stencils)
    idx = np.zeros((len(stencils), width), np.int32)
    w = np.zeros((len(stencils), width), np.float32)
    for i, st in enumerate(stencils):
        ks = list(st.keys())
        vs = np.array([st[k] for k in ks], np.float32)
        idx[i, :len(ks)] = ks
        w[i, :len(ks)] = vs / vs.sum()
    return np.array(f, np.int32), idx, w, np.array(parent, np.int32)


def apply_stencil(values: np.ndarray, idx: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Subdivided values from base values (any trailing shape)."""
    g = values[idx]
    if g.ndim == 2:
        return (g * w).sum(1)
    return np.einsum("mk,mkd->md", w, g)
