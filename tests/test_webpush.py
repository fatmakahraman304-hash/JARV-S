"""Web Push: the body a phone receives must decrypt exactly as RFC 8291 says,
and the VAPID signature must verify with the published key."""
import json
import struct
import unittest
from unittest import mock

from core import webpush


def _decrypt(body: bytes, ua_key, auth: bytes) -> bytes:
    """What the phone's browser does (RFC 8291), written independently."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
    from cryptography.hazmat.primitives import hashes
    salt, rs, idlen = body[:16], struct.unpack(">I", body[16:20])[0], body[20]
    as_pub = body[21:21 + idlen]
    cipher = body[21 + idlen:]
    assert rs == 4096
    ua_pub = ua_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    shared = ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = HKDF(hashes.SHA256(), 32, auth, b"WebPush: info\x00" + ua_pub + as_pub).derive(shared)
    cek = HKDF(hashes.SHA256(), 16, salt, b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt, b"Content-Encoding: nonce\x00").derive(ikm)
    plain = AESGCM(cek).decrypt(nonce, cipher, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


class WebPushTest(unittest.TestCase):
    def test_phone_can_decrypt(self):
        import os
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        ua = ec.generate_private_key(ec.SECP256R1())
        ua_pub = ua.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        auth = os.urandom(16)
        msg = json.dumps({"title": "⏰ Mayk", "body": "ilaç zamanı"}, ensure_ascii=False).encode()
        body = webpush.encrypt(msg, webpush.b64u(ua_pub), webpush.b64u(auth))
        self.assertEqual(_decrypt(body, ua, auth), msg)

    def test_vapid_signature_verifies(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        priv, pub = webpush.new_keys()
        hdr = webpush.vapid_header("https://fcm.googleapis.com/fcm/send/abc", priv, pub)
        token = hdr.split("t=")[1].split(",")[0]
        head, claims, sig = token.split(".")
        self.assertEqual(json.loads(webpush.unb64u(claims))["aud"], "https://fcm.googleapis.com")
        raw = webpush.unb64u(sig)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.unb64u(pub))
        key.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))   # raises if wrong
        self.assertIn(f"k={pub}", hdr)

    def test_bad_subscription_is_refused_quietly(self):
        self.assertEqual(webpush.send({"endpoint": "http://x"}, {}, "a", "b"), (False, 0))


class SyncPushTest(unittest.TestCase):
    def test_closed_phone_gets_due_reminder_and_inbox_items(self):
        from core import sync_hub
        import time
        sent = []
        subs = {"w-phone": {"endpoint": "https://fcm.googleapis.com/x", "keys": {"p256dh": "a", "auth": "b"}}}
        old_phone = [{"id": "w-phone", "name": "Telefon", "kind": "phone", "seen": "2020-01-01T00:00:00Z"}]
        with mock.patch.dict(sync_hub._state, {"push_subs": subs, "push_keys": {"privateKey": "p", "publicKey": "k"},
                                               "pushed": set(), "devices": old_phone, "inbox_seen": set(),
                                               "inbox_primed": True}), \
             mock.patch.object(sync_hub, "push_to", side_effect=lambda *a, **k: sent.append(a) or True):
            now = time.time()
            due = [{"id": "r1", "text": "ilaç", "due": now * 1000 - 5000, "cancelled": ""},
                   {"id": "r2", "text": "sonra", "due": now * 1000 + 600_000, "cancelled": ""}]
            sync_hub._push_due_reminders(due, now)
            sync_hub._push_due_reminders(due, now)                      # once only
            self.assertEqual([(d, b) for d, _, b in sent], [("w-phone", "ilaç")])
            box = [{"id": "g1", "kind": "image", "from": "Tablet", "title": "🚨 Tablet: hareket algılandı (12:03)"}]
            sync_hub._push_inboxes({"inbox-w-phone.json": json.dumps(box)}, now)
            self.assertTrue(sent[-1][1].startswith("🚨 Tablet"))

    def test_keys_made_once_and_shared(self):
        from core import sync_hub
        writes = {}
        with mock.patch.dict(sync_hub._state, {"push_gone": set()}):
            sync_hub._push_setup({"push-sub-w1.json": json.dumps({"endpoint": "https://x/1", "keys": {}})}, writes)
            keys = json.loads(writes["push.json"])
            self.assertTrue(keys["publicKey"] and keys["privateKey"])
            self.assertIn("w1", sync_hub._state["push_subs"])
            again = {}
            sync_hub._push_setup({"push.json": writes["push.json"]}, again)
            self.assertNotIn("push.json", again)


if __name__ == "__main__":
    unittest.main()
