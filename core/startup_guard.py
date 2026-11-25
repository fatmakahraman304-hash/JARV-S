"""Stdlib-only preflight, before application modules can read or change data."""
from pathlib import Path
import sys


def ensure_safe_startup(root):
    root = Path(root)
    marker = root / ".aether-update.lock"
    # A pristine or read-only installation needs no new files at startup.
    if not marker.exists() and not (root / ".aether-update.guard").exists():
        return
    from core.app_updater import _update_guard
    with _update_guard(root):
        if not marker.exists():
            return
        with marker.open("rb") as handle:
            raw = handle.read(64)
        if raw == b"AETHER/1 checking":
            return  # No application files were written during this phase.
        if raw.startswith((b"AETHER/2 zip\n", b"AETHER/2 rollback\n")):
            raise RuntimeError(
                "Yarım kalan ZIP işlemi var. FRIDAY kapalıyken kurulum klasöründe "
                "aynı Python ile `python -m core.app_updater --recover` çalıştırın. "
                "Kurtarma doğrulandıktan sonra yeniden açın. "
                "Ayrıntılar: docs/guncelleme-tr.md")
        raise RuntimeError(
            "Güncelleme işleminin tamamlandığı doğrulanamadı. Kilidi silmeyin; "
            "kurulum ve yedekleri koruyup docs/guncelleme-tr.md kılavuzunu izleyin.")


def preflight(root):
    """Fail closed with a visible error for pythonw, without creating Qt."""
    try:
        ensure_safe_startup(root)
    except (OSError, RuntimeError) as exc:
        message = f"FRIDAY — Açılış durduruldu.\n{exc}"
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "FRIDAY", 0x10)
        raise SystemExit(1) from None
