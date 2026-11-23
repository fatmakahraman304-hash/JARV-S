"""Diagnose windows that flash briefly while MAYK is running.

Windows only. This does not open an extra GUI or capture screen contents.
Qt widgets are observed on the Qt thread; native console windows are observed
via SetWinEventHook in a daemon thread. We record only MAYK windows, MAYK child
process windows, or a brief Windows console seen while MAYK is on screen.

No clipboard content, passwords, full process command lines or unrelated
window titles are ever recorded. Diagnostics are local and size capped.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time

_MAX_BYTES = 96_000
_MAX_DURATION = 3.0
_MIN_DURATION = .035
_LATEST = 30
_monitor = None
_guard = threading.Lock()


def trace_path() -> Path:
    from core.logbook import log_dir
    return log_dir() / "window_flash.log"


def recent(limit: int = 10) -> list[str]:
    """A local-only record the user can read after a fleeting popup."""
    try:
        lines = trace_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-max(1, min(_LATEST, int(limit))):]


class FlashRecorder:
    def __init__(self, notify=None, clock=None, destination: Path | None = None):
        self.notify = notify
        self.clock = clock or time.monotonic
        self.destination = destination
        self._shown: dict[object, tuple[float, str]] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def show(self, key: object, source: str) -> None:
        with self._lock:
            self._shown[key] = (self.clock(), str(source)[:130])
            # No unbounded map if an external application never sends HIDE.
            if len(self._shown) > 240:
                self._shown.clear()

    def hide(self, key: object) -> str | None:
        with self._lock:
            started = self._shown.pop(key, None)
            if not started:
                return None
            now = self.clock()
            duration = max(0, now - started[0])
            if not _MIN_DURATION <= duration <= _MAX_DURATION:
                return None
            label = started[1]
            if now - self._last.get(label, float("-inf")) < 12:
                return None
            self._last[label] = now
        message = f"Anlık pencere ({duration:.1f} sn): {label}"
        self._write(message)
        return message

    def _write(self, message: str) -> None:
        try:
            dest = self.destination or trace_path()
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_file() and dest.stat().st_size > _MAX_BYTES:
                # A bounded local record, not a continuously growing trace.
                lines = dest.read_text(encoding="utf-8", errors="replace").splitlines()
                dest.write_text("\n".join(lines[-_LATEST:]) + "\n",
                                encoding="utf-8")
            with dest.open("a", encoding="utf-8") as stream:
                stream.write(time.strftime("%Y-%m-%d %H:%M:%S") +
                             " " + message + "\n")
        except OSError:
            pass
        try:
            from core import logbook
            logbook.write("PENCERE İZİ: " + message)
        except Exception:
            pass
        if self.notify:
            try:
                self.notify("SYS: " + message)
            except Exception:
                pass


def start(app, window, notify=None):
    """Install non-invasive diagnostics after the QApplication exists.

    Called exactly once by main.py. On non-Windows platforms it is a no-op.
    The observer never creates or raises another window.
    """
    global _monitor
    if sys.platform != "win32":
        return None
    if _monitor is not None:
        return _monitor
    from PyQt6.QtCore import QObject, QEvent, QTimer
    from PyQt6.QtWidgets import QWidget

    recorder = FlashRecorder(notify=notify)

    class QtWindows(QObject):
        def eventFilter(self, obj, event):
            try:
                if not isinstance(obj, QWidget) or obj is window:
                    return False
                kind = event.type()
                if kind not in (QEvent.Type.Show, QEvent.Type.Hide):
                    return False
                widget_type = type(obj).__name__
                # Track top-level popups and MAYK overlays, never ordinary
                # labels or controls that repaint on each frame.
                if not (obj.isWindow() or any(
                        word in widget_type.lower()
                        for word in ("overlay", "popup", "dialog", "banner"))):
                    return False
                if not window.isVisible() or window.isMinimized():
                    return False
                label = "MAYK paneli: " + widget_type
                key = ("qt", id(obj))
                if kind == QEvent.Type.Show:
                    recorder.show(key, label)
                else:
                    recorder.hide(key)
            except (RuntimeError, AttributeError, TypeError):
                pass
            return False

    monitor = QtWindows(app)
    _monitor = (monitor, recorder)
    app.installEventFilter(monitor)

    def begin_native():
        try:
            _start_native(recorder, int(window.winId()))
        except Exception as exc:
            # Missing Windows APIs must never prevent MAYK from opening.
            from core import logbook
            logbook.write("PENCERE İZİ: Windows izleyici açılamadı: " +
                          type(exc).__name__)

    # Wait until startup's expected Qt setup windows have settled.
    QTimer.singleShot(2500, begin_native)
    return _monitor


def _start_native(recorder: FlashRecorder, main_hwnd: int) -> None:
    """WinEvent hooks see a console even if it is visible only for 100 ms."""
    import ctypes
    from ctypes import wintypes
    import psutil

    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
    )
    user32.SetWinEventHook.argtypes = (
        wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, callback_type,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
    )
    user32.SetWinEventHook.restype = wintypes.HANDLE
    user32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetClassNameW.argtypes = (
        wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

    def work():
        current_pid = os.getpid()
        pending = {}

        def window_event(handle, event, hwnd, object_id, child_id, thread_id, tick):
            try:
                if object_id != 0 or child_id != 0 or not hwnd:
                    return
                # Not active while minimized; no unrelated desktop monitoring.
                if (not user32.IsWindowVisible(main_hwnd) or
                        user32.IsIconic(main_hwnd)):
                    return
                key = int(hwnd)
                if event == 0x8002:   # EVENT_OBJECT_SHOW
                    cls_buf = ctypes.create_unicode_buffer(100)
                    user32.GetClassNameW(hwnd, cls_buf, len(cls_buf))
                    class_name = cls_buf.value
                    pid_out = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
                    pid = int(pid_out.value)
                    if not pid or pid == current_pid:
                        return   # Qt widgets already handled on Qt thread.
                    is_console = class_name == "ConsoleWindowClass"
                    try:
                        process = psutil.Process(pid)
                        name = process.name()
                        from_mayk = any(p.pid == current_pid
                                        for p in process.parents())
                    except (psutil.NoSuchProcess, psutil.AccessDenied,
                            psutil.ZombieProcess):
                        name, from_mayk = f"PID {pid}", False
                    if not (is_console or from_mayk):
                        return
                    source = ("MAYK alt işlemi" if from_mayk else
                              "Windows konsolu (kaynağı kesin değil)")
                    label = f"{source}: {name} [{class_name}]"
                    pending[key] = label
                    recorder.show(("win", key), label)
                elif event in (0x8001, 0x8003):  # DESTROY or HIDE
                    if key in pending:
                        pending.pop(key, None)
                        recorder.hide(("win", key))
            except Exception:
                # WinEvent callbacks must never crash the application's Qt loop.
                return

        callback = callback_type(window_event)  # keep alive for the hook's life
        hook = user32.SetWinEventHook(
            0x8001, 0x8003, None, callback, 0, 0,
            0x0000 | 0x0002,  # OUTOFCONTEXT | SKIPOWNPROCESS
        )
        if not hook:
            try:
                from core import logbook
                logbook.write("PENCERE İZİ: WinEventHook oluşturulamadı.")
            except Exception:
                pass
            return
        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWinEvent(hook)

    threading.Thread(target=work, name="mayk-flash-diagnostics",
                     daemon=True).start()
