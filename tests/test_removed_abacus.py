"""Removed integration cannot be revived by aliases, backups or stale UI saves."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.retired_providers import is_retired_provider
from memory import config_manager as cfg
from providers import llm_openai, registry


class RemovedAbacus(unittest.TestCase):
    def sample(self):
        return {"assistant_name":"FRIDAY", "voice_name":"Aoede", "user_name":"Deniz",
                "gemini_api_key":"synthetic-gemini", "abacus_api_key":"synthetic-removed",
                "plugin_config":{"abacus":{"api_key":"synthetic-removed"}, "other":{"keep":True}},
                "providers":{"mode":"pipeline", "sidecar":"openai_compat@abacus", "coding":"openai_compat@abacus",
                    "pipeline":{"llm":"openai_compat@abacus", "stt":"stt_whisper@local", "tts":"tts_edge"},
                    "creds":{"openai_compat@abacus":{"base_url":"https://routellm.abacus.ai/v1", "api_key":"synthetic-removed", "model":"route-llm"},
                             "openai_compat@nvidia":{"base_url":"https://integrate.api.nvidia.com/v1", "api_key":"synthetic-kept", "model":"kept-model"}}}}

    def test_catalog_and_factory_have_no_removed_provider(self):
        self.assertNotIn("Abacus AI", llm_openai.PRESETS)
        self.assertNotIn("abacus", {row["id"] for row in llm_openai.CATALOG})
        self.assertFalse(hasattr(llm_openai, "AbacusPriorityLLM"))
        from core import gemini
        self.assertFalse(hasattr(gemini, "_abacus_rung"))
        self.assertIs(type(llm_openai._make({"base_url":"http://127.0.0.1:1234/v1", "model":"local"})), llm_openai.OpenAICompatLLM)

    def test_alias_and_custom_endpoint_are_blocked_before_factory_or_cache(self):
        for pid, settings in (("openai_compat@abacus", {}),
                              ("openai_compat@other", {"base_url":"https://ROUTELLM.ABACUS.AI./v1"}),
                              ("openai_compat", {"catalog":"abacus"})):
            with self.subTest(pid=pid), patch.object(registry, "get_declaration") as declaration:
                with self.assertRaises(LookupError):
                    registry.build(pid, settings)
                declaration.assert_not_called()
        with self.assertRaises(ValueError):
            llm_openai.OpenAICompatLLM({"base_url":"https://routellm.abacus.ai/v1"})

    def test_host_detection_does_not_remove_unrelated_endpoints(self):
        self.assertTrue(is_retired_provider(settings={"base_url":"routellm.abacus.ai/v1"}))
        for url in ("https://api.openai.com/v1", "http://127.0.0.1:1234/v1", "https://abacus.ai.example.invalid/v1"):
            self.assertFalse(is_retired_provider(settings={"base_url":url}))

    def test_migration_preserves_identity_audio_and_other_credentials_without_mutation(self):
        original = self.sample(); before = copy.deepcopy(original)
        clean = cfg._purged_abacus_data(original)
        self.assertEqual(original, before)
        self.assertNotIn("abacus", json.dumps(clean).casefold())
        self.assertEqual(clean["providers"]["mode"], "gemini")
        self.assertEqual(clean["providers"]["pipeline"], {"llm":"", "stt":"stt_whisper@local", "tts":"tts_edge"})
        for field in ("assistant_name", "voice_name", "user_name", "gemini_api_key"):
            self.assertEqual(clean[field], before[field])
        self.assertEqual(clean["providers"]["creds"]["openai_compat@nvidia"], before["providers"]["creds"]["openai_compat@nvidia"])
        self.assertEqual(clean["plugin_config"]["other"], {"keep":True})
        self.assertEqual(cfg._purged_abacus_data(clean), clean)

    def test_local_only_never_switches_to_cloud_gemini(self):
        original = self.sample(); original["local_only"] = True
        self.assertEqual(cfg._purged_abacus_data(original)["providers"]["mode"], "pipeline")
        original.pop("local_only"); original.pop("gemini_api_key")
        self.assertEqual(cfg._purged_abacus_data(original)["providers"]["mode"], "pipeline")

    def test_custom_alias_and_legacy_shared_catalog_are_removed(self):
        for pid in ("openai_compat@custom", "openai_compat"):
            original = self.sample()
            original["providers"]["pipeline"]["llm"] = pid
            original["providers"]["creds"][pid] = {"catalog":"abacus", "base_url":"https://routellm.abacus.ai/v1", "api_key":"synthetic"}
            clean = cfg._purged_abacus_data(original)
            self.assertEqual(clean["providers"]["pipeline"]["llm"], "")
            self.assertNotIn("abacus", json.dumps(clean).casefold())

    def test_getters_reject_stale_saved_selection(self):
        with patch.object(cfg, "load_api_keys", return_value=self.sample()):
            self.assertEqual(cfg.get_provider_mode(), "gemini")
            self.assertEqual(cfg.get_sidecar_provider(), "")
            self.assertEqual(cfg.get_coding_provider(), "")
            self.assertEqual(cfg.get_provider_config("openai_compat@abacus"), {})

    def test_unrelated_settings_are_exactly_unchanged(self):
        for data in ({"providers":{"mode":"pipeline"},"other":[1,2]},
                     {"providers":{"creds":{"x":{"base_url":"http://localhost:8000/v1"}},"pipeline":{"llm":"x"}}},
                     {"user_name":"Deniz","notes":{"project":"Abacus study"}}):
            self.assertEqual(cfg._purged_abacus_data(data), data)

    def test_purge_and_all_writers_scrub_primary_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            file.write_text(json.dumps(self.sample()))
            with patch.object(cfg, "CONFIG_FILE", file):
                self.assertTrue(cfg.purge_abacus_settings())
                self.assertFalse(cfg.purge_abacus_settings())
                cfg.save_provider_config("openai_compat@abacus", {"api_key":"synthetic-new", "base_url":"https://routellm.abacus.ai/v1"})
                cfg.save_providers(creds={"openai_compat@custom":{"base_url":"https://routellm.abacus.ai/v1", "api_key":"synthetic-new"}}, pipeline={"llm":"openai_compat@custom"})
                for path in (file, Path(str(file) + ".bak")):
                    data = json.loads(path.read_text())
                    self.assertNotIn("abacus", json.dumps(data).casefold())
                    self.assertEqual(data["providers"]["creds"]["openai_compat@nvidia"]["api_key"], "synthetic-kept")

    def test_backup_only_purge_does_not_create_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            backup = Path(str(file) + ".bak"); backup.write_text(json.dumps(self.sample()))
            with patch.object(cfg, "CONFIG_FILE", file):
                self.assertTrue(cfg.purge_abacus_settings())
                self.assertFalse(file.exists())
                self.assertNotIn("abacus", backup.read_text().casefold())
                self.assertEqual(cfg.get_sidecar_provider(), "")

    def test_broken_backup_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "settings.json"
            backup = Path(str(file) + ".bak"); backup.write_text("{broken")
            with patch.object(cfg, "CONFIG_FILE", file):
                self.assertFalse(cfg.purge_abacus_settings())
            self.assertEqual(backup.read_text(), "{broken")

    def test_stale_coding_request_cannot_restore_removed_model(self):
        from core import coding_router, aether_agent
        with patch.object(coding_router, "resting", return_value=0):
            self.assertEqual(coding_router.ladder("openai_compat@abacus", lambda _:True), [aether_agent.PROVIDER_ID, coding_router.GEMINI])


    def test_unrelated_legacy_ids_and_malformed_selections_are_preserved(self):
        for data in (
            {"providers":{"creds":{"openai_compat":{"catalog":"nvidia", "api_key":"synthetic-kept"}}, "pipeline":{"llm":"openai_compat"}}},
            {"providers":{"creds":{}, "sidecar":["invalid"], "pipeline":{"llm":["invalid"]}}},
        ):
            self.assertEqual(cfg._purged_abacus_data(data), data)
