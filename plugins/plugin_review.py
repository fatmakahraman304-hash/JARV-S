"""Read-only, non-executing review of a Python plugin selected by the user.

This is an advisory inspection, not a sandbox or a grant of trust. In
particular, imported helpers, dynamic behavior and installed dependencies
are not verified by it.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

MAX_BYTES = 512 * 1024
MAX_NODES = 20_000

PLUGIN = {
    "name": "plugin_review",
    "description": (
        "Kullanıcının açıkça belirttiği yerel Python eklenti dosyasını çalıştırmadan "
        "incele: eklenti yapısı, SHA-256 ve dikkat gerektiren kod örüntüleri. "
        "Use when asked to review a plugin file before installing it. "
        "Do not use to install, approve, execute or change a plugin."
    ),
    "tier": "extra",
    "parameters": {"type": "OBJECT", "properties": {
        "path": {"type": "STRING", "description": "Kullanıcının seçtiği .py dosyasının tam yerel yolu."}
    }, "required": ["path"]},
}

_IMPORT_GROUPS = {
    "Ağ erişimi": {"requests", "httpx", "urllib", "http", "socket", "websockets", "ftplib", "smtplib"},
    "Sistem veya süreç erişimi": {"os", "subprocess", "ctypes", "win32api", "win32com", "multiprocessing"},
    "Dosya işlemleri": {"pathlib", "shutil", "tempfile", "zipfile", "tarfile"},
    "Klavye, ekran veya kamera": {"pyautogui", "pynput", "keyboard", "mss", "cv2", "pyperclip"},
    "Dinamik yükleme": {"importlib", "runpy", "pickle", "marshal"},
}
_CALLS = {
    "open": "Dosya erişimi",
    "eval": "Dinamik kod yürütme",
    "exec": "Dinamik kod yürütme",
    "__import__": "Dinamik yükleme",
    "compile": "Dinamik kod hazırlama",
    "system": "Sistem veya süreç erişimi",
    "Popen": "Sistem veya süreç erişimi",
    "unlink": "Dosya silme",
    "rmtree": "Dosya silme",
}


def inspect_source(raw: bytes) -> dict:
    if len(raw) > MAX_BYTES:
        raise ValueError("Dosya 512 KB sınırını aşıyor.")
    tree = ast.parse(raw.decode("utf-8-sig"), filename="<plugin>")
    imports = set()
    flags = set()
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > MAX_NODES:
            raise ValueError("Dosyanın sözdizimi inceleme sınırını aşıyor.")
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not node.level:
                imports.add(node.module.split(".")[0])
            if node.level or (node.module or "").startswith(("plugins.", "user_plugins.")):
                flags.add("Bağımlı eklenti dosyaları ayrıca incelenmeli")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if name in _CALLS:
                flags.add(_CALLS[name])
    for label, modules in _IMPORT_GROUPS.items():
        if imports & modules:
            flags.add(label)
    if any(name.startswith("_") for name in imports):
        flags.add("Yardımcı dosyalar ayrıca incelenmeli")
    metadata = False
    runner = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PLUGIN" for t in node.targets):
            metadata = isinstance(node.value, ast.Dict)
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            runner = True
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "plugin_dict": metadata,
        "run_function": runner,
        "flags": sorted(flags),
    }


def run(parameters: dict, player=None, session_memory=None) -> str:
    value = parameters.get("path") if isinstance(parameters, dict) else None
    if not isinstance(value, str) or not value.strip():
        return "İncelemek için bir yerel .py dosyası seç."
    try:
        path = Path(value.strip()).expanduser()
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
            return "Tam yerel dosya yolu gerekli; ağ yolları desteklenmiyor."
        if path.suffix.lower() != ".py" or not path.is_file() or path.is_symlink():
            return "Normal bir yerel .py dosyası seç."
        resolved = path.resolve(strict=True)
        if str(resolved).startswith(("\\\\", "//")):
            return "Ağ yolları desteklenmiyor."
        with resolved.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        report = inspect_source(raw)
    except (OSError, ValueError, SyntaxError, RecursionError) as exc:
        # Never include the source line or arbitrary exception text in the reply.
        return f"Eklenti incelenemedi ({type(exc).__name__}); UTF-8 Python dosyası ve boyutu kontrol et."
    yes_no = lambda value: "var" if value else "bulunamadı"
    risks = "; ".join(report["flags"]) or "Bu sınırlı taramada belirgin örüntü bulunmadı"
    return (
        f"SHA-256: {report['sha256']}\n"
        f"PLUGIN sözlüğü: {yes_no(report['plugin_dict'])}; run fonksiyonu: {yes_no(report['run_function'])}.\n"
        f"Dikkat: {risks}.\n"
        "Kod çalıştırılmadı veya değiştirilmedi. Bu rapor güvenlik garantisi, yükleme izni ya da onay değildir. "
        "Dinamik davranış ve bağımlılıklar ayrıca incelenmelidir."
    )
