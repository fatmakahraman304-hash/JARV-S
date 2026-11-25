"""Windows first-visible-window timing for clean, tracked-source ZIP copies.

Uses the production restart receipt and native close message. No API keys,
user memory, microphone session or copied signing/config files are used.
"""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


def source_copy(root: Path, target: Path):
    paths = subprocess.check_output(["git", "ls-files", "-z", "*.py", "requirements.txt"], cwd=root).decode().split("\0")
    for name in paths:
        if not name or name.startswith(("tests/", "config/")):
            continue
        source = root / name
        if source.is_symlink():
            raise ValueError("Symlinked startup source is not accepted")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def window_for(process):
    import psutil
    try:
        ids = {process.pid} | {child.pid for child in psutil.Process(process.pid).children(recursive=True)}
    except psutil.NoSuchProcess:
        return None
    user32 = ctypes.windll.user32
    windows = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def inspect(handle, _):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(handle), ctypes.byref(pid))
        if pid.value in ids and user32.IsWindowVisible(ctypes.c_void_p(handle)):
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(ctypes.c_void_p(handle), title, len(title))
            if title.value.startswith("FRIDAY"):
                windows.append(handle)
        return True
    user32.EnumWindows(callback_type(inspect), 0)
    return windows[0] if windows else None


def measure(root: Path, interpreter: Path, output: Path):
    if sys.platform != "win32":
        raise RuntimeError("This probe requires a real Windows desktop")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="friday-first-window-") as directory:
        clean = Path(directory)
        source_copy(root, clean)
        receipt = clean / "window-ready"
        env = {**os.environ, "AETHER_RESTART_RECEIPT": str(receipt), "QT_OPENGL": "software",
               "LOCALAPPDATA": str(clean / "LocalAppData"), "APPDATA": str(clean / "AppData"),
               "XDG_DATA_HOME": str(clean / "Data")}
        for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
                     "NVIDIA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ABACUS_API_KEY"):
            env.pop(name, None)
        # A user-level Qt scale override is part of the installed app's normal
        # behaviour; no model/provider configuration is supplied to this probe.
        with (output / "process.log").open("wb") as log:
            started = time.perf_counter()
            process = subprocess.Popen([str(interpreter), "main.py"], cwd=clean, env=env, stdout=log, stderr=log)
            window = None
            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"Application exited before the first window: {process.returncode}")
                    if receipt.is_file():
                        window = window_for(process)
                        if window:
                            break
                    time.sleep(.02)
                if not window:
                    raise TimeoutError("No visible FRIDAY window and restart receipt")
                first_window_ms = (time.perf_counter() - started) * 1000
                # WM_CLOSE is the user's normal close gesture, not termination.
                posted = ctypes.windll.user32.PostMessageW(ctypes.c_void_p(window), 0x0010, 0, 0)
                if not posted:
                    raise RuntimeError("Window did not accept a close message")
                process.wait(timeout=30)
                if process.returncode:
                    raise RuntimeError(f"Application did not close normally: {process.returncode}")
            finally:
                if process.poll() is None:
                    import psutil
                    try:
                        owner = psutil.Process(process.pid)
                        for child in owner.children(recursive=True):
                            child.kill()
                        owner.kill()
                    except psutil.NoSuchProcess:
                        pass
                    process.wait(timeout=10)
        result = {"first_visible_window_ms": first_window_ms, "restart_receipt": True,
                  "native_window": True, "normal_exit": True, "profile": "clean ZIP/source; no API key",
                  "live_model_verified": False, "physical_user_hardware_verified": False}
        (output / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


def compare(before: Path, after: Path, output: Path):
    groups = []
    for root in (before, after):
        values = [json.loads(file.read_text()) for file in sorted(root.glob("*/metrics.json"))]
        if len(values) != 3 or not all(value["native_window"] and value["normal_exit"] and value["restart_receipt"] for value in values):
            raise AssertionError("Three normally closed native windows per checkout required")
        groups.append([value["first_visible_window_ms"] for value in values])
    result = {"baseline_ms": groups[0], "candidate_ms": groups[1],
              "baseline_median_ms": statistics.median(groups[0]), "candidate_median_ms": statistics.median(groups[1]),
              "profile": "clean source/ZIP first setup; no API key", "live_model_verified": False,
              "physical_user_hardware_verified": False}
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path, nargs=2)
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare, args.out)
    elif args.root and args.python:
        measure(args.root, args.python, args.out)
    else:
        parser.error("--root and --python, or --compare, are required")
