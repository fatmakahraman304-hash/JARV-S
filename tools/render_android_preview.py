"""Render the android head to PNG files, the way the HUD draws it.

    python tools/render_android_preview.py OUT_DIR [--size 2160]

Builds the real HoloAvatar, poses it (front, turned, talking, blinking), paints
it with QPainter into a SIZE×SIZE image exactly like the HUD does, and writes
one PNG per pose plus timing. Exits 1 if the GPU path did not run, so CI shows
it. Used by .github/workflows/android-avatar.yml as a visual check.
"""
from __future__ import annotations

import math
import json
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

    look = sys.argv[sys.argv.index("--look") + 1] if "--look" in sys.argv else "holographic"
    av = HoloAvatar()
    av.style = look
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
        if not img.save(str(out / f"{name}.png")):
            raise RuntimeError("Rendered face could not be saved")
        if av.style != look:
            print("Requested face rendering failed:", av.render_note)
            return 1
    # Isolate animation changes at the SAME pose. Different yaw alone must
    # not let a broken mouth/blink/gaze pass the real shader acceptance.
    import numpy as np
    probe_dir = out / "animation-probes"
    probe_dir.mkdir(exist_ok=True)
    probes = {}
    av._yaw = av._pitch = av._glow = 0.0
    for label, mouth, blink, gaze in (("neutral", 0., 0., (0., 0.)),
                                      ("mouth", .85, 0., (0., 0.)),
                                      ("blink", 0., .95, (0., 0.)),
                                      ("gaze", 0., 0., (.8, -.4))):
        av._mouth, av._blink, av._gaze = mouth, blink, list(gaze)
        image = QImage(560, 560, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(qcol(C.BG))
        painter = QPainter(image)
        try:
            av.paint(painter, 280, 560 * .43, 560 * .30, qcol(C.PRI), qcol(C.ACC), qcol(C.BG))
        finally:
            painter.end()
        if av.style != look:
            raise RuntimeError("Requested renderer fell back during animation acceptance: " + av.render_note)
        if not image.save(str(probe_dir / (label + ".png"))):
            raise RuntimeError("Animation probe could not be saved")
        bits = image.bits(); bits.setsize(image.sizeInBytes())
        probes[label] = np.frombuffer(bits, dtype=np.uint8).copy().reshape(560, 560, 4)
    changes = {label: int(np.count_nonzero(np.any(probes[label] != probes["neutral"], axis=2)))
               for label in ("mouth", "blink", "gaze")}
    for label, changed in changes.items():
        if changed < 25:
            raise AssertionError(f"Real {label} animation did not change the framebuffer: {changed}")
    print("Verified same-pose animation pixels:", changes)
    manifest = {"requested_look": look, "renderer": getattr(av._gl, "renderer_name", "projection"),
                "same_pose_changed_pixels": changes, "physical_user_gpu_verified": False}
    (out / "acceptance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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
    if "--log-preview" in sys.argv:
        _log_images(out, size)
    gl = av._gl
    print("renderer:", getattr(gl, "renderer_name", "QPainter projection" if look == "projection" else "?"), "| first frames ms:",
          [round(x * 1000) for x in times])
    return 0


def _log_images(out: Path, size: int) -> None:
    """Print a contact sheet and a full-resolution face crop into the log as
    base64 JPEG, for when CI artifacts cannot be downloaded."""
    import base64
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
    from PyQt6.QtGui import QImage, QPainter

    files = sorted(out.glob("*.png"))
    tiles = [QImage(str(f)) for f in files]
    cw, ch = int(size * 0.62), int(size * 0.80)
    x0, y0 = (size - cw) // 2, int(size * 0.07)
    tw, th = 420, int(420 * ch / cw)
    sheet = QImage(tw * len(tiles), th, QImage.Format.Format_RGB32)
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for i, im in enumerate(tiles):
        p.drawImage(QRect(i * tw, 0, tw, th), im, QRect(x0, y0, cw, ch))
    p.end()
    crop = tiles[0].copy(QRect(int(size * 0.30), int(size * 0.18), int(size * 0.40), int(size * 0.44)))
    mouth = tiles[2].copy(QRect(int(size * 0.36), int(size * 0.44), int(size * 0.28), int(size * 0.22)))
    side = tiles[4].copy(QRect(int(size * 0.22), int(size * 0.10), int(size * 0.56), int(size * 0.62)))
    for label, im, q in (("SHEET", sheet, 82), ("CROP", crop, 88), ("MOUTH", mouth, 88),
                         ("SIDE", side.scaled(900, 996), 85)):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        im.save(buf, "JPG", q)
        data = base64.b64encode(bytes(ba)).decode()
        print(f"=====BEGIN {label}=====")
        for i in range(0, len(data), 3000):
            print(data[i:i + 3000])
        print(f"=====END {label}=====")


if __name__ == "__main__":
    sys.exit(main())
