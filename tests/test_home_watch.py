"""The house, watched: door changes said once, alarms flagged."""
import unittest
from unittest import mock

from core import home_watch as hw


def bs(eid, cls, state, name=None):
    return {"entity_id": f"binary_sensor.{eid}", "state": state,
            "attributes": {"device_class": cls, "friendly_name": name or eid}}


CFG = {"doors": True, "alarms": True}


class HomeWatchTest(unittest.TestCase):
    def test_first_look_only_learns(self):
        w = hw.HomeWatch()
        self.assertEqual(w.tick([bs("on_kapi", "door", "on", "Ön Kapı")], CFG), [])

    def test_door_opened_and_closed(self):
        w = hw.HomeWatch()
        w.tick([bs("on_kapi", "door", "off", "Ön Kapı")], CFG)
        self.assertEqual(w.tick([bs("on_kapi", "door", "on", "Ön Kapı")], CFG), [("info", "Ön Kapı was opened.")])
        self.assertEqual(w.tick([bs("on_kapi", "door", "on", "Ön Kapı")], CFG), [])          # said once
        self.assertEqual(w.tick([bs("on_kapi", "door", "off", "Ön Kapı")], CFG), [("info", "Ön Kapı was closed.")])

    def test_leak_is_an_alarm(self):
        w = hw.HomeWatch()
        w.tick([bs("mutfak_su", "moisture", "off", "Mutfak Su Sensörü")], CFG)
        notes = w.tick([bs("mutfak_su", "moisture", "on", "Mutfak Su Sensörü")], CFG)
        self.assertEqual(notes[0][0], "alarm")
        self.assertIn("water leak", notes[0][1])
        self.assertTrue(hw.instruction(notes).startswith("[HOME_ALARM]"))

    def test_unavailable_is_not_an_event(self):
        w = hw.HomeWatch()
        w.tick([bs("pencere", "window", "off")], CFG)
        self.assertEqual(w.tick([bs("pencere", "window", "unavailable")], CFG), [])
        self.assertEqual(w.tick([bs("pencere", "window", "on")], CFG), [])     # back online, not "opened"

    def test_switches(self):
        w = hw.HomeWatch()
        w.tick([bs("k", "door", "off")], CFG)
        self.assertEqual(w.tick([bs("k", "door", "on")], {"doors": False, "alarms": True}), [])

    def test_ignores_other_sensors(self):
        self.assertEqual(hw.watched([bs("hareket", "motion", "on"),
                                     {"entity_id": "light.x", "state": "on", "attributes": {}}]), {})

    def test_plugin(self):
        from plugins import home_alerts
        saved = {}
        with mock.patch("memory.config_manager.save_plugin_config",
                        lambda ns, v: saved.setdefault(ns, {}).update(v)), \
             mock.patch("memory.config_manager.get_plugin_config", lambda ns: saved.get(ns, {})):
            out = home_alerts.run({"action": "off", "kind": "alarms"})
            self.assertIn("will NOT be announced", out)
            self.assertFalse(hw.settings()["alarms"])
            self.assertTrue(hw.settings()["doors"])


if __name__ == "__main__":
    unittest.main()


class PresenceTest(unittest.TestCase):
    def person(self, state):
        return {"entity_id": "person.murat", "state": state, "attributes": {"friendly_name": "Deniz"}}

    def test_arrive_and_leave(self):
        w = hw.HomeWatch()
        cfg = {"doors": True, "alarms": True, "presence": True}
        w.tick([self.person("not_home")], cfg)
        notes = w.tick([self.person("home")], cfg)
        self.assertEqual(notes, [("arrive", "Deniz arrived home.")])
        self.assertTrue(hw.instruction(notes).startswith("[WELCOME_HOME]"))
        self.assertEqual(w.tick([self.person("Work")], cfg), [("leave", "Deniz left home.")])
        self.assertEqual(w.tick([self.person("not_home")], cfg), [])       # work → elsewhere: not leaving home

    def test_lights_left_on(self):
        states = [{"entity_id": "light.salon", "state": "on", "attributes": {"friendly_name": "Salon"}},
                  {"entity_id": "light.mutfak", "state": "off", "attributes": {"friendly_name": "Mutfak"}}]
        self.assertEqual(hw.lights_left_on(states), ["Salon"])
        title, body = hw.leaving_note(["Deniz"], ["Salon"])
        self.assertIn("evden çıktınız", title)
        self.assertIn("Salon", body)
        self.assertIsNone(hw.leaving_note(["Deniz"], []))


class RainTest(unittest.TestCase):
    def test_rain_in(self):
        from core import open_data
        js = {"hourly": {"time": ["2026-11-20T08:00", "2026-11-20T09:00", "2026-11-20T10:00", "2026-11-20T15:00"],
                         "precipitation_probability": [10, 20, 70, 90]}}
        self.assertEqual(open_data.rain_in(js, 3, 50, now_iso="2026-11-20T08:00"), {"prob": 70, "at": "10:00"})
        self.assertIsNone(open_data.rain_in(js, 2, 50, now_iso="2026-11-20T08:00"))

    def test_leaving_note_with_rain_only(self):
        title, body = hw.leaving_note(["Deniz"], [], {"prob": 70, "at": "10:00"})
        self.assertIn("şemsiye", body)
        self.assertNotIn("ışıklar", body)
