"""Local user plugin approval store. Never executes a plugin.

An approval is tied to exact source bytes. This is a consent mechanism, not
a sandbox, signature, or defense against another process running as the user.
Only the desktop's explicit human approval flow should call approve().
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

MAX_BYTES = 512 * 1024
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")


def directory() -> Path:
    return Path.home() / ".friday" / "user_plugins"


def inspect_bytes(raw: bytes) -> tuple[str, str]:
    if len(raw) > MAX_BYTES:
        raise ValueError("Eklenti 512 KB sınırını aşıyor.")
    tree = ast.parse(raw.decode("utf-8-sig"))
    declarations = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PLUGIN" for t in node.targets):
            declarations.append(ast.literal_eval(node.value))
    if len(declarations) != 1 or not isinstance(declarations[0], dict):
        raise ValueError("Tek bir sabit PLUGIN sözlüğü gerekli.")
    meta = declarations[0]
    name = meta.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("Geçersiz eklenti adı.")
    if not isinstance(meta.get("description"), str) or not meta["description"].strip():
        raise ValueError("Eklenti açıklaması gerekli.")
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        raise ValueError("run fonksiyonu bulunamadı.")
    return name, hashlib.sha256(raw).hexdigest()


def read_source(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".py":
        raise ValueError("Normal bir Python dosyası gerekli.")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Eklenti 512 KB sınırını aşıyor.")
    return raw


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def approve(root: Path, raw: bytes, reviewed_digest: str, reserved: set[str]) -> str:
    name, digest = inspect_bytes(raw)
    if digest != reviewed_digest:
        raise ValueError("Dosya incelemeden sonra değişti; tekrar onay gerekli.")
    if name.casefold() in {item.casefold() for item in reserved}:
        raise ValueError("Bu ad yerleşik bir araca ait.")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Bağlantılı eklenti klasörü desteklenmiyor.")
    source = root / (name + ".py")
    receipt = root / (name + ".approval.json")
    if source.is_symlink() or receipt.is_symlink():
        raise ValueError("Bağlantılı dosya desteklenmiyor.")
    # Source first; interruption before the receipt leaves an unapproved
    # file or a digest mismatch, never approval for different bytes.
    _atomic_write(source, raw)
    _atomic_write(receipt, json.dumps({"name": name, "sha256": digest}).encode("utf-8"))
    return name


def approved_source(root: Path, name: str) -> bytes:
    if not _NAME.fullmatch(name) or root.is_symlink():
        raise ValueError("Geçersiz eklenti konumu.")
    receipt = root / (name + ".approval.json")
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("Kullanıcı onayı yok.")
    with receipt.open("rb") as stream:
        data = json.loads(stream.read(4097))
    raw = read_source(root / (name + ".py"))
    declared, digest = inspect_bytes(raw)
    if (declared != name or not isinstance(data, dict)
            or data.get("name") != name or data.get("sha256") != digest):
        raise ValueError("Eklenti değişti; yeniden onay gerekli.")
    return raw


def installed_names(root: Path) -> list[str]:
    """List only the managed user files, including revoked or broken plugins."""
    if root.is_symlink():
        raise ValueError("Bağlantılı eklenti klasörü desteklenmiyor.")
    if not root.is_dir():
        return []
    names = set()
    for entry in root.iterdir():
        if entry.name.endswith(".approval.json"):
            name = entry.name[:-len(".approval.json")]
        elif entry.suffix == ".py":
            name = entry.stem
        else:
            continue
        if _NAME.fullmatch(name):
            names.add(name)
    return sorted(names, key=str.casefold)


def revoke(root: Path, name: str) -> None:
    """Withdraw approval without touching the source, settings or bundled code."""
    if not isinstance(name, str) or not _NAME.fullmatch(name) or root.is_symlink():
        raise ValueError("Geçersiz eklenti konumu.")
    # Unlink the receipt itself (including a symlink), never its target.
    # A missing receipt already means no approval.
    (root / (name + ".approval.json")).unlink(missing_ok=True)


def remove(root: Path, name: str) -> None:
    """Revoke first; if deletion fails, the remaining source stays unapproved."""
    revoke(root, name)
    (root / (name + ".py")).unlink(missing_ok=True)
