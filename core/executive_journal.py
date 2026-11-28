"""Encrypted transactional journal for narrowly scoped Windows actions.

Uses the same AES-GCM and per-user key protection as NeuralJournal in its own
directory. A started operation is never replayed after a crash.
"""
from __future__ import annotations

import json
from contextlib import closing
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.neural_journal import JournalError, NeuralJournal

_ID = re.compile(r"^o[0-9a-f]{32}$")
_AAD = b"FRIDAY/windows-executive/operation/v1/"
_PENDING = {"started", "undo_started"}
_STATES = _PENDING | {"done", "undone", "aborted", "acknowledged"}
_PROCESS_LOCK = threading.RLock()


class ExecutiveJournal:
    def __init__(self, directory: Path):
        self._journal = None
        self._locked = False
        _PROCESS_LOCK.acquire()
        self._locked = True
        try:
            directory = Path(directory)
            if directory.is_symlink():
                raise JournalError("Operation journal directory cannot be a symbolic link")
            database = directory / "neural_sync.sqlite3"
            had_database = database.exists()
            if (directory / "neural_sync.key").exists() and not had_database:
                raise JournalError("Operation database is missing; the existing key was preserved")
            if database.is_symlink():
                raise JournalError("Operation database cannot be a symbolic link")
            if had_database:
                try:
                    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as probe:
                        table = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='executive_ops'").fetchone()
                except sqlite3.Error as exc:
                    raise JournalError("Operation database cannot be read; it was preserved") from exc
                if table is None:
                    raise JournalError("Operation table is missing; the database was preserved")
            self._journal = NeuralJournal(directory, "windows-executive-v1")
            self._db = self._journal._connection
            self._db.execute("CREATE TABLE IF NOT EXISTS executive_ops (id TEXT PRIMARY KEY, data BLOB NOT NULL)")
            self._db.commit()
        except Exception:
            self.close()
            raise

    def close(self):
        try:
            if self._journal is not None:
                self._journal.close()
                self._journal = None
        finally:
            if self._locked:
                self._locked = False
                _PROCESS_LOCK.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _seal(self, record):
        ident = record["id"]
        if not _ID.fullmatch(ident):
            raise JournalError("Invalid operation identity")
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        nonce = os.urandom(12)
        return nonce + AESGCM(self._journal.key).encrypt(nonce, raw, _AAD + ident.encode("ascii"))

    def _open(self, ident, blob):
        if not _ID.fullmatch(str(ident)):
            raise JournalError("Invalid operation identity")
        try:
            raw = bytes(blob)
            doc = json.loads(AESGCM(self._journal.key).decrypt(raw[:12], raw[12:], _AAD + ident.encode("ascii")))
            if not isinstance(doc, dict) or doc.get("id") != ident or doc.get("status") not in _STATES:
                raise ValueError("invalid record")
            return doc
        except Exception as exc:
            raise JournalError("Operation record could not be authenticated; it was preserved") from exc

    def get(self, ident):
        if not isinstance(ident, str) or not _ID.fullmatch(ident):
            raise ValueError("invalid operation id")
        row = self._db.execute("SELECT data FROM executive_ops WHERE id=?", (ident,)).fetchone()
        return self._open(ident, row[0]) if row else None

    def pending(self):
        rows = self._db.execute("SELECT id, data FROM executive_ops").fetchall()
        return [doc for ident, blob in rows if (doc := self._open(ident, blob))["status"] in _PENDING]

    def recent(self, limit=10):
        rows = self._db.execute("SELECT id, data FROM executive_ops").fetchall()
        docs = [self._open(ident, blob) for ident, blob in rows]
        return sorted(docs, key=lambda doc: float(doc.get("created") or 0), reverse=True)[:limit]

    def begin(self, kind, before, target):
        if self.pending():
            raise JournalError("An earlier operation has an unknown result and needs user inspection")
        record = {"id": "o" + secrets.token_hex(16), "kind": str(kind), "before": str(before),
                  "target": str(target), "status": "started", "created": time.time()}
        with self._db:
            self._db.execute("INSERT INTO executive_ops(id,data) VALUES (?,?)", (record["id"], self._seal(record)))
        return record

    def transition(self, ident, expected, status):
        if status not in _STATES:
            raise ValueError("invalid operation state")
        with self._db:
            doc = self.get(ident)
            if not doc or doc["status"] != expected:
                raise JournalError("Operation state changed; no action was performed")
            doc["status"] = status
            doc["updated"] = time.time()
            self._db.execute("UPDATE executive_ops SET data=? WHERE id=?", (self._seal(doc), ident))
        return doc
