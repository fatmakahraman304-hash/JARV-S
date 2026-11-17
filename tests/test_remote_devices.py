"""Phone remote: device discovery, TV pairing, quick actions, page wiring."""
import re
import unittest
from pathlib import Path
from unittest import mock

from dashboard import devices
from core import remote_control

ROOT = Path(__file__).resolve().parent.parent


class DiscoveryTest(unittest.TestCase):
    def test_round_trip_uses_sender_address(self):
        info = {"id": "abc123", "name": "Laptop", "os": "Windows 11", "kind": "laptop",
                "url": "http://10.0.0.99:8000"}
        peer = devices.decode_announce(devices.encode_announce(info), "192.168.1.20")
        self.assertEqual(peer["url"], "http://192.168.1.20:8000")
        self.assertEqual(peer["kind"], "laptop")
        self.assertEqual(peer["name"], "Laptop")

    def test_rejects_foreign_packets(self):
        self.assertIsNone(devices.decode_announce(b"hello", "1.2.3.4"))
        self.assertIsNone(devices.decode_announce(b'{"m":"other","id":"x","url":"http://a:1"}', "1.2.3.4"))
        self.assertIsNone(devices.decode_announce(
            b'{"m":"JARVIS-DEVICE-1","id":"x","url":"ftp://a:1"}', "1.2.3.4"))

    def test_peers_list_and_timeout(self):
        d = devices.Discovery(lambda: {})
        with mock.patch.object(devices, "device_id", return_value="me"):
            d.note({"id": "me", "name": "Me", "os": "", "kind": "desktop", "url": "http://a:8000"})
            d.note({"id": "p1", "name": "Laptop", "os": "", "kind": "laptop", "url": "http://b:8000"})
        peers = d.peers()
        self.assertEqual([p["id"] for p in peers], ["p1"])
        self.assertTrue(peers[0]["online"])
        d._peers["p1"]["seen"] -= devices.PEER_TIMEOUT + 1
        self.assertFalse(d.peers()[0]["online"])


class ScreenPairingTest(unittest.TestCase):
    def test_code_pairing_flow(self):
        reg = devices.ScreenRegistry()
        hello = reg.hello("Salon")
        self.assertEqual(len(hello["code"]), 6)
        self.assertEqual(reg.poll(hello["screen_id"])["state"], "waiting")
        self.assertEqual(reg.listing(), [])
        wrong = "000000" if hello["code"] != "000000" else "111111"
        self.assertIsNone(reg.approve(wrong))
        got = reg.approve(hello["code"][:3] + " " + hello["code"][3:], "Salon TV")
        self.assertEqual(got["name"], "Salon TV")
        self.assertIsNone(reg.approve(hello["code"]))          # one use only
        p = reg.poll(hello["screen_id"])
        self.assertEqual(p["state"], "paired")
        self.assertEqual(reg.screen_for_token(p["token"]), hello["screen_id"])
        self.assertIsNone(reg.screen_for_token("nope"))
        self.assertEqual(reg.listing({hello["screen_id"]})[0]["online"], True)
        self.assertTrue(reg.remove(hello["screen_id"]))
        self.assertIsNone(reg.screen_for_token(p["token"]))

    def test_expired_code_refused(self):
        reg = devices.ScreenRegistry()
        hello = reg.hello()
        reg._pending[hello["code"]]["ts"] -= reg.CODE_TTL + 1
        self.assertIsNone(reg.approve(hello["code"]))


class QuickActionTest(unittest.TestCase):
    def test_unknown_action(self):
        ok, msg, extra = remote_control.perform("format_disk")
        self.assertFalse(ok)
        self.assertEqual(extra, {})

    def test_media_key_goes_to_pyautogui(self):
        with mock.patch.object(remote_control.platform, "system", return_value="Windows"), \
             mock.patch.object(remote_control, "_press", return_value=True) as press:
            ok, _msg, _ = remote_control.perform("volume_up", 3)
        self.assertTrue(ok)
        press.assert_called_once_with("volumeup", 3)

    def test_youtube_links(self):
        self.assertEqual(remote_control.youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3")[0], "dQw4w9WgXcQ")
        self.assertEqual(remote_control.youtube_id("https://youtu.be/dQw4w9WgXcQ")[0], "dQw4w9WgXcQ")
        self.assertEqual(remote_control.youtube_id(""), ("", ""))


class TvPluginTest(unittest.TestCase):
    def test_without_server_explains(self):
        from plugins import tv_screen
        with mock.patch.object(tv_screen, "_server", return_value=None):
            out = tv_screen.run({"action": "video", "value": "x"})
        self.assertIsInstance(out, str)
        self.assertIn("kapalı", out)

    def test_text_goes_to_screen(self):
        from plugins import tv_screen
        srv = mock.Mock()
        srv.send_to_screen.return_value = "Televizyona gönderildi."
        with mock.patch.object(tv_screen, "_server", return_value=srv):
            self.assertEqual(tv_screen.run({"action": "text", "value": "Merhaba"}), "Televizyona gönderildi.")
        srv.send_to_screen.assert_called_once_with("text", "Merhaba")


class PageWiringTest(unittest.TestCase):
    """Every element the scripts look up must exist in the page."""

    def _check(self, name):
        html = (ROOT / "dashboard" / "static" / name).read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', html)) | set(re.findall(r"\.id = '([^']+)'", html))
        used = set(re.findall(r"getElementById\('([^']+)'\)", html)) | set(re.findall(r"\$\('([^']+)'\)", html))
        self.assertFalse(used - ids, f"{name}: missing elements {sorted(used - ids)}")

    def test_phone_page(self):
        self._check("app.html")

    def test_tv_page(self):
        self._check("tv.html")


if __name__ == "__main__":
    unittest.main()
