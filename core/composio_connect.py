"""core/composio_connect.py — Composio Connect over MCP, for `ck_` consumer keys.

A Composio account opened at composio.dev gets a consumer key (`ck_…`) meant
for MCP clients: requests go to https://connect.composio.dev/mcp with the key
in the `x-consumer-api-key` header. That endpoint is an MCP server (JSON-RPC
over streamable HTTP) whose tools are Composio's meta tools:

    COMPOSIO_SEARCH_TOOLS        find tools for a task, with connection status
    COMPOSIO_MANAGE_CONNECTIONS  add a connection (returns a login link) / list
    COMPOSIO_MULTI_EXECUTE_TOOL  run one or more app tools

This module is a small MCP client for exactly that: initialise, list tools,
call a tool. Arguments for the meta tools are built from the input schemas the
server publishes, so a renamed or newly required field is handled instead of
breaking, and answers are read defensively (JSON or server-sent events, data
wrapped or not). core/composio.py calls into it when the saved key is a `ck_`.
"""
from __future__ import annotations

import json
import threading

MCP_URL = "https://connect.composio.dev/mcp"
PROTOCOL = "2025-03-26"


class ConnectError(RuntimeError):
    pass


class McpClient:
    def __init__(self, key: str, url: str = MCP_URL, timeout: float = 45.0):
        self.key, self.url, self.timeout = key, url, timeout
        self._sid: str | None = None
        self._id = 0
        self._tools: dict[str, dict] | None = None
        self._lock = threading.Lock()
        self.search_session: str | None = None

    # ── transport ─────────────────────────────────────────────────────────────
    def _headers(self) -> dict:
        h = {"x-consumer-api-key": self.key, "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self._sid:
            h["Mcp-Session-Id"] = self._sid
            h["MCP-Protocol-Version"] = PROTOCOL
        return h

    @staticmethod
    def _parse(resp, want_id):
        ctype = str(resp.headers.get("content-type", "")).lower()
        text = resp.text or ""
        if "text/event-stream" in ctype or text.lstrip().startswith(("event:", "data:")):
            found = None
            for block in text.replace("\r\n", "\n").split("\n\n"):
                data = "\n".join(line[5:].lstrip() for line in block.split("\n")
                                 if line.startswith("data:"))
                if not data:
                    continue
                try:
                    msg = json.loads(data)
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("id") == want_id:
                    return msg
                found = found or msg
            return found or {}
        try:
            return resp.json() if text else {}
        except ValueError:
            return {"raw": text[:300]}

    def _post(self, payload: dict, want_id=None):
        import httpx
        try:
            r = httpx.post(self.url, json=payload, headers=self._headers(), timeout=self.timeout)
        except httpx.TimeoutException:
            raise ConnectError("Composio Connect zamanında yanıt vermedi") from None
        except httpx.HTTPError as exc:
            raise ConnectError(f"Composio Connect'e bağlanılamadı: {exc.__class__.__name__}") from None
        sid = r.headers.get("mcp-session-id") or r.headers.get("Mcp-Session-Id")
        if sid:
            self._sid = sid
        if r.status_code in (401, 403):
            raise ConnectError("Composio Connect anahtarı kabul etmedi — composio.dev → Settings → "
                               "Sessions & API Key bölümündeki ck_ anahtarını yeniden kopyala")
        if r.status_code == 404 and self._sid:
            raise _Expired()
        if r.status_code == 429:
            raise ConnectError("Composio hız sınırı — biraz sonra tekrar dene")
        if r.status_code >= 400:
            raise ConnectError(f"Composio Connect hatası {r.status_code}: {(r.text or '')[:200]}")
        return self._parse(r, want_id) if want_id is not None else {}

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        rid = self._id
        msg = self._post({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, rid)
        if isinstance(msg, dict) and msg.get("error"):
            err = msg["error"]
            raise ConnectError(f"Composio Connect: {err.get('message', err) if isinstance(err, dict) else err}"[:240])
        return (msg or {}).get("result") or {}

    def _ensure(self) -> None:
        if self._sid is not None:
            return
        self._rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                 "clientInfo": {"name": "aether", "version": "1.0"}})
        if self._sid is None:
            self._sid = ""            # stateless server: no session header needed
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except ConnectError:
            pass

    def _call_rpc(self, method, params):
        with self._lock:
            self._ensure()
            try:
                return self._rpc(method, params)
            except _Expired:
                self._sid, self._tools = None, None
                self._ensure()
                return self._rpc(method, params)

    # ── MCP operations ────────────────────────────────────────────────────────
    def tools(self) -> dict[str, dict]:
        if self._tools is None:
            out, cursor = {}, None
            for _ in range(10):
                res = self._call_rpc("tools/list", {"cursor": cursor} if cursor else {})
                for t in res.get("tools") or []:
                    out[str(t.get("name"))] = t
                cursor = res.get("nextCursor")
                if not cursor:
                    break
            self._tools = out
        return self._tools

    def call(self, name: str, arguments: dict):
        res = self._call_rpc("tools/call", {"name": name, "arguments": arguments})
        texts = [c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text"]
        payload = res.get("structuredContent")
        if payload is None:
            joined = "\n".join(texts).strip()
            try:
                payload = json.loads(joined) if joined else {}
            except ValueError:
                payload = joined
        if res.get("isError"):
            raise ConnectError(f"{name}: {_short(payload)}")
        return _unwrap(payload)

    def schema(self, name: str) -> dict:
        t = self.tools().get(name) or {}
        return t.get("inputSchema") or {}


class _Expired(Exception):
    pass


# ── reading answers ───────────────────────────────────────────────────────────
def _short(v, n=240) -> str:
    try:
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    except Exception:
        s = str(v)
    return s[:n]


def _unwrap(v):
    """{'data': {...}, 'successful': true} → {...}; anything else unchanged."""
    for _ in range(3):
        if isinstance(v, dict) and "data" in v and set(v) <= {"data", "successful", "error",
                                                                "log_id", "logId", "success"}:
            if v.get("successful") is False or v.get("success") is False:
                if v.get("error"):
                    raise ConnectError(_short(v["error"]))
            v = v["data"]
        else:
            break
    return v


def _walk(v):
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x)


def find_url(v) -> str:
    for d in _walk(v):
        for k in ("redirect_url", "redirectUrl", "auth_url", "link", "url"):
            u = d.get(k)
            if isinstance(u, str) and u.startswith("http"):
                return u
    return ""


def connection_statuses(v) -> dict[str, bool]:
    """toolkit slug → connected, from any answer that reports statuses."""
    out: dict[str, bool] = {}
    for d in _walk(v):
        tk = d.get("toolkit") or d.get("toolkit_slug") or d.get("app") or d.get("appName") or d.get("slug")
        if isinstance(tk, dict):
            tk = tk.get("slug") or tk.get("name")
        if isinstance(tk, str) and tk:
            slug = tk.lower()
            active = account_active(d)
            if active is not None:
                out[slug] = out.get(slug, False) or active
        results = d.get("results")
        if not isinstance(results, dict):
            continue
        for toolkit, result in results.items():
            if isinstance(result, dict) and not result.get("toolkit"):
                active = account_active(result)
                if active is not None:
                    slug = toolkit.lower()
                    out[slug] = out.get(slug, False) or active
    return out


def account_active(item: dict) -> bool | None:
    """Read both the current session connection and older account formats."""
    for key in ("has_active_connection", "is_active", "isActive", "already_connected"):
        if isinstance(item.get(key), bool):
            return item[key]
    if isinstance(item.get("status"), str):
        return item["status"].upper() == "ACTIVE"
    for key in ("connection", "connected_account", "connectedAccount"):
        if key in item:
            value = item[key]
            return account_active(value) if isinstance(value, dict) and value else False
    for key in ("connected_accounts", "accounts"):
        if isinstance(item.get(key), list):
            return any(account_active(a) is True for a in item[key] if isinstance(a, dict))
    return None


# ── argument building from the published schemas ─────────────────────────────
def _fill_required(schema: dict, args: dict) -> dict:
    props = schema.get("properties") or {}
    for name in schema.get("required") or []:
        if name in args:
            continue
        spec = props.get(name) or {}
        typ = spec.get("type")
        enum = spec.get("enum") or []
        if enum:
            args[name] = enum[0]
        elif name in ("thought", "reasoning"):
            args[name] = "AETHER is carrying out the user's spoken request."
        elif name in ("current_step", "step"):
            args[name] = "EXECUTING"
        elif typ == "boolean":
            args[name] = False
        elif typ in ("integer", "number"):
            args[name] = 1
        elif typ == "array":
            args[name] = []
        elif typ == "object":
            args[name] = {}
        else:
            args[name] = ""
    return args


def _with_session(client: McpClient, schema: dict, args: dict) -> dict:
    props = schema.get("properties") or {}
    if client.search_session:
        if "session_id" in props:
            args["session_id"] = client.search_session
        elif "session" in props:
            args["session"] = {"id": client.search_session}
    elif "session" in props and "session" in (schema.get("required") or []):
        args["session"] = {"generate_id": True}
    return args


def search_args(client: McpClient, use_case: str | list[str]) -> dict:
    sc = client.schema("COMPOSIO_SEARCH_TOOLS")
    props = sc.get("properties") or {}
    queries = [use_case] if isinstance(use_case, str) else use_case
    if "queries" in props or not props:
        args = {"queries": [{"use_case": query} for query in queries]}
    else:
        args = {"use_case": "\n".join(queries)}
    if "session" in props:
        args["session"] = ({"id": client.search_session} if client.search_session
                           else {"generate_id": True})
    return _fill_required(sc, args)


def manage_args(client: McpClient, toolkit: str | None, action: str) -> dict:
    sc = client.schema("COMPOSIO_MANAGE_CONNECTIONS")
    props = sc.get("properties") or {}
    args: dict = {}
    if toolkit:
        args["toolkits"] = [toolkit] if ("toolkits" in props or not props) else toolkit
        if "toolkits" not in props and "toolkit" in props:
            args = {"toolkit": toolkit}
    act = props.get("action") or {}
    if act:
        choices = [str(c) for c in act.get("enum") or []]
        args["action"] = action if (not choices or action in choices) else choices[0]
    return _fill_required(sc, _with_session(client, sc, args))


def execute_args(client: McpClient, slug: str, arguments: dict) -> dict:
    sc = client.schema("COMPOSIO_MULTI_EXECUTE_TOOL")
    args = {"tools": [{"tool_slug": slug, "arguments": arguments}]}
    props = sc.get("properties") or {}
    if "sync_response_to_workbench" in props:
        args["sync_response_to_workbench"] = False
    return _fill_required(sc, _with_session(client, sc, args))
