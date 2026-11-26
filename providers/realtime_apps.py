"""Restricted Windows system application launcher for Realtime.

No model-controlled path, arguments, shell, URI, search fallback or PATH lookup.
The caller must obtain the human's HUD approval before calling launch().
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import platform
import subprocess

APPLICATIONS = {
    "calculator": ("calc.exe", "Hesap Makinesi"),
    "notepad": ("notepad.exe", "Not Defteri"),
    "paint": ("mspaint.exe", "Paint"),
}


def supported():
    return platform.system() == "Windows"


def _system_directory():
    # Query Windows itself; never trust PATH or a model-supplied environment path.
    buffer = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < count < len(buffer):
        raise OSError("Windows sistem dizini okunamadı.")
    path = Path(buffer.value)
    if not path.is_absolute():
        raise OSError("Windows sistem dizini geçersiz.")
    return path


def launch(app_id):
    if not isinstance(app_id, str) or app_id not in APPLICATIONS:
        return "NOT EXECUTED: İzinli uygulama değil."
    if not supported():
        return "NOT EXECUTED: Bu uygulama kontrolü yalnızca Windows içindir."
    executable, label = APPLICATIONS[app_id]
    try:
        directory = _system_directory().resolve(strict=True)
        target = (directory / executable).resolve(strict=True)
        if target.parent != directory or not target.is_file():
            return "NOT EXECUTED: Sistem uygulaması doğrulanamadı."
        subprocess.Popen([str(target)], cwd=str(directory), shell=False,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except (OSError, RuntimeError):
        return f"NOT EXECUTED: {label} başlatma isteği başarısız."
    return f"{label} başlatma isteği gönderildi; pencerenin açıldığı doğrulanmadı."
