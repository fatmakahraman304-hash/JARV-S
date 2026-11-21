"""DeepSeek anahtarı, kota kontrolü ve kodlama önceliği regresyonları."""
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from core import deepseek_account, jarvis_agent, coding_router, agent_coding


class DeepSeekSettingsTests(unittest.TestCase):
    def test_key_from_coding_or_provider_config(self):
        with patch("memory.config_manager.get_plugin_config",
                   return_value={"deepseek_key": "private-coding-key"}), \
             patch("memory.config_manager.get_providers", return_value={}), \
             patch("memory.config_manager.load_api_keys", return_value={}):
            self.assertEqual(deepseek_account.api_key(), "private-coding-key")
        with patch("memory.config_manager.get_plugin_config", return_value={}), \
             patch("memory.config_manager.get_providers",
                   return_value={"creds": {"openai_compat@deepseek": {
                       "api_key": "private-provider-key"}}}), \
             patch("memory.config_manager.load_api_keys", return_value={}):
            self.assertEqual(deepseek_account.api_key(), "private-provider-key")
        with patch("memory.config_manager.get_plugin_config", return_value={}), \
             patch("memory.config_manager.get_providers",
                   return_value={"creds": {"openai_compat@openai": {
                       "api_key": "other-provider-key"}}}), \
             patch("memory.config_manager.load_api_keys", return_value={}), \
             patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}):
            self.assertEqual(deepseek_account.api_key(), "")

    def test_model_order_and_old_aliases(self):
        with patch.object(jarvis_agent, "_settings", return_value={}):
            self.assertEqual(jarvis_agent.deepseek_models(),
                             ["deepseek-v4-pro", "deepseek-flash"])
        with patch.object(jarvis_agent, "_settings",
                          return_value={"deepseek_models": ["deepseek-chat", "deepseek-reasoner"]}):
            self.assertEqual(jarvis_agent.deepseek_models(),
                             ["deepseek-flash", "deepseek-v4-pro"])

    def test_balance_is_read_without_leaking_key(self):
        class Dummy:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, *args):
                return json.dumps({"is_available": True, "balance_infos": [
                    {"currency": "USD", "total_balance": "5.25"}]}).encode()
        with patch.object(deepseek_account.urllib.request, "urlopen", return_value=Dummy()) as call:
            status = deepseek_account.balance_status("private123", refresh=True)
        self.assertTrue(status["available"])
        self.assertEqual(status["balances"], [{"currency": "USD", "total": "5.25"}])
        self.assertNotIn("private123", repr(status))
        self.assertEqual(call.call_args.args[0].full_url,
                         "https://api.deepseek.com/user/balance")

    def test_402_is_empty_and_timeout_is_unknown(self):
        err = HTTPError(deepseek_account.BALANCE_URL, 402, "payment required", {}, None)
        with patch.object(deepseek_account.urllib.request, "urlopen", side_effect=err):
            self.assertEqual(deepseek_account.balance_status("private402", refresh=True)["available"], False)
        with patch.object(deepseek_account.urllib.request, "urlopen", side_effect=OSError("offline")):
            status = deepseek_account.balance_status("privateoffline", refresh=True)
        self.assertIsNone(status["available"])
        self.assertNotEqual(status["reason"], "empty")


class CodingRoutesTests(unittest.TestCase):
    def test_cli_agents_not_routed(self):
        self.assertEqual(coding_router.AGENTS, (jarvis_agent.PROVIDER_ID,))
        self.assertEqual(agent_coding.AGENT_PROVIDERS, {jarvis_agent.PROVIDER_ID})
        self.assertFalse(agent_coding.available("claude_code"))
        self.assertFalse(agent_coding.available("codex_cli"))
        with patch.object(coding_router, "resting", return_value=0):
            self.assertEqual(coding_router.ladder("claude_code", lambda p: True),
                             [jarvis_agent.PROVIDER_ID, ""])
            self.assertEqual(coding_router.ladder("codex_cli", lambda p: True),
                             [jarvis_agent.PROVIDER_ID, ""])

    def test_skips_deepseek_on_confirmed_empty_balance(self):
        with patch.object(deepseek_account, "api_key", return_value="k"), \
             patch.object(deepseek_account, "balance_status", return_value={
                 "available": False, "reason": "empty", "balances": []}), \
             patch.object(jarvis_agent, "_gemini_key", return_value="g"), \
             patch.object(jarvis_agent, "gemini_models", return_value=["gemini-pro"]):
            self.assertEqual([b.name for b in jarvis_agent.brains()], ["Gemini (gemini-pro)"])

    def test_no_secret_in_account_message(self):
        with patch.object(deepseek_account, "api_key", return_value="do-not-print"), \
             patch.object(deepseek_account, "balance_status", return_value={
                 "available": True, "reason": "ok", "balances": [
                     {"currency": "USD", "total": "2.15"}]}):
            message = deepseek_account.status_text()
        self.assertIn("2.15 USD", message)
        self.assertNotIn("do-not-print", message)


if __name__ == "__main__":
    unittest.main()
