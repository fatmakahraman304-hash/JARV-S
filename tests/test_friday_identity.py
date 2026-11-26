"""FRIDAY display identity with existing stores, wire formats and APIs intact."""
import html
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from core import identity

ROOT = Path(__file__).resolve().parents[1]
OLD = re.compile(r'\b(?:aether|jarvis|mayk|murat)\b', re.I)


class FridayIdentity(unittest.TestCase):
    def test_existing_store_and_fresh_store_are_distinct_without_moving_data(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            base = Path(directory)
            self.assertEqual(identity.data_home(), base / 'FridayAssistant')
            old = base / identity.LEGACY_DATA_DIR
            old.mkdir()
            sentinel = old / 'long_term.json'
            sentinel.write_text('private sentinel')
            self.assertEqual(identity.data_home(), old)
            self.assertEqual(sentinel.read_text(), 'private sentinel')
            self.assertFalse((base / 'FridayAssistant').exists())

    def test_artifacts_keep_existing_files_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertEqual(identity.artifact_home(base), base / 'FRIDAY')
            old = base / 'AETHER'
            old.mkdir()
            file = old / 'project.blend'
            file.write_text('fixture')
            self.assertEqual(identity.artifact_home(base), old)
            self.assertEqual(file.read_text(), 'fixture')

    def test_legacy_class_imports_resolve_to_friday_classes(self):
        from tests._main_import import load_main
        import ui
        main = load_main()
        self.assertIs(getattr(ui, identity.LEGACY_UI_CLASS), ui.FridayUI)
        self.assertIs(getattr(main, identity.LEGACY_LIVE_CLASS), main.FridayLive)
        self.assertEqual(ui.FridayUI.__name__, 'FridayUI')
        self.assertEqual(main.FridayLive.__name__, 'FridayLive')

    def test_crypto_salt_and_discovery_stay_compatible_with_installed_clients(self):
        from dashboard import devices, server
        self.assertEqual(server._AES_SALT, identity.LEGACY_AES_SALT)
        self.assertIn(identity.LEGACY_AES_SALT.decode(), (ROOT / 'dashboard/static/app.html').read_text())
        info = {'id': 'fixture', 'name': 'FRIDAY', 'url': 'http://127.0.0.1:8000', 'kind': 'desktop'}
        data = devices.encode_announce(info)
        self.assertEqual(json.loads(data)['m'], identity.LEGACY_DISCOVERY_MAGIC)
        self.assertEqual(devices.decode_announce(data, '127.0.0.1')['name'], 'FRIDAY')
        modern = json.loads(data); modern['m'] = 'FRIDAY-DEVICE-1'
        self.assertIsNotNone(devices.decode_announce(json.dumps(modern).encode(), '127.0.0.1'))

    def test_browser_labels_and_manifest_only_use_friday(self):
        for name in ('web/index.html', 'dashboard/static/app.html', 'dashboard/static/login.html', 'dashboard/static/tv.html'):
            text = (ROOT / name).read_text()
            # Remove scripts/styles before joining adjacent visible text nodes,
            # catching split logos such as an initial inside <em>.
            text = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', text, flags=re.S|re.I)
            visible = html.unescape(re.sub(r'<[^>]+>', '', text))
            self.assertIsNone(OLD.search(visible), name)
            self.assertIn('FRIDAY', visible)
        manifest = json.loads((ROOT / 'web/manifest.webmanifest').read_text())
        self.assertEqual(manifest['name'], 'FRIDAY')
        self.assertEqual(manifest['short_name'], 'FRIDAY')

    def test_shared_theme_is_identical_and_cached_offline(self):
        self.assertEqual((ROOT / 'web/friday-theme.css').read_bytes(), (ROOT / 'dashboard/static/friday-theme.css').read_bytes())
        self.assertIn("'friday-theme.css' + suffix", (ROOT / 'web/sw.js').read_text())

    def test_provider_identity_is_not_relabelled_or_removed(self):
        from providers.llm_openai import PRESETS, CATALOG
        self.assertEqual(PRESETS['Aether API'], 'https://api.aetherapi.dev/v1')
        self.assertTrue(any(item['label'] == 'Aether API' for item in CATALOG))

    def test_android_identity_and_signing_bytes_are_not_changed(self):
        import xml.etree.ElementTree as ET
        gradle = (ROOT / 'android-receiver/app/build.gradle').read_text()
        self.assertIn("applicationId 'com.aether.alici'", gradle)
        strings = ET.parse(ROOT / 'android-receiver/app/src/main/res/values/strings.xml')
        for element in strings.getroot():
            self.assertIsNone(OLD.search(element.text or ''))
        manifest = (ROOT / 'android-receiver/app/src/main/AndroidManifest.xml').read_text()
        self.assertIn('android:scheme="aetheralici"', manifest)
        self.assertIn('@style/Theme.Friday', manifest)
        key = ROOT / 'android-receiver/app/aether-alici.jks'
        if key.exists():
            import hashlib
            self.assertEqual(hashlib.sha256(key.read_bytes()).hexdigest(), '1eef72853679e57202f55f7b63dce9d538f02444c46c6c4b0115f8e63a2b6118')

        else:
            self.assertTrue((ROOT / 'friday-release.json').is_file(), 'Signing key must not be deleted from the repository')

    def test_old_reverse_rebrand_cannot_run(self):
        self.assertFalse((ROOT / 'tools/aether_migrate.py').exists())
        self.assertFalse((ROOT / '.github/workflows/aether-rebrand.yml').exists())

    def test_license_and_upstream_attribution_remain(self):
        license_text = (ROOT / 'LICENSE').read_text()
        self.assertIn('Copyright (c) 2026 FatihMakes', license_text)
        self.assertIn('CC BY-NC 4.0', license_text)

    def test_saved_private_memory_is_read_from_the_legacy_store(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            old = base / identity.LEGACY_DATA_DIR
            old.mkdir()
            source = old / 'long_term.json'
            payload = json.dumps({'notes': {'fixture': {'value': 'kept', 'updated': '2026-01-01'}}})
            source.write_text(payload)
            code = "from memory.memory_manager import load_memory; assert load_memory()['notes']['fixture']['value'] == 'kept'"
            import sys
            env = dict(os.environ, LOCALAPPDATA=directory, XDG_DATA_HOME=directory)
            subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True, capture_output=True)
            self.assertEqual(source.read_text(), payload)

    def test_qt_visible_literals_and_title_do_not_use_legacy_branding(self):
        import ast
        from gui.window import MainWindow
        for value in ('FRIDAY', 'custom', identity.LEGACY_UI_CLASS):
            self.assertEqual(MainWindow._wordmark(value), 'FRIDAY')
        calls = {'QLabel', 'QPushButton', 'setText', 'setWindowTitle', 'setPlaceholderText'}
        for file in (ROOT / 'gui').glob('*.py'):
            for node in ast.walk(ast.parse(file.read_text())):
                if not isinstance(node, ast.Call): continue
                name = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
                if name not in calls: continue
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        label = argument.value.replace('Aether API', 'External provider')
                        label = re.sub(r'https?://\S+|\.?aether[-_]\S+', '', label)
                        self.assertIsNone(OLD.search(label), str(file.relative_to(ROOT)) + ':' + str(node.lineno))
