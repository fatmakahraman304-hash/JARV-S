"""JARVIS's self check: every check runs, problems come with a fix, a hung check cannot hold it up."""
import time
import unittest
from unittest.mock import patch

from plugins import self_check as sc


class SelfCheck(unittest.TestCase):
    def test_report_lists_every_check_with_fixes(self):
        fake = {"Yapay zekâ": lambda: (sc.FAIL, "Yapay zekâ anahtarı yok", "Ayarlara anahtar gir."),
                "İnternet": lambda: (sc.OK, "İnternet bağlantısı var", ""), "Ses": lambda: (sc.OK, "Mikrofon: X", "")}
        checks = tuple((label, fake.get(label, fn)) for label, fn in sc.CHECKS)
        with patch.object(sc, "CHECKS", checks):
            out = sc.run({})
        for label in ("Yapay zekâ", "İnternet", "Ses", "Disk", "Hafıza", "Eklentiler", "Blender", "Paketler"):
            self.assertIn(label, out)
        self.assertIn("❌ Yapay zekâ: Yapay zekâ anahtarı yok\n    → Ayarlara anahtar gir.", out)
        self.assertTrue(out.startswith(("1 konuda", "2 konuda", "3 konuda", "4 konuda")))

    def test_a_hung_check_cannot_hold_it_up(self):
        def slow():
            time.sleep(5)
            return sc.OK, "x", ""
        with patch.object(sc, "CHECKS", (("Yavaş", slow), ("Disk", sc.check_disk))):
            t0 = time.time()
            rows = sc.run_checks(timeout=0.5)
        self.assertLess(time.time() - t0, 2)
        self.assertEqual(rows[0][1], sc.WARN)
        self.assertIn("zamanında yanıt vermedi", rows[0][2])

    def test_real_local_checks_run(self):
        for fn in (sc.check_disk, sc.check_memory, sc.check_plugins, sc.check_packages, sc.check_blender):
            mark, text, _fix = fn()
            self.assertIn(mark, (sc.OK, sc.WARN, sc.FAIL))
            self.assertTrue(text)


if __name__ == "__main__":
    unittest.main()
