"""Real Ed25519 signatures, tampering and extraction boundaries; ephemeral keys only."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from core import release_signatures as signatures
from tools import release_package as release
from tests import test_release_package


class ReleaseSignatures(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.private = self.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.public = self.key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        self.payload = b'archive bytes'
        self.commit = 'a' * 40

    def test_real_signature_accepts_only_exact_payload_commit_and_key(self):
        envelope = signatures.sign(self.payload, self.commit, self.private)
        self.assertTrue(signatures.verify(self.payload, self.commit, envelope, self.public))
        other = Ed25519PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        for payload, commit, key in [(b'changed', self.commit, self.public),
                                      (self.payload, 'b' * 40, self.public),
                                      (self.payload, self.commit, other)]:
            with self.subTest(commit=commit, payload=payload), self.assertRaises(ValueError):
                signatures.verify(payload, commit, envelope, key)

    def test_malformed_and_forged_envelopes_are_rejected(self):
        original = json.loads(signatures.sign(self.payload, self.commit, self.private))
        forged = {**original, 'signature': base64.b64encode(b'x' * 64).decode()}
        unknown = {**original, 'public_key': self.public.decode()}
        for envelope in (b'[]', b'{', b'x' * (signatures.MAX_SIGNATURE + 1),
                         json.dumps(forged).encode(), json.dumps(unknown).encode()):
            with self.subTest(size=len(envelope)), self.assertRaises(ValueError):
                signatures.verify(self.payload, self.commit, envelope, self.public)

    def test_required_authentication_precedes_any_extraction(self):
        # Use the existing real Git/source-archive fixture, not a fake ZIP verifier.
        fixture = test_release_package.ReleasePackage()
        fixture.setUp()
        try:
            fixture.build()
            envelope = fixture.base / 'signature.json'
            public = fixture.base / 'public.pem'
            public.write_bytes(self.public)
            envelope.write_bytes(signatures.sign(fixture.archive.read_bytes(), fixture.sha, self.private))
            target = fixture.base / 'extract'
            with self.assertRaises(ValueError):
                release.verify(fixture.archive, fixture.sha, target, require_signature=True)
            self.assertFalse(target.exists())
            envelope.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                release.verify(fixture.archive, fixture.sha, target, signature=envelope, public_key=public)
            self.assertFalse(target.exists())
            envelope.write_bytes(signatures.sign(fixture.archive.read_bytes(), fixture.sha, self.private))
            result = release.verify(fixture.archive, fixture.sha, target,
                                    signature=envelope, public_key=public, require_signature=True)
            self.assertTrue(result['publisher_signature_verified'])
            self.assertTrue((target / 'main.py').is_file())
            # The original unsigned source manifest is not rewritten into an attestation.
            self.assertFalse(json.loads((target / release.MANIFEST).read_text())['publisher_signature_verified'])
        finally:
            fixture.doCleanups()

    def test_encrypted_key_password_is_not_in_errors(self):
        password = b'synthetic-private-password'
        encrypted = self.key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(password))
        envelope = signatures.sign(self.payload, self.commit, encrypted, password)
        self.assertTrue(signatures.verify(self.payload, self.commit, envelope, self.public))
        with self.assertRaises(ValueError) as error:
            signatures.sign(self.payload, self.commit, encrypted, b'wrong-password')
        self.assertNotIn('wrong-password', str(error.exception))
        self.assertNotIn(password.decode(), str(error.exception))
