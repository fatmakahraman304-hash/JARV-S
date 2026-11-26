import base64
import json
import unittest
from collections import deque
from unittest.mock import patch

from providers import realtime_tools as tools
from providers.realtime_transport import RealtimeError
from providers.realtime_session import RealtimeSession


def call(name="assistant_help", arguments='{"topic":"index"}', cid="call_1"):
    return {"type": "function_call", "name": name, "arguments": arguments,
            "call_id": cid, "status": "completed"}


class GuideValidation(unittest.TestCase):
    def test_only_static_guide_is_dispatched(self):
        with patch("plugins.assistant_help.run", return_value="guide") as run:
            output = tools.guide_output({"output": [call()]}, enabled=lambda: True, seen=set())
        run.assert_called_once_with({"topic": "index"})
        self.assertEqual(output["item"]["call_id"], "call_1")
        self.assertIn("guide", json.loads(output["item"]["output"])["guide"])

    def test_unknown_disabled_duplicate_or_malformed_never_executes(self):
        bad = [call("computer_control"), call(arguments='{"topic":"../secret"}'),
               call(arguments='{"topic":"index","path":"secret"}'),
               call(arguments='{"topic":"index","topic":"audio"}'),
               call(arguments='[]'), call(cid="bad id")]
        with patch("plugins.assistant_help.run") as run:
            for item in bad:
                with self.subTest(item=item), self.assertRaises(RealtimeError):
                    tools.guide_output({"output": [item]}, enabled=lambda: True, seen=set())
            for items, enabled, seen in [([call()], False, set()),
                                         ([call()], True, {"call_1"}),
                                         ([call(), call(cid="call_2")], True, set())]:
                with self.assertRaises(RealtimeError):
                    tools.guide_output({"output": items}, enabled=lambda: enabled, seen=seen)
            run.assert_not_called()


class Socket:
    def __init__(self, events):
        self.events = deque([{"type": "session.updated"}, *events])
        self.sent = []
        self.closed = False
    async def recv(self):
        return json.dumps(self.events.popleft())
    async def send(self, raw):
        self.sent.append(json.loads(raw))
    async def close(self):
        self.closed = True


def created(rid):
    return {"type": "response.created", "response": {"id": rid}}


def done(rid, output=None):
    return {"type": "response.done", "response": {"id": rid, "status": "completed",
                                                   "output": output or []}}


class SessionGuideTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_only_response_followed_by_audio(self):
        ws = Socket([created("r1"), done("r1", [call()]), created("r2"),
                     {"type": "response.output_audio.delta", "response_id": "r2",
                      "delta": base64.b64encode(b"\x01\x00").decode()},
                     {"type": "response.output_audio_transcript.done", "response_id": "r2",
                      "transcript": "Kılavuz"},
                     done("r2")])
        session = RealtimeSession(ws, guide_enabled=lambda: True)
        self.addAsyncCleanup(session.close)
        await session.start()
        events = [msg async for msg in session.turn(text="Kılavuzu oku")]
        self.assertEqual(ws.sent[0]["session"]["tools"], [tools.declaration()])
        self.assertEqual(ws.sent[3]["item"]["type"], "function_call_output")
        self.assertEqual(ws.sent[4]["type"], "response.create")
        self.assertEqual(events[0].data, b"\x01\x00")
        self.assertEqual(events[1].server_content.output_transcription.text, "Kılavuz")
        self.assertTrue(events[2].server_content.turn_complete)

    async def test_disabled_guide_fails_closed(self):
        ws = Socket([created("r1"), done("r1", [call()])])
        session = RealtimeSession(ws)
        await session.start()
        with self.assertRaises(RealtimeError):
            _ = [msg async for msg in session.turn(text="Kılavuz")]
        self.assertEqual(ws.sent[0]["session"]["tools"], [])
        self.assertEqual(len(ws.sent), 3)
        self.assertTrue(ws.closed)

    async def test_round_limit(self):
        events = []
        for i in range(tools.MAX_ROUNDS + 1):
            events += [created(str(i)), done(str(i), [call(cid=f"call_{i}")])]
        ws = Socket(events)
        session = RealtimeSession(ws, guide_enabled=lambda: True)
        await session.start()
        with self.assertRaisesRegex(RealtimeError, "tur sınırı"):
            _ = [msg async for msg in session.turn(text="Kılavuz")]
        self.assertTrue(ws.closed)
        self.assertEqual(sum(e.get("item", {}).get("type") == "function_call_output"
                             for e in ws.sent), tools.MAX_ROUNDS)
