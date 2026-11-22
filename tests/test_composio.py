"""Composio client and the `apps` tool, against a fake HTTP layer."""
import json
import sys
import types
import unittest
from unittest.mock import patch


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.content = json.dumps(data).encode()
        self.text = json.dumps(data)

    def json(self):
        return self._data


class FakeHttpx(types.ModuleType):
    class TimeoutException(Exception):
        pass

    class HTTPError(Exception):
        pass

    def __init__(self):
        super().__init__("httpx")
        self.calls = []
        self.routes = {}

    def request(self, method, url, json=None, params=None, timeout=None, headers=None):
        self.calls.append((method, url, json, params, headers))
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp(json) if callable(resp) else resp
        return _Resp(404, {"error": "not found"})


class _Setup:
    def setUp(self):
        self.store = {}
        self.httpx = FakeHttpx()
        self.patches = [
            patch.dict(sys.modules, {"httpx": self.httpx}),
            patch("memory.config_manager.get_plugin_config",
                  side_effect=lambda ns: dict(self.store.get(ns, {}))),
            patch("memory.config_manager.save_plugin_config",
                  side_effect=lambda ns, v: self.store.setdefault(ns, {}).update(v)),
        ]
        for p in self.patches:
            p.start()
        from core import composio
        self.c = composio
        composio._session_id = composio._session_key = None
        self.httpx.routes[("POST", "/tool_router/session")] = _Resp(201, {"session_id": "trs_1"})
        self.httpx.routes[("GET", "/trs_1/toolkits")] = _Resp(200, {"items": []})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()


class ComposioTests(_Setup, unittest.TestCase):

    def test_no_key_is_a_clear_error(self):
        self.assertFalse(self.c.is_configured())
        with self.assertRaises(self.c.ComposioError):
            self.c.search("x")

    def test_key_header_user_id_and_session_reuse(self):
        self.c.save_api_key("  k123 ")
        self.httpx.routes[("GET", "/trs_1/toolkits")] = _Resp(200, {"items": [
            {"slug": "gmail", "name": "Gmail", "connected_account": {"id": "ca_1", "status": "ACTIVE"}},
            {"slug": "notion", "name": "Notion", "connected_account": None},
        ]})
        items = self.c.toolkits(connected_only=True)
        self.c.toolkits()
        self.assertEqual([t["connected"] for t in items], [True, False])
        sessions = [c for c in self.httpx.calls if c[1].endswith("/tool_router/session")]
        self.assertEqual(len(sessions), 1)                       # reused
        self.assertEqual(sessions[0][4]["x-api-key"], "k123")
        uid = sessions[0][2]["user_id"]
        self.assertTrue(uid.startswith("aether-"))
        self.assertEqual(self.c.user_id(), uid)                  # stable
        from core import activity
        self.assertIn("gmail", activity.connected())

    def test_search_execute_link(self):
        self.c.save_api_key("k")
        self.httpx.routes[("POST", "/trs_1/search")] = _Resp(200, {
            "success": True,
            "results": [{"primary_tool_slugs": ["GMAIL_SEND_EMAIL"], "execution_guidance": "do it"}],
            "tool_schemas": {"GMAIL_SEND_EMAIL": {
                "toolkit": "gmail", "description": "Send an email",
                "input_schema": {"properties": {"recipient_email": {"type": "string"},
                                                "body": {"type": "string"}},
                                 "required": ["recipient_email"]}}},
            "toolkit_connection_statuses": [{"toolkit": "gmail", "has_active_connection": False}],
        })
        r = self.c.search("send an email")
        self.assertEqual(r["tools"][0]["slug"], "GMAIL_SEND_EMAIL")
        self.assertIn("recipient_email*", r["tools"][0]["inputs"])
        self.assertFalse(r["connections"][0]["connected"])

        self.httpx.routes[("POST", "/trs_1/execute")] = lambda body: _Resp(200, {
            "result_type": "completed", "data": {"echo": body}, "error": None})
        out = self.c.execute("GMAIL_SEND_EMAIL", {"recipient_email": "a@b.c"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"]["echo"]["tool_slug"], "GMAIL_SEND_EMAIL")

        self.httpx.routes[("POST", "/trs_1/link")] = _Resp(201, {"redirect_url": "https://x/login"})
        self.assertEqual(self.c.link("gmail"), "https://x/login")

    def test_expired_session_is_replaced_once(self):
        self.c.save_api_key("k")
        self.c._session()
        self.httpx.routes[("POST", "/tool_router/session")] = _Resp(201, {"session_id": "trs_2"})
        self.httpx.routes[("GET", "/trs_2/toolkits")] = _Resp(200, {"items": []})
        self.httpx.routes[("POST", "/trs_2/link")] = _Resp(201, {"redirect_url": "https://y"})
        self.assertEqual(self.c.link("notion"), "https://y")       # trs_1 → 404 → trs_2

    def test_project_recognizes_active_account_and_skips_new_login(self):
        self.c.save_api_key("ak_good")
        self.httpx.routes[("GET", "/trs_1/toolkits")] = _Resp(200, {"items": [
            {"slug": "gmail", "connection": {"is_active": True, "connected_account": {"id": "ca_1"}}},
            {"slug": "notion", "connection": {"is_active": False, "connected_account": {"status": "ACTIVE"}}},
        ]})
        self.assertEqual(self.c.refresh_connections(), {"gmail"})
        self.assertEqual(self.c.link("Gmail"), "")
        self.assertEqual(self.httpx.calls[-1][3]["toolkits"], "gmail")
        self.assertFalse(any(c[1].endswith("/link") for c in self.httpx.calls))

    def test_http_errors_are_readable(self):
        self.c.save_api_key("bad")
        self.httpx.routes[("POST", "/tool_router/session")] = _Resp(401, {"error": "nope"})
        with self.assertRaisesRegex(self.c.ComposioError, "kabul etmedi"):
            self.c.link("gmail")

    def test_apps_tool(self):
        from plugins import apps
        self.assertIn("status=failed", apps.run({"action": "search", "use_case": "x"}))   # no key
        self.c.save_api_key("k")
        self.httpx.routes[("POST", "/trs_1/execute")] = _Resp(200, {
            "result_type": "completed", "data": {"id": "evt_1"}, "error": None})
        out = apps.run({"action": "run", "tool_slug": "GOOGLECALENDAR_CREATE_EVENT",
                        "arguments": '{"summary": "Toplantı"}'})
        self.assertTrue(out.startswith("status=done"))
        self.assertIn("evt_1", out)
        self.assertIn("UNTRUSTED", out)
        self.assertIn("status=failed", apps.run({"action": "run", "tool_slug": "X", "arguments": "[1]"}))
        self.httpx.routes[("POST", "/trs_1/execute")] = _Resp(200, {
            "result_type": "completed", "data": None, "error": "No connected account"})
        self.assertIn("status=failed", apps.run({"action": "run", "tool_slug": "GMAIL_X", "arguments": "{}"}))
        self.httpx.routes[("POST", "/trs_1/link")] = _Resp(201, {"redirect_url": "https://login"})
        with patch("webbrowser.open", return_value=True) as wb:
            out = apps.run({"action": "connect", "toolkit": "Gmail"})
        wb.assert_called_once_with("https://login")
        self.assertIn("login_page_opened=true", out.lower())

    def test_activity_nodes_for_apps(self):
        from core import activity
        self.assertEqual(activity.node_for_tool("apps", {"tool_slug": "GMAIL_SEND_EMAIL"}), "gmail")
        self.assertEqual(activity.node_for_tool("apps", {"toolkit": "googlesheets"}), "googlesheets")
        self.assertEqual(activity.node_for_tool("apps", {"tool_slug": "SLACK_SEND"}), "apps")
        self.assertEqual(activity.status_of("Tool 'apps' failed: boom"), "fail")


if __name__ == "__main__":
    unittest.main()


class KeyKindTests(_Setup, unittest.TestCase):
    def test_user_key_is_named_without_a_request(self):
        self.c.save_api_key("uak_abc")
        with self.assertRaisesRegex(self.c.ComposioError, "kullanıcı anahtarı"):
            self.c.link("gmail")
        self.assertEqual(self.httpx.calls, [])

    def test_pasted_key_is_cleaned(self):
        self.c.save_api_key(' "Bearer ak_123"\n')
        self.assertEqual(self.c.api_key(), "ak_123")

    def test_org_token_falls_back_to_org_header(self):
        self.c.save_api_key("org_tok")

        def session(body):
            hdrs = self.httpx.calls[-1][4]
            return (_Resp(201, {"session_id": "trs_1"}) if "x-org-api-key" in hdrs
                    else _Resp(401, {"error": {"message": "Invalid API key"}}))
        self.httpx.routes[("POST", "/tool_router/session")] = session
        self.assertEqual(self.c._session(fresh=True), "trs_1")
        self.assertEqual(self.c._header, "x-org-api-key")

    def test_project_key_401_shows_server_reason_and_help(self):
        self.c.save_api_key("ak_wrong")
        self.httpx.routes[("POST", "/tool_router/session")] = _Resp(
            401, {"error": {"message": "Invalid API key"}})
        ok, msg = self.c.check()
        self.assertFalse(ok)
        self.assertIn("Invalid API key", msg)
        self.assertIn("Project Settings", msg)
        self.assertEqual(len(self.httpx.calls), 1)          # ak_ keys are not retried as org

    def test_check_ok(self):
        self.c.save_api_key("ak_ok")
        self.httpx.routes[("GET", "/trs_1/toolkits")] = _Resp(200, {"items": []})
        self.assertEqual(self.c.check(), (True, "Bağlantı başarılı"))


class _McpResp:
    def __init__(self, status=200, data=None, sse=False, headers=None):
        self.status_code = status
        self.headers = dict(headers or {})
        if data is None:
            self.text = ""
        elif sse:
            self.headers.setdefault("content-type", "text/event-stream")
            self.text = "event: message\ndata: " + json.dumps(data) + "\n\n"
        else:
            self.headers.setdefault("content-type", "application/json")
            self.text = json.dumps(data)

    def json(self):
        return json.loads(self.text)


class FakeMcpServer:
    """Answers like connect.composio.dev/mcp."""

    TOOLS = [
        {"name": "COMPOSIO_SEARCH_TOOLS", "inputSchema": {
            "type": "object", "properties": {"queries": {"type": "array"}, "session": {"type": "object"}},
            "required": ["queries"]}},
        {"name": "COMPOSIO_MANAGE_CONNECTIONS", "inputSchema": {
            "type": "object", "properties": {"toolkits": {"type": "array"},
                                             "action": {"type": "string", "enum": ["add", "list", "remove"]},
                                             "session_id": {"type": "string"}},
            "required": ["toolkits"]}},
        {"name": "COMPOSIO_MULTI_EXECUTE_TOOL", "inputSchema": {
            "type": "object", "properties": {"tools": {"type": "array"}, "thought": {"type": "string"},
                                             "sync_response_to_workbench": {"type": "boolean"},
                                             "session_id": {"type": "string"}},
            "required": ["tools", "thought", "sync_response_to_workbench"]}},
    ]

    def __init__(self):
        self.calls = []
        self.headers_seen = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.headers_seen.append(dict(headers or {}))
        if headers.get("x-consumer-api-key") != "ck_good":
            return _McpResp(401, {"error": "unauthorized"})
        m = json.get("method")
        rid = json.get("id")
        if m == "initialize":
            return _McpResp(200, {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2025-03-26"}},
                            sse=True, headers={"mcp-session-id": "mcp_s1"})
        if headers.get("Mcp-Session-Id") != "mcp_s1":
            return _McpResp(400, {"error": "no session"})
        if m == "notifications/initialized":
            return _McpResp(202)
        if m == "tools/list":
            return _McpResp(200, {"jsonrpc": "2.0", "id": rid, "result": {"tools": self.TOOLS}})
        if m == "tools/call":
            name, args = json["params"]["name"], json["params"]["arguments"]
            self.calls.append((name, args))
            payload = self.answer(name, args)
            return _McpResp(200, {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": __import__("json").dumps(payload)}]}}, sse=True)
        return _McpResp(400, {"error": "?"})

    def answer(self, name, args):
        if name == "COMPOSIO_SEARCH_TOOLS":
            return {"data": {"results": [{"primary_tool_slugs": ["GOOGLECALENDAR_CREATE_EVENT"]}],
                             "tool_schemas": {"GOOGLECALENDAR_CREATE_EVENT": {
                                 "toolkit": "googlecalendar", "description": "Create event",
                                 "input_schema": {"properties": {"summary": {"type": "string"}},
                                                  "required": ["summary"]}}},
                             "toolkit_connection_statuses": [
                                 {"toolkit": "googlecalendar", "has_active_connection": False}],
                             "session": {"id": "srch_9"}},
                    "successful": True}
        if name == "COMPOSIO_MANAGE_CONNECTIONS":
            if args.get("action") == "list":
                return {"data": {"results": {"gmail": {"toolkit": "gmail", "status": "ACTIVE"},
                                             "notion": {"toolkit": "notion", "status": "INITIATED"}}},
                        "successful": True}
            tk = args["toolkits"][0]
            if tk == "gmail":
                return {"data": {"results": {"gmail": {"toolkit": "gmail", "status": "ACTIVE"}}},
                        "successful": True}
            return {"data": {"results": {tk: {"toolkit": tk, "status": "initiated",
                                              "redirect_url": f"https://connect.composio.dev/link/{tk}"}}},
                    "successful": True}
        if name == "COMPOSIO_MULTI_EXECUTE_TOOL":
            slug = args["tools"][0]["tool_slug"]
            if slug == "BAD_TOOL":
                return {"data": {"results": [{"tool_slug": slug, "response": {
                    "successful": False, "data": {}, "error": "Invalid arguments"}}]}, "successful": True}
            return {"data": {"results": [{"tool_slug": slug, "response": {
                "successful": True, "data": {"id": "evt_42"}, "error": None}}]}, "successful": True}
        return {}


class ConnectTests(_Setup, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = FakeMcpServer()
        self.httpx.post = self.server
        self.c.save_api_key("ck_good")

    def test_check_and_session_header(self):
        self.assertTrue(self.c.is_consumer())
        ok, msg = self.c.check()
        self.assertTrue(ok, msg)
        self.assertIn("Connect", msg)
        self.assertTrue(any(h.get("Mcp-Session-Id") == "mcp_s1" for h in self.server.headers_seen))
        from core import activity
        self.assertIn("gmail", activity.connected())          # from the list call in check()
        self.assertEqual(self.httpx.calls, [])                # never touched the project API

    def test_search_link_execute(self):
        r = self.c.search("yarın 18:30 takvime toplantı ekle")
        self.assertEqual(r["tools"][0]["slug"], "GOOGLECALENDAR_CREATE_EVENT")
        self.assertIn("summary*", r["tools"][0]["inputs"])
        self.assertFalse(r["connections"][0]["connected"])
        self.assertEqual(self.c.link("GoogleCalendar"), "https://connect.composio.dev/link/googlecalendar")
        add = [a for n, a in self.server.calls if n == "COMPOSIO_MANAGE_CONNECTIONS"][-1]
        self.assertEqual(add["action"], "add")
        self.assertEqual(add["session_id"], "srch_9")          # search session carried over
        self.assertEqual(self.c.link("gmail"), "")              # already connected
        out = self.c.execute("GOOGLECALENDAR_CREATE_EVENT", {"summary": "Toplantı"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"], {"id": "evt_42"})
        ex = [a for n, a in self.server.calls if n == "COMPOSIO_MULTI_EXECUTE_TOOL"][-1]
        self.assertFalse(ex["sync_response_to_workbench"])
        self.assertTrue(ex["thought"])                          # required field filled
        bad = self.c.execute("BAD_TOOL", {})
        self.assertFalse(bad["ok"])
        self.assertIn("Invalid arguments", bad["error"])

    def test_bad_consumer_key(self):
        self.c.save_api_key("ck_wrong")
        ok, msg = self.c.check()
        self.assertFalse(ok)
        self.assertIn("ck_", msg)

    def test_modern_connect_recognizes_browser_approval_and_restores_it_on_reopen(self):
        schema = {"type": "object", "properties": {"toolkits": {"type": "array"},
                  "reinitiate_all": {"type": "boolean"}}, "required": ["toolkits"]}
        self.server.TOOLS = [dict(t, inputSchema=schema) if t["name"] == "COMPOSIO_MANAGE_CONNECTIONS" else t
                             for t in self.server.TOOLS]
        active = False

        def answer(name, args):
            if name == "COMPOSIO_SEARCH_TOOLS":
                self.assertTrue(any("gmail" in q["use_case"] for q in args["queries"]))
                return {"data": {"toolkit_connection_statuses": [
                    {"toolkit": {"slug": "gmail"}, "has_active_connection": active},
                ]}, "successful": True}
            self.assertEqual(args, {"toolkits": ["gmail"]})
            result = ({"status": "ACTIVE"} if active else
                      {"status": "INITIATED", "redirect_url": "https://connect.composio.dev/link/gmail"})
            return {"data": {"results": {"gmail": result}}, "successful": True}

        self.server.answer = answer
        self.assertEqual(self.c.refresh_connections(raise_errors=True), set())
        self.assertEqual(self.c.link("gmail"), "https://connect.composio.dev/link/gmail")
        active = True
        self.assertEqual(self.c.refresh_connections(raise_errors=True), {"gmail"})
        self.c._mcp = None
        self.c._remember_connected(set())
        self.assertEqual(self.c.refresh_connections(raise_errors=True), {"gmail"})
        self.assertEqual(self.c.link("gmail"), "")
        active = False
        self.assertEqual(self.c.refresh_connections(raise_errors=True), set())

    def test_apps_tool_with_consumer_key(self):
        from plugins import apps
        out = apps.run({"action": "connect", "toolkit": "gmail"})
        self.assertIn("already_connected=true", out.lower())
        out = apps.run({"action": "run", "tool_slug": "GOOGLECALENDAR_CREATE_EVENT",
                        "arguments": '{"summary": "x"}'})
        self.assertIn("evt_42", out)
