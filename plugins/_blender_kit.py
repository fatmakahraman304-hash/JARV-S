"""JARVIS's Blender toolkit — loaded inside Blender before every script JARVIS
writes, so a script can say `wood("Ceviz")` or `place_on(leg, floor)` instead of
fighting node trees and bounding boxes. Everything here uses real metres.

The functions (documented for the model in KIT_DOC in _blender_brain.py):
    clear()                                       empty scene
    box(name, size, loc=(0,0,0), bevel=0.004, rot=(0,0,0))        size = full x,y,z extents
    cylinder(name, radius, depth, loc=(0,0,0), bevel=0.002, rot=(0,0,0), verts=64)
    sphere(name, radius, loc=(0,0,0), segments=64)
    tube(name, points, radius, bevel_res=12)      a round bar through 3D points (rails, handles, frames)
    lathe(name, profile, loc=(0,0,0), steps=96)   profile = [(radius, z), ...] turned around z (vases, cups, lamps)
    extrude(name, outline, depth, loc=(0,0,0), bevel=0.003)   2D outline [(x,y),...] made thick along z
    wood(name, color=(0.36,0.2,0.1), grain=1.0)   procedural wood
    metal(name, color=(0.8,0.8,0.82), rough=0.25) brushed metal
    plastic(name, color, rough=0.4) / paint(name, color, rough=0.25, coat=0.6)
    glass(name, tint=(1,1,1), rough=0.0) / fabric(name, color) / rubber(name) / stone(name, color)
    emission(name, color, strength=8)
    assign(obj, material)
    bottom(obj) / top(obj) / size(obj)            world-space bounds
    on_floor(obj)                                 rest the object on z = 0
    place_on(obj, base, x=None, y=None)           rest obj exactly on top of base (optionally at x,y)
    touch(obj, other, axis="z")                   slide obj along an axis until it touches other
    smooth(obj, angle=35)                         smooth shading with sharp edges kept
    join(objs, name)                              one object
    group(name, objs)                             an empty parent for several parts
    studio(target=None, floor=True)               floor, softbox lights, world, framed camera, Cycles
    frame_camera(objs=None)                       camera aimed and framed on the meshes
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Vector


def _link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(bpy.data.objects.new(name, me))


def _bevel(obj, width, segments=3):
    if width and width > 0:
        m = obj.modifiers.new("Pah", "BEVEL")
        m.width = width
        m.segments = segments
        m.limit_method = "ANGLE"
        try:
            m.harden_normals = True
        except Exception:
            pass
    return obj


def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def box(name, size, loc=(0, 0, 0), bevel=0.004, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = _mesh_obj(name, bm)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    return _bevel(obj, min(bevel, min(size) * 0.45))


def cylinder(name, radius, depth, loc=(0, 0, 0), bevel=0.002, rot=(0, 0, 0), verts=64):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius, radius2=radius, depth=depth)
    obj = _mesh_obj(name, bm)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    smooth(obj)
    return _bevel(obj, min(bevel, radius * 0.4, depth * 0.4))


def sphere(name, radius, loc=(0, 0, 0), segments=64):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=segments // 2, radius=radius)
    obj = _mesh_obj(name, bm)
    obj.location = loc
    return smooth(obj, 80)


def tube(name, points, radius, bevel_res=12):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY" if len(points) < 3 else "NURBS")
    sp.points.add(len(points) - 1)
    for p, c in zip(sp.points, points):
        p.co = (c[0], c[1], c[2], 1)
    if sp.type == "NURBS":
        sp.use_endpoint_u = True
        sp.order_u = 3
    cu.bevel_depth = radius
    cu.bevel_resolution = bevel_res
    cu.use_fill_caps = True
    return _link(bpy.data.objects.new(name, cu))


def lathe(name, profile, loc=(0, 0, 0), steps=96):
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = [bm.verts.new((r * math.cos(2 * math.pi * i / steps), r * math.sin(2 * math.pi * i / steps), z))
                for i in range(steps)]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(steps):
            j = (i + 1) % steps
            bm.faces.new((a[i], a[j], b[j], b[i]))
    obj = _mesh_obj(name, bm)
    obj.location = loc
    bm2 = bmesh.new()
    bm2.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm2, faces=bm2.faces)
    bm2.to_mesh(obj.data)
    bm2.free()
    sol = obj.modifiers.new("Kalınlık", "SOLIDIFY")
    sol.thickness = 0.003
    return smooth(obj, 60)


def extrude(name, outline, depth, loc=(0, 0, 0), bevel=0.003):
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, 0)) for x, y in outline]
    face = bm.faces.new(verts)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, 0, depth))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _mesh_obj(name, bm)
    obj.location = loc
    return _bevel(obj, bevel)


# ── materials ────────────────────────────────────────────────────────────────

def _principled(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    return mat, nt, bsdf


def _set(bsdf, key, value):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = value


def wood(name, color=(0.36, 0.2, 0.1), grain=1.0):
    """Long-fibre grain along the object's x axis, darker growth lines, a light varnish."""
    mat, nt, bsdf = _principled(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.5 * grain, 40.0 * grain, 40.0 * grain)     # stretched: fibres run along x
    fib = nt.nodes.new("ShaderNodeTexNoise")
    fib.inputs["Scale"].default_value = 2.0
    fib.inputs["Detail"].default_value = 8.0
    fib.inputs["Roughness"].default_value = 0.65
    rings = nt.nodes.new("ShaderNodeTexWave")
    rings.wave_type = "BANDS"
    rings.bands_direction = "Y"
    rings.inputs["Scale"].default_value = 0.6
    rings.inputs["Distortion"].default_value = 4.0
    rings.inputs["Detail"].default_value = 2.0
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    c = Vector(color)
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (*(c * 0.5), 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (*(c * 1.15), 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    L = nt.links
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    L.new(mp.outputs["Vector"], fib.inputs["Vector"])
    L.new(mp.outputs["Vector"], rings.inputs["Vector"])
    L.new(fib.outputs["Fac"], mix.inputs[0])
    L.new(rings.outputs["Fac"], mix.inputs[1])
    L.new(fib.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    L.new(mix.outputs[0], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Roughness", 0.42)
    _set(bsdf, "Coat Weight", 0.3)
    _set(bsdf, "Coat Roughness", 0.15)
    return mat


def metal(name, color=(0.8, 0.8, 0.82), rough=0.25):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*color, 1))
    _set(bsdf, "Metallic", 1.0)
    _set(bsdf, "Roughness", rough)
    _set(bsdf, "Anisotropic", 0.4)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 300.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.02
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def plastic(name, color=(0.1, 0.1, 0.1), rough=0.4):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*color, 1))
    _set(bsdf, "Roughness", rough)
    return mat


def paint(name, color=(0.6, 0.02, 0.02), rough=0.25, coat=0.6):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*color, 1))
    _set(bsdf, "Metallic", 0.3)
    _set(bsdf, "Roughness", rough)
    _set(bsdf, "Coat Weight", coat)
    _set(bsdf, "Coat Roughness", 0.03)
    return mat


def glass(name, tint=(1, 1, 1), rough=0.0):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*tint, 1))
    _set(bsdf, "Roughness", rough)
    _set(bsdf, "Transmission Weight", 1.0)
    _set(bsdf, "IOR", 1.5)
    return mat


def fabric(name, color=(0.3, 0.32, 0.35)):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*color, 1))
    _set(bsdf, "Roughness", 0.9)
    _set(bsdf, "Sheen Weight", 0.6)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 600.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def rubber(name, color=(0.02, 0.02, 0.02)):
    return plastic(name, color, 0.8)


def stone(name, color=(0.5, 0.5, 0.48)):
    mat, nt, bsdf = _principled(name)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 12.0
    noise.inputs["Detail"].default_value = 10.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    c = Vector(color)
    ramp.color_ramp.elements[0].color = (*(c * 0.7), 1)
    ramp.color_ramp.elements[1].color = (*(c * 1.15), 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    _set(bsdf, "Roughness", 0.7)
    return mat


def emission(name, color=(1, 0.9, 0.7), strength=8.0):
    mat, nt, bsdf = _principled(name)
    _set(bsdf, "Base Color", (*color, 1))
    _set(bsdf, "Emission Color", (*color, 1))
    _set(bsdf, "Emission Strength", strength)
    return mat


def assign(obj, mat):
    if obj.data is not None and hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    for child in obj.children:
        assign(child, mat)
    return obj


# ── placement ────────────────────────────────────────────────────────────────

def _bounds(obj):
    bpy.context.view_layer.update()
    objs = [obj] + [c for c in obj.children_recursive if c.type in ("MESH", "CURVE")] if obj.type == "EMPTY" else [obj]
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type in ("MESH", "CURVE", "FONT") for c in o.bound_box]
    if not pts:
        return obj.location.copy(), obj.location.copy()
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def bottom(obj):
    return _bounds(obj)[0].z


def top(obj):
    return _bounds(obj)[1].z


def size(obj):
    lo, hi = _bounds(obj)
    return hi - lo


def on_floor(obj):
    obj.location.z -= bottom(obj)
    bpy.context.view_layer.update()
    return obj


def place_on(obj, base, x=None, y=None):
    if x is not None:
        obj.location.x = x
    if y is not None:
        obj.location.y = y
    obj.location.z += top(base) - bottom(obj)
    bpy.context.view_layer.update()
    return obj


def touch(obj, other, axis="z"):
    i = "xyz".index(axis)
    lo, hi = _bounds(obj)
    olo, ohi = _bounds(other)
    if lo[i] >= ohi[i]:
        obj.location[i] -= lo[i] - ohi[i]
    elif hi[i] <= olo[i]:
        obj.location[i] += olo[i] - hi[i]
    bpy.context.view_layer.update()
    return obj


def smooth(obj, angle=35):
    if obj.type != "MESH":
        return obj
    for p in obj.data.polygons:
        p.use_smooth = True
    try:
        obj.data.set_sharp_from_angle(angle=math.radians(angle))     # 4.1+
    except Exception:
        try:
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = math.radians(angle)
        except Exception:
            pass
    return obj


def join(objs, name):
    objs = [o for o in objs if o.type == "MESH"]
    if not objs:
        return None
    ctx = bpy.context
    for o in ctx.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    ctx.view_layer.objects.active = objs[0]
    with ctx.temp_override(active_object=objs[0], selected_editable_objects=objs, selected_objects=objs):
        bpy.ops.object.join()
    objs[0].name = name
    return objs[0]


def group(name, objs):
    root = _link(bpy.data.objects.new(name, None))
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    return root


# ── studio ───────────────────────────────────────────────────────────────────

def _meshes():
    return [o for o in bpy.context.scene.objects if o.type in ("MESH", "CURVE", "FONT") and not o.get("jarvis_floor")]


def frame_camera(objs=None, yaw=-35.0, pitch=18.0, lens=60.0, margin=1.08):
    scene = bpy.context.scene
    objs = objs or _meshes()
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return None
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    cam = scene.camera
    if cam is None:
        cam = _link(bpy.data.objects.new("Kamera", bpy.data.cameras.new("Kamera")))
        scene.camera = cam
    cam.data.lens = lens
    cam.data.sensor_fit = "HORIZONTAL"
    aspect = scene.render.resolution_x / max(scene.render.resolution_y, 1)
    tx = math.tan(cam.data.angle_x / 2)
    ty = tx / aspect
    y, p = math.radians(yaw), math.radians(pitch)
    v = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
    fwd = -v
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd)
    aim = (lo + hi) / 2
    corners = [Vector((a, b, c)) for a in (lo.x, hi.x) for b in (lo.y, hi.y) for c in (lo.z, hi.z)]
    xs = [(c - aim).dot(right) for c in corners]
    ys = [(c - aim).dot(up) for c in corners]
    aim = aim + right * (max(xs) + min(xs)) / 2 + up * (max(ys) + min(ys)) / 2
    dist = max(max((c - aim).dot(v) + abs((c - aim).dot(right)) / tx, (c - aim).dot(v) + abs((c - aim).dot(up)) / ty)
               for c in corners) * margin
    cam.location = aim + v * dist
    cam.rotation_euler = (aim - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start, cam.data.clip_end = dist * 0.005, dist * 100
    return cam


def studio(target=None, floor=True, samples=128):
    scene = bpy.context.scene
    objs = [target] if target is not None else _meshes()
    lo = Vector((min(bottom(o) for o in objs), 0, 0)) if objs else Vector((0, 0, 0))
    s = max((size(o).length for o in objs), default=1.0)
    if floor:
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=s * 20)
        fl = _mesh_obj("Zemin", bm)
        fl["jarvis_floor"] = True
        fl.location.z = min(lo.z, 0.0)
        fl.data.materials.append(plastic("Zemin", (0.16, 0.155, 0.15), 0.55))
    for name, loc, power, sz in (("Ana ışık", (-1.6, -1.4, 1.9), 110, 1.4), ("Dolgu", (1.9, -1.0, 0.9), 30, 2.0),
                                  ("Kontur", (0.5, 2.0, 1.7), 80, 1.0)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = power * s * s
        light.size = s * sz
        ob = _link(bpy.data.objects.new(name, light))
        ob.location = Vector(loc) * s
        ob.rotation_euler = (Vector((0, 0, s * 0.3)) - ob.location).to_track_quat("-Z", "Y").to_euler()
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.05, 0.05, 0.055, 1)
        bg.inputs["Strength"].default_value = 0.6
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    import _cycles
    scene.cycles.use_denoising = getattr(_cycles, "with_openimagedenoise", True)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    frame_camera(objs)
    return scene.camera
