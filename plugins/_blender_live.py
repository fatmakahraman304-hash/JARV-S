"""Mayk side of the live Blender link (see _blender_live_addon.py, which runs
inside Blender): install the add-on, talk to the open Blender, and let the
user direct the scene in their own window."""
from __future__ import annotations

import json
import secrets
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDON = Path(__file__).with_name("_blender_live_addon.py")
TOKEN = ROOT / "memory" / "blender_live.token"
LAST = ROOT / "memory" / "blender_live_last.json"       # what Mayk changed last: what "onu / it" means
PORT = 47863


def token() -> str:
    try:
        t = TOKEN.read_text(encoding="utf8").strip()
        if t:
            return t
    except OSError:
        pass
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    t = secrets.token_hex(16)
    TOKEN.write_text(t, encoding="utf8")
    return t


def startup_dir(binary: str) -> Path:
    """Blender's own user scripts/startup folder (asked from Blender, so every OS and version is right)."""
    r = subprocess.run([binary, "-b", "--factory-startup", "--python-expr",
                        "import bpy;print('JARVIS_STARTUP=' + bpy.utils.user_resource('SCRIPTS', path='startup', create=True))"],
                       capture_output=True, encoding="utf8", errors="replace", timeout=180)
    for line in (r.stdout or "").splitlines():
        if line.startswith("JARVIS_STARTUP="):
            return Path(line.split("=", 1)[1].strip())
    raise ValueError("Blender'ın eklenti klasörü bulunamadı: " + ((r.stderr or r.stdout or "").strip().splitlines() or [""])[-1][:200])


def install(binary: str) -> Path:
    """Put the live link in Blender's startup folder (idempotent). Takes effect in Blenders opened afterwards."""
    token()
    folder = startup_dir(binary)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "jarvis_live.py"
    code = ADDON.read_text(encoding="utf8").replace("__JARVIS_DIR__", str(ROOT).replace("\\", "\\\\"))
    if not target.is_file() or target.read_text(encoding="utf8") != code:
        target.write_text(code, encoding="utf8")
    return target


def call(op: str, timeout: float = 120.0, **fields) -> dict:
    req = {"token": token(), "op": op, **fields}
    with socket.create_connection(("127.0.0.1", PORT), timeout=3.0) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    reply = json.loads(data.decode("utf8") or "{}")
    if reply.get("error") == "token":
        raise ConnectionError("Açık Blender Mayk'ı tanımadı (eski bağlantı). Blender'ı kapatıp yeniden aç.")
    return reply


def available() -> bool:
    try:
        return bool(call("state", timeout=5.0).get("ok"))
    except (OSError, ValueError, ConnectionError):
        return False


def state() -> dict:
    r = call("state", timeout=10.0)
    if not r.get("ok"):
        raise ValueError(r.get("error") or "Blender durumu alınamadı")
    return r["state"]


def run(code: str, label: str = "") -> dict:
    """Run a script in the open Blender; raises ValueError(traceback) when it fails (for the fix loop)."""
    r = call("exec", timeout=600.0, code=code, label=label)
    if not r.get("ok"):
        raise ValueError(r.get("error") or "Blender betiği çalışmadı")
    d = r.get("diff") or {}
    touched = (d.get("added") or []) + (d.get("changed") or [])
    if touched and label not in ("aç", "seç"):
        try:
            LAST.parent.mkdir(parents=True, exist_ok=True)
            LAST.write_text(json.dumps({"request": label, **d}, ensure_ascii=False), encoding="utf8")
        except OSError:
            pass
    return r["state"]


def last_change() -> dict:
    try:
        return json.loads(LAST.read_text(encoding="utf8"))
    except Exception:
        return {}


def copy_scene(path: str) -> str:
    r = call("copy", timeout=120.0, path=path)
    if not r.get("ok"):
        raise ValueError(r.get("error") or "Sahnenin kopyası alınamadı")
    return r["path"]


def issues() -> list[str]:
    r = call("issues", timeout=30.0)
    return r.get("issues") or [] if r.get("ok") else []


def undo(redo: bool = False) -> dict:
    r = call("redo" if redo else "undo", timeout=20.0)
    if not r.get("ok"):
        raise ValueError(r.get("error") or "Geri alınamadı")
    return r["state"]


def edit(request: str, player=None) -> str:
    """The user's command on the open scene: 'şunu/bunu' is what they have selected; only that changes."""
    from plugins import _blender_brain as brain
    st = state()
    sel = st.get("selected") or []
    last = last_change()
    recent = (last.get("added") or []) + (last.get("changed") or [])
    told = (f"{request}\n\nThis runs LIVE in the user's open Blender window. Selected objects (what 'bu', 'şu', 'bunu', "
            f"'şunu', 'this' mean): {sel or 'none'}; active: {st.get('active')}.\n"
            f"What Mayk changed last (for «{last.get('request', '')}») — what 'onu', 'o', 'it', 'biraz daha' refer to "
            f"when nothing is selected: {recent[:20] or 'nothing yet'}.\n"
            "Change ONLY what the user said; keep every other object exactly as it is. Never call clear() or studio() "
            "unless the user asks; do not save or render.")
    if player is not None:
        player.write_log(f"🟧 Açık Blender'da: {request}" + (f"  (seçili: {', '.join(sel[:5])})" if sel else ""))
    brain.run_with_fixes(told, st, st.get("version", "4"), lambda code: run(code, request), log=print)
    found = issues()
    if found:                                        # one more pass for what it broke or left floating
        brain.run_with_fixes(f"{told}\nAfter the change these parts are floating or disconnected — fix them "
                             f"without undoing the user's change:\n- " + "\n- ".join(found[:10]),
                             state(), st.get("version", "4"), lambda code: run(code, "düzeltme"), log=print)
        found = issues()
    score = look_live(request, player)
    return "Yaptım." + (f" Hâlâ kopuk görünen parçalar var: {'; '.join(found[:3])}" if found else "") + \
        (f" ({score:.0f}/10)" if score is not None else "")


def _studio():
    from plugins import blender_studio
    return blender_studio


def preview(player=None, title="Blender") -> tuple[bytes, list[str]]:
    """Pictures of the open scene from several sides (rendered from a copy, so the window never freezes)."""
    import tempfile
    studio = _studio()
    with tempfile.TemporaryDirectory() as temp:
        copy = copy_scene(str(Path(temp) / "canli.blend"))
        png, issues_ = studio.views_sheet(studio.executable(), Path(copy), Path(temp))
        if png and player is not None and hasattr(player, "show_image"):
            keep = ROOT / "memory" / "blender_preview.png"
            keep.write_bytes(png)
            player.show_image(str(keep), title)
    return png, issues_


def look_live(request: str, player=None):
    """Mayk looks at what it just did in the open window; real defects (not taste) get one fix."""
    from plugins import _blender_brain as brain
    try:
        png, found = preview(player, f"Blender: {request[:40]}")
        verdict = brain.look(png, request, found) if png else {}
    except Exception as exc:
        print(f"[Blender] Canlı önizleme olmadı: {exc}")
        return None
    if not verdict:
        return None
    if verdict.get("score", 10) < 7 and verdict.get("problems"):
        st = state()
        brain.run_with_fixes(f"{request}\nThis runs LIVE in the user's open Blender. Your change has these defects — "
                             "fix them without changing anything the user did not ask for:\n- " +
                             "\n- ".join(verdict["problems"][:6]), st, st.get("version", "4"),
                             lambda code: run(code, request), log=print)
        try:
            png, found = preview(player, f"Blender: {request[:40]}")
            again = brain.look(png, request, found) if png else {}
            return again.get("score", verdict["score"]) if again else verdict["score"]
        except Exception:
            return verdict["score"]
    return verdict["score"]


def render(player=None, width=1920, height=1080, samples=128) -> Path:
    """'Render al' on the open scene: a copy is rendered in the background with Cycles; the window stays free."""
    import shutil
    import tempfile
    studio = _studio()
    temp = Path(tempfile.mkdtemp(prefix="canli-render-"))
    copy = copy_scene(str(temp / "canli.blend"))
    studio.invoke(studio.executable(), Path(copy), temp, "render", auto_camera=True)
    out = temp / "render.png"
    if not out.is_file():
        raise ValueError("Render dosyası oluşmadı.")
    keep_dir = studio.ROOT / "Renderlar"
    keep_dir.mkdir(parents=True, exist_ok=True)
    import time as _t
    final = keep_dir / f"render_{_t.strftime('%Y%m%d_%H%M%S')}.png"
    shutil.copyfile(out, final)
    shutil.rmtree(temp, ignore_errors=True)
    if player is not None and hasattr(player, "show_image"):
        player.show_image(str(final), "Blender render")
    return final


def open_file(path: str) -> None:
    """Show a .blend in the user's open window (after Mayk rebuilt it)."""
    run(f"import bpy\nbpy.ops.wm.open_mainfile(filepath={path!r})\n", "aç")
