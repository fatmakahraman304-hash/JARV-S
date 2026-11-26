"""Candidate signing refuses exposed keys, wrong certificates and failed signers."""
import base64
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools import android_signing as signing


class AndroidSigning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        signer = self.root / 'sdk/build-tools/34.0.0/apksigner'
        signer.parent.mkdir(parents=True)
        signer.write_text('fixture executable')
        self.source = self.root / 'unsigned.apk'
        self.source.write_bytes(b'unsigned fixture')
        self.target = self.root / 'signed.apk'
        self.env = {name: 'synthetic-secret' for name in signing.SECRET_NAMES}
        self.env.update(ANDROID_HOME=str(self.root / 'sdk'), FRIDAY_ANDROID_CERT_SHA256='a' * 64,
                        FRIDAY_ANDROID_KEYSTORE_BASE64=base64.b64encode(b'synthetic keystore').decode())

    def fake_signer(self, commands, fingerprint='a' * 64, fail=False):
        def run(command, **kwargs):
            commands.append((command, kwargs))
            if command[1] == 'sign':
                key = Path(command[command.index('--ks') + 1])
                self.assertEqual(key.read_bytes(), b'synthetic keystore')
                self.assertFalse(key.is_relative_to(self.root))
                self.assertNotIn('FRIDAY_ANDROID_KEYSTORE_BASE64', kwargs['env'])
                Path(command[command.index('--out') + 1]).write_bytes(b'signed fixture')
            return subprocess.CompletedProcess(command, 1 if fail else 0,
                stdout='Signer #1 certificate SHA-256 digest: ' + fingerprint,
                stderr='private error data that must never be shown')
        return run

    def test_exposed_missing_or_invalid_material_never_launches_signer(self):
        bad = [{}, {**self.env, 'FRIDAY_ANDROID_CERT_SHA256': signing.EXPOSED_CERT},
               {**self.env, 'FRIDAY_ANDROID_KEYSTORE_BASE64': '%%%'}]
        with patch.object(signing.subprocess, 'run') as run:
            for env in bad:
                with self.subTest(names=sorted(env)), self.assertRaises(ValueError):
                    signing.sign(self.source, self.target, env)
            run.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_success_verifies_fingerprint_and_cleans_private_material(self):
        commands = []
        with patch.object(signing.subprocess, 'run', side_effect=self.fake_signer(commands)):
            result = signing.sign(self.source, self.target, self.env)
        self.assertEqual(self.target.read_bytes(), b'signed fixture')
        self.assertFalse(result['published'])
        self.assertFalse(result['installed_client_rotation_verified'])
        key = Path(commands[0][0][commands[0][0].index('--ks') + 1])
        self.assertFalse(key.exists())
        self.assertEqual(len(commands), 2)

    def test_failed_signer_wrong_certificate_and_timeout_preserve_source(self):
        for failure in ('signer', 'certificate', 'timeout'):
            commands = []
            side_effect = (subprocess.TimeoutExpired('apksigner', 120) if failure == 'timeout'
                           else self.fake_signer(commands, fingerprint='b' * 64 if failure == 'certificate' else 'a' * 64,
                                                 fail=failure == 'signer'))
            with self.subTest(failure=failure), patch.object(signing.subprocess, 'run', side_effect=side_effect):
                with self.assertRaises(ValueError) as error:
                    signing.sign(self.source, self.target, self.env)
                self.assertNotIn('private error data', str(error.exception))
            self.assertFalse(self.target.exists())
            self.assertEqual(self.source.read_bytes(), b'unsigned fixture')
            if commands:
                command = commands[0][0]
                self.assertFalse(Path(command[command.index('--ks') + 1]).exists())

    def test_existing_destination_is_never_overwritten(self):
        self.target.write_bytes(b'prior accepted candidate')
        with patch.object(signing.subprocess, 'run') as run, self.assertRaises(ValueError):
            signing.sign(self.source, self.target, self.env)
        run.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b'prior accepted candidate')
