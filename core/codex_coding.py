"""Use the user's signed-in Codex CLI as a text model for the coding agent."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PROVIDER_ID = "codex_cli"


def _command() -> list[str]:
    if sys.platform != "win32":
        if executable := shutil.which("codex"):
            return [executable]
    else:
        if executable := shutil.which("codex.exe"):
            return [executable]
        if (shim := shutil.which("codex.cmd")) and (node := shutil.which("node.exe")):
            script = Path(shim).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
            if script.is_file():
                return [node, str(script)]
    raise RuntimeError("Codex CLI bulunamadı. Kurduktan sonra JARVIS’i yeniden aç.")


def generate_content(prompt: str):
    with tempfile.TemporaryDirectory(prefix="jarvis-codex-") as folder:
        reply = Path(folder) / "reply.txt"
        try:
            result = subprocess.run(
                [*_command(), "--ask-for-approval", "never", "exec",
                 "--sandbox", "read-only", "--skip-git-repo-check",
                 "--ignore-user-config", "--ignore-rules", "--ephemeral",
                 "--output-last-message", str(reply), "-"],
                input=("Respond with the requested text only. Use only the supplied context; "
                       "JARVIS applies edits and runs tests separately.\n\n" + prompt),
                cwd=folder, capture_output=True, encoding="utf-8", errors="replace",
                timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Codex yanıtı zaman aşımına uğradı.") from None
        except OSError:
            raise RuntimeError("Codex CLI başlatılamadı. Kurulumu kontrol et.") from None

        if result.returncode or not reply.is_file():
            raise RuntimeError("Codex yanıtı alınamadı. PowerShell’de codex login status ile hesabını kontrol et.")
        text = reply.read_text(encoding="utf-8").strip()
        if not text:
            raise RuntimeError("Codex boş yanıt verdi.")
        return SimpleNamespace(text=text)
