import unittest
from unittest.mock import patch

from core import free_models


class FreePoolTests(unittest.TestCase):
    def setUp(self):
        self.block = {"free_multi": True, "creds": {
            "openai_compat@groq": {"api_key": "fake-groq", "model": "paid-example"},
            "openai_compat@cerebras": {"api_key": "fake-cerebras"},
            "openai_compat@openrouter": {"api_key": "fake-router"},
            "openai_compat@ollama": {"model": "qwen3:8b"},
        }}

    def test_opt_in_and_role_order(self):
        self.assertEqual(free_models.specs("fast", {}), [])
        fast = free_models.specs("fast", self.block)
        smart = free_models.specs("smart", self.block)
        self.assertEqual(fast[0][:2], ("groq", "openai/gpt-oss-20b"))
        self.assertEqual(smart[0][:2], ("groq", "openai/gpt-oss-120b"))
        self.assertEqual(smart[-1][:2], ("ollama", "qwen3:8b"))
        self.assertNotIn("paid-example", [s[1] for s in smart])
        self.assertIn(("openrouter", "openrouter/free"), [s[:2] for s in smart])

    def test_no_key_or_changed_endpoint(self):
        self.block["creds"]["openai_compat@groq"]["base_url"] = "https://example.org/v1"
        self.block["creds"]["openai_compat@cerebras"]["api_key"] = ""
        self.assertEqual([s[0] for s in free_models.specs("coding", self.block)],
                         ["openrouter", "ollama"])

    def test_cloudflare_account_endpoint_and_no_cerebras(self):
        cf = {"api_key": "fake-cf", "base_url": "a" * 32}
        self.block["creds"]["openai_compat@cloudflare"] = cf
        smart = free_models.specs("smart", self.block)
        self.assertNotIn("cerebras", [s[0] for s in smart])
        spec = next(s for s in smart if s[0] == "cloudflare")
        self.assertEqual(spec[1], "@cf/openai/gpt-oss-120b")
        self.assertEqual(spec[2], "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32 + "/ai/v1")
        cf["base_url"] = "https://example.org/" + "a" * 32
        self.assertNotIn("cloudflare", [s[0] for s in free_models.specs("smart", self.block)])

    def test_cloudflare_registry_rejects_foreign_url(self):
        from providers import registry
        with self.assertRaisesRegex(ValueError, "Cloudflare"):
            registry.build("openai_compat@cloudflare", {
                "base_url": "https://example.org/v1", "api_key": "fake",
                "model": "@cf/openai/gpt-oss-20b"})

    def test_media_not_routed(self):
        self.assertTrue(free_models.text_only("hello"))
        self.assertTrue(free_models.text_only(["a", "b"]))
        self.assertFalse(free_models.text_only(["a", {"inline_data": {}}]))

    def test_usage_and_copy(self):
        base = free_models.BASES["groq"]
        with patch.object(free_models, "_usage", {}):
            free_models.record_usage(base, "test", {"prompt_tokens": 12, "completion_tokens": 3})
            report = free_models.usage_report()
            self.assertEqual(report["groq:test"], {"requests": 1, "tokens": 15})
            report["groq:test"]["tokens"] = 0
            self.assertEqual(free_models.usage_report()["groq:test"]["tokens"], 15)

    def test_code_agent_uses_pool_without_gemini(self):
        from core import aether_agent
        with patch.object(free_models, "settings", return_value=self.block), \
             patch.object(aether_agent, "_gemini_key", return_value=""), \
             patch.object(aether_agent, "_settings", return_value={}):
            brains = aether_agent.brains()
            self.assertEqual(brains[0].model, "openai/gpt-oss-120b")
            self.assertTrue(aether_agent.available())


if __name__ == "__main__":
    unittest.main()
