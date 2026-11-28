"""Local personal tasks, stored live in the existing encrypted task journal."""
import json
import os
import uuid
from datetime import date, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.tasks.secure_checkpoint import TaskCheckpoint


PRIORITIES = {"high": "Yüksek", "normal": "Normal", "low": "Düşük"}


def read_record(cipher, ident, blob):
    return json.loads(cipher.decrypt(blob[:12], blob[12:], b"agenda/v1/" + ident.encode()))


def schedule_fields(params):
    priority = params.get("priority", "normal")
    if priority not in PRIORITIES:
        raise ValueError("invalid priority")
    fields = {"priority": priority}
    if "start_time" in params or "duration" in params:
        clock = datetime.strptime(params["start_time"], "%H:%M")
        start = clock.hour * 60 + clock.minute
        minutes = params.get("duration")
        if type(minutes) is not int or not 1 <= minutes <= 1440 - start:
            raise ValueError("time block must fit within the selected day")
        fields.update(start=start, duration=minutes)
    return fields


def clock_text(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def agenda(engine, action, params, player):
    if not callable(getattr(player, "show_content", None)):
        raise ValueError("local display required")
    day = date.fromisoformat(params.get("day") or date.today().isoformat())
    with TaskCheckpoint(engine.store.root / "_encrypted_checkpoint") as archive:
        db = archive._db
        cipher = AESGCM(archive._journal.key)
        db.execute("CREATE TABLE IF NOT EXISTS personal_tasks(id TEXT PRIMARY KEY, data BLOB NOT NULL)")

        def write(ident, item):
            nonce = os.urandom(12)
            blob = nonce + cipher.encrypt(nonce, json.dumps(item).encode(), b"agenda/v1/" + ident.encode())
            db.execute("INSERT OR REPLACE INTO personal_tasks VALUES (?,?)", (ident, blob))
            stored = db.execute("SELECT data FROM personal_tasks WHERE id=?", (ident,)).fetchone()[0]
            if read_record(cipher, ident, stored) != item:
                raise ValueError("task verification failed")

        if action == "agenda_add":
            title = str(params.get("task") or "").strip()
            if not 1 <= len(title) <= 300:
                raise ValueError("invalid personal task title")
            ident = uuid.uuid4().hex
            with db:
                write(ident, {"day": day.isoformat(), "title": title, "done": False, **schedule_fields(params)})
            return "Personal task saved. ID " + ident
        if action in ("agenda_complete", "agenda_reschedule"):
            ident = str(params.get("task_id") or "")
            row = db.execute("SELECT data FROM personal_tasks WHERE id=?", (ident,)).fetchone()
            if not row:
                raise ValueError("unknown personal task")
            item = read_record(cipher, ident, row[0])
            if action == "agenda_complete":
                item["done"] = True
            else:
                if not any(key in params for key in ("day", "priority", "start_time")):
                    raise ValueError("no schedule change supplied")
                item.update(schedule_fields({"priority": item.get("priority", "normal"), **params}))
                if "day" in params:
                    item["day"] = day.isoformat()
            with db:
                write(ident, item)
            return "Personal task marked complete." if action == "agenda_complete" else "Personal schedule updated."
        monday = day - timedelta(days=day.weekday())
        tasks = []
        for ident, blob in db.execute("SELECT id,data FROM personal_tasks ORDER BY rowid"):
            item = read_record(cipher, ident, blob)
            scheduled = date.fromisoformat(item["day"])
            matches = scheduled == day
            if action == "agenda_week":
                matches = 0 <= (scheduled - monday).days < 7
            if matches:
                tasks.append((ident, item))
    if action == "agenda_week":
        done = sum(item["done"] for _, item in tasks)
        player.show_content("HAFTALIK İLERLEME", f"{monday} – {monday + timedelta(days=6)}"
                            + f"\nBu haftaya planlanan {len(tasks)} görevin {done} tanesi tamamlandı.")
        return "Weekly progress shown locally."
    rows = []
    blocks = sorted((item["start"], item["start"] + item["duration"], ident)
                    for ident, item in tasks if not item["done"] and "start" in item)
    for ident, item in sorted(tasks, key=lambda pair: (pair[1]["done"],
                              list(PRIORITIES).index(pair[1].get("priority", "normal")), pair[1].get("start", 1440))):
        status = "Tamamlandı" if item["done"] else "Bekliyor"
        label = PRIORITIES[item.get("priority", "normal")]
        line = f"{status} · {item['title']} [{ident}] · {label}"
        if "start" in item:
            start, duration = item["start"], item["duration"]
            line += f" · {clock_text(start)}–{clock_text(start + duration)}"
            if not item["done"]:
                candidate = start
                for left, right, other in blocks:
                    if other != ident and candidate < right and left < candidate + duration:
                        candidate = right
                if candidate != start:
                    line += " · Çakışma"
                    if candidate + duration <= 1440:
                        line += f" · Öneri {clock_text(candidate)}"
        rows.append(line)
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
