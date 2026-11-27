"""Realtime credentials stay on the originally selected connection."""
import unittest
from unittest.mock import patch

from providers import realtime_transport as rt

try:
    from websockets.asyncio.server import serve
except ImportError:
    serve = None


@unittest.skipIf(serve is None, "Optional Realtime websockets dependency unavailable")
class RealtimeConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_redirect_never_contacts_second_endpoint(self):
        requests = []

        async def handler(connection):
            await connection.close()

        def second(connection, request):
            requests.append("redirect destination")
            return connection.respond(403, "unexpected")

        async with serve(handler, "127.0.0.1", 0, process_request=second) as destination:
            port = destination.sockets[0].getsockname()[1]

            def redirect(connection, request):
                requests.append("initial endpoint")
                response = connection.respond(307, "redirect")
                response.headers["Location"] = f"ws://127.0.0.1:{port}/unexpected"
                return response

            async with serve(handler, "127.0.0.1", 0, process_request=redirect) as origin:
                original_port = origin.sockets[0].getsockname()[1]
                with patch.object(rt, "URL", f"ws://127.0.0.1:{original_port}/realtime"):
                    with self.assertRaisesRegex(rt.RealtimeError, "^Realtime bağlantısı kurulamadı.$"):
                        async with rt.open_realtime("fixture-key"):
                            self.fail("Redirect must not produce a session")
        self.assertEqual(requests, ["initial endpoint"])

    async def test_direct_session_and_caller_exception_not_masked(self):
        received = []

        async def handler(connection):
            received.append(connection.request.headers["Authorization"])
            await connection.send("ready")
            await connection.wait_closed()

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with patch.object(rt, "URL", f"ws://127.0.0.1:{port}/realtime"):
                with self.assertRaisesRegex(ValueError, "^caller failure$"):
                    async with rt.open_realtime("fixture-key") as ws:
                        self.assertEqual(await ws.recv(), "ready")
                        raise ValueError("caller failure")
        self.assertEqual(received, ["Bearer fixture-key"])


class InvalidConnectionInputTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_control_characters_rejected_before_connect(self):
        for key in ("", " key", "key\r\n", "key\x7f", "key\x00", "ş"):
            with self.subTest(key=repr(key)), self.assertRaises(ValueError):
                async with rt.open_realtime(key):
                    self.fail("Invalid credentials reached connection")
