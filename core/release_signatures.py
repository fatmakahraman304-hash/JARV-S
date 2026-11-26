"""Detached Ed25519 source-package signatures; trust comes from an external key."""
from __future__ import annotations
import base64
import binascii
import hashlib
import json
import re

MAX_SIGNATURE = 4096


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate signature field')
        result[key] = value
    return result


def _message(payload, commit):
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('An exact trusted source commit is required')
    metadata = {'schema': 1, 'algorithm': 'Ed25519', 'source_commit': commit,
                'archive_sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    message = b'FRIDAY-RELEASE/1\n' + json.dumps(
        metadata, sort_keys=True, separators=(',', ':')).encode('ascii')
    return metadata, message


def sign(payload, commit, private_key_pem, password=None):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    try:
        key = load_pem_private_key(private_key_pem, password=password)
    except (TypeError, ValueError):
        raise ValueError('Release signing key could not be loaded; values withheld') from None
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Release signatures require an Ed25519 key')
    metadata, message = _message(payload, commit)
    metadata['signature'] = base64.b64encode(key.sign(message)).decode('ascii')
    return (json.dumps(metadata, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def verify(payload, commit, envelope, trusted_public_key_pem):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if len(envelope) > MAX_SIGNATURE:
        raise ValueError('Oversized release signature')
    metadata, message = _message(payload, commit)
    try:
        signed = json.loads(envelope, object_pairs_hook=_unique_object)
        if not isinstance(signed, dict) or set(signed) != set(metadata) | {'signature'}:
            raise ValueError('Unexpected signature fields')
        signature = base64.b64decode(signed.pop('signature'), validate=True)
        if (json.dumps(signed, sort_keys=True, separators=(',', ':')) !=
                json.dumps(metadata, sort_keys=True, separators=(',', ':')) or len(signature) != 64):
            raise ValueError('Signature metadata differs from this archive/commit')
        key = load_pem_public_key(trusted_public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError('Wrong release public key type')
        key.verify(signature, message)
    except (InvalidSignature, TypeError, ValueError, binascii.Error):
        raise ValueError('Release signature verification failed') from None
    return True
