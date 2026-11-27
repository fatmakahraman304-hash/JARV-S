"""Encrypted, transactional local checkpoint for the device sync worker.

The SQLite database only sees ciphertext and keyed command digests. Windows
protects the random encryption key with current-user DPAPI. On POSIX the key
is a mode-0600 file: this protects against other local users, not the owner or
an attacker who can read both the key and database. Never silently replace a
missing or unreadable key when a database already exists.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

QUEUES = ("pending", "turns", "out_cmds", "img_new", "rem_new")
_AAD = b"FRIDAY/neural-sync/checkpoint/v1"
_ENTROPY = b"FRIDAY/neural-sync/key/v1"


class JournalError(RuntimeError):
    pass


class NeuralJournal:
    def __init__(self, directory: Path, scope: str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / "neural_sync.sqlite3"
        self.key_path = self.directory / "neural_sync.key"
        self.scope = str(scope)
        self._guard = None
        self._connection = None
        try:
            self._acquire()
            self.key = self._load_key()
            if self.db_path.is_symlink():
                raise JournalError("Eşitleme veritabanı bağlantısı kullanılamaz.")
            self._connection = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), data BLOB NOT NULL)")
            self._connection.execute("CREATE TABLE IF NOT EXISTS claims (digest BLOB PRIMARY KEY)")
            self._connection.commit()
        except Exception:
            self.close()
            raise

    def _acquire(self):
        path = self.directory / "neural_sync.lock"
        if path.is_symlink():
            raise JournalError("Eşitleme kilidi bağlantısı kullanılamaz.")
        self._guard = path.open("a+b")
        self._guard.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise JournalError("Cihaz eşitleme kaydı başka bir süreç tarafından kullanılıyor.") from exc

    def _load_key(self):
        if self.key_path.is_symlink():
            raise JournalError("Eşitleme anahtarı bağlantısı kullanılamaz.")
        if not self.key_path.exists():
            if self.db_path.exists():
                raise JournalError("Eşitleme anahtarı eksik; kayıtlar korunuyor.")
            key = os.urandom(32)
            if os.name == "nt":
                from memory.secret_storage import _dpapi
                contents = b"DPAPI1\n" + _dpapi(key, _ENTROPY)
            else:
                contents = b"POSIX1\n" + key
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.key_path, flags, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            return key
        if os.name != "nt" and self.key_path.stat().st_mode & 0o077:
            raise JournalError("Eşitleme anahtarının dosya izinleri güvenli değil.")
        contents = self.key_path.read_bytes()
        if os.name == "nt" and contents.startswith(b"DPAPI1\n"):
            from memory.secret_storage import _dpapi
            key = _dpapi(contents[7:], _ENTROPY, decrypt=True)
        elif os.name != "nt" and contents.startswith(b"POSIX1\n"):
            key = contents[7:]
        else:
            raise JournalError("Eşitleme anahtarı bu kullanıcıda açılamıyor; kayıtlar korunuyor.")
        if len(key) != 32:
            raise JournalError("Eşitleme anahtarı geçersiz; kayıtlar korunuyor.")
        return key

    def load(self):
        row = self._connection.execute("SELECT data FROM checkpoint WHERE id=1").fetchone()
        if row is None:
            return {name: [] for name in QUEUES}
        try:
            raw = bytes(row[0])
            doc = json.loads(AESGCM(self.key).decrypt(raw[:12], raw[12:], _AAD))
            queues = doc["queues"]
            if not isinstance(queues, dict) or any(not isinstance(queues.get(k), list) for k in QUEUES):
                raise ValueError("invalid queues")
            if doc["scope"] != self.scope and any(queues[k] for k in QUEUES):
                raise JournalError("Bekleyen kayıtlar başka bir eşitleme hesabına ait; aktarım durduruldu.")
            if doc["scope"] != self.scope:
                return {name: [] for name in QUEUES}
            return queues
        except JournalError:
            raise
        except Exception as exc:
            raise JournalError("Eşitleme kaydı doğrulanamadı; veriler korunuyor.") from exc

    def _seal(self, queues):
        payload = json.dumps({"scope": self.scope, "queues": queues}, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        nonce = os.urandom(12)
        return nonce + AESGCM(self.key).encrypt(nonce, payload, _AAD)

    def save(self, queues):
        encrypted = self._seal(queues)
        with self._connection:
            self._connection.execute("INSERT OR REPLACE INTO checkpoint (id, data) VALUES (1, ?)", (encrypted,))

    def claim(self, device: str, command_id: str, queues=None) -> bool:
        """Commit an irreversible claim *before* execution. Never auto-replay."""
        text = json.dumps([self.scope, str(device), str(command_id)], ensure_ascii=False).encode("utf-8")
        digest = hmac.new(self.key, b"FRIDAY/command/v1\0" + text, hashlib.sha256).digest()
        encrypted = self._seal(queues) if queues is not None else None
        with self._connection:
            cur = self._connection.execute("INSERT OR IGNORE INTO claims (digest) VALUES (?)", (digest,))
            if cur.rowcount == 1 and encrypted is not None:
                self._connection.execute("INSERT OR REPLACE INTO checkpoint (id, data) VALUES (1, ?)", (encrypted,))
        return cur.rowcount == 1

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._guard is not None:
            self._guard.close()
            self._guard = None
