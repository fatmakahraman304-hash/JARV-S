"""Bounded, cancellable command execution for MAYK's coding agent.

A shell=False call alone cannot stop a running test when the user presses
Durdur. Start each test in its own process group, poll cancellation, and kill
the entire spawned process tree on cancellation, timeout or excessive output.
The command's output goes to temporary files, not unbounded RAM buffers.
This is a process supervisor, not a sandbox: arbitrary project test scripts
still execute with the user's OS permissions.
"""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

MAX_CAPTURE = 8_000
MAX_OUTPUT_BYTES = 3_000_000
POLL_SECONDS = .15


class CommandTimedOut(RuntimeError):
    pass


class CommandOutputLimit(RuntimeError):
    pass


def _tail(stream, cap: int = MAX_CAPTURE) -> str:
    size = os.fstat(stream.fileno()).st_size
    stream.seek(max(0, size - cap * 3))
    return stream.read().decode("utf-8", errors="replace")[-cap:]


def _kill_tree(proc) -> None:
    """Kill children as well as their parent to prevent abandoned test runs."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            pass
    try:
        proc.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def execute(
    argv: list[str], cwd: Path, *, timeout: float,
    cancel_check: Callable[[], None],
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Return exit code, final stdout and stderr, or raise after cleanup.

    cancel_check may raise the caller's cancellation exception. It propagates
    unchanged after the subprocess tree is terminated.
    """
    with tempfile.TemporaryFile(mode="w+b") as out, \
            tempfile.TemporaryFile(mode="w+b") as err:
        proc = subprocess.Popen(
            argv, shell=False, cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, env=env,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                           getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            if os.name == "nt" else 0,
            start_new_session=(os.name != "nt"),
        )
        start = time.monotonic()
        try:
            while True:
                cancel_check()
                if (os.fstat(out.fileno()).st_size +
                        os.fstat(err.fileno()).st_size > MAX_OUTPUT_BYTES):
                    raise CommandOutputLimit(
                        "Test komutu aşırı çıktı üretti; güvenlik için durduruldu. "
                        + _tail(err, 350))
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise CommandTimedOut(
                        f"Test komutu {timeout:g} saniyede tamamlanmadı. "
                        + _tail(err, 350))
                try:
                    code = proc.wait(timeout=min(POLL_SECONDS, remaining))
                except subprocess.TimeoutExpired:
                    continue
                cancel_check()
                return int(code), _tail(out), _tail(err)
        finally:
            if proc.poll() is None:
                _kill_tree(proc)
