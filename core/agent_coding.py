"""
core/agent_coding.py — let Claude Code or Codex work INSIDE the project.

Used as plain text models (core/claude_coding.py, core/codex_coding.py) they
see only what Mayk pastes into one prompt and answer with whole files. As
agents they read any file they need, search the code, make small exact edits,
run the project's tests and keep going until the tests pass — the way a person
works, and far stronger on a real codebase.

Mayk stays in charge around them: it snapshots the folder before (for undo),
works out afterwards which files really changed, runs its own checks on them
and hands any failure back for one more round (actions/dev_agent.py).

Limits:
  Claude Code  edits are accepted inside the folder; shell commands are limited
               to running and testing code (python, pytest, npm, node, …).
  Codex        runs in its workspace-write sandbox: it can only write inside the
               folder, with no network.

No Qt here; nothing raises except RuntimeError with a sentence for the user.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from core import claude_coding, codex_coding, jarvis_agent

AGENT_TIMEOUT = 45 * 60          # one agent round, seconds (a whole site or app takes a while)

# Claude Code works with the strongest model the user's plan has: Opus first
# (Claude Opus 5.5 today — the alias always means the newest Opus), Sonnet if
# Opus is not available on the plan or is overloaded. Settable under the
# "coding" plugin config as {"model": "opus" | "sonnet" | a full model id}.
CLAUDE_MODELS = ("opus", "sonnet")

# Shell commands Claude Code may run on its own: running and testing code.
_CLAUDE_BASH = [
    "python", "python3", "py", "pytest", "pip install", "pip show", "pip list",
    "node", "npm test", "npm run", "npm install", "npx", "yarn", "pnpm",
    "go test", "go build", "go run", "cargo test", "cargo build", "cargo run",
    "dotnet build", "dotnet test", "mvn test", "gradle test", "make",
    "git status", "git diff", "git log", "ls", "dir", "cat", "type", "find", "grep",
    # building, checking and running more kinds of project
    "pip3 install", "python -m", "py -m", "uv", "poetry", "deno", "bun", "tsc", "eslint", "prettier",
    "ruff", "black", "mypy", "flutter", "dart", "java", "javac", "gcc", "g++", "clang", "cmake",
    "php", "composer", "ruby", "bundle", "rustc", "go mod", "go vet", "dotnet run", "dotnet new",
    "npm create", "npm init", "npm ci", "npm ls", "mkdir", "echo", "where", "which", "head", "tail", "wc",
]
# WebSearch/WebFetch: the agent looks up current docs and APIs like a person
# would, instead of guessing from memory.
_CLAUDE_TOOLS = ["Read", "Edit", "MultiEdit", "Write", "Glob", "Grep", "LS", "TodoWrite",
                 "WebSearch", "WebFetch", "NotebookEdit"] + \
    [f"Bash({c}:*)" for c in _CLAUDE_BASH]

AGENT_PROVIDERS = {claude_coding.PROVIDER_ID, codex_coding.PROVIDER_ID, jarvis_agent.PROVIDER_ID}


def available(provider: str) -> bool:
    """Is this provider one that can work as an agent, and is it installed?"""
    try:
        if provider == claude_coding.PROVIDER_ID:
            claude_coding._executable()
            return True
        if provider == codex_coding.PROVIDER_ID:
            codex_coding._command()
            return True
        if provider == jarvis_agent.PROVIDER_ID:       # Mayk's own agent: needs only a free brain
            return jarvis_agent.available()
    except Exception:
        return False
    return False


def _brief(instruction: str, guide: str, extra: str) -> str:
    return (
        "You are the coding agent of Mayk, working directly in this project folder. Work like a "
        "senior engineer who owns the result: the user asked by voice and will not review your diff, "
        "so what you hand back must simply work.\n\n"
        f"TASK (from the user, often in Turkish):\n{instruction}\n\n"
        + (f"PROJECT RULES — follow them exactly:\n{guide}\n\n" if guide else "")
        + (f"{extra}\n\n" if extra else "")
        + "How to work — think hard before you edit:\n"
        "1. Understand first. Read the code that matters, find how the project already does similar "
        "things and reuse it. If the task is ambiguous, choose the most sensible reading the user "
        "would expect and say which in your summary — do not stop to ask.\n"
        "2. Plan. For anything bigger than a small fix, write a short TodoWrite list and work through it.\n"
        "3. Build it completely. No placeholders, no 'TODO: implement', no fake data standing in for "
        "real logic, no half-finished screens. A website gets real content, a responsive layout and "
        "working links; an app gets its real features. Look up current library docs with WebSearch/"
        "WebFetch instead of guessing APIs.\n"
        "4. Make focused, exact edits. Never rewrite or delete files wholesale to make a small change, "
        "never touch secrets, keys or local settings files, never delete the user's data.\n"
        "5. Verify like a careful reviewer. Run the tests (add tests for new logic where the project has "
        "a test setup), run or import what you changed, build it if it builds. Read your own diff once "
        "for bugs, edge cases and leftovers. If anything fails, fix it and run again until it passes.\n"
        "6. Do not commit, push or change git history.\n"
        "7. Finish with a short summary IN TURKISH: what you built or changed, how you checked it, and "
        "how to open or run it — three to five sentences, no code."
    )


def _kill(proc: subprocess.Popen, flag: dict) -> None:
    flag["timeout"] = True
    try:
        proc.kill()
    except Exception:
        pass


def _stream(cmd: list[str], cwd: Path, stdin_text: str, on_line, timeout: float,
            env: dict | None = None) -> tuple[int, list[str], str]:
    """Run, feeding each stdout line to on_line. Returns (code, lines, stderr)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                                creationflags=flags, env=env)
    except OSError as exc:
        raise RuntimeError(f"Kodlama ajanı başlatılamadı: {exc}") from None
    flag: dict = {}
    timer = threading.Timer(timeout, _kill, args=(proc, flag))
    timer.start()
    err_parts: list[str] = []
    t_err = threading.Thread(target=lambda: err_parts.append(proc.stderr.read() or ""), daemon=True)
    t_err.start()
    lines: list[str] = []
    try:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except Exception:
            pass
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line:
                continue
            lines.append(line)
            try:
                on_line(line)
            except Exception:
                pass
        proc.wait()
    finally:
        timer.cancel()
    t_err.join(timeout=5)
    stderr = "".join(err_parts)
    if flag.get("timeout"):
        stderr += "\n(timeout)"
    return proc.returncode or 0, lines, stderr


# ── Claude Code ──────────────────────────────────────────────────────────────

def _claude_event(line: str, log) -> str:
    """Log what the agent is doing; return the final result text if this is it."""
    try:
        ev = json.loads(line)
    except ValueError:
        return ""
    if ev.get("type") == "assistant":
        for part in (ev.get("message") or {}).get("content") or []:
            if part.get("type") == "tool_use":
                name, inp = part.get("name", ""), part.get("input") or {}
                target = inp.get("file_path") or inp.get("path") or inp.get("pattern") or inp.get("command") or ""
                verb = {"Read": "Okuyor", "Edit": "Düzenliyor", "MultiEdit": "Düzenliyor", "Write": "Yazıyor",
                        "Bash": "Çalıştırıyor", "Grep": "Arıyor", "Glob": "Arıyor", "LS": "Bakıyor",
                        "TodoWrite": "Planlıyor"}.get(name, name)
                if name != "TodoWrite":
                    log(f"  {verb}: {str(target)[:140]}")
            elif part.get("type") == "text" and part.get("text", "").strip():
                log("  " + part["text"].strip().splitlines()[0][:160])
    if ev.get("type") == "result":
        if ev.get("is_error"):
            raise RuntimeError(str(ev.get("result") or "Claude Code hata verdi")[:300])
        return str(ev.get("result") or "")
    return ""


def claude_models() -> list[str]:
    """The models to try with Claude Code, strongest first."""
    try:
        from memory.config_manager import get_plugin_config
        chosen = str(get_plugin_config("coding").get("model") or "").strip()
    except Exception:
        chosen = ""
    out = [chosen] if chosen else []
    out += [m for m in CLAUDE_MODELS if m not in out]
    return out


def _claude_cmd(exe: str, model: str) -> list[str]:
    cmd = [exe, "--print", "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--allowedTools", ",".join(_CLAUDE_TOOLS),
           "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--no-session-persistence"]
    if model:
        cmd += ["--model", model]
        if model != "sonnet":
            cmd += ["--fallback-model", "sonnet"]      # Opus overloaded: Sonnet carries on
    return cmd


def _model_refused(diag: str) -> bool:
    d = diag.casefold()
    return any(w in d for w in ("invalid model", "model not found", "not available", "does not have access",
                                "no access to", "unknown model", "not_found_error", "fallback-model"))


def _run_claude(folder: Path, prompt: str, log) -> str:
    exe = claude_coding._executable()
    models = claude_models()
    for i, model in enumerate(models + [""]):
        if i:
            log(f"  {models[i - 1]} kullanılamadı; {model or 'varsayılan model'} ile devam.")
        else:
            log(f"  Model: {model} (Claude Code)")
        text, code, lines, err = _claude_once(exe, model, folder, prompt, log)
        if text:
            return text
        diag = err + "\n".join(lines[-5:])
        if not _model_refused(diag):
            break
    return _claude_fail(code, lines, err)


def _claude_once(exe: str, model: str, folder: Path, prompt: str, log):
    result = {"text": ""}

    def on_line(line):
        txt = _claude_event(line, log)
        if txt:
            result["text"] = txt
    try:
        code, lines, err = _stream(_claude_cmd(exe, model), folder, prompt, on_line, AGENT_TIMEOUT)
    except RuntimeError as exc:                 # an error event: maybe the model was refused
        if _model_refused(str(exc)):
            return "", 1, [str(exc)], str(exc)
        raise
    return result["text"], code, lines, err


def _claude_fail(code, lines, err) -> str:
    diag = (err + "\n".join(lines[-5:])).casefold()
    if any(w in diag for w in ("not logged in", "please run /login", "401")):
        raise RuntimeError("Claude Code oturumu kapalı. PowerShell'de claude auth login çalıştır.")
    if any(w in diag for w in ("usage limit", "rate limit", "429")):
        raise RuntimeError("Claude Code kullanım sınırına ulaşıldı.")
    if "unknown option" in diag or "unrecognized" in diag:
        raise RuntimeError("Claude Code sürümü eski. PowerShell'de winget upgrade Anthropic.ClaudeCode çalıştır.")
    if "(timeout)" in err:
        raise RuntimeError("Kodlama ajanı süre sınırını aştı.")
    raise RuntimeError(f"Claude Code bitirmeden durdu (kod {code}).")


# ── Codex ────────────────────────────────────────────────────────────────────

def _codex_event(line: str, log) -> None:
    try:
        ev = json.loads(line)
    except ValueError:
        return
    item = ev.get("item") or ev.get("msg") or {}
    kind = item.get("type") or item.get("item_type") or ev.get("type", "")
    if "command" in kind or kind == "exec_command_begin":
        cmd = item.get("command") or item.get("cmd") or ""
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
        if cmd:
            log(f"  Çalıştırıyor: {str(cmd)[:140]}")
    elif "file_change" in kind or "patch" in kind:
        changes = item.get("changes") or []
        paths = [c.get("path", "") for c in changes if isinstance(c, dict)] if isinstance(changes, list) \
            else list(changes) if isinstance(changes, dict) else []
        if paths:
            log("  Düzenliyor: " + ", ".join(Path(p).name for p in paths[:4]))


def _run_codex(folder: Path, prompt: str, log) -> str:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="jarvis-codex-agent-") as tmp:
        reply = Path(tmp) / "reply.txt"
        cmd = [*codex_coding._command(), "--ask-for-approval", "never", "exec",
               "--sandbox", "workspace-write", "--skip-git-repo-check", "--json",
               "--cd", str(folder), "--output-last-message", str(reply), "-"]
        code, lines, err = _stream(cmd, folder, prompt, lambda ln: _codex_event(ln, log), AGENT_TIMEOUT)
        if reply.is_file() and reply.read_text(encoding="utf-8", errors="replace").strip():
            return reply.read_text(encoding="utf-8", errors="replace").strip()
    diag = (err + "\n".join(lines[-5:])).casefold()
    if any(w in diag for w in ("not logged in", "401", "authentication required", "refresh token")):
        raise RuntimeError("Codex oturumu doğrulanamadı. PowerShell'de codex login çalıştır.")
    if any(w in diag for w in ("usage limit", "rate limit", "429")):
        raise RuntimeError("Codex kullanım sınırına ulaşıldı.")
    if "unexpected argument" in diag or "unrecognized" in diag:
        raise RuntimeError("Codex CLI sürümü eski; güncelle.")
    if "(timeout)" in err:
        raise RuntimeError("Kodlama ajanı süre sınırını aştı.")
    raise RuntimeError(f"Codex bitirmeden durdu (kod {code}).")


def run(provider: str, folder: Path, instruction: str, guide: str = "", extra: str = "",
        log=print) -> str:
    """One agent round in `folder`. Returns the agent's own summary."""
    prompt = _brief(instruction, guide, extra)
    if provider == claude_coding.PROVIDER_ID:
        return _run_claude(folder, prompt, log)
    if provider == codex_coding.PROVIDER_ID:
        return _run_codex(folder, prompt, log)
    if provider == jarvis_agent.PROVIDER_ID:
        return jarvis_agent.run(folder, prompt, log)
    raise RuntimeError("Bu model ajan olarak çalışamıyor.")


# ── snapshot: what the agent really changed, and undo ───────────────────────

_SKIP = {".git", ".hg", ".svn", "node_modules", "venv", ".venv", "env", "__pycache__",
         ".jarvis_backup", "dist", "build", ".idea", ".vscode", ".mypy_cache", ".pytest_cache"}
_MAX_BYTES = 2_000_000
_MAX_TOTAL = 300_000_000         # content kept for undo; past this only hashes


def snapshot(folder: Path) -> dict[str, tuple[float, int, bytes]]:
    """{relative path: (mtime, size, digest, content | None)} for the project's files."""
    import hashlib
    out = {}
    kept = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith(".jarvis")]
        for name in files:
            p = Path(root) / name
            try:
                st = p.stat()
                if st.st_size > _MAX_BYTES:
                    continue
                data = p.read_bytes()
                keep = kept + len(data) <= _MAX_TOTAL
                kept += len(data) if keep else 0
                out[p.relative_to(folder).as_posix()] = (st.st_mtime, st.st_size,
                                                         hashlib.sha1(data).hexdigest(),
                                                         data if keep else None)
            except OSError:
                continue
        if len(out) > 20_000:
            break
    return out


def diff(before: dict, after: dict) -> tuple[list[str], list[str], list[str]]:
    """(changed, created, deleted) relative paths."""
    changed = [r for r in after if r in before and after[r][2] != before[r][2]]  # digests
    created = [r for r in after if r not in before]
    deleted = [r for r in before if r not in after]
    return sorted(changed), sorted(created), sorted(deleted)


def restore(folder: Path, before: dict, after_paths: list[str]) -> None:
    """Put the folder back: rewrite what changed, remove what was created."""
    for rel, (_m, _s, _h, data) in before.items():
        if data is None:
            continue
        p = folder / rel
        try:
            if not p.exists() or p.read_bytes() != data:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        except OSError:
            pass
    for rel in after_paths:
        if rel not in before:
            try:
                (folder / rel).unlink()
            except OSError:
                pass
