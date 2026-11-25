"""Fixed, offline component checks. No model, code agent or real device actions.

Each check runs against a temporary source/data copy in a separate process.
Passing a component check is deliberately not a live-service/hardware claim.
"""
from __future__ import annotations
import argparse
from contextlib import redirect_stdout, redirect_stderr
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 20
AREAS = (
    ('voice', 'Ses ve konuşma', 'Türkçe döküm birleştirme ve ses kuyruğu', 'Mikrofon, hoparlör ve canlı ses denenmedi.'),
    ('memory', 'Hafıza', 'Geçici hafızaya yazma, arama, unutma ve tombstone', 'Kişisel hafıza ve gerçek cihaz eşitlemesi kullanılmadı.'),
    ('models', 'Model yönlendirme', 'Araç şemasını sağlayıcı biçimine dönüştürme', 'Canlı model, hesap, kota ve ağ bağlantısı denenmedi.'),
    ('coding', 'Kod ajanı', 'Bozuk Python kodunu saptama', 'Kod ajanı başlatılmadı; kaynak kod değiştirilmedi.'),
    ('updates', 'Güncelleme', 'ZIP içerik ve güvensiz yol doğrulaması', 'Gerçek kurulum güncellenmedi; yeniden başlatma yapılmadı.'),
    ('security', 'Güvenlik', 'Sahte onay tokenını reddetme ve iptal', 'Gerçek onay penceresi veya etkili işlem açılmadı.'),
    ('devices', 'Cihazlar', 'Ses sahibi seçimi ve boş cihaz listesi', 'Telefon ve akıllı ev cihazlarına bağlanılmadı.'),
    ('interface', 'Arayüz', '3D yüz geometrisi ve sonlu koordinatlar', 'Qt penceresi, GPU ve görsel kalite denenmedi.'),
    ('research', 'Araştırma', 'Belirsiz kitap sonucunu indirmeden reddetme', 'Sentetik HTTP yanıtı; internette araştırma yapılmadı.'),
    ('automation', 'Otomasyon', 'İşlem sonucunda doğrulanmadı/başarısız ayrımı', 'Gerçek tarayıcı, klavye veya fare kullanılmadı.'),
    ('integrations', 'Eklentiler', 'Holo Masa OBJ içe/dışa aktarma', 'Blender, kamera ve harici entegrasyonlar açılmadı.'),
    ('tasks', 'Uzun işler', 'Görev bağlamını sınırlama', 'Gerçek kullanıcı görevi başlatılmadı.'),
)


def _expect(condition, message):
    if not condition:
        raise AssertionError(message)


def _voice():
    from core.live_transcript import merge_input_chunk, combined_text
    from providers.engine_pipeline import PipelineEngine
    from providers.base import Msg
    chunks = merge_input_chunk(['ışığı aç'], 'ışığı aç lütfen')
    _expect(combined_text(chunks) == 'ışığı aç lütfen', 'Türkçe döküm tekrarsız birleşmedi.')
    async def check():
        engine = PipelineEngine(None)
        _expect(engine._queue.maxsize > 0, 'Ses çıktı kuyruğunun sınırı yok.')
        await engine._emit(Msg.audio(b'\x01\0' * 20))
        iterator = engine.receive()
        _expect((await anext(iterator)).data == b'\x01\0' * 20, 'PCM çıktısı değişti.')
        await engine.close()
        _expect(await anext(iterator, None) is None, 'Ses kuyruğu kapanmadı.')
    asyncio.run(check())


def _memory():
    from memory import memory_manager as memory, continuity
    from core.sync_hub import merge_memory
    memory.remember('monitor_fixture', 'mor lamba')
    _expect('mor lamba' in memory.search_memory('mor lamba'), 'Hafıza araması kaydı bulmadı.')
    old = memory.load_memory()
    memory.forget('monitor_fixture')
    merged = merge_memory(memory.load_memory(), old)
    _expect('monitor_fixture' not in merged.get('notes', {}), 'Unutulan kayıt eşitlemeyle geri geldi.')
    continuity.record('Kullanıcı', 'mor lamba denetimi')
    _expect('mor lamba' in continuity.search('mor lamba'), 'SQLite geçmiş araması kaydı bulmadı.')


def _models():
    from providers.schema import to_openai
    tools = to_openai([{'name': 'monitor_fixture', 'description': 'fixture',
                       'parameters': {'type': 'OBJECT', 'properties': {'topic': {'type': 'STRING'}}}}])
    _expect(tools[0]['function']['name'] == 'monitor_fixture', 'Araç adı şemada değişti.')
    _expect(tools[0]['function']['parameters']['type'] == 'object', 'Araç şeması dönüştürülemedi.')


def _coding():
    from core.code_checks import syntax_problems
    with tempfile.TemporaryDirectory() as directory:
        problems = syntax_problems(Path(directory), {'broken.py': 'def broken(:\n'})
    _expect('broken.py' in problems, 'Kod denetimi bozuk Python kodunu kabul etti.')


def _updates():
    from core.app_updater import _archive
    def archive(extra):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as file:
            for name in ('main.py', 'requirements.txt', 'gui/window.py'):
                file.writestr('repo/' + name, b'fixture')
            if extra:
                file.writestr('repo/../escape.py', b'fixture')
        return buffer.getvalue()
    _expect('main.py' in _archive(archive(False)), 'Geçerli ZIP okunamadı.')
    try:
        _archive(archive(True))
    except RuntimeError:
        return
    raise AssertionError('Güvensiz ZIP yolu reddedilmedi.')


def _security():
    from core import confirm
    tokens, effects = [], []
    confirm.bind(lambda *args: tokens.append(args[-1]), lambda: None)
    confirm.request('monitor_fixture', 'Sentetik kontrol', 'Test verisi', lambda: effects.append(True))
    _expect(tokens, 'Onay isteği oluşmadı.')
    confirm.resolve(True, 'invalid-monitor-token')
    _expect(not effects and confirm.pending_title(), 'Sahte token işlemi onayladı.')
    confirm.resolve(False, tokens[0])
    _expect(not effects and not confirm.pending_title(), 'İptal edilen onay kapanmadı.')


def _devices():
    from core.sync_hub import voice_owner
    _expect(voice_owner([], time.time()) is None, 'Boş cihaz listesi ses sahibi seçti.')


def _interface():
    import numpy as np
    from core.avatar import get_head_mesh
    mesh = get_head_mesh()
    _expect(len(mesh['verts']) > 100 and len(mesh['faces']) > 100, 'Yüz geometrisi eksik.')
    _expect(np.isfinite(mesh['verts']).all(), 'Yüz geometrisinde geçersiz koordinat var.')


def _research():
    from unittest.mock import Mock, patch
    from core import scan_research
    response = Mock()
    response.json.return_value = {'results': [
        {'id': 1, 'title': 'Fixture', 'copyright': False},
        {'id': 2, 'title': 'Fixture', 'copyright': False}]}
    with patch.object(scan_research.httpx, 'get', return_value=response), \
         patch.object(scan_research.httpx, 'stream') as download:
        _expect(scan_research._gutenberg('Fixture', '') == [], 'Belirsiz sonuç kabul edildi.')
        _expect(not download.called, 'Belirsiz kitap için indirme başladı.')


def _automation():
    from core import outcome
    _expect('status=unverified' in outcome.unverified('fixture', 'Not observed'), 'Doğrulanmadı durumu kayboldu.')
    _expect(outcome.is_problem(outcome.failed('fixture', 'synthetic')), 'Başarısız sonuç tanınmadı.')
    _expect(not outcome.is_problem(outcome.done('fixture', verified=True)), 'Doğrulanmış sonuç hatalı işaretlendi.')


def _integrations():
    import numpy as np
    from core.holo_desk import mesh, obj_text, parse_obj
    vertices, faces = mesh("Küp")
    restored, triangles = parse_obj(obj_text(vertices, faces))
    again, _ = parse_obj(obj_text(restored, triangles))
    _expect(np.allclose(again, restored, atol=1e-5), 'OBJ tekrar aktarımda değişti.')
    _expect(len(faces) == len(triangles), 'OBJ yüz sayısı değişti.')


def _tasks():
    from core.tasks.engine import trim_turns
    turns = [{'role': 'tool', 'results': [{'result': 'fixture ' * 1000}]} for _ in range(20)]
    limited = trim_turns(turns, limit=2000)
    _expect(len(limited) == len(turns) and len(limited[0]['results'][0]['result']) < len(turns[0]['results'][0]['result']), 'Görev bağlamı sınırlanmadı.')


CHECKS = {key: globals()['_' + key] for key, *_ in AREAS}


def _external_network_off():
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original(sock, address)  # asyncio's internal socketpair on Windows
        raise PermissionError('Feature checks cannot connect to external services')
    socket.socket.connect = connect
    socket.socket.connect_ex = lambda *args: 1
    socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('Offline check'))


def _child(area, output):
    expected = str(ROOT.parent / 'data')
    isolated = (os.environ.get('FRIDAY_FEATURE_CHECK_ROOT') == str(ROOT)
                and ROOT.parent.name.startswith('friday-feature-check-')
                and all(os.environ.get(name) == expected
                        for name in ('LOCALAPPDATA', 'APPDATA', 'XDG_DATA_HOME')))
    if not isolated:
        with output.open('x', encoding='utf-8') as file:
            json.dump({'area': area, 'status': 'unverified',
                       'detail': 'Denetim yalnızca geçici kaynak/veri kopyasında çalışabilir.'}, file)
        return
    _external_network_off()
    started = time.monotonic()
    result = {'area': area, 'status': 'passed', 'detail': 'Yerel bileşen kontrolü geçti.'}
    try:
        class CappedLog(io.StringIO):
            def write(self, text):
                super().write(text[:max(0, 32768 - self.tell())])
                return len(text)
        captured = CappedLog()
        with redirect_stdout(captured), redirect_stderr(captured):
            CHECKS[area]()
    except (ImportError, ModuleNotFoundError) as exc:
        result.update(status='unverified', detail='Bağımlılık yüklenemedi: ' + type(exc).__name__)
    except Exception as exc:
        frames = traceback.extract_tb(exc.__traceback__)
        location = frames[-1] if frames else None
        path = Path(location.filename) if location else None
        relative = (str(path.relative_to(ROOT)) if path and path.is_relative_to(ROOT)
                    else path.name if path else '')
        result.update(status='failed', detail=f'{type(exc).__name__}: {str(exc)[:400]}',
                      location=f'{relative}:{location.lineno}' if location else '')
    if sys.stdout is not None and 'captured' in locals():
        sys.stdout.write(captured.getvalue())
    result['duration_ms'] = round((time.monotonic() - started) * 1000, 2)
    with output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False)


def _safe_source(file, root):
    relative = file.relative_to(root)
    return file.is_file() and not any(root.joinpath(*relative.parts[:i]).is_symlink()
                                      for i in range(1, len(relative.parts) + 1))


def _sources(root):
    # Fixed source directories only: no user config/history, checkouts, tests,
    # uploads, symlinks or arbitrary script paths enter the test process.
    for folder in ('core', 'providers', 'actions', 'plugins', 'gui', 'dashboard'):
        for file in sorted((root / folder).rglob('*.py')):
            if _safe_source(file, root) and not any(p.startswith('.') or p == '__pycache__' for p in file.relative_to(root).parts):
                yield file
    for file in sorted((root / 'memory').glob('*.py')):
        if _safe_source(file, root):
            yield file
    for name in ('config/__init__.py', 'core/face_model.obj'):
        file = root / name
        if _safe_source(file, root):
            yield file


def run_check(area, stop_event, root=ROOT):
    if area not in CHECKS:
        raise ValueError('Unknown feature check')
    if getattr(sys, 'frozen', False):
        return {'status': 'unverified', 'detail': 'Bu paket ayrı Python denetim sürecini desteklemiyor.'}
    with tempfile.TemporaryDirectory(prefix='friday-feature-check-') as directory:
        scratch = Path(directory).resolve()
        source = scratch / 'source'
        original = {}
        total = 0
        for file in _sources(root):
            if stop_event.is_set():
                return {'status': 'cancelled', 'detail': 'Kontrol durduruldu.'}
            data = file.read_bytes()
            total += len(data)
            if total > 40 * 1024 * 1024:
                return {'status': 'unverified', 'detail': 'Denetim kaynağı boyut sınırını aşıyor.'}
            relative = file.relative_to(root)
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            original[file] = hashlib.sha256(data).digest()
        output = scratch / 'result.json'
        env = {key: value for key, value in os.environ.items()
               if not any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL'))
               and not key.startswith(('PYTHON', 'QT_'))}
        env.update(LOCALAPPDATA=str(scratch / 'data'), APPDATA=str(scratch / 'data'),
                   XDG_DATA_HOME=str(scratch / 'data'), PYTHONUTF8='1', QT_QPA_PLATFORM='offscreen',
                   FRIDAY_FEATURE_CHECK_ROOT=str(source))
        started = time.monotonic()
        with (scratch / 'process.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-m', 'core.feature_checks', '--area', area,
                                        '--result', str(output)], cwd=source, env=env, stdout=log, stderr=log)
            try:
                while process.poll() is None:
                    if stop_event.wait(.1):
                        return {'status': 'cancelled', 'detail': 'Kontrol durduruldu.'}
                    if time.monotonic() - started > TIMEOUT:
                        return {'status': 'failed', 'detail': f'Denetim {TIMEOUT:g} saniyede tamamlanmadı (zaman aşımı).'}
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            if process.returncode or not output.is_file():
                return {'status': 'unverified', 'detail': f'Denetim süreci sonuç üretmedi (çıkış {process.returncode}).'}
        for file, digest in original.items():
            if not file.is_file() or file.is_symlink() or hashlib.sha256(file.read_bytes()).digest() != digest:
                return {'status': 'unverified', 'detail': 'Kaynak sürümü kontrol sırasında değişti; sonuç geçersiz.'}
        result = json.loads(output.read_text(encoding='utf-8'))
        if result.get('status') not in ('passed', 'failed', 'unverified') or result.get('area') != area:
            raise ValueError('Geçersiz denetim sonucu')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--area', choices=CHECKS, required=True)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    _child(args.area, args.result)
