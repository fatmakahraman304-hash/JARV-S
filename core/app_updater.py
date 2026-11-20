"""User-triggered, pinned GitHub updates. No Qt or credentials in this module."""
from __future__ import annotations

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
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import zipfile

REPOSITORY = 'fatmakahraman304-hash/JARV-S'
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 150 * 1024 * 1024


def _git(root, *args):
    p = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=180, creationflags=0x08000000 if os.name == 'nt' else 0)
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
    label = f'jarvis-update {time.strftime("%Y-%m-%d %H:%M:%S")}'
    _git(root, 'stash', 'push', '-m', label)
    return label


def _restore(root, label):
    """Re-apply stashed edits; on conflict leave them stashed. Returns a note."""
    ref = None
    for line in _git(root, 'stash', 'list').splitlines():
        if label in line:
            ref = line.split(':', 1)[0]
            break
    if ref is None:
        return ''
    try:
        _git(root, 'stash', 'pop', ref)
        return ' Yerel değişikliklerin yeniden uygulandı.'
    except RuntimeError:
        try:
            _git(root, 'reset', '--hard', 'HEAD')
        except RuntimeError:
            pass
        return (f' Yerel değişikliklerin yeni sürümle çakıştı; kaybolmadı, "{label}" adıyla '
                'git stash listesinde saklı.')


def _get(url):
    req = Request(url, headers={'User-Agent': 'Jarvis-Updater', 'Accept': 'application/vnd.github+json'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=45) as response:
                data = response.read(LIMIT + 1)
            break
        except HTTPError as exc:
            # Retry temporary server failures, leaving authentication and quota
            # errors visible to the user without repeated requests.
            if exc.code not in {502, 503, 504} or attempt == 2:
                raise
            exc.close()
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
    if len(data) > LIMIT:
        raise RuntimeError('Güncelleme indirme sınırını aşıyor.')
    return data


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _protected(name):
    if name == '.gitignore':
        return False
    p = PurePosixPath(name)
    return (any(part.startswith('.') for part in p.parts)
            or p.parts[0] in {'venv', 'env', 'ENV', 'logs', 'downloads', 'screenshots', '__pycache__', 'uploads', 'reports'}
            or (p.parts[0] == 'config' and name not in {'config/__init__.py', 'config/jarvis.ico'})
            or p.suffix.lower() in {'.db', '.log', '.pyc'}
            or (p.parts[0] == 'memory' and (p.suffix != '.py' or p.parts[1:2] == ('tasks',)))
            or any(x in p.name.lower() for x in ('token', 'credential', 'client_secret')))


def _archive(data):
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        for info in archive.infolist():
            raw = info.filename
            path = PurePosixPath(raw)
            if '\\' in raw or path.is_absolute() or '..' in path.parts or ':' in raw:
                raise RuntimeError('Güvensiz arşiv yolu.')
            if info.is_dir() or len(path.parts) < 2:
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError('Arşivde sembolik bağlantı var.')
            name = str(PurePosixPath(*path.parts[1:]))
            if _protected(name):
                continue
            total += info.file_size
            if total > LIMIT or name in files:
                raise RuntimeError('Geçersiz veya çok büyük güncelleme arşivi.')
            files[name] = archive.read(info)
    if not {'main.py', 'requirements.txt', 'gui/window.py'} <= files.keys():
        raise RuntimeError('Eksik JARVIS arşivi.')
    return files


def _target(root, name):
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise RuntimeError('Güncelleme yolu uygulama dışına çıkıyor.')
    return path


def _apply_zip(root, files, sha, branch):
    """Back up before writing; restore every changed/deleted file on failure."""
    state_path = root / '.jarvis-update.json'
    old = json.loads(state_path.read_text('utf-8')) if state_path.exists() else {}
    previous = old.get('files', {})
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
    backup = root / '.jarvis-backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + sha[:8] + '-' + str(time.time_ns()))
    backup.mkdir(parents=True, exist_ok=False)
    existed = set()
    for name in names:
        path = _target(root, name)
        if path.exists():
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            existed.add(name)
    old_state = state_path.read_bytes() if state_path.exists() else None
    touched = []
    try:
        for name in sorted(names):
            path = _target(root, name)
            touched.append(name)
            if name in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + '.jarvis-new')
                try:
                    tmp.write_bytes(files[name])
                    os.replace(tmp, path)
                finally:
                    tmp.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
        state = {'sha': sha, 'branch': branch, 'files': {n: _hash(b) for n, b in files.items()}}
        temp_state = state_path.with_suffix('.tmp')
        temp_state.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temp_state, state_path)
    except Exception:
        for name in reversed(touched):
            path = root / name
            if name in existed:
                shutil.copy2(backup / name, path)
            else:
                path.unlink(missing_ok=True)
        if old_state is None:
            state_path.unlink(missing_ok=True)
        else:
            state_path.write_bytes(old_state)
        raise
    return backup


def _needs_dependency_install(old, new):
    """Allow removal of ordinary package declarations, retaining pip directives verbatim."""
    def declarations(content):
        return [line.strip() for line in content.splitlines()
                if line.strip() and not line.lstrip().startswith('#')]

    before, after = declarations(old), declarations(new)
    if before == after:
        return False
    # Options, included files and continued lines can affect neighbouring entries.
    # Only apply the subset rule to independent package declarations.
    if any(not re.match(r'^[A-Za-z0-9]', line) or line.endswith('\\')
           for line in before + after):
        return True
    return not set(after).issubset(before)


def update(root=ROOT, progress=lambda message: None):
    root = Path(root)
    if getattr(sys, 'frozen', False):
        raise RuntimeError('Bu paketli sürüm için kurulum paketi gerekir; kaynak güncellemesi uygulanmadı.')
    lock = root / '.jarvis-update.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('Başka bir güncelleme çalışıyor. Önceki işlem kesildiyse .jarvis-update.lock dosyasını kaldırın.') from None
    os.close(fd)
    try:
        is_git = (root / '.git').exists()
        state_file = root / '.jarvis-update.json'
        state = json.loads(state_file.read_text('utf-8')) if state_file.exists() else {}
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
            return False, f'JARVIS güncel · {sha[:8]}'

        if is_git:
            if int(_git(root, 'rev-list', '--count', f'{sha}..{current}')):
                raise RuntimeError('Bu dalda GitHub sürümünde bulunmayan yerel commit var. Güncelleme durduruldu.')
            new_req = _git(root, 'show', f'{sha}:requirements.txt')
        else:
            progress('Yeni sürüm indiriliyor…')
            files = _archive(_get(f'https://codeload.github.com/{REPOSITORY}/zip/{sha}'))
            new_req = files['requirements.txt'].decode('utf-8')
        # Do not replace dependencies while Qt/audio DLLs are in use.
        old_req = (root / 'requirements.txt').read_text('utf-8')
        if _needs_dependency_install(old_req, new_req):
            raise RuntimeError('Bu sürüm yeni bağımlılıklar gerektiriyor. JARVIS’i kapatıp yeni sürümün setup.py kurulumunu çalıştırın. Mevcut sürüm korunuyor.')
        progress('Yedek alınıyor ve güncelleme uygulanıyor…')
        note = ''
        if is_git:
            if (_git(root, 'symbolic-ref', '--short', 'HEAD') != branch
                    or _git(root, 'rev-parse', 'HEAD') != current
                    or _local_changes(root) != (real_changes, eol_only)):
                raise RuntimeError('Kontrol sırasında yerel kod değişti; güncelleme durduruldu.')
            _git(root, 'branch', f'jarvis-backup/{time.time_ns()}', current)
            label = None
            if real_changes:
                shown = ', '.join(real_changes[:5]) + (' …' if len(real_changes) > 5 else '')
                progress(f'Yerel değişiklikler kenara alınıyor: {shown}')
                label = _set_aside(root)
            try:
                if eol_only:
                    # Only CRLF/LF differences: nothing to keep. The target is a
                    # descendant (checked above), so this is a fast-forward.
                    _git(root, 'reset', '--hard', sha)
                else:
                    _git(root, 'merge', '--ff-only', '--no-overwrite-ignore', sha)
            except RuntimeError:
                if label:
                    _restore(root, label)
                raise
            if _git(root, 'rev-parse', 'HEAD') != sha:
                raise RuntimeError('Güncelleme sonucu doğrulanamadı.')
            if label:
                note = _restore(root, label)
        else:
            _apply_zip(root, files, sha, branch)
        return True, f'Güncellendi · {sha[:8]}. JARVIS otomatik yeniden başlatılıyor.{note}'
    finally:
        lock.unlink(missing_ok=True)


def check(root=ROOT) -> dict:
    """Read-only: is there a newer JARVIS on GitHub, and what changed?
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
    state_file = root / '.jarvis-update.json'
    state = json.loads(state_file.read_text('utf-8')) if state_file.exists() else {}
    channel = json.loads((root / 'update_channel.json').read_text('utf-8'))
    branch = state.get('branch', channel['branch'])
    commit = json.loads(_get(f'https://api.github.com/repos/{REPOSITORY}/commits/{quote(branch, safe="")}'))
    sha = commit['sha']
    return {"newer": sha != state.get('sha'), "sha": sha, "current": state.get('sha') or "",
            "changes": str(commit.get('commit', {}).get('message', '')).splitlines()[:1] if sha != state.get('sha') else [],
            "branch": branch}
