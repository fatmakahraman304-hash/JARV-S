"""What JARVIS knows and learns about Blender.

* KNOWLEDGE — the Blender 4.x Python facts models most often get wrong.
* Lessons — a small file JARVIS keeps (memory/blender_lessons.json):
  recipes that worked (request -> steps or script), errors and the code that
  fixed them, and tips the user taught. The closest ones go into every new
  Blender prompt, so a mistake made once is not made again.
* Script mode — for anything the step language cannot say, the model writes
  a bpy script; Blender runs it; a traceback goes back to the model, which
  fixes the script (up to MAX_TRIES). A working script is learned.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from pathlib import Path

LESSONS = Path(__file__).resolve().parent.parent / "memory" / "blender_lessons.json"
MAX_LESSONS = 400
MAX_TRIES = 4
_lock = threading.Lock()

KNOWLEDGE = """Blender 4.x Python (bpy) facts — follow them exactly:
- Run headless: no bpy.context.area / screen / window; avoid operators that need a 3D view. Prefer bpy.data and
  bmesh over bpy.ops. If an operator is unavoidable, select/activate first:
  bpy.context.view_layer.objects.active = obj; obj.select_set(True).
- Create mesh objects with bpy.ops.mesh.primitive_*_add(...) or bpy.data.meshes.new + mesh.from_pydata(verts, [], faces);
  link new objects: bpy.context.collection.objects.link(obj).
- Principled BSDF input names (4.0+): "Base Color", "Metallic", "Roughness", "IOR", "Alpha", "Normal",
  "Subsurface Weight", "Subsurface Radius", "Specular IOR Level", "Specular Tint", "Anisotropic",
  "Coat Weight", "Coat Roughness", "Sheen Weight", "Emission Color", "Emission Strength", "Transmission Weight".
  NOT "Subsurface", "Specular", "Clearcoat", "Emission", "Transmission" (those were 3.x).
- Materials: mat = bpy.data.materials.new(name); mat.use_nodes = True; bsdf = mat.node_tree.nodes["Principled BSDF"];
  obj.data.materials.append(mat).
- Render engines: 'CYCLES', 'BLENDER_EEVEE_NEXT' (4.2+; 'BLENDER_EEVEE' before 4.2), 'BLENDER_WORKBENCH'.
  Cycles: scene.cycles.samples, scene.cycles.use_denoising = True, scene.cycles.device = 'CPU' unless GPU set.
- Shade smooth without operators: for p in mesh.polygons: p.use_smooth = True (4.1+ removed mesh.use_auto_smooth;
  use bpy.ops.object.shade_smooth_by_angle() or a "Smooth by Angle" modifier instead).
- Import/export: bpy.ops.import_scene.gltf(filepath=...), bpy.ops.export_scene.gltf(filepath=..., export_format='GLB'),
  bpy.ops.wm.obj_import / wm.obj_export (4.x; NOT import_scene.obj), bpy.ops.wm.stl_import (4.1+),
  bpy.ops.wm.save_as_mainfile(filepath=...).
- Modifiers: obj.modifiers.new(name, 'SUBSURF'|'BEVEL'|'SOLIDIFY'|'MIRROR'|'ARRAY'|'BOOLEAN'|'NODES'...).
  Apply: bpy.ops.object.modifier_apply(modifier=name) with obj active.
- Geometry nodes: mod = obj.modifiers.new("GN", 'NODES'); tree = bpy.data.node_groups.new("GN", 'GeometryNodeTree');
  tree.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry') (4.0+, NOT tree.inputs.new);
  same with in_out='OUTPUT'; mod.node_group = tree.
- Animation: obj.location = (...); obj.keyframe_insert("location", frame=1). scene.frame_start / frame_end / render.fps.
- Lights: bpy.data.lights.new(name, 'POINT'|'SUN'|'SPOT'|'AREA'); energy in watts (area 200–1000 W for a product).
- Camera: cam = bpy.data.cameras.new(n); obj = bpy.data.objects.new(n, cam); scene.camera = obj;
  aim with a TRACK_TO constraint or rotation from (target - location).to_track_quat('-Z', 'Y').to_euler().
- World: scene.world = scene.world or bpy.data.worlds.new("World"); scene.world.use_nodes = True;
  scene.world.node_tree.nodes["Background"].inputs["Color"/"Strength"].
- Units: 1 Blender unit = 1 metre. Angles in radians (math.radians).
- Text: bpy.data.curves.new(n, 'FONT'); curve.body = "..."; bpy.data.objects.new(n, curve).
"""

KIT_DOC = """JARVIS toolkit — these functions ALREADY EXIST in the script (no import needed); metres everywhere:
clear()  — empty the scene (only for a brand-new scene)
box(name, size=(x,y,z), loc=(x,y,z), bevel=0.004, rot=(deg,deg,deg))  — size is the FULL extent, loc is the centre
cylinder(name, radius, depth, loc, bevel=0.002, rot=(deg,deg,deg), verts=64)  — axis along z before rot
sphere(name, radius, loc, segments=64)
tube(name, points=[(x,y,z),...], radius)  — round bar / pipe / handle / frame through points
lathe(name, profile=[(radius, z), ...], loc)  — turned shapes: cups, vases, bottles, lamp shades, chair feet
extrude(name, outline=[(x,y),...], depth, loc, bevel)  — flat outline made thick along z (signs, plates, shaped tops)
Materials (return a material): wood(name, color, grain) metal(name, color, rough) plastic(name, color, rough)
  paint(name, color, rough, coat) glass(name, tint, rough) fabric(name, color) rubber(name) stone(name, color)
  emission(name, color, strength);  assign(obj, material)
Placement (USE THEM — parts must touch, nothing floats): bottom(obj) top(obj) size(obj) on_floor(obj)
  place_on(obj, base, x=None, y=None) — obj rests exactly on base's top;  touch(obj, other, axis) — slide until touching
smooth(obj, angle)  join(objs, name)  group(name, objs)
studio(target=None, floor=True)  — floor, softbox lights, world, Cycles, framed camera (call it LAST for a new scene)
frame_camera(objs=None, yaw=-35, pitch=18, lens=60)
"""

REALISM = """Realism checklist (the result is judged from pictures, parts are measured):
- Real-world sizes (table 75 cm high, top 3–4 cm thick; chair seat 45 cm; mug 9.5 cm; car 4.5 m).
- Every part is attached: legs touch the underside of the top, inset 4–8 cm from the edges; nothing floats, no gaps,
  no part sinks through another. Compute positions from the other parts' sizes (use top()/bottom()/place_on()).
- Enough parts for the real thing (a table: top, 4 legs, aprons/rails between the legs, maybe a lower shelf;
  a chair: seat, legs, back posts, back slats, stretchers). Bevel every hard edge; smooth round parts.
- Proper materials from the toolkit (wood grain, brushed metal, fabric…), not flat grey.
- Build the object at the world origin standing on z = 0 (on_floor), then call studio() at the end."""

SCRIPT_RULES = """Write ONE complete Python script for Blender {version} run in background mode (no UI).
Rules:
- `import bpy` (and math, bmesh, mathutils, random as needed). No other imports, no file reads, no network,
  no subprocess, no os.system, no exec/eval, no input().
- The variable OUT (a pathlib.Path folder) already exists — save extra files only inside it.
- The scene file is saved for you afterwards; do not call save_as_mainfile or quit Blender.
- For a new scene finish with studio() (camera, lights, floor) unless the user asked otherwise.
- When the current scene already has objects and the request is a correction, CHANGE those objects (move, resize,
  replace, add missing parts); do not call clear() and do not add a second studio() if lights/camera exist.
- Name objects in Turkish, uniquely (Masa, Masa ayağı, Kamera, Işık).
- Build exactly the subject the user asked for — never a different object.
- Prefer data API (bpy.data, bmesh) over bpy.ops when an operator would need a 3D viewport.
- Make it detailed and realistic: bevels, subdivision, proper PBR materials, not placeholder blocks.
Return ONLY the code, no explanations, no markdown fences."""


# ── lessons ───────────────────────────────────────────────────────────────────

STOP = {"bir", "yap", "yapa", "olus", "olust", "modell", "model", "blende", "sahne", "icin", "ile", "olsun", "ver", "ekle",
        "the", "and", "with", "make", "create", "for", "add", "bana", "lutfe", "sunu", "bunu", "gibi", "daha", "cok"}


def _words(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (text or "").casefold().replace("ı", "i"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w[:6] for w in re.findall(r"[a-z0-9_.]{3,}", t)} - STOP    # crude stem: first 6 letters


def load() -> list[dict]:
    try:
        data = json.loads(LESSONS.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    tmp = LESSONS.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-MAX_LESSONS:], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(LESSONS)


def remember(kind: str, request: str, content, error: str = "") -> dict:
    """kind: recipe (steps that worked) | script (a bpy script that worked) | fix (an error and its cure) | tip."""
    item = {"kind": kind, "request": str(request)[:600], "content": content, "error": str(error)[:600],
            "created": time.strftime("%Y-%m-%d %H:%M"), "uses": 0}
    with _lock:
        items = load()
        key = (kind, item["request"], json.dumps(content, ensure_ascii=False)[:2000])
        items = [i for i in items if (i.get("kind"), i.get("request"), json.dumps(i.get("content"), ensure_ascii=False)[:2000]) != key]
        items.append(item)
        _save(items)
    return item


def recall(request: str, k: int = 4, kinds=("recipe", "script", "fix", "tip")) -> list[dict]:
    """The lessons closest to this request (shared words; tips and fixes always count a little)."""
    want = _words(request)
    scored = []
    for n, it in enumerate(load()):
        if it.get("kind") not in kinds:
            continue
        have = _words(it.get("request", "") + " " + it.get("error", ""))
        score = len(want & have) / (1 + len(have) ** 0.5)
        if it.get("kind") in ("tip", "fix"):
            score += 0.15
        if score > 0.1:
            scored.append((score, n, it))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [it for _s, _n, it in scored[:k]]


def lessons_prompt(request: str, kinds=("recipe", "script", "fix", "tip"), k: int = 4) -> str:
    out = []
    for it in recall(request, k, kinds):
        body = it["content"] if isinstance(it["content"], str) else json.dumps(it["content"], ensure_ascii=False)
        body = body[:2500]
        if it["kind"] == "tip":
            out.append(f"- Tip from the user: {body}")
        elif it["kind"] == "fix":
            out.append(f"- Earlier error «{it['error'][:300]}» was fixed with:\n{body}")
        else:
            out.append(f"- A similar request that worked («{it['request'][:160]}»):\n{body}")
    return ("Lessons JARVIS learned before (reuse what fits):\n" + "\n".join(out)) if out else ""


def summary() -> str:
    items = load()
    if not items:
        return "Henüz Blender'da öğrendiğim bir şey yok."
    count = {}
    for it in items:
        count[it.get("kind")] = count.get(it.get("kind"), 0) + 1
    names = {"recipe": "tarif", "script": "betik", "fix": "hata çözümü", "tip": "senin öğrettiğin ipucu"}
    parts = [f"{v} {names.get(k, k)}" for k, v in count.items()]
    last = "; ".join(it["request"][:60] for it in items[-3:])
    return f"Blender'da öğrendiklerim: {', '.join(parts)}. Son öğrendiklerim: {last}."


# ── script mode ───────────────────────────────────────────────────────────────

FORBIDDEN = re.compile(r"\b(subprocess|os\.system|os\.popen|shutil\.rmtree|__import__|eval\(|exec\(|socket|urllib|requests|"
                       r"ctypes|os\.remove|os\.unlink|rmdir|open\(\s*['\"]/|wm\.quit_blender)")


def clean_code(text: str) -> str:
    t = (text or "").strip()
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", t, re.S)
    if m:
        t = m.group(1)
    return t.strip() + "\n"


def check_code(code: str) -> str:
    """'' when the script may run, else why not."""
    if "import bpy" not in code:
        return "Betik bpy kullanmıyor."
    bad = FORBIDDEN.search(code)
    if bad:
        return f"Betikte izin verilmeyen ifade: {bad.group(0)}"
    try:
        compile(code, "<jarvis-blender>", "exec")
    except SyntaxError as exc:
        return f"SyntaxError: {exc.msg} (satır {exc.lineno})"
    return ""


def write_script(request: str, scene: dict, version: str, previous: str = "", error: str = "") -> str:
    from core import gemini
    lessons = lessons_prompt(request, ("script", "fix", "tip"), 4)
    prompt = (f"{KNOWLEDGE}\n{KIT_DOC}\n{REALISM}\n{SCRIPT_RULES.format(version=version)}\n\n{lessons}\n\n"
              f"Current scene: {json.dumps(scene, ensure_ascii=False)[:6000]}\n"
              f"User request (any language): {request}")
    if previous:
        prompt += (f"\n\nYour previous script failed.\nScript:\n{previous[:12000]}\n\nBlender error:\n{error[-3000:]}\n"
                   "Fix the cause (check the facts above) and return the whole corrected script.")
    return clean_code(gemini.text(prompt, tier=gemini.SMART) or "")


LOOK = """You are JARVIS's eye, checking its own Blender work. The image shows the scene from up to four sides
(scene camera / front / three-quarter / side / top). The user asked for: {request}
Measured geometry problems: {issues}
Judge like a demanding 3D artist. Return JSON:
{{"subject_ok": true|false (is it clearly the requested thing?),
  "score": 0-10 (10 = indistinguishable from a real, well-made product; 6 = clearly right but plain; <5 = wrong/broken),
  "problems": ["concrete fixes in Turkish, with parts and directions — e.g. 'Ayaklar tablanın altına değmiyor: 4 ayağı
   tablanın köşelerinden 6 cm içeriye ve tabla altına taşı', 'Ayaklar arasına kuşak (apron) yok', 'Malzeme düz gri'"]}}
At most 8 problems, most important first."""


def look(sheet_png: bytes, request: str, issues: list[str]) -> dict:
    """Show the picture of the scene to the model; get a score and what to fix."""
    from core import gemini
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=sheet_png, mime_type="image/png")
    except Exception:
        return {}
    verdict = gemini.as_json([LOOK.format(request=request, issues="; ".join(issues) or "yok"), part], tier=gemini.SMART)
    if not isinstance(verdict, dict) or "score" not in verdict:
        return {}
    try:
        verdict["score"] = float(verdict["score"])
    except (TypeError, ValueError):
        return {}
    verdict["problems"] = [str(p) for p in (verdict.get("problems") or [])][:8]
    return verdict


def run_with_fixes(request: str, scene: dict, version: str, execute, log=print) -> tuple[str, int]:
    """execute(code) runs a script in Blender and raises ValueError(traceback) on failure.
    Returns (working code, tries). Learns the script — and every error it got past."""
    code, error, errors = "", "", []
    for attempt in range(1, MAX_TRIES + 1):
        code = write_script(request, scene, version, code, error)
        why = check_code(code)
        try:
            if why:
                raise ValueError(why)
            execute(code)
        except ValueError as exc:
            error = str(exc)
            errors.append(error)
            log(f"[Blender] Deneme {attempt} hata verdi: {error.strip().splitlines()[-1][:200] if error.strip() else error}")
            continue
        remember("script", request, code)
        for e in errors:                                         # what went wrong, and the code that got past it
            last = e.strip().splitlines()[-1] if e.strip() else e
            remember("fix", request, code[:3000], last)
        return code, attempt
    raise ValueError(f"{MAX_TRIES} denemede çalışan bir Blender betiği yazamadım. Son hata: "
                     f"{error.strip().splitlines()[-1][:300] if error.strip() else error}")
