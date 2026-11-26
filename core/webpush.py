"""
core/webpush.py — notifications to the phone even when the FRIDAY page is closed.

Standard Web Push, sent straight from this computer to the phone's push
service (Google's for Android/Chrome, Apple's for an iPhone with FRIDAY on the
home screen): VAPID (RFC 8292) to say who is sending and aes128gcm (RFC 8291)
to encrypt the message so only that phone can read it. Built on the
`cryptography` package already in requirements.txt — no push server, no
account.

The key pair lives in the shared gist (push.json), so every computer of the
user can send to every device that subscribed (web/app.js enablePush,
web/sw.js shows the notification).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

SUBJECT = "https://fatmakahraman304-hash.github.io/JARV-S/"


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    text = str(text or "")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_keys() -> tuple[str, str]:
    """(private, public) VAPID keys: the raw P-256 secret (32 bytes) and the
    uncompressed public point (65 bytes), both base64url."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64u(priv), b64u(pub)


def _private_key(priv_b64: str):
    from cryptography.hazmat.primitives.asymmetric import ec
    return ec.derive_private_key(int.from_bytes(unb64u(priv_b64), "big"), ec.SECP256R1())


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    out, block, i = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([i]), hashlib.sha256).digest()
        out += block
        i += 1
    return out[:length]


def encrypt(plaintext: bytes, p256dh_b64: str, auth_b64: str, *, salt: bytes | None = None,
            server_key=None) -> bytes:
    """RFC 8291 aes128gcm body for one subscription (a single record)."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    ua_pub_bytes = unb64u(p256dh_b64)
    auth = unb64u(auth_b64)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = server_key.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint)
    shared = server_key.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf_expand(_hkdf_extract(auth, shared), b"WebPush: info\x00" + ua_pub_bytes + as_pub, 32)
    salt = salt or os.urandom(16)
    prk = _hkdf_extract(salt, ikm)
    cek = _hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)
    cipher = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + cipher


def vapid_header(endpoint: str, priv_b64: str, pub_b64: str, subject: str = SUBJECT) -> str:
    """`Authorization: vapid t=…, k=…` for this endpoint (RFC 8292)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    u = urllib.parse.urlsplit(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                            "sub": subject}, separators=(",", ":")).encode())
    der = _private_key(priv_b64).sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{sig}, k={pub_b64}"


def send(subscription: dict, payload: dict, priv_b64: str, pub_b64: str, ttl: int = 86400) -> tuple[bool, int]:
    """Send one notification. (delivered, HTTP status); 404/410 mean the
    subscription is gone and should be forgotten."""
    try:
        endpoint = str(subscription.get("endpoint") or "")
        keys = subscription.get("keys") or {}
        if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
            return False, 0
        body = encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8")[:3000],
                       keys["p256dh"], keys["auth"])
        req = urllib.request.Request(endpoint, data=body, method="POST", headers={
            "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
            "TTL": str(ttl), "Urgency": "high",
            "Authorization": vapid_header(endpoint, priv_b64, pub_b64)})
        with urllib.request.urlopen(req, timeout=15) as r:
            return 200 <= r.status < 300, r.status
    except urllib.error.HTTPError as e:
        return False, e.code
    except Exception:
        return False, -1
