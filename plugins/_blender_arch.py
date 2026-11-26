"""FRIDAY's architecture engine — loaded inside Blender after _blender_kit.py
(it uses box(), assign(), the materials …). The model describes a building as
a plan (a dict); this file turns the plan into exact geometry, so walls meet,
slabs sit on walls, windows and doors are real holes with frames and glass,
stairs climb from slab to slab and the roof sits on the top slab.

Coordinates: the footprint is centred on the origin, x = width (left→right),
y = depth; the FRONT facade faces -y. Metres.

    building(plan) -> the building's root empty
    plan = {
      "name": "Apartman", "width": 16, "depth": 11, "floors": 4, "floor_height": 3.0,
      "wall": 0.25, "inner_wall": 0.12, "slab": 0.2,
      "rooms": [{"name": "Salon", "rect": [x0, y0, x1, y1]}, ...],   # same plan on every floor …
      "floor_rooms": {"0": [...]},                                      # … or per floor (key = floor index)
      "windows": {"width": 1.4, "height": 1.5, "sill": 0.9, "spacing": 3.2, "sides": ["front","back","left","right"]},
      "entrance": {"side": "front", "x": 0.0, "width": 1.6, "height": 2.5, "canopy": true},
      "balconies": {"side": "front", "width": 3.6, "depth": 1.4, "from_floor": 1, "positions": [-4.5, 4.5],
                    "rail": "glass" | "metal"},
      "stairs": {"rect": [x0, y0, x1, y1]},
      "roof": {"type": "gable" | "hip" | "flat", "pitch": 30, "overhang": 0.5},
      "style": {"facade": "plaster" | "brick" | "stone", "facade_color": [r,g,b], "base_color": [r,g,b],
                "roof_color": [r,g,b], "frame_color": [r,g,b], "door_color": [r,g,b]}
    }
    outdoor(target=None)  — grass site, sun, sky, architectural camera (instead of studio() for buildings)
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector

EPS = 1e-4


# ── low-level: meshes from boxes, booleans baked into the mesh ───────────────

def _boxes_mesh(name, boxes):
    """One object made of several boxes: boxes = [(centre, size, rot_z_deg), ...] (world)."""
    bm = bmesh.new()
    for centre, size, rz in boxes:
        geom = bmesh.ops.create_cube(bm, size=1.0)
        verts = geom["verts"]
        bmesh.ops.scale(bm, vec=Vector(size), verts=verts)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=_rot(rz), verts=verts)
        bmesh.ops.translate(bm, vec=Vector(centre), verts=verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _rot(deg):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(deg), 3, "Z")


def _bake(obj):
    """Apply every modifier into the mesh (no operators, works headless)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def _cut(obj, cutters, name="Boşluk"):
    """Holes: subtract the cutter boxes from obj and bake the result."""
    if not cutters:
        return obj
    cutter = _boxes_mesh(f"{obj.name} {name}", cutters)
    mod = obj.modifiers.new(name, "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    _bake(obj)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return obj


def _anchor(name, loc, rz):
    """An empty at an opening; parts are built in its local frame (x along the wall, y outward, z up)."""
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.location = loc
    e.rotation_euler = (0, 0, math.radians(rz))
    e.empty_display_size = 0.2
    return e


def _part(parent, obj):
    obj.parent = parent
    return obj


# ── walls, openings, windows, doors ──────────────────────────────────────────

class Wall:
    """A straight wall from a to b (2D), z0..z0+h, thickness t, with openings along it."""

    def __init__(self, name, a, b, z0, h, t, outward=None):
        self.name, self.a, self.b, self.z0, self.h, self.t = name, Vector((*a, 0)), Vector((*b, 0)), z0, h, t
        d = self.b - self.a
        self.length = d.length
        self.dir = d.normalized()
        self.rz = math.degrees(math.atan2(d.y, d.x))
        self.normal = Vector((self.dir.y, -self.dir.x, 0)) if outward is None else Vector((*outward, 0)).normalized()
        self.openings = []          # (u from a, width, bottom above z0, height, kind)

    def add(self, u, width, bottom, height, kind):
        u = min(max(u, width / 2 + 0.15), self.length - width / 2 - 0.15)
        if width + 0.3 > self.length or bottom + height > self.h - 0.05:
            return None
        for ou, ow, *_ in self.openings:                      # never two holes on top of each other
            if abs(ou - u) < (ow + width) / 2 + 0.2:
                return None
        self.openings.append((u, width, bottom, height, kind))
        return u

    def point(self, u, z):
        p = self.a + self.dir * u
        return Vector((p.x, p.y, self.z0 + z))

    def build(self, material):
        mid = (self.a + self.b) / 2
        obj = _boxes_mesh(self.name, [((mid.x, mid.y, self.z0 + self.h / 2), (self.length, self.t, self.h), self.rz)])
        cutters = []
        for u, w, bottom, height, _kind in self.openings:
            c = self.point(u, bottom + height / 2)
            cutters.append(((c.x, c.y, c.z), (w, self.t + 0.4, height), self.rz))
        _cut(obj, cutters)
        assign(obj, material)
        return obj


def window(name, wall, u, width, height, bottom, mats):
    """Frame, mullion/transom, glass and an outside sill, fitted in a wall opening."""
    c = wall.point(u, bottom + height / 2)
    rz = math.degrees(math.atan2(wall.normal.y, wall.normal.x)) - 90.0     # local -y … +y = inside … outside
    e = _anchor(name, c, rz)
    f, d = 0.065, min(0.09, wall.t * 0.6)
    parts = [box(f"{name} kasa sol", (f, d, height), (-width / 2 + f / 2, 0, 0), bevel=0.004),
             box(f"{name} kasa sağ", (f, d, height), (width / 2 - f / 2, 0, 0), bevel=0.004),
             box(f"{name} kasa üst", (width, d, f), (0, 0, height / 2 - f / 2), bevel=0.004),
             box(f"{name} kasa alt", (width, d, f), (0, 0, -height / 2 + f / 2), bevel=0.004)]
    if width > 1.1:
        parts.append(box(f"{name} kayıt", (f * 0.8, d * 0.9, height - 2 * f), (0, 0, 0), bevel=0.003))
    if height > 1.6:
        parts.append(box(f"{name} vasistas kaydı", (width - 2 * f, d * 0.9, f * 0.8), (0, 0, height / 2 - 0.45), bevel=0.003))
    for p in parts:
        assign(_part(e, p), mats["frame"])
    glass_ = box(f"{name} cam", (width - 2 * f + 0.002, 0.012, height - 2 * f + 0.002), (0, 0, 0), bevel=0)
    assign(_part(e, glass_), mats["glass"])
    sill = box(f"{name} denizlik", (width + 0.12, wall.t / 2 + 0.06, 0.04),
               (0, wall.t / 4 + 0.03, -height / 2 - 0.02), bevel=0.006)
    assign(_part(e, sill), mats["sill"])
    return e


def door(name, wall, u, width, height, mats, outside_step=False):
    c = wall.point(u, height / 2)
    rz = math.degrees(math.atan2(wall.normal.y, wall.normal.x)) - 90.0
    e = _anchor(name, c, rz)
    f, d = 0.07, min(0.11, wall.t * 0.7)
    for p in (box(f"{name} kasa sol", (f, d, height), (-width / 2 + f / 2, 0, 0), bevel=0.004),
              box(f"{name} kasa sağ", (f, d, height), (width / 2 - f / 2, 0, 0), bevel=0.004),
              box(f"{name} kasa üst", (width, d, f), (0, 0, height / 2 - f / 2), bevel=0.004)):
        assign(_part(e, p), mats["frame"])
    leaf = box(f"{name} kanat", (width - 2 * f, 0.045, height - f), (0, 0, -f / 2), bevel=0.005)
    assign(_part(e, leaf), mats["door"])
    if width - 2 * f > 1.2:                                  # double door: a centre line
        line = box(f"{name} orta", (0.012, 0.05, height - f), (0, 0, -f / 2), bevel=0)
        assign(_part(e, line), mats["frame"])
    handle = cylinder(f"{name} kol", 0.012, 0.14, (width / 2 - f - 0.09, 0.045, 0.0), rot=(90, 0, 0), bevel=0.001)
    assign(_part(e, handle), mats["metal"])
    if outside_step:
        step = box(f"{name} basamak", (width + 0.6, 0.45, 0.16), (0, wall.t / 2 + 0.225, -height / 2 - 0.08), bevel=0.01)
        assign(_part(e, step), mats["base"])
    return e


# ── materials for buildings ──────────────────────────────────────────────────

def _wall_uv(nt):
    """(x + y, z): runs along any axis-aligned wall, so bricks lie flat on every facade."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs[0], add.inputs[0])
    nt.links.new(sep.outputs[1], add.inputs[1])
    nt.links.new(add.outputs[0], comb.inputs[0])
    nt.links.new(sep.outputs[2], comb.inputs[1])
    return comb.outputs[0]


def brick(name, color=(0.55, 0.22, 0.14), mortar=(0.75, 0.73, 0.7)):
    mat, nt, bsdf = _principled(name)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value = (*color, 1)
    br.inputs["Color2"].default_value = (*(Vector(color) * 0.8), 1)
    br.inputs["Mortar"].default_value = (*mortar, 1)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Brick Width"].default_value = 0.25          # a real brick: 25 × 6.5 cm
    br.inputs["Row Height"].default_value = 0.075
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    nt.links.new(_wall_uv(nt), br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(br.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Roughness", 0.85)
    return mat


def plaster(name, color=(0.86, 0.83, 0.77)):
    mat, nt, bsdf = _principled(name)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    c = Vector(color)
    ramp.color_ramp.elements[0].color = (*(c * 0.92), 1)
    ramp.color_ramp.elements[1].color = (*c, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Roughness", 0.9)
    return mat


def roof_tiles(name, color=(0.45, 0.13, 0.08)):
    mat, nt, bsdf = _principled(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value = (*color, 1)
    br.inputs["Color2"].default_value = (*(Vector(color) * 0.75), 1)
    br.inputs["Mortar"].default_value = (*(Vector(color) * 0.35), 1)
    br.inputs["Scale"].default_value = 3.0
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Brick Width"].default_value = 0.5
    br.inputs["Row Height"].default_value = 0.3
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    nt.links.new(br.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(br.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Roughness", 0.6)
    return mat


def _materials(style):
    s = style or {}
    facade_kind = s.get("facade", "plaster")
    fc = tuple(s.get("facade_color") or (0.86, 0.83, 0.77))
    facade = brick("Cephe tuğla", fc if s.get("facade_color") else (0.55, 0.22, 0.14)) if facade_kind == "brick" else \
        stone("Cephe taş", fc) if facade_kind == "stone" else plaster("Cephe sıva", fc)
    return {
        "facade": facade,
        "inner": plaster("İç duvar", (0.92, 0.91, 0.88)),
        "slab": stone("Döşeme beton", (0.55, 0.54, 0.52)),
        "base": stone("Subasman", tuple(s.get("base_color") or (0.42, 0.41, 0.4))),
        "roof": roof_tiles("Kiremit", tuple(s.get("roof_color") or (0.45, 0.13, 0.08))),
        "flat_roof": stone("Teras", (0.35, 0.35, 0.35)),
        "frame": plastic("Doğrama", tuple(s.get("frame_color") or (0.93, 0.93, 0.92)), 0.35),
        "glass": glass("Cam", (0.85, 0.92, 0.95), 0.0),
        "sill": stone("Denizlik", (0.8, 0.79, 0.76)),
        "door": wood("Kapı", tuple(s.get("door_color") or (0.3, 0.17, 0.08))),
        "metal": metal("Metal", (0.2, 0.2, 0.21), 0.35),
        "rail_glass": glass("Korkuluk camı", (0.8, 0.9, 0.92), 0.05),
        "stairs": stone("Merdiven", (0.7, 0.69, 0.66)),
    }


# ── rooms → interior walls ───────────────────────────────────────────────────

def _interior_segments(rooms, W, D, t_out):
    """Room edges that are not on the facade, merged where two rooms share them."""
    inner_x0, inner_x1, inner_y0, inner_y1 = -W / 2 + t_out, W / 2 - t_out, -D / 2 + t_out, D / 2 - t_out
    horiz, vert = {}, {}
    for r in rooms:
        x0, y0, x1, y1 = (float(v) for v in r["rect"])
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        for y in (y0, y1):
            if abs(y - inner_y0) > 0.3 and abs(y - inner_y1) > 0.3 and abs(y + D / 2) > 0.3 and abs(y - D / 2) > 0.3:
                horiz.setdefault(round(y, 2), []).append((max(x0, inner_x0), min(x1, inner_x1), r["name"]))
        for x in (x0, x1):
            if abs(x - inner_x0) > 0.3 and abs(x - inner_x1) > 0.3 and abs(x + W / 2) > 0.3 and abs(x - W / 2) > 0.3:
                vert.setdefault(round(x, 2), []).append((max(y0, inner_y0), min(y1, inner_y1), r["name"]))

    def merge(spans):
        spans = sorted(spans)
        out = []
        for a, b, n in spans:
            if b - a < 0.3:
                continue
            if out and a <= out[-1][1] + 0.05:
                out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2] + [n])
            else:
                out.append((a, b, [n]))
        return out
    segs = []
    for y, spans in horiz.items():
        for a, b, names in merge(spans):
            segs.append(((a, y), (b, y), names))
    for x, spans in vert.items():
        for a, b, names in merge(spans):
            segs.append(((x, a), (x, b), names))
    return segs


# ── stairs ───────────────────────────────────────────────────────────────────

def _stairs(name, rect, z_base, rise, mat):
    """Solid steps from z_base up `rise`; a switchback with a landing when one flight does not fit."""
    x0, y0, x1, y1 = rect
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    n = max(2, math.ceil(rise / 0.18))
    h = rise / n
    along_y = (y1 - y0) >= (x1 - x0)
    L, Wd = ((y1 - y0), (x1 - x0)) if along_y else ((x1 - x0), (y1 - y0))
    boxes = []

    def step(i, start, direction, lane0, lane1, z0, count, going):
        top = z0 + (i + 1) * h
        s = start + direction * (i + 0.5) * going
        c_lane = (lane0 + lane1) / 2
        w_lane = lane1 - lane0
        hgt = top - z_base
        if along_y:
            boxes.append(((c_lane, s, z_base + hgt / 2), (w_lane, going, hgt), 0))
        else:
            boxes.append(((s, c_lane, z_base + hgt / 2), (going, w_lane, hgt), 0))
    a0, a1 = (y0, y1) if along_y else (x0, x1)
    l0, l1 = (x0, x1) if along_y else (y0, y1)
    if n * 0.26 <= L:                                       # one straight flight
        going = min(0.3, L / n)
        for i in range(n):
            step(i, a0, 1, l0, l1, z_base, n, going)
    else:                                                    # two flights and a landing
        half = n // 2
        landing = min(max(Wd / 2, 1.0), L * 0.35)
        going = min(0.3, (L - landing) / max(half, n - half))
        mid = (l0 + l1) / 2
        for i in range(half):
            step(i, a0, 1, l0, mid - 0.02, z_base, half, going)
        z_land = z_base + half * h
        land_c = a1 - landing / 2
        if along_y:
            boxes.append((((l0 + l1) / 2, land_c, z_base + (z_land - z_base) / 2), (l1 - l0, landing, z_land - z_base), 0))
        else:
            boxes.append(((land_c, (l0 + l1) / 2, z_base + (z_land - z_base) / 2), (landing, l1 - l0, z_land - z_base), 0))
        start2 = a1 - landing
        for i in range(n - half):
            top = z_land + (i + 1) * h
            s = start2 - (i + 0.5) * going
            hgt = top - z_base
            if along_y:
                boxes.append((((mid + 0.02 + l1) / 2, s, z_base + hgt / 2), (l1 - mid - 0.02, going, hgt), 0))
            else:
                boxes.append(((s, (mid + 0.02 + l1) / 2, z_base + hgt / 2), (going, l1 - mid - 0.02, hgt), 0))
    obj = _boxes_mesh(name, boxes)
    assign(obj, mat)
    return obj


# ── roofs ────────────────────────────────────────────────────────────────────

def _roof(name, W, D, z, kind, pitch, overhang, mats, t_wall):
    o = overhang
    hw, hd = W / 2 + o, D / 2 + o
    if kind == "flat":
        slab = box(f"{name} teras", (W, D, 0.12), (0, 0, z + 0.06), bevel=0.01)
        assign(slab, mats["flat_roof"])
        rail = []
        for nm, size_, loc in ((f"{name} parapet ön", (W, 0.2, 0.9), (0, -D / 2 + 0.1, z + 0.12 + 0.45)),
                               (f"{name} parapet arka", (W, 0.2, 0.9), (0, D / 2 - 0.1, z + 0.12 + 0.45)),
                               (f"{name} parapet sol", (0.2, D - 0.4, 0.9), (-W / 2 + 0.1, 0, z + 0.12 + 0.45)),
                               (f"{name} parapet sağ", (0.2, D - 0.4, 0.9), (W / 2 - 0.1, 0, z + 0.12 + 0.45))):
            p = box(nm, size_, loc, bevel=0.01)
            assign(p, mats["facade"])
            rail.append(p)
        cap = box(f"{name} su basman", (W + 0.08, D + 0.08, 0.06), (0, 0, z + 0.12 + 0.9 + 0.03), bevel=0.01)
        _cut(cap, [((0, 0, z + 1.05), (W - 0.42, D - 0.42, 0.4), 0)])
        assign(cap, mats["sill"])
        return [slab] + rail + [cap]
    ridge_along_x = W >= D
    span = hd if ridge_along_x else hw
    rise = span * math.tan(math.radians(pitch))
    bm = bmesh.new()
    if ridge_along_x:
        r = hw - (hd if kind == "hip" else 0.0)
        r = max(r, 0.0)
        v = [bm.verts.new(p) for p in ((-hw, -hd, z), (hw, -hd, z), (hw, hd, z), (-hw, hd, z), (-r, 0, z + rise), (r, 0, z + rise))]
        faces = [(v[0], v[1], v[5], v[4]), (v[2], v[3], v[4], v[5]), (v[1], v[2], v[5]), (v[3], v[0], v[4])]
    else:
        r = max(hd - (hw if kind == "hip" else 0.0), 0.0)
        v = [bm.verts.new(p) for p in ((-hw, -hd, z), (hw, -hd, z), (hw, hd, z), (-hw, hd, z), (0, -r, z + rise), (0, r, z + rise))]
        faces = [(v[1], v[2], v[5], v[4]), (v[3], v[0], v[4], v[5]), (v[0], v[1], v[4]), (v[2], v[3], v[5])]
    roof_faces = []
    for f in faces:
        try:
            roof_faces.append(bm.faces.new(f))
        except ValueError:
            pass
    if kind == "gable":                                     # gable ends are walls, not roof
        for f in list(bm.faces):
            if len(f.verts) == 3:
                bm.faces.remove(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    roof = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(roof)
    sol = roof.modifiers.new("Kalınlık", "SOLIDIFY")
    sol.thickness = 0.16
    sol.offset = 1.0
    _bake(roof)
    assign(roof, mats["roof"])
    out = [roof]
    if kind == "gable":                                     # triangular gable walls on the facade line
        for side in (-1, 1):
            bm = bmesh.new()
            if ridge_along_x:
                x = side * (W / 2 - t_wall / 2)
                tn = math.tan(math.radians(pitch))       # follows the roof's underside, so roof and wall meet
                tri = [(x - t_wall / 2, -D / 2, z), (x - t_wall / 2, D / 2, z), (x - t_wall / 2, D / 2, z + o * tn),
                       (x - t_wall / 2, 0, z + hd * tn), (x - t_wall / 2, -D / 2, z + o * tn)]
                vs = [bm.verts.new(p) for p in tri]
                face = bm.faces.new(vs)
                ext = bmesh.ops.extrude_face_region(bm, geom=[face])
                bmesh.ops.translate(bm, verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(t_wall, 0, 0))
            else:
                y = side * (D / 2 - t_wall / 2)
                tn = math.tan(math.radians(pitch))
                tri = [(-W / 2, y - t_wall / 2, z), (W / 2, y - t_wall / 2, z), (W / 2, y - t_wall / 2, z + o * tn),
                       (0, y - t_wall / 2, z + hw * tn), (-W / 2, y - t_wall / 2, z + o * tn)]
                vs = [bm.verts.new(p) for p in tri]
                face = bm.faces.new(vs)
                ext = bmesh.ops.extrude_face_region(bm, geom=[face])
                bmesh.ops.translate(bm, verts=[e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)], vec=(0, t_wall, 0))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            me = bpy.data.meshes.new(f"{name} alın {side}")
            bm.to_mesh(me)
            bm.free()
            g = bpy.data.objects.new(f"{name} alın duvarı {'sol' if side < 0 else 'sağ'}", me)
            bpy.context.scene.collection.objects.link(g)
            assign(g, mats["facade"])
            out.append(g)
    return out


# ── the building ─────────────────────────────────────────────────────────────

def building(plan):
    p = dict(plan or {})
    name = p.get("name", "Bina")
    W, D = float(p.get("width", 12)), float(p.get("depth", 9))
    floors = max(1, int(p.get("floors", 2)))
    fh = float(p.get("floor_height", 3.0))
    t, ti, ts = float(p.get("wall", 0.25)), float(p.get("inner_wall", 0.12)), float(p.get("slab", 0.2))
    mats = _materials(p.get("style"))
    win = {"width": 1.4, "height": 1.5, "sill": 0.9, "spacing": 3.2, "sides": ["front", "back", "left", "right"]}
    win.update(p.get("windows") or {})
    ent = {"side": "front", "x": 0.0, "width": 1.6, "height": 2.5, "canopy": True}
    ent.update(p.get("entrance") or {})
    bal = p.get("balconies") or {}
    stairs = p.get("stairs") or {}
    made = []
    wall_h = fh - ts
    sides = {   # name: (a, b, outward)  — along the outer face line, centred in the wall thickness
        "front": ((-W / 2, -D / 2 + t / 2), (W / 2, -D / 2 + t / 2), (0, -1)),
        "back": ((W / 2, D / 2 - t / 2), (-W / 2, D / 2 - t / 2), (0, 1)),
        "left": ((-W / 2 + t / 2, D / 2 - t), (-W / 2 + t / 2, -D / 2 + t), (-1, 0)),
        "right": ((W / 2 - t / 2, -D / 2 + t), (W / 2 - t / 2, D / 2 - t), (1, 0)),
    }
    bal_positions = [float(x) for x in (bal.get("positions") or [])] if bal else []
    for level in range(floors + 1):                         # slabs: ground, each floor, top
        z = level * fh
        slab = box(f"Döşeme {level}" if level < floors else "Çatı döşemesi", (W, D, ts), (0, 0, z + ts / 2), bevel=0.01)
        if 0 < level < floors and stairs.get("rect"):
            x0, y0, x1, y1 = stairs["rect"]
            _cut(slab, [(((x0 + x1) / 2, (y0 + y1) / 2, z + ts / 2), (abs(x1 - x0), abs(y1 - y0), ts + 0.4), 0)])
        assign(slab, mats["slab"] if level else mats["base"])
        made.append(slab)
    for level in range(floors):
        z0 = level * fh + ts
        for side, (a, b, out) in sides.items():
            w = Wall(f"Dış duvar {side} {level}", a, b, z0, wall_h, t, out)
            u_door = None
            if level == 0 and side == ent["side"]:
                u_center = (float(ent["x"]) - a[0]) if side in ("front",) else (a[0] - float(ent["x"])) if side == "back" \
                    else (float(ent["x"]) - a[1]) if side == "right" else (a[1] - float(ent["x"]))
                u_door = w.add(u_center, float(ent["width"]), 0.0, min(float(ent["height"]), wall_h - 0.3), "entrance")
            bal_doors = []
            if bal and side == bal.get("side", "front") and level >= int(bal.get("from_floor", 1)):
                for x in bal_positions:
                    u = (x - a[0]) if side == "front" else (a[0] - x) if side == "back" else (x - a[1]) if side == "right" else (a[1] - x)
                    got = w.add(u, 0.95, 0.0, 2.2, "balcony")
                    if got is not None:
                        bal_doors.append((got, x))
            if side in win["sides"]:
                n = max(1, int((w.length - 0.8) // float(win["spacing"])))
                step_ = w.length / n
                for k in range(n):
                    w.add(step_ * (k + 0.5), float(win["width"]), float(win["sill"]), float(win["height"]), "window")
            made.append(w.build(mats["facade"]))
            for idx, (u, width, bottom, height, kind) in enumerate(w.openings):
                tag = f"{side} {level}-{idx + 1}"
                if kind == "window":
                    window(f"Pencere {tag}", w, u, width, height, bottom, mats)
                elif kind == "entrance":
                    door(f"Giriş kapısı", w, u, width, height, mats, outside_step=True)
                    if ent.get("canopy", True):
                        c = w.point(u, height + 0.12)
                        cnp = box("Giriş saçağı", (width + 1.0, 1.2, 0.12), (c.x + w.normal.x * (t / 2 + 0.6), c.y + w.normal.y * (t / 2 + 0.6), c.z),
                                  bevel=0.01, rot=(0, 0, w.rz))
                        assign(cnp, mats["sill"])
                else:
                    door(f"Balkon kapısı {tag}", w, u, width, height, mats)
            for u, x in bal_doors:                          # the balcony itself, on the slab edge
                depth, width = float(bal.get("depth", 1.4)), float(bal.get("width", 3.4))
                zb = level * fh
                base = w.point(u, 0)
                cx, cy = base.x + w.normal.x * (t / 2 + depth / 2), base.y + w.normal.y * (t / 2 + depth / 2)
                sl = box(f"Balkon {tag}", (width, depth, ts), (cx, cy, zb + ts / 2), bevel=0.01, rot=(0, 0, w.rz))
                assign(sl, mats["slab"])
                rail_h = 1.05
                # posts and a top rail on the three open sides, panels between
                along, outn = w.dir, w.normal
                corners = [base + along * (-width / 2 + 0.04) + outn * (t / 2 + 0.04),
                           base + along * (-width / 2 + 0.04) + outn * (t / 2 + depth - 0.04),
                           base + along * (width / 2 - 0.04) + outn * (t / 2 + depth - 0.04),
                           base + along * (width / 2 - 0.04) + outn * (t / 2 + 0.04)]
                for k, cpt in enumerate(corners):
                    post = box(f"Balkon {tag} dikme {k + 1}", (0.05, 0.05, rail_h), (cpt.x, cpt.y, zb + ts + rail_h / 2), bevel=0.003)
                    assign(post, mats["metal"])
                for k in range(3):
                    a2, b2 = corners[k], corners[k + 1]
                    mid = (a2 + b2) / 2
                    ln = (b2 - a2).length
                    rz = math.degrees(math.atan2((b2 - a2).y, (b2 - a2).x))
                    top_ = box(f"Balkon {tag} küpeşte {k + 1}", (ln + 0.05, 0.06, 0.05), (mid.x, mid.y, zb + ts + rail_h + 0.025), bevel=0.004, rot=(0, 0, rz))
                    assign(top_, mats["metal"])
                    if bal.get("rail", "glass") == "glass":
                        pane = box(f"Balkon {tag} cam {k + 1}", (ln - 0.05, 0.012, rail_h - 0.06), (mid.x, mid.y, zb + ts + (rail_h - 0.06) / 2 + 0.03), bevel=0, rot=(0, 0, rz))
                        assign(pane, mats["rail_glass"])
                    else:
                        for q in range(1, int(ln / 0.12)):
                            pt = a2 + (b2 - a2) * (q / int(ln / 0.12))
                            bar = box(f"Balkon {tag} çubuk {k + 1}-{q}", (0.018, 0.018, rail_h), (pt.x, pt.y, zb + ts + rail_h / 2), bevel=0)
                            assign(bar, mats["metal"])
        rooms = (p.get("floor_rooms") or {}).get(str(level)) or p.get("rooms") or []
        for k, (a, b, names) in enumerate(_interior_segments(rooms, W, D, t)):
            w = Wall(f"İç duvar {level}-{k + 1}", a, b, z0, wall_h, ti)
            if w.length > 1.4:
                w.add(w.length / 2, 0.9, 0.0, 2.1, "door")
            w.build(mats["inner"])
            for u, width, bottom, height, _kind in w.openings:
                door(f"İç kapı {level}-{k + 1}", w, u, width, height, mats)
        if stairs.get("rect") and level < floors - 1:
            _stairs(f"Merdiven {level}", stairs["rect"], level * fh + ts, fh, mats["stairs"])
    _roof(f"{name} çatısı", W, D, floors * fh + ts, (p.get("roof") or {}).get("type", "gable"),
          float((p.get("roof") or {}).get("pitch", 30)), float((p.get("roof") or {}).get("overhang", 0.5)), mats, t)
    for ex in p.get("extras") or []:                       # the user's own additions: pool, garden, fence …
        code = str(ex.get("code") or "")
        if not code.strip():
            continue
        try:
            exec(compile(code, f"ek: {ex.get('name', 'ek')}", "exec"), globals())
        except Exception as exc:
            raise RuntimeError(f"AETHER_EXTRA_FAILED::{ex.get('name', 'ek')}::{type(exc).__name__}: {exc}") from exc
    bpy.context.view_layer.update()
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    return root


def outdoor(target=None, samples=128, yaw=-32.0, pitch=10.0):
    """Grass site, sun and sky for buildings, and an architectural camera (35 mm)."""
    scene = bpy.context.scene
    objs = [o for o in scene.objects if o.type in ("MESH", "CURVE", "FONT") and not o.get("aether_floor")]
    span = max((size(o).length for o in objs), default=10.0)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=span * 6)
    me = bpy.data.meshes.new("Arazi")
    bm.to_mesh(me)
    bm.free()
    site = bpy.data.objects.new("Arazi", me)
    scene.collection.objects.link(site)
    site["aether_floor"] = True
    site.location.z = -0.001
    mat, nt, bsdf = _principled("Çim")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 30.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.05, 0.11, 0.03, 1)
    ramp.color_ramp.elements[1].color = (0.13, 0.22, 0.06, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.95)
    site.data.materials.append(mat)
    sun = bpy.data.lights.new("Güneş", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(1.5)
    so = bpy.data.objects.new("Güneş", sun)
    scene.collection.objects.link(so)
    so.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.45, 0.6, 0.85, 1)
        bg.inputs["Strength"].default_value = 0.8
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    import _cycles
    scene.cycles.use_denoising = getattr(_cycles, "with_openimagedenoise", True)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    frame_camera(objs, yaw=yaw, pitch=pitch, lens=35.0, margin=1.06)
    return scene.camera
