"""Reentrant thread and OS-file lock for local JSON read/modify/write cycles."""
import errno
import os
from threading import RLock
import time


class FileRLock:
    def __init__(self, path, timeout=10.0):
        self.path = path
        self.timeout = timeout
        self.thread_lock = RLock()
        self._depth = 0
        self._handle = None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            if self._depth == 0:
                path = self.path()
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open("a+b")
                try:
                    deadline = time.monotonic() + self.timeout
                    while True:
                        handle.seek(0)
                        try:
                            if os.name == "nt":
                                import msvcrt
                                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                            else:
                                import fcntl
                                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except OSError as exc:
                            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                                raise
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    "Hafıza başka bir süreç tarafından kullanılıyor; kayıt uygulanmadı. "
                                    "Diğer işlemin bitmesini bekleyip yeniden deneyin.") from exc
                            time.sleep(.025)
                    # Windows permits locking beyond EOF. Initialize only
                    # after acquiring that region: another process may have
                    # locked byte zero after we opened the still-empty file.
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"\0")
                        handle.flush()
                    self._handle = handle
                except BaseException:
                    handle.close()
                    raise
            self._depth += 1
            return self
        except BaseException:
            self.thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self._depth -= 1
            if self._depth == 0:
                handle, self._handle = self._handle, None
                # Closing the descriptor releases the OS lock, also on crash.
                handle.close()
        finally:
            self.thread_lock.release()
        return False
