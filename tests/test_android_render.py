"""Android face geometry helpers (numpy only, no OpenGL needed)."""
import unittest

import numpy as np

from core.android_render import apply_stencil, bake_cavity, loop_subdivision
from core.avatar_mesh import get_head_mesh


class LoopSubdivisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = get_head_mesh()
        cls.sub = loop_subdivision(cls.m["faces"], len(cls.m["verts"]), 2)

    def test_counts(self):
        faces, idx, w, parent = self.sub
        self.assertEqual(len(faces), len(self.m["faces"]) * 16)
        self.assertEqual(len(parent), len(faces))
        self.assertEqual(int(parent.max()), len(self.m["faces"]) - 1)
        self.assertEqual(int(faces.max()), len(idx) - 1)

    def test_weights_are_affine(self):
        _, idx, w, _ = self.sub
        np.testing.assert_allclose(w.sum(1), 1.0, atol=1e-5)
        self.assertTrue((idx >= 0).all() and (idx < len(self.m["verts"])).all())

    def test_surface_stays_in_hull(self):
        _, idx, w, _ = self.sub
        v = self.m["verts"]
        p = apply_stencil(v, idx, w)
        self.assertTrue((p.min(0) >= v.min(0) - 1e-4).all())
        self.assertTrue((p.max(0) <= v.max(0) + 1e-4).all())
        # scalar attributes follow the same stencil
        self.assertEqual(apply_stencil(self.m["jaw"], idx, w).shape, (len(idx),))

    def test_cavity_range(self):
        ao = bake_cavity(self.m["verts"], self.m["normals"], self.m["faces"])
        self.assertEqual(len(ao), len(self.m["verts"]))
        self.assertGreaterEqual(float(ao.min()), 0.35 - 1e-6)
        self.assertLessEqual(float(ao.max()), 1.0 + 1e-6)


if __name__ == "__main__":
    unittest.main()
