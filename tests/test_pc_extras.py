"""Computer-side plugins: focus_mode, clipboard_bridge, laptop_battery,
screen_time, disk_cleanup, network_check, system_alerts, wake_lan,
file_to_device, day_report — and sync_hub.cancel_reminder."""
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from core import sync_hub
from plugins import (_pc_kit, clipboard_bridge, day_report, disk_cleanup, file_to_device, focus_mode,
                     laptop_battery, network_check, screen_time, system_alerts, wake_lan)

NAMES = ["focus_mode", "clipboard_bridge", "laptop_battery", "screen_time", "disk_cleanup",
         "network_check", "system_alerts", "wake_lan", "file_to_device", "day_report"]


class DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(_pc_kit, "DATA", Path(self.tmp.name))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()


class LoaderTests(unittest.TestCase):
    def test_all_ten_load_as_plugins(self):
        from core import plugin_loader
        reg = plugin_loader.discover_plugins(Path(__file__).resolve().parent.parent / "plugins", set(), logger=lambda *_: None)
        names = {r.name for r in reg.all_records if r.ok} if hasattr(reg, "all_records") else set()
        if names:
            for n in NAMES:
                self.assertIn(n, names)
        for n in NAMES:
            mod = __import__(f"plugins.{n}", fromlist=["PLUGIN"])
            self.assertEqual(mod.PLUGIN["name"], n)
            self.assertTrue(callable(mod.run))


class FocusTests(DataDir):
    def test_plan_two_cycles(self):
        ph = focus_mode.plan(25, 5, 2, 1000.0, "rapor")
        self.assertEqual([round(p["at"] - 1000) for p in ph], [1500, 1800, 3300])
        self.assertIn("mola", ph[0]["text"])
        self.assertIn("tamamlandı", ph[-1]["text"])

    def test_start_status_stop(self):
        with mock.patch.object(_pc_kit, "say_at", return_value="") as say, mock.patch.object(_pc_kit, "cancel") as cancel:
            r = focus_mode.run({"action": "start", "minutes": 30, "task": "kod"})
            self.assertIn("30 dakika", r)
            self.assertEqual(say.call_count, 1)
            self.assertIn("Odak modu açık", focus_mode.run({"action": "status"}))
            self.assertIn("kapatıldı", focus_mode.run({"action": "stop"}))
            self.assertTrue(cancel.called)
            self.assertIn("kapalı", focus_mode.run({"action": "status"}))
        self.assertEqual(len(_pc_kit.load("focus.json")["log"]), 1)


class ClipboardTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(clipboard_bridge.command_for(" https://youtu.be/x ")["kind"], "open")
        self.assertEqual(clipboard_bridge.command_for("alışveriş: süt")["kind"], "text")
        self.assertEqual(clipboard_bridge.command_for("def f():\n    return 1")["kind"], "code")
        self.assertIsNone(clipboard_bridge.command_for("  "))

    def test_sends_to_phone_by_default(self):
        with mock.patch.object(clipboard_bridge, "read_clipboard", return_value="https://a.com"), \
             mock.patch.object(sync_hub, "send_to_device", return_value=(True, "Telefonum cihazına gönderiyorum.")) as s:
            r = clipboard_bridge.run({})
        self.assertEqual(s.call_args[0][0], "telefon")
        self.assertIn("bağlantıyı", r)


class BatteryTests(unittest.TestCase):
    def test_missing_sensor_and_unwatch(self):
        with mock.patch("psutil.sensors_battery", create=True, side_effect=FileNotFoundError):
            self.assertIn("pil yok", laptop_battery.run({"action": "status"}))
        with mock.patch.dict(laptop_battery._watch, on=True), mock.patch.object(laptop_battery, "_battery") as read:
            laptop_battery.run({"action": "unwatch"})
            self.assertFalse(laptop_battery._watch["on"])
            read.assert_not_called()

    def test_advice(self):
        self.assertIn("şarja tak", laptop_battery.advice(15, False, 1800).lower())
        self.assertIn("30 dk", laptop_battery.advice(50, False, 1800))
        self.assertIn("şarjdan çıkar", laptop_battery.advice(97, True, -2))

    def test_crossings_once(self):
        self.assertEqual(laptop_battery.crossing(None, 15, False), "")
        self.assertIn("%19", laptop_battery.crossing(21, 19, False))
        self.assertIn("şarja tak", laptop_battery.crossing(11, 9.6, False))
        self.assertEqual(laptop_battery.crossing(19, 18, False), "")
        self.assertIn("%95", laptop_battery.crossing(94, 95, True))
        self.assertEqual(laptop_battery.crossing(21, 19, True), "")


class ScreenTimeTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(screen_time.app_label(r"C:\x\chrome.exe"), "Chrome")
        self.assertEqual(screen_time.app_label("Code.exe"), "VS Code")
        self.assertEqual(screen_time.app_label("figma"), "Figma")

    def test_report(self):
        d = {}
        t = date(2026, 11, 18)
        for app, s in (("Chrome", 3600), ("VS Code", 1800), ("Chrome", 600)):
            screen_time.add_sample(d, t.isoformat(), app, s)
        screen_time.add_sample(d, "2026-11-17", "Spotify", 1200)
        self.assertEqual(screen_time.report_text(d, "today", t), "Bugün bilgisayarda 1 sa 40 dk aktiftin. En çok: Chrome 1 sa 10 dk, VS Code 30 dk.")
        self.assertIn("Spotify 20 dk", screen_time.report_text(d, "yesterday", t))
        self.assertIn("2 sa", screen_time.report_text(d, "week", t))
        self.assertIn("kayıt yok", screen_time.report_text({}, "today", t))

    def test_keeps_60_days(self):
        d = {}
        for i in range(70):
            screen_time.add_sample(d, f"2026-01-{i:02d}", "A", 1)
        self.assertEqual(len(d), 60)


class DiskTests(unittest.TestCase):
    def test_old_files_and_clean_needs_confirm(self):
        with tempfile.TemporaryDirectory() as t:
            old, new = Path(t, "old.tmp"), Path(t, "new.tmp")
            old.write_bytes(b"x" * 1000); new.write_bytes(b"y")
            past = time.time() - 5 * 86400
            os.utime(old, (past, past))
            found = disk_cleanup.old_files(Path(t), time.time())
            self.assertEqual([p.name for p, _ in found], ["old.tmp"])
            with mock.patch.object(disk_cleanup, "temp_dirs", return_value=[Path(t)]):
                self.assertIn("1 eski dosya", disk_cleanup.run({"action": "scan"}))
                self.assertIn("Onaylıyor", disk_cleanup.run({"action": "clean"}))
                self.assertTrue(old.exists())
                self.assertIn("1 geçici dosya silindi", disk_cleanup.run({"action": "clean", "confirm": True}))
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())

    def test_sizes(self):
        self.assertEqual(_pc_kit.human_size(512), "512 B")
        self.assertEqual(_pc_kit.human_size(5 * 1024 ** 2), "5.0 MB")


class NetworkTests(unittest.TestCase):
    def test_verdicts(self):
        self.assertIn("hiçbir ağa", network_check.verdict([None], None, ""))
        self.assertIn("internete çıkılamıyor", network_check.verdict([None, None], 20, "192.168.1.5"))
        self.assertTrue(network_check.verdict([20, 25, 30], 15, "192.168.1.5").startswith("İnternet iyi: gecikme 20 ms"))
        slow = network_check.verdict([250, None], 400, "10.0.0.2")
        self.assertIn("yavaş", slow); self.assertIn("1/2", slow); self.assertIn("DNS yavaş", slow)
        self.assertIn("DNS çalışmıyor", network_check.verdict([30], None, "10.0.0.2"))


class AlertTests(unittest.TestCase):
    def test_cpu_needs_a_streak_and_quiet_hour(self):
        memo = {}
        hot = {"cpu": 97, "ram": 50, "disk_free_gb": 100, "top": "chrome.exe"}
        self.assertEqual(system_alerts.check(hot, memo, 0), [])
        self.assertEqual(system_alerts.check(hot, memo, 30), [])
        out = system_alerts.check(hot, memo, 60)
        self.assertEqual(len(out), 1); self.assertIn("chrome.exe", out[0])
        self.assertEqual(system_alerts.check(hot, memo, 90), [])                 # said this hour
        self.assertEqual(len(system_alerts.check(hot, memo, 3700)), 1)

    def test_ram_and_disk(self):
        out = system_alerts.check({"cpu": 10, "ram": 95, "disk_free_gb": 2.5}, {}, 0)
        self.assertEqual(len(out), 2)
        self.assertIn("2.5 GB", out[1])


class WakeTests(DataDir):
    def test_packet(self):
        pkt = wake_lan.magic_packet("aa-bb-cc-dd-ee-ff")
        self.assertEqual(len(pkt), 102)
        self.assertEqual(pkt[:6], b"\xff" * 6)
        self.assertEqual(pkt[6:12], bytes.fromhex("aabbccddeeff"))
        with self.assertRaises(ValueError):
            wake_lan.norm_mac("12:34")

    def test_save_and_wake(self):
        self.assertIn("Kaydettim", wake_lan.run({"action": "save", "name": "Masaüstü", "mac": "AA:BB:CC:DD:EE:FF"}))
        with mock.patch.object(wake_lan, "send") as s:
            self.assertIn("uyandırma sinyali", wake_lan.run({"action": "wake", "name": "masaüstü"}))
            s.assert_called_once_with("AA:BB:CC:DD:EE:FF")
            self.assertIn("bulunamadı", wake_lan.run({"action": "wake", "name": "oyun"}))


class FileTests(unittest.TestCase):
    def test_find_and_command(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "sub").mkdir()
            img = root / "sub" / "Fatura Kasım.png"; img.write_bytes(b"\x89PNG....")
            note = root / "notlar.md"; note.write_text("# merhaba", encoding="utf-8")
            (root / "x.zip").write_bytes(b"z")
            self.assertEqual(file_to_device.find_file("fatura", [root]), img)
            self.assertEqual(file_to_device.find_file("notlar", [root]), note)
            self.assertIsNone(file_to_device.find_file("yok", [root]))
            cmd, _ = file_to_device.command_for(img)
            self.assertEqual((cmd["kind"], cmd["mime"]), ("image", "image/png"))
            self.assertEqual(file_to_device.command_for(note)[0]["kind"], "text")
            self.assertIsNone(file_to_device.command_for(root / "x.zip")[0])


class DayReportTests(unittest.TestCase):
    def test_build(self):
        spoken, full = day_report.build("Bugün bilgisayarda 2 sa aktiftin.", (2, 50), "Pil %80, şarj oluyor.",
                                        "1. süt al\n2. fatura öde", ["Per 09:00 — toplantı"])
        self.assertIn("2 odak turu", spoken); self.assertIn("2 iş", spoken); self.assertIn("toplantı", spoken)
        self.assertIn("SIRADAKİ HATIRLATICILAR", full)

    def test_focus_today(self):
        from datetime import datetime
        today = date(2026, 11, 25)
        now = datetime(2026, 11, 25, 12).timestamp()
        with mock.patch.object(day_report.time, "time", return_value=now):
            n, m = day_report.focus_today([
                {"start": now - 3000, "end": now - 1500},
                {"start": now - 10 * 86400, "end": now - 10 * 86400 + 60},
            ], today=today)
        self.assertEqual(n, 1); self.assertAlmostEqual(m, 25, delta=0.1)

    def test_focus_today_near_midnight_excludes_previous_day(self):
        from datetime import datetime
        today = date(2026, 11, 25)
        midnight = datetime(2026, 11, 25).timestamp()
        with mock.patch.object(day_report.time, "time", return_value=midnight + 600):
            n, m = day_report.focus_today([
                {"start": midnight - 3000, "end": midnight - 1500},
                {"start": midnight + 60, "end": midnight + 360},
            ], today=today)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(m, 5, delta=0.1)


class CancelReminderTests(unittest.TestCase):
    def test_cancel_wins_the_merge(self):
        with mock.patch.dict(sync_hub._state, {"rem_new": [], "reminders": [{"id": "r1", "text": "a", "due": 5e12, "cancelled": ""}]}):
            self.assertTrue(sync_hub.cancel_reminder("r1"))
            self.assertFalse(sync_hub.cancel_reminder("nope"))
            merged = sync_hub.merge_reminders([{"id": "r1", "text": "a", "due": 5e12, "cancelled": ""}], sync_hub._state["rem_new"], 1e12)
        self.assertTrue(merged[0]["cancelled"])


if __name__ == "__main__":
    unittest.main()
