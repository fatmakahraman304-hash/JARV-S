"""Stdlib-only preflight, before application modules can read or change data."""
from pathlib import Path
import os
import sys


def ensure_safe_startup(root):
    root = Path(root)
    marker = root / ".aether-update.lock"
    # A pristine or read-only installation needs no new files at startup.
    if not marker.exists() and not (root / ".aether-update.guard").exists():
        return
    from core.app_updater import _update_guard, _recover_transaction, _GIT_MARKER
    with _update_guard(root):
        if not marker.exists():
            return
        with marker.open("rb") as handle:
            raw = handle.read(64)
        if raw == b"AETHER/1 checking":
            return  # No application files were written during this phase.
        if raw.startswith((_GIT_MARKER, b"AETHER/2 zip\n", b"AETHER/2 rollback\n")):
            # Reuse the offline, hash-checked transaction recovery. It validates
            # all files/backups before restoring and refuses unexpected edits.
            try:
                with marker.open('rb') as handle:
                    transaction = handle.read(1024 * 1024 + 1)
                if len(transaction) > 1024 * 1024:
                    raise ValueError('Oversized recovery journal')
                _recover_transaction(root, marker, transaction, lambda message: None)
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError) as error:
                raise RuntimeError(
                    'Otomatik güncelleme kurtarması doğrulanamadı. Yerel dosya ve yedekleri koruyun; '
                    'kilidi silmeyin. FRIDAY kapalıyken `python -m core.app_updater --recover` '
                    'ile inceleyin. Ayrıntılar: docs/guncelleme-tr.md') from error
            return True
        raise RuntimeError(
            "Güncelleme işleminin tamamlandığı doğrulanamadı. Kilidi silmeyin; "
            "kurulum ve yedekleri koruyup docs/guncelleme-tr.md kılavuzunu izleyin.")


def preflight(root):
    """Fail closed with a visible error for pythonw, without creating Qt."""
    try:
        recovered = ensure_safe_startup(root)
        if recovered:
            # main.py and the guard may have been restored. Never continue with
            # Python code loaded from two different installation versions.
            if sys.stdout is not None:
                # A Windows console may still use cp1252. Recovery must not
                # fail just because Turkish status text cannot be encoded.
                print('FRIDAY_RECOVERY_VERIFIED: update recovery verified; restarting a clean process.', flush=True)
            original = getattr(sys, 'orig_argv', None)
            arguments = (sys.argv[1:] if getattr(sys, 'frozen', False)
                         else original[1:] if original else sys.argv)
            os.execv(sys.executable, [sys.executable, *arguments])
    except (OSError, RuntimeError) as exc:
        message = f"FRIDAY — Açılış durduruldu.\n{exc}"
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "FRIDAY", 0x10)
        raise SystemExit(1) from None
