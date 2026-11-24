"""Explicit user-managed records, stored outside the installation.

No background collection, remote upload or execution. Backup import validates
the entire document before writing and merges without replacing existing rows.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid

KINDS = ("project", "idea", "decision", "source", "feedback", "template", "note", "task")
PRIORITIES = ("Normal", "Yüksek", "Acil", "Düşük")
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
                # Separate table: rolling back to the older application leaves
                # its original records schema and record types usable.
                db.execute("""CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    body TEXT NOT NULL, tags TEXT NOT NULL, project TEXT NOT NULL,
                    stage TEXT NOT NULL, confidence TEXT NOT NULL, created TEXT NOT NULL,
                    updated TEXT NOT NULL, due TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'Normal')""")
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
        due, priority = row.get("due", ""), row.get("priority", "Normal")
        if not isinstance(due, str) or len(due) > 10 or priority not in PRIORITIES:
            raise ValueError("Geçersiz tarih veya öncelik.")
        if due and date.fromisoformat(due).isoformat() != due:
            raise ValueError("Tarih YYYY-AA-GG biçiminde olmalı.")
        if out["kind"] != "task" and (due or priority != "Normal"):
            raise ValueError("Son tarih ve öncelik yalnız görevlerde kullanılabilir.")
        out["due"] = due
        out["priority"] = priority
        return out

    @staticmethod
    def _get(db, record_id):
        if not record_id:
            return None
        row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if row is not None:
            return dict(row, due="", priority="Normal")
        row = db.execute("SELECT * FROM tasks WHERE id=?", (record_id,)).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _write(db, row):
        if row["kind"] == "task":
            db.execute("""INSERT OR REPLACE INTO tasks VALUES(
                :id,:kind,:title,:body,:tags,:project,:stage,:confidence,:created,:updated,:due,:priority)""", row)
        else:
            db.execute("""INSERT OR REPLACE INTO records VALUES(
                :id,:kind,:title,:body,:tags,:project,:stage,:confidence,:created,:updated)""", row)

    def save(self, *, kind, title, body="", tags="", project="", stage="Taslak",
             confidence="Belirtilmedi", record_id=None, due=None, priority=None, expected_updated=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self._get(db, record_id)
            if record_id and old is None:
                raise ValueError("Düzenlenecek kayıt bulunamadı.")
            if old and expected_updated is not None and old["updated"] != expected_updated:
                raise ValueError("Kayıt başka bir pencerede değişti; yeniden açın.")
            if old and (old["kind"] == "task") != (kind == "task"):
                raise ValueError("Görev türü diğer kayıt türlerine dönüştürülemez; yeni kayıt oluşturun.")
            if kind != "task" and (due or priority not in (None, "Normal")):
                raise ValueError("Son tarih ve öncelik yalnız görev türünde kullanılabilir.")
            stamp = now()
            row = self.validate(dict(id=record_id or uuid.uuid4().hex, kind=kind, title=title.strip(),
                                     body=body, tags=tags, project=project, stage=stage,
                                     confidence=confidence, created=old["created"] if old else stamp,
                                     updated=stamp,
                                     due=due if due is not None else (old["due"] if old else ""),
                                     priority=priority if priority is not None else (old["priority"] if old else "Normal")))
            if old:
                db.execute("INSERT INTO versions(record_id,time,data) VALUES(?,?,?)",
                           (record_id, stamp, json.dumps(dict(old), ensure_ascii=False)))
            self._write(db, row)
            return row["id"]

    def get(self, record_id):
        with self.db() as db:
            return self._get(db, record_id)

    def restore_version(self, record_id, seq, expected_updated):
        """Restore a single historical snapshot, retaining the current revision."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._get(db, record_id)
            if current is None or current["updated"] != expected_updated:
                raise ValueError("Kayıt değişti veya silindi; yeniden açın.")
            version = db.execute("SELECT data FROM versions WHERE seq=? AND record_id=?",
                                 (seq, record_id)).fetchone()
            if version is None:
                raise ValueError("Sürüm bulunamadı.")
            old = self.validate(json.loads(version["data"]))
            if old["id"] != record_id or (old["kind"] == "task") != (current["kind"] == "task"):
                raise ValueError("Sürüm bu kayda ait değil.")
            stamp = now()
            old["created"], old["updated"] = current["created"], stamp
            db.execute("INSERT INTO versions(record_id,time,data) VALUES(?,?,?)",
                       (record_id, stamp, json.dumps(current, ensure_ascii=False)))
            self._write(db, old)
            return old

    def list(self, query="", kind="", project=""):
        with self.db() as db:
            rows = [dict(r, due="", priority="Normal") for r in db.execute("SELECT * FROM records")]
            rows.extend(dict(r) for r in db.execute("SELECT * FROM tasks"))
            rows.sort(key=lambda r:r["updated"], reverse=True)
        from core.voice_commands import normalize_command
        q = normalize_command(query)
        return [r for r in rows if (not kind or r["kind"] == kind)
                and (not project or r["project"] == project)
                and (not q or q in normalize_command(" ".join(r[k] for k in ("title","body","tags","project"))))]

    def delete(self, record_id):
        with self.db() as db:
            db.execute("DELETE FROM versions WHERE record_id=?", (record_id,))
            removed = db.execute("DELETE FROM records WHERE id=?", (record_id,)).rowcount
            removed += db.execute("DELETE FROM tasks WHERE id=?", (record_id,)).rowcount
            return bool(removed)

    def versions(self, record_id):
        with self.db() as db:
            return [dict(json.loads(r["data"]), saved_at=r["time"], version_seq=r["seq"]) for r in db.execute(
                "SELECT seq,time,data FROM versions WHERE record_id=? ORDER BY seq DESC", (record_id,))]

    def export(self):
        rows = self.list()
        result = json.dumps({"format": "friday-studio-1", "records": rows}, ensure_ascii=False, indent=2)
        if len(rows) > 10000 or len(result.encode("utf-8")) > MAX_BACKUP:
            raise ValueError("Arşiv tek yedek sınırını aşıyor; mevcut dosya değiştirilmedi.")
        return result

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
            db.execute("BEGIN IMMEDIATE")
            for row in clean:
                if self._get(db,row["id"]) is None:
                    self._write(db,row)
                    count += 1
        return count

    def task_overview(self, project="", today=None):
        """A local snapshot only; no reminders, uploads or actions."""
        today = date.today() if today is None else date.fromisoformat(today)
        rows = self.list(kind="task", project=project)
        counts = {"open": 0, "overdue": 0, "today": 0, "completed": 0, "archived": 0}
        priority_order = {"Acil": 0, "Yüksek": 1, "Normal": 2, "Düşük": 3}
        for r in rows:
            if r["stage"] == "Tamamlandı":
                state = "completed"
            elif r["stage"] == "Arşiv":
                state = "archived"
            else:
                counts["open"] += 1
                due = date.fromisoformat(r["due"]) if r["due"] else None
                state = "overdue" if due and due < today else "today" if due == today else "open"
                if state != "open":
                    counts[state] += 1
            if state in ("completed", "archived"):
                counts[state] += 1
            r["task_state"] = state
        state_order = {"overdue": 0, "today": 1, "open": 2, "completed": 3, "archived": 4}
        rows.sort(key=lambda r: (state_order[r["task_state"]], priority_order[r["priority"]],
                                r["due"] or "9999-12-31", r["title"].casefold()))
        return counts, rows

    def relationships(self, project="", limit=200):
        """Edges reflect explicitly entered project names and shared tags."""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Bağlantı görünümü 1–200 kayıtla sınırlıdır.")
        rows = self.list(project=project)[:limit]
        nodes = [{"id": r["id"], "title": r["title"], "kind": r["kind"]} for r in rows]
        edges = []
        tag_sets = {r["id"]: {x.strip().casefold() for x in r["tags"].split(",") if x.strip()} for r in rows}
        for i, a in enumerate(rows):
            tags = tag_sets[a["id"]]
            for b in rows[i+1:]:
                shared = tags & tag_sets[b["id"]]
                if a["project"] and a["project"] == b["project"]:
                    shared.add("ortak proje")
                if shared:
                    edges.append({"from": a["id"], "to": b["id"], "reason": ", ".join(sorted(shared))})
        return nodes, edges
