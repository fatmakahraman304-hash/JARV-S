"""Executed by Blender's Python in a separate background session."""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def transform(obj, step):
    for key in ("location", "scale", "rotation"):
        if key in step:
            values = tuple(float(v) for v in step[key])
            if len(values) != 3 or not all(math.isfinite(v) for v in values):
                raise ValueError(key)
            if key == "rotation":
                obj.rotation_euler = tuple(map(math.radians, values))
            else:
                setattr(obj, key, values)


def create(step):
    kind = step["kind"]
    ops = bpy.ops
    shapes = {"cube": ops.mesh.primitive_cube_add, "sphere": ops.mesh.primitive_uv_sphere_add,
              "cylinder": ops.mesh.primitive_cylinder_add, "cone": ops.mesh.primitive_cone_add,
              "plane": ops.mesh.primitive_plane_add, "torus": ops.mesh.primitive_torus_add,
              "ico_sphere": ops.mesh.primitive_ico_sphere_add, "monkey": ops.mesh.primitive_monkey_add}
    if kind in shapes:
        shapes[kind]()
    elif kind == "text":
        ops.object.text_add()
        bpy.context.object.data.body = step["body"]
    elif kind == "camera":
        ops.object.camera_add()
        bpy.context.scene.camera = bpy.context.object
        bpy.context.object.data.lens = step.get("lens", 50)
    elif kind == "light":
        ops.object.light_add(type=step.get("type", "AREA"))
        bpy.context.object.data.energy = step.get("energy", 1000)
    elif kind == "armature":
        data = bpy.data.armatures.new(step["name"])
        obj = bpy.data.objects.new(step["name"], data)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        ops.object.mode_set(mode="EDIT")
        try:
            for item in step["bones"]:
                if item["name"] in data.edit_bones:
                    raise ValueError(item["name"])
                bone = data.edit_bones.new(item["name"])
                bone.head, bone.tail = item["head"], item["tail"]
                if (bone.tail - bone.head).length < 0.00001:
                    raise ValueError("Kemik uzunluğu sıfır")
                if item.get("parent"):
                    bone.parent = data.edit_bones[item["parent"]]
        finally:
            ops.object.mode_set(mode="OBJECT")
        return obj
    elif kind == "mesh":
        vertices, faces = step["vertices"], step["faces"]
        if not vertices or any(len(f) < 3 or any(type(i) is not int or not 0 <= i < len(vertices)
                                                 for i in f) for f in faces):
            raise ValueError("Geçersiz mesh yüzeyi")
        mesh = bpy.data.meshes.new(step["name"])
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(step["name"], mesh)
        bpy.context.collection.objects.link(obj)
        return obj
    else:
        raise ValueError(f"Desteklenmeyen nesne: {kind}")
    return bpy.context.object


EDIT_OPS = {
    "subdivide": bpy.ops.mesh.subdivide, "bevel": bpy.ops.mesh.bevel,
    "inset": bpy.ops.mesh.inset, "poke": bpy.ops.mesh.poke,
    "triangulate": bpy.ops.mesh.quads_convert_to_tris,
    "recalculate_normals": bpy.ops.mesh.normals_make_consistent,
    "remove_doubles": bpy.ops.mesh.remove_doubles, "unwrap": bpy.ops.uv.unwrap,
    "smart_project": bpy.ops.uv.smart_project,
}


def edit_mesh(obj, step):
    if obj.type != "MESH":
        raise ValueError("Mesh nesnesi gerekli")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        bpy.ops.mesh.select_all(action="SELECT")
        operator = EDIT_OPS[step["tool"]]
        if not operator.poll() or "FINISHED" not in operator(**step.get("settings", {})):
            raise ValueError(step["tool"])
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def reference(query):
    words = query.lower().replace("_", " ").replace(".", " ").split()
    hits = []
    for group in dir(bpy.ops):
        for tool in dir(getattr(bpy.ops, group)):
            op = getattr(getattr(bpy.ops, group), tool)
            label = f"{group}.{tool}"
            if not words or not all(w in label.replace("_", " ") for w in words):
                continue
            rna = op.get_rna_type()
            hits.append((label, rna.description, list(rna.properties.keys())[1:]))
            if len(hits) == 24:
                return hits
    return hits


def node_graph(obj, step):
    if step["op"] == "geometry_nodes":
        tree = bpy.data.node_groups.new(step.get("title", obj.name), "GeometryNodeTree")
        for direction in ("INPUT", "OUTPUT"):
            tree.interface.new_socket(name="Geometry", in_out=direction, socket_type="NodeSocketGeometry")
        mod = obj.modifiers.new(tree.name, "NODES")
        mod.node_group = tree
    else:
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        mat = bpy.data.materials.new(step.get("title", obj.name))
        mat.use_nodes = True
        tree = mat.node_tree
        tree.nodes.clear()
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    nodes = {}
    for definition in step["nodes"]:
        key = definition["id"]
        if key in nodes:
            raise ValueError(f"Yinelenen düğüm: {key}")
        node = tree.nodes.new(definition["type"])
        node.label = key
        node.location = definition.get("xy", (180 * len(nodes), 0))
        nodes[key] = node
        for prop, value in definition.get("settings", {}).items():
            if prop not in ("operation", "blend_type", "data_type", "domain", "noise_dimensions"):
                raise ValueError(prop)
            setattr(node, prop, value)
        for socket, value in definition.get("inputs", {}).items():
            index = int(socket) if socket.isdigit() else socket
            node.inputs[index].default_value = value
    for source, output, dest, inp in step["links"]:
        link = tree.links.new(nodes[source].outputs[output], nodes[dest].inputs[inp])
        if not link.is_valid:
            raise ValueError(f"Geçersiz düğüm bağlantısı: {source} > {dest}")
    output_type = "NodeGroupOutput" if step["op"] == "geometry_nodes" else "ShaderNodeOutputMaterial"
    if not any(n.bl_idname == output_type and any(s.is_linked for s in n.inputs) for n in nodes.values()):
        raise ValueError("Düğüm ağı bağlı bir çıkış gerektiriyor")


def apply(step):
    op, scene = step["op"], bpy.context.scene
    if op in ("district", "wall", "landscape", "lathe", "cable", "loft"):
        from _blender_world import cable, district, landscape, lathe, loft, wall
        builders = {"district": district, "wall": wall, "landscape": landscape,
                    "lathe": lathe, "cable": cable, "loft": loft}
        builders[op](step)
        return
    if op == "render_settings":
        for key in ("resolution_x", "resolution_y"):
            if key in step:
                value = int(step[key])
                if not 4 <= value <= 8192:
                    raise ValueError(key)
                setattr(scene.render, key, value)
        scene.render.resolution_percentage = 100
        if "engine" in step:
            scene.render.engine = step["engine"]
        if "transparent" in step:
            scene.render.film_transparent = bool(step["transparent"])
        return
    if op == "timeline":
        scene.frame_start, scene.frame_end = step["start"], step["end"]
        scene.render.fps = step.get("fps", scene.render.fps)
        scene.frame_set(scene.frame_start)
        return
    name = step["name"]
    if op in ("create", "duplicate"):
        if bpy.data.objects.get(name):
            raise ValueError(f"Ad zaten var: {name}")
        if op == "create":
            obj = create(step)
        else:
            obj = scene.objects[step["source"]].copy()
            bpy.context.collection.objects.link(obj)
        obj.name = name
        transform(obj, step)
        return
    obj = scene.objects[name]
    if op == "transform":
        transform(obj, step)
    elif op == "aim":
        direction = Vector(step["target"]) - obj.matrix_world.translation
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    elif op == "material":
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        mat = bpy.data.materials.new(step.get("material", name))
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        color = tuple(step["rgb"]) + (1.0,)
        mat.diffuse_color = color
        for key, value in [("Base Color", color), ("Metallic", step.get("metallic", 0)),
                           ("Roughness", step.get("roughness", 0.5))]:
            bsdf.inputs[key].default_value = value
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    elif op == "modifier":
        allowed = {"BEVEL": ("width", "segments"), "SUBSURF": ("levels", "render_levels"),
                   "SOLIDIFY": ("thickness",), "ARRAY": ("count", "relative_offset_displace"),
                   "MIRROR": ("use_axis",), "BOOLEAN": ("operation", "object")}
        kind = step["type"]
        fields = allowed[kind]
        mod = obj.modifiers.new(kind, kind)
        for field, value in step.get("settings", {}).items():
            if field not in fields:
                raise ValueError(field)
            setattr(mod, field, scene.objects[value] if field == "object" else value)
    elif op in ("geometry_nodes", "shader_nodes"):
        node_graph(obj, step)
    elif op == "physics":
        if obj.type != "MESH":
            raise ValueError("Fizik için mesh seçilmeli")
        kind = step["type"]
        if kind in ("ACTIVE", "PASSIVE"):
            bpy.ops.object.select_all(action="DESELECT")
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            if obj.rigid_body is None:
                bpy.ops.rigidbody.object_add()
            obj.rigid_body.type = kind
            obj.rigid_body.mass = step.get("mass", 1)
        elif kind == "CLOTH":
            mod = obj.modifiers.new("Kumaş", "CLOTH")
            mod.settings.mass = step.get("mass", 0.3)
        elif kind == "COLLISION":
            obj.modifiers.new("Çarpışma", "COLLISION")
        else:
            raise ValueError(kind)
    elif op == "mesh_edit":
        edit_mesh(obj, step)
    elif op == "parent":
        obj.parent = scene.objects[step["parent"]]
    elif op == "skin":
        rig = scene.objects[step["rig"]]
        if obj.type != "MESH" or rig.type != "ARMATURE":
            raise ValueError("Mesh ve armature gerekli")
        mod = obj.modifiers.new("Rig", "ARMATURE")
        mod.object = rig
        for bone, indices in step["groups"].items():
            if bone not in rig.data.bones:
                raise ValueError(bone)
            group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
            if any(type(i) is not int or not 0 <= i < len(obj.data.vertices) for i in indices):
                raise ValueError("Geçersiz vertex numarası")
            group.add(indices, 1.0, "REPLACE")
    elif op == "pose":
        bone = obj.pose.bones[step["bone"]]
        bone.rotation_mode = "XYZ"
        transform(bone, step)
        if "frame" in step:
            for field in ("location", "scale", "rotation"):
                if field in step:
                    bone.keyframe_insert(data_path="rotation_euler" if field == "rotation" else field,
                                         frame=step["frame"])
    elif op == "keyframe":
        transform(obj, step)
        for field in ("location", "scale", "rotation"):
            if field in step:
                obj.keyframe_insert(data_path="rotation_euler" if field == "rotation" else field,
                                    frame=step["frame"])
    else:
        raise ValueError(f"Desteklenmeyen işlem: {op}")


def main():
    job = Path(sys.argv[sys.argv.index("--") + 1])
    request = json.loads((job / "request.json").read_text(encoding="utf8"))
    scene = bpy.context.scene
    if request["mode"] == "build":
        if request["empty"]:
            for obj in list(scene.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
        for index, step in enumerate(request["steps"], 1):
            try:
                apply(step)
                bpy.context.view_layer.update()
            except Exception as exc:
                raise ValueError(f"Adım {index}: {exc}") from exc
        scene.frame_set(scene.frame_start)
        bpy.ops.wm.save_as_mainfile(filepath=str(job / "scene.blend"))
    elif request["mode"] == "glb":
        bpy.ops.export_scene.gltf(filepath=str(job / "scene.glb"), export_format="GLB")
    elif request["mode"] in ("render", "animation"):
        if scene.camera is None:
            raise ValueError("Sahnede etkin kamera yok")
        scene.render.image_settings.file_format = "PNG"
        if request["mode"] == "animation":
            scene.render.filepath = str(job / "frames" / "frame_")
            scene.render.use_file_extension = True
            bpy.ops.render.render(animation=True)
            for frame in range(scene.frame_start, scene.frame_end + 1, scene.frame_step):
                path = Path(scene.render.frame_path(frame=frame))
                if not path.is_file() or not path.stat().st_size:
                    raise ValueError(f"Eksik animasyon karesi: {frame}")
        else:
            scene.render.filepath = str(job / "render.png")
            bpy.ops.render.render(write_still=True)
    report = {"version": bpy.app.version_string, "count": len(scene.objects),
              "objects": [[o.name, o.type] for o in list(scene.objects)[:250]],
              "camera": scene.camera.name if scene.camera else None,
              "frames": [scene.frame_start, scene.frame_end]}
    if request["mode"] == "inspect":
        report["details"] = [
            {"name": o.name, "location": list(o.location), "dimensions": list(o.dimensions),
             "rotation_deg": list(map(math.degrees, o.rotation_euler)),
             "parent": o.parent.name if o.parent else None,
             "materials": [slot.name for slot in o.material_slots],
             "modifiers": [m.type for m in o.modifiers],
             "bones": list(o.data.bones.keys())[:80] if o.type == "ARMATURE" else []}
            for o in list(scene.objects)[:100]]
    if request["mode"] == "reference":
        report["operators"] = reference(request["query"])
    (job / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf8")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
