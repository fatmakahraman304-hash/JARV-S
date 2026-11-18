"""core/glb.py — read a binary glTF (.glb) into flat numpy arrays.

What the image-to-3D services return (TRELLIS, Hunyuan3D, TripoSG, Stable
Fast 3D) is a .glb: one or more meshes with a base-colour texture and a
metal/roughness material. This reads exactly that — node transforms,
positions, normals, UVs, vertex colours, indices, the base-colour texture and
the metal/roughness factors — with numpy and Pillow only. Draco-compressed
files are refused with a clear message.
"""
from __future__ import annotations

import base64
import io
import json
import struct

import numpy as np

_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NUM = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
MAX_TEX = 2048


class GlbError(ValueError):
    pass


def _chunks(data: bytes):
    if len(data) < 20 or data[:4] != b"glTF":
        raise GlbError("glb dosyası değil")
    _magic, _version, length = struct.unpack_from("<III", data, 0)
    off, js, binary = 12, None, b""
    while off + 8 <= min(length, len(data)):
        clen, ctype = struct.unpack_from("<II", data, off)
        body = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(body.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = body
        off += 8 + clen
    if js is None:
        raise GlbError("glb içinde JSON yok")
    return js, binary


def _accessor(js, binary, idx):
    acc = js["accessors"][idx]
    n, comps = acc["count"], _NUM[acc["type"]]
    dt = np.dtype(_COMP[acc["componentType"]])
    if "bufferView" not in acc:
        out = np.zeros((n, comps), dt)
    else:
        bv = js["bufferViews"][acc["bufferView"]]
        start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = bv.get("byteStride") or dt.itemsize * comps
        if stride == dt.itemsize * comps:
            out = np.frombuffer(binary, dt, count=n * comps, offset=start).reshape(n, comps)
        else:                                             # interleaved: take each vertex's slice
            item = dt.itemsize * comps
            raw = np.frombuffer(binary, np.uint8, count=stride * (n - 1) + item, offset=start)
            out = np.lib.stride_tricks.as_strided(raw, shape=(n, item), strides=(stride, 1)).copy().view(dt).reshape(n, comps)
    if acc.get("normalized") and dt.kind in "iu":
        out = out.astype(np.float32) / float(np.iinfo(dt).max)
    return np.array(out)


def _node_matrix(node) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], np.float64).reshape(4, 4).T
    m = np.eye(4)
    t = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = node.get("scale", [1, 1, 1])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m[:3, :3] = r * np.asarray(s)
    m[:3, 3] = t
    return m


def _image(js, binary, tex_idx):
    try:
        from PIL import Image
        tex = js["textures"][tex_idx]
        src = tex.get("source")
        if src is None:
            for ext in (tex.get("extensions") or {}).values():
                src = ext.get("source", src)
        img = js["images"][src]
        if "bufferView" in img:
            bv = js["bufferViews"][img["bufferView"]]
            raw = binary[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        elif str(img.get("uri", "")).startswith("data:"):
            raw = base64.b64decode(img["uri"].split(",", 1)[1])
        else:
            return None
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        if max(im.size) > MAX_TEX:
            im.thumbnail((MAX_TEX, MAX_TEX))
        return np.asarray(im)
    except Exception as exc:
        print(f"[glb] texture skipped: {exc}")
        return None


def load(data: bytes) -> list[dict]:
    """Primitives of the default scene in world space:
    [{V, N|None, UV|None, C|None, F, color(4), metal, rough, emissive(3), texture|None, name}]."""
    js, binary = _chunks(data)
    if "KHR_draco_mesh_compression" in (js.get("extensionsRequired") or []) + (js.get("extensionsUsed") or []):
        raise GlbError("Draco sıkıştırmalı glb desteklenmiyor")
    out: list[dict] = []
    tex_cache: dict = {}

    def mesh_prims(mi, M):
        mesh = js["meshes"][mi]
        nmat = np.linalg.inv(M[:3, :3]).T
        for k, prim in enumerate(mesh.get("primitives", [])):
            if prim.get("mode", 4) != 4:
                continue                                   # points / lines: not a surface
            at = prim["attributes"]
            if "POSITION" not in at:
                continue
            V = _accessor(js, binary, at["POSITION"]).astype(np.float64)
            V = V @ M[:3, :3].T + M[:3, 3]
            N = None
            if "NORMAL" in at:
                N = _accessor(js, binary, at["NORMAL"]).astype(np.float64) @ nmat.T
                N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
            UV = _accessor(js, binary, at["TEXCOORD_0"]).astype(np.float32) if "TEXCOORD_0" in at else None
            C = _accessor(js, binary, at["COLOR_0"]).astype(np.float32) if "COLOR_0" in at else None
            if C is not None and C.max() > 1.0:
                C = C / 255.0
            F = (_accessor(js, binary, prim["indices"]).reshape(-1).astype(np.int64) if "indices" in prim
                 else np.arange(len(V)))
            F = F[: len(F) // 3 * 3].reshape(-1, 3)
            if np.linalg.det(M[:3, :3]) < 0:
                F = F[:, ::-1]
            mat = js.get("materials", [{}])[prim["material"]] if "material" in prim and js.get("materials") else {}
            pbr = mat.get("pbrMetallicRoughness", {})
            sg = (mat.get("extensions") or {}).get("KHR_materials_pbrSpecularGlossiness", {})
            color = pbr.get("baseColorFactor") or sg.get("diffuseFactor") or [1, 1, 1, 1]
            tinfo = pbr.get("baseColorTexture") or sg.get("diffuseTexture")
            tex = None
            if tinfo is not None and "index" in tinfo:
                ti = tinfo["index"]
                if ti not in tex_cache:
                    tex_cache[ti] = _image(js, binary, ti)
                tex = tex_cache[ti]
            out.append({"V": V.astype(np.float32), "N": None if N is None else N.astype(np.float32), "UV": UV, "C": C, "F": F,
                        "color": [float(c) for c in color], "metal": float(pbr.get("metallicFactor", 0.0 if sg else 1.0)),
                        "rough": float(pbr.get("roughnessFactor", 1.0 - float(sg.get("glossinessFactor", 0.0)) if sg else 1.0)),
                        "emissive": [float(c) for c in mat.get("emissiveFactor", [0, 0, 0])],
                        "alpha": mat.get("alphaMode", "OPAQUE"), "texture": tex,
                        "name": mesh.get("name") or mat.get("name") or f"parça {len(out) + 1}"})

    def walk(ni, parent):
        node = js["nodes"][ni]
        M = parent @ _node_matrix(node)
        if "mesh" in node:
            mesh_prims(node["mesh"], M)
        for c in node.get("children", []):
            walk(c, M)

    scenes = js.get("scenes") or []
    if scenes:
        for ni in scenes[js.get("scene", 0)].get("nodes", []):
            walk(ni, np.eye(4))
    else:
        for mi in range(len(js.get("meshes", []))):
            mesh_prims(mi, np.eye(4))
    if not out:
        raise GlbError("glb içinde çizilecek yüzey yok")
    return out


def write(prims: list[dict]) -> bytes:
    """A minimal glb (positions, normals, colours) — for tests and exports."""
    bins, views, accs, meshes = bytearray(), [], [], []

    def add(arr, comp, typ, target=None):
        arr = np.ascontiguousarray(arr)
        while len(bins) % 4:
            bins.append(0)
        off = len(bins)
        bins.extend(arr.tobytes())
        views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes, **({"target": target} if target else {})})
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": typ}
        if typ == "VEC3" and comp == 5126:
            a["min"], a["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accs.append(a)
        return len(accs) - 1

    materials = []
    for p in prims:
        attrs = {"POSITION": add(p["V"].astype(np.float32), 5126, "VEC3", 34962)}
        if p.get("N") is not None:
            attrs["NORMAL"] = add(p["N"].astype(np.float32), 5126, "VEC3", 34962)
        idx = add(p["F"].astype(np.uint32).reshape(-1), 5125, "SCALAR", 34963)
        materials.append({"pbrMetallicRoughness": {"baseColorFactor": list(p.get("color", [1, 1, 1, 1])),
                                                    "metallicFactor": p.get("metal", 0.0), "roughnessFactor": p.get("rough", 0.5)}})
        meshes.append({"name": p.get("name", ""), "primitives": [{"attributes": attrs, "indices": idx, "material": len(materials) - 1}]})
    js = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(bins)}], "bufferViews": views, "accessors": accs,
          "materials": materials, "meshes": meshes, "nodes": [{"mesh": i} for i in range(len(meshes))],
          "scenes": [{"nodes": list(range(len(meshes)))}], "scene": 0}
    jb = json.dumps(js).encode()
    jb += b" " * (-len(jb) % 4)
    bb = bytes(bins) + b"\0" * (-len(bins) % 4)
    total = 12 + 8 + len(jb) + 8 + len(bb)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(jb), 0x4E4F534A) + jb
            + struct.pack("<II", len(bb), 0x004E4942) + bb)
