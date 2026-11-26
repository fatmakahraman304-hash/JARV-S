"""Manual protected-CI candidate signing. Never publish or reuse the exposed key."""
from __future__ import annotations
import argparse
import base64
import binascii
import os
from pathlib import Path
import re
import subprocess
import tempfile

EXPOSED_CERT = 'f7283e63fa679c4c414c6fac84e78b9527bd3dcd9b5db6dc972b2e479f811b72'
SECRET_NAMES = ('FRIDAY_ANDROID_KEYSTORE_BASE64', 'FRIDAY_ANDROID_STORE_PASSWORD',
                'FRIDAY_ANDROID_KEY_ALIAS', 'FRIDAY_ANDROID_KEY_PASSWORD')


def signing_material(env):
    if not all(isinstance(env.get(name), str) and env[name] for name in SECRET_NAMES):
        raise ValueError('Protected Android signing secrets are not configured')
    expected = env.get('FRIDAY_ANDROID_CERT_SHA256', '').replace(':', '').lower()
    if not re.fullmatch('[0-9a-f]{64}', expected) or expected == EXPOSED_CERT:
        raise ValueError('A new, reviewed certificate fingerprint is required')
    try:
        raw = base64.b64decode(env[SECRET_NAMES[0]], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Invalid protected keystore encoding') from None
    if not raw or len(raw) > 1024 * 1024:
        raise ValueError('Invalid protected keystore size')
    return raw, expected


def certificate_matches(output, expected):
    fingerprints = re.findall(r'certificate SHA-256 digest:\s*([0-9a-fA-F]+)', output)
    return bool(fingerprints) and all(value.lower() == expected for value in fingerprints)


def sign(source: Path, target: Path, env=None):
    env = dict(os.environ if env is None else env)
    material, expected = signing_material(env)
    if not source.is_file() or target.exists() or target.is_symlink():
        raise ValueError('Source APK missing or candidate destination already exists')
    sdk = Path(env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or '')
    signers = sorted((sdk / 'build-tools').glob('*/apksigner'))
    if not signers:
        raise ValueError('Android SDK apksigner is unavailable')
    signer = str(signers[-1].resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    # Signing failures never replace an existing candidate or leak key values.
    with tempfile.TemporaryDirectory(prefix='friday-sign-') as directory:
        key = Path(directory) / 'release.jks'
        with key.open('xb') as handle:
            os.chmod(key, 0o600)
            handle.write(material)
        candidate = Path(directory) / 'candidate.apk'
        child_env = {k: v for k, v in env.items() if k != SECRET_NAMES[0]}
        commands = [
            [signer, 'sign', '--ks', str(key), '--ks-pass', 'env:FRIDAY_ANDROID_STORE_PASSWORD',
             '--ks-key-alias', env['FRIDAY_ANDROID_KEY_ALIAS'], '--key-pass', 'env:FRIDAY_ANDROID_KEY_PASSWORD',
             '--out', str(candidate), str(source.resolve())],
            [signer, 'verify', '--verbose', '--print-certs', str(candidate)],
        ]
        result = None
        for command in commands:
            try:
                result = subprocess.run(command, env=child_env, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace', timeout=120)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError('APK signing/verification could not finish; details withheld') from None
            if result.returncode:
                raise ValueError('APK signing/verification failed; details withheld')
        if not certificate_matches(result.stdout, expected):
            raise ValueError('APK certificate differs from the reviewed fingerprint')
        if not candidate.is_file() or not candidate.stat().st_size:
            raise ValueError('Signer did not produce an APK')
        # Exclusive creation: never clobber an earlier accepted artifact.
        created = False
        try:
            with target.open('xb') as output, candidate.open('rb') as input_file:
                created = True
                import shutil
                shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            if created:
                target.unlink(missing_ok=True)
            raise
    return {'signed_candidate': str(target), 'certificate_sha256': expected,
            'published': False, 'installed_client_rotation_verified': False}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(sign(args.source, args.target)))
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
