import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from dashboard.server import DashboardServer
from core.tasks.store import TaskStore


class DashboardTaskStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_metadata_requires_live_https_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TaskStore(Path(tmp))
            store.create({"id": "tabc123", "status": "running", "task": "PRIVATE", "result": "PRIVATE"})
            with patch("core.tasks.desktop.engine", return_value=SimpleNamespace(store=store)):
                server = DashboardServer()
                server._tokens["controller"] = time.time()
                transport = httpx.ASGITransport(app=server.app)
                async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
                    endpoint = "/api/task-status"
                    self.assertEqual((await client.get(endpoint)).status_code, 403)
                    headers = {"Authorization": "Bearer controller"}
                    response = await client.get(endpoint, headers=headers)
                    self.assertEqual(response.json(), {"tasks": [{"id": "tabc123", "status": "running"}]})
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual((await client.get("http://test" + endpoint, headers=headers)).status_code, 403)
                    server._tokens.clear()
                    self.assertEqual((await client.get(endpoint, headers=headers)).status_code, 403)
