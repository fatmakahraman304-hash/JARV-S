"""Missing tool evidence must not become success or cause duplicate effects."""
import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import outcome, toolwait
from core.action_loader import ActionRecord, ActionRegistry
from core.plugin_loader import PluginRecord, PluginRegistry


class OutcomeIntegrity(unittest.TestCase):
    def assert_uncertain(self, text):
        self.assertIn('status=unverified', text)
        self.assertIn('verified=false', text)
        self.assertIn('retry_automatically=false', text)
        self.assertNotIn('status=done', text)
        self.assertNotEqual(text, 'Done.')

    def test_missing_result_is_uncertain_and_falsy_data_survives(self):
        for value in (None, '', '  \n '):
            with self.subTest(value=value):
                self.assert_uncertain(outcome.result_text('fixture', value))
        for value in (False, True, 0, [], {}, [0, False], {'count': 0}):
            with self.subTest(value=value):
                self.assertEqual(json.loads(outcome.result_text('fixture', value)), value)
        for text in ('0', 'false', outcome.done('fixture', observed=True),
                     outcome.failed('fixture', 'a real failure'), outcome.started('fixture')):
            self.assertEqual(outcome.result_text('fixture', text), text)

    def test_unserializable_or_nonfinite_results_do_not_become_success(self):
        for value in (float('nan'), float('inf'), object(), {1, 2}):
            with self.subTest(type=type(value).__name__):
                self.assert_uncertain(outcome.result_text('fixture', value))

    def test_action_and_plugin_execute_once_then_report_uncertainty(self):
        effects = []
        def action(parameters):
            effects.append('action')
        def plugin(parameters):
            effects.append('plugin')
        actions = ActionRegistry({'fixture': ActionRecord(name='fixture', handler=action, valid=True)}, lambda *_: None)
        plugins = PluginRegistry({'fixture': PluginRecord(name='fixture', run=plugin, valid=True)}, lambda *_: None)
        self.assert_uncertain(actions.run('fixture', {}))
        with patch('core.plugin_loader.get_plugin_enabled', return_value=True):
            self.assert_uncertain(plugins.run('fixture', {}))
        self.assertEqual(effects, ['action', 'plugin'])

    def test_background_and_cloud_borrowed_tools_share_the_same_boundary(self):
        from core.tasks.tools import TaskTools
        from core.cloud import ToolBox
        effects = []
        def action(parameters):
            effects.append('called')
        with tempfile.TemporaryDirectory() as directory:
            tasks = TaskTools(Path(directory), ['web_search'], log=lambda *_: None)
            tasks._borrowed['web_search'] = {'handler': action}
            self.assert_uncertain(tasks.execute('web_search', {}))
            cloud = ToolBox.__new__(ToolBox)
            cloud.rt = SimpleNamespace(log=lambda *_: None)
            cloud._borrowed = {'web_search': {'handler': action}}
            self.assert_uncertain(cloud.execute('web_search', {}, {'origin': 'telegram'}))
        self.assertEqual(effects, ['called', 'called'])

    def test_confirmed_callback_is_not_execution_evidence(self):
        from core import confirm
        shown, logs, effects = [], [], []
        finished = threading.Event()
        def log(text):
            logs.append(text)
            finished.set()
        with patch.object(confirm, '_pending', None), patch.object(confirm, '_show_cb', lambda *args: shown.append(args)), \
             patch.object(confirm, '_hide_cb', lambda: None), patch.object(confirm, '_log_cb', log):
            confirm.request('fixture', 'Fixture action', 'No external action', lambda: effects.append('executed'))
            self.assertEqual(effects, [])
            confirm.resolve(True, 'forged-token')
            self.assertEqual(effects, [])
            confirm.resolve(True, shown[0][-1])
            self.assertTrue(finished.wait(2))
            self.assertEqual(effects, ['executed'])
            self.assert_uncertain(logs[-1])


class AsyncOutcomeIntegrity(unittest.IsolatedAsyncioTestCase):
    async def test_fast_and_late_missing_results_do_not_replay(self):
        effects, late = [], []
        ready = threading.Event()
        def fast():
            effects.append('fast')
        first = await toolwait.run('fixture', fast, wait=1)
        self.assertIn('status=unverified', first)
        def slow():
            ready.wait(2)
            effects.append('slow')
        answer = await toolwait.run('fixture', slow, wait=0.01, on_late=lambda *args: late.append(args))
        self.assertIn('STILL RUNNING', answer)
        ready.set()
        for _ in range(100):
            if late:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(late), 1)
        self.assertIn('status=unverified', late[0][1])
        self.assertEqual(effects, ['fast', 'slow'])
