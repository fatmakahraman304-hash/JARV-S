"""AETHER NVIDIA Build API: anahtar gizliliği, model seçimi ve otomatik yedekler."""
import json
import unittest
import urllib.error
from unittest import mock

from core import nvidia_account as nvidia
from core import aether_agent


class _Reply:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, *_):
        return self.body


class NvidiaAccountTests(unittest.TestCase):
    def setUp(self):
        nvidia._CACHE.update(key=None, at=0., models=None, reason=None)

    def test_key_from_local_provider_only_not_other_provider(self):
        creds = {"creds": {
            "openai_compat@openai": {"api_key": "wrong-key"},
            "openai_compat@nvidia": {"api_key": "nvidia-private-key"},
        }}
        with mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch("memory.config_manager.get_providers", return_value=creds):
            self.assertEqual(nvidia.api_key(), "nvidia-private-key")
        with mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch("memory.config_manager.get_providers", return_value={
                 "creds": {"openai_compat@openai": {"api_key": "wrong-key"}}}), \
             mock.patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            self.assertEqual(nvidia.api_key(), "")

    def test_key_can_be_loaded_from_environment(self):
        with mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch("memory.config_manager.get_providers", return_value={}), \
             mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-secret"}):
            self.assertEqual(nvidia.api_key(), "nvapi-secret")

    def test_catalog_models_filtered_to_available_ids(self):
        result = {"data": [{"id": "z-ai/glm-5.3-flash"},
                           {"id": "nvidia/nemotron-3.5-super-vl-120b-a12b"},
                           {"id": "other/unknown"}]}
        with mock.patch.object(nvidia.urllib.request, "urlopen", return_value=_Reply(result)) as req, \
             mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch("memory.config_manager.get_provider_config", return_value={}):
            models = nvidia.available_models("private", refresh=True)
        self.assertEqual(models[:2], ["nvidia/nemotron-3.5-super-vl-120b-a12b",
                                     "z-ai/glm-5.3-flash"])
        request = req.call_args.args[0]
        self.assertEqual(request.full_url, "https://integrate.api.nvidia.com/v1/models")
        self.assertNotIn("private", repr(models))
        self.assertEqual(request.headers.get("Authorization"), "Bearer private")

    def test_free_limit_is_not_assumed_unlimited(self):
        err = urllib.error.HTTPError("https://integrate.api.nvidia.com/v1/models",
                                     429, "rate limit", {}, None)
        with mock.patch.object(nvidia.urllib.request, "urlopen", side_effect=err):
            self.assertEqual(nvidia.available_models("rate-key", refresh=True), [])
        self.assertEqual(nvidia._CACHE["reason"], "limit")
        with mock.patch.object(nvidia, "api_key", return_value="rate-key"), \
             mock.patch.object(nvidia.urllib.request, "urlopen", side_effect=err):
            text = nvidia.status_text()
        self.assertIn("429", text)
        self.assertNotIn("rate-key", text)

    def test_network_error_is_not_claimed_as_zero_quota(self):
        with mock.patch.object(nvidia.urllib.request, "urlopen", side_effect=OSError("offline")), \
             mock.patch("memory.config_manager.get_plugin_config", return_value={}), \
             mock.patch("memory.config_manager.get_provider_config", return_value={}):
            available = nvidia.available_models("test-key", refresh=True)
        self.assertIn("nvidia/nemotron-3.5-lightning-30b-a3b", available)
        self.assertEqual(nvidia._CACHE["reason"], "unavailable")

    def test_offline_catalog_is_briefly_cached_and_cannot_confirm_a_selection(self):
        with mock.patch.object(nvidia.urllib.request, "urlopen", side_effect=OSError("offline")) as req:
            self.assertTrue(nvidia.available_models("test"))
            self.assertEqual(nvidia.available_models("test", verified_only=True), [])
            req.assert_called_once()
            nvidia.available_models("test", refresh=True)
            self.assertEqual(req.call_count, 2)

    def test_complete_request_and_secret_never_in_error(self):
        models = ["z-ai/glm-5.3-flash"]
        with mock.patch.object(nvidia, "api_key", return_value="private-key"), \
             mock.patch.object(nvidia, "available_models", return_value=models), \
             mock.patch.object(nvidia.urllib.request, "urlopen",
                               return_value=_Reply({"choices": [
                                   {"message": {"content": "Kod hazır."}}]})) as req:
            self.assertEqual(nvidia.complete_text("kod yaz"), "Kod hazır.")
        request = req.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://integrate.api.nvidia.com/v1/chat/completions")
        sent = json.loads(request.data)
        self.assertEqual(sent["model"], "z-ai/glm-5.3-flash")
        self.assertEqual(request.headers.get("Authorization"), "Bearer private-key")
        self.assertNotIn("private-key", repr(sent))
        err = urllib.error.HTTPError(request.full_url, 429, "rate limited", {},
                                     None)
        with mock.patch.object(nvidia, "api_key", return_value="private-key"), \
             mock.patch.object(nvidia, "available_models", return_value=models), \
             mock.patch.object(nvidia.urllib.request, "urlopen", side_effect=err):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA 429") as failure:
                nvidia.complete_text("iş")
        self.assertNotIn("private-key", str(failure.exception))


class NvidiaRoutingTests(unittest.TestCase):
    def test_nvidia_then_gemini(self):
        with mock.patch.object(nvidia, "api_key", return_value="nvapi-secret"), \
             mock.patch.object(nvidia, "available_models",
                               return_value=["z-ai/glm-5.3-flash"]), \
             mock.patch.object(aether_agent, "_settings", return_value={}), \
             mock.patch.object(aether_agent, "_gemini_key", return_value="gemini"), \
             mock.patch.object(aether_agent, "gemini_models",
                               return_value=["gemini-2.5-pro"]):
            names = [model.name for model in aether_agent.brains()]
        self.assertEqual(names, [
            "NVIDIA (z-ai/glm-5.3-flash)", "Gemini (gemini-2.5-pro)"])

    def test_nvidia_agent_tool_call_keeps_tools(self):
        response = {"choices": [{"message": {"tool_calls": [
            {"id": "a", "function": {"name": "read_file",
                                     "arguments": '{"path":"main.py"}'}}]}}]}
        brain = aether_agent.OpenAIBrain(nvidia.BASE_URL, "secret", "z-ai/glm-5.3-flash", "NVIDIA")
        with mock.patch.object(aether_agent, "_http_json", return_value=response) as request:
            _, calls, _ = brain.turn([{"role": "user", "text": "dosyayı oku"}])
        self.assertEqual(calls[0]["name"], "read_file")
        self.assertEqual(request.call_args.args[0],
                         "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertIn("tools", request.call_args.args[1])

    def test_plain_code_uses_nvidia_first(self):
        from actions import dev_agent
        from core import coding_router
        with mock.patch.object(coding_router, "ladder",
                               return_value=[aether_agent.PROVIDER_ID, ""]), \
             mock.patch.object(nvidia, "api_key", return_value="nvidia"), \
             mock.patch.object(nvidia, "available_models",
                               return_value=["z-ai/glm-5.3-flash"]), \
             mock.patch.object(nvidia, "complete_text", return_value="NVIDIA yaptı") as run, \
             mock.patch.object(dev_agent.gemini, "call") as gem:
            self.assertEqual(dev_agent._get_model().generate_content("kod").text,
                             "NVIDIA yaptı")
        run.assert_called_once()
        gem.assert_not_called()

    def test_plain_code_uses_gemini_after_nvidia_429(self):
        from actions import dev_agent
        from core import coding_router
        with mock.patch.object(coding_router, "ladder",
                               return_value=[aether_agent.PROVIDER_ID, ""]), \
             mock.patch.object(coding_router, "rest", return_value=3600), \
             mock.patch.object(nvidia, "api_key", return_value="nvidia"), \
             mock.patch.object(nvidia, "available_models",
                               return_value=["z-ai/glm-5.3-flash"]), \
             mock.patch.object(nvidia, "complete_text", side_effect=RuntimeError("NVIDIA 429")), \
             mock.patch.object(dev_agent.gemini, "call",
                               return_value=mock.Mock(text="Gemini devam etti")) as gem:
            self.assertEqual(dev_agent._get_model().generate_content("kod").text,
                             "Gemini devam etti")
        gem.assert_called_once()

    def test_nvidia_ui_is_registered(self):
        from providers.llm_openai import PRESETS, CATALOG
        self.assertEqual(PRESETS["NVIDIA"], nvidia.BASE_URL)
        self.assertEqual(next(p for p in CATALOG if p["id"] == "nvidia")["values"]["model"],
                         "nvidia/nemotron-3.5-lightning-30b-a3b")
        from pathlib import Path
        panel = (Path(__file__).resolve().parents[1] / "gui/providers_panel.py").read_text(
            encoding="utf-8")
        self.assertIn("NVIDIA API anahtarınızı", panel)
        self.assertIn('endswith("@nvidia")', panel)
        self.assertIn("working_model", panel)
        self.assertIn("box.setCurrentIndex(index)", panel)

    def test_nvidia_settings_hints_are_in_turkish(self):
        from providers.llm_openai import PROVIDER, CATALOG
        from pathlib import Path
        fields = {field.key: field for field in PROVIDER["needs"]}
        self.assertEqual(fields["api_key"].label, "API anahtarı")
        self.assertIn("YENİLE", fields["model"].hint)
        self.assertNotIn("REFRESH", fields["model"].hint)
        self.assertEqual(fields["vision"].label, "Görselleri anlayabilir")
        self.assertEqual(fields["base_url"].label, "API adresi")
        self.assertIn("kendiniz girin", next(entry for entry in CATALOG
                                             if entry["id"] == "custom")["note"])

        panel = (Path(__file__).resolve().parents[1] / "gui/providers_panel.py").read_text(
            encoding="utf-8")
        self.assertIn("API anahtarınızı buraya yapıştırın", panel)
        self.assertIn("Önce Gemini — seçilen model yedek", panel)
        self.assertIn("Önce seçilen model — Gemini yedek", panel)
        self.assertIn("kodlama ajanının NVIDIA → Gemini sırasından ayrıdır", panel)
        self.assertNotIn('hint=f"Needed — create one', panel)
        self.assertNotIn('f"{f.label}   (optional)"', panel)


class NvidiaProbeTests(unittest.TestCase):
    """MODEL LISTE başarılı olsa bile gerçek chat çağrısının hatası anlaşılmalı."""

    @staticmethod
    def _provider(key="secret-do-not-show"):
        from providers.llm_openai import OpenAICompatLLM, PRESETS
        return OpenAICompatLLM({
            "base_url": PRESETS["NVIDIA"],
            "api_key": key,
            "model": "z-ai/glm-5.3-flash",
        })

    def test_nvidia_probe_requires_key(self):
        instance = self._provider("")
        with mock.patch.object(instance, "complete") as complete:
            ok, message = instance.probe(check_vision=False)
        self.assertFalse(ok)
        self.assertIn("anahtarı girilmedi", message)
        complete.assert_not_called()

    def test_nvidia_probe_http_errors_are_actionable(self):
        for error, expected in (
            ("401 API anahtarı reddedildi", "HTTP 401"),
            ("403 Permission denied", "HTTP 403"),
            ("402 Payment Required", "HTTP 402"),
            ("429 Too Many Requests", "HTTP 429"),
            ("404 Model not found", "HTTP 404"),
            ("504 API provider internal error: timed out", "HTTP 504"),
        ):
            with self.subTest(error=error):
                instance = self._provider()
                with mock.patch.object(instance, "complete", side_effect=RuntimeError(error)), \
                     mock.patch("core.nvidia_account.available_models", return_value=[]):
                    ok, message = instance.probe(check_vision=False)
                self.assertFalse(ok)
                self.assertIn(expected, message)
                self.assertNotIn("Sunucu çalışıyor mu?", message)
                self.assertNotIn("secret-do-not-show", message)

    def test_nvidia_probe_distinguishes_timeout_from_network(self):
        instance = self._provider()
        for error, expected in (
            ("ReadTimeout: timed out connecting", "zamanında yanıt vermedi"),
            ("ConnectError: All connection attempts failed", "bağlantısı kurulamadı"),
            ("SSL verification failed", "bağlantısı kurulamadı"),
        ):
            with self.subTest(error=error):
                with mock.patch.object(instance, "complete", side_effect=RuntimeError(error)), \
                     mock.patch("core.nvidia_account.available_models", return_value=[]):
                    ok, message = instance.probe(check_vision=False)
                self.assertFalse(ok)
                self.assertIn(expected, message)
                self.assertNotIn("Sunucu çalışıyor mu?", message)

    def test_nvidia_probe_uses_extra_timeout_without_extra_vision_call(self):
        instance = self._provider()
        with mock.patch.object(instance, "complete", return_value=("ok", [])) as complete, \
             mock.patch.object(instance, "ensure_vision_known") as vision:
            ok, message = instance.probe(check_vision=False)
        self.assertTrue(ok)
        self.assertIn("saniyede yanıt verdi", message)
        self.assertEqual(complete.call_args.kwargs["timeout"], 18.0)
        vision.assert_not_called()


    def test_glm_504_automatically_tests_nemotron_and_updates_choice(self):
        instance = self._provider()
        first = "z-ai/glm-5.3-flash"
        alternate = "nvidia/nemotron-3.5-lightning-30b-a3b"
        tried = []

        def fake_complete(messages, **kwargs):
            tried.append((instance.model, kwargs["timeout"]))
            if instance.model == first:
                raise RuntimeError("504 Model sunucusu yanıt vermedi")
            return ("ok", [])

        with mock.patch.object(instance, "complete", side_effect=fake_complete), \
             mock.patch("core.nvidia_account.available_models",
                        return_value=[first, alternate,
                                      "nvidia/nemotron-3.5-super-vl-120b-a12b"]):
            ok, msg = instance.probe(check_vision=False)
        self.assertTrue(ok)
        self.assertEqual(instance.model, alternate)
        self.assertEqual(tried[:2], [(first, 18.0), (alternate, 25.0)])
        self.assertIn("KAYDET VE UYGULA", msg)

    def test_authentication_and_quota_failures_do_not_test_other_models(self):
        for status in ("401 Yetkisiz", "402 Yetersiz kredi",
                       "403 Erişim yok", "429 Kullanım sınırı"):
            with self.subTest(status=status):
                instance = self._provider()
                with mock.patch.object(instance, "complete",
                                       side_effect=RuntimeError(status)) as complete, \
                     mock.patch("core.nvidia_account.available_models") as models:
                    ok, msg = instance.probe(check_vision=False)
                self.assertFalse(ok)
                self.assertEqual(complete.call_count, 1)
                models.assert_not_called()
                self.assertEqual(instance.model, "z-ai/glm-5.3-flash")

    def test_all_alternate_models_fail_without_changing_original_choice(self):
        instance = self._provider()
        first = "z-ai/glm-5.3-flash"
        with mock.patch.object(instance, "complete",
                               side_effect=RuntimeError("504 API provider internal error")) as complete, \
             mock.patch("core.nvidia_account.available_models",
                        return_value=[first, "nvidia/nemotron-3.5-lightning-30b-a3b",
                                      "nvidia/nemotron-3.5-super-vl-120b-a12b"]):
            ok, msg = instance.probe(check_vision=False)
        self.assertFalse(ok)
        self.assertEqual(instance.model, first)
        self.assertEqual(complete.call_count, 3)
        self.assertIn("Alternatif NVIDIA modelleri de yanıt vermedi.", msg)

    def test_connection_failures_do_not_retry_other_models(self):
        instance = self._provider()
        with mock.patch.object(instance, "complete",
                               side_effect=RuntimeError("ConnectError: connection refused")) as complete, \
             mock.patch("core.nvidia_account.available_models") as models:
            ok, _ = instance.probe(check_vision=False)
        self.assertFalse(ok)
        self.assertEqual(complete.call_count, 1)
        models.assert_not_called()

    def test_other_provider_keeps_original_probe_timeout(self):
        from providers.llm_openai import OpenAICompatLLM
        instance = OpenAICompatLLM({
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "test-model",
        })
        with mock.patch.object(instance, "complete", return_value=("ok", [])) as complete:
            ok, _ = instance.probe(check_vision=False)
        self.assertTrue(ok)
        self.assertEqual(complete.call_args.kwargs["timeout"], 20.0)


if __name__ == "__main__":
    unittest.main()


class ModelAttemptTests(unittest.TestCase):
    def test_refused_key_skips_shared_credentials_but_keeps_provider(self):
        from core import gemini
        client = mock.Mock()
        client.models.generate_content.side_effect = RuntimeError("401 UNAUTHENTICATED")
        provider = gemini.PROVIDER_PREFIX + "fallback"
        with mock.patch.dict(gemini._LADDERS, {gemini.FAST: ("one", "two")}), mock.patch.object(
                gemini, "_provider_rungs", return_value=(provider,)), mock.patch.object(
                gemini, "_provider_first", return_value=False), mock.patch.object(
                gemini, "client", return_value=client), mock.patch.object(
                gemini, "_provider_call", return_value="ok"), mock.patch.object(gemini, "_recent_attempts", []):
            self.assertEqual(gemini.call("selam", key="test"), "ok")
            stats = gemini.model_report()
        client.models.generate_content.assert_called_once()
        self.assertEqual(stats["one"]["last_error"], "auth")
        self.assertEqual(stats[provider]["errors"], 0)
        self.assertNotIn("two", stats)
