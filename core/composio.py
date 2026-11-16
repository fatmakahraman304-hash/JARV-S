"""core/composio.py — Jarvis's bridge to 1000+ apps through Composio.

Composio's Tool Router gives one session per user that can search every app
Composio supports, connect the user's account with Composio-managed login (no
OAuth app of our own to register), and run the app's actions. Jarvis uses it
through four calls:

    search(use_case)       which tools fit a task, their inputs, and whether the
                           app is connected yet
    link(toolkit)          a login page for one app; opened in the browser
    execute(slug, args)    run one tool and return its result
    toolkits(connected)    which apps exist / are connected

The free Hobby plan is enough for personal use: no card, and managed apps stop
when the monthly allowance is used instead of billing.

Settings live in config/api_keys.json under plugin_config["composio"] (via
memory/config_manager): the API key the user pastes in Settings, and a stable
user id generated once per install. Nothing here touches Qt; callers on worker
threads may block on it, and every call has a deadline.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

BASE_URL = "https://backend.composio.dev/api/v3.1"
_NS = "composio"
_TIMEOUT = 30.0

_lock = threading.Lock()
_session_id: str | None = None
_session_key: tuple | None = None
_connected_cache: tuple[float, set] = (0.0, set())


class ComposioError(RuntimeError):
    """A failure with a short, human-readable reason."""


# ── settings ──────────────────────────────────────────────────────────────────
def _cfg() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return get_plugin_config(_NS)
    except Exception:
        return {}


def api_key() -> str:
    return str(_cfg().get("api_key") or "").strip()


def is_configured() -> bool:
    return bool(api_key())


def save_api_key(key: str) -> None:
    global _session_id, _session_key
    from memory.config_manager import save_plugin_config
    save_plugin_config(_NS, {"api_key": str(key or "").strip()})
    with _lock:
        _session_id, _session_key = None, None


def user_id() -> str:
    """A stable id for this install's user, created once."""
    uid = str(_cfg().get("user_id") or "").strip()
    if not uid:
        uid = f"jarvis-{uuid.uuid4().hex[:12]}"
        try:
            from memory.config_manager import save_plugin_config
            save_plugin_config(_NS, {"user_id": uid})
        except Exception:
            pass
    return uid


# ── http ──────────────────────────────────────────────────────────────────────
def _request(method: str, path: str, *, body: dict | None = None, params: dict | None = None,
             timeout: float = _TIMEOUT) -> dict:
    key = api_key()
    if not key:
        raise ComposioError("Composio API anahtarı girilmemiş (Ayarlar → Bağlantılar → Uygulamalar)")
    import httpx
    try:
        r = httpx.request(method, BASE_URL + path, json=body, params=params, timeout=timeout,
                          headers={"x-api-key": key, "Content-Type": "application/json"})
    except httpx.TimeoutException:
        raise ComposioError("Composio zamanında yanıt vermedi") from None
    except httpx.HTTPError as exc:
        raise ComposioError(f"Composio'ya bağlanılamadı: {exc.__class__.__name__}") from None
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:300]}
    if r.status_code == 401:
        raise ComposioError("Composio API anahtarı geçersiz")
    if r.status_code == 402:
        raise ComposioError("Composio ücretsiz aylık kullanım hakkı doldu")
    if r.status_code == 429:
        raise ComposioError("Composio hız sınırı — biraz sonra tekrar dene")
    if r.status_code >= 400:
        msg = ""
        if isinstance(data, dict):
            err = data.get("error") or data.get("message") or data.get("detail") or ""
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
        raise ComposioError(f"Composio hatası {r.status_code}: {msg[:200] or 'ayrıntı yok'}")
    return data if isinstance(data, dict) else {"data": data}


def _session(fresh: bool = False) -> str:
    """The Tool Router session for this user, created on first use."""
    global _session_id, _session_key
    key = (api_key(), user_id())
    with _lock:
        if not fresh and _session_id and _session_key == key:
            return _session_id
    data = _request("POST", "/tool_router/session", body={"user_id": key[1]})
    sid = str(data.get("session_id") or "")
    if not sid:
        raise ComposioError("Composio oturumu açılamadı")
    with _lock:
        _session_id, _session_key = sid, key
    return sid


def _in_session(method: str, sub: str, **kw) -> dict:
    """Call a session endpoint; an expired session is replaced once."""
    sid = _session()
    try:
        return _request(method, f"/tool_router/session/{sid}{sub}", **kw)
    except ComposioError as exc:
        if " 404" in str(exc) or " 410" in str(exc):
            sid = _session(fresh=True)
            return _request(method, f"/tool_router/session/{sid}{sub}", **kw)
        raise


# ── the four operations ───────────────────────────────────────────────────────
def _schema_summary(schema: dict, limit: int = 12) -> str:
    props = (schema or {}).get("properties") or {}
    req = set((schema or {}).get("required") or [])
    parts = []
    for name, spec in list(props.items())[:limit]:
        typ = (spec or {}).get("type", "")
        mark = "*" if name in req else ""
        desc = str((spec or {}).get("description") or "")[:70]
        parts.append(f"{name}{mark}:{typ} {desc}".strip())
    return "; ".join(parts)


def search(use_case: str) -> dict:
    """Tools that fit a task, with their inputs and the app's connection status."""
    data = _in_session("POST", "/search", body={"queries": [{"use_case": str(use_case)[:500]}]})
    if data.get("success") is False and data.get("error"):
        raise ComposioError(str(data["error"])[:200])
    res = (data.get("results") or [{}])[0] or {}
    tools = []
    schemas = data.get("tool_schemas") or {}
    slugs = list(res.get("primary_tool_slugs") or []) + list(res.get("related_tool_slugs") or [])
    for slug in slugs[:6]:
        sc = schemas.get(slug) or {}
        tools.append({"slug": slug, "toolkit": sc.get("toolkit", ""),
                      "description": str(sc.get("description") or "")[:200],
                      "inputs": _schema_summary(sc.get("input_schema") or {})})
    conns = []
    for st in data.get("toolkit_connection_statuses") or []:
        conns.append({"toolkit": st.get("toolkit", ""),
                      "connected": bool(st.get("has_active_connection")),
                      "note": str(st.get("status_message") or "")[:160]})
    connected = {c["toolkit"].lower() for c in conns if c["connected"]}
    if connected:
        _remember_connected(connected, merge=True)
    return {"tools": tools, "connections": conns,
            "guidance": str(res.get("execution_guidance") or "")[:600],
            "pitfalls": [str(p)[:160] for p in (res.get("known_pitfalls") or [])[:3]]}


def link(toolkit: str) -> str:
    """A login page URL that connects the user's account for one app."""
    data = _in_session("POST", "/link", body={"toolkit": str(toolkit).strip().lower()})
    url = str(data.get("redirect_url") or "")
    if not url:
        raise ComposioError("Composio bağlantı sayfası vermedi")
    return url


def execute(tool_slug: str, arguments: dict | None = None) -> dict:
    """Run one tool. Returns {'ok': bool, 'data': ..., 'error': str}."""
    data = _in_session("POST", "/execute",
                       body={"tool_slug": str(tool_slug).strip(), "arguments": arguments or {}},
                       timeout=60.0)
    err = data.get("error")
    ok = not err and str(data.get("result_type") or "completed") != "error"
    return {"ok": bool(ok), "data": data.get("data"), "error": str(err or "")[:400],
            "result_type": data.get("result_type", "")}


def toolkits(connected_only: bool = False, search_text: str = "", limit: int = 50) -> list[dict]:
    params = {"limit": max(1, min(50, int(limit)))}
    if connected_only:
        params["is_connected"] = "true"
    if search_text:
        params["search"] = search_text
    data = _in_session("GET", "/toolkits", params=params)
    out = []
    for it in data.get("items") or []:
        ca = it.get("connected_account") or {}
        out.append({"slug": str(it.get("slug") or ""), "name": str(it.get("name") or ""),
                    "connected": bool(ca) and str(ca.get("status") or "ACTIVE").upper() == "ACTIVE"})
    if connected_only or not search_text:
        _remember_connected({t["slug"].lower() for t in out if t["connected"]})
    return out


# ── connection cache for the Control Centre ───────────────────────────────────
def _remember_connected(slugs: set, merge: bool = False) -> None:
    global _connected_cache
    with _lock:
        cur = set(_connected_cache[1]) if merge else set()
        _connected_cache = (time.time(), cur | set(slugs))
    try:
        from core import activity
        activity.set_connected(_connected_cache[1])
    except Exception:
        pass


def refresh_connections() -> set:
    """Ask Composio which apps are connected. Never raises; returns the set."""
    if not is_configured():
        return set()
    try:
        toolkits(connected_only=True)
    except Exception:
        pass
    with _lock:
        return set(_connected_cache[1])


def compact(value, limit: int = 3000) -> str:
    """A tool result as text short enough for the voice model."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[:limit] + " …(kısaltıldı)"
