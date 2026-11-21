"""MAYK'ın kendi kodlama ajanı: DeepSeek V4 Pro → Flash → Gemini.

Dosyaları analiz eder, düzenler ve test eder. Kod değişiklikleri proje klasöründe
kalır; API anahtarları aracıya, günlük dosyalarına veya model istemine verilmez.
DeepSeek bakiyesi ya da kota sınırı dolarsa sıradaki uygun modele geçilir.
"""

from __future__ import annotations

import fnmatch
import html
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVIDER_ID = "jarvis_agent"
MAX_STEPS = 90
MAX_OUTPUT = 8000
MAX_READ_LINES = 500
CONTEXT_BUDGET = 350_000          # characters of history kept before old tool output is shortened
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"

# Commands the agent may run: building, running and testing code.
RUN_ALLOWED = (
    "python", "python3", "py", "pytest", "pip install", "pip3 install", "pip show", "pip list", "uv",
    "node", "npm", "npx", "yarn", "pnpm", "bun", "deno", "tsc", "eslint", "prettier",
    "go ", "cargo", "rustc", "dotnet", "mvn", "gradle", "java", "javac", "gcc", "g++", "clang", "cmake", "make",
    "php", "composer", "ruby", "bundle", "flutter", "dart", "ruff", "black", "mypy",
    "git status", "git diff", "git log", "ls", "dir", "cat", "type", "head", "tail", "wc", "echo", "mkdir",
    "where", "which", "find", "grep",
)
RUN_FORBIDDEN = re.compile(r"\b(rm|rmdir|del|erase|rd|format|shutdown|reboot|mkfs|dd|chmod|chown|curl|wget|"
                           r"powershell|pwsh|reg|sudo|su)\b|git\s+(commit|push|reset|checkout|clean|rebase)|"
                           r">\s*/dev/|\bnpm\s+(publish|login)\b", re.I)
_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build", ".next",
              ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".jarvis_backup"}

SYSTEM = (
    "Sen MAYK'ın kodlama ajanısın. Yalnızca verilen proje klasöründe çalışırsın. "
    "Deneyimli bir yazılım mühendisi gibi eksiksiz ve doğrulanmış çözüm üret. "
    "Kullanıcı Türkçe konuşuyorsa yanıtların, günlük açıklamaların ve özetlerin Türkçe olsun.\n"
    "1. Önce incele: list_files, search ve read_file ile mevcut yapıyı anla; tekrar kullanılabilecek kodu bul.\n"
    "2. Gerekli adımları planla ve sırayla uygula.\n"
    "3. Gerçek işlevleri tamamla. Sahte veri, boş fonksiyon veya TODO bırakma. "
    "Web uygulamasında gerçek içerik, duyarlı tasarım ve çalışan bağlantılar kullan.\n"
    "4. Mevcut dosyalarda küçük ve tam edit_file değişiklikleri yap; yeni dosyalar için "
    "write_file kullan. API anahtarlarına, şifrelere, yerel ayarlara dokunma ve kullanıcı verisini silme.\n"
    "5. run ile testleri veya uygulamayı çalıştır; hataları okuyup düzelt. İşini bitirmeden bir kez daha kontrol et.\n"
    "6. Bittiğinde finish aracını çağır; ne yaptığını ve nasıl doğruladığını "
    "Türkçe 3–5 cümlede açıkla. Sadece açıklama yaparak işi bitirmiş sayma.\n"
    "Yalnızca tanımlanmış araçları çağır; dosya yolları proje klasörüne göreli olmalıdır."
)

TOOLS = [
    {"name": "list_files", "description": "Dosya ve klasörleri listele (.git, venv ve node_modules hariç).",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Göreli klasör yolu; varsayılan '.'"},
         "depth": {"type": "integer", "description": "Arama derinliği: 1–4, varsayılan 2"}}}},
    {"name": "read_file", "description": "Bir metin dosyasını satır numaralarıyla oku (en fazla 500 satır).",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
         "required": ["path"]}},
    {"name": "search", "description": "Projede düzenli ifadeyle metin ara.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "glob": {"type": "string", "description": "Örn. *.py; varsayılan: tümü"}},
         "required": ["pattern"]}},
    {"name": "write_file", "description": "Yeni dosya oluştur veya tüm içeriğini değiştir.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Dosyada belirtilen metni birebir değiştir. Eski metin, replace_all kullanılmadığında "
                                         "yalnızca bir kez bulunmalıdır; yeterli bağlam belirt.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
         "replace_all": {"type": "boolean"}}, "required": ["path", "old", "new"]}},
    {"name": "run", "description": "Proje klasöründe derleme, çalıştırma veya test komutu uygula (python, "
                                   "pytest, npm, node, go, cargo vb.). Çıkış kodunu ve sonucu döndürür.",
     "parameters": {"type": "object", "properties": {
         "command": {"type": "string"}, "timeout": {"type": "integer", "description": "Saniye cinsinden süre; varsayılan 120"}},
         "required": ["command"]}},
    {"name": "fetch_url", "description": "Bir dokümantasyon sayfasını metin olarak oku.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "finish", "description": "İş tamamlandı ve doğrulandı: sonucu Türkçe özetle.",
     "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}},
]


class BrainError(RuntimeError):
    """This brain cannot go on (limit, no access, down): try the next one."""


# ── tools ────────────────────────────────────────────────────────────────────

class Workspace:
    def __init__(self, folder: Path, log=print):
        self.root = Path(folder).resolve()
        self.log = log
        self.changed: set[str] = set()

    def _path(self, rel: str) -> Path:
        p = (self.root / str(rel or ".").strip().lstrip("/\\")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError("Proje klasörünün dışına çıkılamaz.")
        return p

    def call(self, name: str, args: dict) -> str:
        try:
            fn = getattr(self, "t_" + name, None)
            if fn is None:
                return f"Bilinmeyen araç: {name}."
            return fn(**{k: v for k, v in (args or {}).items() if v is not None})
        except TypeError as exc:
            return f"{name} için geçersiz parametreler: {exc}"
        except Exception as exc:
            return f"Hata: {type(exc).__name__}: {exc}"

    def t_list_files(self, path=".", depth=2):
        base = self._path(path)
        depth = max(1, min(4, int(depth or 2)))
        out = []
        for root, dirs, files in os.walk(base):
            rel = Path(root).relative_to(base)
            if len(rel.parts) >= depth:
                dirs[:] = []
            dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".jarvis"))
            for d in dirs:
                out.append(str((rel / d).as_posix()) + "/")
            for f in sorted(files):
                fp = Path(root) / f
                try:
                    size = fp.stat().st_size
                except OSError:
                    size = 0
                out.append(f"{(rel / f).as_posix()}  ({size} B)")
            if len(out) > 600:
                out.append("… (more)")
                break
        return "\n".join(out) or "(empty folder)"

    def t_read_file(self, path, start_line=1, end_line=None):
        p = self._path(path)
        if not p.is_file():
            return f"Dosya bulunamadı: {path}"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        s = max(1, int(start_line or 1))
        e = min(len(lines), int(end_line or s + MAX_READ_LINES - 1), s + MAX_READ_LINES - 1)
        body = "\n".join(f"{i:5}| {lines[i - 1]}" for i in range(s, e + 1))
        more = f"\n… {len(lines) - e} more lines (read with start_line={e + 1})" if e < len(lines) else ""
        return f"{path} (lines {s}-{e} of {len(lines)})\n{body}{more}"

    def t_search(self, pattern, glob="*"):
        rx = re.compile(pattern, re.I)
        hits = []
        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".jarvis")]
            for f in files:
                if not fnmatch.fnmatch(f, glob or "*"):
                    continue
                fp = Path(root) / f
                try:
                    if fp.stat().st_size > 1_500_000:
                        continue
                    text = fp.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{fp.relative_to(self.root).as_posix()}:{n}: {line.strip()[:200]}")
                        if len(hits) >= 80:
                            return "\n".join(hits) + "\n… (more hits)"
        return "\n".join(hits) or "Eşleşme bulunamadı."

    def t_write_file(self, path, content):
        p = self._path(path)
        if p.name.lower() in (".env", "api_keys.json", "credentials.json"):
            return "Reddedildi: bu dosyada gizli bilgiler var."
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
        self.changed.add(p.relative_to(self.root).as_posix())
        self.log(f"  Yazdı: {p.relative_to(self.root).as_posix()}")
        return f"{path} yazıldı ({len(str(content))} karakter)."

    def t_edit_file(self, path, old, new, replace_all=False):
        p = self._path(path)
        if not p.is_file():
            return f"Dosya bulunamadı: {path}"
        text = p.read_text(encoding="utf-8", errors="replace")
        n = text.count(old) if old else 0
        if n == 0:
            return "Eski metin bulunamadı. Dosyayı yeniden okuyup tam metni kullanın."
        if n > 1 and not replace_all:
            return f"`old` appears {n} times; add more surrounding text or set replace_all."
        p.write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1), encoding="utf-8")
        self.changed.add(p.relative_to(self.root).as_posix())
        self.log(f"  Düzenledi: {p.relative_to(self.root).as_posix()}")
        return f"{path} düzenlendi ({n if replace_all else 1} değiştirme)."

    @staticmethod
    def allowed(command: str) -> bool:
        cmd = str(command or "").strip()
        if not cmd or RUN_FORBIDDEN.search(cmd):
            return False
        for part in re.split(r"&&|\|\||;|\|", cmd):
            part = part.strip()
            if part and not any(part.lower().startswith(a) for a in RUN_ALLOWED):
                return False
        return True

    def t_run(self, command, timeout=120):
        if not self.allowed(command):
            return ( "Reddedildi: yalnızca derleme, çalıştırma ve test komutlarına izin verilir "
                    "(no deleting, no git commit/push, no downloads).")
        self.log(f"  Çalıştırıyor: {str(command)[:140]}")
        try:
            r = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                               timeout=max(5, min(600, int(timeout or 120))), encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL,
                               # a file fixed within the same second must not run from a stale .pyc
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = (r.stdout or "") + ("\n[stderr]\n" + r.stderr if r.stderr else "")
            if len(out) > MAX_OUTPUT:
                out = out[:MAX_OUTPUT // 2] + "\n… (cut) …\n" + out[-MAX_OUTPUT // 2:]
            return f"exit code {r.returncode}\n{out}"
        except subprocess.TimeoutExpired:
            return "Süre sınırı doldu. Sürekli çalışan sunucu veya programsa yeniden açmayın; başka yöntemle test edin."

    def t_fetch_url(self, url):
        if not str(url).startswith(("http://", "https://")):
            return "Yalnızca web adresleri kabul edilir."
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MAYK"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(600_000).decode("utf-8", errors="replace")
        text = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        return re.sub(r"\s+", " ", text).strip()[:15000]


# ── brains ───────────────────────────────────────────────────────────────────

def _http_json(url: str, body: dict | None, headers: dict, timeout: int = 180) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", **headers})
    ctx = None
    try:
        from core import tls
        ctx = tls.context()
    except Exception:
        ctx = None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            msg = ""
        raise BrainError(f"{e.code} {msg}") from None
    except Exception as exc:
        raise BrainError(str(exc)[:300]) from None


def _retry_after(err: str) -> float:
    m = re.search(r"retry in ([\d.]+)s|retryDelay\"?:\s*\"?(\d+)", err)
    if m:
        return float(m.group(1) or m.group(2))
    return 0.0


def _gemini_schema(schema):
    """Gemini's REST API spells the types in capitals (OBJECT, STRING …)."""
    if isinstance(schema, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) else _gemini_schema(v)) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_gemini_schema(x) for x in schema]
    return schema


class GeminiBrain:
    """Gemini through its REST API with function calling. Keeps the model's
    own parts (with their thought signatures) to send back unchanged."""

    def __init__(self, key: str, model: str):
        self.key, self.model = key, model
        self.name = f"Gemini ({model})"

    def turn(self, history: list[dict]) -> tuple[str, list[dict], object]:
        contents, pending = [], []
        for h in history:
            if h["role"] == "tool":
                pending.append({"functionResponse": {"name": h["name"], "response": {"result": h["result"]}}})
                continue
            if pending:
                contents.append({"role": "user", "parts": pending})
                pending = []
            if h["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": h["text"]}]})
            elif h.get("raw_gemini"):
                contents.append({"role": "model", "parts": h["raw_gemini"]})
            else:
                parts = ([{"text": h["text"]}] if h.get("text") else []) + \
                        [{"functionCall": {"name": c["name"], "args": c["args"]}} for c in h.get("calls", [])]
                contents.append({"role": "model", "parts": parts or [{"text": "…"}]})
        if pending:
            contents.append({"role": "user", "parts": pending})
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                "tools": [{"functionDeclarations": [
                    {"name": t["name"], "description": t["description"], "parameters": _gemini_schema(t["parameters"])}
                    for t in TOOLS]}],
                "generationConfig": {"temperature": 0.2}}
        js = _http_json(f"{GEMINI_API}/models/{self.model}:generateContent", body, {"x-goog-api-key": self.key})
        cand = (js.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if p.get("text") and not p.get("thought"))
        calls = [{"id": f"c{i}", "name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}}
                 for i, p in enumerate(parts) if p.get("functionCall")]
        if not parts and cand.get("finishReason") not in (None, "STOP"):
            raise BrainError(f"model stopped: {cand.get('finishReason')}")
        return text, calls, parts


class OpenAIBrain:
    """An OpenAI-compatible chat API with tools (DeepSeek)."""

    def __init__(self, base_url: str, key: str, model: str, label: str):
        self.base, self.key, self.model = base_url.rstrip("/"), key, model
        self.name = f"{label} ({model})"

    def turn(self, history: list[dict]) -> tuple[str, list[dict], object]:
        msgs = [{"role": "system", "content": SYSTEM}]
        for h in history:
            if h["role"] == "user":
                msgs.append({"role": "user", "content": h["text"]})
            elif h["role"] == "tool":
                msgs.append({"role": "tool", "tool_call_id": h["id"], "content": h["result"]})
            else:
                m = {"role": "assistant", "content": h.get("text") or ""}
                if h.get("calls"):
                    m["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c["args"])}}
                                       for c in h["calls"]]
                msgs.append(m)
        body = {"model": self.model, "messages": msgs, "temperature": 0.2,
                "tools": [{"type": "function", "function": t} for t in TOOLS]}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        js = _http_json(f"{self.base}/chat/completions", body, headers, timeout=300)
        if js.get("error"):
            raise BrainError(str(js["error"])[:300])
        msg = ((js.get("choices") or [{}])[0].get("message")) or {}
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append({"id": c.get("id") or f"c{i}", "name": fn.get("name", ""), "args": args})
        return msg.get("content") or "", calls, None


# ── which brains are there, best first ───────────────────────────────────────

def _settings() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return dict(get_plugin_config("coding") or {})
    except Exception:
        return {}


def _gemini_key() -> str:
    try:
        from core import gemini
        return gemini.api_key() or ""
    except Exception:
        return ""


def _version(name: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def rank_gemini(names: list[str]) -> list[str]:
    """Text models that can code, best first: Pro before Flash before
    Flash-Lite, newer before older, stable before preview."""
    bad = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use", "aqa",
           "learnlm", "gemma", "exp-", "thinking", "omni")
    keep = [n for n in names if n.startswith("gemini-") and not any(b in n for b in bad)]

    def tier(n):
        return 0 if "-pro" in n else 2 if "lite" in n else 1
    return sorted(dict.fromkeys(keep), key=lambda n: (tier(n), -_version(n), "preview" in n, len(n)))


_gemini_cache: dict = {"at": 0.0, "models": []}


def gemini_models(key: str) -> list[str]:
    if _gemini_cache["models"] and time.time() - _gemini_cache["at"] < 6 * 3600:
        return _gemini_cache["models"]
    names = []
    try:
        js = _http_json(f"{GEMINI_API}/models?pageSize=200", None, {"x-goog-api-key": key}, timeout=20)
        for m in js.get("models") or []:
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                names.append(str(m.get("name", "")).replace("models/", ""))
    except BrainError:
        names = []
    ranked = rank_gemini(names) or ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"]
    _gemini_cache.update(at=time.time(), models=ranked[:6])
    return _gemini_cache["models"]


def deepseek_models() -> list[str]:
    """Önce güçlü V4 Pro, ardından hızlı/ekonomik Flash.

    Eski model takma adları yeni API'de kaldırıldığı için otomatik dönüştürülür.
    """
    cfg = _settings()
    requested = cfg.get("deepseek_models")
    if isinstance(requested, str):
        requested = [requested]
    aliases = {"deepseek-chat": "deepseek-flash",
               "deepseek-reasoner": "deepseek-v4-pro",
               "deepseek-v4-flash": "deepseek-flash"}
    models = requested if isinstance(requested, (list, tuple)) and requested else [
        "deepseek-v4-pro", "deepseek-flash"]
    models = [aliases.get(str(m).strip(), str(m).strip()) for m in models]
    return list(dict.fromkeys(m for m in models if m))


def brains() -> list:
    """Kullanılabilir kodlama modelleri: DeepSeek → Gemini."""
    from core import deepseek_account
    cfg = _settings()
    out = []
    key = deepseek_account.api_key()
    if key:
        info = deepseek_account.balance_status(key)
        # Bakiye kesin olarak yetersizse DeepSeek'e gereksiz istek yapma.
        # Ağ hatasını asla 'bakiye bitti' diye yorumlama.
        if info["available"] is not False:
            out.extend(OpenAIBrain("https://api.deepseek.com", key, m, "DeepSeek")
                       for m in deepseek_models())
    gemini_key = _gemini_key()
    if gemini_key and cfg.get("use_gemini", True) is not False:
        out.extend(GeminiBrain(gemini_key, m) for m in gemini_models(gemini_key))
    return out


def available() -> bool:
    from core import deepseek_account
    return bool(deepseek_account.api_key() or _gemini_key())


def deepseek_ready() -> bool:
    from core import deepseek_account
    return bool(deepseek_account.api_key())


# ── the loop ─────────────────────────────────────────────────────────────────

def _shrink(history: list[dict]) -> None:
    """Keep the conversation within budget: old tool output is cut first."""
    total = sum(len(json.dumps(h, ensure_ascii=False, default=str)) for h in history)
    for h in history[1:-12]:
        if total <= CONTEXT_BUDGET:
            break
        if h["role"] == "tool" and len(h["result"]) > 600:
            total -= len(h["result"]) - 300
            h["result"] = h["result"][:300] + "\n… (older output shortened)"


def run(folder: Path, task: str, log=print, brain_list: list | None = None, max_steps: int = MAX_STEPS) -> str:
    """Do `task` in `folder`. Returns the agent's Turkish summary."""
    ws = Workspace(folder, log)
    pool = list(brain_list if brain_list is not None else brains())
    if not pool:
        raise RuntimeError("MAYK'ın kod ajanı için beyin yok: DeepSeek ya da Gemini anahtarı gerekiyor.")
    history: list[dict] = [{"role": "user", "text": task}]
    brain = pool.pop(0)
    log(f"  MAYK ajanı: {brain.name}")
    idle = 0
    for step in range(max_steps):
        _shrink(history)
        try:
            text, calls, raw = brain.turn(history)
        except BrainError as e:
            err = str(e)
            # 402 aynı hesap bakiyesidir; Flash denemek de işe yaramaz.
            if (isinstance(brain, OpenAIBrain) and brain.name.startswith("DeepSeek")
                    and ("402" in err or "insufficient balance" in err.casefold())):
                pool = [b for b in pool if not (
                    isinstance(b, OpenAIBrain) and b.name.startswith("DeepSeek"))]
            wait = _retry_after(err)
            if "429" in err and 0 < wait <= 60 and "limit: 0" not in err:
                log(f"  {brain.name} dakikalık sınırda; {int(wait) + 1} sn bekliyor.")
                time.sleep(wait + 1)
                continue
            if not pool:
                raise RuntimeError(f"Kod ajanının bütün beyinleri sınırda ya da ulaşılamıyor: {err[:200]}")
            # a model change mid-job: the new brain sees the same history, minus
            # the old model's private parts
            for h in history:
                h.pop("raw_gemini", None)
            brain = pool.pop(0)
            log(f"  Önceki model kullanılamadı ({err[:80]}); {brain.name} ile devam.")
            continue
        item = {"role": "assistant", "text": text, "calls": calls}
        if isinstance(brain, GeminiBrain) and raw:
            item["raw_gemini"] = raw
        history.append(item)
        if not calls:
            idle += 1
            if idle >= 2:
                # answered in words without tools: take it as the summary
                return text.strip() or "İş bitti."
            history.append({"role": "user", "text": "Araçları kullanarak işi tamamla; ardından finish çağır."})
            continue
        idle = 0
        for c in calls:
            if c["name"] == "finish":
                summary = str((c.get("args") or {}).get("summary") or text or "İş bitti.").strip()
                return summary
            result = ws.call(c["name"], c.get("args") or {})
            history.append({"role": "tool", "id": c["id"], "name": c["name"], "result": result})
    return ("Kod ajanı adım sınırına ulaştı; yapılanlar kaydedildi: "
            + (", ".join(sorted(ws.changed)[:12]) or "hiçbir dosya değişmedi") + ".")
