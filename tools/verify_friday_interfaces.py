"""Real offline browser layouts and Qt UI evidence. No accounts/devices used."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OLD_BRAND = re.compile(r'\b(?:aether|jarvis|mayk|murat)\b', re.I)
PROFILES = [('phone', 390, 844), ('small-phone', 320, 568), ('tablet', 820, 1180),
            ('pc', 1440, 1000), ('tv', 1920, 1080), ('projector', 1280, 800),
            ('watch', 240, 240)]


@contextmanager
def server():
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)
        def log_message(self, *args):
            pass
        def do_GET(self):
            path = urlparse(self.path).path
            if path.startswith('/assets/'):
                self.path = '/dashboard/static/' + path.rsplit('/', 1)[-1]
            super().do_GET()
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}'
    finally:
        http.shutdown(); http.server_close(); worker.join(3)


def verify(output, executable=None, engines=('chromium', 'firefox')):
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True, exist_ok=True)
    evidence = []
    with server() as origin, sync_playwright() as api:
        for engine in engines:
            options = {'headless': True}
            if executable:
                options['executable_path'] = executable
            browser = getattr(api, engine).launch(**options)
            try:
                for profile, width, height in PROFILES:
                    kind = 'phone' if profile == 'small-phone' else profile
                    context = browser.new_context(viewport={'width': width, 'height': height},
                                                  reduced_motion='reduce', service_workers='block')
                    context.add_init_script('localStorage.setItem("aether_web", ' +
                                            json.dumps(json.dumps({'kind': kind, 'name': 'old saved name'})) + ');')
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    try:
                        page.goto(origin + '/web/index.html', wait_until='load')
                        page.wait_for_function('window.FRIDAY && window.FridayKit')
                        page.wait_for_timeout(650)
                        if page.locator('#s-setup').is_visible():
                            page.locator('#f-close').click()
                        assert page.title() == 'FRIDAY'
                        assert page.locator('#brand-name').inner_text() == 'FRIDAY'
                        assert page.evaluate('window.FRIDAY.kind') == kind
                        assert not errors, errors
                        assert not OLD_BRAND.search(page.locator('body').inner_text()), 'Old visible identity'
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), f'Horizontal overflow: {engine}/{profile} at {width}x{height}'
                        mic = page.locator('#mic').bounding_box()
                        assert mic and mic['x'] >= 0 and mic['y'] >= 0 and mic['x'] + mic['width'] <= width + 1 and mic['y'] + mic['height'] <= height + 1, mic
                        if kind != 'watch':
                            page.locator('#b-set').focus()
                            page.keyboard.press('Tab')
                        page.screenshot(path=str(output / f'{engine}-{profile}.png'))
                        # Existing settings survive the brand refresh; no API key is supplied.
                        assert page.evaluate('JSON.parse(localStorage.getItem("aether_web")).kind') == kind
                        evidence.append({'engine': engine, 'profile': profile, 'viewport': [width, height],
                                         'runtime_errors': errors, 'horizontal_overflow': False,
                                         'real_device_verified': False})
                    finally:
                        context.close()
                for name in ('login', 'app', 'tv'):
                    context = browser.new_context(viewport={'width': 1280 if name == 'tv' else 390,
                                                          'height': 800 if name == 'tv' else 844}, service_workers='block')
                    # Layout fixture only: this never authenticates to a real server.
                    context.add_init_script("sessionStorage.setItem('aether_token','preview-only');")
                    def routes(route):
                        url = route.request.url
                        if not url.startswith(origin + '/'):
                            return route.abort()
                        if '/api/' in url:
                            return route.fulfill(json={'ok': True, 'name': 'FRIDAY', 'version': 'preview',
                                                       'state': 'offline', 'self': {'id': 'preview', 'name': 'Önizleme'},
                                                       'peers': [], 'screens': [], 'token': 'preview-only', 'code': '123456'})
                        return route.continue_()
                    context.route('**/*', routes)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    try:
                        page.goto(origin + f'/dashboard/static/{name}.html', wait_until='load')
                        page.wait_for_timeout(600)
                        assert 'FRIDAY' in page.title()
                        assert not OLD_BRAND.search(page.locator('body').inner_text()), 'Old dashboard identity'
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Dashboard horizontal overflow'
                        assert not errors, errors
                        page.screenshot(path=str(output / f'{engine}-dashboard-{name}.png'))
                        evidence.append({'engine': engine, 'profile': 'dashboard-' + name,
                                         'backend': 'synthetic layout fixture', 'runtime_errors': errors,
                                         'real_device_verified': False})
                    finally:
                        context.close()
            finally:
                browser.close()
    report = {'scope': 'real browser engines at device viewports; offline/synthetic data only',
              'physical_device_verified': False, 'live_accounts_verified': False, 'checks': evidence}
    (output / 'layouts.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'layouts_passed': len(evidence), 'engines': list(engines), 'physical_devices_verified': False}))


def qt_preview(output):
    import tempfile
    from unittest.mock import patch
    from PyQt6.QtWidgets import QApplication, QLabel
    from memory import config_manager
    from gui.window import MainWindow
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory, 'XDG_DATA_HOME': directory}), \
         patch.object(config_manager, 'CONFIG_FILE', Path(directory) / 'config.json'):
        window = MainWindow('')
        try:
            window.resize(1366, 900)
            window.show()
            if window._overlay is not None:
                window._overlay.hide()  # Review configured layout without supplying a real account.
            app.processEvents()
            for label in window.findChildren(QLabel):
                if label.isVisible():
                    assert not OLD_BRAND.search(label.text().replace('Aether API', 'External provider'))
            assert window.windowTitle() == 'FRIDAY'
            output.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(output / 'desktop-qt.png'))
        finally:
            window.close()
            app.processEvents()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--executable')
    parser.add_argument('--qt-preview', action='store_true')
    parser.add_argument('--engine', action='append', choices=('chromium', 'firefox'))
    args = parser.parse_args()
    if args.qt_preview:
        qt_preview(args.output)
    else:
        verify(args.output, args.executable, tuple(args.engine or ('chromium', 'firefox')))
