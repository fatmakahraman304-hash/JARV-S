"""MAYK's self check: every check runs, problems come with a fix, a hung check cannot hold it up."""
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


class Logbook(unittest.TestCase):
    def test_prints_and_crashes_are_kept_and_read_back(self):
        import subprocess, sys, tempfile, textwrap
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as d:
            code = textwrap.dedent(f"""
                import sys, threading
                sys.path.insert(0, {str(root)!r})
                from core import logbook
                logbook.install({d!r})
                print("[MAYK] normal bir satır")
                print("[Blender] Error: bağlantı koptu")
                t = threading.Thread(target=lambda: 1 / 0, name="arka-is"); t.start(); t.join()
                raise RuntimeError("ana iş çöktü")
            """)
            subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=30)
            text = (Path(d) / "jarvis.log").read_text(encoding="utf-8")
            self.assertIn("normal bir satır", text)
            self.assertIn("ÇÖKME (arka-is)", text)
            self.assertIn("ZeroDivisionError", text)
            self.assertIn("RuntimeError: ana iş çöktü", text)
            from core import logbook
            with patch.object(logbook, "_path", Path(d) / "jarvis.log"):
                errs = logbook.recent_errors()
            self.assertTrue(any("bağlantı koptu" in e for e in errs))
            self.assertTrue(any("ÇÖKME" in e for e in errs))

    def test_rotation_keeps_the_size_bounded(self):
        import tempfile
        from pathlib import Path
        from core import logbook
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "jarvis.log"
            with patch.object(logbook, "_path", p), patch.object(logbook, "MAX_BYTES", 2000):
                logbook._file = open(p, "a", encoding="utf-8")
                for i in range(400):
                    logbook.write(f"satır {i} " + "x" * 40)
                logbook._file.close()
                logbook._file = None
            sizes = [f.stat().st_size for f in Path(d).glob("jarvis.log*")]
            self.assertLessEqual(len(sizes), logbook.KEEP + 1)
            self.assertTrue(all(s < 4000 for s in sizes))
