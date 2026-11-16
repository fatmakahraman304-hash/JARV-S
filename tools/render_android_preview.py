"""Render the android head to PNG files, the way the HUD draws it.

    python tools/render_android_preview.py OUT_DIR [--size 2160]

Builds the real HoloAvatar, poses it (front, turned, talking, blinking), paints
it with QPainter into a SIZE×SIZE image exactly like the HUD does, and writes
one PNG per pose plus timing. Exits 1 if the GPU path did not run, so CI shows
it. Used by .github/workflows/android-avatar.yml as a visual check.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "android_preview")
    size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 2160
    out.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QRadialGradient, QBrush
    app = QGuiApplication(sys.argv)
    from core.avatar import HoloAvatar
    from gui.theme import C, qcol

    av = HoloAvatar()
    av.style = "android"
    poses = [("1_front", 0.0, 0.0, 0.0, 0.0, 0.0), ("2_turned", 0.42, 0.07, 0.0, 0.0, 0.0),
             ("3_talking", -0.18, 0.02, 0.85, 0.0, 0.7), ("4_blink", 0.12, -0.04, 0.0, 0.85, 0.0),
             ("5_side", 1.05, 0.0, 0.0, 0.0, 0.0)]
    times = []
    for name, yaw, pitch, mouth, blink, glow in poses:
        av._yaw, av._pitch, av._mouth, av._blink, av._glow = yaw, pitch, mouth, blink, glow
        av._gaze = [0.25 if yaw > 0 else -0.2, 0.05]
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(qcol(C.BG))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = size * 0.30
        t0 = time.perf_counter()
        av.paint(p, size / 2, size * 0.43, r, qcol(C.PRI), qcol(C.ACC), qcol(C.BG))
        times.append(time.perf_counter() - t0)
        p.end()
        img.save(str(out / f"{name}.png"))
        if av.style != "android":
            print("GPU path failed:", av.render_note)
            return 1
    # steady-state timing at HUD size (1080p and 4K head heights)
    for label, s in (("1080p", 560), ("4K", 1120)):
        img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        t0 = time.perf_counter()
        n = 20
        for i in range(n):
            av._yaw = 0.3 * math.sin(i * 0.3)
            av._mouth = 0.5 + 0.5 * math.sin(i)
            av.paint(p, s / 2, s * 0.43, s * 0.30, qcol(C.PRI), qcol(C.ACC), qcol(C.BG))
        dt = (time.perf_counter() - t0) / n
        p.end()
        print(f"frame {label}: {dt * 1000:.1f} ms")
    gl = av._gl
    print("renderer:", getattr(gl, "renderer_name", "?"), "| first frames ms:",
          [round(x * 1000) for x in times])
    return 0


if __name__ == "__main__":
    sys.exit(main())
