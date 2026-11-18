import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class AdbTest(unittest.TestCase):
    def setUp(self):
        from core import adb_control
        self.A = adb_control
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(adb_control, "_STATE", Path(self.tmp.name) / "dev.json")
        self.p.start()
        self.calls = []

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def fake_run(self, args, timeout=20, binary=False):
        self.calls.append(args)
        if args[0] == "connect":
            return 0, "connected to 192.168.1.50:5555"
        if "get-state" in args:
            return 0, "device"
        cmd = args[-1] if args[:1] == ["-s"] else ""
        answers = {"getprop ro.product.model": "HY320", "getprop ro.product.manufacturer": "Allwinner",
                   "getprop ro.build.version.release": "11", "getprop ro.board.platform": "sun50iw12p1",
                   "wm size": "Physical size: 1920x1080",
                   "pm list packages -3": "package:com.google.android.youtube.tv\npackage:com.netflix.ninja",
                   "pm list packages -s": "package:com.android.chrome\npackage:com.android.tv.settings"}
        return 0, answers.get(cmd, "Events injected: 1")

    def test_learns_the_projector(self):
        with mock.patch.object(self.A, "_run", side_effect=self.fake_run):
            ok, msg = self.A.learn("Projeksiyon", "192.168.1.50")
        self.assertTrue(ok, msg)
        self.assertIn("HY320", msg)
        self.assertIn("youtube", msg)
        self.assertEqual(self.A.resolve("projeksiyon")[1]["android"], "11")

    def test_remote_actions_become_adb_commands(self):
        with mock.patch.object(self.A, "_run", side_effect=self.fake_run):
            self.A.learn("Projeksiyon", "192.168.1.50")
            self.calls.clear()
            self.assertTrue(self.A.press("sesi kıs")[0])
            self.assertTrue(self.A.open_app("youtube")[0])
            self.A.type_text("Tarkan şımarık", enter=True)
            self.A.wifi("EvAgi", "sifre123")
        shells = [c[-1] for c in self.calls if c[:1] == ["-s"] and c[2] == "shell"]
        self.assertIn("input keyevent 25", shells)
        self.assertTrue(any("monkey -p com.google.android.youtube.tv" in s for s in shells))
        self.assertTrue(any(s.startswith('input text "Tarkan%ssimarik"') for s in shells))   # plain letters, %s spaces
        self.assertTrue(any("cmd wifi connect-network 'EvAgi' wpa2 'sifre123'" in s for s in shells))

    def test_unknown_key_and_no_device(self):
        self.assertFalse(self.A.press("uçur")[0])
        self.assertIn("Kayıtlı", self.A.open_url("https://x.com")[1])

    def test_phone_remote_reaches_adb(self):
        from core import sync_hub
        with mock.patch.dict(sync_hub._state, {"pending": []}), \
             mock.patch("core.adb_control.press", return_value=(True, "up tuşuna basıldı.")) as pr:
            sync_hub._run_command("c1", "adb:key:up", "Telefon")
            import time
            for _ in range(50):
                if sync_hub._state["pending"]:
                    break
                time.sleep(0.02)
            self.assertEqual(sync_hub._state["pending"][0]["reply"], "up tuşuna basıldı.")
        pr.assert_called_once_with("up", "")


class PcExtraTest(unittest.TestCase):
    def test_power_needs_confirmation(self):
        from plugins import pc_extra
        self.assertIn("onay", pc_extra.run({"action": "power", "op": "shutdown"}))

    def test_protected_processes_are_not_killed(self):
        from plugins import pc_extra
        self.assertIn("kapatmıyorum", pc_extra.run({"action": "processes", "op": "kill", "name": "explorer.exe"}))

    def test_info_and_top(self):
        from plugins import pc_extra
        self.assertIn("çekirdek", pc_extra.run({"action": "info"}))
        self.assertIn("En çok işlemci", pc_extra.run({"action": "processes", "op": "top"}))


if __name__ == "__main__":
    unittest.main()
