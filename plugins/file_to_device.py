"""Bilgisayardaki bir dosyayı telefona/tablete/TV'ye gönder: resimler orada
görünür, yazı ve kod dosyaları ekranda açılır."""
from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

PLUGIN = {
    "name": "file_to_device",
    "description": (
        "Bilgisayardaki bir dosyayı başka cihaza gönder: 'masaüstündeki fatura resmini telefona gönder', "
        "'indirilenlerdeki notları tablete at', 'şu kodu telefonuma yolla'. name: dosya adı ya da adından bir parça; "
        "device: cihaz (varsayılan telefon). Resimler (2,5 MB'a kadar) ve yazı/kod dosyaları (200 KB'a kadar) gider. "
        "Son çizilen resim için send_to_device kullan."
    ),
    "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "device": {"type": "STRING"}}, "required": ["name"]},
}

TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".java", ".kt", ".c", ".cpp", ".h",
            ".cs", ".go", ".rs", ".yml", ".yaml", ".ini", ".log", ".xml", ".sql", ".sh", ".ps1", ".bat"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_IMG, MAX_TEXT = 2_500_000, 200_000
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "AppData", ".venv", "venv"}


def roots() -> list[Path]:
    home = Path.home()
    out = []
    for sub in ("Desktop", "Masaüstü", "Downloads", "İndirilenler", "Documents", "Belgeler", "Pictures", "Resimler", "OneDrive/Desktop", "OneDrive/Masaüstü"):
        p = home / sub
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def find_file(name: str, where: list[Path], depth: int = 2) -> Path | None:
    """Exact name first, then the newest file whose name contains every word."""
    q = (name or "").casefold().strip()
    if not q:
        return None
    direct = Path(name).expanduser()
    if direct.is_file():
        return direct
    words = [w for w in q.replace("_", " ").replace("-", " ").split() if w]
    exact, partial = [], []
    for root in where:
        base = len(root.parts)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            if len(Path(dirpath).parts) - base >= depth:
                dirs[:] = []
            for f in files:
                fl = f.casefold()
                p = Path(dirpath) / f
                if fl == q or Path(fl).stem == q:
                    exact.append(p)
                elif all(w in fl for w in words):
                    partial.append(p)
    pool = exact or partial
    if not pool:
        return None
    return max(pool, key=lambda p: p.stat().st_mtime)


def command_for(path: Path) -> tuple[dict | None, str]:
    ext, size = path.suffix.lower(), path.stat().st_size
    if ext in IMG_EXT:
        if size > MAX_IMG:
            return None, f"{path.name} çok büyük ({size // 1_000_000} MB); 2,5 MB'a kadar resim gönderebiliyorum."
        return {"kind": "image", "data": base64.b64encode(path.read_bytes()).decode(),
                "mime": mimetypes.guess_type(path.name)[0] or "image/png", "title": path.name, "prompt": path.name}, ""
    if ext in TEXT_EXT:
        if size > MAX_TEXT:
            return None, f"{path.name} çok büyük; 200 KB'a kadar yazı dosyası gönderebiliyorum."
        text = path.read_text(encoding="utf-8", errors="replace")
        return {"kind": "text" if ext in {".txt", ".md", ".log", ".csv"} else "code", "text": text, "title": path.name, "filename": path.name}, ""
    return None, f"{path.name} türündeki dosyaları ({ext or 'uzantısız'}) gönderemiyorum; resim ya da yazı/kod dosyası olmalı."


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        p = parameters or {}
        path = find_file(str(p.get("name") or ""), roots())
        if not path:
            return f"'{p.get('name')}' adında bir dosya bulamadım (Masaüstü, İndirilenler, Belgeler, Resimler'e baktım)."
        cmd, err = command_for(path)
        if cmd is None:
            return err
        ok, msg = sync_hub.send_to_device(str(p.get("device") or "telefon"), cmd)
        return f"{path.name}: {msg}" if ok else msg
    except Exception as exc:
        return f"Dosya gönderilemedi: {exc}"
