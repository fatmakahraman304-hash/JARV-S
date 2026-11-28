"""Local personal tasks, stored live in the existing encrypted task journal."""
import json
import os
import uuid
from datetime import date, datetime

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.tasks.secure_checkpoint import TaskCheckpoint


def agenda(engine, action, params, player):
    if not callable(getattr(player, "show_content", None)):
        raise ValueError("local display required")
    day = date.fromisoformat(params.get("day") or date.today().isoformat())
    with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
        db = archive._db
        cipher = AESGCM(archive._journal.key)
        db.execute("CREATE TABLE IF NOT EXISTS personal_tasks(id TEXT PRIMARY KEY, data BLOB NOT NULL)")

        def read(ident, blob):
            return json.loads(cipher.decrypt(blob[:12], blob[12:], b"agenda/v1/" + ident.encode()))

        def write(ident, item):
            nonce = os.urandom(12)
            blob = nonce + cipher.encrypt(nonce, json.dumps(item).encode(), b"agenda/v1/" + ident.encode())
            db.execute("INSERT OR REPLACE INTO personal_tasks VALUES (?,?)", (ident, blob))
            stored = db.execute("SELECT data FROM personal_tasks WHERE id=?", (ident,)).fetchone()[0]
            if read(ident, stored) != item:
                raise ValueError("task verification failed")

        if action == "agenda_add":
            title = str(params.get("task") or "").strip()
            if not 1 <= len(title) <= 300:
                raise ValueError("invalid personal task title")
            ident = uuid.uuid4().hex
            with db:
                write(ident, {"day": day.isoformat(), "title": title, "done": False})
            return "Personal task saved. ID " + ident
        if action == "agenda_complete":
            ident = str(params.get("task_id") or "")
            row = db.execute("SELECT data FROM personal_tasks WHERE id=?", (ident,)).fetchone()
            if not row:
                raise ValueError("unknown personal task")
            item = read(ident, row[0])
            item["done"] = True
            with db:
                write(ident, item)
            return "Personal task marked complete."
        rows = []
        for ident, blob in db.execute("SELECT id,data FROM personal_tasks ORDER BY rowid"):
            item = read(ident, blob)
            if item["day"] == day.isoformat():
                status = "Tamamlandı" if item["done"] else "Bekliyor"
                rows.append(f"{status} · {item['title']} [{ident}]")
    from core.routines import desktop
    routines = desktop.engine()
    if routines is None:
        rows.append("Rutin motoruna ulaşılamadı.")
    else:
        for routine in sorted(routines.list(), key=lambda r: r.get("next_ts") or 0):
            stamp = routine.get("next_ts")
            if routine.get("enabled") and stamp:
                when = datetime.fromtimestamp(stamp)
                if when.date() == day:
                    rows.append(f"{when:%H:%M} · {routine['name']}")
    player.show_content("GÜNLÜK PLAN · " + day.isoformat(), "\n".join(rows) or "Bu tarih için kayıt yok.")
    return "Daily plan shown locally."
