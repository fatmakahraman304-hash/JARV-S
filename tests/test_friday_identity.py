"""Visible identity across desktop, PWA and Android; preserve provider identity."""
import json
import os
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class FridayIdentity(unittest.TestCase):
    def test_visible_pages_including_split_logo(self):
        for name in ('web/index.html', 'dashboard/static/login.html',
                     'dashboard/static/app.html', 'dashboard/static/tv.html'):
            with self.subTest(name=name):
                parser = VisibleText()
                parser.feed((ROOT / name).read_text(encoding='utf-8'))
                text = ''.join(parser.parts).upper()
                self.assertIn('FRIDAY', text)
                for legacy in ('JARVIS', 'AETHER', 'MAYK', 'MURAT', 'ULTRON'):
                    self.assertNotIn(legacy, text)

    def test_installed_device_names(self):
        manifest = json.loads((ROOT / 'web/manifest.webmanifest').read_text())
        self.assertEqual(manifest['name'], 'FRIDAY')
        self.assertEqual(manifest['short_name'], 'FRIDAY')
        android = (ROOT / 'android-receiver/app/src/main/res/values/strings.xml').read_text()
        self.assertIn('>FRIDAY Alıcı<', android)

    def test_desktop_and_provider_keep_distinct_names(self):
        script = '''
from gui.theme import APP_VERSION
from ui import FridayUI, AetherUI
from providers.llm_openai import PRESETS
assert APP_VERSION == 'FRIDAY'
assert FridayUI is AetherUI
assert PRESETS['Aether API'] == 'https://api.aetherapi.dev/v1'
ui = FridayUI('')
assert ui._win._assistant_name == 'FRIDAY'
assert 'FRIDAY' in ui._win.windowTitle()
ui._win.close()
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
