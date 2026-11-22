"""Extend the measured male face with a smooth, rig-safe 3D shoulder base."""
import numpy as np
from core.avatar_mesh import _vertex_normals, _unique_edges


def with_shoulders(mesh):
    result = dict(mesh)
    original = mesh["verts"]
    segments = 14  # The existing neck ends with a 14-vertex elliptical ring.
    base = original[-segments:].copy()
    vertices = [original]
    faces = [mesh["faces"]]
    last = np.arange(len(original) - segments, len(original))
    count = len(original)
    for width, depth, y in ((1.24, 1.10, -1.40), (1.68, 1.18, -1.50),
                            (1.96, 1.22, -1.62)):
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
    result["fade"] = np.concatenate((mesh["fade"], np.repeat([.86, .60, .0], segments).astype(np.float32)))
    result["face_group"] = np.concatenate((mesh["face_group"], np.zeros(segments * 6, np.float32)))
    outward = np.concatenate((mesh["normals"], result["verts"][len(original):] - [0, -1.40, -.25]))
    result["normals"] = np.ascontiguousarray(_vertex_normals(result["verts"], result["faces"], outward), dtype=np.float32)
    result["edges"] = _unique_edges(result["faces"])[::3]
    result["span"] = (1.0, -1.62)
    return result
