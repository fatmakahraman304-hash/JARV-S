"""Only the decision on the matching HUD banner may dispatch a message."""
import threading
import unittest
from unittest.mock import Mock, patch

from actions import send_message as sm
from core import confirm


class Confirm(unittest.TestCase):
    def setUp(self):
        self.show = Mock()
        self.sent = threading.Event()
        self.send = Mock(side_effect=lambda *_: self.sent.set() or "unverified")
        for target, field, value in [(confirm, "_pending", None), (confirm, "_show_cb", self.show),
                                     (sm, "_PYAUTOGUI", True), (sm, "_send_and_report", self.send)]:
            self.enterContext(patch.object(target, field, value))

    def call(self, **extra):
        return sm.send_message(dict(receiver="Annem", message_text="Akşam geliyorum",
                                    platform="WhatsApp") | extra)

    def test_model_flags_and_repeat_cannot_authorize_or_change_settings(self):
        with patch("memory.config_manager.save_plugin_config") as save:
            self.call(always_send_without_asking=True)
            self.call(confirmed=True)
            save.assert_not_called()
        self.show.assert_called_once()
        self.send.assert_not_called()

    def test_matching_decision_dispatches_exactly_once(self):
        self.call()
        _, detail, token = self.show.call_args.args
        self.assertIn("Akşam geliyorum", detail)
        self.call(message_text="Değişti")
        confirm.resolve(True, "obsolete")
        self.send.assert_not_called()
        confirm.resolve(True, token)
        self.assertTrue(self.sent.wait(2))
        confirm.resolve(True, token)
        self.send.assert_called_once_with(None, "WhatsApp", "Annem", "Akşam geliyorum")

    def test_cancel(self):
        self.call()
        confirm.resolve(False, self.show.call_args.args[-1])
        self.send.assert_not_called()

    def test_headless_and_expired_banner(self):
        with patch.object(confirm, "_show_cb", None):
            self.call()
        self.assertIsNone(confirm._pending)
        self.call()
        old = self.show.call_args.args[-1]
        confirm._pending.at -= confirm.TIMEOUT_SECONDS + 1
        self.call(message_text="Yeni")
        confirm.resolve(True, old)
        self.send.assert_not_called()
