"""MAYK live link — runs INSIDE the user's open Blender.

MAYK copies this file into Blender's scripts/startup folder, so every Blender
the user opens listens on 127.0.0.1 for MAYK (with a token only MAYK knows).
MAYK can then read what the user has selected and change the open scene in
place: "şunu kırmızı yap" means the selected object, the result appears in the
window at once, and Ctrl+Z (or "geri al") undoes it like any other edit.

Everything runs on Blender's main thread from a timer; one request at a time.
Requests and replies are one JSON object per connection:
    {"token": ..., "op": "state"}                 -> scene, selection, file
    {"token": ..., "op": "exec", "code": "..."}   -> runs code with MAYK's toolkit; error = traceback
    {"token": ..., "op": "undo"} / {"op": "redo"}
    {"token": ..., "op": "issues"}                -> floating / disconnected parts
"""
from __future__ import annotations

import json
import socket
import traceback
from pathlib import Path

import bpy

# filled in by MAYK when it installs the file
JARVIS_DIR = r"__JARVIS_DIR__"
PORT = 47863

_server = None


def _token():
    try:
        return (Path(JARVIS_DIR) / "memory" / "blender_live.token").read_text(encoding="utf8").strip()
    except OSError:
        return ""


def _kit_env():
    env = {"__name__": "jarvis_kit", "bpy": bpy}
    for name in ("_blender_kit.py", "_blender_arch.py"):
        f = Path(JARVIS_DIR) / "plugins" / name
        if f.is_file():
            exec(compile(f.read_text(encoding="utf8"), str(f), "exec"), env)
    env["__name__"] = "__main__"
    return env


def _state():
    ctx = bpy.context
    scene = ctx.scene
    sel = [o.name for o in ctx.view_layer.objects if o.select_get()] if ctx.view_layer else []
    active = ctx.view_layer.objects.active.name if ctx.view_layer and ctx.view_layer.objects.active else None
    objs = []
    for o in list(scene.objects)[:300]:
        objs.append({"name": o.name, "type": o.type, "location": [round(v, 3) for v in o.location],
                     "dimensions": [round(v, 3) for v in o.dimensions], "parent": o.parent.name if o.parent else None,
                     "materials": [s.name for s in o.material_slots][:4]})
    return {"version": bpy.app.version_string, "file": bpy.data.filepath, "selected": sel, "active": active,
            "count": len(scene.objects), "objects": objs, "camera": scene.camera.name if scene.camera else None,
            "frame": scene.frame_current}


def _snapshot():
    """What every object looks like now — to tell afterwards exactly what MAYK changed."""
    snap = {}
    for o in bpy.context.scene.objects:
        mw = o.matrix_world
        snap[o.name] = (tuple(round(v, 4) for row in mw for v in row), tuple(round(v, 4) for v in o.dimensions),
                        tuple(s.material.name if s.material else "" for s in o.material_slots),
                        len(o.data.vertices) if o.type == "MESH" and o.data else 0, o.hide_viewport)
    return snap


def _diff(before, after):
    added = [n for n in after if n not in before]
    removed = [n for n in before if n not in after]
    changed = [n for n in after if n in before and after[n] != before[n]]
    return {"added": added[:60], "removed": removed[:60], "changed": changed[:60]}


def _issues():
    from mathutils import Vector
    ctx = bpy.context
    ctx.view_layer.update()
    boxes = []
    for o in ctx.scene.objects:
        if o.type not in ("MESH", "CURVE", "FONT") or o.get("jarvis_floor") or o.hide_render:
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        boxes.append((o.name, Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
                      Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))))
    if len(boxes) < 2:
        return []
    span = max(max(b[2][i] for b in boxes) - min(b[1][i] for b in boxes) for i in range(3))
    tol = max(span * 0.004, 0.002)
    out = []
    for i, a in enumerate(boxes):
        if not any(j != i and all(a[1][k] - tol <= b[2][k] and b[1][k] - tol <= a[2][k] for k in range(3))
                   for j, b in enumerate(boxes)):
            out.append(f"'{a[0]}' hiçbir parçaya değmiyor (havada / kopuk).")
    return out[:30]


def _in_window(fn):
    """Run an operator that needs a window (undo) from a timer: borrow the first window and a 3D view."""
    wm = bpy.context.window_manager
    if wm is None or not wm.windows:
        return fn()
    win = wm.windows[0]
    area = next((a for a in win.screen.areas if a.type == "VIEW_3D"), win.screen.areas[0])
    with bpy.context.temp_override(window=win, screen=win.screen, area=area):
        return fn()


def handle(req: dict) -> dict:
    if req.get("token") != _token() or not req.get("token"):
        return {"ok": False, "error": "token"}
    op = req.get("op")
    try:
        if op == "state":
            return {"ok": True, "state": _state()}
        if op == "issues":
            return {"ok": True, "issues": _issues()}
        if op in ("undo", "redo"):
            try:
                _in_window(getattr(bpy.ops.ed, op))
            except Exception as exc:
                return {"ok": False, "error": f"{op}: {exc}"}
            return {"ok": True, "state": _state()}
        if op == "exec":
            env = _kit_env()
            try:
                _in_window(lambda: bpy.ops.ed.undo_push(message="MAYK öncesi"))
            except Exception:
                pass
            before = _snapshot()
            try:
                exec(compile(req.get("code", ""), "jarvis_script.py", "exec"), env)
                bpy.context.view_layer.update()
            except Exception:
                tb = traceback.format_exc()
                lines = req.get("code", "").splitlines()
                import re
                hit = [int(n) for n in re.findall(r'jarvis_script.py", line (\d+)', tb)]
                if hit and 0 < hit[-1] <= len(lines):
                    tb += f"\nFailing line {hit[-1]}: {lines[hit[-1] - 1].strip()}"
                return {"ok": False, "error": tb}
            try:
                _in_window(lambda: bpy.ops.ed.undo_push(message="MAYK: " + (req.get("label") or "değişiklik")[:60]))
            except Exception:
                pass
            return {"ok": True, "state": _state(), "diff": _diff(before, _snapshot())}
        if op == "copy":                                  # a copy of the open scene, for renders and checks
            path = req.get("path")
            bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, check_existing=False)
            return {"ok": True, "path": path}
        return {"ok": False, "error": f"unknown op {op}"}
    except Exception:
        return {"ok": False, "error": traceback.format_exc()}


def serve_once() -> float:
    """Handle at most one waiting request; returns the delay until the next poll (a bpy timer)."""
    global _server
    if _server is None:
        try:
            _server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _server.bind(("127.0.0.1", PORT))
            _server.listen(4)
            _server.setblocking(False)
        except OSError:
            _server = None                         # another Blender already listens: stay quiet
            return 5.0
    try:
        conn, _addr = _server.accept()
    except (BlockingIOError, OSError):
        return 0.15
    try:
        conn.settimeout(5.0)
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        reply = handle(json.loads(data.decode("utf8") or "{}"))
    except Exception:
        reply = {"ok": False, "error": traceback.format_exc()}
    try:
        conn.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf8"))
    finally:
        conn.close()
    return 0.02


def register():
    if not bpy.app.timers.is_registered(serve_once):
        bpy.app.timers.register(serve_once, first_interval=1.0, persistent=True)


def unregister():
    global _server
    if bpy.app.timers.is_registered(serve_once):
        bpy.app.timers.unregister(serve_once)
    if _server is not None:
        _server.close()
        _server = None
