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
_header: str = "x-api-key"     # becomes x-org-api-key if the key turns out to be an org token

KEY_HELP = ("composio.dev → Settings → Sessions & API Key bölümündeki ck_ anahtarını ya da "
            "geliştirici panelinde Project Settings → API Keys'teki ak_ anahtarını kopyala")


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
    global _session_id, _session_key, _header
    from memory.config_manager import save_plugin_config
    # People paste keys with quotes, a "Bearer " prefix or a trailing newline.
    key = str(key or "").strip().strip('"').strip("'").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    save_plugin_config(_NS, {"api_key": key})
    global _mcp
    with _lock:
        _session_id, _session_key, _header = None, None, "x-api-key"
        _mcp = None


def check() -> tuple[bool, str]:
    """Try the key by opening a session. (ok, short message). Never raises."""
    if not is_configured():
        return False, "Anahtar girilmemiş"
    try:
        if is_consumer():
            names = _c(lambda cc, cl: cl.tools())
            if "COMPOSIO_SEARCH_TOOLS" not in names:
                return False, "Composio Connect açıldı ama uygulama araçları listelenmedi"
            refresh_connections()
            return True, "Bağlantı başarılı (Composio Connect)"
        _session(fresh=True)
        refresh_connections()
        return True, "Bağlantı başarılı"
    except ComposioError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Beklenmeyen hata: {exc}"[:200]


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
def _server_message(data) -> str:
    if not isinstance(data, dict):
        return ""
    err = data.get("error") or data.get("message") or data.get("detail") or ""
    if isinstance(err, dict):
        err = err.get("message") or err.get("detail") or ""
    return str(err or "")[:200]


def _send(method, path, key, header, body, params, timeout):
    import httpx
    try:
        r = httpx.request(method, BASE_URL + path, json=body, params=params, timeout=timeout,
                          headers={header: key, "Content-Type": "application/json"})
    except httpx.TimeoutException:
        raise ComposioError("Composio zamanında yanıt vermedi") from None
    except httpx.HTTPError as exc:
        raise ComposioError(f"Composio'ya bağlanılamadı: {exc.__class__.__name__}") from None
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:300]}
    return r, data


def _request(method: str, path: str, *, body: dict | None = None, params: dict | None = None,
             timeout: float = _TIMEOUT) -> dict:
    global _header
    key = api_key()
    if not key:
        raise ComposioError("Composio API anahtarı girilmemiş (Ayarlar → Bağlantılar → Uygulamalar)")
    if key.startswith("uak_"):
        # a CLI user key; Composio rejects it in x-api-key
        raise ComposioError(f"Bu bir kullanıcı anahtarı (uak_), proje anahtarı değil — {KEY_HELP}")
    r, data = _send(method, path, key, _header, body, params, timeout)
    if r.status_code == 401 and _header == "x-api-key" and not key.startswith("ak_"):
        # not a project key — perhaps an organization access token
        r2, data2 = _send(method, path, key, "x-org-api-key", body, params, timeout)
        if r2.status_code != 401:
            _header = "x-org-api-key"
            r, data = r2, data2
    if r.status_code == 401:
        why = _server_message(data)
        raise ComposioError("Composio API anahtarını kabul etmedi"
                            + (f" ({why})" if why else "") + f" — {KEY_HELP}")
    if r.status_code == 402:
        raise ComposioError("Composio ücretsiz aylık kullanım hakkı doldu")
    if r.status_code == 429:
        raise ComposioError("Composio hız sınırı — biraz sonra tekrar dene")
    if r.status_code >= 400:
        msg = _server_message(data)
        raise ComposioError(f"Composio hatası {r.status_code}: {msg or 'ayrıntı yok'}")
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


def _parse_search(data) -> dict:
    if not isinstance(data, dict):
        raise ComposioError(f"Composio araması beklenmeyen yanıt verdi: {str(data)[:160]}")
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


def _p_search(use_case: str) -> dict:
    return _parse_search(_in_session("POST", "/search",
                                     body={"queries": [{"use_case": str(use_case)[:500]}]}))


def _p_link(toolkit: str) -> str:
    data = _in_session("POST", "/link", body={"toolkit": str(toolkit).strip().lower()})
    url = str(data.get("redirect_url") or "")
    if not url:
        raise ComposioError("Composio bağlantı sayfası vermedi")
    return url


def _p_execute(tool_slug: str, arguments: dict | None = None) -> dict:
    data = _in_session("POST", "/execute",
                       body={"tool_slug": str(tool_slug).strip(), "arguments": arguments or {}},
                       timeout=60.0)
    err = data.get("error")
    ok = not err and str(data.get("result_type") or "completed") != "error"
    return {"ok": bool(ok), "data": data.get("data"), "error": str(err or "")[:400],
            "result_type": data.get("result_type", "")}


def _p_toolkits(connected_only: bool = False, search_text: str = "", limit: int = 50) -> list[dict]:
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


# ── Composio Connect (ck_ consumer keys) over MCP ─────────────────────────────
_mcp = None


def is_consumer() -> bool:
    return api_key().startswith("ck_")


def _client():
    global _mcp
    from core import composio_connect as cc
    key = api_key()
    with _lock:
        if _mcp is None or _mcp.key != key:
            _mcp = cc.McpClient(key)
        return _mcp


def _c(fn):
    """Run a Connect call, turning its errors into ComposioError."""
    from core import composio_connect as cc
    try:
        return fn(cc, _client())
    except cc.ConnectError as exc:
        raise ComposioError(str(exc)) from None


def _c_search(use_case: str) -> dict:
    def go(cc, cl):
        data = cl.call("COMPOSIO_SEARCH_TOOLS", cc.search_args(cl, str(use_case)[:500]))
        sess = (data.get("session") or {}) if isinstance(data, dict) else {}
        if isinstance(sess, dict) and sess.get("id"):
            cl.search_session = str(sess["id"])
        return data
    data = _c(go)
    return _parse_search(data)


def _c_link(toolkit: str) -> str:
    tk = str(toolkit).strip().lower()

    def go(cc, cl):
        return cl.call("COMPOSIO_MANAGE_CONNECTIONS", cc.manage_args(cl, tk, "add"))
    data = _c(go)
    from core import composio_connect as cc
    url = cc.find_url(data)
    if not url:
        st = cc.connection_statuses(data)
        if st.get(tk):
            _remember_connected({tk}, merge=True)
            return ""                                   # already connected
        raise ComposioError(f"Composio bağlantı sayfası vermedi: {str(data)[:160]}")
    return url


def _c_execute(tool_slug: str, arguments: dict | None = None) -> dict:
    def go(cc, cl):
        return cl.call("COMPOSIO_MULTI_EXECUTE_TOOL",
                       cc.execute_args(cl, str(tool_slug).strip(), arguments or {}))
    data = _c(go)
    item = data
    if isinstance(data, dict) and isinstance(data.get("results"), list) and data["results"]:
        item = data["results"][0]
    resp = item.get("response", item) if isinstance(item, dict) else item
    if isinstance(resp, dict):
        err = resp.get("error") or (item.get("error") if isinstance(item, dict) else None)
        failed = resp.get("successful") is False or resp.get("success") is False or bool(err)
        return {"ok": not failed, "data": resp.get("data", resp), "error": str(err or "")[:400],
                "result_type": "error" if failed else "completed"}
    return {"ok": True, "data": resp, "error": "", "result_type": "completed"}


def _c_toolkits(connected_only: bool = False, search_text: str = "", limit: int = 50) -> list[dict]:
    def go(cc, cl):
        return cl.call("COMPOSIO_MANAGE_CONNECTIONS", cc.manage_args(cl, None, "list"))
    data = _c(go)
    from core import composio_connect as cc
    st = cc.connection_statuses(data)
    _remember_connected({k for k, v in st.items() if v})
    items = [{"slug": k, "name": k, "connected": v} for k, v in sorted(st.items())]
    return [t for t in items if t["connected"]] if connected_only else items


# ── public operations: Connect for ck_ keys, the project API otherwise ────────
def search(use_case: str) -> dict:
    """Tools that fit a task, with their inputs and the app's connection status."""
    return _c_search(use_case) if is_consumer() else _p_search(use_case)


def link(toolkit: str) -> str:
    """A login page URL for one app, or "" when it is already connected."""
    return _c_link(toolkit) if is_consumer() else _p_link(toolkit)


def execute(tool_slug: str, arguments: dict | None = None) -> dict:
    """Run one tool. Returns {'ok': bool, 'data': ..., 'error': str}."""
    return _c_execute(tool_slug, arguments) if is_consumer() else _p_execute(tool_slug, arguments)


def toolkits(connected_only: bool = False, search_text: str = "", limit: int = 50) -> list[dict]:
    if is_consumer():
        return _c_toolkits(connected_only, search_text, limit)
    return _p_toolkits(connected_only, search_text, limit)


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
