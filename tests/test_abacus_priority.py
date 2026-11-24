import unittest
from unittest.mock import patch

from providers.llm_openai import (
    AbacusPriorityLLM, OpenAICompatLLM, PRESETS, _abacus_rest_seconds, _make,
)


class AbacusPriorityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.primary = _make(dict(base_url=PRESETS["Abacus AI"],
                                  model="route-llm", api_key="test-only"))
        self.backup = OpenAICompatLLM(dict(base_url=PRESETS["Google Gemini"],
                                         model="test-backup", api_key="test-only"))
        self.calls = []

    async def collect(self):
        return [e async for e in self.primary.chat([{"role": "user", "content": "hi"}])]

    async def test_healthy_abacus_first(self):
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            yield {"text": "primary"}
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", return_value=iter([self.backup])):
            self.assertEqual(await self.collect(), [{"text": "primary"}])
        self.assertEqual(self.calls, ["route-llm"])

    async def test_quota_skips_primary_on_next_turn(self):
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            if provider is self.primary:
                raise RuntimeError("429 quota exceeded")
            yield {"text": "backup"}
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", side_effect=lambda: iter([self.backup])):
            self.assertEqual(await self.collect(), [{"text": "backup"}])
            self.assertEqual(await self.collect(), [{"text": "backup"}])
        self.assertEqual(self.calls, ["route-llm", "test-backup", "test-backup"])

    async def test_partial_response_not_replayed(self):
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            yield {"text": "partial"}
            raise RuntimeError("503")
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", return_value=iter([self.backup])):
            with self.assertRaisesRegex(RuntimeError, "503"):
                await self.collect()
        self.assertEqual(self.calls, ["route-llm"])

    def test_credit_and_rate_limit_cooldown(self):
        self.assertIsInstance(self.primary, AbacusPriorityLLM)
        self.assertEqual(_abacus_rest_seconds(RuntimeError("402 credits")), 900)
        self.assertEqual(_abacus_rest_seconds(RuntimeError("429")), 900)
        self.assertEqual(_abacus_rest_seconds(RuntimeError("503")), 30)
