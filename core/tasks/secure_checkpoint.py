"""Encrypted, transactional *copy* of local task records for recovery.

Live task files remain unchanged and plaintext. This is deliberately not an
automatic migration or a license to restart recovered tasks. Large attachments,
generated files and reports outside the task directory are not included.
"""
from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.neural_journal import JournalError, NeuralJournal

_AAD = b"FRIDAY/task-checkpoint/v1"
_MAX_BYTES = 32_000_000
_MAX_FILES = 5000
_TASK = re.compile(r"^t[0-9a-f-]{1,70}$")
_LOCK = threading.RLock()


def _safe_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\0" in value:
        raise ValueError("invalid checkpoint path")
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in path.parts):
        raise ValueError("invalid checkpoint path")
    return path


def _candidates(engine):
    root = engine.store.root
    files = set(root.glob("*.json"))
    for name in ("plans", "cognitive"):
        directory = root / name
        if directory.is_symlink():
            raise ValueError("a checkpoint source directory is a symbolic link")
        if directory.exists():
            files.update(directory.glob("*.json"))
    for task in engine.store.all():
        ident = str(task.get("id") or "")
        if not _TASK.fullmatch(ident):
            raise ValueError("invalid task identity in store")
        work = root / ident
        if work.is_symlink():
            raise ValueError("a task directory is a symbolic link")
        for name in ("notes.md", "plan.json", "sources.json", "findings.jsonl"):
            path = work / name
            if path.is_symlink() or path.exists():
                files.add(path)
        pages = work / "pages"
        if pages.is_symlink():
            raise ValueError("a research page directory is a symbolic link")
        if pages.exists():
            for path in pages.rglob("*"):
                if path.is_symlink():
                    raise ValueError("a checkpoint source is a symbolic link")
                if path.is_file():
                    files.add(path)
    return sorted(files, key=lambda p: str(p))


def _collect(engine):
    root = engine.store.root
    entries, total, observed = [], 0, {}
    candidates = _candidates(engine)
    if len(candidates) > _MAX_FILES:
        raise ValueError("task checkpoint has too many files")
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            raise ValueError("checkpoint source is not a regular file")
        rel = path.relative_to(root).as_posix()
        _safe_path(rel)
        before = path.stat()
        if before.st_size > _MAX_BYTES - total:
            raise ValueError("task checkpoint exceeds size limit")
        data = path.read_bytes()
        after = path.stat()
        stamp = lambda s: (s.st_size, s.st_mtime_ns, s.st_ino)
        if stamp(before) != stamp(after) or len(data) != before.st_size:
            raise ValueError("task file changed while being read")
        if path.suffix == ".json":
            try:
                json.loads(data)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("a task JSON file is invalid; existing data was not changed") from exc
        total += len(data)
        observed[path] = stamp(after)
        entries.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(),
                        "data": base64.b64encode(data).decode("ascii")})
    if _candidates(engine) != candidates or any(p.is_symlink() or stamp(p.stat()) != v for p, v in observed.items()):
        raise ValueError("task files changed while creating checkpoint")
    return {"version": 1, "created": time.time(), "files": entries, "total_bytes": total,
            "scope": "task-json-turns-research-notes; excludes attachments, generated files and reports"}


class SnapshotLimitError(ValueError):
    pass


class TaskCheckpoint:
    def __init__(self, directory):
        self._journal = None
        self._locked = False
        _LOCK.acquire()
        self._locked = True
        try:
            directory = Path(directory)
            if directory.is_symlink():
                raise JournalError("Checkpoint directory cannot be a symbolic link")
            database = directory / "neural_sync.sqlite3"
            had_database = database.exists()
            if (directory / "neural_sync.key").exists() and not had_database:
                raise JournalError("Checkpoint database is missing; the key was preserved")
            if database.is_symlink():
                raise JournalError("Checkpoint database cannot be a symbolic link")
            if had_database:
                try:
                    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as probe:
                        table = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_snapshot'").fetchone()
                except sqlite3.Error as exc:
                    raise JournalError("Checkpoint database cannot be read; it was preserved") from exc
                if table is None:
                    raise JournalError("Checkpoint table is missing; the database was preserved")
            self._journal = NeuralJournal(directory, "task-checkpoint-v1")
            self._db = self._journal._connection
            self._db.execute("CREATE TABLE IF NOT EXISTS task_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), data BLOB NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS task_snapshot_history (id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL, data BLOB NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS snapshot_policy (id INTEGER PRIMARY KEY CHECK(id=1), limit_mib INTEGER NOT NULL)")
            self._db.commit()
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        try:
            if self._journal is not None:
                self._journal.close()
                self._journal = None
        finally:
            if self._locked:
                self._locked = False
                _LOCK.release()

    def include_agenda(self, snapshot):
        from core.tasks.agenda import read_record
        if not self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='personal_tasks'").fetchone():
            return
        cipher = AESGCM(self._journal.key)
        for ident, blob in self._db.execute("SELECT id,data FROM personal_tasks ORDER BY id"):
            if not re.fullmatch("[0-9a-f]{32}", ident):
                raise ValueError("invalid agenda identity")
            item = read_record(cipher, ident, blob)
            data = json.dumps(item, ensure_ascii=False).encode("utf-8")
            snapshot["total_bytes"] += len(data)
            if snapshot["total_bytes"] > _MAX_BYTES or len(snapshot["files"]) >= _MAX_FILES:
                raise ValueError("personal agenda exceeds checkpoint limit")
            snapshot["files"].append({"path": f"personal_agenda/{ident}.json",
                                      "sha256": hashlib.sha256(data).hexdigest(),
                                      "data": base64.b64encode(data).decode("ascii")})
        snapshot["scope"] += "; includes personal agenda"

    def set_limit(self, limit_mib):
        if type(limit_mib) is not int or not 1 <= limit_mib <= 65536:
            raise ValueError("checkpoint limit must be 1 to 65536 MiB")
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO snapshot_policy VALUES (1, ?)", (limit_mib,))

    def save(self, snapshot):
        if self._db.execute("SELECT 1 FROM task_snapshot WHERE id=1").fetchone() is not None:
            self.load()  # Never overwrite an unreadable/tampered older checkpoint.
        raw = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        nonce = os.urandom(12)
        encrypted = nonce + AESGCM(self._journal.key).encrypt(nonce, raw, _AAD)
        with self._db:
            old = self._db.execute("SELECT data FROM task_snapshot WHERE id=1").fetchone()
            policy = self._db.execute("SELECT limit_mib FROM snapshot_policy WHERE id=1").fetchone()
            if policy:
                history_size = self._db.execute(
                    "SELECT COALESCE(SUM(length(data)),0) FROM task_snapshot_history").fetchone()[0]
                current_size = len(old[0]) if old is not None else 0
                if history_size + current_size + len(encrypted) > policy[0] * 1024 ** 2:
                    raise SnapshotLimitError("Configured encrypted snapshot limit reached; existing versions preserved")
            if old is not None:
                self._db.execute("INSERT INTO task_snapshot_history(created,data) VALUES (?,?)", (time.time(), old[0]))
            self._db.execute("INSERT OR REPLACE INTO task_snapshot(id,data) VALUES (1,?)", (encrypted,))

    def versions(self):
        """List history identifiers, newest first; contents stay encrypted."""
        return [{"id": row[0], "archived_at": row[1]} for row in
                self._db.execute("SELECT id,created FROM task_snapshot_history ORDER BY id DESC")]

    def load(self, version=None):
        if version is None:
            row = self._db.execute("SELECT data FROM task_snapshot WHERE id=1").fetchone()
        else:
            row = self._db.execute("SELECT data FROM task_snapshot_history WHERE id=?", (version,)).fetchone()
        if row is None:
            raise JournalError("No encrypted task checkpoint exists")
        try:
            raw = bytes(row[0])
            doc = json.loads(AESGCM(self._journal.key).decrypt(raw[:12], raw[12:], _AAD))
            if not isinstance(doc, dict) or doc.get("version") != 1 or not isinstance(doc.get("files"), list):
                raise ValueError("invalid checkpoint")
            if len(doc["files"]) > _MAX_FILES:
                raise ValueError("too many files")
            total, paths = 0, set()
            for item in doc["files"]:
                path = _safe_path(item["path"])
                if str(path) in paths:
                    raise ValueError("duplicate checkpoint path")
                paths.add(str(path))
                data = base64.b64decode(item["data"], validate=True)
                total += len(data)
                if total > _MAX_BYTES or hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("invalid checkpoint data")
            if total != doc.get("total_bytes"):
                raise ValueError("invalid checkpoint size")
            return doc
        except Exception as exc:
            raise JournalError("Task checkpoint could not be authenticated; it was preserved") from exc


def checkpoint(engine):
    # Freeze scheduling and record changes; never capture worker files while a
    # worker can still be writing. External processes are only detected by stat.
    with engine._lock:
        if any(worker.is_alive() for worker in engine._workers.values()):
            raise ValueError("A task is running; wait for it to stop before creating a checkpoint")
        with engine.store._lock:
            snapshot = _collect(engine)
            with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
                archive.include_agenda(snapshot)
                archive.save(snapshot)
    return {"files": len(snapshot["files"]), "bytes": snapshot["total_bytes"]}


def history(engine):
    with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
        return archive.versions()


def verify(engine, version=None):
    with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
        snapshot = archive.load(version)
    return {"files": len(snapshot["files"]), "bytes": snapshot["total_bytes"], "created": snapshot["created"]}


def recover_to_isolated_folder(engine, version=None):
    """Export plaintext to a new isolated folder; never touches live tasks."""
    with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
        snapshot = archive.load(version)
    from core.identity import data_home
    base = data_home() / "task_recovery"
    base.mkdir(parents=True, exist_ok=True)
    if base.is_symlink():
        raise ValueError("recovery directory cannot be a symbolic link")
    staging = Path(tempfile.mkdtemp(prefix=".partial-", dir=base))
    destination = base / ("recovery-" + secrets.token_hex(12))
    try:
        for item in snapshot["files"]:
            path = staging.joinpath(*_safe_path(item["path"]).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = base64.b64decode(item["data"], validate=True)
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        (staging / "RECOVERY_INFO.txt").write_text(
            "Offline recovery copy. Do not run tasks automatically. Attachments, generated files and external reports are not included.\n",
            encoding="utf-8")
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination
