"""Disk temizliği: geçici dosyaların ne kadar yer kapladığını söyler; onay
verilirse 2 günden eski geçici dosyaları siler."""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

from plugins import _pc_kit as kit

PLUGIN = {
    "name": "disk_cleanup",
    "description": (
        "Disk temizliği: 'diskte ne kadar yer var', 'gereksiz dosyaları temizle', 'geçici dosyaları sil'. "
        "action: scan (ne kadar yer açılabilir, boş alan) | clean (2 günden eski geçici dosyaları siler). "
        "clean için önce scan sonucunu söyle ve kullanıcı açıkça onaylarsa confirm=true ile çağır."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "scan | clean"},
        "confirm": {"type": "BOOLEAN"},
    }, "required": ["action"]},
}

MIN_AGE = 2 * 86400
MAX_FILES = 50_000


def temp_dirs() -> list[Path]:
    out = {Path(tempfile.gettempdir())}
    if sys.platform == "win32":
        for env in ("TEMP", "TMP"):
            if os.environ.get(env):
                out.add(Path(os.environ[env]))
        win = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
        out.add(win)
    return [p for p in out if p.is_dir()]


def old_files(root: Path, now: float, min_age: float = MIN_AGE) -> list[tuple[Path, int]]:
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            if now - max(st.st_mtime, st.st_atime) >= min_age:
                found.append((p, st.st_size))
                if len(found) >= MAX_FILES:
                    return found
    return found


def free_text() -> str:
    import shutil
    total, _used, free = shutil.disk_usage(Path.home().anchor or "/")
    return f"Ana diskte {kit.human_size(free)} boş ({round(free / total * 100)}%)."


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        act = str(p.get("action") or "scan").lower()
        now = time.time()
        files = [x for d in temp_dirs() for x in old_files(d, now)]
        size = sum(s for _, s in files)
        if act != "clean":
            return f"{free_text()} Geçici dosyalarda {len(files)} eski dosya, {kit.human_size(size)} temizlenebilir. Silmemi ister misin?"
        if not p.get("confirm"):
            return f"{kit.human_size(size)} geçici dosya silinecek. Onaylıyor musun?"
        freed = n = 0
        for f, s in files:
            try:
                f.unlink()
                freed += s; n += 1
            except OSError:
                pass                                # in use: skipped
        kit.log(player, f"Disk temizliği: {n} dosya, {kit.human_size(freed)}")
        return f"{n} geçici dosya silindi, {kit.human_size(freed)} yer açıldı (kullanımdaki {len(files) - n} dosyaya dokunmadım). {free_text()}"
    except Exception as exc:
        return f"Disk temizliği yapılamadı: {exc}"
