"""Start a reliable post-update FRIDAY relaunch without Qt imports.

When FRIDAY was started by a supervisor, return control to
that supervisor (which restarts on main.py's exit code 75). Otherwise launch
a detached helper that waits for the running process to release audio/Qt
resources before opening the updated main.py.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def schedule_restart(project_root: Path, current_pid: int,
                     executable: str | None = None) -> str:
    """Schedule restart, or raise *before* the existing GUI is closed.

    This function never kills the old process. Calling Qt code can request
    application quit only after this function has returned successfully.
    """
    if not isinstance(current_pid, int) or current_pid <= 0:
        raise ValueError("FRIDAY yeniden başlatma PID değeri geçersiz.")

    if os.environ.get("AETHER_MANAGED_RESTART") == "1":
        # A supervisor from a previous installation restarts on exit code 75.
        return "managed"

    project = Path(project_root).resolve()
    helper = project / "tools" / "restart_app.py"
    if not helper.is_file():
        raise FileNotFoundError(
            f"Yeniden başlatma aracı bulunamadı: {helper}"
        )
    python = str(executable or sys.executable)
    if not Path(python).is_file():
        raise FileNotFoundError(
            f"FRIDAY Python yürütülebilir dosyası bulunamadı: {python}"
        )

    log_root = Path(os.environ.get("LOCALAPPDATA")
                    or str(Path.home() / ".local" / "share"))
    from core.identity import artifact_home
    log_dir = artifact_home(log_root, logs=True) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "restart.log").open("a", encoding="utf-8") as log:
        helper_proc = subprocess.Popen(
            [python, str(helper), str(current_pid), str(project)],
            cwd=str(project),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=(0x08000000 if os.name == "nt" else 0),
            start_new_session=(os.name != "nt"),
        )
    if helper_proc.poll() is not None and helper_proc.returncode != 0:
        raise RuntimeError(
            "Yeniden başlatma aracı hemen sonlandı. "
            "Friday/logs/restart.log dosyasını kontrol edin."
        )
    return "helper"
