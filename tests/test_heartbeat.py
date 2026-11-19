"""Background watchers can be told alive from stopped, and the self-check says so."""
import unittest
from unittest import mock

from core import heartbeat


class HeartbeatTest(unittest.TestCase):
    def setUp(self):
        heartbeat._beats.clear()
        heartbeat._stopped.clear()

    def test_states(self):
        heartbeat.beat("away")
        st = heartbeat.status()
        self.assertTrue(st["away"]["ok"])
        self.assertEqual(st["vigil"]["why"], "not started yet")
        st = heartbeat.status(now=heartbeat._beats["away"] + 500)
        self.assertFalse(st["away"]["ok"])
        heartbeat.stopped("sentinel", "RuntimeError('x')")
        self.assertFalse(heartbeat.status()["sentinel"]["ok"])
        heartbeat.beat("sentinel")
        self.assertTrue(heartbeat.status()["sentinel"]["ok"])

    def test_self_check_reports(self):
        from plugins import self_check as sc
        self.assertEqual(sc.check_watchers()[0], sc.OK)
        heartbeat.beat("away")
        heartbeat.stopped("vigil", "boom")
        mark, text, fix = sc.check_watchers()
        self.assertEqual(mark, sc.FAIL)
        self.assertIn("mola notları", text)

    def test_home_check(self):
        from plugins import self_check as sc, smart_home
        with mock.patch.object(smart_home, "_cfg", lambda: {}):
            self.assertIn("bağlı değil", sc.check_home()[1])
        with mock.patch.object(smart_home, "_cfg", lambda: {"url": "u", "token": "t"}), \
             mock.patch.object(smart_home, "_states", lambda: [1, 2, 3]):
            self.assertIn("3 cihaz", sc.check_home()[1])


if __name__ == "__main__":
    unittest.main()
