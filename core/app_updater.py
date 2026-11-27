"""User-triggered, pinned GitHub updates. No Qt or credentials in this module."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import zipfile

REPOSITORY = 'fatmakahraman304-hash/JARV-S'
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 150 * 1024 * 1024
DOWNLOAD_SECONDS = 120


def _git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=180,
                       stdin=subprocess.DEVNULL, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never'}, creationflags=0x08000000 if os.name == 'nt' else 0)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or 'Git işlemi başarısız.')
    return p.stdout.strip()


def _local_changes(root):
    """(real, eol_only): tracked files changed on disk.

    Windows Git reports files whose only difference is CRLF/LF as modified;
    those are not edits and must not block an update. Real edits are listed
    so the user sees which files they are."""
    if not _git(root, 'status', '--porcelain', '--untracked-files=no'):
        return [], False
    real = set()
    for staged in ((), ('--cached',)):
        # --name-only ignores whitespace options, so read the patch itself: a
        # file counts only if it still has a hunk once CR at line end is ignored.
        patch_text = _git(root, 'diff', *staged, '--ignore-cr-at-eol', '--no-renames', '--no-color', '--no-ext-diff', '-U0')
        current = None
        for line in patch_text.splitlines():
            if line.startswith('diff --git '):
                current = line.split(' b/', 1)[-1]
            elif current and (line.startswith('@@') or line.startswith('Binary files')
                              or line.startswith(('deleted file mode', 'new file mode', 'old mode'))):
                real.add(current)
    return sorted(real), not real


def _set_aside(root):
    """Keep real local edits in a named stash so the update can proceed."""
    label = f'aether-update {time.strftime("%Y-%m-%d %H:%M:%S")}'
    _git(root, 'stash', 'push', '-m', label)
    return label


def _restore(root, label):
    """Check a stash in a disposable worktree before touching the user's tree."""
    ref = None
    for line in _git(root, 'stash', 'list').splitlines():
        if label in line:
            ref = line.split(':', 1)[0]
            break
    if ref is None:
        return ''
    note = (f' Yerel değişiklikler "{label}" adıyla git stash listesinde saklı; '
            'yeniden uygulamadan önce gözden geçirin.')
    # A different process may have edited or staged files after the update
    # began. Never reset or overwrite those changes.
    if _git(root, 'status', '--porcelain', '--untracked-files=no'):
        return note
    try:
        with tempfile.TemporaryDirectory(prefix='friday-stash-check-') as directory:
            worktree = Path(directory) / 'checkout'
            _git(root, 'worktree', 'add', '--detach', str(worktree), 'HEAD')
            try:
                _git(worktree, 'stash', 'apply', ref)
            finally:
                _git(root, 'worktree', 'remove', '--force', str(worktree))
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return note
    # Recheck after the independent trial in case a user edited during it.
    if _git(root, 'status', '--porcelain', '--untracked-files=no'):
        return note
    try:
        _git(root, 'stash', 'pop', ref)
    except RuntimeError as exc:
        # Unexpected concurrent edits or a partial apply need manual recovery.
        # The caller retains the transaction marker and must not auto-restart.
        raise _RecoveryRequired(
            f'Yerel değişiklikler uygulanırken işlem durdu. {note}'
        ) from exc
    return ' Yerel değişikliklerin yeniden uygulandı.'


def _get(url, *, limit=LIMIT, progress=None):
    req = Request(url, headers={'User-Agent': 'Friday-Updater', 'Accept': 'application/vnd.github+json'})
    deadline = time.monotonic() + DOWNLOAD_SECONDS
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Güncelleme indirme süresi doldu. Yeniden deneyin.")
        try:
            with urlopen(req, timeout=min(15, remaining)) as response:
                data = bytearray()
                total = response.length
                next_report = 0.0
                while time.monotonic() < deadline:
                    # read1 returns after at most one underlying read. read(n)
                    # can wait indefinitely if the peer keeps trickling bytes.
                    chunk = response.read1(min(256 * 1024, limit + 1 - len(data)))
                    if not chunk:
                        if isinstance(response.length, int) and response.length > 0:
                            raise ConnectionError("Güncelleme indirmesi yarıda kesildi.")
                        return bytes(data)
                    data.extend(chunk)
                    if len(data) > limit:
                        raise RuntimeError('Güncelleme indirme sınırını aşıyor.')
                    if progress is not None:
                        now = time.monotonic()
                        if now >= next_report:
                            if isinstance(total, int) and total > 0:
                                size = f'%{min(100, len(data) * 100 // total)}'
                            else:
                                size = f'{len(data) / 1024:.0f} KiB'
                            progress(f'İndiriliyor · {size}')
                            next_report = now + 2
                raise RuntimeError("Güncelleme indirme süresi doldu. Yeniden deneyin.")
        except HTTPError as exc:
            # Retry temporary server failures, leaving authentication and quota
            # errors visible to the user without repeated requests.
            exc.close()
            if exc.code not in {502, 503, 504} or attempt == 2:
                raise
        except (URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, 'reason', exc)
            transient = isinstance(reason, (socket.gaierror, TimeoutError, ConnectionError))
            if not transient or attempt == 2:
                if isinstance(reason, socket.gaierror):
                    host = urlsplit(url).hostname
                    raise RuntimeError(
                        f"GitHub bağlantısı kurulamadı ({host}). "
                        "DNS veya proxy ayarlarını kontrol edip yeniden deneyin."
                    ) from exc
                raise
        time.sleep(attempt + 1)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _publisher_files(sha, progress):
    """A configured trust policy must succeed on both ZIP and Git installations."""
    from core.update_trust import trusted_key
    pem = trusted_key()
    if pem is None:
        return None
    from core.release_signatures import MAX_SIGNATURE, verify
    from tools.release_package import MAX_TOTAL, verified_files
    progress('Yayıncı imzası kontrol ediliyor…')
    prefix = f'https://github.com/{REPOSITORY}/releases/download/friday-source-{sha}/friday-source'
    envelope = _get(prefix + '.sig.json', limit=MAX_SIGNATURE)
    payload = _get(prefix + '.zip', limit=MAX_TOTAL, progress=progress)
    verify(payload, sha, envelope, pem)
    _, contents = verified_files(payload, sha)
    if 'gui/window.py' not in contents:
        raise RuntimeError('İmzalı paket FRIDAY arayüzünü içermiyor.')
    return {name: data for name, data in contents.items() if not _protected(name)}


def _protected(name):
    name = name.casefold()
    if name == '.gitignore':
        return False
    p = PurePosixPath(name)
    return (any(part.startswith('.') for part in p.parts)
            or p.parts[0] in {'venv', 'env', 'ENV', 'logs', 'downloads', 'screenshots', '__pycache__', 'uploads', 'reports'}
            or (p.parts[0] == 'config' and name not in {'config/__init__.py', 'config/aether.ico'})
            or p.suffix.partition('-')[0] in {'.db', '.sqlite', '.sqlite3'}
            or p.suffix in {'.log', '.pyc',
                                    '.jks', '.keystore', '.p12', '.pfx', '.key', '.pem'}
            or (p.parts[0] == 'memory' and (p.suffix != '.py' or p.parts[1:2] == ('tasks',)))
            or any(x in p.name.lower() for x in ('token', 'credential', 'client_secret')))


def _validate_relative(name):
    """Reject ambiguous paths on both POSIX and Windows before any write."""
    if not isinstance(name, str) or not name:
        raise RuntimeError("Geçersiz güncelleme yolu.")
    parts = name.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part.endswith((" ", "."))
                or any(c in '<>:"\\|?*' or ord(c) < 32 for c in part)
                or re.fullmatch(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])",
                                part.split(".")[0].casefold())):
            raise RuntimeError("Güvensiz güncelleme yolu: " + name)
    return name


def _validate_names(names):
    seen = set()
    for name in names:
        key = _validate_relative(name).casefold()
        if key in seen:
            raise RuntimeError("Çakışan güncelleme yolları.")
        seen.add(key)
    for key in seen:
        parts = key.split("/")
        if any("/".join(parts[:i]) in seen for i in range(1, len(parts))):
            raise RuntimeError("Dosya ve klasör yolu çakışıyor.")


def _archive(data):
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        names = []
        roots = set()
        for info in archive.infolist():
            raw = info.filename
            path = PurePosixPath(raw)
            if '\\' in raw or path.is_absolute() or '..' in path.parts or ':' in raw:
                raise RuntimeError('Güvensiz arşiv yolu.')
            _validate_relative(raw.rstrip('/') if info.is_dir() else raw)
            roots.add(path.parts[0])
            if len(roots) != 1:
                raise RuntimeError('Arşivde birden fazla kök klasör var.')
            if info.is_dir() or len(path.parts) < 2:
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError('Arşivde sembolik bağlantı var.')
            name = str(PurePosixPath(*path.parts[1:]))
            names.append(name)
            if _protected(name):
                continue
            total += info.file_size
            if total > LIMIT or name in files:
                raise RuntimeError('Geçersiz veya çok büyük güncelleme arşivi.')
            files[name] = archive.read(info)
    _validate_names(names)
    if not {'main.py', 'requirements.txt', 'gui/window.py'} <= files.keys():
        raise RuntimeError('Eksik FRIDAY arşivi.')
    return files


def _target(root, name):
    _validate_relative(name)
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise RuntimeError('Güncelleme yolu uygulama dışına çıkıyor.')
    return path


class _RecoveryRequired(RuntimeError):
    """Keep the transaction marker until the saved copies can be restored."""


def _replace_bytes(path, data):
    # A private sibling directory keeps the replacement on the same volume and
    # cannot collide with a user's files, even after an interrupted update.
    with tempfile.TemporaryDirectory(dir=path.parent) as staging:
        tmp = Path(staging) / path.name
        tmp.write_bytes(data)
        if path.suffix == ".py" and path.is_file():
            # CPython validates timestamp-based bytecode using whole seconds
            # and file size. A same-size edit in one second can run old code.
            old = path.stat()
            current = tmp.stat()
            if old.st_size == current.st_size and int(old.st_mtime) == int(current.st_mtime):
                os.utime(tmp, (current.st_atime, int(old.st_mtime) + 1))
        os.replace(tmp, path)


_GIT_MARKER = b'AETHER/3 git\n'
_ZIP_MARKER = b'AETHER/2 zip\n'
_ROLLBACK_MARKER = b'AETHER/2 rollback\n'


def _file_digest(path):
    return _hash(path.read_bytes()) if path.exists() else None


def _backup_directory(root, name):
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{8}-[0-9]+", name):
        raise _RecoveryRequired("ZIP yedek kaydı geçersiz.")
    backup = _target(root, ".aether-backups/" + name)
    if backup.parent.is_symlink() or not backup.is_dir():
        raise _RecoveryRequired("ZIP yedek klasörü doğrulanamadı.")
    return backup


def _recover_transaction(root, marker, raw, progress):
    if not raw.startswith(_GIT_MARKER):
        return _recover_zip(root, marker, raw, progress)
    record = json.loads(raw[len(_GIT_MARKER):])
    before, after, backup = record['before'], record['after'], record['backup']
    if (not re.fullmatch('[0-9a-f]{40}', before) or not re.fullmatch('[0-9a-f]{40}', after)
            or not re.fullmatch(r'aether-backup/[0-9]+', backup) or before == after):
        raise _RecoveryRequired('Git işlem kaydı geçersiz.')
    if (_git(root, 'symbolic-ref', '--short', 'HEAD') != record['branch']
            or _git(root, 'rev-parse', 'refs/heads/' + backup) != before
            or _git(root, 'rev-parse', 'HEAD') != after
            or _git(root, 'status', '--porcelain', '--untracked-files=no')):
        raise _RecoveryRequired('Git işlemi veya yerel dosyalar doğrulanamadı; işlem kaydı korunuyor.')
    for state in ('index.lock', 'MERGE_HEAD', 'rebase-apply', 'rebase-merge', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'):
        if (root / _git(root, 'rev-parse', '--git-path', state)).exists():
            raise _RecoveryRequired('Devam eden Git işlemi var; işlem kaydı korunuyor.')
    progress('Kurulan Git sürümü ve geri dönüş noktası doğrulandı.')
    marker.unlink()
    return True, 'Kurulan Git sürümü doğrulandı. FRIDAY yeniden başlatılacak.'


def _recover_zip(root, lock, raw, progress):
    """Resolve a stopped ZIP transaction offline. Leave conflicts and backups intact."""
    journal = json.loads(raw.split(b"\n", 1)[1])
    backup = _backup_directory(root, journal["backup"])
    rollback = raw.startswith(_ROLLBACK_MARKER)
    manifest = _file_digest(_target(root, ".aether-update.json"))
    committed = not rollback and manifest == journal["new_manifest"]
    if manifest not in (journal["old_manifest"], journal["new_manifest"]):
        raise _RecoveryRequired("Yerel sürüm kaydı değişmiş. Kurtarma durduruldu.")
    before, after = journal["before"], journal["after"]
    _validate_names(before)
    _validate_names(after)
    _validate_names(set(before) | set(after))
    if any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
           for digest in (*before.values(), *after.values())):
        raise _RecoveryRequired("ZIP kurtarma kaydında geçersiz dosya özeti.")
    previous_manifest = None
    if rollback and journal["old_manifest"] is not None:
        previous_manifest = _target(backup, ".previous-manifest").read_bytes()
        if _hash(previous_manifest) != journal["old_manifest"]:
            raise _RecoveryRequired("Önceki sürüm kaydının yedeği doğrulanamadı.")
    restore = []
    for rel in sorted(before.keys() | after.keys()):
        path_name = PurePosixPath(rel)
        if (not path_name.parts or str(path_name) != rel or path_name.is_absolute()
                or ".." in path_name.parts or ":" in rel or chr(92) in rel or _protected(rel)):
            raise _RecoveryRequired("ZIP kurtarma kaydında geçersiz yol.")
        target = _target(root, rel)
        if target.resolve() != root.resolve() / rel:
            raise _RecoveryRequired(f"Kurtarma yolu değişmiş: {rel}")
        current = _file_digest(target)
        expected = after.get(rel) if committed else before.get(rel)
        if current == expected:
            continue
        if committed or current != after.get(rel):
            raise _RecoveryRequired(f"Dosya beklenmeyen biçimde değişmiş: {rel}. Yerel içerik korunuyor.")
        if expected is not None and _file_digest(_target(backup, rel)) != expected:
            raise _RecoveryRequired(f"Yedek doğrulanamadı: {rel}")
        restore.append((rel, expected))
    progress("Kesilen ZIP güncellemesi doğrulanıyor…" if committed else "Önceki ZIP kurulumu geri yükleniyor…")
    for rel, digest in restore:
        target = _target(root, rel)
        if _file_digest(target) != after.get(rel):
            raise _RecoveryRequired(f"Kurtarma sırasında dosya değişti: {rel}")
        if digest is None:
            target.unlink()
        else:
            data = _target(backup, rel).read_bytes()
            if _hash(data) != digest:
                raise _RecoveryRequired(f"Yedek değişti: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_bytes(target, data)
        if _file_digest(target) != digest:
            raise _RecoveryRequired(f"Geri yüklenen dosya doğrulanamadı: {rel}")
    if rollback:
        state_path = _target(root, ".aether-update.json")
        if previous_manifest is None:
            state_path.unlink(missing_ok=True)
        else:
            _replace_bytes(state_path, previous_manifest)
        if _file_digest(state_path) != journal["old_manifest"]:
            raise _RecoveryRequired("Önceki sürüm kaydı geri yüklenemedi.")
    lock.unlink()
    return (True, "Kurulan ZIP sürümü doğrulandı. FRIDAY yeniden başlatılacak." if committed
            else "Kesilen ZIP güncellemesi geri alındı. Önceki sürüm doğrulandı. FRIDAY yeniden başlatılacak.")


def rollback_zip(root=ROOT, progress=print):
    """Explicit offline downgrade of the last intact ZIP update, with the app closed."""
    root = Path(root)
    with _update_guard(root):
        marker = _target(root, ".aether-update.lock")
        if (root / ".git").exists() or marker.exists():
            raise _RecoveryRequired("ZIP geri dönüşü için kurulumu ve bekleyen kurtarmayı kontrol edin.")
        state_path = _target(root, ".aether-update.json")
        state = json.loads(state_path.read_bytes())
        if not state.get("backup"):
            raise _RecoveryRequired("Bu sürüm doğrulanabilir geri dönüş kaydı içermiyor.")
        backup = _backup_directory(root, state["backup"])
        raw = _target(backup, ".rollback.json").read_bytes()
        journal = json.loads(raw)
        if journal.get("backup") != state["backup"] or _hash(state_path.read_bytes()) != journal.get("new_manifest"):
            raise _RecoveryRequired("Geri dönüş kaydı kurulu sürümle eşleşmiyor.")
        originals = json.dumps(journal["before"], sort_keys=True).encode("utf-8")
        if (_hash(originals) != state.get("originals_digest") or journal["after"] != state["files"]
                or journal["old_manifest"] != state.get("old_manifest")):
            raise _RecoveryRequired("Geri dönüş dosya listesi kurulu sürümle eşleşmiyor.")
        if "main.py" not in journal["before"]:
            raise _RecoveryRequired("Yedekte önceki FRIDAY başlangıç dosyası yok.")
        for rel in journal["before"].keys() | journal["after"].keys():
            if _file_digest(_target(root, rel)) != journal["after"].get(rel):
                raise _RecoveryRequired(f"Yerel değişiklik korunuyor: {rel}")
        transaction = _ROLLBACK_MARKER + raw
        _replace_bytes(marker, transaction)
        return _recover_zip(root, marker, transaction, progress)


def _zip_state(root):
    """Use a packaged source baseline before the first in-place update.

    This local inventory detects accidental edits/collisions; it is not
    publisher authentication. A completed update's own journal takes priority.
    Legacy GitHub archives with neither inventory retain their old behaviour.
    """
    state = _target(root, ".aether-update.json")
    if state.exists():
        return json.loads(state.read_text("utf-8"))
    candidate = _target(root, "friday-release.json")
    if not candidate.exists():
        return {}
    try:
        with candidate.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("inventory size")
        manifest = json.loads(raw)
        sha = manifest["source_commit"]
        entries = manifest["files"]
        if (manifest.get("schema") != 1 or manifest.get("kind") != "source-candidate"
                or not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha)
                or not isinstance(entries, dict) or len(entries) > 2000
                or not {"main.py", "ui.py", "requirements.txt", "gui/window.py"} <= entries.keys()):
            raise ValueError("inventory identity")
        _validate_names(entries)
        files = {}
        for name, entry in entries.items():
            digest = entry["sha256"]
            if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
                raise ValueError("inventory digest")
            if not _protected(name):
                files[name] = digest
        return {"sha": sha, "files": files}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        raise RuntimeError("Kaynak paketinin başlangıç dosya listesi doğrulanamadı. Yerel dosyalar korunuyor.") from exc


def _apply_zip(root, files, sha, branch, progress=lambda message: None, *, marker=None):
    """Back up before writing; restore every changed/deleted file on failure."""
    state_path = root / '.aether-update.json'
    old = _zip_state(root)
    previous = old.get('files', {})
    _validate_names(previous)
    _validate_names(files)
    if any(_protected(name) for name in files):
        raise RuntimeError('Korunan dosya güncellenemez.')
    _validate_names(set(files) | set(previous))
    for name, digest in previous.items():
        if _protected(name):
            continue
        path = _target(root, name)
        if path.exists() and _hash(path.read_bytes()) != digest:
            raise RuntimeError(f'Yerel değişiklik korunuyor: {name}. Güncelleme uygulanmadı.')
    if old:
        for name in files.keys() - previous.keys():
            path = _target(root, name)
            if path.exists() and (not path.is_file() or _hash(path.read_bytes()) != _hash(files[name])):
                raise RuntimeError(f'Yeni sürümdeki dosya yerel dosyayla çakışıyor: {name}. Güncelleme uygulanmadı.')
    names = set(files) | {n for n in previous if not _protected(n)}
    backup = root / '.aether-backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + sha[:8] + '-' + str(time.time_ns()))
    backup.mkdir(parents=True, exist_ok=False)
    existed = set()
    for name in names:
        path = _target(root, name)
        if path.exists():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            existed.add(name)
    state = {'sha': sha, 'branch': branch, 'files': {n: _hash(b) for n, b in files.items()}}
    if marker is not None:
        originals = {n: _file_digest(backup / n) for n in existed}
        state["backup"] = backup.name
        state["originals_digest"] = _hash(json.dumps(originals, sort_keys=True).encode("utf-8"))
        state["old_manifest"] = _file_digest(state_path)
    state_bytes = json.dumps(state).encode('utf-8')
    if marker is not None:
        journal = {"backup": backup.name, "before": originals,
                   "after": state["files"], "old_manifest": state["old_manifest"],
                   "new_manifest": _hash(state_bytes)}
        raw = json.dumps(journal).encode("utf-8")
        if state_path.exists():
            _replace_bytes(backup / ".previous-manifest", state_path.read_bytes())
        _replace_bytes(backup / ".rollback.json", raw)
        _replace_bytes(marker, _ZIP_MARKER + raw)
    touched = []
    try:
        progress('Yeni kod uygulanıyor…')
        for name in sorted(names):
            path = _target(root, name)
            if name in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                _replace_bytes(path, files[name])
            else:
                path.unlink(missing_ok=True)
            touched.append(name)
        progress('Kurulan dosyalar doğrulanıyor…')
        for name, digest in state['files'].items():
            if _hash(_target(root, name).read_bytes()) != digest:
                raise RuntimeError(f'Yazılan dosya doğrulanamadı: {name}')
        _replace_bytes(state_path, state_bytes)
    except Exception:
        if marker is not None:
            # Use the durable journal rather than the in-memory touched list.
            # A replacement can succeed immediately before an exception.
            try:
                _recover_zip(root, marker, marker.read_bytes(), progress)
            except Exception as exc:
                raise _RecoveryRequired("Otomatik kurtarma tamamlanamadı; işlem kaydı ve yedekler korunuyor.") from exc
            raise
        failed = []
        for name in reversed(touched):
            path = root / name
            try:
                if name in existed:
                    shutil.copy2(backup / name, path)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                failed.append(name)
        if failed:
            raise _RecoveryRequired(f'Geri alma tamamlanamadı. Yedek: {backup}. Dosyalar: {", ".join(failed[:5])}')
        # The old manifest remains intact until the final atomic replace.
        raise
    return backup


def _needs_dependency_install(old, new):
    """Allow removal of ordinary package declarations, retaining pip directives verbatim."""
    def declarations(content):
        # pip joins continued lines before removing comments. Keep those
        # manifests conservative, since the position of a comment matters.
        lines = content.splitlines()
        if not any(line.rstrip().endswith('\\') for line in lines):
            lines = [re.split(r'\s+#', line, maxsplit=1)[0] for line in lines]
        return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith('#')]

    before, after = declarations(old), declarations(new)
    if before == after:
        return False
    # Options, included files and continued lines can affect neighbouring entries.
    # Only apply the subset rule to independent package declarations.
    if any(not re.match(r'^[A-Za-z0-9]', line) or line.endswith('\\')
           for line in before + after):
        return True
    return not set(after).issubset(before)


@contextmanager
def _update_guard(root):
    """The kernel releases this lock even if Windows terminates the process."""
    with (root / '.aether-update.guard').open('a+b') as handle:
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Başka bir güncelleme çalışıyor veya güncelleme kilidi alınamadı.') from exc
        yield


def update(root=ROOT, progress=lambda message: None):
    root = Path(root)
    if getattr(sys, 'frozen', False):
        raise RuntimeError('Bu paketli sürüm için kurulum paketi gerekir; kaynak güncellemesi uygulanmadı.')
    with _update_guard(root):
        return _update_locked(root, progress)


def _update_locked(root, progress, *, prepared_manifest=None):
    lock = root / '.aether-update.lock'
    checking = b'AETHER/1 checking'
    try:
        with lock.open('xb') as marker:
            marker.write(checking)
    except FileExistsError:
        raw = lock.read_bytes()
        if raw.startswith((_GIT_MARKER, _ZIP_MARKER, _ROLLBACK_MARKER)):
            return _recover_transaction(root, lock, raw, progress)
        if raw != checking:
            raise RuntimeError('Başka bir güncelleme veya yarım kalan kurulum var. '
                               'Güncelleme kilidi ve yedekler korunuyor. docs/guncelleme-tr.md dosyasına bakın.') from None
        progress('Kesilen kontrolün ardından yeniden deneniyor…')
    release_marker = True
    try:
        is_git = (root / '.git').exists()
        state = {} if is_git else _zip_state(root)
        eol_only, real_changes = False, []
        if is_git:
            real_changes, eol_only = _local_changes(root)
            branch = _git(root, 'symbolic-ref', '--short', 'HEAD')
            current = _git(root, 'rev-parse', 'HEAD')
        else:
            channel = json.loads((root / 'update_channel.json').read_text('utf-8'))
            branch = state.get('branch', channel['branch'])
            current = state.get('sha')
        progress(f'GitHub kontrol ediliyor · {branch}')
        if is_git:
            # Fetch the exact tracked branch directly from the official repository.
            _git(root, 'fetch', '--no-tags', f'https://github.com/{REPOSITORY}.git',
                 f'refs/heads/{branch}')
            sha = _git(root, 'rev-parse', 'FETCH_HEAD^{commit}')
        else:
            commit = json.loads(_get(f'https://api.github.com/repos/{REPOSITORY}/commits/{quote(branch, safe="")}'))
            sha = commit['sha']
        if not re.fullmatch('[0-9a-f]{40}', sha):
            raise RuntimeError('Geçersiz GitHub sürüm kimliği.')
        if current == sha:
            return False, f'FRIDAY güncel · {sha[:8]}'

        signed_files = _publisher_files(sha, progress)
        if is_git:
            if int(_git(root, 'rev-list', '--count', f'{sha}..{current}')):
                raise RuntimeError('Bu dalda GitHub sürümünde bulunmayan yerel commit var. Güncelleme durduruldu.')
            new_req = _git(root, 'show', f'{sha}:requirements.txt')
        else:
            progress('Yeni sürüm indiriliyor…')
            files = signed_files if signed_files is not None else _archive(
                _get(f'https://codeload.github.com/{REPOSITORY}/zip/{sha}', progress=progress))
            new_req = files['requirements.txt'].decode('utf-8')
        # Do not replace dependencies while Qt/audio DLLs are in use.
        old_req = (root / 'requirements.txt').read_text('utf-8')
        if prepared_manifest is not None and prepared_manifest.strip() != new_req.replace('\r\n', '\n').strip():
            raise RuntimeError('Hazırlanan paket ile güncel sürümün bağımlılıkları farklı.')
        if prepared_manifest is None and _needs_dependency_install(old_req, new_req):
            raise RuntimeError('Bu sürüm yeni bağımlılıklar gerektiriyor. FRIDAY’ı kapatıp yeni sürümün setup.py kurulumunu çalıştırın. Mevcut sürüm korunuyor.')
        if is_git:
            _replace_bytes(lock, b'AETHER/1 applying')
        progress('Yedek alınıyor…')
        note = ''
        if is_git:
            if (_git(root, 'symbolic-ref', '--short', 'HEAD') != branch
                    or _git(root, 'rev-parse', 'HEAD') != current
                    or _local_changes(root) != (real_changes, eol_only)):
                raise RuntimeError('Kontrol sırasında yerel kod değişti; güncelleme durduruldu.')
            backup = f'aether-backup/{time.time_ns()}'
            _git(root, 'branch', backup, current)
            clean_git = not real_changes and not eol_only
            if clean_git:
                record = {'branch': branch, 'before': current, 'after': sha, 'backup': backup}
                _replace_bytes(lock, _GIT_MARKER + json.dumps(record).encode('utf-8'))
                release_marker = False
            label = None
            if real_changes:
                shown = ', '.join(real_changes[:5]) + (' …' if len(real_changes) > 5 else '')
                progress(f'Yerel değişiklikler kenara alınıyor: {shown}')
                label = _set_aside(root)
            progress('Yeni kod uygulanıyor…')
            try:
                if eol_only:
                    # Normalize tracked files before the fast-forward. Git merge
                    # then checks for collisions with personal untracked files.
                    _git(root, 'restore', '--source=HEAD', '--staged', '--worktree', '--', '.')
                _git(root, 'merge', '--ff-only', '--no-overwrite-ignore', sha)
            except RuntimeError:
                if clean_git and _git(root, 'rev-parse', 'HEAD') == current and not _git(
                        root, 'status', '--porcelain', '--untracked-files=no'):
                    release_marker = True
                if label:
                    _restore(root, label)
                raise
            progress('Kurulan commit doğrulanıyor…')
            if _git(root, 'rev-parse', 'HEAD') != sha:
                raise RuntimeError('Güncelleme sonucu doğrulanamadı.')
            release_marker = True
            if label:
                note = _restore(root, label)
        else:
            _apply_zip(root, files, sha, branch, progress, marker=lock)
        return True, f'Güncellendi · {sha[:8]}. FRIDAY otomatik yeniden başlatılıyor.{note}'
    except _RecoveryRequired:
        release_marker = False
        raise
    finally:
        if release_marker:
            lock.unlink(missing_ok=True)


def check(root=ROOT) -> dict:
    """Read-only: is there a newer FRIDAY on GitHub, and what changed?
    {"newer": bool, "sha": str, "current": str, "changes": [first lines of the new commits]}"""
    root = Path(root)
    if (root / '.git').exists():
        branch = _git(root, 'symbolic-ref', '--short', 'HEAD')
        current = _git(root, 'rev-parse', 'HEAD')
        _git(root, 'fetch', '--no-tags', f'https://github.com/{REPOSITORY}.git', f'refs/heads/{branch}')
        sha = _git(root, 'rev-parse', 'FETCH_HEAD^{commit}')
        ahead, behind = map(int, _git(root, 'rev-list', '--left-right', '--count', f'{current}...{sha}').split())
        changes = []
        if behind and not ahead:
            changes = _git(root, 'log', '-15', '--format=%s', f'{current}..{sha}').splitlines()
        return {"newer": bool(behind and not ahead), "sha": sha, "current": current, "changes": changes,
                "branch": branch, "ahead": ahead, "behind": behind}
    state = _zip_state(root)
    channel = json.loads((root / 'update_channel.json').read_text('utf-8'))
    branch = state.get('branch', channel['branch'])
    commit = json.loads(_get(f'https://api.github.com/repos/{REPOSITORY}/commits/{quote(branch, safe="")}'))
    sha = commit['sha']
    return {"newer": sha != state.get('sha'), "sha": sha, "current": state.get('sha') or "",
            "changes": str(commit.get('commit', {}).get('message', '')).splitlines()[:1] if sha != state.get('sha') else [],
            "branch": branch}

if __name__ == "__main__":
    if sys.stdout is not None and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    import argparse
    parser = argparse.ArgumentParser(description="Kesilen FRIDAY güncellemesini çevrimdışı kurtar.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--recover", action="store_true")
    action.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    try:
        if args.rollback:
            rollback_zip()
            print("Önceki ZIP sürümü geri yüklendi ve doğrulandı.")
            sys.exit(0)
        with _update_guard(ROOT):
            marker = ROOT / ".aether-update.lock"
            raw = marker.read_bytes() if marker.exists() else b""
            if raw.startswith((_GIT_MARKER, _ZIP_MARKER, _ROLLBACK_MARKER)):
                _recover_transaction(ROOT, marker, raw, print)
                print("Kurtarma doğrulandı. FRIDAY'ı açabilirsiniz.")
            elif marker.exists():
                sys.exit("Bu kilit otomatik ZIP kurtarmasına uygun değil. Güncelleme kılavuzuna bakın.")
            else:
                print("Bekleyen ZIP kurtarması yok. Bekleyen Git kurtarması yok.")
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"Kurtarma tamamlanamadı: {exc}")
