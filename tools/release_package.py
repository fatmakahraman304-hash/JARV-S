"""Build/verify a committed-source candidate; never copy the user's working tree.

Checksums detect corruption; optional Ed25519 authentication uses an independently
trusted public key. Physical acceptance, Android rotation and license review remain
separate release gates. Unsigned inspection uses only stdlib and Git; signatures
use the application's existing, lazily imported cryptography dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

MANIFEST = 'friday-release.json'
MAX_TOTAL = 100 * 1024 * 1024
MAX_FILE = 20 * 1024 * 1024
REQUIRED = {'main.py', 'ui.py', 'setup.py', 'requirements.txt', 'LICENSE',
            'update_channel.json', 'core/face_model.obj'}
PRIVATE_SUFFIXES = {'.jks', '.keystore', '.p12', '.pfx', '.key', '.pem', '.db', '.sqlite', '.sqlite3'}
PRIVATE_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'uploads', 'screenshots',
                'logs', 'reports', 'downloads', '.aether-backups'}
SECRET_PATTERNS = {
    'google_api_key': re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
    'github_token': re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    'nvidia_api_key': re.compile(rb'nvapi-[A-Za-z0-9_-]{30,}'),
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
}


def safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(ord(char) < 32 or char in '<>\"|?*' for char in name)):
        return False
    parts = name.split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    return all(part not in ('', '.', '..') and part.rstrip(' .') == part
               and part.split('.')[0].upper() not in reserved for part in parts)


def private_path(name):
    path = PurePosixPath(name.lower())
    if any(part in PRIVATE_DIRS for part in path.parts):
        return True
    if path.suffix in PRIVATE_SUFFIXES or any(prefix in path.name for prefix in ('.db-', '.sqlite-', '.sqlite3-')):
        return True
    if path.name == '.env' or path.name.startswith('.env.'):
        return True
    if any(word in path.name for word in ('credentials', 'client_secret')) or path.name.startswith('token'):
        return True
    if path.parts[0] == 'memory' and path.suffix != '.py':
        return True
    if path.parts[0] == 'config' and name not in ('config/__init__.py', 'config/aether.ico'):
        return True
    if path.name.startswith('.aether-update') or path.name.endswith('.aether-new'):
        return True
    return False


def secret_kinds(data):
    return [kind for kind, pattern in SECRET_PATTERNS.items() if pattern.search(data)]


def build(root: Path, output: Path, ref='HEAD'):
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options',
                                      ref + '^{commit}'], cwd=root, text=True).strip()
    tree = subprocess.check_output(['git', 'ls-tree', '-rz', commit], cwd=root)
    for entry in tree.split(b'\0'):
        if entry and entry.split(b' ', 1)[0] not in (b'100644', b'100755'):
            raise ValueError('Source candidate cannot contain symlinks/submodules')
    raw = subprocess.check_output(['git', 'archive', '--format=zip', commit], cwd=root)
    files, excluded, seen = {}, [], set()
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        if sum(item.file_size for item in source.infolist()) > MAX_TOTAL:
            raise ValueError('Oversized committed source tree')
        for item in source.infolist():
            if item.is_dir():
                continue
            name = item.filename
            if not safe_name(name) or name.casefold() in seen or name == MANIFEST:
                raise ValueError('Unsafe or conflicting committed path')
            seen.add(name.casefold())
            if private_path(name):
                excluded.append(name)
                continue
            if item.file_size > MAX_FILE:
                raise ValueError('Oversized committed source file')
            data = source.read(item)
            if secret_kinds(data):
                raise ValueError(f'Credential-like material in {name}; values withheld')
            files[name] = data
    if not REQUIRED <= files.keys() or sum(map(len, files.values())) > MAX_TOTAL:
        raise ValueError('Missing required assets or oversized source candidate')
    manifest = {'schema': 1, 'source_commit': commit, 'kind': 'source-candidate',
                'publisher_signature_verified': False, 'full_product_ready': False,
                'excluded_paths': sorted(excluded),
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in sorted(files.items())}}
    files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    payload = buffer.getvalue()
    output.parent.mkdir(parents=True, exist_ok=True)
    # A new name is required; never overwrite an earlier candidate silently.
    with output.open('xb') as file:
        file.write(payload)
    output.with_suffix(output.suffix + '.sha256').write_text(
        hashlib.sha256(payload).hexdigest() + '  ' + output.name + '\n', encoding='utf-8')
    return manifest


def verify(archive: Path, expected_commit=None, destination: Path | None = None,
           *, signature: Path | None = None, public_key: Path | None = None,
           require_signature=False):
    # The signed bytes are the same snapshot parsed and extracted below.
    with archive.open('rb') as handle:
        payload = handle.read(MAX_TOTAL + 1)
    return _verify_snapshot(payload, expected_commit, destination, signature=signature,
                            public_key=public_key, require_signature=require_signature)


def _verify_snapshot(payload, expected_commit=None, destination=None, *,
                     signature=None, public_key=None, require_signature=False):
    if len(payload) > MAX_TOTAL:
        raise ValueError('Oversized source archive')
    authenticated = False
    if signature is not None or public_key is not None or require_signature:
        if signature is None or public_key is None:
            raise ValueError('A detached signature and trusted public key are both required')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from core.release_signatures import verify as verify_signature, MAX_SIGNATURE
        with signature.open('rb') as handle:
            envelope = handle.read(MAX_SIGNATURE + 1)
        with public_key.open('rb') as handle:
            trusted_key = handle.read(16385)
        if len(trusted_key) > 16384:
            raise ValueError('Oversized trusted public key')
        authenticated = verify_signature(payload, expected_commit, envelope, trusted_key)
    files, seen = {}, set()
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        items = source.infolist()
        if len(items) > 2000 or sum(item.file_size for item in items) > MAX_TOTAL:
            raise ValueError('Oversized source archive')
        for item in items:
            name = item.filename
            if (not safe_name(name) or name.casefold() in seen or private_path(name)
                    or item.is_dir() or item.file_size > MAX_FILE
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unsafe, private or duplicated source entry')
            seen.add(name.casefold())
            files[name] = source.read(item)
    manifest = json.loads(files.pop(MANIFEST))
    if (manifest.get('schema') != 1 or manifest.get('kind') != 'source-candidate'
            or manifest.get('full_product_ready') is not False
            or manifest.get('publisher_signature_verified') is not False
            or not re.fullmatch('[0-9a-f]{40}', manifest.get('source_commit', ''))
            or (expected_commit and manifest['source_commit'] != expected_commit)):
        raise ValueError('Source identity does not match')
    declared = manifest.get('files')
    if not isinstance(declared, dict) or declared.keys() != files.keys() or not REQUIRED <= files.keys():
        raise ValueError('Incomplete or undeclared source contents')
    for name, data in files.items():
        if (declared[name] != {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                or secret_kinds(data)):
            raise ValueError(f'Content verification failed: {name}; values withheld')
    if destination is not None:
        # Verification finishes before any filesystem write; no extractall/path
        # traversal, overwriting an installation, or writing through symlinks.
        destination.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as file:
                file.write(data)
        (destination / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return {**manifest, 'publisher_signature_verified': authenticated}


def inventory(output: Path):
    """Inventory installed versions and retain license text; no compliance claim."""
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    with zipfile.ZipFile(output / 'dependency-licenses.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for index, distribution in enumerate(sorted(importlib.metadata.distributions(),
                                             key=lambda d: d.metadata.get('Name', '').lower())):
            metadata = distribution.metadata
            row = {'name': metadata.get('Name'), 'version': distribution.version,
                   'license_expression': metadata.get('License-Expression'),
                   'license_classifiers': [v for v in metadata.get_all('Classifier', [])
                                           if v.startswith('License ::')], 'license_files': []}
            for file in distribution.files or ():
                if (any(word in file.name.lower() for word in ('license', 'copying', 'notice'))
                        and ('.dist-info' in str(file) or '.egg-info' in str(file))):
                    path = distribution.locate_file(file)
                    if path.is_file() and path.stat().st_size <= MAX_FILE:
                        name = f'{index}/{file.as_posix()}'
                        if not safe_name(name):
                            continue
                        if name in row['license_files']:
                            continue
                        archive.writestr(name, path.read_bytes())
                        row['license_files'].append(name)
            rows.append(row)
    (output / 'dependencies.json').write_text(json.dumps(
        {'scope': 'installed Python distributions; not OS/browser/Qt binary dependencies',
         'compatibility_review': 'UNVERIFIED', 'vulnerability_audit': 'UNVERIFIED',
         'distributions': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    create.add_argument('--root', type=Path, default=Path.cwd())
    create.add_argument('--ref', default='HEAD')
    create.add_argument('--out', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('archive', type=Path)
    check.add_argument('--commit', required=True)
    check.add_argument('--extract', type=Path)
    check.add_argument('--signature', type=Path)
    check.add_argument('--public-key', type=Path)
    check.add_argument('--require-signature', action='store_true')
    signing = commands.add_parser('sign')
    signing.add_argument('archive', type=Path)
    signing.add_argument('--commit', required=True)
    signing.add_argument('--key', type=Path, required=True)
    signing.add_argument('--out', type=Path, required=True)
    signing.add_argument('--password-env', help='Name of an environment variable for encrypted PEM; never a password value')
    license_parser = commands.add_parser('inventory')
    license_parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'inventory':
        print(json.dumps({'distributions': inventory(args.out), 'compliance': 'UNVERIFIED'}))
    elif args.command == 'sign':
        # Never load release private keys from a source checkout or its folders.
        root = Path(__file__).resolve().parents[1]
        if args.key.resolve().is_relative_to(root):
            raise ValueError('Keep the private release key outside the checkout')
        with args.archive.open('rb') as handle:
            payload = handle.read(MAX_TOTAL + 1)
        _verify_snapshot(payload, args.commit)
        sys.path.insert(0, str(root))
        from core.release_signatures import sign
        with args.key.open('rb') as handle:
            key = handle.read(16385)
        if len(key) > 16384:
            raise ValueError('Oversized private release key')
        password = None
        if args.password_env:
            value = os.environ.get(args.password_env)
            if not value:
                raise ValueError('Signing password environment variable is missing')
            password = value.encode('utf-8')
        envelope = sign(payload, args.commit, key, password=password)
        with args.out.open('xb') as handle:
            handle.write(envelope)
        print(json.dumps({'signature': str(args.out), 'published': False}))
    else:
        result = (build(args.root, args.out, args.ref) if args.command == 'build'
                  else verify(args.archive, args.commit, args.extract,
                              signature=args.signature, public_key=args.public_key,
                              require_signature=args.require_signature))
        print(json.dumps({'source_commit': result['source_commit'], 'files': len(result['files']),
                          'kind': 'source-candidate', 'full_product_ready': False,
                          'publisher_signature_verified': result['publisher_signature_verified']}))


if __name__ == '__main__':
    main()
