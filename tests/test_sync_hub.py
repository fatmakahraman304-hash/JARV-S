"""JARVIS everywhere: memory merge, setup link, remote commands, web page wiring."""
import base64
import json
import re
import time
import unittest
from pathlib import Path
from unittest import mock

from core import sync_hub

ROOT = Path(__file__).resolve().parent.parent


class MergeTest(unittest.TestCase):
    def test_newer_wins_and_union(self):
        a = {"notes": {"x": {"value": "eski", "updated": "2026-01-01"}, "only_a": "düz"}}
        b = {"notes": {"x": {"value": "yeni", "updated": "2026-02-01T10:00:00Z"}},
             "preferences": {"çay": {"value": "şekersiz", "updated": "2026-02-01"}}}
        m = sync_hub.merge_memory(a, b)
        self.assertEqual(m["notes"]["x"]["value"], "yeni")
        self.assertEqual(m["notes"]["only_a"]["value"], "düz")
        self.assertEqual(m["preferences"]["çay"]["value"], "şekersiz")

    def test_tombstone_removes_older_entry(self):
        a = {"notes": {"x": {"value": "v", "updated": "2026-01-01"}}}
        b = {"notes": {}, "_deleted": {"notes/x": "2026-01-02T00:00:00Z"}}
        m = sync_hub.merge_memory(a, b)
        self.assertNotIn("x", m["notes"])
        self.assertIn("notes/x", m["_deleted"])
        # re-added later: the newer entry survives the old tombstone
        a2 = {"notes": {"x": {"value": "geri", "updated": "2026-03-01T00:00:00Z"}}}
        self.assertEqual(sync_hub.merge_memory(a2, b)["notes"]["x"]["value"], "geri")


class VoiceOwnerTest(unittest.TestCase):
    """One voice: phone first, then the computer, then the rest; a device the
    user just turned to wins for a while."""

    def _d(self, id_, kind, active=True, age=5, claim_age=None):
        now = 1_800_000_000
        iso = lambda a: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - a))
        return {"id": id_, "kind": kind, "active": active, "seen": iso(age),
                "claim": iso(claim_age) if claim_age is not None else ""}

    def test_priority(self):
        now = 1_800_000_000
        devs = [self._d("tv", "tv"), self._d("pc", "pc"), self._d("ph", "phone"), self._d("w", "watch")]
        self.assertEqual(sync_hub.voice_owner(devs, now), "ph")
        devs[2]["active"] = False                       # phone put away
        self.assertEqual(sync_hub.voice_owner(devs, now), "pc")
        devs[1] = self._d("pc", "pc", age=120)          # laptop closed (no heartbeat)
        self.assertEqual(sync_hub.voice_owner(devs, now), "tv")
        self.assertIsNone(sync_hub.voice_owner([], now))

    def test_claim_wins_then_expires(self):
        now = 1_800_000_000
        devs = [self._d("ph", "phone"), self._d("pc", "pc", claim_age=30)]
        self.assertEqual(sync_hub.voice_owner(devs, now), "pc")
        devs[1] = self._d("pc", "pc", claim_age=sync_hub.CLAIM_SECONDS + 5)
        self.assertEqual(sync_hub.voice_owner(devs, now), "ph")


class SetupLinkTest(unittest.TestCase):
    def test_link_carries_settings(self):
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "ghp_x", "gist_id": "abc"}), \
             mock.patch.object(sync_hub, "_assistant_name", return_value="JARVIS"):
            link = sync_hub.setup_link("AIzaKEY")
        self.assertTrue(link.startswith(sync_hub.WEB_URL + "#s="))
        blob = link.split("#s=", 1)[1]
        data = json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
        self.assertEqual(data, {"g": "AIzaKEY", "t": "ghp_x", "i": "abc", "n": "JARVIS"})


class CommandTest(unittest.TestCase):
    def setUp(self):
        sync_hub._state["pending"] = []
        sync_hub._state["inject"] = None

    def test_command_goes_to_session_and_waits_for_reply(self):
        got = []
        sync_hub._state["inject"] = got.append
        sync_hub._run_command("c1", "sunumu aç", "Telefon")
        self.assertEqual(got, ["[Telefon cihazından komut] sunumu aç"])
        self.assertIsNone(sync_hub._state["pending"][0]["reply"])
        sync_hub.note_reply("Sunumu açtım.")
        self.assertEqual(sync_hub._state["pending"][0]["reply"], "Sunumu açtım.")

    def test_quick_action_runs_directly(self):
        with mock.patch("core.remote_control.perform", return_value=(True, "Ses açıldı", {})) as perf:
            sync_hub._run_command("c2", "quick:volume_up", "Saat")
        perf.assert_called_once_with("volume_up")
        self.assertEqual(sync_hub._state["pending"][0]["reply"], "Ses açıldı")

    def test_no_session(self):
        sync_hub._run_command("c3", "merhaba", "Tablet")
        self.assertIn("açık değil", sync_hub._state["pending"][0]["reply"])


class CycleTest(unittest.TestCase):
    def test_inbox_is_processed_and_answer_written(self):
        sync_hub._state.update(pending=[], done=set(), etag="", last_memory=time.time(),
                               last_beat=time.time(), turns=[])
        got = []
        sync_hub._state["inject"] = got.append
        files = {"inbox-pc1.json": json.dumps([{"id": "k1", "text": "ekranda ne var", "from": "Telefon"}]),
                 "memory.json": "{}", "recent.json": "[]"}
        writes = []
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "g"}), \
             mock.patch.object(sync_hub, "device_id", return_value="pc1"), \
             mock.patch.object(sync_hub, "read_gist", return_value=(files, "e1", "")), \
             mock.patch.object(sync_hub, "write_files", side_effect=lambda t, g, f: writes.append(f) or True):
            sync_hub._cycle()
            self.assertEqual(got, ["[Telefon cihazından komut] ekranda ne var"])
            self.assertEqual(writes[-1]["inbox-pc1.json"], "[]")
            sync_hub.note_reply("Ekranda bir kod düzenleyici açık.")
            sync_hub._cycle()
        out = json.loads(writes[-1]["outbox-pc1.json"])
        self.assertEqual(out[-1]["id"], "k1")
        self.assertIn("kod düzenleyici", out[-1]["reply"])


class UpdateAllTest(unittest.TestCase):
    def test_update_file_triggers_once_but_not_on_first_look(self):
        calls = []
        sync_hub._state.update(pending=[], done=set(), etag="", last_memory=time.time(),
                               last_beat=time.time(), turns=[], on_update=lambda: calls.append(1))
        sync_hub._state.pop("update_seen", None)
        files = {"update.json": json.dumps({"ts": "2026-11-18T10:00:00Z", "by": "Telefon"}), "memory.json": "{}"}
        with mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "g"}), \
             mock.patch.object(sync_hub, "device_id", return_value="pc1"), \
             mock.patch.object(sync_hub, "write_files", return_value=True), \
             mock.patch.object(sync_hub, "read_gist", return_value=(files, "", "")):
            sync_hub._cycle()                       # an old request: remembered, not obeyed
            self.assertEqual(calls, [])
            files["update.json"] = json.dumps({"ts": "2026-11-18T10:05:00Z", "by": "Telefon"})
            sync_hub._cycle()
            sync_hub._cycle()
        self.assertEqual(calls, [1])

    def test_update_command_from_mailbox(self):
        calls = []
        sync_hub._state.update(pending=[], on_update=lambda: calls.append(1))
        sync_hub._run_command("u1", "update:", "Telefon")
        self.assertEqual(calls, [1])
        self.assertIn("Güncelleme başladı", sync_hub._state["pending"][0]["reply"])


class SharedRemindersTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._patches = [mock.patch.object(sync_hub, "_REM_FILE", Path(self._tmp.name) / "rem.json"),
                         mock.patch.dict(sync_hub._state, {"rem_new": [], "rem_known": None, "on_reminder": None})]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_merge_union_cancel_wins_old_dropped(self):
        now = 1_800_000_000_000
        a = [{"id": "x", "text": "süt", "due": now + 60_000, "cancelled": ""},
             {"id": "old", "text": "o", "due": now - 2 * 86_400_000}]
        b = [{"id": "x", "text": "süt", "due": now + 60_000, "cancelled": "2026-11-18T09:00:00Z"},
             {"id": "y", "text": "ilaç", "due": now + 100_000}]
        m = sync_hub.merge_reminders(a, b, now)
        self.assertEqual([(r["id"], bool(r["cancelled"])) for r in m], [("x", True), ("y", False)])

    def test_daily_brings_the_same_next_day_everywhere(self):
        now = 1_800_000_000_000
        daily = [{"id": "w-a", "text": "ilaç", "due": now - 1000, "repeat": "daily", "cancelled": ""}]
        m1 = sync_hub.merge_reminders(daily, [], now)
        self.assertEqual([r["id"] for r in m1], ["w-a", f"w-a@{now - 1000 + 86_400_000}"])
        self.assertEqual(len(sync_hub.merge_reminders(m1, m1, now)), 2)      # two devices: still one next day
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("split('@')[0]}@${nxt}", js)                           # same id rule on the web

    def test_scheduled_protocol_is_carried_out_on_desktop(self):
        from actions import reminder
        added = []

        class Eng:
            def list(self):
                return []

            def add(self, **kw):
                added.append(kw)
        r = {"id": "w-b", "text": "sabah protokolü", "protocol": "sabah", "due": (time.time() + 600) * 1000}
        with mock.patch("core.routines.desktop.engine", return_value=Eng()):
            reminder.on_shared_reminder("new", r)
        self.assertEqual(added[0]["kind"], "prompt")
        self.assertIn("sabah", added[0]["text"])

    def test_phone_reminder_reaches_desktop_once_and_cancel_follows(self):
        events = []
        sync_hub.on_reminder(lambda ev, r: events.append((ev, r["id"])))
        now = time.time()
        phone = [{"id": "w1-a", "text": "ilaç iç", "due": (now + 600) * 1000, "from": "Telefon", "cancelled": ""}]
        writes = {}
        sync_hub._sync_reminders({"reminders.json": json.dumps(phone)}, writes, now)
        self.assertEqual(events, [("new", "w1-a")])
        self.assertNotIn("reminders.json", writes)          # nothing new to send
        sync_hub._sync_reminders({"reminders.json": json.dumps(phone)}, writes, now)
        self.assertEqual(events, [("new", "w1-a")])          # not twice
        phone[0]["cancelled"] = "2026-11-18T10:00:00Z"
        sync_hub._sync_reminders({"reminders.json": json.dumps(phone)}, writes, now)
        self.assertEqual(events[-1], ("cancelled", "w1-a"))

    def test_desktop_reminder_is_written_for_the_devices(self):
        events = []
        sync_hub.on_reminder(lambda ev, r: events.append(ev))
        now = time.time()
        rid = sync_hub.add_reminder("toplantı", now + 3600)
        writes = {}
        sync_hub._sync_reminders({}, writes, now)
        sent = json.loads(writes["reminders.json"])
        self.assertEqual([r["id"] for r in sent], [rid])
        self.assertEqual(events, [])                          # our own: no callback

    def test_desktop_says_phone_reminder_and_drops_it_when_cancelled(self):
        from actions import reminder

        class Eng:
            def __init__(self):
                self.r = []

            def list(self):
                return list(self.r)

            def add(self, **kw):
                kw["id"] = str(len(self.r))
                self.r.append(kw)

            def remove(self, rid):
                self.r = [x for x in self.r if x["id"] != rid]
        eng = Eng()
        r = {"id": "w1-b", "text": "ilaç", "due": (time.time() + 600) * 1000, "from": "Telefon"}
        with mock.patch("core.routines.desktop.engine", return_value=eng):
            reminder.on_shared_reminder("new", r)
            reminder.on_shared_reminder("new", r)                 # once only
            self.assertEqual(len(eng.r), 1)
            self.assertEqual(eng.r[0]["source"], "shared:w1-b")
            self.assertIn("ilaç", eng.r[0]["text"])
            reminder.on_shared_reminder("cancelled", r)
            self.assertEqual(eng.r, [])

    def test_web_uses_the_same_file(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("reminders.json", js)
        self.assertIn("function mergeReminders", js)


class SendToDeviceTest(unittest.TestCase):
    def _devs(self):
        now = sync_hub._now()
        return [{"id": "w-phone", "name": "Telefonum", "kind": "phone", "seen": now},
                {"id": "w-tv", "name": "Salon", "kind": "tv", "seen": now},
                {"id": "w-old-tv", "name": "Yatak odası", "kind": "tv", "seen": "2020-01-01T00:00:00Z"}]

    def setUp(self):
        self._p = [mock.patch.dict(sync_hub._state, {"devices": self._devs(), "out_cmds": []}),
                   mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "g"})]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_find_by_kind_prefers_online_and_by_name(self):
        self.assertEqual(sync_hub.find_device("televizyon")["id"], "w-tv")
        self.assertEqual(sync_hub.find_device("yatak odası")["id"], "w-old-tv")
        self.assertEqual(sync_hub.find_device("telefonuma")["id"], "w-phone")
        self.assertIsNone(sync_hub.find_device("buzdolabı"))

    def test_queued_then_written_to_that_devices_inbox(self):
        ok, msg = sync_hub.send_to_device("tv", {"kind": "open", "url": "https://youtu.be/x"})
        self.assertTrue(ok, msg)
        writes = {}
        sync_hub._deliver_out({"inbox-w-tv.json": json.dumps([{"id": "old", "kind": "say", "text": "x"}])}, writes)
        box = json.loads(writes["inbox-w-tv.json"])
        self.assertEqual([b["kind"] for b in box], ["say", "open"])
        self.assertEqual(box[-1]["url"], "https://youtu.be/x")
        self.assertFalse(sync_hub._state["out_cmds"])

    def test_plugin_sends_free_picture_as_link(self):
        from plugins import send_to_device
        sent = []
        with mock.patch("core.image_studio.last_image", return_value=Path(__file__)), \
             mock.patch("core.image_studio.history_entry", return_value={"url": "https://image.pollinations.ai/p/x", "prompt": "tilki"}), \
             mock.patch.object(sync_hub, "send_to_device", side_effect=lambda d, c: sent.append((d, c)) or (True, "ok")):
            self.assertEqual(send_to_device.run({"device": "tv", "what": "image"}), "ok")
        self.assertEqual(sent[0][1]["url"], "https://image.pollinations.ai/p/x")
        self.assertNotIn("data", sent[0][1])
        self.assertIn("adres", send_to_device.run({"device": "tv", "what": "open", "url": "dosya"}))
        with mock.patch.object(sync_hub, "send_to_device", side_effect=lambda d, c: sent.append((d, c)) or (True, "ok")):
            send_to_device.run({"device": "tablet", "what": "guard_on"})
        self.assertEqual(sent[-1], ("tablet", {"kind": "guard", "on": True}))

    def test_web_reads_its_inbox(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function runInbox", js)
        self.assertIn("c.kind === 'guard'", js)
        self.assertIn("inbox-${S.id}.json", js)


class ProjectsSummaryTest(unittest.TestCase):
    def test_staged_project_shows_current_stage(self):
        rows = [{"id": 7, "kind": "build", "title": "Kafe sitesi", "folder": "/home/u/kafe", "status": "yarıda kaldı",
                 "stage": 2, "stages": {"plan": {"stages": [{"title": "Plan"}, {"title": "Menü sayfası"}, {"title": "Test"}]}},
                 "note": "menü yarım", "updated": "2026-11-18T09:00:00+00:00"},
                {"id": 6, "kind": "edit", "title": "Hesap makinesi", "folder": "", "status": "bitti", "stage": 0,
                 "stages": [], "note": "", "updated": "2026-11-17T09:00:00"}]
        with mock.patch("memory.continuity.projects", return_value=rows):
            out = sync_hub.projects_summary()
        self.assertEqual(out[0]["current"], "Menü sayfası")
        self.assertEqual((out[0]["stage"], out[0]["stages"], out[0]["folder"]), (2, 3, "kafe"))
        self.assertEqual(out[1]["stages"], 0)

    def test_desktop_hears_what_was_said_on_the_phone(self):
        now = sync_hub._now()
        turns = [{"ts": now, "device": "Telefon", "role": "user", "text": "akşam sinemaya gidiyoruz"},
                 {"ts": now, "device": "MASAÜSTÜ", "role": "user", "text": "burada söylendi"},
                 {"ts": "2020-01-01T00:00:00Z", "device": "Telefon", "role": "user", "text": "eski"}]
        with mock.patch.dict(sync_hub._state, {"recent": turns}), \
             mock.patch.object(sync_hub, "device_name", return_value="MASAÜSTÜ"):
            ctx = sync_hub.recent_context()
        self.assertIn("[Telefon] Kullanıcı: akşam sinemaya gidiyoruz", ctx)
        self.assertNotIn("burada söylendi", ctx)
        self.assertNotIn("eski", ctx)
        with mock.patch.dict(sync_hub._state, {"recent": []}):
            self.assertEqual(sync_hub.recent_context(), "")

    def test_web_shows_them(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("projects-", js)
        self.assertIn("function projectsText", js)


class ComputerReceivesTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.shown = []
        self._p = [mock.patch.dict(sync_hub._state, {"pending": [], "on_item": lambda *a: self.shown.append(a)}),
                   mock.patch.object(sync_hub, "_received_dir", return_value=Path(self.tmp.name))]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()
        self.tmp.cleanup()

    def test_code_is_saved_and_shown(self):
        sync_hub._receive_item("c1", {"kind": "code", "filename": "../site/index.html", "text": "<h1>Merhaba</h1>"}, "Telefon")
        saved = list(Path(self.tmp.name).iterdir())
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(encoding="utf-8"), "<h1>Merhaba</h1>")
        self.assertNotIn("..", saved[0].name.split("_")[0])
        self.assertEqual(self.shown[0][0], "code")
        self.assertIn("kaydedildi", sync_hub._state["pending"][0]["reply"])

    def test_picture_data_is_saved_and_remembered(self):
        import base64
        from core import image_studio
        png = b"\x89PNG" + b"0" * 500
        with mock.patch.object(image_studio, "out_dir", return_value=Path(self.tmp.name)), \
             mock.patch.object(image_studio, "_STATE", Path(self.tmp.name) / "st.json"):
            sync_hub._receive_image("i1", {"kind": "image", "data": base64.b64encode(png).decode(),
                                           "mime": "image/png", "prompt": "tilki"}, "Telefon")
            self.assertEqual(image_studio.last_image().read_bytes(), png)
        self.assertEqual(self.shown[0][0], "image")

    def test_screenshot_goes_back_to_the_phone(self):
        with mock.patch.dict(sync_hub._state, {"out_cmds": []}), \
             mock.patch("core.remote_control.screenshot_jpeg", return_value=b"\xff\xd8jpeg"):
            sync_hub._send_screenshot("s1", {"kind": "screenshot", "reply_to": "w-phone", "question": "indirme bitti mi"})
            dev, item = sync_hub._state["out_cmds"][0]
        self.assertEqual(dev, "w-phone")
        self.assertEqual((item["kind"], item["see"], item["question"]), ("image", True, "indirme bitti mi"))
        self.assertIn("gönderildi", sync_hub._state["pending"][-1]["reply"])

    def test_link_opens_in_browser(self):
        with mock.patch("webbrowser.open") as op:
            sync_hub._receive_item("o1", {"kind": "open", "url": "https://maps.google.com"}, "Telefon")
            op.assert_called_once_with("https://maps.google.com")
            sync_hub._receive_item("o2", {"kind": "open", "url": "file:///etc/passwd"}, "Telefon")
            self.assertEqual(op.call_count, 1)


class StatusReportTest(unittest.TestCase):
    def test_devices_with_health_and_reminders(self):
        now = sync_hub._now()
        devs = [{"id": "w1", "name": "Telefon", "kind": "phone", "seen": now, "battery": 14, "charging": False},
                {"id": "w2", "name": "Salon", "kind": "tv", "seen": "2020-01-01T00:00:00Z"}]
        rem = [{"id": "r", "text": "ilaç", "due": (time.time() + 3600) * 1000, "cancelled": ""}]
        with mock.patch.dict(sync_hub._state, {"devices": devs, "reminders": rem}), \
             mock.patch.object(sync_hub, "health", return_value={"cpu": 12, "battery": 80, "charging": True}), \
             mock.patch.object(sync_hub, "settings", return_value={"gist_id": "g"}):
            out = sync_hub.status_report()
        self.assertIn("Telefon (telefon): açık, pil %14", out)
        self.assertIn("Salon (televizyon): kapalı", out)
        self.assertIn("pil %80 (şarjda), işlemci %12", out)
        self.assertIn("ilaç", out)

    def test_health_has_numbers(self):
        h = sync_hub.health()
        self.assertIsInstance(h.get("cpu", 0), int)

    def test_plugin_runs(self):
        from plugins import status_report
        with mock.patch.object(sync_hub, "status_report", return_value="CİHAZLAR:\n- x"), \
             mock.patch.object(sync_hub, "projects_summary", return_value=[]):
            out = status_report.run({})
        self.assertIn("CİHAZLAR", out)
        self.assertIn("PROJELER", out)


class LowBatteryTest(unittest.TestCase):
    def test_announced_once_until_charged(self):
        now = sync_hub._now()
        alerted = set()
        phone = {"id": "p", "name": "Telefon", "battery": 12, "charging": False, "seen": now}
        self.assertEqual([d["id"] for d in sync_hub.low_battery([phone], alerted)], ["p"])
        self.assertEqual(sync_hub.low_battery([phone], alerted), [])            # once
        sync_hub.low_battery([dict(phone, charging=True)], alerted)              # plugged in: forgotten
        self.assertEqual(len(sync_hub.low_battery([phone], alerted)), 1)          # low again: said again
        self.assertEqual(sync_hub.low_battery([{"id": "x", "seen": now}], alerted), [])   # no battery info

    def test_only_the_voice_owner_speaks(self):
        said = []
        now = sync_hub._now()
        low = [{"id": "p", "name": "Telefon", "battery": 9, "charging": False, "seen": now}]
        with mock.patch.dict(sync_hub._state, {"devices": low, "owner": "p", "inject": said.append, "bat_alerted": set()}), \
             mock.patch.object(sync_hub, "health", return_value={}):
            sync_hub._battery_watch("me")
        self.assertEqual(said, [])
        with mock.patch.dict(sync_hub._state, {"devices": low, "owner": "me", "inject": said.append, "bat_alerted": set()}), \
             mock.patch.object(sync_hub, "health", return_value={}):
            sync_hub._battery_watch("me")
        self.assertIn("Telefon %9", said[0])

    def test_full_disk_said_once_a_day(self):
        said = []
        now = sync_hub._now()
        pcs = [{"id": "pc2", "name": "Laptop", "kind": "pc", "seen": now, "disk": 96}]
        with mock.patch.dict(sync_hub._state, {"devices": pcs, "owner": "me", "inject": said.append,
                                               "bat_alerted": set(), "disk_alerted": set()}), \
             mock.patch.object(sync_hub, "health", return_value={}):
            sync_hub._battery_watch("me")
            sync_hub._battery_watch("me")
        self.assertEqual(len(said), 1)
        self.assertIn("Laptop diski %96", said[0])


class GalleryTest(unittest.TestCase):
    def test_merge_keeps_links_only_and_newest(self):
        a = [{"id": "1", "url": "https://x/1", "ts": "2026-11-18T10:00:00Z", "prompt": "aslan"},
             {"id": "bad", "url": "", "ts": "2026-11-18T11:00:00Z"}]
        b = [{"id": "2", "url": "https://x/2", "ts": "2026-11-18T12:00:00Z", "prompt": "logo"}]
        self.assertEqual([g["id"] for g in sync_hub.merge_gallery(a, b)], ["1", "2"])

    def test_new_picture_is_written_and_listed(self):
        with mock.patch.dict(sync_hub._state, {"img_new": [], "gallery": []}):
            sync_hub.add_image("kırmızı tilki", "https://image.pollinations.ai/prompt/x", seed=5)
            sync_hub.add_image("yerel", "C:/resim.png")                      # no link: not shared
            writes = {}
            files = {"images.json": json.dumps([{"id": "o", "url": "https://x/o", "ts": "2026-01-01T00:00:00Z", "prompt": "eski"}])}
            # run only the gallery step of the cycle
            cloud_g = json.loads(files["images.json"])
            with sync_hub._state["lock"]:
                new_g, sync_hub._state["img_new"] = sync_hub._state["img_new"], []
            merged = sync_hub.merge_gallery(cloud_g, new_g)
            self.assertEqual([g["prompt"] for g in merged], ["eski", "kırmızı tilki"])
        from plugins import gallery
        with mock.patch.object(sync_hub, "gallery", return_value=merged):
            out = gallery.run({"action": "list"})
            self.assertTrue(out.splitlines()[1].startswith("1. kırmızı tilki"))
            sent = []
            with mock.patch.object(sync_hub, "send_to_device", side_effect=lambda d, c: sent.append(c) or (True, "ok")):
                gallery.run({"action": "send", "query": "eski", "device": "tv"})
            self.assertEqual(sent[0]["url"], "https://x/o")


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.store = {"old": json.dumps([{"ts": "2026-10-01T10:00:00Z", "device": "Telefon", "role": "user",
                                          "text": "annemin doğum günü 3 Mart"},
                                         {"ts": "2026-10-01T10:00:05Z", "device": "Telefon", "role": "jarvis",
                                          "text": "Not ettim efendim."}])}
        self.writes = []

        def read(token, gid, etag=""):
            if gid == "arch":
                return {"history-2026-10.json": self.store["old"],
                        **{k: v for k, v in self.store.items() if k.startswith("history-")}}, "", ""
            return {"archive.json": json.dumps({"gist": "arch"})}, "", ""

        def write(token, gid, files):
            self.writes.append((gid, files))
            self.store.update(files)
            return True
        self._p = [mock.patch.object(sync_hub, "read_gist", side_effect=read),
                   mock.patch.object(sync_hub, "write_files", side_effect=write),
                   mock.patch.object(sync_hub, "settings", return_value={"github_token": "t", "gist_id": "main"}),
                   mock.patch.dict(sync_hub._state, {"arch_queue": [], "arch_last": 0.0, "arch_id": ""})]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()

    def test_search_finds_with_the_line_around_it(self):
        out = sync_hub.search_archive("annemin doğum günü ne zaman")
        self.assertIn("3 Mart", out)
        self.assertIn("Not ettim", out)
        self.assertIn("bulamadım", sync_hub.search_archive("uzay gemisi"))

    def test_own_turns_are_written_by_month(self):
        sync_hub._state["thread"] = object()
        try:
            sync_hub.note_turn("Kullanıcı", "yarın sinemaya gidiyoruz")
        finally:
            sync_hub._state["thread"] = None
        sync_hub._archive_flush("t", {"archive.json": json.dumps({"gist": "arch"})}, time.time())
        gid, files = self.writes[-1]
        self.assertEqual(gid, "arch")
        name = next(iter(files))
        self.assertTrue(name.startswith("history-20"))
        self.assertIn("sinemaya", files[name])
        self.assertEqual(sync_hub._state["arch_queue"], [])

    def test_web_uses_the_same_archive(self):
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("'archive.json'", js)
        self.assertIn("history-${t.ts.slice(0, 7)}.json", js)


class DeliverToVoiceTest(unittest.TestCase):
    def test_result_goes_to_the_phone_when_it_has_the_voice(self):
        devs = [{"id": "w-phone", "name": "Telefon", "kind": "phone", "seen": sync_hub._now()}]
        with mock.patch.dict(sync_hub._state, {"owner": "w-phone", "devices": devs, "out_cmds": []}), \
             mock.patch.object(sync_hub, "settings", return_value={"gist_id": "g"}):
            self.assertEqual(sync_hub.deliver_to_voice("Görev bitti: araştırma", "sonuç"), "Telefon")
            dev, item = sync_hub._state["out_cmds"][0]
        self.assertEqual((dev, item["kind"], item["text"]), ("w-phone", "report", "sonuç"))
        with mock.patch.dict(sync_hub._state, {"owner": None, "devices": devs, "out_cmds": []}), \
             mock.patch.object(sync_hub, "settings", return_value={"gist_id": "g"}):
            self.assertEqual(sync_hub.deliver_to_voice("x", "y"), "")              # this computer speaks


class WebPageWiringTest(unittest.TestCase):
    def test_ids_exist(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        ids = set(re.findall(r'id="([^"]+)"', html))
        used = set(re.findall(r"\$\('([^']+)'\)", js))
        self.assertFalse(used - ids, f"missing: {sorted(used - ids)}")
        for name in ("manifest.webmanifest", "sw.js", "icon-192.png", "icon-512.png", "icon.svg"):
            self.assertTrue((ROOT / "web" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
