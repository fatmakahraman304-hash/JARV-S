"""Regressions for interrupted updates, map navigation and generated revisions."""
import importlib.util
import io
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

from core import app_updater, code_checks
from core.social_sites import SITES, site_for_command
from plugins import capacity_simulation, github_develop, night_shift, normal_map


class QtFixtureTests(unittest.TestCase):
    def test_static_checks_allow_qapplication_in_tests_but_guard_production(self):
        fixture = (
            "from PyQt6.QtWidgets import QApplication\n"
            "app = QApplication.instance() or QApplication([])\n"
        )
        checks = code_checks.static_problems(Path("."), {
            "tests/test_book_panel.py": fixture,
            "gui/book_panel.py": fixture,
            "gui/test_book_panel.py": fixture,
            "actions/book_panel.py": fixture,
            "ui.py": fixture,
        }, {"profiles": ["jarvis"]})
        self.assertEqual(set(checks), {
            "gui/book_panel.py", "gui/test_book_panel.py", "actions/book_panel.py",
        })
        self.assertIn("creates a QApplication", checks["gui/book_panel.py"])
        self.assertIn("worker threads", checks["actions/book_panel.py"])


class DownloadTests(unittest.TestCase):
    def test_transient_dns_recovers(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'archive'
        with patch.object(app_updater, 'urlopen', side_effect=[URLError(socket.gaierror('dns')), response]) as get, patch.object(app_updater.time, 'sleep'):
            self.assertEqual(app_updater._get('https://github.com/example'), b'archive')
            self.assertEqual(get.call_count, 2)

    def test_persistent_dns_has_bounded_attempts(self):
        with patch.object(app_updater, 'urlopen', side_effect=URLError(socket.gaierror('dns'))) as get, patch.object(app_updater.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'DNS'):
                app_updater._get('https://github.com/example')
            self.assertEqual(get.call_count, 3)

    def test_authentication_error_is_not_retried(self):
        error = HTTPError('https://github.com/example', 401, 'Unauthorized', {}, io.BytesIO())
        with patch.object(app_updater, 'urlopen', side_effect=error) as get:
            with self.assertRaises(HTTPError):
                app_updater._get(error.url)
            self.assertEqual(get.call_count, 1)
        error.close()

    def test_retry_same_zip_does_not_collide_with_backup(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app_updater.time, 'strftime', return_value='fixed-time'):
            root = Path(directory)
            files = {'main.py': b'original'}
            first = app_updater._apply_zip(root, files, 'a' * 40, 'main')
            second = app_updater._apply_zip(root, files, 'a' * 40, 'main')
            self.assertNotEqual(first, second)
            self.assertEqual((root / 'main.py').read_bytes(), b'original')


class SearchTests(unittest.TestCase):
    def setUp(self):
        normal_map._cache.clear()
        normal_map._last_request = 0

    def response(self, values):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(values).encode()
        return response

    def test_malformed_result_does_not_hide_valid_place(self):
        values = [None, {}, {'lat': 'bad', 'lon': 0, 'display_name': 'Bad'},
                  {'lat': '35', 'lon': '34', 'display_name': 'Gazimağusa'}]
        with patch.object(normal_map, 'urlopen', return_value=self.response(values)):
            found = normal_map.search('Gazimağusa')
        self.assertEqual([p['name'] for p in found], ['Gazimağusa'])

    def test_cache_is_bounded_and_returns_independent_results(self):
        values = [{'lat': '35', 'lon': '34', 'display_name': 'Place'}]
        with patch.object(normal_map, '_CACHE_LIMIT', 2), patch.object(normal_map.time, 'sleep'), patch.object(normal_map, 'urlopen', return_value=self.response(values)):
            normal_map.search('a')[0]['name'] = 'mutated'
            self.assertEqual(normal_map.search('a')[0]['name'], 'Place')
            normal_map.search('b')
            normal_map.search('c')
            self.assertEqual(len(normal_map._cache), 2)

    def test_empty_search_can_be_retried(self):
        values = [{'lat': 35, 'lon': 34, 'display_name': 'Place'}]
        with patch.object(normal_map.time, 'sleep'), patch.object(normal_map, 'urlopen', side_effect=[self.response([]), self.response(values)]):
            self.assertEqual(normal_map.search('a'), [])
            self.assertEqual(len(normal_map.search('a')), 1)

    def test_expired_cache_refreshes(self):
        normal_map._cache['a'] = (-10000, [{'name': 'old'}])
        with patch.object(normal_map, 'urlopen', return_value=self.response([])) as get:
            self.assertEqual(normal_map.search('a'), [])
            get.assert_called_once()


class CommandTests(unittest.TestCase):
    def test_platform_commands_with_names_and_suffixes(self):
        self.assertEqual(set(SITES), {'github', 'claude', 'chatgpt'})
        for command, site in [
            ('Jarvis, GitHub’ı aç', 'github'),
            ('Friday ChatGPT’yi aç', 'chatgpt'),
            ('claudeyi aç', 'claude'),
        ]:
            self.assertEqual(site_for_command(command), site)
        for command in [
            'Instagramı aç', 'TikTok’u aç', 'Facebook aç', 'WhatsApp aç', 'WPyi aç',
            'Claude’u açma', 'GitHub kodunu aç',
        ]:
            self.assertIsNone(site_for_command(command))

    def test_failed_worker_start_releases_github_lock(self):
        with patch.object(github_develop.threading.Thread, 'start', side_effect=RuntimeError('thread unavailable')):
            result = github_develop.run({'mode': 'inspect'}, player=Mock())
        self.assertFalse(github_develop._LOCK.locked())
        self.assertIn('başlatılamadı', result)


class ReportTests(unittest.TestCase):
    def test_nightly_report_skips_duplicates_and_can_be_read_without_ui(self):
        results = [
            {'title': 'Broken', 'url': 'https://['},
            {'title': 'First article', 'url': 'https://example.org/article', 'source': 'Publisher'},
            {'title': 'Duplicate', 'url': 'https://example.org/article#intro'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(night_shift, 'CONFIG_DIR', Path(directory)), patch('actions.web_search._ddg_news', return_value=results):
                night_shift.build_report({'topic': 'Python'})
                report = night_shift.show_report(None)
        self.assertIn('First article · Publisher', report)
        self.assertIn('https://example.org/article', report)
        self.assertNotIn('Duplicate', report)

    def test_backlog_can_clear_after_demand_falls(self):
        results, _ = capacity_simulation.simulate(120, -50, 3, [
            {'name': 'A', 'daily_capacity': 100}, {'name': 'B', 'daily_capacity': 140},
        ])
        self.assertEqual(results[0]['peak_backlog'], 20)
        self.assertEqual(results[0]['cleared'], 2)
        self.assertIsNone(results[1]['first'])


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'numpy required for PCM detection')
class SleepTests(unittest.TestCase):
    def test_sleep_commands_and_negation(self):
        from core.snap_wake import is_sleep_command
        for text in ['uyu', 'FRIDAY uyu', 'J.A.R.V.I.S uyu', 'Jarvis uyku moduna geç']:
            self.assertTrue(is_sleep_command(text), text)
        for text in ['uyuma', 'jarvis uyu deme', 'bilgisayarı uyut', 'uyu dedim ama şimdi konuş']:
            self.assertFalse(is_sleep_command(text), text)

    def test_snap_across_chunks_and_sustained_noise(self):
        import numpy as np
        from core.snap_wake import SnapDetector
        quiet = np.zeros(1024, dtype=np.int16)
        pulse = np.tile(np.array([4000, -4000], dtype=np.int16), 64)
        detector = SnapDetector(16000)
        self.assertFalse(detector.feed(quiet))
        self.assertFalse(detector.feed(pulse[:50]))
        self.assertTrue(detector.feed(np.concatenate((pulse[50:], quiet))))
        detector = SnapDetector(16000)
        detector.feed(quiet)
        self.assertFalse(detector.feed(np.tile(pulse, 20)))
        self.assertFalse(detector.feed(quiet))


class MapNavigationTests(unittest.TestCase):
    def test_world_map_command_routes_without_a_geocoding_request(self):
        player = Mock()
        self.assertIs(normal_map.map_command_for_text("JARVIS, Dünya haritasını aç."), True)
        self.assertIs(normal_map.map_command_for_text("Haritayı kapat"), False)
        self.assertIsNone(normal_map.map_command_for_text("Gazimağusa’yı haritada aç"))
        with patch.object(normal_map, "search") as search:
            normal_map.run({"action": "open"}, player)
            player.show_world_map.assert_called_once_with(True)
            search.assert_not_called()

    def test_world_overview_centers_native_map_without_location(self):
        from gui.location_map import tile_position
        from gui.window import MainWindow
        view = Mock(zoom=15, route_points=[[1, 2], [3, 4]])
        owner = SimpleNamespace(_city_explorer=object(), _large_city_map=view,
                                _hud_cam_stack=Mock(), _map_place_label=Mock())
        MainWindow._explore_city_map(owner, world=True)
        self.assertEqual(view.zoom, 2)
        self.assertEqual(view.center, tile_position(20, 0, 2))
        self.assertEqual(view.route_points, [])
        self.assertFalse(view.show_center_marker)

    def test_reopening_explorer_preserves_view_and_route(self):
        from gui.window import MainWindow
        map_view = Mock(center=(12, 20), zoom=15, route_points=[[1, 2], [3, 4]])
        owner = SimpleNamespace(_city_explorer=object(), _large_city_map=map_view, _hud_cam_stack=Mock())
        MainWindow._explore_city_map(owner)
        self.assertEqual(map_view.center, (12, 20))
        self.assertEqual(map_view.zoom, 15)
        self.assertEqual(map_view.route_points, [[1, 2], [3, 4]])

    def test_return_to_location_clears_old_route(self):
        from gui.window import MainWindow
        owner = SimpleNamespace(_large_city_map=Mock(), _map_place_label=Mock(),
                                _location_panel=SimpleNamespace(map=SimpleNamespace(center=(8, 9), zoom=11), city=Mock()))
        owner._location_panel.city.text.return_value = 'Gazimağusa'
        MainWindow._center_city_map(owner)
        self.assertEqual(owner._large_city_map.center, (8, 9))
        self.assertEqual(owner._large_city_map.route_points, [])


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        from plugins import voice_prototype
        self.module = voice_prototype
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_revision_can_be_undone_without_calling_model(self):
        module = self.module
        path = self.root / 'prototype.html'
        module.save_draft(path, '<html>first</html>')
        module.save_draft(path, '<html>second</html>')
        player = Mock()
        with patch.object(module, '_ROOT', self.root), patch.object(module.gemini, 'text') as model, patch.object(module.threading.Thread, 'start', lambda thread: thread.run()):
            module.run({'mode': 'undo', 'format': 'web'}, player=player)
        model.assert_not_called()
        self.assertEqual(path.read_text(), '<html>first</html>')
        player.show_prototype.assert_called_once_with('<html>first</html>')
        self.assertFalse(module._LOCK.locked())

    def test_replace_failure_keeps_working_draft(self):
        path = self.root / 'prototype.py'
        self.module.save_draft(path, 'print(1)')
        original_replace = Path.replace
        def replace(source, destination):
            if destination == path:
                raise OSError('disk failure')
            return original_replace(source, destination)
        with patch.object(Path, 'replace', replace):
            with self.assertRaises(OSError):
                self.module.save_draft(path, 'print(2)')
        self.assertEqual(path.read_text(), 'print(1)')
        self.assertFalse(path.with_suffix('.py.tmp').exists())


if __name__ == '__main__':
    unittest.main()
