"""Enroll the publisher's public key once in the local user's profile."""
import argparse
import hashlib
import hmac
import os
from pathlib import Path
import re


def pin_path():
    if os.name == 'nt':
        directory = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    else:
        directory = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    if not directory.is_absolute():
        raise ValueError('Güncelleme güven dizini mutlak yol olmalı.')
    return directory / 'FRIDAY' / 'update-trust' / 'publisher.pem'


def _read_key(path):
    with path.open('rb') as stream:
        data = stream.read(16385)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    if len(data) > 16384 or not isinstance(load_pem_public_key(data), Ed25519PublicKey):
        raise ValueError('Geçerli bir Ed25519 yayıncı açık anahtarı gerekiyor.')
    return data


def trusted_key():
    path = pin_path()
    if path.is_symlink():
        raise ValueError('Güven dosyası sembolik bağlantı olamaz.')
    try:
        return _read_key(path)
    except FileNotFoundError:
        return None


def enroll(public_key, expected_sha256):
    data = _read_key(public_key)
    digest = hashlib.sha256(data).hexdigest()
    if not re.fullmatch(r'[0-9a-fA-F]{64}', expected_sha256) or not hmac.compare_digest(
            digest, expected_sha256.lower()):
        raise ValueError('Bağımsız kanaldan alınan SHA-256 parmak izi eşleşmedi.')
    path = pin_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Exclusive creation prevents a second enrollment from changing active trust.
    # A partial write on power loss fails closed when the updater reads the PEM.
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-key', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    try:
        print(enroll(args.public_key, args.expected_sha256))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Güven kaydı oluşturulamadı: {exc}\n')
