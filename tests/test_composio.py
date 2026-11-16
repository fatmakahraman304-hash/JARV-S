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


class ComposioTests(unittest.TestCase):
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

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

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
        self.assertTrue(uid.startswith("jarvis-"))
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
        self.httpx.routes[("POST", "/trs_2/link")] = _Resp(201, {"redirect_url": "https://y"})
        self.assertEqual(self.c.link("notion"), "https://y")       # trs_1 → 404 → trs_2

    def test_http_errors_are_readable(self):
        self.c.save_api_key("bad")
        self.httpx.routes[("POST", "/tool_router/session")] = _Resp(401, {"error": "nope"})
        with self.assertRaisesRegex(self.c.ComposioError, "geçersiz"):
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
