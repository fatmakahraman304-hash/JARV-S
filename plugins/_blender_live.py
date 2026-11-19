"""JARVIS side of the live Blender link (see _blender_live_addon.py, which runs
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
        raise ConnectionError("Açık Blender JARVIS'i tanımadı (eski bağlantı). Blender'ı kapatıp yeniden aç.")
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
    return r["state"]


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
    told = (f"{request}\n\nThis runs LIVE in the user's open Blender window. Selected objects (what 'bu', 'şu', 'bunu', "
            f"'şunu', 'this', 'it' mean): {sel or 'none'}; active: {st.get('active')}.\n"
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
    return "Yaptım." + (f" Hâlâ kopuk görünen parçalar var: {'; '.join(found[:3])}" if found else "")


def open_file(path: str) -> None:
    """Show a .blend in the user's open window (after JARVIS rebuilt it)."""
    run(f"import bpy\nbpy.ops.wm.open_mainfile(filepath={path!r})\n", "aç")
