"""Mayk notices a newer version on GitHub and says what changed; updating uses the safe updater."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import app_updater
from plugins import self_update


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, check=True).stdout.strip()


class Check(unittest.TestCase):
    def test_lists_the_new_changes(self):
        with tempfile.TemporaryDirectory() as d:
            origin, local = Path(d) / "origin", Path(d) / "local"
            origin.mkdir()
            git(origin, "init", "-q", "-b", "main")
            git(origin, "config", "user.email", "t@t"); git(origin, "config", "user.name", "t")
            (origin / "a.txt").write_text("1"); git(origin, "add", "."); git(origin, "commit", "-qm", "ilk")
            git(Path(d), "clone", "-q", str(origin), str(local))
            (origin / "a.txt").write_text("2"); git(origin, "commit", "-qam", "Blender: masa daha gerçekçi")
            (origin / "a.txt").write_text("3"); git(origin, "commit", "-qam", "Hafıza asla kaybolmuyor")
            real = app_updater._git

            def fake(root, *args):
                if args[:1] == ("fetch",):
                    args = ("fetch", "--no-tags", str(origin), args[-1])
                return real(root, *args)
            with patch.object(app_updater, "_git", side_effect=fake):
                info = app_updater.check(local)
            self.assertTrue(info["newer"])
            self.assertEqual(info["changes"], ["Hafıza asla kaybolmuyor", "Blender: masa daha gerçekçi"])
            text = self_update.summary(info)
            self.assertIn("2 değişiklik", text)
            self.assertIn("Hafıza asla kaybolmuyor", text)
            git(local, "config", "user.email", "t@t")
            git(local, "config", "user.name", "t")
            git(local, "commit", "--allow-empty", "-qm", "local")
            with patch.object(app_updater, "_git", side_effect=fake):
                diverged = app_updater.check(local)
                self.assertFalse(diverged["newer"])
                self.assertIn("ayrı ayrı", self_update.summary(diverged))
                git(origin, "reset", "--hard", "HEAD~2")
                ahead = app_updater.check(local)
                self.assertFalse(ahead["newer"])
                self.assertIn("ilerisinde", self_update.summary(ahead))

    def test_up_to_date(self):
        self.assertIn("güncel", self_update.summary({"newer": False, "current": "a" * 40}))

    def test_update_uses_the_window_updater(self):
        calls = []
        player = type("P", (), {"start_update": lambda self: calls.append(1)})()
        self.assertIn("yedek", self_update.run({"action": "update"}, player))
        self.assertEqual(calls, [1])

    def test_main_watches_for_updates(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("tg.create_task(self._guarded(self._watch_updates))", src)
        self.assertIn('"[UPDATE_AVAILABLE] "', src)


if __name__ == "__main__":
    unittest.main()
