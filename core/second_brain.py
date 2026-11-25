"""Historical improvement records retained; autonomous development is disabled."""
import threading
from datetime import datetime, timezone

from memory.continuity import connect, _write_lock

_LABELS = {"idea": "Fikir", "requested": "Hazırlanıyor", "running": "Geliştiriliyor",
           "verified": "Testleri geçti", "failed": "Kontroller başarısız",
           "unverified": "Doğrulanamadı", "dismissed": "Arşivlendi"}
_scan_lock = threading.Lock()


def _table(db):
    db.execute("CREATE TABLE IF NOT EXISTS improvements (id INTEGER PRIMARY KEY, title TEXT NOT NULL,"
               " detail TEXT NOT NULL, source TEXT UNIQUE, state TEXT NOT NULL DEFAULT 'idea',"
               " analysis TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '', baseline INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL)")


def add(title, detail="", source=None):
    title, detail = str(title).strip()[:160], str(detail).strip()[:4000]
    if not title:
        raise ValueError("Geliştirme fikrini yazın.")
    with _write_lock, connect() as db:
        _table(db)
        db.execute("INSERT OR IGNORE INTO improvements(title,detail,source,updated) VALUES(?,?,?,?)",
                   (title, detail, source, datetime.now(timezone.utc).isoformat()))


def items(*, active_only=False):
    with connect() as db:
        _table(db)
        where = " WHERE state IN ('requested','running')" if active_only else ""
        limit = "" if active_only else " LIMIT 100"
        rows = db.execute("SELECT id,title,detail,state,analysis,result FROM improvements" + where +
                          " ORDER BY CASE state WHEN 'running' THEN 0 WHEN 'failed' THEN 1 "
                          "WHEN 'idea' THEN 2 ELSE 3 END,id DESC" + limit).fetchall()
    return [dict(zip(("id", "title", "detail", "state", "analysis", "result"), row)) for row in rows]


def _get(item_id):
    with connect() as db:
        _table(db)
        row = db.execute("SELECT id,title,detail,state,analysis,result FROM improvements WHERE id=?", (int(item_id),)).fetchone()
    if not row:
        raise ValueError("Geliştirme kaydı bulunamadı.")
    return dict(zip(("id", "title", "detail", "state", "analysis", "result"), row))


def update(item_id, *, state=None, analysis=None, result=None):
    if state is not None and state not in _LABELS:
        raise ValueError("Geçersiz geliştirme durumu.")
    with _write_lock, connect() as db:
        _table(db)
        db.execute("UPDATE improvements SET state=COALESCE(?,state),analysis=COALESCE(?,analysis),result=COALESCE(?,result),updated=? WHERE id=?",
                   (state, analysis, result, datetime.now(timezone.utc).isoformat(), item_id))


def scan():
    """Collect evidenced failures and reconcile agent jobs without model calls."""
    if not _scan_lock.acquire(False):
        return
    try:
        from memory.continuity import projects, project_with_marker
        jobs = projects(limit=200)
        for job in jobs:
            if (job["status"] in ("başarısız", "sorunlu bitti", "aşama bekliyor")
                    and "[SECOND_BRAIN:" not in job["instruction"]):
                add("Kod işini incele · " + job["title"], job["note"], "project:" + str(job["id"]))
        for item in items(active_only=True):
            marker = f"[SECOND_BRAIN:{item['id']}]"
            with connect() as db:
                baseline = db.execute("SELECT baseline FROM improvements WHERE id=?", (item["id"],)).fetchone()[0]
            job = project_with_marker(marker, after_id=baseline)
            if job:
                state = {"çalışıyor": "running", "bitti": "verified",
                         "başarısız": "failed", "sorunlu bitti": "failed"}.get(job["status"], "unverified")
                update(item["id"], state=state, result=job["note"])
            else:
                with connect() as db:
                    updated = db.execute("SELECT updated FROM improvements WHERE id=?", (item["id"],)).fetchone()[0]
                if (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds() > 300:
                    reason = ("Beş dakika içinde kod ajanının başladığı doğrulanamadı."
                              if item["state"] == "requested" else
                              "İzlenen geliştirmeyle eşleşen kod işi kaydı bulunamadı.")
                    update(item["id"], state="unverified", result=reason + " Günlüğü inceleyin.")
    finally:
        _scan_lock.release()


def analyze(item_id):
    raise ValueError("İkincil beyin yalnızca özellik denetler; geliştirme planlamaz.")


def develop(item_id, player):
    raise ValueError("İkincil beyin kod yazmaz veya kod ajanı başlatmaz. Hata raporunu kullanın.")
