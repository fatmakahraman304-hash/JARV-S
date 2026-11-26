"""Use the locally installed Claude Code CLI for FRIDAY coding prompts."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PROVIDER_ID = "claude_code"


def _executable() -> str:
    if executable := shutil.which("claude.exe" if sys.platform == "win32" else "claude"):
        return executable
    if sys.platform == "win32":
        candidates = [Path.home() / ".local" / "bin" / "claude.exe"]
        for variable, directory in (
            ("LOCALAPPDATA", "Microsoft/WinGet/Links"), ("ProgramFiles", "WinGet/Links")
        ):
            if root := os.environ.get(variable):
                candidates.append(Path(root) / directory / "claude.exe")
        for candidate in candidates:
            if candidate.is_absolute() and candidate.is_file():
                return str(candidate)
    raise RuntimeError("Claude Code bulunamadı. PowerShell’de winget install Anthropic.ClaudeCode çalıştır.")


def generate_content(prompt: str):
    executable = _executable()
    with tempfile.TemporaryDirectory(prefix="aether-claude-") as folder:
        try:
            result = subprocess.run(
                [executable, "--print", "--output-format", "json", "--tools", "",
                 "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                 "--disallowedTools", "mcp__*", "--setting-sources", "",
                 "--no-chrome", "--no-session-persistence",
                 "Return only the requested response using the supplied stdin as the task. "
                 "FRIDAY applies changes and tests separately."],
                input=prompt, cwd=folder, capture_output=True, encoding="utf-8", errors="replace",
                timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude Code yanıtı zaman aşımına uğradı.") from None
        except OSError:
            raise RuntimeError("Claude Code başlatılamadı. PowerShell’de claude --version ile kurulumu kontrol et.") from None

    try:
        response = json.loads(result.stdout)
    except ValueError:
        response = {}
    if isinstance(response, dict) and result.returncode == 0 and not response.get("is_error"):
        text = response.get("result")
        if isinstance(text, str) and text.strip():
            return SimpleNamespace(text=text.strip())
    diagnostics = (result.stdout + "\n" + result.stderr).casefold()
    if any(word in diagnostics for word in ("not logged in", "please run /login", "401 unauthorized", "login required")):
        raise RuntimeError("Claude Code oturumu kapalı. PowerShell’de claude auth login çalıştır.")
    if any(word in diagnostics for word in ("usage limit", "rate limit", "429 too many requests")):
        raise RuntimeError("Claude Code kullanım sınırına ulaşıldı.")
    if any(word in diagnostics for word in ("unknown option", "unrecognized option")):
        raise RuntimeError("Claude Code sürümü bu komutu desteklemiyor. PowerShell’de winget upgrade Anthropic.ClaudeCode çalıştır.")
    raise RuntimeError(f"Claude Code yanıtı alınamadı (kod {result.returncode}). PowerShell’de claude auth status ile oturumu kontrol et.")
