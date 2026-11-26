"""FRIDAY's logbook: everything printed, every traceback and every crash, kept on disk.

Before this the console was the only record — closed with the window, so "why did
it stop yesterday?" had no answer. `install()` (called first thing at startup)
tees stdout/stderr into a size-capped, rotating file with a timestamp on every
line, and records uncaught exceptions from any thread. `recent_errors()` reads
the problems back for the self check and for "son hataları göster".
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
KEEP = 4
_lock = threading.Lock()
_installed = False
_file = None
_path: Path | None = None


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "AetherMurat" / "logs"


def path() -> Path:
    return _path or (log_dir() / "aether.log")


def _rotate():
    """aether.log → aether.log.1 → … → aether.log.KEEP (the oldest is dropped) once it passes MAX_BYTES."""
    global _file
    p = path()
    try:
        if not p.exists() or p.stat().st_size <= MAX_BYTES:
            return
        if _file:
            _file.close()
        for i in range(KEEP - 1, 0, -1):
            src = p.with_suffix(f".log.{i}")
            if src.exists():
                os.replace(src, p.with_suffix(f".log.{i + 1}"))
        os.replace(p, p.with_suffix(".log.1"))
        _file = open(p, "a", encoding="utf-8", errors="replace")
    except OSError:
        pass


def write(text: str) -> None:
    """One or more lines into the logbook, each with its time."""
    if not text or _file is None:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        try:
            for line in text.splitlines():
                if line.strip():
                    _file.write(f"{stamp} {line}\n")
            _file.flush()
            _rotate()
        except Exception:
            pass


class _Tee:
    def __init__(self, stream):
        self._stream = stream
        self._buf = ""

    def write(self, s):
        try:
            if self._stream is not None:
                self._stream.write(s)
        except Exception:
            pass                                   # a console that went away must not stop the log
        self._buf += s
        if "\n" in self._buf:
            done, self._buf = self._buf.rsplit("\n", 1)
            write(done)
        return len(s)

    def flush(self):
        try:
            if self._stream is not None:
                self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install(directory: Path | None = None) -> Path:
    """Start the logbook (idempotent). Safe to call before anything else."""
    global _installed, _file, _path
    if _installed:
        return path()
    d = Path(directory) if directory else log_dir()
    d.mkdir(parents=True, exist_ok=True)
    _path = d / "aether.log"
    _file = open(_path, "a", encoding="utf-8", errors="replace")
    _installed = True
    write(f"──────── FRIDAY başladı (Python {sys.version.split()[0]}, {sys.platform}) ────────")
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
    old_hook = sys.excepthook

    def hook(etype, value, tb):
        import traceback
        write("ÇÖKME (yakalanmamış hata):\n" + "".join(traceback.format_exception(etype, value, tb)))
        try:
            old_hook(etype, value, tb)
        except Exception:
            pass
    sys.excepthook = hook

    def thread_hook(args):
        import traceback
        write(f"ÇÖKME ({args.thread.name if args.thread else 'thread'}):\n"
              + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thread_hook
    return _path


_PROBLEM = re.compile(r"(Traceback|Error\b|Exception|ÇÖKME|❌|failed|crashed|Hata|başarısız|yapılamadı)", re.I)
_NOISE = re.compile(r"(DeprecationWarning|FutureWarning|ResourceWarning)")


def recent_errors(hours: float = 24.0, limit: int = 12) -> list[str]:
    """The last problems in the logbook (one line each, newest last), within `hours`."""
    files = [path().with_suffix(".log.1"), path()]
    since = time.time() - hours * 3600
    found = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not _PROBLEM.search(line) or _NOISE.search(line):
                continue
            try:
                ts = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
            if ts >= since:
                found.append(line[:300])
    out = []
    for line in found:                              # the same error twenty times is one error
        if not out or out[-1][20:] != line[20:]:
            out.append(line)
    return out[-limit:]
