"""A message is read back and sent only after the user says yes to that exact message."""
import unittest
from unittest.mock import patch

from actions import send_message as sm


class Confirm(unittest.TestCase):
    def setUp(self):
        sm._pending.clear()
        self.cfg = patch.object(sm, "_send_without_asking", return_value=False)
        self.cfg.start()
        self.started = patch.object(sm.threading, "Thread")
        self.thread = self.started.start()
        self.pyauto = patch.object(sm, "_PYAUTOGUI", True)
        self.pyauto.start()

    def tearDown(self):
        self.cfg.stop()
        self.started.stop()
        self.pyauto.stop()

    def call(self, **kw):
        p = {"receiver": "Annem", "message_text": "Akşam geliyorum", "platform": "WhatsApp", **kw}
        return sm.send_message(p)

    def test_first_call_reads_back_and_does_not_send(self):
        out = self.call(confirmed=True)                  # the model cannot confirm on its own first call
        self.assertIn("status=ask", out)
        self.assertIn("«Akşam geliyorum»", out)
        self.thread.assert_not_called()

    def test_yes_sends_that_exact_message(self):
        self.call()
        self.assertIn("status=started", self.call(confirmed=True))
        self.thread.assert_called_once()

    def test_a_changed_message_is_read_back_again(self):
        self.call()
        out = self.call(message_text="Akşam geç geliyorum", confirmed=True)
        self.assertIn("status=ask", out)
        self.thread.assert_not_called()

    def test_user_can_turn_it_off(self):
        with patch.object(sm, "_send_without_asking", return_value=True):
            self.assertIn("status=started", self.call())


if __name__ == "__main__":
    unittest.main()
