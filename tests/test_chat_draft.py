import unittest
from unittest.mock import Mock

from core.social_sites import chat_draft_command
from gui.chat_composer import composer_script
from plugins import chat_draft


class ChatDraftTests(unittest.TestCase):
    def test_explicit_commands_keep_original_text(self):
        self.assertEqual(chat_draft_command("JARVIS, Claude’a yaz: Merhaba!\nİkinci satır"),
                         ("claude", "Merhaba!\nİkinci satır"))
        self.assertEqual(chat_draft_command("ChatGBT’ye şunu yaz: Merhaba"), ("chatgpt", "Merhaba"))
        self.assertEqual(chat_draft_command("Buraya yaz: Selam"), ("", "Selam"))
        self.assertIsNone(chat_draft_command("Claude’a yazma: Selam"))
        self.assertIsNone(chat_draft_command("ChatGPT nedir?"))

    def test_tool_does_not_forward_to_other_platforms(self):
        player = Mock()
        chat_draft.run({"site": "github", "text": "hello"}, player=player)
        player.write_chat_draft.assert_not_called()
        chat_draft.run({"site": "active", "text": "hello"}, player=player)
        player.write_chat_draft.assert_called_once_with("", "hello")

    def test_script_bounds(self):
        for site, text in (("github", "hello"), ("claude", " "), ("chatgpt", "x" * 8001)):
            with self.assertRaises(ValueError):
                composer_script(site, text)
