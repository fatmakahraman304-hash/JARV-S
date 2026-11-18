"""Editable architectural meshes and landscapes. Runs inside Blender."""
import math
import random

import bpy
from mathutils import Vector


def number(value, low, high):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{value} geçersiz, {low}–{high} aralığı gerekli")
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{low}–{high} aralığında tam sayı gerekli")
    return value


def mesh_object(name, verts, faces, collection):
    if bpy.data.objects.get(name):
        raise ValueError(f"Ad zaten var: {name}")
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


class Boxes:
    """Combine rectangular solids into one editable mesh per real-world object."""
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.materials = []
        self.indices = []

    def add(self, center, size, material=None):
        x, y, z = center
        a, b, c = (v / 2 for v in size)
        offset = len(self.vertices)
        self.vertices.extend((x + dx, y + dy, z + dz) for dz in (-c, c)
                             for dx, dy in ((-a, -b), (a, -b), (a, b), (-a, b)))
        for face in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
                     (2, 3, 7, 6), (3, 0, 4, 7)):
            self.faces.append(tuple(offset + i for i in face))
        if material is not None:
            if material not in self.materials:
                self.materials.append(material)
            self.indices.extend([self.materials.index(material)] * 6)

    def finish(self, name, collection):
        obj = mesh_object(name, self.vertices, self.faces, collection)
        for mat in self.materials:
            obj.data.materials.append(mat)
        for face, index in zip(obj.data.polygons, self.indices):
            face.material_index = index
        return obj


def wall(step):
    start, end = Vector(step["start"]), Vector(step["end"])
    if len(start) != 2 or len(end) != 2:
        raise ValueError("Duvar için iki XY noktası gerekli")
    delta = end - start
    length = number(delta.length, 0.01, 5000)
    height = number(step.get("height", 3), 0.05, 500)
    thick = number(step.get("thickness", 0.2), 0.01, 10)
    boxes = Boxes()

    def panel(left, right, bottom, top):
        if right > left and top > bottom:
            boxes.add(((left + right) / 2, 0, (bottom + top) / 2),
                      (right - left, thick, top - bottom))

    cursor = 0
    for hole in sorted(step.get("openings", []), key=lambda h: h["offset"]):
        left = number(hole["offset"], cursor, length)
        right = left + number(hole["width"], 0.01, length - left)
        sill = number(hole.get("sill", 0), 0, height)
        head = sill + number(hole["height"], 0.01, height - sill)
        panel(cursor, left, 0, height)
        panel(left, right, 0, sill)
        panel(left, right, head, height)
        cursor = right
    panel(cursor, length, 0, height)
    if not boxes.vertices:
        raise ValueError("Açıklık duvarın tamamını kaplıyor")
    obj = boxes.finish(step["name"], bpy.context.collection)
    obj.location = (*start, step.get("base_z", 0))
    obj.rotation_euler.z = math.atan2(delta.y, delta.x)


def landscape(step):
    n = integer(step.get("resolution", 40), 2, 200)
    size = number(step.get("size", 100), 0.1, 10000)
    amplitude = number(step.get("height", 10), 0, 2000)
    rng = random.Random(step.get("seed", 0))
    waves = [(rng.uniform(-1, 1) * f, rng.uniform(-1, 1) * f,
              rng.uniform(0, math.tau), 0.5 ** i)
             for i, f in enumerate((4, 8, 16, 32, 64))]
    verts = []
    for row in range(n + 1):
        for col in range(n + 1):
            x, y = col / n - 0.5, row / n - 0.5
            z = sum(w * math.sin(x * a + y * b + p) for a, b, p, w in waves)
            verts.append((x * size, y * size, amplitude * z / 1.9375))
    faces = []
    for j in range(n):
        for i in range(n):
            k = j * (n + 1) + i
            faces.append((k, k + 1, k + n + 2, k + n + 1))
    obj = mesh_object(step["name"], verts, faces, bpy.context.collection)
    obj.location = step.get("location", (0, 0, 0))
    for poly in obj.data.polygons:
        poly.use_smooth = True


def district(step):
    name = step["name"]
    if bpy.data.collections.get(name):
        raise ValueError(f"Koleksiyon zaten var: {name}")
    rows = integer(step.get("rows", 3), 1, 12)
    cols = integer(step.get("columns", 4), 1, 12)
    levels = integer(step.get("max_floors", 4), 1, 24)
    park_cells = set()
    for row, col in step.get("parks", []):
        park_cells.add((integer(row, 1, rows), integer(col, 1, cols)))
    rng = random.Random(step.get("seed", 0))
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    origin = Vector(step.get("location", (0, 0, 0)))
    palette = {}
    for key, rgb in {"road": (.08, .09, .11), "paving": (.55, .51, .44),
                     "stripe": (.91, .85, .66), "wall": (.89, .72, .51), "brick": (.65, .31, .22),
                     "glass": (.11, .29, .37), "roof": (.32, .27, .24),
                     "grass": (.22, .46, .15), "tree": (.08, .30, .12)}.items():
        mat = bpy.data.materials.new(f"{name} {key}")
        mat.diffuse_color = (*rgb, 1)
        palette[key] = mat

    def place(parts, label, x, y):
        obj = parts.finish(f"{name} {label}", collection)
        obj.location = origin + Vector((x, y, 0))

    pitch = 20
    roads = Boxes()
    roads.add((0, 0, -.12), (cols * pitch + 5, rows * pitch + 5, .24), palette["road"])
    for row in range(rows + 1):
        y = (row - rows / 2) * pitch
        for col in range(cols):
            x = (col - (cols - 1) / 2) * pitch
            for offset in (-4, 0, 4):
                roads.add((x + offset, y, .012), (1.7, .12, .024), palette["stripe"])
    for col in range(cols + 1):
        x = (col - cols / 2) * pitch
        for row in range(rows):
            y = (row - (rows - 1) / 2) * pitch
            for offset in (-4, 0, 4):
                roads.add((x, y + offset, .012), (.12, 1.7, .024), palette["stripe"])
    place(roads, "Yollar", 0, 0)
    for r in range(rows):
        for c in range(cols):
            x, y = (c - (cols - 1) / 2) * pitch, (r - (rows - 1) / 2) * pitch
            parts = Boxes()
            park = (r + 1, c + 1) in park_cells
            parts.add((0, 0, .1), (15, 15, .2), palette["grass" if park else "paving"])
            if park:
                for dx, dy in ((-4, -4), (4, -4), (0, 4)):
                    parts.add((dx, dy, 1.3), (.55, .55, 2.2), palette["roof"])
                    parts.add((dx, dy, 3.1), (2.6, 2.6, 2.5), palette["tree"])
            else:
                floors = rng.randint(1, levels)
                height = floors * 3
                parts.add((0, 0, .2 + height / 2), (10, 9, height),
                          palette[rng.choice(("wall", "brick"))])
                parts.add((0, 0, .35 + height), (10.5, 9.5, .3), palette["roof"])
                parts.add((0, -4.57, 1.35), (1.4, .12, 2.3), palette["roof"])
                parts.add((0, -4.95, 2.68), (2.3, 1.1, .15), palette["wall"])
                for floor in range(floors):
                    for dx in (-3, 0, 3):
                        for dy in (-4.52, 4.52):
                            if floor == 0 and dx == 0 and dy < 0:
                                continue
                            parts.add((dx, dy, 1.9 + floor * 3), (1.5, .08, 1.3), palette["glass"])
            label = "Park" if park else "Bina"
            place(parts, f"{label} {r + 1}-{c + 1}", x, y)


def lathe(step):
    profile = step["profile"]
    if not 2 <= len(profile) <= 256:
        raise ValueError("En az iki, en fazla 256 profil noktası gerekli")
    rings = integer(step.get("segments", 48), 3, 256)
    verts, faces, previous = [], [], []
    for radius, z in profile:
        radius = number(radius, 0, 10000)
        z = number(z, -10000, 10000)
        ring = []
        for j in range(rings if radius else 1):
            angle = math.tau * j / rings
            ring.append(len(verts))
            verts.append((radius * math.cos(angle), radius * math.sin(angle), z))
        if len(previous) == len(ring) == 1:
            raise ValueError("Ardışık iki profil noktası eksen üzerinde")
        if previous:
            for j in range(rings):
                k = (j + 1) % rings
                quad = [previous[j % len(previous)], previous[k % len(previous)],
                        ring[k % len(ring)], ring[j % len(ring)]]
                faces.append(tuple(dict.fromkeys(quad)))
        previous = ring
    obj = mesh_object(step["name"], verts, faces, bpy.context.collection)
    obj.location = step.get("location", (0, 0, 0))
    for poly in obj.data.polygons:
        poly.use_smooth = True


def cable(step):
    name = step["name"]
    if bpy.data.objects.get(name):
        raise ValueError(f"Ad zaten var: {name}")
    points = step["points"]
    if not 2 <= len(points) <= 1024:
        raise ValueError("Eğri için 2–1024 nokta gerekli")
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = number(step.get("radius", .1), .001, 100)
    curve.bevel_resolution = 3
    curve.use_fill_caps = True
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for control, point in zip(spline.bezier_points, points):
        control.co = point
        control.handle_left_type = control.handle_right_type = "AUTO"
    spline.use_cyclic_u = bool(step.get("closed", False))
    bpy.context.collection.objects.link(bpy.data.objects.new(name, curve))
