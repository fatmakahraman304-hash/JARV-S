"""Periodic feature monitoring never asks a model or starts development."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from core import second_brain_service as service
from memory import continuity


class FeatureMonitor(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(continuity, 'data_dir', return_value=self.root / 'data'))
        self.player = Mock()
        self.controller = service.Controller(self.player)

    def result(self, status='passed', detail='fixture'):
        return {'status': status, 'detail': detail, 'duration_ms': 2}

    def test_cycle_checks_a_feature_without_model_or_code_agent(self):
        with patch.object(service, 'run_check', return_value=self.result()) as check, \
             patch('core.gemini.as_json') as model, patch('core.second_brain.develop') as develop:
            self.controller.cycle(now=100)
        check.assert_called_once_with('voice', self.controller._cancel)
        model.assert_not_called()
        develop.assert_not_called()
        self.assertEqual(service.results()[0]['status'], 'passed')
        self.player.write_log.assert_not_called()

    def test_pause_and_cooldown_survive_restart(self):
        self.controller.pause()
        with patch.object(service, 'run_check') as check:
            service.Controller(Mock()).cycle(now=100)
            check.assert_not_called()
        self.controller.resume()
        with patch.object(service, 'run_check', return_value=self.result()) as check:
            self.controller.cycle(now=100)
            service.Controller(Mock()).cycle(now=101)
            self.assertEqual(check.call_count, 1)
        self.assertGreater(service.settings()['due'], 101)

    def test_old_pause_migrates_without_starting_or_deleting_old_work(self):
        with continuity.connect() as db:
            db.execute('CREATE TABLE brain_runtime(id INTEGER PRIMARY KEY,enabled INTEGER)')
            db.execute('INSERT INTO brain_runtime VALUES(1,0)')
        self.assertFalse(service.settings()['enabled'])
        with continuity.connect() as db:
            self.assertEqual(db.execute('SELECT enabled FROM brain_runtime').fetchone()[0], 0)

    def test_failure_notifies_once_across_restarts_and_recovery_notifies(self):
        with patch.object(service, 'AREAS', (service.AREAS[0],)), \
             patch.object(service, 'run_check', return_value=self.result('failed', 'PCM mismatch')):
            self.controller.cycle(now=100)
            service.Controller(self.player).cycle(now=200)
        self.assertEqual(self.player.write_log.call_count, 1)
        self.assertIn('PCM mismatch', self.player.write_log.call_args.args[0])
        with patch.object(service, 'AREAS', (service.AREAS[0],)), \
             patch.object(service, 'run_check', return_value=self.result()):
            self.controller.cycle(now=300)
        self.assertEqual(self.player.write_log.call_count, 2)
        self.assertEqual(service.results()[0]['status'], 'passed')

    def test_exception_is_unverified_not_a_pass(self):
        with patch.object(service, 'run_check', side_effect=OSError('private-content')):
            self.controller.cycle(now=100)
        self.assertEqual(service.results()[0]['status'], 'unverified')
        self.assertNotIn('private-content', service.report(self.controller.snapshot()))

    def test_pause_cancels_running_check(self):
        entered = threading.Event()
        def check(area, cancelled):
            entered.set()
            self.assertTrue(cancelled.wait(2))
            return self.result('cancelled', 'Stopped')
        with patch.object(service, 'run_check', side_effect=check):
            worker = threading.Thread(target=lambda: self.controller.cycle(now=100))
            worker.start()
            self.assertTrue(entered.wait(2))
            self.controller.pause()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(service.results()[0]['status'], 'cancelled')

    def test_worker_runs_without_open_panel_and_stops(self):
        done = threading.Event()
        def cycle():
            done.set()
            self.controller.stop()
        with patch.object(self.controller, 'cycle', side_effect=cycle):
            self.controller.start(delay=0)
            self.assertTrue(done.wait(2))
            self.controller.thread.join(2)
        self.assertFalse(self.controller.thread.is_alive())

    def test_first_setup_does_not_start_a_probe(self):
        controller = service.Controller(Mock(), ready=lambda: False)
        with patch.object(service, 'run_check') as check:
            controller.cycle(now=100)
        check.assert_not_called()
        self.assertEqual(service.settings()['due'], 0)

    def test_atomic_claim_and_no_overlapping_cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(service._claim, [100] * 4))
        self.assertEqual(sum(item is not None for item in claims), 1)
        self.controller._cycle_lock.acquire()
        try:
            with patch.object(service, 'run_check') as check:
                self.controller.cycle(now=200)
                check.assert_not_called()
        finally:
            self.controller._cycle_lock.release()

    def test_stale_inflight_record_never_claims_success(self):
        service._record('memory', 'running', 'fixture')
        with continuity.connect() as db:
            db.execute('UPDATE brain_checks SET updated=?', (time.time() - 100,))
        self.assertEqual(self.controller.snapshot()['results'][0]['status'], 'unverified')

    def test_history_bounded_and_report_explains_scope(self):
        for i in range(520):
            service._record('voice', 'passed', f'fixture {i}')
        with continuity.connect() as db:
            self.assertLessEqual(db.execute('SELECT COUNT(*) FROM brain_check_events').fetchone()[0], 500)
        report = service.report(self.controller.snapshot())
        self.assertIn('Mikrofon, hoparlör ve canlı ses denenmedi', report)
        self.assertIn('fixture 519', report)


class LiveWatchers(unittest.TestCase):
    def test_stopped_real_watcher_is_reported_without_leaking_its_exception(self):
        from core import heartbeat
        with patch.object(heartbeat, 'status', return_value={'vigil': {'ok': False, 'age': 2, 'why': 'private-api-sentinel'}}):
            result = service.live_watchers()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('vigil', result['detail'])
        self.assertNotIn('private-api-sentinel', result['detail'])

    def test_no_heartbeat_is_unverified(self):
        with patch('core.heartbeat.status', return_value={'away': {'ok': True, 'age': None, 'why': 'not started'}}):
            self.assertEqual(service.live_watchers()['status'], 'unverified')

    def test_active_heartbeat_is_observed_without_modification(self):
        with patch('core.heartbeat.status', return_value={'away': {'ok': True, 'age': 1, 'why': ''}}):
            self.assertEqual(service.live_watchers()['status'], 'passed')
