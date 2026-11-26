"""Optional, current-user Windows DPAPI protection for JSON credential fields.

No keys are generated, stored beside the file, or sent to a service. This is
at-rest protection, not isolation from code already running as the same user.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from functools import lru_cache

MARKER = '_friday_credential_storage'
POLICY = {'schema': 1, 'backend': 'windows-dpapi'}
PREFIX = 'friday-dpapi:v1:'
LIMIT = 16 * 1024 * 1024
_SECRET = re.compile(r'(?:^|_)(?:api_keys?|access_key|private_key|secret_key|access_token|refresh_token|'
                     r'client_secret|token|password|passwd|passphrase|secret|credentials?|creds|'
                     r'authorization|cookies?)$')


class StorageError(RuntimeError):
    """Never recover an unreadable protected document by replacing it with {}."""


def available():
    return os.name == 'nt'


def protected(data):
    if not isinstance(data, dict):
        raise ValueError('Settings must be a JSON object')
    if MARKER not in data:
        return False
    policy = data[MARKER]
    if (not isinstance(policy, dict) or set(policy) != set(POLICY)
            or type(policy.get('schema')) is not int or policy != POLICY):
        raise StorageError('Unknown credential storage format; settings were preserved')
    return True


def _sensitive(key):
    key = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', str(key)).replace('-', '_').casefold()
    return key == 'key' or bool(_SECRET.search(key))


def _entropy(path):
    return b'FRIDAY/credentials/v1\0' + json.dumps(path, ensure_ascii=False,
                                                 separators=(',', ':')).encode('utf-8')


@lru_cache(maxsize=1)
def _native():
    # Keep the DLL bindings once instead of loading handles for every getter.
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    try:
        crypt = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    except OSError:
        raise StorageError('Windows protection API is unavailable; settings were preserved') from None
    for operation in (crypt.CryptUnprotectData, crypt.CryptProtectData):
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        operation.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    return Blob, crypt.CryptProtectData, crypt.CryptUnprotectData, kernel.LocalFree


def _dpapi(value, entropy, *, decrypt=False):
    if not available():
        raise StorageError('Protected settings require the original Windows user profile')
    import ctypes
    Blob, protect, unprotect, release = _native()
    def blob(raw):
        buffer = ctypes.create_string_buffer(raw)
        return Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer
    source, source_buffer = blob(value)
    extra, extra_buffer = blob(entropy)
    output = Blob()
    operation = unprotect if decrypt else protect
    try:
        # UI forbidden; never use LOCAL_MACHINE (which would allow other users).
        if not operation(ctypes.byref(source), None, ctypes.byref(extra), None,
                         None, 1, ctypes.byref(output)):
            raise StorageError('Windows credential protection failed; settings were preserved')
        if not output.data or output.size > LIMIT:
            raise StorageError('Invalid Windows credential result; settings were preserved')
        return ctypes.string_at(output.data, output.size)
    finally:
        if output.data:
            if output.size <= LIMIT:
                ctypes.memset(output.data, 0, output.size)
            release(output.data)
        ctypes.memset(source_buffer, 0, len(source_buffer))
        ctypes.memset(extra_buffer, 0, len(extra_buffer))


def _pack(value, path):
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    envelope = json.dumps({'schema': 1, 'value': value,
                           'sha256': hashlib.sha256(data).hexdigest()}, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(envelope) > LIMIT:
        raise StorageError('Credential field exceeds the protection limit')
    return PREFIX + base64.b64encode(_dpapi(envelope, _entropy(path))).decode('ascii')


def _unpack(value, path):
    try:
        if not isinstance(value, str) or not value.startswith(PREFIX) or len(value) > LIMIT * 2:
            raise ValueError('Missing protected credential')
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
        decoded = json.loads(_dpapi(raw, _entropy(path), decrypt=True))
        if (not isinstance(decoded, dict) or set(decoded) != {'schema', 'value', 'sha256'}
                or type(decoded['schema']) is not int or decoded['schema'] != 1):
            raise ValueError('Invalid decrypted schema')
        data = json.dumps(decoded['value'], ensure_ascii=False, separators=(',', ':'),
                          allow_nan=False).encode('utf-8')
        if hashlib.sha256(data).hexdigest() != decoded['sha256']:
            raise ValueError('Decrypted integrity mismatch')
        return decoded['value']
    except (ValueError, TypeError, KeyError):
        raise StorageError('Protected credentials could not be verified; settings were preserved') from None


def _walk(value, path=(), *, decrypt=False):
    if len(path) > 128:
        raise StorageError('Settings nesting exceeds the protection limit')
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            here = (*path, key)
            if not path and key == MARKER:
                result[key] = dict(POLICY)
            elif _sensitive(key) and item is not None and item != '':
                result[key] = _unpack(item, here) if decrypt else _pack(item, here)
            else:
                result[key] = _walk(item, here, decrypt=decrypt)
        return result
    if isinstance(value, list):
        return [_walk(item, (*path, index), decrypt=decrypt) for index, item in enumerate(value)]
    return value


def encode(data):
    return _walk(data) if protected(data) else data


def decode(data):
    if protected(data):
        return _walk(data, decrypt=True)
    def check(value, depth=0):
        if depth > 128:
            raise StorageError('Settings nesting exceeds the protection limit')
        if isinstance(value, dict):
            for key, item in value.items():
                if _sensitive(key) and isinstance(item, str) and item.startswith(PREFIX):
                    raise StorageError('Credential storage marker is missing; settings were preserved')
                check(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                check(item, depth + 1)
    check(data)
    return data


def read_document(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise StorageError('Settings file exceeds the read limit; file was preserved')
    return decode(json.loads(raw))


def read_settings(path):
    """Read-only primary/backup adapter for legacy consumers; never hide DPAPI failure."""
    path = Path(path)
    for candidate in (path, path.with_name(path.name + '.bak')):
        try:
            return read_document(candidate)
        except (OSError, ValueError):
            pass
    return {}
