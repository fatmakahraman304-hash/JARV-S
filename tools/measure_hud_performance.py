"""Measure real HUD work and framebuffer churn in a selected checkout.

Separate processes keep imports and Qt/OpenGL state independent. The comparison
uses baseline/candidate on the SAME runner, without calling a model or microphone.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path


def measure(root: Path, out: Path, no_render=False):
    started = time.perf_counter()
    sys.path.insert(0, str(root.resolve()))
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QPainter
    from gui.hud import HudCanvas
    from gui.theme import C, qcol
    from unittest.mock import patch
    import psutil
    import numpy as np
    import_ms = (time.perf_counter() - started) * 1000
    app = QApplication.instance() or QApplication([])
    with patch("memory.config_manager.get_hud_style", return_value="face"):
        started = time.perf_counter()
        widget = HudCanvas("")
        construct_ms = (time.perf_counter() - started) * 1000
    callbacks = []
    widget._tmr.timeout.connect(lambda: callbacks.append(time.monotonic()))
    cpu = time.process_time()
    started = time.monotonic()
    while time.monotonic() - started < 1.0:
        app.processEvents()
        time.sleep(.002)
    hidden_cpu_ms = (time.process_time() - cpu) * 1000
    widget._tmr.stop()
    out.mkdir(parents=True, exist_ok=True)
    result = {"import_ms": import_ms, "hud_construct_ms": construct_ms,
              "hidden_timer_callbacks": len(callbacks), "hidden_animation_steps": widget._tick,
              "hidden_cpu_ms": hidden_cpu_ms, "physical_user_hardware_verified": False,
              "render_verified": False}
    if not no_render:
        avatar = widget._avatar
        image = QImage(560, 560, QImage.Format.Format_ARGB32_Premultiplied)
        def frame(index):
            avatar._yaw = .30 * math.sin(index * .30)
            avatar._pitch = avatar._blink = avatar._glow = 0.0
            avatar._mouth = .5 + .5 * math.sin(index)
            avatar._gaze = [0., 0.]
            image.fill(qcol(C.BG))
            painter = QPainter(image)
            try:
                avatar.paint(painter, 280, 560 * .43, 168, qcol(C.PRI), qcol(C.ACC), qcol(C.BG))
            finally:
                painter.end()
            if avatar.style != "holographic" or avatar._gl is None or not avatar._gl.ok:
                raise RuntimeError("Real OpenGL render unavailable: " + avatar.render_note)
        frame(0)  # warm driver, shaders, buffers and mesh before steady-state timing
        renderer = avatar._gl
        ensure = renderer._ensure_fbo
        allocations = []
        def counted(w, h):
            if renderer._fbo_size != (w, h):
                allocations.append((w, h))
            return ensure(w, h)
        renderer._ensure_fbo = counted
        samples = []
        for index in range(20):
            started = time.perf_counter()
            frame(index)
            samples.append((time.perf_counter() - started) * 1000)
            if index == 0 and not image.save(str(out / "reference.png")):
                raise RuntimeError("Reference framebuffer could not be saved")
        result.update(render_verified=True, render_ms_median=statistics.median(samples),
                      render_ms_p95=float(np.percentile(samples, 95)),
                      fbo_reallocations=len(allocations), frames=len(samples),
                      renderer=renderer.renderer_name)
    result["rss_mb"] = psutil.Process().memory_info().rss / 1024 ** 2
    widget.close()
    (out / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


def compare(base: Path, candidate: Path, output: Path):
    import numpy as np
    from PIL import Image
    before = [json.loads(p.read_text()) for p in sorted(base.glob("*/metrics.json"))]
    after = [json.loads(p.read_text()) for p in sorted(candidate.glob("*/metrics.json"))]
    if len(before) != 3 or len(after) != 3 or not all(r["render_verified"] for r in before + after):
        raise AssertionError("Three real-render runs per checkout are required")
    keys = ("import_ms", "hud_construct_ms", "hidden_timer_callbacks", "hidden_animation_steps",
            "hidden_cpu_ms", "render_ms_median", "render_ms_p95", "fbo_reallocations", "rss_mb")
    summary = {"before": {k: statistics.median(r[k] for r in before) for k in keys},
               "after": {k: statistics.median(r[k] for r in after) for k in keys},
               "renderer_before": before[0]["renderer"], "renderer_after": after[0]["renderer"],
               "physical_user_hardware_verified": False}
    first = np.asarray(Image.open(sorted(base.glob("*/reference.png"))[0]).convert("RGB"), dtype=np.float32)
    second = np.asarray(Image.open(sorted(candidate.glob("*/reference.png"))[0]).convert("RGB"), dtype=np.float32)
    summary["image_rgb_mean_absolute_difference"] = float(np.abs(first - second).mean())
    assert summary["image_rgb_mean_absolute_difference"] <= 2., "Face image changed beyond the padding tolerance"
    assert summary["after"]["hidden_animation_steps"] == 0, "Hidden HUD still computed animation"
    assert summary["after"]["hidden_timer_callbacks"] < summary["before"]["hidden_timer_callbacks"] / 2, "Hidden timer work was not reduced"
    assert summary["after"]["fbo_reallocations"] < summary["before"]["fbo_reallocations"], "Framebuffer allocation churn was not reduced"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASE_RESULTS", "CANDIDATE_RESULTS"))
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare, args.out)
    elif args.root:
        measure(args.root, args.out, args.no_render)
    else:
        parser.error("--root or --compare is required")
