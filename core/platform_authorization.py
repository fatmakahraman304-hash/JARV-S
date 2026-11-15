"""Explicit API authorization and GitHub CLI access for the desktop app."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

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


def find_github_cli() -> str | None:
    executable = shutil.which("gh")
    if executable or sys.platform != "win32":
        return executable

    # A running process or its launcher may still have the pre-install PATH.
    for variable, directory in (
        ("ProgramW6432", "GitHub CLI"),
        ("ProgramFiles", "GitHub CLI"),
        ("ProgramFiles(x86)", "GitHub CLI"),
        ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
        ("ProgramFiles", "WinGet/Links"),
    ):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / directory / "gh.exe"
            if candidate.is_absolute() and candidate.is_file():
                return str(candidate)
    return None


def github_access() -> str:
    executable = find_github_cli()
    if not executable:
        raise AuthorizationError("GitHub CLI (gh) kurulu olmalı.")
    options = dict(
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=15, env=dict(os.environ, GH_PROMPT_DISABLED="1"),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    status = subprocess.run(
        [executable, "auth", "status", "--hostname", "github.com"], **options,
    )
    if status.returncode:
        raise AuthorizationError("GitHub oturumu doğrulanamadı. GitHub hesabını bağla ve tekrar dene.")
    api = [executable, "api", "--hostname", "github.com"]
    result = subprocess.run([*api, f"repos/{GITHUB_REPOSITORY}"], **options)
    if result.returncode:
        raise AuthorizationError("GitHub erişimi doğrulanamadı. Oturumu ve internet bağlantısını kontrol et.")
    permissions = json.loads(result.stdout).get("permissions") or {}
    if not permissions.get("push"):
        raise AuthorizationError("GitHub hesabı bu depoya yazma yetkisine sahip değil.")
    account = subprocess.run([*api, "user", "--jq", ".login"], **options)
    login = account.stdout.strip()
    if account.returncode or not login:
        raise AuthorizationError("Bağlı GitHub hesabı doğrulanamadı.")
    return login
