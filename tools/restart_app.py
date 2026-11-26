"""Wait for the old process to release audio/Qt resources before relaunching."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil

_READY_GRACE = 1.0  # Observe early shutdown after the Qt-ready receipt.


def restart(pid, project):
    try:
        psutil.Process(pid).wait(timeout=120)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        print('Restart cancelled: original FRIDAY did not exit.', flush=True)
        return 1
    with tempfile.TemporaryDirectory(prefix="aether-restart-") as directory:
        receipt = Path(directory) / "hud-ready"
        try:
            child = subprocess.Popen([sys.executable, str(Path(project) / 'main.py')], cwd=project,
                                     env=dict(os.environ, AETHER_RESTART_RECEIPT=str(receipt)),
                                     stdout=sys.stdout, stderr=sys.stderr)
        except OSError as exc:
            print(f"FRIDAY başlatılamadı: {exc}", flush=True)
            return 1
        deadline = time.monotonic() + 90
        ready_since = None
        while time.monotonic() < deadline:
            code = child.poll()
            if code is not None:
                print(f"FRIDAY yeniden açılırken kapandı (kod {code}). Açılış doğrulanamadı. "
                      "ZIP kurulumunda geri dönüş için docs/guncelleme-tr.md dosyasına bakın.", flush=True)
                return 1
            if receipt.is_file():
                now = time.monotonic()
                if ready_since is None:
                    ready_since = now
                if now - ready_since >= _READY_GRACE:
                    print("Yeni FRIDAY penceresinin Qt olay döngüsü açıldı; süreç ilk açılış kontrolünde açık kaldı.",
                          flush=True)
                    return 0
            else:
                ready_since = None
            time.sleep(0.1)
        print("FRIDAY penceresinin açılışı 90 saniyede doğrulanamadı. Süreç çalışmaya devam edebilir.", flush=True)
        return 2


if __name__ == '__main__':
    if sys.stdout is not None and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(restart(int(sys.argv[1]), sys.argv[2]))
