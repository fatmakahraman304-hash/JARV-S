"""Extend the feminine AETHER face with a smooth, rig-safe 3D shoulder base."""
import numpy as np
from core.avatar_mesh import _vertex_normals, _unique_edges


def with_shoulders(mesh):
    result = dict(mesh)
    # Sculpt a soft oval crown and narrow tapered feminine jaw.
    # This warp applies ONLY to the hologram. Preserve vertex indices,
    # the speaking jaw and the existing eyelid and lip animations.
    original = mesh["verts"].copy()
    count_head = int(mesh["n_head"])
    y = original[:count_head, 1]
    forehead = np.clip((y + .48) / 1.25, 0.0, 1.0) ** 1.4
    jaw = np.clip((-.28 - y) / .77, 0.0, 1.0)
    crown = np.clip((y - .34) / .66, 0.0, 1.0) ** 2
    # Narrow the upper skull into the reference's rounded oval dome instead
    # of the wide, nearly vertical capsule that appeared on the user's HUD.
    # Smoothly reduce width at the crown while keeping measured eyes/jaw and
    # the existing landmark-based lip/blink animation intact.
    # Keep a rounded forehead but avoid the old tubular egg-shaped face.
    # Broaden the temples/upper cheeks, then taper naturally into a defined,
    # narrower chin. The 468 measured landmark IDs and lip/eyelid rig remain
    # exactly where the animation code expects them.
    cheek = np.exp(-((y + .20) / .34) ** 2)
    original[:count_head, 0] *= (1.076 + .035 * forehead -
                                 .048 * crown - .180 * jaw +
                                 .022 * cheek)
    segments = 14  # The existing neck ends with a 14-vertex elliptical ring.
    base = original[-segments:].copy()
    vertices = [original]
    faces = [mesh["faces"]]
    last = np.arange(len(original) - segments, len(original))
    count = len(original)
    # Extra rings smooth the transition from the neck into broad shoulders.
    ring_specs = ((1.08, 1.03, -1.28), (1.24, 1.08, -1.35),
                  (1.54, 1.12, -1.43), (2.00, 1.16, -1.51),
                  (2.47, 1.20, -1.59), (2.84, 1.23, -1.68))
    for width, depth, y in ring_specs:
        ring = base.copy()
        ring[:, 0] *= width
        ring[:, 2] = -.25 + (ring[:, 2] + .25) * depth
        ring[:, 1] = y
        current = np.arange(count, count + segments)
        strips = []
        for i in range(segments):
            j = (i + 1) % segments
            strips.extend(((last[i], current[i], last[j]),
                           (last[j], current[i], current[j])))
        vertices.append(ring)
        faces.append(np.asarray(strips, dtype=np.int32))
        last, count = current, count + segments
    result["verts"] = np.ascontiguousarray(np.concatenate(vertices), dtype=np.float32)
    result["faces"] = np.ascontiguousarray(np.concatenate(faces), dtype=np.int32)
    added = count - len(original)
    for field in ("jaw", "brow", "lips"):
        result[field] = np.concatenate((mesh[field], np.zeros(added, np.float32)))
    fade = mesh["fade"].copy()
    fade[mesh["n_head"]:] = 1.0
    result["fade"] = np.concatenate(
        (fade, np.repeat([1.0, .98, .91, .79, .58, .0], segments).astype(np.float32)))
    result["face_group"] = np.concatenate(
        (mesh["face_group"], np.zeros(segments * 2 * len(ring_specs), np.float32)))
    outward = np.concatenate((mesh["normals"], result["verts"][len(original):] - [0, -1.40, -.25]))
    result["normals"] = np.ascontiguousarray(_vertex_normals(result["verts"], result["faces"], outward), dtype=np.float32)
    result["edges"] = _unique_edges(result["faces"])[::3]
    result["span"] = (1.0, -1.68)
    return result
