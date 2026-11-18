"""Render the hologram table's sample models to PNG files (both looks).

    python tools/render_holo_preview.py OUT_DIR [--size 1400]

Used by .github/workflows/holo-render.yml as a visual check. Exits 1 if the GPU
path did not run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "holo_preview")
    size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 1400
    out.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QColor, QRadialGradient
    from PyQt6.QtCore import QPointF
    app = QGuiApplication(sys.argv)
    from core import holo_model
    from gui.holo_gl import Camera, HoloGL
    from tools.holo_samples import ALL
    gl, cam = HoloGL(), Camera()
    w, h = size, int(size * 0.62)
    for m in ALL:
        mesh = holo_model.Mesh(holo_model.clean(m))
        for look in ("real", "holo"):
            for k, (yaw, pitch, ex) in enumerate(((-32, 18, 0.0), (35, 10, 0.0), (-20, 25, 1.0))):
                cam.yaw, cam.pitch = yaw, pitch
                t0 = time.perf_counter()
                img = gl.render(mesh, cam, w, h, holo=look == "holo", accent=(1.0, 0.54, 0.11), t=1.3, explode=ex, sel=1 if k == 1 else -1)
                dt = time.perf_counter() - t0
                if img is None:
                    print("GPU path failed:", gl.error)
                    return 1
                base = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
                p = QPainter(base)
                g = QRadialGradient(QPointF(w / 2, h * 0.58), w * 0.75)
                g.setColorAt(0, QColor(26, 22, 19) if look == "real" else QColor(43, 26, 11))
                g.setColorAt(0.55, QColor(5, 4, 3)); g.setColorAt(1, QColor(0, 0, 0))
                p.fillRect(0, 0, w, h, g)
                p.drawImage(0, 0, img)
                p.end()
                name = holo_model.clean(m)["name"].split()[0].lower()
                base.save(str(out / f"{name}_{look}_{k}.png"))
                print(f"{name} {look} {k}: {mesh.n_vert // 3} tris, {dt * 1000:.0f} ms")
    print("renderer:", gl.renderer_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
