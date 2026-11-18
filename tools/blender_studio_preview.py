"""CI preview: the hologram's Blender studio render of a real PBR asset and a
parts model, printed as a base64 JPEG contact sheet (SHEET-BEGIN/SHEET-END)."""
from __future__ import annotations

import base64
import io
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from PIL import Image
    from core import holo_model as hm
    from plugins import blender_studio as studio
    from tools import holo_samples
    tmp = Path(tempfile.mkdtemp())
    studio.ROOT = tmp / "Blender"
    binary = studio.executable()
    jobs = []
    helmet = tmp / "DamagedHelmet.glb"
    try:
        urllib.request.urlretrieve("https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/"
                                   "DamagedHelmet/glTF-Binary/DamagedHelmet.glb", str(helmet))
        jobs.append((helmet, 0.3))
    except Exception as exc:
        print("helmet download skipped:", exc)
    for spec in (holo_samples.HEADPHONES, holo_samples.WHEEL):
        m = hm.clean(spec)
        mesh = hm.build_mesh(m)
        f = tmp / f"{len(jobs)}.glb"
        f.write_bytes(hm.export_glb(mesh, m))
        jobs.append((f, float(mesh.size[1]) / 100))
    shots = []
    for f, height in jobs:
        try:
            out = studio.hologram_render(binary, str(f), w=960, h=540, samples=48, height_m=height)
            shots.append(Image.open(out).convert("RGB"))
            print("rendered", f.name)
        except Exception as exc:
            print("render failed", f.name, exc)
    if not shots:
        raise SystemExit("no renders")
    sheet = Image.new("RGB", (960 * 2, 540 * ((len(shots) + 1) // 2)))
    for i, im in enumerate(shots):
        sheet.paste(im.resize((960, 540)), ((i % 2) * 960, (i // 2) * 540))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=84)
    data = base64.b64encode(buf.getvalue()).decode()
    print("SHEET-BEGIN 0")
    for i in range(0, len(data), 4000):
        print("SHEET:" + data[i:i + 4000])
    print("SHEET-END")


if __name__ == "__main__":
    main()
