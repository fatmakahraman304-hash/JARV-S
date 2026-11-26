"""Finish an in-place source update after preparing the closed installation's venv."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from core import app_updater


def apply(target, progress=print):
    target = Path(target).resolve()
    if (Path(sys.prefix).resolve() != (target / '.venv').resolve()
            or sys.prefix == sys.base_prefix):
        raise RuntimeError("Mevcut FRIDAY kurulumunun .venv Python'u gerekiyor.")
    if not (target / 'main.py').is_file() or not (target / 'ui.py').is_file():
        raise RuntimeError("Mevcut FRIDAY kurulum dizini bulunamadı.")
    channel = json.loads((target / 'update_channel.json').read_text('utf-8'))
    if channel.get('repository') != app_updater.REPOSITORY:
        raise RuntimeError("Hedef FRIDAY güncelleme kanalı doğrulanamadı.")
    source = app_updater.ROOT / 'requirements.txt'
    manifest = source.read_text('utf-8')
    # The preparation check accepts package declarations only. No pip directives,
    # direct URLs, local archives, editable packages or requirement includes.
    from packaging.requirements import Requirement
    lines = []
    for line in manifest.splitlines():
        line = line.partition('#')[0].strip()
        if line:
            if Requirement(line).url:
                raise RuntimeError("Doğrudan paket URL'si bakım doğrulamasında kullanılamaz.")
            lines.append(line)
    with tempfile.TemporaryDirectory() as directory:
        requirements = Path(directory) / 'requirements.txt'
        requirements.write_text('\n'.join(lines), encoding='utf-8')
        report = Path(directory) / 'report.json'
        command = [sys.executable, '-m', 'pip', '--isolated', '--disable-pip-version-check']
        subprocess.run([*command, 'install', '--dry-run', '--no-index', '--only-binary=:all:',
                        '-r', str(requirements), '--report', str(report)], check=True, timeout=120)
        if json.loads(report.read_bytes()).get('install') != []:
            raise RuntimeError("Mevcut ortamın bağımlılıkları hazır değil.")
        subprocess.run([*command, 'check'], check=True, timeout=120)
    with app_updater._update_guard(target):
        if (target / '.aether-update.lock').exists():
            raise RuntimeError("Hedefte bekleyen güncelleme var. Önce kurtarma işlemini tamamlayın.")
        return app_updater._update_locked(target, progress, prepared_manifest=manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    try:
        changed, message = apply(args.target)
        print("Güncelleme doğrulandı. FRIDAY mevcut kurulumundan açılabilir." if changed else message)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'Güncelleme tamamlanamadı: {exc}\n')
