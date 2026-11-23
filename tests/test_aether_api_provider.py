"""Offline regressions for Aether API model discovery and spend protection.

All calls are mocked: tests must never use a real API key or bill credits.
"""
import asyncio
import unittest
from unittest.mock import MagicMock, Mock, patch

from providers.llm_openai import (
    CATALOG, PRESETS, OpenAICompatLLM, _aether_is_free_model,
)


class AetherAPIProviderTests(unittest.TestCase):
    def make_provider(self, model="gpt-oss-120b-free", paid=False, url=None):
        return OpenAICompatLLM({
            "base_url": url or PRESETS["Aether API"],
            "model": model,
            "api_key": "test-only-placeholder",
            "aether_allow_paid": "1" if paid else "",
        })

    def test_catalog_uses_official_endpoint_and_free_default(self):
        self.assertEqual(PRESETS["Aether API"], "https://api.aetherapi.dev/v1")
        entry = next(row for row in CATALOG if row["id"] == "aether")
        self.assertEqual(entry["values"]["model"], "gpt-oss-120b-free")
        self.assertEqual(entry["values"]["aether_allow_paid"], "")

    def test_only_explicitly_labeled_free_models_are_free(self):
        self.assertTrue(_aether_is_free_model("gpt-oss-120b-free"))
        self.assertTrue(_aether_is_free_model("some-org/model-free"))
        self.assertFalse(_aether_is_free_model("gpt-4o"))
        self.assertFalse(_aether_is_free_model("gpt-oss-120b"))
        self.assertFalse(_aether_is_free_model(""))
        self.assertFalse(_aether_is_free_model("free-in-the-middle-paid"))

    def test_paid_and_unknown_models_blocked_before_network(self):
        llm = self.make_provider(model="claude-opus-4-7")
        with self.assertRaisesRegex(ValueError, "engellendi"):
            llm._body([{"role": "user", "content": "hi"}], None, False, None)

    def test_free_model_can_build_request_without_network(self):
        llm = self.make_provider()
        body = llm._body([{"role": "user", "content": "hi"}], None, False, None)
        self.assertEqual(body["model"], "gpt-oss-120b-free")

    def test_paid_model_requires_explicit_opt_in(self):
        llm = self.make_provider(model="gpt-4o", paid=True)
        body = llm._body([], None, False, None)
        self.assertEqual(body["model"], "gpt-4o")

    def test_string_false_does_not_enable_paid_requests(self):
        llm = OpenAICompatLLM({
            "base_url": PRESETS["Aether API"],
            "model": "gpt-4o",
            "aether_allow_paid": "false",
        })
        with self.assertRaises(ValueError):
            llm._body([], None, False, None)

    def test_blocked_even_when_request_is_streamed(self):
        llm = self.make_provider(model="gpt-4o")

        async def collect():
            return [chunk async for chunk in llm.chat([], stream=True)]

        with self.assertRaises(ValueError):
            asyncio.run(collect())

    def test_non_aether_providers_not_restricted(self):
        llm = self.make_provider(model="gpt-4o", url=PRESETS["OpenAI"])
        self.assertEqual(llm._body([], None, False, None)["model"], "gpt-4o")

    def test_model_list_filters_paid_nonchat_and_denied(self):
        rows = [
            {"id": "gpt-oss-120b-free",
             "supported_endpoints": ["/v1/chat/completions"]},
            {"id": "qwen3.8-27b-free",
             "supported_endpoints": ["/v1/chat/completions"],
             "capabilities": {"/v1/chat/completions": {
                 "access": {"allowed": True}}}},
            {"id": "paid-model", "supported_endpoints": ["/v1/chat/completions"]},
            {"id": "image-model-free",
             "supported_endpoints": ["/v1/images/generations"]},
            {"id": "denied-model-free",
             "supported_endpoints": ["/v1/chat/completions"],
             "capabilities": {"/v1/chat/completions": {
                 "access": {"allowed": False, "reason": "model_not_allowed"}}}},
        ]
        response = Mock()
        response.json.return_value = {"data": rows}
        response.raise_for_status.return_value = None
        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.get.return_value = response
        with patch("httpx.Client", return_value=fake_client):
            self.assertEqual(
                self.make_provider().models(),
                ["gpt-oss-120b-free", "qwen3.8-27b-free"],
            )
            self.assertEqual(
                self.make_provider(paid=True).models(),
                ["gpt-oss-120b-free", "qwen3.8-27b-free", "paid-model"],
            )


if __name__ == "__main__":
    unittest.main()
