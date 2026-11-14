"""Explicit API authorization and GitHub CLI access for the desktop app."""

import json
import os
import shutil
import subprocess

import httpx

MODEL_PLATFORMS = {
    "chatgpt": ("openai_compat@openai", "https://api.openai.com/v1", "https://platform.openai.com/api-keys"),
    "claude": ("openai_compat@anthropic", "https://api.anthropic.com/v1", "https://platform.claude.com/settings/keys"),
}
GITHUB_REPOSITORY = "fatmakahraman304-hash/JARV-S"
GITHUB_LOGIN = ("gh", "auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https")


class AuthorizationError(ValueError):
    """A connection failure safe to display without credentials."""


def verify_model(site, key, model):
    """Verify usable model access with a minimal text request."""
    base = MODEL_PLATFORMS[site][1]
    try:
        result = httpx.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_completion_tokens" if site == "chatgpt" else "max_tokens": 256,
            },
            timeout=20, follow_redirects=False,
        )
        result.raise_for_status()
        response = result.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        messages = {
            401: "API anahtarı kabul edilmedi.", 403: "Bu modele erişim izni yok.",
            404: "Model bulunamadı. Sağlayıcıdaki model kimliğini kontrol et.",
            429: "API kotasını, bakiyeyi veya istek sınırını kontrol et.",
        }
        raise AuthorizationError(messages.get(exc.response.status_code, "Sağlayıcı isteği kabul etmedi.")) from None
    if not isinstance(response, str) or not response.strip():
        raise AuthorizationError("Model boş yanıt verdi.")


def github_access():
    if not shutil.which("gh"):
        raise AuthorizationError("GitHub CLI (gh) kurulu olmalı.")
    environment = dict(os.environ, GH_PROMPT_DISABLED="1")
    status = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"], capture_output=True,
        timeout=15, env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if status.returncode:
        raise AuthorizationError("GitHub oturumu açık değil. Önce GitHub’da giriş yap.")
    result = subprocess.run(
        ["gh", "api", "--hostname", "github.com", f"repos/{GITHUB_REPOSITORY}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15, env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise AuthorizationError("GitHub erişimi doğrulanamadı. Oturumu ve internet bağlantısını kontrol et.")
    permissions = json.loads(result.stdout).get("permissions") or {}
    if not permissions.get("push"):
        raise AuthorizationError("GitHub hesabı bu depoya yazma yetkisine sahip değil.")
