"""FRIDAY free-role model profiles: offline and credential-safe.

The tests use only fake API keys; no real model calls or credits.
"""
import unittest
from unittest import mock

from core import coding_router, gemini
from memory import config_manager
from providers.llm_openai import (
    AETHER_FREE_ROLES, PRESETS, OpenAICompatLLM, aether_role_model,
)


def profile(**other):
    return {
        "base_url": PRESETS["Aether API"],
        "api_key": "local-test-key-not-a-secret",
        "model": "gpt-oss-120b-free",
        "aether_auto_models": "1",
        "aether_allow_paid": "",
        **other,
    }


class AetherSmartModelTests(unittest.TestCase):
    def test_free_choices_by_role(self):
        expected = {
            "conversation": "gpt-oss-120b-free",
            "fast": "qwen3.8-35b-a3b-free",
            "research": "qwen3.8-27b-free",
            "coding": "minimax-m3-free",
        }
        self.assertEqual(AETHER_FREE_ROLES, expected)
        for role, model in expected.items():
            with self.subTest(role=role):
                self.assertEqual(aether_role_model(profile(), role), model)
                self.assertTrue(model.endswith("-free"))
                llm = OpenAICompatLLM(profile(aether_role=role))
                self.assertEqual(llm.model, model)
                body = llm._body([], None, False, None)
                self.assertEqual(body["model"], model)

    def test_manual_selection_and_legacy_config_are_preserved(self):
        self.assertEqual(
            aether_role_model(profile(model="gpt-4o",
                                       aether_auto_models=""), "coding"),
            "gpt-4o")
        legacy = profile(model="gpt-4o")
        del legacy["aether_auto_models"]
        self.assertEqual(aether_role_model(legacy, "coding"), "gpt-4o")
        # Existing default GPT OSS automatically gets workload selection.
        legacy_default = profile()
        del legacy_default["aether_auto_models"]
        self.assertEqual(aether_role_model(legacy_default, "coding"),
                         "minimax-m3-free")

    def test_other_api_providers_remain_unchanged(self):
        self.assertEqual(
            aether_role_model(profile(base_url=PRESETS["OpenAI"],
                                       model="gpt-4o"), "coding"),
            "gpt-4o")

    def test_no_paid_auto_switch_even_with_paid_access_enabled(self):
        for role in AETHER_FREE_ROLES:
            llm = OpenAICompatLLM(profile(
                model="gpt-4o", aether_allow_paid="1", aether_role=role))
            self.assertTrue(llm.model.endswith("-free"))

    def test_background_provider_uses_fast_and_research_roles(self):
        class FakeLLM:
            def complete(self, messages, tools=None, **kwargs):
                return "done", []

        built = []
        def build(_pid, cfg):
            built.append(cfg)
            return FakeLLM()

        with mock.patch.object(config_manager, "get_provider_config",
                               return_value=profile()), \
             mock.patch("providers.registry.missing_fields", return_value=[]), \
             mock.patch("providers.registry.build", side_effect=build):
            for tier, coding in ((gemini.FAST, False),
                                 (gemini.SMART, False),
                                 (gemini.SMART, True)):
                reply = gemini._provider_call(
                    gemini.PROVIDER_PREFIX + "openai_compat@aether",
                    "hello", None, 12000, tier=tier, coding=coding)
                self.assertEqual(reply.text, "done")
        self.assertEqual([cfg["aether_role"] for cfg in built],
                         ["fast", "research", "coding"])

    def test_auto_coding_reuses_existing_local_aether_key(self):
        provider = "openai_compat@aether"
        settings = {"sidecar": provider, "coding": "",
                    "creds": {provider: profile()}}
        with mock.patch.object(config_manager, "get_providers",
                               return_value=settings):
            self.assertEqual(config_manager.get_coding_provider(), provider)
        settings["coding"] = "openai_compat@nvidia"
        with mock.patch.object(config_manager, "get_providers",
                               return_value=settings):
            self.assertEqual(config_manager.get_coding_provider(),
                             "openai_compat@nvidia")
        settings["coding"] = ""
        settings["creds"][provider]["aether_auto_models"] = ""
        with mock.patch.object(config_manager, "get_providers",
                               return_value=settings):
            self.assertEqual(config_manager.get_coding_provider(), "")
        settings["sidecar"] = ""
        with mock.patch.object(config_manager, "get_providers",
                               return_value=settings):
            self.assertEqual(config_manager.get_coding_provider(), "")
        settings["creds"][provider]["aether_auto_models"] = "1"
        settings["pipeline"] = {"llm": provider}
        with mock.patch.object(config_manager, "get_providers",
                               return_value=settings):
            self.assertEqual(config_manager.get_coding_provider(), provider)

    def test_chosen_aether_coding_precedes_nvidia_with_gemini_fallback(self):
        with mock.patch.object(coding_router, "resting", return_value=0.0):
            self.assertEqual(
                coding_router.ladder("openai_compat@aether", lambda p: True),
                ["openai_compat@aether", "aether_agent", ""])
            self.assertEqual(
                coding_router.ladder("", lambda p: True),
                ["aether_agent", ""])


if __name__ == "__main__":
    unittest.main()
