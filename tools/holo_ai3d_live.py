"""Live check of the real-3D engine: render a sample object, send it to each
image-to-3D Space, load what comes back and render it. Prints contact sheets
into the log (tools/render_holo_preview.py's format).

    xvfb-run python tools/holo_ai3d_live.py OUT [provider …]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "ai3d_out")
    only = sys.argv[2:]
    out.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QPainter, QColor
    app = QApplication(sys.argv)
    from core import holo_model, holo_ai3d, glb
    from gui.holo_gl import Camera, HoloGL, render_still
    from tools.holo_samples import HEADPHONES
    gl, cam = HoloGL(), Camera()
    mesh = holo_model.Mesh(holo_model.clean(HEADPHONES))
    cam.yaw, cam.pitch = -25, 12
    img = render_still(gl, mesh, cam, 900, 900, ss=1.5, holo=False, accent=(1, .54, .11), t=1.0)
    base = QImage(900, 900, QImage.Format.Format_RGB32)
    base.fill(QColor(205, 205, 208))
    p = QPainter(base); p.drawImage(0, 0, img); p.end()
    src = out / "00_source.jpg"
    base.save(str(src), "JPG", 92)
    ok = 0
    for name, _space, _fn in holo_ai3d.PROVIDERS:
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        t0 = time.time()
        data, prov, msg = holo_ai3d.image_to_3d(str(src), only=name, log=print)
        print(f"PROVIDER {name}: {'OK' if data else 'FAIL'} in {time.time() - t0:.0f} s — {msg}")
        if not data:
            continue
        ok += 1
        try:
            prims = glb.load(data)
            print(f"  prims {len(prims)}, tris {sum(len(q['F']) for q in prims)}, textures {sum(q['texture'] is not None for q in prims)}")
            model = {"name": name, "glb": str(out / f"{name}.glb"), "height_cm": 20}
            Path(model["glb"]).write_bytes(data)
            M = holo_model.build_mesh(holo_model.clean(model))
            print(f"  pieces {M.pieces}, size {[round(float(x), 1) for x in M.size]}")
            for look in ("real", "holo"):
                for k, yaw in enumerate((-30, 150)):
                    cam.yaw, cam.pitch = yaw, 14
                    im = render_still(gl, M, cam, 1000, 700, ss=1.5, holo=look == "holo", accent=(1, .54, .11), t=1.0)
                    canvas = QImage(1000, 700, QImage.Format.Format_RGB32); canvas.fill(QColor(12, 10, 9))
                    p = QPainter(canvas); p.drawImage(0, 0, im); p.end()
                    safe = "".join(ch for ch in name if ch.isalnum())
                    canvas.save(str(out / f"{safe}_{look}_{k}.png"))
        except Exception as exc:
            import traceback; traceback.print_exc()
            print(f"  load/render failed: {exc}")
    # real textured assets (what the services return looks like these): proves loading and rendering
    import urllib.request
    base = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/"
    for name, path, h in (("DamagedHelmet", "DamagedHelmet/glTF-Binary/DamagedHelmet.glb", 30),
                          ("ToyCar", "ToyCar/glTF-Binary/ToyCar.glb", 12), ("CesiumMan", "CesiumMan/glTF-Binary/CesiumMan.glb", 175)):
        try:
            f = out / f"{name}.glb"
            urllib.request.urlretrieve(base + path, str(f))
            model = holo_model.clean({"name": name, "glb": str(f), "height_cm": h})
            t0 = time.time()
            M = holo_model.build_mesh(model)
            print(f"SAMPLE {name}: {M.n_vert // 3} tris, {len(M.textures)} textures, {M.pieces} pieces, {time.time() - t0:.1f} s")
            for look in ("real", "holo"):
                cam.yaw, cam.pitch = (-35 if look == "real" else 30), 12
                im = render_still(gl, M, cam, 1000, 700, ss=1.5, holo=look == "holo", accent=(1, .54, .11), t=1.0)
                canvas = QImage(1000, 700, QImage.Format.Format_RGB32); canvas.fill(QColor(12, 10, 9))
                p = QPainter(canvas); p.drawImage(0, 0, im); p.end()
                canvas.save(str(out / f"zs_{name}_{look}.png"))
        except Exception as exc:
            import traceback; traceback.print_exc()
            print(f"SAMPLE {name} failed: {exc}")
    from tools.render_holo_preview import _log_sheet
    _log_sheet(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
