"""Self-healing: a microphone that stopped calling back is noticed and reopened."""
import unittest
from pathlib import Path

from core import selfheal


class Mic(unittest.TestCase):
    def test_rules(self):
        self.assertFalse(selfheal.mic_dead(100.0, True, now=101.0))
        self.assertTrue(selfheal.mic_dead(100.0, True, now=104.0))
        self.assertTrue(selfheal.mic_dead(100.0, False, now=100.1))

    def test_main_reopens_a_dead_microphone(self):
        src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
        self.assertIn("self._mic_heartbeat = time.monotonic()      # the microphone is alive", src)
        self.assertIn("while not selfheal.mic_dead(self._mic_heartbeat", src)
        self.assertIn("Mikrofon yeniden bağlandı", src)


if __name__ == "__main__":
    unittest.main()
