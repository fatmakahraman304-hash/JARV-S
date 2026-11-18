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
    from PyQt6.QtGui import QImage, QPainter, QColor, QRadialGradient
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from core import holo_model
    from gui.holo_gl import Camera, HoloGL, render_still
    from tools.holo_samples import ALL
    gl, cam = HoloGL(), Camera()
    w, h = size, int(size * 0.62)
    for m in ALL:
        mesh = holo_model.Mesh(holo_model.clean(m))
        for look in ("real", "holo"):
            for k, (yaw, pitch, ex) in enumerate(((-32, 18, 0.0), (35, 10, 0.0), (-20, 25, 1.0))):
                cam.yaw, cam.pitch = yaw, pitch
                t0 = time.perf_counter()
                img = render_still(gl, mesh, cam, w, h, ss=2.0, holo=look == "holo", accent=(1.0, 0.54, 0.11), t=1.3, explode=ex, sel=1 if k == 1 else -1)
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
                name = "".join(ch for ch in holo_model.clean(m)["name"].split()[0].lower() if ch.isascii() and ch.isalnum()) or "model"
                base.save(str(out / f"{name}_{look}_{k}.png"))
                print(f"{name} {look} {k}: {mesh.n_vert // 3} tris, {dt * 1000:.0f} ms")
    # one real 4K frame
    cam.yaw, cam.pitch = -28, 14
    mesh = holo_model.Mesh(holo_model.clean(ALL[3]))
    t0 = time.perf_counter()
    img = render_still(gl, mesh, cam, 3840, 2160, ss=1.5, holo=False, accent=(1.0, 0.54, 0.11), t=1.3)
    print(f"4K still: {img.width() if img else 0}x{img.height() if img else 0}, {(time.perf_counter() - t0) * 1000:.0f} ms")
    if img is not None:
        img.save(str(out / "zz_4k_helmet.png"))
        crop = img.copy(1500, 500, 1280, 794)
        crop.save(str(out / "zz_4k_crop.png"))
    # a real PBR asset (normal, metal/roughness, emissive, occlusion maps)
    try:
        import urllib.request
        f = out / "DamagedHelmet.glb"
        urllib.request.urlretrieve("https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/"
                                   "DamagedHelmet/glTF-Binary/DamagedHelmet.glb", str(f))
        M = holo_model.build_mesh(holo_model.clean({"name": "DamagedHelmet", "glb": str(f), "height_cm": 30}))
        print("PBR maps:", [sorted(k for k in d if d.get(k) is not None) for d in M.textures])
        for k, yaw in enumerate((-35, 20, 140)):
            cam.yaw, cam.pitch = yaw, 8
            im = render_still(gl, M, cam, w, h, ss=2.0, holo=False, accent=(1.0, 0.54, 0.11), t=1.3)
            canvas = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(canvas)
            g = QRadialGradient(QPointF(w / 2, h * 0.58), w * 0.75)
            g.setColorAt(0, QColor(26, 22, 19)); g.setColorAt(0.55, QColor(5, 4, 3)); g.setColorAt(1, QColor(0, 0, 0))
            p.fillRect(0, 0, w, h, g); p.drawImage(0, 0, im); p.end()
            canvas.save(str(out / f"pbr_helmet_{k}.png"))
        cam.reset()
    except Exception as exc:
        print("PBR sample skipped:", exc)
    # the whole table as it appears in JARVIS's window
    from unittest import mock
    from gui import holo_panel
    with mock.patch.object(holo_panel, "load_library", return_value=[]):
        panel = holo_panel.HoloPanel()
        panel.resize(1600, 900)
        panel.set_model(holo_model.clean(ALL[3]), animate=False)
        panel.show()
        app.processEvents()
        for look in ("real", "holo"):
            panel.command({"action": look})
            panel.sel = 1
            app.processEvents()
            panel.grab().save(str(out / f"zz_panel_{look}.png"))
        panel.set_model(holo_model.clean(ALL[6]), animate=False)
        panel.command({"action": "real"}); panel.command({"action": "measure"}); panel.command({"action": "cut"})
        panel.cut = 0.62
        for _ in range(12):                      # let the ambient occlusion finish
            panel.repaint(); app.processEvents()
        panel.grab().save(str(out / "zz_panel_lab.png"))
        panel.hide()
    print("renderer:", gl.renderer_name)
    if "--log-preview" in sys.argv:
        _log_sheet(out)
    return 0


def _log_sheet(out: Path) -> None:
    """Contact sheets as base64 JPEG in the log (when artifacts can't be fetched)."""
    import base64
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage, QPainter
    files = sorted(f for f in list(out.glob("*.png")) + list(out.glob("00_*.jpg")) if "zz_4k_helmet" not in f.name)
    for start in range(0, len(files), 6):
        group = files[start:start + 6]
        tw, th = 640, 397
        sheet = QImage(tw * 2, th * 3, QImage.Format.Format_RGB32)
        sheet.fill(0)
        p = QPainter(sheet)
        for i, f in enumerate(group):
            img = QImage(str(f)).scaled(tw, th, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawImage((i % 2) * tw, (i // 2) * th, img)
        p.end()
        ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly)
        sheet.save(buf, "JPG", 82)
        data = base64.b64encode(bytes(ba)).decode()
        print(f"SHEET-BEGIN {start // 6}")
        for k in range(0, len(data), 4000):
            print("SHEET:" + data[k:k + 4000])
        print("SHEET-END")


if __name__ == "__main__":
    sys.exit(main())
