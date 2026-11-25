"""Recurring local feature checks and evidence, never autonomous development."""
import threading
import time
from core.feature_checks import AREAS as COMPONENT_AREAS, run_check

AREAS = COMPONENT_AREAS + (('watchers', 'Canlı izleme', 'Çalışan arka plan izleyicilerinin kalp atışı',
                            'Henüz başlamamış izleyici başarı sayılmaz; mikrofon/model bağlantısını doğrulamaz.'),)
from memory.continuity import connect, _write_lock

INTERVAL = 60
LABELS = {'passed': 'Geçti', 'failed': 'Hata', 'unverified': 'Doğrulanmadı',
          'running': 'Deneniyor', 'cancelled': 'Durduruldu'}


def _tables(db):
    db.execute('CREATE TABLE IF NOT EXISTS brain_monitor_runtime ('
               'id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 1,'
               'due REAL NOT NULL DEFAULT 0,cursor INTEGER NOT NULL DEFAULT 0)')
    # Preserve the old pause preference, without resuming an old code job.
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brain_runtime'").fetchone()
    old = db.execute('SELECT enabled FROM brain_runtime WHERE id=1').fetchone() if exists else None
    db.execute('INSERT OR IGNORE INTO brain_monitor_runtime(id,enabled) VALUES(1,?)', (old[0] if old else 1,))
    db.execute('CREATE TABLE IF NOT EXISTS brain_checks (area TEXT PRIMARY KEY,status TEXT NOT NULL,'
               'detail TEXT NOT NULL,location TEXT NOT NULL DEFAULT \'\',duration_ms REAL NOT NULL DEFAULT 0,updated REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS brain_check_events (id INTEGER PRIMARY KEY,time REAL,'
               'area TEXT,status TEXT,detail TEXT)')


def settings():
    with _write_lock, connect() as db:
        _tables(db)
        row = db.execute('SELECT enabled,due,cursor FROM brain_monitor_runtime WHERE id=1').fetchone()
    return dict(zip(('enabled', 'due', 'cursor'), row))


def set_enabled(enabled):
    with _write_lock, connect() as db:
        _tables(db)
        db.execute('UPDATE brain_monitor_runtime SET enabled=? WHERE id=1', (int(bool(enabled)),))


def events():
    with _write_lock, connect() as db:
        _tables(db)
        return [dict(zip(('time', 'area', 'status', 'detail'), row)) for row in db.execute(
            'SELECT time,area,status,detail FROM brain_check_events ORDER BY id DESC LIMIT 100')]


def results():
    with _write_lock, connect() as db:
        _tables(db)
        return [dict(zip(('area', 'status', 'detail', 'location', 'duration_ms', 'updated'), row))
                for row in db.execute('SELECT area,status,detail,location,duration_ms,updated FROM brain_checks')]


def _record(area, status, detail, *, location='', duration_ms=0):
    if status not in LABELS:
        raise ValueError('Invalid feature check status')
    with _write_lock, connect() as db:
        _tables(db)
        db.execute('INSERT INTO brain_check_events(time,area,status,detail) VALUES(?,?,?,?)',
                   (time.time(), area, status, str(detail)[:2000]))
        db.execute('DELETE FROM brain_check_events WHERE id < (SELECT MAX(id)-499 FROM brain_check_events)')
        db.execute('INSERT INTO brain_checks(area,status,detail,location,duration_ms,updated) VALUES(?,?,?,?,?,?) '
                   'ON CONFLICT(area) DO UPDATE SET status=excluded.status,detail=excluded.detail,'
                   'location=excluded.location,duration_ms=excluded.duration_ms,updated=excluded.updated',
                   (area, status, str(detail)[:2000], str(location)[:200], max(0, float(duration_ms)), time.time()))


def _claim(now):
    with _write_lock, connect() as db:
        _tables(db)
        row = db.execute('UPDATE brain_monitor_runtime SET due=?,cursor=cursor+1 '
                         'WHERE id=1 AND enabled=1 AND due<=? RETURNING cursor-1',
                         (now + INTERVAL, now)).fetchone()
        return row[0] % len(AREAS) if row else None


def report(snapshot):
    areas = {area: (label, scope, limits) for area, label, scope, limits in AREAS}
    lines = ['FRIDAY · İkincil beyin özellik denetimi',
             'Yerel bileşen testleri; canlı hizmet ve donanım kabulü değildir.']
    for row in snapshot.get('results', []):
        label, scope, limits = areas.get(row['area'], (row['area'], '', ''))
        when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['updated']))
        lines.append(f"{label} · {LABELS.get(row['status'], row['status'])} · {when}\n"
                     f"Kontrol: {scope}\n{row['detail']}\n{row.get('location', '')}\n"
                     f"Süre: {row['duration_ms']:.0f} ms\nSınır: {limits}")
    return '\n\n'.join(lines)


def live_watchers():
    from core import heartbeat
    states = heartbeat.status()
    failed = [name for name, state in states.items() if not state['ok']]
    active = [name for name, state in states.items() if state['age'] is not None]
    if failed:
        return {'status': 'failed', 'detail': 'Yanıt vermeyen arka plan izleyicisi: ' + ', '.join(failed)[:300]}
    if not active:
        return {'status': 'unverified', 'detail': 'Henüz çalışan izleyiciden kalp atışı alınmadı.'}
    return {'status': 'passed', 'detail': f'{len(active)} etkin arka plan izleyicisinin kalp atışı güncel. Başlamayanlar doğrulanmadı.'}


class Controller:
    def __init__(self, player, ready=None):
        self.player = player
        self.ready = ready or (lambda: True)
        self.stop_event = threading.Event()
        self._cancel = threading.Event()
        self._cycle_lock = threading.Lock()
        self.thread = None
        self.startup_at = 0.0
        self.area = ''
        self.phase = 'Başlangıç bekleniyor'

    def snapshot(self):
        state = settings()
        rows = results()
        # A killed process is never a permanently live or successful check.
        for row in rows:
            if row['status'] == 'running' and time.time() - row['updated'] > 35:
                row.update(status='unverified', detail='Önceki kontrol yarıda kaldı; yeniden denenecek.')
        return {'area': self.area, 'phase': self.phase, 'enabled': bool(state['enabled']),
                'next_due': max(state['due'], self.startup_at), 'events': events(), 'results': rows}

    def pause(self):
        set_enabled(False)
        self._cancel.set()

    def resume(self):
        set_enabled(True)

    def cycle(self, now=None):
        if not self._cycle_lock.acquire(False):
            return
        try:
            if self.stop_event.is_set() or not settings()['enabled']:
                return
            if not self.ready():
                self.phase = 'İlk kurulum bekleniyor'
                return
            index = _claim(time.time() if now is None else now)
            if index is None:
                return
            area, label, scope, _ = AREAS[index]
            previous = next((row for row in results() if row['area'] == area), {})
            self.area, self.phase = area, 'Deneniyor'
            self._cancel.clear()
            if self.stop_event.is_set() or not settings()['enabled']:
                return
            _record(area, 'running', scope)
            try:
                result = live_watchers() if area == 'watchers' else run_check(area, self._cancel)
                status = result['status']
                detail = result['detail']
                _record(area, status, detail, location=result.get('location', ''),
                        duration_ms=result.get('duration_ms', 0))
            except Exception as exc:
                status, detail = 'unverified', 'Denetim çalıştırılamadı: ' + type(exc).__name__
                _record(area, status, detail)
            self.phase = LABELS[status]
            if status in ('failed', 'unverified') and (previous.get('status') != status or previous.get('detail') != detail):
                self.player.write_log(f'İKİNCİL BEYİN · {label}: {detail} Beyin panelinden hata raporunu kopyalayabilirsin.')
            elif status == 'passed' and previous.get('status') in ('failed', 'unverified'):
                self.player.write_log(f'İKİNCİL BEYİN · {label}: önceki başarısız yerel kontrol artık geçti.')
        finally:
            self._cycle_lock.release()

    def start(self, delay=45):
        if self.thread and self.thread.is_alive():
            return
        self.startup_at = time.time() + delay
        def work():
            if self.stop_event.wait(delay):
                return
            while not self.stop_event.is_set():
                try:
                    self.cycle()
                except Exception as exc:
                    self.phase = 'Doğrulanmadı'
                    self.player.write_log('İKİNCİL BEYİN · İzleme hatası: ' + type(exc).__name__)
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=work, daemon=True, name='friday-feature-monitor')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self._cancel.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
