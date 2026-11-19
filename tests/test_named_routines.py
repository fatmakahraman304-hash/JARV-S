"""Named routines: taught once ('akşam modu: …'), run when the user says the name, never on their own."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.routines.engine import RoutineEngine


class Host:
    def __init__(self):
        self.prompts, self.logs = [], []

    def prompt(self, text):
        self.prompts.append(text)

    def say(self, text):
        self.prompts.append(text)

    def ready(self):
        return True

    def idle_seconds(self):
        return 10_000.0

    def log(self, text):
        self.logs.append(text)


class NamedRoutines(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.host = Host()
        self.eng = RoutineEngine(Path(self.tmp.name) / "r.json", self.host, autostart=False, log=lambda *a: None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_taught_once_run_by_name(self):
        r = self.eng.add(name="Akşam modu", kind="prompt", trigger={"type": "command"},
                         text="ışıkları kıs, sakin müzik aç, yarının takvimini oku")
        self.assertEqual(self.eng.describe(r), "when the user says its name")
        for _ in range(3):
            self.eng.tick()                                   # never fires by itself
        self.assertEqual(self.host.prompts, [])
        for said in ("akşam modu", "Akşam Modunu", "akşam modunu çalıştır"):
            self.assertEqual(self.eng.find_by_name(said)["id"], r["id"], said)
        self.eng.run_now(r["id"])
        self.assertIn("the user asked for it just now", self.host.prompts[0])
        self.assertIn("yarının takvimini oku", self.host.prompts[0])

    def test_tool_adds_and_runs_by_name(self):
        from actions import routines as tool
        from core.routines import desktop
        with patch.object(desktop, "engine", return_value=self.eng):
            tool.routines({"action": "add", "kind": "prompt", "on": "command", "name": "Sabah rutini",
                           "text": "haberleri ve hava durumunu söyle"})
            out = tool.routines({"action": "run_now", "name": "sabah rutinini başlat"})
            missing = tool.routines({"action": "run_now", "name": "gece modu"})
        self.assertIn("ran", out)
        self.assertIn("haberleri", self.host.prompts[-1])
        self.assertIn("no routine called 'gece modu'", missing)


if __name__ == "__main__":
    unittest.main()
