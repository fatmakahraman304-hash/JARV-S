import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx

from core import platform_authorization as auth
from memory import config_manager as cfg
from providers import registry


class PlatformAuthorizationTests(unittest.TestCase):
    def test_keys_are_verified_only_against_official_endpoints(self):
        for site, expected in (("chatgpt", "api.openai.com"), ("claude", "api.anthropic.com")):
            request = httpx.Request("POST", f"https://{expected}/v1/chat/completions")
            reply = httpx.Response(200, request=request, json={"choices": [
                {"message": {"content": "OK"}},
            ]})
            with self.subTest(site=site), patch.object(auth.httpx, "post", return_value=reply) as post:
                auth.verify_model(site, "example-key", "example-model")
                self.assertEqual(post.call_args.args[0], str(request.url))
                self.assertFalse(post.call_args.kwargs["follow_redirects"])
                self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer example-key")

    def test_rejected_key_is_not_echoed(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(401, request=request, text="example-key")
        with patch.object(auth.httpx, "post", return_value=response):
            with self.assertRaisesRegex(auth.AuthorizationError, "^API anahtarı kabul edilmedi"):
                auth.verify_model("chatgpt", "example-key", "example-model")

    def test_github_requires_authenticated_repo_write_access(self):
        with patch.object(auth.shutil, "which", return_value="gh"), patch.object(
            auth.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 0),
                subprocess.CompletedProcess([], 0, json.dumps({"permissions": {"push": False}})),
            ],
        ):
            with self.assertRaisesRegex(auth.AuthorizationError, "yazma yetkisine"):
                auth.github_access()

    def test_github_returns_the_authenticated_account_after_verifying_repo_write_access(self):
        with patch.object(auth.shutil, "which", return_value="gh"), patch.object(
            auth.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 0),
                subprocess.CompletedProcess([], 0, json.dumps({"permissions": {"push": True}})),
                subprocess.CompletedProcess([], 0, "example-user\n"),
            ],
        ) as run:
            self.assertEqual(auth.github_access(), "example-user")
            self.assertIn(f"repos/{auth.GITHUB_REPOSITORY}", run.call_args_list[1].args[0])
            self.assertEqual(run.call_args.args[0][-3:], ["user", "--jq", ".login"])

    def test_authorized_claude_can_be_selected_without_replacing_voice(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cfg, "CONFIG_FILE", Path(folder) / "api_keys.json"), patch.object(cfg, "CONFIG_DIR", Path(folder)):
            provider, base, _ = auth.MODEL_PLATFORMS["claude"]
            cfg.save_provider_mode("gemini")
            cfg.save_authorized_model(provider, "example-key", "example-model", base,
                                      coding=True, background=True)
            self.assertEqual(cfg.get_provider_mode(), "gemini")
            self.assertEqual(cfg.get_coding_provider(), provider)
            self.assertEqual(cfg.get_sidecar_provider(), provider)
            self.assertTrue(cfg.get_sidecar_first())
            model = registry.build(provider, cfg.get_provider_config(provider))
            self.assertEqual(model.base, base)
            cfg.save_authorized_model(provider, "example-key", "example-model", base,
                                      coding=False, background=False)
            self.assertEqual(cfg.get_coding_provider(), "")
            self.assertEqual(cfg.get_sidecar_provider(), "")
