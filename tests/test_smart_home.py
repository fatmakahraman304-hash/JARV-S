"""Smart home via Home Assistant: the right device by the user's words, safe with locks."""
import unittest
from unittest import mock

from plugins import smart_home as sh

STATES = [
    {"entity_id": "light.salon", "state": "on", "attributes": {"friendly_name": "Salon Işığı", "brightness": 128}},
    {"entity_id": "light.yatak_odasi", "state": "off", "attributes": {"friendly_name": "Yatak Odası Lambası"}},
    {"entity_id": "light.mutfak", "state": "on", "attributes": {"friendly_name": "Mutfak"}},
    {"entity_id": "switch.kahve", "state": "off", "attributes": {"friendly_name": "Kahve Makinesi Prizi"}},
    {"entity_id": "climate.salon_klima", "state": "cool",
     "attributes": {"friendly_name": "Salon Klima", "current_temperature": 26, "temperature": 24}},
    {"entity_id": "cover.salon_perde", "state": "open", "attributes": {"friendly_name": "Salon Perde", "current_position": 100}},
    {"entity_id": "scene.film", "state": "scening", "attributes": {"friendly_name": "Film Gecesi"}},
    {"entity_id": "lock.on_kapi", "state": "locked", "attributes": {"friendly_name": "Ön Kapı"}},
    {"entity_id": "sensor.salon_sicaklik", "state": "23.5",
     "attributes": {"friendly_name": "Salon Sıcaklık", "unit_of_measurement": "°C"}},
]


class MatchTest(unittest.TestCase):
    def ids(self, target, **kw):
        return [e["entity_id"] for e in sh.match(target, STATES, **kw)]

    def test_by_room_and_type_with_turkish_endings(self):
        self.assertEqual(self.ids("salonun ışığı"), ["light.salon"])
        self.assertEqual(self.ids("yatak odasının lambası"), ["light.yatak_odasi"])
        self.assertEqual(self.ids("kahve makinesi"), ["switch.kahve"])
        self.assertEqual(self.ids("klima"), ["climate.salon_klima"])
        self.assertEqual(self.ids("perdeyi"), ["cover.salon_perde"])

    def test_all_lights(self):
        self.assertEqual(sorted(self.ids("bütün ışıklar")), ["light.mutfak", "light.salon", "light.yatak_odasi"])

    def test_unknown(self):
        self.assertEqual(self.ids("garaj kapısı motoru xyz"), [])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.p = [mock.patch.object(sh, "_states", lambda cfg=None: STATES),
                  mock.patch.object(sh, "_call", lambda d, s, data, cfg=None: self.calls.append((d, s, data)))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_light_on_with_brightness(self):
        out = sh.run({"action": "on", "target": "yatak odası lambası", "brightness": 30})
        self.assertEqual(self.calls, [("light", "turn_on", {"entity_id": "light.yatak_odasi", "brightness_pct": 30})])
        self.assertIn("Yatak Odası", out)

    def test_climate_temperature(self):
        sh.run({"action": "set", "target": "klima", "temperature": 22})
        self.assertEqual(self.calls[0][:2], ("climate", "set_temperature"))
        self.assertEqual(self.calls[0][2]["temperature"], 22.0)

    def test_scene(self):
        self.assertIn("Film Gecesi", sh.run({"action": "scene", "target": "film"}))
        self.assertEqual(self.calls, [("scene", "turn_on", {"entity_id": "scene.film"})])

    def test_state_reads_sensors(self):
        out = sh.run({"action": "state", "target": "salon sıcaklık"})
        self.assertIn("23.5 °C", out)
        out = sh.run({"action": "state", "target": "kapı"})
        self.assertIn("locked", out)

    def test_all_lights_off(self):
        sh.run({"action": "off", "target": "bütün ışıkları"})
        self.assertEqual(len(self.calls), 3)
        self.assertTrue(all(c[1] == "turn_off" for c in self.calls))

    def test_lock_needs_explicit_lock_words(self):
        sh.run({"action": "off", "target": "ön kapı kilidi"})
        self.assertEqual(self.calls, [("lock", "unlock", {"entity_id": "lock.on_kapi"})])

    def test_a_door_is_never_unlocked_by_a_loose_word(self):
        out = sh.run({"action": "off", "target": "ön kapı"})
        self.assertEqual(self.calls, [])
        self.assertIn("Nothing changed", out)
        sh.run({"action": "on", "target": "kapıyı kilitle"})
        self.assertEqual(self.calls, [("lock", "lock", {"entity_id": "lock.on_kapi"})])

    def test_status_lists_lights_on(self):
        out = sh.run({"action": "status"})
        self.assertIn("Salon Işığı", out)
        self.assertIn("Mutfak", out)


class SetupTest(unittest.TestCase):
    def test_not_set_up(self):
        with mock.patch.object(sh, "_cfg", lambda: {}):
            self.assertIn("not connected yet", sh.run({"action": "status"}))

    def test_setup_verifies_before_saving(self):
        saved = {}
        with mock.patch.object(sh, "_request", lambda m, path, body=None, cfg=None:
                               {"message": "API running."} if path == "/api/" else []), \
             mock.patch("memory.config_manager.save_plugin_config", lambda ns, v: saved.update(v)):
            out = sh.run({"action": "setup", "url": "homeassistant.local:8123", "token": "abc"})
        self.assertIn("Connected", out)
        self.assertEqual(saved["url"], "http://homeassistant.local:8123")

    def test_bad_token(self):
        import urllib.error
        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 401, "no", {}, None)
        with mock.patch.object(sh, "_request", boom):
            self.assertIn("401", sh.run({"action": "setup", "url": "http://x", "token": "bad"}))


if __name__ == "__main__":
    unittest.main()


class LeftOnTest(unittest.TestCase):
    def test_lights_left_on(self):
        ids = [e["entity_id"] for e in sh.match("açık kalan ışıkları", STATES)]
        self.assertEqual(sorted(ids), ["light.mutfak", "light.salon"])

    def test_phone_relays_smart_home(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("açık kalan ışıkları kapat", js)


class DiscoverTest(unittest.TestCase):
    def test_setup_without_url_discovers(self):
        saved = {}
        with mock.patch.object(sh, "discover", lambda: "http://homeassistant.local:8123"), \
             mock.patch.object(sh, "_request", lambda m, path, body=None, cfg=None:
                               {"message": "API running."} if path == "/api/" else []), \
             mock.patch("memory.config_manager.save_plugin_config", lambda ns, v: saved.update(v)):
            ok, msg = sh.connect("", "tok")
        self.assertTrue(ok, msg)
        self.assertEqual(saved["url"], "http://homeassistant.local:8123")

    def test_setup_without_url_not_found(self):
        with mock.patch.object(sh, "discover", lambda: None):
            ok, msg = sh.connect("", "tok")
        self.assertFalse(ok)
        self.assertIn("could not find", msg)

    def test_settings_page_has_the_card(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "gui" / "settings_page.py").read_text(encoding="utf-8")
        self.assertIn("Akıllı ev (Home Assistant)", src)
        self.assertIn("_sh.connect(url, token)", src)


class TimerTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(sh, "_timers_path", lambda: Path(self.tmp.name) / "t.json"),
                  mock.patch.object(sh, "_cfg", lambda: {"url": "u", "token": "t"})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_when_from(self):
        from datetime import datetime
        now = datetime(2026, 11, 20, 22, 0).timestamp()
        self.assertEqual(sh.when_from({"after_minutes": 30}, now), now + 1800)
        self.assertEqual(datetime.fromtimestamp(sh.when_from({"at": "23:15"}, now)).strftime("%d %H:%M"), "20 23:15")
        self.assertEqual(datetime.fromtimestamp(sh.when_from({"at": "7"}, now)).strftime("%d %H:%M"), "21 07:00")
        self.assertIsNone(sh.when_from({}, now))

    def test_schedule_and_run_later(self):
        out = sh.run({"action": "off", "target": "bütün ışıklar", "after_minutes": 30})
        self.assertIn("Scheduled", out)
        self.assertIn("off", sh.run({"action": "timers"}))
        import time
        self.assertEqual(sh.run_due_timers(now=time.time() + 60), [])          # not yet
        calls = []
        with mock.patch.object(sh, "_states", lambda cfg=None: STATES), \
             mock.patch.object(sh, "_call", lambda d, s, data, cfg=None: calls.append(s)):
            done = sh.run_due_timers(now=time.time() + 1900)
        self.assertEqual(len(done), 1)
        self.assertEqual(calls, ["turn_off"] * 3)
        self.assertIn("No delayed", sh.run({"action": "timers"}))

    def test_cancel(self):
        sh.run({"action": "on", "target": "salon ışığı", "at": "07:00"})
        self.assertIn("Cancelled 1", sh.run({"action": "cancel_timers"}))


class SummaryAndGraceTest(unittest.TestCase):
    def test_home_summary(self):
        states = STATES + [{"entity_id": "binary_sensor.balkon", "state": "on",
                            "attributes": {"device_class": "door", "friendly_name": "Balkon Kapısı"}}]
        out = sh.home_summary(states)
        self.assertIn("Salon Işığı", out)
        self.assertIn("Balkon Kapısı", out)
        self.assertIn("Salon Klima", out)
        self.assertIn("locked", out)

    def test_missed_timer_is_skipped(self):
        import tempfile, time
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(sh, "_timers_path", lambda: Path(d) / "t.json"):
            sh._save_timers([{"at": time.time() - 3 * 3600, "params": {"action": "off", "target": "salon ışığı"}}])
            out = sh.run_due_timers()
        self.assertIn("Skipped", out[0])

class AmbiguousDeviceTest(unittest.TestCase):
    def setUp(self):
        self.states = [
            {"entity_id": "light.salon_tavan", "state": "off", "attributes": {"friendly_name": "Salon Tavan Işığı"}},
            {"entity_id": "light.salon_masa", "state": "off", "attributes": {"friendly_name": "Salon Masa Işığı"}},
            {"entity_id": "light.mutfak", "state": "off", "attributes": {"friendly_name": "Mutfak Işığı"}},
        ]

    def test_ambiguous_room_does_not_control_arbitrary_light(self):
        with mock.patch.object(sh, "_states", return_value=self.states), mock.patch.object(sh, "_call") as call:
            result = sh.run({"action": "on", "target": "salon ışığı"})
        call.assert_not_called()
        self.assertIn("hangisini", result)
        self.assertIn("Salon Tavan", result)
        self.assertIn("Salon Masa", result)

    def test_explicit_group_controls_matching_room(self):
        with mock.patch.object(sh, "_states", return_value=self.states), mock.patch.object(sh, "_call") as call:
            result = sh.run({"action": "on", "target": "salondaki bütün ışıklar"})
        self.assertEqual(call.call_count, 2)
        self.assertIn("doğrulanmadı", result)

    def test_unknown_room_does_not_match_a_known_room(self):
        with mock.patch.object(sh, "_states", return_value=self.states), mock.patch.object(sh, "_call") as call:
            sh.run({"action": "on", "target": "salon garaj ışığı"})
        call.assert_not_called()
