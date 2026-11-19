"""Commands given while a Blender job runs are queued and done in order; 'dur' clears the line."""
import threading
import time
import unittest
from unittest.mock import patch

from plugins import blender_studio as studio
from plugins import job_control


class Queue(unittest.TestCase):
    def setUp(self):
        studio._queue.clear()

    def _fake(self, done, gate):
        def process(action, request, project, topic="", **kw):
            if request == "masa yap":
                gate.wait(5)
            done.append(request)
            return f"{request}: hazır"
        return process

    def test_commands_run_in_the_order_they_were_said(self):
        done, gate = [], threading.Event()
        with patch.object(studio, "process", side_effect=self._fake(done, gate)), \
             patch.object(studio, "executable", return_value="blender"):
            studio.run({"action": "new", "request": "masa yap"})
            time.sleep(0.2)
            out = studio.run({"action": "edit", "request": "rengini koyu yap"})
            studio.run({"action": "edit", "request": "ayakları kalınlaştır"})
            self.assertIn("sıraya aldım (1. sırada)", out)
            self.assertEqual(studio.queued(), ["rengini koyu yap", "ayakları kalınlaştır"])
            self.assertIn("Sırada (Blender): rengini koyu yap", job_control.run({"action": "list"}))
            gate.set()
            for _ in range(50):
                if len(done) == 3 and not studio._lock.locked():
                    break
                time.sleep(0.1)
        self.assertEqual(done, ["masa yap", "rengini koyu yap", "ayakları kalınlaştır"])

    def test_stop_clears_the_line(self):
        done, gate = [], threading.Event()
        with patch.object(studio, "process", side_effect=self._fake(done, gate)), \
             patch.object(studio, "executable", return_value="blender"):
            studio.run({"action": "new", "request": "masa yap"})
            time.sleep(0.2)
            studio.run({"action": "edit", "request": "rengini koyu yap"})
            out = job_control.run({"action": "cancel", "which": "blender"})
            self.assertIn("sıradaki 1 Blender işi", out)
            gate.set()
            for _ in range(50):
                if not studio._lock.locked():
                    break
                time.sleep(0.1)
            time.sleep(0.3)
        self.assertNotIn("rengini koyu yap", done)
        self.assertEqual(studio.queued(), [])


if __name__ == "__main__":
    unittest.main()
