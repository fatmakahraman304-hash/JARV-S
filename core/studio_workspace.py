"""Explicit user-managed records, stored outside the installation.

No background collection, remote upload or execution. Backup import validates
the entire document before writing and merges without replacing existing rows.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid

KINDS = ("project", "idea", "decision", "source", "feedback", "template", "note")
STAGES = ("Taslak", "Planlandı", "Devam ediyor", "Test", "Tamamlandı", "Arşiv")
CONFIDENCE = ("Belirtilmedi", "Doğrulanmış", "Çıkarım", "Tahmin", "Kurgu")
MAX_BACKUP = 8 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


class Workspace:
    def __init__(self, path=None):
        if path is None:
            from memory.continuity import data_dir
            path = data_dir() / "thinking_studio.sqlite3"
        self.path = Path(path)

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    body TEXT NOT NULL, tags TEXT NOT NULL, project TEXT NOT NULL,
                    stage TEXT NOT NULL, confidence TEXT NOT NULL, created TEXT NOT NULL,
                    updated TEXT NOT NULL)""")
                db.execute("""CREATE TABLE IF NOT EXISTS versions (
                    seq INTEGER PRIMARY KEY, record_id TEXT NOT NULL, time TEXT NOT NULL,
                    data TEXT NOT NULL)""")
                yield db

    @staticmethod
    def validate(row):
        if not isinstance(row, dict):
            raise ValueError("Geçersiz kayıt.")
        out = {}
        for key, limit in (("id", 64), ("kind", 32), ("title", 200),
                           ("body", 40000), ("tags", 500), ("project", 200),
                           ("stage", 32), ("confidence", 32), ("created", 64), ("updated", 64)):
            val = row.get(key)
            if not isinstance(val, str) or len(val) > limit:
                raise ValueError("Geçersiz alan: " + key)
            out[key] = val
        if not out["id"] or not out["title"].strip() or out["kind"] not in KINDS:
            raise ValueError("Başlık ve geçerli kayıt türü gerekli.")
        if out["stage"] not in STAGES or out["confidence"] not in CONFIDENCE:
            raise ValueError("Geçersiz aşama veya güven etiketi.")
        for key in ("created", "updated"):
            if datetime.fromisoformat(out[key]).tzinfo is None:
                raise ValueError("Zaman dilimi gerekli.")
        return out

    def save(self, *, kind, title, body="", tags="", project="", stage="Taslak",
             confidence="Belirtilmedi", record_id=None):
        with self.db() as db:
            old = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone() if record_id else None
            if record_id and old is None:
                raise ValueError("Düzenlenecek kayıt bulunamadı.")
            stamp = now()
            row = self.validate(dict(id=record_id or uuid.uuid4().hex, kind=kind, title=title.strip(),
                                     body=body, tags=tags, project=project, stage=stage,
                                     confidence=confidence, created=old["created"] if old else stamp,
                                     updated=stamp))
            if old:
                db.execute("INSERT INTO versions(record_id,time,data) VALUES(?,?,?)",
                           (record_id, stamp, json.dumps(dict(old), ensure_ascii=False)))
            db.execute("""INSERT OR REPLACE INTO records VALUES(
                :id,:kind,:title,:body,:tags,:project,:stage,:confidence,:created,:updated)""", row)
            return row["id"]

    def list(self, query="", kind="", project=""):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM records ORDER BY updated DESC")]
        from core.voice_commands import normalize_command
        q = normalize_command(query)
        return [r for r in rows if (not kind or r["kind"] == kind)
                and (not project or r["project"] == project)
                and (not q or q in normalize_command(" ".join(r[k] for k in ("title","body","tags","project"))))]

    def delete(self, record_id):
        with self.db() as db:
            db.execute("DELETE FROM versions WHERE record_id=?", (record_id,))
            return bool(db.execute("DELETE FROM records WHERE id=?", (record_id,)).rowcount)

    def versions(self, record_id):
        with self.db() as db:
            return [dict(json.loads(r["data"]), saved_at=r["time"]) for r in db.execute(
                "SELECT time,data FROM versions WHERE record_id=? ORDER BY seq DESC", (record_id,))]

    def export(self):
        return json.dumps({"format": "friday-studio-1", "records": self.list()},
                          ensure_ascii=False, indent=2)

    def import_backup(self, text):
        if len(text.encode("utf-8")) > MAX_BACKUP:
            raise ValueError("Yedek çok büyük.")
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != "friday-studio-1":
            raise ValueError("Geçersiz FRIDAY yedeği.")
        rows = data.get("records")
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError("Geçersiz kayıt listesi.")
        clean = [self.validate(row) for row in rows]
        count = 0
        with self.db() as db:
            for row in clean:
                count += db.execute("""INSERT OR IGNORE INTO records VALUES(
                    :id,:kind,:title,:body,:tags,:project,:stage,:confidence,:created,:updated)""", row).rowcount
        return count

    def relationships(self, project=""):
        """Edges reflect explicitly entered project names and shared tags."""
        rows = self.list(project=project)
        nodes = [{"id": r["id"], "title": r["title"], "kind": r["kind"]} for r in rows]
        edges = []
        for i, a in enumerate(rows):
            tags = {x.strip().casefold() for x in a["tags"].split(",") if x.strip()}
            for b in rows[i+1:]:
                shared = tags & {x.strip().casefold() for x in b["tags"].split(",") if x.strip()}
                if a["project"] and a["project"] == b["project"]:
                    shared.add("ortak proje")
                if shared:
                    edges.append({"from": a["id"], "to": b["id"], "reason": ", ".join(sorted(shared))})
        return nodes, edges
