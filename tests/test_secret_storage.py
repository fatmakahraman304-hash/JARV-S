"""At-rest protection, atomic migration and native Windows profile checks.

Cross-platform tests use an ephemeral AEAD stand-in; native tests below use
real DPAPI on Windows and must not be reported as native passes elsewhere.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from memory import config_manager as config, secret_storage as storage


class ProtectedSettings(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'api_keys.json'
        self.backup = self.path.with_name(self.path.name + '.bak')
        self.primary = {'gemini_api_key': 'synthetic-primary-secret', 'voice_name': 'Aoede',
                        'user_name': 'Fixture', 'custom': {'keep': [1, False]},
                        'providers': {'creds': {'custom': {'api_key': 'synthetic-provider-secret'}}},
                        'plugin_config': {'mail': {'password': 'synthetic-mail-secret'}}}
        self.previous = dict(self.primary, gemini_api_key='synthetic-backup-secret', custom={'prior': 2})
        self.path.write_text(json.dumps(self.primary), encoding='utf-8')
        self.backup.write_text(json.dumps(self.previous), encoding='utf-8')
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        cipher = AESGCM(AESGCM.generate_key(bit_length=256))
        def transform(value, entropy, *, decrypt=False):
            try:
                if decrypt:
                    return cipher.decrypt(value[:12], value[12:], entropy)
                nonce = os.urandom(12)
                return nonce + cipher.encrypt(nonce, value, entropy)
            except Exception:
                raise storage.StorageError('Synthetic backend refused the payload') from None
        for context in (patch.object(config, 'CONFIG_FILE', self.path),
                        patch.object(config, 'ensure_config_dir', lambda: None),
                        patch.object(storage, 'available', return_value=True),
                        patch.object(storage, '_dpapi', side_effect=transform)):
            context.start()
            self.addCleanup(context.stop)

    def enable(self):
        self.assertTrue(config.configure_credential_storage(True))

    def without_mode(self, data):
        return {k: v for k, v in data.items() if k != storage.MARKER}

    def test_enable_round_trip_keeps_primary_and_backup_distinct_and_removes_plaintext(self):
        self.enable()
        for path, expected in ((self.path, self.primary), (self.backup, self.previous)):
            raw = path.read_bytes()
            for secret in ('synthetic-primary-secret', 'synthetic-backup-secret',
                           'synthetic-provider-secret', 'synthetic-mail-secret'):
                self.assertNotIn(secret.encode(), raw)
            self.assertEqual(self.without_mode(storage.read_document(path)), expected)
        self.assertFalse(config.configure_credential_storage(True))
        self.assertEqual(config.get_voice(), 'Aoede')
        self.assertEqual(config.get_gemini_key(), self.primary['gemini_api_key'])

    def test_settings_write_keeps_protection_even_if_caller_drops_marker(self):
        self.enable()
        config.save_voice('Kore')
        self.assertEqual(config.get_voice(), 'Kore')
        self.assertEqual(config.get_gemini_key(), self.primary['gemini_api_key'])
        config._write_config(dict(self.primary, voice_name='Aoede'))
        for path in (self.path, self.backup):
            self.assertTrue(storage.protected(json.loads(path.read_text())))
            self.assertNotIn(self.primary['gemini_api_key'].encode(), path.read_bytes())

    def test_tampering_or_field_swap_never_falls_back_to_empty_or_plaintext(self):
        self.enable()
        raw = json.loads(self.path.read_text())
        raw['gemini_api_key'] = raw['plugin_config']['mail']['password']
        self.path.write_text(json.dumps(raw))
        before = {p: p.read_bytes() for p in (self.path, self.backup)}
        for operation in (config.load_api_keys, lambda: config.save_voice('Kore'),
                          lambda: config.read_config(self.path)):
            with self.assertRaises(storage.StorageError):
                operation()
        for path, value in before.items():
            self.assertEqual(path.read_bytes(), value)

    def test_unavailable_backend_cannot_mutate_or_silently_unlock_settings(self):
        self.enable()
        before = {p: p.read_bytes() for p in (self.path, self.backup)}
        with patch.object(storage, '_dpapi', side_effect=storage.StorageError('Other Windows profile')):
            for operation in (config.load_api_keys, lambda: config.save_api_keys('replacement'),
                              lambda: config.configure_credential_storage(False)):
                with self.assertRaises(storage.StorageError):
                    operation()
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_staging_failure_preserves_both_files_and_cleans_temporary_data(self):
        before = {p: p.read_bytes() for p in (self.path, self.backup)}
        with patch.object(config.os, 'fsync', side_effect=[None, OSError('Backup flush failed')]):
            with self.assertRaises(OSError):
                config.configure_credential_storage(True)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_interrupted_primary_publication_can_be_completed_without_plaintext_downgrade(self):
        replace = config._replace_config
        def fail_primary(source, target):
            if target == self.path:
                raise OSError('Interrupted primary replacement')
            return replace(source, target)
        with patch.object(config, '_replace_config', side_effect=fail_primary):
            with self.assertRaises(OSError):
                config.configure_credential_storage(True)
        self.assertFalse(storage.protected(json.loads(self.path.read_text())))
        self.assertTrue(storage.protected(json.loads(self.backup.read_text())))
        config.save_voice('Kore')
        self.assertTrue(storage.protected(json.loads(self.path.read_text())))
        self.assertEqual(config.get_gemini_key(), self.primary['gemini_api_key'])
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_explicit_disable_restores_portable_data_without_erasing_old_backup(self):
        self.enable()
        self.assertTrue(config.configure_credential_storage(False))
        self.assertEqual(json.loads(self.path.read_text()), self.primary)
        self.assertEqual(json.loads(self.backup.read_text()), self.previous)
        self.assertFalse(config.configure_credential_storage(False))

    def test_missing_primary_uses_protected_backup_without_publishing_until_write(self):
        self.enable()
        self.path.unlink()
        self.assertEqual(config.get_gemini_key(), self.previous['gemini_api_key'])
        self.assertFalse(self.path.exists())
        config.save_voice('Kore')
        self.assertTrue(storage.protected(json.loads(self.path.read_text())))

    def test_unknown_storage_format_and_plaintext_in_protected_mode_are_rejected(self):
        for policy in ({'schema': True, 'backend': 'windows-dpapi'},
                       {'schema': 2, 'backend': 'windows-dpapi'}, storage.POLICY):
            self.path.write_text(json.dumps({**self.primary, storage.MARKER: policy}))
            before = self.path.read_bytes()
            with self.assertRaises(storage.StorageError):
                config.save_voice('Kore')
            self.assertEqual(self.path.read_bytes(), before)

    def test_missing_storage_marker_never_sends_ciphertext_as_an_api_key(self):
        self.enable()
        raw = json.loads(self.path.read_text())
        raw.pop(storage.MARKER)
        self.path.write_text(json.dumps(raw))
        with self.assertRaises(storage.StorageError):
            config.load_api_keys()

    def test_unsupported_platform_refuses_enable_without_changes(self):
        before = {p: p.read_bytes() for p in (self.path, self.backup)}
        with patch.object(storage, 'available', return_value=False):
            with self.assertRaises(storage.StorageError):
                config.configure_credential_storage(True)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_nested_aliases_and_typed_credentials_keep_values(self):
        values = {'x-api-key': 'header-secret', 'accessToken': 'camel-secret',
                  'Authorization': 'Bearer fixture', 'password': False,
                  'items': [{'token': ['part-one', 0]}], 'cookie': {},
                  'empty_api_key': '', 'empty_token': None}
        document = {storage.MARKER: dict(storage.POLICY), **values}
        encrypted = storage.encode(document)
        for secret in ('header-secret', 'camel-secret', 'Bearer fixture', 'part-one'):
            self.assertNotIn(secret, json.dumps(encrypted))
        self.assertEqual(storage.decode(encrypted), document)

    def test_legacy_readers_get_decrypted_values_without_network_calls(self):
        self.enable()
        for name in ('actions.code_helper', 'actions.dev_agent', 'actions.web_search',
                     'actions.youtube_video', 'actions.flight_finder'):
            with self.subTest(module=name):
                module = importlib.import_module(name)
                with patch.object(module, 'API_CONFIG_PATH', self.path):
                    self.assertEqual(module._get_api_key(), self.primary['gemini_api_key'])
        from core import gemini
        with patch.object(gemini, '_KEY_FILE', self.path), patch.object(gemini, '_cached_key', None):
            self.assertEqual(gemini.api_key(refresh=True), self.primary['gemini_api_key'])
        from dashboard import server, devices
        with patch.object(server, 'BASE_DIR', self.root.parent), patch.object(config, 'read_config',
                wraps=lambda path=None: storage.read_settings(self.path)):
            self.assertEqual(server._get_gemini_key(), self.primary['gemini_api_key'])


@unittest.skipUnless(os.name == 'nt', 'Real Windows DPAPI/current profile required')
class NativeDPAPI(unittest.TestCase):
    def test_current_user_round_trip_and_wrong_field_context(self):
        data = {storage.MARKER: dict(storage.POLICY), 'api_key': 'native-synthetic-secret'}
        encrypted = storage.encode(data)
        self.assertNotIn('native-synthetic-secret', json.dumps(encrypted))
        self.assertEqual(storage.decode(encrypted), data)
        altered = {storage.MARKER: dict(storage.POLICY), 'password': encrypted['api_key']}
        with self.assertRaises(storage.StorageError):
            storage.decode(altered)

    def test_native_config_can_be_read_by_a_second_process_without_key_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'api_keys.json'
            original = {'gemini_api_key': 'native-process-synthetic-secret', 'voice_name': 'Aoede'}
            path.write_text(json.dumps(original))
            with patch.object(config, 'CONFIG_FILE', path), patch.object(config, 'ensure_config_dir', lambda: None):
                config.configure_credential_storage(True)
                config.save_voice('Kore')
                self.assertEqual(config.get_gemini_key(), original['gemini_api_key'])
            program = "from pathlib import Path;import sys;from memory.secret_storage import read_settings;d=read_settings(Path(sys.argv[1]));assert d['gemini_api_key']=='native-process-synthetic-secret';assert d['voice_name']=='Kore';print('verified')"
            result = subprocess.run([sys.executable, '-c', program, str(path)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'verified')
            self.assertNotIn(original['gemini_api_key'].encode(), path.read_bytes())
            self.assertEqual({p.name for p in Path(directory).iterdir()},
                             {'api_keys.json', 'api_keys.json.bak', 'api_keys.json.lock'})
