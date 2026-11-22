"""AETHER: kaldırılan DeepSeek'in yeniden etkinleşmemesi ve anahtar temizliği."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import coding_router, aether_agent, nvidia_account
from memory import config_manager as cfg


class RemovedDeepSeekTests(unittest.TestCase):
    def _old(self):
        return {
            "gemini_api_key": "gemini-secret",
            "deepseek_api_key": "removed-root-secret",
            "plugin_config": {
                "coding": {
                    "deepseek_key": "removed-code-key",
                    "deepseek_models": ["old-model"],
                    "nvidia_models": ["nvidia/nemotron-3.5-lightning-30b-a3b"],
                },
                "other": {"setting": "retained"},
            },
            "providers": {
                "mode": "pipeline",
                "pipeline": {
                    "llm": "openai_compat@deepseek",
                    "stt": "stt_whisper@local",
                },
                "sidecar": "openai_compat@deepseek",
                "coding": "openai_compat@deepseek",
                "creds": {
                    "openai_compat@deepseek": {
                        "api_key": "removed-provider-secret",
                        "base_url": "https://api.deepseek.com/v1",
                    },
                    "openai_compat@nvidia": {
                        "api_key": "kept-nvidia-secret",
                        "base_url": "https://integrate.api.nvidia.com/v1",
                    },
                },
            },
        }

    def test_in_memory_config_blocks_old_selection(self):
        old = self._old()
        with mock.patch.object(cfg, "load_api_keys", return_value=old):
            self.assertEqual(cfg.get_coding_provider(), "")
            self.assertEqual(cfg.get_sidecar_provider(), "")
            self.assertEqual(cfg.get_provider_mode(), cfg.PROVIDER_MODE_GEMINI)
            self.assertEqual(cfg.get_pipeline()["llm"], "")
            self.assertEqual(cfg.get_provider_config("openai_compat@deepseek"), {})
            self.assertEqual(cfg.get_provider_config("openai_compat@nvidia")["api_key"],
                             "kept-nvidia-secret")
            self.assertNotIn("deepseek_key", cfg.get_plugin_config("coding"))
            self.assertEqual(cfg.get_plugin_config("coding")["nvidia_models"],
                             ["nvidia/nemotron-3.5-lightning-30b-a3b"])
        self.assertEqual(old["providers"]["coding"], "openai_compat@deepseek")

    def test_migration_clears_only_removed_data(self):
        old = self._old()
        clean = cfg._purged_deepseek_data(old)
        self.assertNotIn("deepseek_api_key", clean)
        self.assertNotIn("deepseek_key", clean["plugin_config"]["coding"])
        self.assertNotIn("deepseek_models", clean["plugin_config"]["coding"])
        self.assertNotIn("openai_compat@deepseek", clean["providers"]["creds"])
        self.assertEqual(clean["providers"]["coding"], "")
        self.assertEqual(clean["providers"]["sidecar"], "")
        self.assertEqual(clean["providers"]["mode"], "gemini")
        self.assertEqual(clean["providers"]["pipeline"]["stt"], "stt_whisper@local")
        self.assertEqual(clean["providers"]["creds"]["openai_compat@nvidia"]["api_key"],
                         "kept-nvidia-secret")
        self.assertEqual(clean["plugin_config"]["other"], {"setting": "retained"})
        self.assertEqual(clean["gemini_api_key"], "gemini-secret")

    def test_purge_scrubs_active_settings_and_last_backup(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "api_keys.json"
            path.write_text(json.dumps(self._old()), encoding="utf-8")
            with mock.patch.object(cfg, "CONFIG_FILE", path), \
                 mock.patch.object(cfg, "ensure_config_dir", return_value=None):
                self.assertTrue(cfg.purge_deepseek_settings())
                self.assertFalse(cfg.purge_deepseek_settings())
                backup = Path(str(path) + ".bak")
                self.assertTrue(backup.exists())
                for file in (path, backup):
                    data = json.loads(file.read_text(encoding="utf-8"))
                    text = json.dumps(data).casefold()
                    self.assertNotIn("deepseek", text)
                    self.assertEqual(
                        data["providers"]["creds"]["openai_compat@nvidia"]["api_key"],
                        "kept-nvidia-secret")
                    self.assertEqual(data["gemini_api_key"], "gemini-secret")

    def test_stale_coding_choice_cannot_reenable_removed_provider(self):
        with mock.patch.object(coding_router, "resting", return_value=0):
            self.assertEqual(coding_router.ladder("openai_compat@deepseek",
                                                  lambda _: True),
                             [aether_agent.PROVIDER_ID, coding_router.GEMINI])

    def test_nvidia_and_gemini_are_only_auto_brains(self):
        with mock.patch.object(nvidia_account, "api_key", return_value="nvidia-key"), \
             mock.patch.object(nvidia_account, "available_models",
                               return_value=["nvidia/nemotron-3.5-lightning-30b-a3b"]), \
             mock.patch.object(aether_agent, "_gemini_key", return_value="gemini-key"), \
             mock.patch.object(aether_agent, "_settings", return_value={}), \
             mock.patch.object(aether_agent, "gemini_models",
                               return_value=["gemini-2.5-flash"]), \
             mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "removed-key"}):
            names = [brain.name for brain in aether_agent.brains()]
        self.assertEqual(names, [
            "NVIDIA (nvidia/nemotron-3.5-lightning-30b-a3b)",
            "Gemini (gemini-2.5-flash)",
        ])

    def test_deepseek_removed_from_provider_catalog(self):
        from providers.llm_openai import CATALOG, PRESETS
        ids = {item["id"] for item in CATALOG}
        self.assertNotIn("deepseek", ids)
        self.assertNotIn("DeepSeek", PRESETS)


if __name__ == "__main__":
    unittest.main()
