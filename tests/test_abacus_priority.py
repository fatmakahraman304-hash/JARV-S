import unittest
from unittest.mock import patch

from providers.llm_openai import (
    AbacusPriorityLLM, OpenAICompatLLM, PRESETS, _abacus_rest_seconds, _make,
)
from providers.base import FunctionCall


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

    async def test_rate_limited_backup_is_not_retried_on_every_turn(self):
        healthy = OpenAICompatLLM(dict(base_url=PRESETS["Google Gemini"],
                                      model="healthy-backup", api_key="test-only"))
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            if provider in (self.primary, self.backup):
                raise RuntimeError("429 quota exceeded")
            yield {"text": "answer"}
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", side_effect=lambda: iter([self.backup, healthy])):
            self.assertEqual(await self.collect(), [{"text": "answer"}])
            self.assertEqual(await self.collect(), [{"text": "answer"}])
        self.assertEqual(self.calls, ["route-llm", "test-backup", "healthy-backup", "healthy-backup"])

    async def test_transient_backup_recovers_after_its_cooldown(self):
        healthy = OpenAICompatLLM(dict(base_url=PRESETS["Google Gemini"],
                                      model="healthy-backup", api_key="test-only"))
        recovered = False
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            if provider is self.primary:
                raise RuntimeError("429 quota exceeded")
            if provider is self.backup and not recovered:
                raise RuntimeError("503 temporarily unavailable")
            yield {"text": provider.model}
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", side_effect=lambda: iter([self.backup, healthy])), \
                patch("providers.llm_openai.time") as clock:
            clock.monotonic.return_value = 100.0
            self.assertEqual(await self.collect(), [{"text": "healthy-backup"}])
            clock.monotonic.return_value = 110.0
            self.assertEqual(await self.collect(), [{"text": "healthy-backup"}])
            recovered = True
            clock.monotonic.return_value = 131.0
            self.assertEqual(await self.collect(), [{"text": "test-backup"}])
        self.assertEqual(self.calls, ["route-llm", "test-backup", "healthy-backup",
                                     "healthy-backup", "test-backup"])

    async def test_all_models_resting_reports_failure_without_network_retry(self):
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            raise RuntimeError("429 quota exceeded")
            yield  # async generator matching the provider interface
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", side_effect=lambda: iter([self.backup])):
            with self.assertRaisesRegex(RuntimeError, "429"):
                await self.collect()
            with self.assertRaisesRegex(RuntimeError, "beklemede"):
                await self.collect()
        self.assertEqual(self.calls, ["route-llm", "test-backup"])

    async def test_context_and_tool_declarations_reach_backup_unchanged(self):
        messages = [{"role": "user", "content": "Proje Atlas"},
                    {"role": "assistant", "content": "Hangi adım?"},
                    {"role": "user", "content": "Testleri incele"}]
        tools = [{"type": "function", "function": {"name": "inspect_tests"}}]
        async def chat(provider, given, offered, **kwargs):
            self.assertIs(given, messages)
            self.assertIs(offered, tools)
            self.assertEqual(kwargs, {"stream": True, "temperature": .2})
            if provider is self.primary:
                raise RuntimeError("503")
            yield {"text": "backup"}
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", return_value=iter([self.backup])):
            result = [event async for event in self.primary.chat(messages, tools, temperature=.2)]
        self.assertEqual(result, [{"text": "backup"}])
        self.assertEqual(messages[-1]["content"], "Testleri incele")

    async def test_partial_tool_call_from_backup_cannot_be_replayed(self):
        third = OpenAICompatLLM(dict(base_url=PRESETS["Google Gemini"],
                                    model="third", api_key="test-only"))
        call = FunctionCall(id="once", name="open_app", args={"name": "test"})
        async def chat(provider, *args, **kwargs):
            self.calls.append(provider.model)
            if provider is self.primary:
                raise RuntimeError("429")
            yield {"tool_calls": [call]}
            raise RuntimeError("503")
        with patch.object(OpenAICompatLLM, "chat", chat), patch.object(
                self.primary, "_fallbacks", return_value=iter([self.backup, third])):
            with self.assertRaisesRegex(RuntimeError, "503"):
                await self.collect()
        self.assertEqual(self.calls, ["route-llm", "test-backup"])
