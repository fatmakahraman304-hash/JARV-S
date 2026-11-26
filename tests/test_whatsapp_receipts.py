import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from actions import send_message
from core import whatsapp_receipts as wa


class ReceiptTests(unittest.TestCase):
    def test_reads_the_automation_id_from_released_pywinauto(self):
        def element(name, kind, key, top, bottom, identity, children=()):
            return SimpleNamespace(
                name=name, control_type=kind, automation_id=key,
                rectangle=SimpleNamespace(top=top, bottom=bottom, left=0, right=700),
                element=SimpleNamespace(GetRuntimeId=lambda: (identity,)),
                children=lambda **kwargs: children,
            )

        pane = element("", "Pane", "ConversationPanel", 0, 700, 1, (
            element("Deniz (Siz)", "Button", "", 25, 50, 2),
            element("Merhaba", "Text", "", 250, 270, 3),
            element("", "Edit", "InputBox", 640, 690, 4),
        ))
        self.assertEqual(wa._read_pane(pane, "Kendim", "Merhaba").messages, {(3,): "visible"})

    def test_reads_a_timestamp_and_receipt_in_one_accessible_label(self):
        nodes = [
            wa.Node("", "Pane", "main", -1, 0, 700),
            wa.Node("Deniz (Siz)", "Button", "", 0, 30, 55),
            wa.Node("Siz: Merhaba 20:24, Teslim edildi", "ListItem", "", 0, 180, 220),
            wa.Node("Mesaj yazın…", "Document", "", 0, 650, 690),
        ]
        self.assertEqual(wa._conversation(nodes, lambda i: (i,), "Kendim", "Merhaba").messages,
                         {(2,): "delivered"})

    def test_matches_only_the_chat_and_deduplicates_accessible_message_text(self):
        nodes = [
            wa.Node("", "Pane", "main", -1, 0, 700),
            wa.Node("Deniz (Siz)", "Button", "", 0, 30, 55),
            wa.Node("Siz: Merhaba!", "ListItem", "", 0, 180, 220),
            wa.Node("Merhaba!", "Text", "", 2, 181, 201),
            wa.Node("Teslim edildi", "Image", "", 2, 201, 220),
            wa.Node("Mesaj yazın", "Edit", "", 0, 650, 690),
            wa.Node("Merhaba!", "Text", "", 5, 650, 690),
        ]
        identity = lambda i: (i,)
        self.assertEqual(wa._conversation(nodes, identity, "Kendim", "Merhaba!").messages,
                         {(3,): "delivered"})
        self.assertFalse(wa._conversation(nodes, identity, "Başka kişi", "Merhaba!").matches_recipient)
        nodes[4].name = ""
        self.assertEqual(wa._conversation(nodes, identity, "Kendim", "Merhaba!").messages,
                         {(3,): "visible"})

    def test_old_matching_message_does_not_confirm_a_new_send(self):
        before = wa.Conversation(True, {(1,): "read"})
        with patch.object(wa, "foreground_window", return_value=10), patch.object(
            wa, "read_conversation", return_value=wa.Conversation(True, {(2,): "read"})
        ), patch.object(wa.time, "monotonic", side_effect=[0, 0, 10]), patch.object(wa.time, "sleep"):
            self.assertEqual(wa.wait_for_receipt(10, "Deniz", "Merhaba", before), "")

    def test_tracks_a_new_outgoing_message_from_pending_to_delivered(self):
        before = wa.Conversation(True, {(1,): "sent"})
        states = [wa.Conversation(True, {(1,): "sent", (2,): status})
                  for status in ("pending", "sent", "delivered")]
        with patch.object(wa, "foreground_window", return_value=10), patch.object(
            wa, "read_conversation", side_effect=states
        ), patch.object(wa.time, "sleep"):
            self.assertEqual(wa.wait_for_receipt(10, "Deniz", "Merhaba", before), "delivered")

    def test_status_from_another_conversation_is_ignored(self):
        before = wa.Conversation(True, {})
        with patch.object(wa, "foreground_window", return_value=10), patch.object(
            wa, "read_conversation", return_value=wa.Conversation(False, {(1,): "delivered"})
        ), patch.object(wa.time, "monotonic", side_effect=[0, 0, 10]), patch.object(wa.time, "sleep"):
            self.assertEqual(wa.wait_for_receipt(10, "Deniz", "Merhaba", before), "")

    def test_success_is_reported_and_a_readback_failure_does_not_retry(self):
        player = Mock()
        gui = Mock()
        with patch.object(send_message.sys, "platform", "win32"), patch.object(
            send_message, "_open_app", return_value=True
        ), patch.object(send_message, "_search_in_app"), patch.object(send_message, "_paste_text") as paste, patch.object(
            send_message, "pyautogui", new=gui
        ), patch.object(wa, "foreground_window", return_value=10), patch.object(
            wa, "read_conversation", return_value=wa.Conversation(True, {})
        ), patch.object(wa, "wait_for_receipt", side_effect=["delivered", RuntimeError("unreadable")]), patch.object(
            send_message.time, "sleep"
        ):
            send_message._send_and_report(player, "whatsapp", "Deniz", "Merhaba")
            self.assertIn("Teslim edildi", player.write_log.call_args.args[0])
            self.assertIn("receipt=delivered", player.request_say.call_args.args[0])
            paste.assert_called_once_with("Merhaba")
            self.assertEqual(gui.press.call_count, 2)  # open chat, then send
            gui.reset_mock()
            paste.reset_mock()
            send_message._send_and_report(player, "whatsapp", "Deniz", "Bir daha")
            self.assertIn("doğrulanamadı", player.write_log.call_args.args[0])
            paste.assert_called_once_with("Bir daha")
            self.assertEqual(gui.press.call_count, 2)
