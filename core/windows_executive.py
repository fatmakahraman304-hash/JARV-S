"""Reversible Windows settings with typed, allowlisted operations.

No shell, arbitrary command, elevation, or creation/deletion of power schemes.
Every mutation is checkpointed before execution and verified afterwards.
"""
from __future__ import annotations

import ctypes
import platform
from pathlib import Path
import re
import subprocess

from core.executive_journal import ExecutiveJournal
from core.neural_journal import JournalError

SCHEMES = {"balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
           "power_saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
           "high_performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}
_GUID = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?![0-9a-f])")


class ExecutiveError(RuntimeError):
    pass


class UnknownOutcome(ExecutiveError):
    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__("The operation outcome is unknown and needs user inspection")


def journal_directory():
    from core.identity import data_home
    return data_home() / "windows_executive"


def _executable():
    if platform.system() != "Windows":
        raise ExecutiveError("Windows power control is available only on Windows")
    buf = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetSystemDirectoryW(buf, len(buf))
    if not size or size >= len(buf):
        raise ExecutiveError("Windows system directory could not be determined")
    exe = Path(buf.value) / "powercfg.exe"
    if not exe.is_file():
        raise ExecutiveError("Windows powercfg.exe is unavailable")
    return exe


def _run(*args):
    proc = subprocess.run([str(_executable()), *args], shell=False, input="", capture_output=True,
                          encoding="utf-8", errors="replace", timeout=10,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode:
        raise ExecutiveError(f"powercfg failed with exit code {proc.returncode}")
    if len(proc.stdout) > 200_000 or len(proc.stderr) > 200_000:
        raise ExecutiveError("powercfg output exceeds the limit")
    return proc.stdout


def active_guid():
    found = {x.lower() for x in _GUID.findall(_run("/getactivescheme"))}
    if len(found) != 1:
        raise ExecutiveError("The active power scheme could not be determined")
    return found.pop()


def available_guids():
    values = {x.lower() for x in _GUID.findall(_run("/list"))}
    if not values:
        raise ExecutiveError("The power scheme list could not be determined")
    return values


def status():
    active, available = active_guid(), available_guids()
    current = next((name for name, guid in SCHEMES.items() if guid == active), "custom")
    return {"current": current, "available": [name for name, guid in SCHEMES.items() if guid in available]}


def _pointer_speed():
    value = ctypes.c_int()
    if not ctypes.windll.user32.SystemParametersInfoW(0x0070, 0, ctypes.byref(value), 0):
        raise ExecutiveError("Windows could not read pointer speed")
    if not 1 <= value.value <= 20:
        raise ExecutiveError("Windows returned an invalid pointer speed")
    return str(value.value)


def _write_pointer(value):
    if value not in {str(n) for n in range(1, 21)}:
        raise ValueError("Pointer speed must be between 1 and 20")
    # SPI_SETMOUSESPEED, current session only. No registry persistence or broadcast.
    if not ctypes.windll.user32.SystemParametersInfoW(0x0071, 0, ctypes.c_void_p(int(value)), 0):
        raise ExecutiveError("Windows could not set pointer speed")


def _setting(kind):
    if kind == "power_plan":
        return active_guid, lambda guid: _run("/setactive", guid)
    if kind == "pointer_speed":
        return _pointer_speed, _write_pointer
    raise ExecutiveError("Unsupported Windows setting")


def _apply(journal, ident, kind, expected, target, undoing=False):
    read, write = _setting(kind)
    state, cancelled, success = ("undo_started", "done", "undone") if undoing else ("started", "aborted", "done")
    try:
        if read() != expected:
            raise ExecutiveError("Setting changed before undo" if undoing else "Setting changed before execution")
    except Exception:
        try:
            journal.transition(ident, state, cancelled)
        except Exception as exc:
            raise UnknownOutcome(ident) from exc
        raise
    try:
        write(target)
        if read() != target:
            raise ExecutiveError("Setting readback differs from target")
        journal.transition(ident, state, success)
    except Exception as exc:
        raise UnknownOutcome(ident) from exc


def _set(kind, target, directory):
    with ExecutiveJournal(directory or journal_directory()) as journal:
        if journal.pending():
            raise JournalError("An earlier operation has an unknown result and needs user inspection")
        read, _ = _setting(kind)
        before = read()
        if kind == "power_plan" and target not in available_guids():
            raise ExecutiveError("The requested built-in power scheme is not available")
        if before == target:
            return {"status": "unchanged"}
        ident = journal.begin(kind, before, target)["id"]
        _apply(journal, ident, kind, before, target)
        return {"status": "done", "operation_id": ident}


def set_plan(mode, directory=None):
    if mode not in SCHEMES:
        raise ValueError("Choose balanced, power_saver or high_performance")
    return dict(_set("power_plan", SCHEMES[mode], directory), mode=mode)


def set_pointer_speed(speed, directory=None):
    if type(speed) is not int or not 1 <= speed <= 20:
        raise ValueError("Pointer speed must be an integer between 1 and 20")
    return _set("pointer_speed", str(speed), directory)


def undo(operation_id, directory=None):
    with ExecutiveJournal(directory or journal_directory()) as journal:
        if journal.pending():
            raise JournalError("An earlier operation has an unknown result and needs user inspection")
        record = journal.get(operation_id)
        if not record or record["status"] != "done":
            raise ExecutiveError("That operation cannot be undone")
        kind, before, target = record["kind"], record["before"], record["target"]
        read, _ = _setting(kind)
        if kind == "power_plan" and (not _GUID.fullmatch(before) or target not in SCHEMES.values() or before not in available_guids()):
            raise ExecutiveError("The previous scheme is no longer available")
        if read() != target:
            raise ExecutiveError("The setting changed since this operation; it was not overwritten")
        journal.transition(operation_id, "done", "undo_started")
        _apply(journal, operation_id, kind, target, before, undoing=True)
        return {"status": "undone", "operation_id": operation_id}


def pending_operations(directory=None):
    with ExecutiveJournal(directory or journal_directory()) as journal:
        return journal.pending()


def operation_history(directory=None):
    with ExecutiveJournal(directory or journal_directory()) as journal:
        return journal.recent()


def acknowledge(operation_id, expected_status, directory=None):
    """Clear only the exact unresolved record after a real user confirmation."""
    if expected_status not in ("started", "undo_started"):
        raise ValueError("only unresolved operations can be acknowledged")
    with ExecutiveJournal(directory or journal_directory()) as journal:
        journal.transition(operation_id, expected_status, "acknowledged")
