"""
Kodlama kurulumu: JARVIS'in en güçlü kodlama ajanıyla (Claude Code, Opus) çalışıp
çalışmadığını söyler, eksikse kurar ve giriş ekranını açar.

"Kodlama kurulumunu kontrol et", "Claude Code'u kur", "Claude'a giriş yap",
"kodlamada Opus kullan / Sonnet kullan".
"""

import shutil
import subprocess
import sys
import threading

PLUGIN = {
    "name": "coding_setup",
    "description": (
        "JARVIS'in kodlama ajanını hazırla ve durumunu söyle: 'kodlama kurulumunu kontrol et', "
        "'Claude Code'u kur', 'Claude'a giriş yap', 'kodlamada Opus/Sonnet kullan'. "
        "action: status | install | login | model | deepseek. deepseek için name: DeepSeek API anahtarı "
        "(kodlamayı DeepSeek yapar); model için name: opus | sonnet | tam model adı."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "status | install | login | model"},
            "name": {"type": "STRING", "description": "model için: opus, sonnet ya da tam model adı"},
        },
        "required": ["action"],
    },
}


def _say(player, text: str) -> None:
    if player:
        try:
            player.write_log(f"JARVIS: {text}")
        except Exception:
            pass


def status() -> str:
    from core import agent_coding, claude_coding, codex_coding, coding_router
    lines = []
    if agent_coding.available(claude_coding.PROVIDER_ID):
        models = agent_coding.claude_models()
        lines.append(f"Claude Code kurulu; kodlamada önce {models[0]}, olmazsa {', '.join(models[1:])} kullanılır.")
    else:
        lines.append("Claude Code kurulu değil. Opus düzeyinde kodlama için 'Claude Code'u kur' de "
                     "(Claude Pro/Max hesabı ya da Anthropic API anahtarı gerekir).")
    lines.append("Codex kurulu." if agent_coding.available(codex_coding.PROVIDER_ID) else "Codex kurulu değil.")
    try:
        from core import jarvis_agent
        names = [b.name for b in jarvis_agent.brains()]
        lines.append("JARVIS'in kendi kod ajanı hazır; beyinleri sırayla: " + ", ".join(names[:5]) + "."
                     if names else "JARVIS'in kendi kod ajanı için beyin yok.")
        if not jarvis_agent.deepseek_ready():
            lines.append("Kodlamayı DeepSeek yapsın diye 'DeepSeek anahtarımı ekle' de.")
    except Exception:
        pass
    resting = coding_router.status_line()
    if resting:
        lines.append(f"Şu an limitte: {resting}.")
    lines.append("Sıra: " + " → ".join(coding_router.name(p) for p in coding_router.ladder()))
    return " ".join(lines)


def _install(player) -> None:
    if sys.platform == "win32" and shutil.which("winget"):
        cmd = ["winget", "install", "-e", "--id", "Anthropic.ClaudeCode", "--accept-source-agreements",
               "--accept-package-agreements", "--silent"]
    elif shutil.which("npm"):
        cmd = ["npm", "install", "-g", "@anthropic-ai/claude-code"]
    else:
        _say(player, "Claude Code'u kuracak winget ya da npm bulunamadı; claude.com/claude-code adresinden kurulabilir.")
        return
    _say(player, "Claude Code kuruluyor… (bir iki dakika sürebilir)")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout + r.stderr).strip().splitlines()
        tail = out[-1] if out else ""
        if r.returncode == 0 or "already installed" in (r.stdout + r.stderr).lower():
            _say(player, "Claude Code kuruldu. Şimdi 'Claude'a giriş yap' de; açılan pencerede hesabınla giriş yap. "
                         "Gerekirse JARVIS'i yeniden aç.")
        else:
            _say(player, f"Claude Code kurulamadı (kod {r.returncode}): {tail[:200]}")
    except Exception as exc:
        _say(player, f"Claude Code kurulamadı: {exc}")


def _login() -> str:
    from core import claude_coding
    try:
        exe = claude_coding._executable()
    except RuntimeError as exc:
        return str(exc)
    try:
        if sys.platform == "win32":
            # a console of its own: the user signs in in the browser it opens
            subprocess.Popen(["cmd", "/c", "start", "Claude Code girişi", "cmd", "/k", exe, "auth", "login"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", exe])
        else:
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
            if not term:
                return "Bir terminal açıp 'claude auth login' yazman gerekiyor."
            subprocess.Popen([term, "--", exe, "auth", "login"])
        return ("Giriş penceresi açıldı: tarayıcıda Claude hesabınla giriş yap. Bitince JARVIS kodlamada "
                "Opus'u kullanır.")
    except Exception as exc:
        return f"Giriş penceresi açılamadı: {exc}. PowerShell'de 'claude auth login' yazabilirsin."


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        action = str(p.get("action") or "status").strip().lower()
        if action == "install":
            from core import agent_coding, claude_coding
            if agent_coding.available(claude_coding.PROVIDER_ID):
                return "Claude Code zaten kurulu. Giriş yapılmadıysa 'Claude'a giriş yap' de."
            threading.Thread(target=_install, args=(player,), daemon=True, name="claude-install").start()
            return "Claude Code'u kuruyorum; bitince haber vereceğim."
        if action == "login":
            return _login()
        if action == "deepseek":
            val = str(p.get("name") or "").strip()
            if not val:
                return "DeepSeek API anahtarı lazım (platform.deepseek.com → API Keys)."
            from memory.config_manager import get_plugin_config, save_plugin_config
            cfg = {k: v for k, v in dict(get_plugin_config("coding") or {}).items()
                   if k not in ("openrouter_key", "openrouter_models", "ollama_model", "ollama_url")}
            cfg["deepseek_key"] = val
            save_plugin_config("coding", cfg)
            return "DeepSeek eklendi: bundan sonra kodlamayı DeepSeek yapar; bakiyesi biterse Gemini devralır."
        if action == "model":
            name = str(p.get("name") or "").strip().lower()
            if not name:
                return "Hangi model? opus ya da sonnet."
            from memory.config_manager import get_plugin_config, save_plugin_config
            cfg = dict(get_plugin_config("coding") or {})
            cfg["model"] = name
            save_plugin_config("coding", cfg)
            return f"Tamam, kodlamada önce {name} kullanılacak."
        return status()
    except Exception as exc:
        return f"Kodlama kurulumuna bakamadım: {exc}"
