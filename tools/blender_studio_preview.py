"""CI preview: Blender toolkit and architecture renders, printed as a base64 JPEG contact sheet (SHEET-BEGIN/SHEET-END)."""
from __future__ import annotations

import base64
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from PIL import Image
    from plugins import blender_studio as studio
    tmp = Path(tempfile.mkdtemp())
    studio.ROOT = tmp / "Blender"
    binary = studio.executable()
    shots = []
    # the toolkit, as a script Mayk would write: a real table + a mug on it
    table = """import bpy
clear()
W, D, H, T = 1.40, 0.80, 0.75, 0.035
oak = wood("Meşe", (0.42, 0.25, 0.12))
top_ = box("Tabla", (W, D, T), (0, 0, H - T / 2), bevel=0.006)
legs = []
for i, (sx, sy) in enumerate([(-1, -1), (1, -1), (-1, 1), (1, 1)], 1):
    leg = box(f"Masa ayağı {i}", (0.055, 0.055, H - T), (sx * (W / 2 - 0.07), sy * (D / 2 - 0.07), (H - T) / 2), bevel=0.004)
    legs.append(leg)
for name, l, a in (("Ön kuşak", W - 0.2, 0), ("Arka kuşak", W - 0.2, 0), ("Sol kuşak", D - 0.2, 90), ("Sağ kuşak", D - 0.2, 90)):
    y = {"Ön kuşak": -(D / 2 - 0.07), "Arka kuşak": D / 2 - 0.07}.get(name, 0)
    x = {"Sol kuşak": -(W / 2 - 0.07), "Sağ kuşak": W / 2 - 0.07}.get(name, 0)
    rail = box(name, (l, 0.022, 0.09), (x, y, 0), rot=(0, 0, a))
    rail.location.z = H - T - 0.045
    legs.append(rail)
for o in [top_] + legs:
    assign(o, oak)
mug = lathe("Kupa", [(0.0, 0.0), (0.04, 0.0), (0.042, 0.01), (0.043, 0.095), (0.04, 0.095), (0.039, 0.012), (0.0, 0.012)])
place_on(mug, top_, x=0.3, y=-0.1)
handle = tube("Kulp", [(0.343, -0.1, H + 0.025), (0.375, -0.1, H + 0.045), (0.375, -0.1, H + 0.07), (0.343, -0.1, H + 0.085)], 0.006)
for o in (mug, handle):
    assign(o, paint("Seramik", (0.85, 0.83, 0.78), 0.3, 0.8))
studio(samples=48)
"""
    try:
        folder = tmp / "masa"
        folder.mkdir()
        studio.run_script(binary, None, folder, table)
        (tmp / "masa_v").mkdir()
        (tmp / "masa_r").mkdir()
        rep = studio.invoke(binary, folder / "scene.blend", tmp / "masa_v", "views")
        print("table issues:", rep.get("issues"))
        shots.append(Image.open(rep["views"][0][1]).convert("RGB"))
        studio.invoke(binary, folder / "scene.blend", tmp / "masa_r", "render")
        shots.append(Image.open(tmp / "masa_r" / "render.png").convert("RGB"))
        print("rendered table")
    except Exception as exc:
        print("table failed:", exc)
    # buildings from the architecture engine (camera view, studio quality)
    from tests.test_blender_arch import APARTMENT, HOUSE
    for plan in (APARTMENT, HOUSE):
        try:
            folder = tmp / plan["name"].replace(" ", "_")
            folder.mkdir()
            studio.building_project(binary, folder, plan["name"], plan)
            out_dir = tmp / (folder.name + "_r")
            out_dir.mkdir()
            rep = studio.invoke(binary, folder / "scene.blend", out_dir, "views", w=960, h=540, samples=32)
            print(plan["name"], "issues:", rep.get("issues"))
            for _n, path in rep["views"][:2]:
                shots.append(Image.open(path).convert("RGB"))
        except Exception as exc:
            import traceback
            print("building failed:", plan["name"], exc, traceback.format_exc()[-1500:])
    if not shots:
        raise SystemExit("no renders")
    sheet = Image.new("RGB", (960 * 2, 540 * ((len(shots) + 1) // 2)))  # noqa
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
