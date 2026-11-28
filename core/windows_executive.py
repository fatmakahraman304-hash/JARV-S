"""A small reversible Windows executive: built-in power schemes only.

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


def set_plan(mode, directory=None):
    if mode not in SCHEMES:
        raise ValueError("Choose balanced, power_saver or high_performance")
    target = SCHEMES[mode]
    with ExecutiveJournal(directory or journal_directory()) as journal:
        if journal.pending():
            raise JournalError("An earlier operation has an unknown result and needs user inspection")
        before, available = active_guid(), available_guids()
        if target not in available:
            raise ExecutiveError("The requested built-in power scheme is not available")
        if before == target:
            return {"status": "unchanged", "mode": mode}
        record = journal.begin("power_plan", before, target)
        ident = record["id"]
        try:
            # Do not overwrite a setting the user changed while we prepared.
            current = active_guid()
        except Exception as exc:
            try:
                journal.transition(ident, "started", "aborted")
            except Exception as journal_exc:
                raise UnknownOutcome(ident) from journal_exc
            raise ExecutiveError("The current power scheme could not be rechecked; nothing was done") from exc
        if current != before:
            try:
                journal.transition(ident, "started", "aborted")
            except Exception as exc:
                raise UnknownOutcome(ident) from exc
            raise ExecutiveError("The power scheme changed before execution; nothing was done")
        try:
            _run("/setactive", target)
            if active_guid() != target:
                raise ExecutiveError("The requested power scheme could not be verified")
            journal.transition(ident, "started", "done")
        except Exception as exc:
            raise UnknownOutcome(ident) from exc
        return {"status": "done", "mode": mode, "operation_id": ident}


def undo(operation_id, directory=None):
    with ExecutiveJournal(directory or journal_directory()) as journal:
        if journal.pending():
            raise JournalError("An earlier operation has an unknown result and needs user inspection")
        record = journal.get(operation_id)
        if not record or record.get("kind") != "power_plan" or record.get("status") != "done":
            raise ExecutiveError("That operation cannot be undone")
        before, target = record.get("before", ""), record.get("target", "")
        if not _GUID.fullmatch(before) or target not in SCHEMES.values() or before not in available_guids():
            raise ExecutiveError("The previous scheme is no longer available")
        if active_guid() != target:
            raise ExecutiveError("The current scheme changed since this operation; it was not overwritten")
        journal.transition(operation_id, "done", "undo_started")
        try:
            current = active_guid()
        except Exception as exc:
            try:
                journal.transition(operation_id, "undo_started", "done")
            except Exception as journal_exc:
                raise UnknownOutcome(operation_id) from journal_exc
            raise ExecutiveError("The current power scheme could not be rechecked; nothing was done") from exc
        if current != target:
            try:
                journal.transition(operation_id, "undo_started", "done")
            except Exception as exc:
                raise UnknownOutcome(operation_id) from exc
            raise ExecutiveError("The current scheme changed before undo; it was not overwritten")
        try:
            _run("/setactive", before)
            if active_guid() != before:
                raise ExecutiveError("The previous scheme could not be verified")
            journal.transition(operation_id, "undo_started", "undone")
        except Exception as exc:
            raise UnknownOutcome(operation_id) from exc
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
