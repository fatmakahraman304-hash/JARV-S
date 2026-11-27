"""core/tasks/brain.py — one round of a tool-calling model.

The engine drives the loop; this answers one question: given the conversation
so far and the tools on offer, what does the model say or call next?

It walks the same Gemini ladder and cooldowns as core/gemini.py, with one
difference. gemini.call() leads with a Live rung and can fall to a provider
through a path that passes no tools — right for one-shot calls, wrong here,
where a turn landing on either would come back as prose describing a call.
So this uses the ladder's REST models, and makes the configured provider a
real tool-calling rung.

Turns are stored vendor-neutral, so a task that began on Gemini can continue on
a fallback provider, and survives a restart:

    {"role": "user",  "text"}
    {"role": "model", "text", "calls": [{id, name, args, sig}]}
    {"role": "tool",  "results": [{id, name, result}]}

Gemini 3 attaches a thought signature to every function call and rejects the
next request without it, so signatures are kept with the history; a model that
rejects another model's signatures after a fallback is asked again without them.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time


class NoModel(RuntimeError):
    """Nothing answered. `transient` means waiting is likely to help: quota,
    an overloaded model, a dropped connection — as opposed to no key at all."""

    def __init__(self, message: str, transient: bool):
        super().__init__(message)
        self.transient = transient


_NETWORK_HINTS = ("connecterror", "connection", "timed out", "timeout", "getaddrinfo",
                  "temporarily", "network", "unreachable", "reset by peer")


def _is_network(msg: str) -> bool:
    low = msg.lower()
    return any(h in low for h in _NETWORK_HINTS)


_catalog_lock = threading.Lock()
_catalog = {"key": "", "at": 0.0, "models": None}


def _fetch_catalog(key, params, timeout):
    from urllib.parse import urlencode
    from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
    from core import tls

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # never forward a credential to a redirect destination

    url = "https://generativelanguage.googleapis.com/v1beta/models?" + urlencode(params)
    request = Request(url, headers={"x-goog-api-key": key, "Accept": "application/json"})
    opener = build_opener(NoRedirect(), HTTPSHandler(context=tls.context()))
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("model catalog exceeds limit")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid model catalog")
    return data


def _accessible_gemini(key: str):
    """Discover this credential's text models; None means discovery failed.

    Cache by a one-way key digest. Do not persist credentials, prompts, or
    provider error messages. A list entry establishes availability, not quality
    or a guarantee that a particular tool call will succeed.
    """
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _catalog_lock:
        if _catalog["key"] == digest and now - _catalog["at"] < (600 if _catalog["models"] is not None else 30):
            cached = _catalog["models"]
            return None if cached is None else set(cached)
        try:
            token = ""
            names = set()
            deadline = time.monotonic() + 12
            for _ in range(5):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("model discovery deadline")
                params = {"pageSize": 200}
                if token:
                    params["pageToken"] = token
                data = _fetch_catalog(key, params, timeout=min(10, remaining))
                if not isinstance(data.get("models"), list):
                    raise ValueError("invalid model catalog")
                for entry in data["models"]:
                    if not isinstance(entry, dict) or "generateContent" not in (entry.get("supportedGenerationMethods") or []):
                        continue
                    name = str(entry.get("name") or "")
                    if name.startswith("models/"):
                        names.add(name[len("models/"):])
                token = data.get("nextPageToken") or ""
                if not isinstance(token, str) or len(token) > 1024:
                    raise ValueError("invalid model page token")
                if not token:
                    break
            _catalog.update(key=digest, at=time.monotonic(), models=names)
            return set(names)
        except Exception:
            _catalog.update(key=digest, at=time.monotonic(), models=None)
            return None


def to_gemini(turns: list, signatures: bool = True) -> list:
    from google.genai import types

    out = []
    for t in turns:
        if t["role"] == "user":
            out.append(types.Content(role="user", parts=[types.Part(text=t.get("text") or "")]))
        elif t["role"] == "model":
            parts = [types.Part(text=t["text"])] if t.get("text") else []
            for c in t.get("calls") or []:
                kw = {"function_call": types.FunctionCall(name=c["name"], args=c.get("args") or {})}
                if signatures and c.get("sig"):
                    kw["thought_signature"] = base64.b64decode(c["sig"])
                parts.append(types.Part(**kw))
            if parts:
                out.append(types.Content(role="model", parts=parts))
        elif t["role"] == "tool":
            out.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=r["name"], response={"result": r["result"]})
                for r in t["results"]]))
    return out


def to_openai(turns: list, system: str) -> list:
    msgs = [{"role": "system", "content": system}]
    for t in turns:
        if t["role"] == "user":
            msgs.append({"role": "user", "content": t.get("text") or ""})
        elif t["role"] == "model":
            m = {"role": "assistant", "content": t.get("text") or None}
            if t.get("calls"):
                m["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                    "name": c["name"], "arguments": json.dumps(c.get("args") or {})}}
                    for c in t["calls"]]
            msgs.append(m)
        elif t["role"] == "tool":
            msgs += [{"role": "tool", "tool_call_id": r["id"], "name": r["name"],
                      "content": str(r["result"])} for r in t["results"]]
    return msgs


def _ask_gemini(model: str, system: str, turns: list, decls) -> dict:
    from google.genai import types

    from core import gemini

    cfg = {"system_instruction": system,
           "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True)}
    if decls:
        cfg["tools"] = [{"function_declarations": decls}]
    client = gemini.client(timeout_ms=120_000)
    try:
        resp = client.models.generate_content(model=model, contents=to_gemini(turns),
                                              config=types.GenerateContentConfig(**cfg))
    except Exception as e:
        if "signature" not in str(e).lower():
            raise
        resp = client.models.generate_content(model=model, contents=to_gemini(turns, signatures=False),
                                              config=types.GenerateContentConfig(**cfg))
    cand = (resp.candidates or [None])[0]
    text, calls = [], []
    for part in (getattr(getattr(cand, "content", None), "parts", None) or []):
        if getattr(part, "thought", False):
            continue
        fc = getattr(part, "function_call", None)
        if fc is not None and fc.name:
            sig = getattr(part, "thought_signature", None)
            calls.append({"id": fc.id or f"call_{len(calls)}_{int(time.time() * 1000)}",
                          "name": fc.name, "args": dict(fc.args or {}),
                          "sig": base64.b64encode(sig).decode("ascii") if sig else ""})
        elif getattr(part, "text", None):
            text.append(part.text)
    if not text and not calls:
        raise RuntimeError(f"empty answer ({getattr(cand, 'finish_reason', 'no candidate')})")
    return {"text": "".join(text).strip(), "calls": calls}


def _ask_provider(model: str, system: str, turns: list, decls) -> dict:
    from core import gemini
    from memory.config_manager import get_provider_config
    from providers import registry, schema

    pid = model[len(gemini.PROVIDER_PREFIX):]
    llm = registry.build(pid, get_provider_config(pid))
    text, calls = llm.complete(to_openai(turns, system),
                               tools=schema.to_openai(decls) if decls else None, timeout=120)
    if not str(text or "").strip() and not calls:
        raise RuntimeError("the provider returned an empty response")
    return {"text": (text or "").strip(),
            "calls": [{"id": c.id or f"call_{i}", "name": c.name, "args": dict(c.args or {}), "sig": ""}
                      for i, c in enumerate(calls or [])]}


def ask(system: str, turns: list, decls: list | None, *, tier: str = "smart",
        verified_models: bool = False) -> dict:
    """One model turn: {"text": str, "calls": [...]}. Raises NoModel."""
    from core import gemini
    from core.action_loader import strip_meta

    if tier not in (gemini.FAST, gemini.SMART):
        raise ValueError("unsupported background model tier")
    decls = strip_meta(decls) if decls else None
    discovery_failed = False
    listed_models = False
    key = gemini.api_key()
    provider = list(gemini._provider_rungs(tier))
    provider_first = bool(provider and gemini._provider_first())

    def candidates():
        nonlocal discovery_failed, listed_models
        # Honor the user's preferred provider without paying for model catalog
        # discovery unless that provider actually fails.
        if provider_first:
            yield from provider
        if key:
            ladder = [m for m in gemini._LADDERS[tier]
                      if m != gemini.LIVE and not m.startswith(gemini.PROVIDER_PREFIX)]
            if verified_models:
                accessible = _accessible_gemini(key)
                discovery_failed = accessible is None
                ladder = [model for model in ladder if accessible is not None and model in accessible]
            listed_models = bool(ladder)
            yield from gemini.usable_rungs(ladder)
        if not provider_first:
            yield from provider

    errors, transient = [], False
    for model in candidates():
        try:
            if model.startswith(gemini.PROVIDER_PREFIX):
                return _ask_provider(model, system, turns, decls)
            return _ask_gemini(model, system, turns, decls)
        except Exception as e:
            msg = str(e)
            errors.append(f"{model}: {msg[:120]}")
            if gemini.is_quota_error(msg):
                gemini._cool(model)
                transient = True
            elif gemini.is_gone_error(msg):
                gemini._cool(model, gemini._GONE_SECONDS)
            elif gemini.is_unavailable_error(msg):
                gemini._cool(model, gemini._UNAVAILABLE_SECONDS)
                transient = True
            elif _is_network(msg):
                transient = True
            print(f"[Tasks] {model} failed: {msg[:160]}")
    if verified_models and key and not listed_models:
        transient = True
        errors.append("Gemini model availability could not be checked" if discovery_failed
                      else "no configured Gemini model was listed as available")
    if not errors:
        raise NoModel("no Gemini key and no provider configured", transient=False)
    raise NoModel("no model answered — " + "; ".join(errors[-3:]), transient=transient)
