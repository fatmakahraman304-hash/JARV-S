"""Wait for the old process to release audio/Qt resources before relaunching."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil


def restart(pid, project):
    try:
        psutil.Process(pid).wait(timeout=120)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        print('Restart cancelled: original AETHER did not exit.', flush=True)
        return 1
    with tempfile.TemporaryDirectory(prefix="aether-restart-") as directory:
        receipt = Path(directory) / "hud-ready"
        try:
            child = subprocess.Popen([sys.executable, str(Path(project) / 'main.py')], cwd=project,
                                     env=dict(os.environ, AETHER_RESTART_RECEIPT=str(receipt)),
                                     stdout=sys.stdout, stderr=sys.stderr)
        except OSError as exc:
            print(f"AETHER başlatılamadı: {exc}", flush=True)
            return 1
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if receipt.is_file():
                print("Yeni AETHER penceresinin Qt olay döngüsü açıldı.", flush=True)
                return 0
            code = child.poll()
            if code is not None:
                print(f"AETHER pencereyi açmadan kapandı (kod {code}). "
                      "ZIP kurulumunda geri dönüş için docs/guncelleme-tr.md dosyasına bakın.", flush=True)
                return 1
            time.sleep(0.1)
        print("AETHER penceresinin açılışı 90 saniyede doğrulanamadı. Süreç çalışmaya devam edebilir.", flush=True)
        return 2


if __name__ == '__main__':
    if sys.stdout is not None and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(restart(int(sys.argv[1]), sys.argv[2]))
