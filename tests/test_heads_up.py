"""A heads-up a quarter of an hour before an appointment-like reminder."""
import unittest

from core import heads_up as hu

NOW = 1_800_000_000.0


def rem(rid, text, minutes):
    return {"id": rid, "text": text, "due": (NOW + minutes * 60) * 1000}


class HeadsUpTest(unittest.TestCase):
    def test_appointment_words(self):
        self.assertTrue(hu.looks_like_appointment("Doktor randevusu"))
        self.assertTrue(hu.looks_like_appointment("Ekiple toplantı"))
        self.assertTrue(hu.looks_like_appointment("İstanbul uçuşu"))
        self.assertFalse(hu.looks_like_appointment("ilaç iç"))
        self.assertFalse(hu.looks_like_appointment("çamaşırları as"))

    def test_window(self):
        rs = [rem("a", "toplantı", 14), rem("b", "toplantı", 30), rem("c", "ilaç", 14), rem("d", "randevu", 5)]
        self.assertEqual([r["id"] for r in hu.due_soon(rs, set(), now=NOW)], ["a"])
        self.assertEqual(hu.due_soon(rs, {"a"}, now=NOW), [])        # once

    def test_instruction(self):
        text = hu.instruction(rem("a", "Ekip toplantısı", 15), now=NOW)
        self.assertTrue(text.startswith("[HEADS_UP] In 15 minutes: Ekip toplantısı"))


if __name__ == "__main__":
    unittest.main()


class RoutingTest(unittest.TestCase):
    def test_passes_quiet_and_reaches_the_phone(self):
        from unittest import mock
        from core import away, quiet
        with mock.patch.object(quiet, "is_on", lambda now=None: True):
            self.assertFalse(quiet.holds("heads_up"))
        t, b = away.phone_note(hu.instruction(rem("a", "Doktor randevusu", 15), now=NOW), "heads_up")
        self.assertEqual(t, "FRIDAY — yaklaşan")
        self.assertEqual(b, "Doktor randevusu — 15 dakika sonra.")
        with mock.patch.object(away, "push_enabled", lambda: True):
            away._last_push["at"] = float("-inf")
            self.assertTrue(away.should_push("heads_up", 3600, now=10))


class LocalTest(unittest.TestCase):
    def test_routines_and_merge(self):
        routines = [{"id": "x1", "kind": "say", "text": "Toplantı", "enabled": True, "next_ts": NOW + 840,
                     "trigger": {"type": "time", "rule": {"type": "once", "at_ts": NOW + 840}}},
                    {"id": "x2", "kind": "builtin", "enabled": True, "trigger": {"type": "startup"}}]
        local = hu.from_routines(routines)
        self.assertEqual([r["id"] for r in local], ["rt:x1"])
        shared = [{"id": "s1", "text": "toplantı", "due": (NOW + 840) * 1000}]
        merged = hu.merge(shared, local)
        self.assertEqual([r["id"] for r in merged], ["s1"])          # the same appointment once
        self.assertEqual([r["id"] for r in hu.due_soon(hu.merge([], local), set(), now=NOW)], ["rt:x1"])
