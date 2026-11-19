"""Everything JARVIS knows about Blender, kept on this PC:

* api   — read from the user's own Blender (every operator and its options, every
          data type, every node and its sockets): exact for that version.
* manual — the official Blender manual, downloaded once, kept as searchable text.

search() finds what a request needs; prompt() turns it into a block that goes
into every Blender script / plan / answer, so JARVIS writes correct names and
knows how a feature is meant to be used.
"""
from __future__ import annotations

import gzip
import html
import io
import json
import math
import re
import tempfile
import threading
import time
import unicodedata
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "memory" / "blender_knowledge"
API = STORE / "api.json.gz"
MANUAL = STORE / "manual.json.gz"
MANUAL_URLS = ("https://docs.blender.org/manual/en/{ver}/blender_manual_html.zip",
               "https://docs.blender.org/manual/en/latest/blender_manual_html.zip")
_cache: dict = {}
_lock = threading.Lock()
_manual_job = None


# ── building ─────────────────────────────────────────────────────────────────

def _stamp(binary) -> str:
    try:
        st = Path(binary).stat()
        return f"{binary}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        return str(binary)


def build_api(binary, invoke) -> dict:
    """Ask this Blender for its whole API (one background Blender run)."""
    with tempfile.TemporaryDirectory() as temp:
        invoke(binary, None, Path(temp), "index")
        data = json.loads((Path(temp) / "index.json").read_text(encoding="utf8"))
    data["stamp"] = _stamp(binary)
    STORE.mkdir(parents=True, exist_ok=True)
    with gzip.open(API, "wt", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    _cache.pop("api", None)
    return {"version": data["version"], "operators": len(data["operators"]), "types": len(data["types"]),
            "nodes": len(data["nodes"])}


class _Text(HTMLParser):
    """The readable text of one manual page (headings kept, navigation dropped)."""
    SKIP = {"script", "style", "nav", "footer", "header"}

    def __init__(self):
        super().__init__()
        self.parts, self.title, self._skip, self._in_title, self._main = [], "", 0, False, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP or "sidebar" in (a.get("class") or "") or a.get("role") == "navigation":
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("h1", "h2", "h3", "h4"):
            self.parts.append("\n## ")
        if tag in ("p", "li", "dt", "dd", "tr", "br", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if (tag in self.SKIP) and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def _chunks(path: str, raw: bytes, size: int = 1400) -> list[dict]:
    p = _Text()
    try:
        p.feed(raw.decode("utf8", errors="replace"))
    except Exception:
        return []
    text = re.sub(r"[ \t]+", " ", html.unescape("".join(p.parts)))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    title = re.sub(r"\s*[—–-]\s*Blender.*$", "", html.unescape(p.title)).strip()
    if len(text) < 200:
        return []
    out, buf = [], ""
    for para in text.split("\n"):
        if len(buf) + len(para) > size and buf:
            out.append({"page": path, "title": title, "text": buf.strip()})
            buf = ""
        buf += para + "\n"
    if buf.strip():
        out.append({"page": path, "title": title, "text": buf.strip()})
    return out


def build_manual(version: str = "", log=print) -> dict:
    """Download the official manual (zipped HTML, once) and keep only its text, in sections."""
    import urllib.request
    ver = ".".join(version.split(".")[:2]) if version else "latest"
    last = None
    for url in [u.format(ver=ver) for u in MANUAL_URLS]:
        for attempt in range(3):
            try:
                log(f"[Blender] Kılavuz indiriliyor: {url}")
                tmp = Path(tempfile.mkstemp(suffix=".zip")[1])
                with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                    while True:
                        block = r.read(1 << 20)
                        if not block:
                            break
                        f.write(block)
                chunks = []
                with zipfile.ZipFile(tmp) as z:
                    for name in z.namelist():
                        if not name.endswith(".html") or "/_static/" in name or name.endswith(("genindex.html", "search.html")):
                            continue
                        chunks += _chunks(name.split("/", 1)[-1], z.read(name))
                tmp.unlink(missing_ok=True)
                if len(chunks) < 200:
                    raise ValueError(f"kılavuz eksik görünüyor ({len(chunks)} bölüm)")
                STORE.mkdir(parents=True, exist_ok=True)
                with gzip.open(MANUAL, "wt", encoding="utf8") as f:
                    json.dump({"source": url, "chunks": chunks}, f, ensure_ascii=False, separators=(",", ":"))
                _cache.pop("manual", None)
                return {"source": url, "sections": len(chunks)}
            except Exception as exc:
                last = exc
                log(f"[Blender] Kılavuz indirilemedi ({attempt + 1}. deneme): {exc}")
                time.sleep(3)
    raise ValueError(f"Blender kılavuzu indirilemedi: {last}")


def ensure(binary, invoke, version: str = "", log=print) -> None:
    """The API index now (needed for every script); the manual in the background, once."""
    global _manual_job
    try:
        have = _load("api")
        if not have or have.get("stamp") != _stamp(binary):          # new install or a Blender update: re-read it
            build_api(binary, invoke)
            have = _load("api")
        version = version or str((have or {}).get("version", ""))
    except Exception as exc:
        log(f"[Blender] API dizini çıkarılamadı: {exc}")
    import os
    if os.environ.get("JARVIS_BLENDER_NO_MANUAL"):
        return
    if not MANUAL.is_file() and (_manual_job is None or not _manual_job.is_alive()):
        _manual_job = threading.Thread(target=lambda: _safe(build_manual, version, log), daemon=True)
        _manual_job.start()


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception as exc:
        print(f"[Blender] {exc}")


def status() -> str:
    api, man = _load("api"), _load("manual")
    parts = []
    if api:
        parts.append(f"Blender {api.get('version')} için {len(api['operators'])} komut, {len(api['types'])} veri türü, "
                     f"{len(api['nodes'])} düğüm biliyorum")
    if man:
        parts.append(f"resmi kılavuzdan {len(man['chunks'])} bölüm okudum")
    elif _manual_job is not None and _manual_job.is_alive():
        parts.append("kılavuzu şu an indiriyorum")
    return ("; ".join(parts) + ".") if parts else "Blender bilgi bankam henüz kurulmadı."


# ── searching ────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").replace("ı", "i").replace("İ", "i"))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")         # camelCase → words
    return [w for w in re.findall(r"[a-z0-9]{2,}", _norm(text).replace("_", " ")) if w not in _STOP]


_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "use", "used", "can", "will", "its", "into", "of",
         "to", "in", "on", "is", "be", "or", "an", "as", "by", "it", "bpy", "ops", "types"}


def _load(kind):
    with _lock:
        if kind in _cache:
            return _cache[kind]
        path = API if kind == "api" else MANUAL
        try:
            with gzip.open(path, "rt", encoding="utf8") as f:
                data = json.load(f)
        except Exception:
            return None
        docs = []
        if kind == "api":
            for o in data["operators"]:
                docs.append(("op", o, f"{o['id']} {o.get('name', '')} {o['d']} " + " ".join(p["n"] for p in o["p"])))
            for t in data["types"]:
                docs.append(("type", t, f"{t['id']} {t['d']} " + " ".join(p["n"] for p in t["p"]) + " " + " ".join(t["f"])))
            for n in data["nodes"]:
                docs.append(("node", n, f"{n['id']} {n['label']} " + " ".join(n["in"] + n["out"])))
        else:
            for c in data["chunks"]:
                docs.append(("manual", c, f"{c['title']} {c['title']} {c['page']} {c['text']}"))
        index, df = [], {}
        for kind_, obj, text in docs:
            toks = _tokens(text)
            tf = {}
            for w in toks:
                tf[w] = tf.get(w, 0) + 1
            for w in tf:
                df[w] = df.get(w, 0) + 1
            index.append((kind_, obj, tf, len(toks)))
        data["_index"], data["_df"], data["_n"] = index, df, len(index)
        _cache[kind] = data
        return data


def _rank(kind, words, k):
    data = _load(kind)
    if not data or not words:
        return []
    n, df = data["_n"], data["_df"]
    scored = []
    for kind_, obj, tf, length in data["_index"]:
        s = 0.0
        for w in words:
            f = tf.get(w)
            if f:
                idf = math.log(1 + n / df[w])
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / 60))     # BM25-ish
        if s > 0:
            ident = (obj.get("id") or obj.get("title") or "").lower()
            s *= 1.0 + 0.35 * sum(w in ident for w in words)                     # name hits count more
            scored.append((s, kind_, obj))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def keywords(request: str) -> list[str]:
    """English Blender words for a request in any language (the API and the manual are English)."""
    key = request.strip()[:300]
    if key in _cache.setdefault("kw", {}):
        return _cache["kw"][key]
    words = _tokens(request)
    try:
        from core import gemini
        got = gemini.as_json("List 8-16 English Blender keywords (feature names, operator / modifier / node / property "
                             f"words, editor names) needed to do this in Blender. Request: {request}\n"
                             'Return JSON {"keywords": [...]}', tier=gemini.FAST)
        if isinstance(got, dict):
            words = _tokens(" ".join(map(str, got.get("keywords") or []))) + words
    except Exception:
        pass
    words = list(dict.fromkeys(words))[:24]
    _cache["kw"][key] = words
    return words


def _fmt(kind, o):
    if kind == "op":
        ps = ", ".join(f"{p['n']}:{p['t']}" + (f"[{'|'.join(p['e'][:8])}]" if p.get("e") else "") for p in o["p"][:14])
        return f"{o['id']}({ps}) — {o['d'][:140]}"
    if kind == "type":
        ps = ", ".join(f"{p['n']}:{p['t']}" + (f"[{'|'.join(p['e'][:6])}]" if p.get("e") else "") +
                       (f"->{p['r']}" if p.get("r") else "") for p in o["p"][:22])
        fs = (" functions: " + ", ".join(o["f"][:10])) if o.get("f") else ""
        return f"bpy.types.{o['id']}({o.get('base') or ''}): {ps}{fs} — {o['d'][:100]}"
    if kind == "node":
        return f"node '{o['id']}' ({o['label']}, {o['tree']}): inputs {o['in'][:16]} outputs {o['out'][:8]} props {o['p'][:10]}"
    return ""


def search(request: str, k_api: int = 14, k_manual: int = 4) -> dict:
    words = keywords(request)
    return {"api": [(kd, o) for _s, kd, o in _rank("api", words, k_api)],
            "manual": [o for _s, _kd, o in _rank("manual", words, k_manual)]}


def prompt(request: str, k_api: int = 14, k_manual: int = 3) -> str:
    """The knowledge block for a Blender prompt: exact API entries of this Blender + manual excerpts."""
    try:
        found = search(request, k_api, k_manual)
    except Exception:
        return ""
    lines = []
    if found["api"]:
        api = _load("api") or {}
        lines.append(f"Exact API of the user's Blender {api.get('version', '')} (names below are authoritative):")
        lines += ["- " + _fmt(kd, o) for kd, o in found["api"]]
    if found["manual"]:
        lines.append("From the official Blender manual:")
        lines += [f"[{c['title']}] {c['text'][:900]}" for c in found["manual"]]
    return "\n".join(lines)


def answer(question: str) -> str:
    """'Blender'da X nasıl yapılır?' — from the manual and the API, in Turkish."""
    from core import gemini
    found = search(question, 10, 6)
    if not found["api"] and not found["manual"]:
        return ""
    ctx = "\n\n".join(f"[{c['title']} — docs.blender.org/manual/en/latest/{c['page']}]\n{c['text'][:1500]}"
                      for c in found["manual"])
    api = "\n".join(_fmt(kd, o) for kd, o in found["api"])
    return gemini.text(f"Answer the user's Blender question in Turkish, clearly and step by step (menus, shortcuts, "
                       f"settings). Use ONLY the manual excerpts and API below; name the manual page you used.\n\n"
                       f"Manual:\n{ctx}\n\nAPI:\n{api}\n\nQuestion: {question}", tier=gemini.SMART) or ""
