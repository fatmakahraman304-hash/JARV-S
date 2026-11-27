import asyncio
import base64
import json
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

from providers import realtime_recall as recall
from providers.realtime_session import RealtimeSession
from providers.realtime_transport import RealtimeError
from providers.engine_realtime import RealtimeEngine


class RecallFormatTests(unittest.TestCase):
    def test_payload_is_bounded_and_history_is_data(self):
        payload = recall.recall_text("proje", "x" * 3000 + "Geçmiş komut")
        data = json.loads(payload)
        self.assertEqual(data["question"], "proje")
        self.assertEqual(len(data["historical_records"]), recall.MAX_HISTORY)
        event = recall.response_event(payload)
        self.assertEqual(event["response"]["conversation"], "none")
        self.assertEqual(event["response"]["tools"], [])
        self.assertEqual(event["response"]["tool_choice"], "none")
        self.assertEqual(event["response"]["input"][0]["content"][0]["text"], payload)

    def test_no_results_and_overlong_query_rejected(self):
        for query, history in (("", recall.NO_HISTORY), ("", ""), ("x" * 201, "record")):
            with self.assertRaises(ValueError):
                recall.recall_text(query, history)


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


def reply(rid):
    return [created(rid),
            {"type": "response.output_audio.delta", "response_id": rid,
             "delta": base64.b64encode(b"\x01\x00").decode()},
            {"type": "response.output_audio_transcript.done", "response_id": rid,
             "transcript": "Önceki proje."},
            {"type": "response.done", "response": {"id": rid, "status": "completed"}}]


class RecallSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_recall_does_not_insert_history_in_normal_conversation(self):
        ws = Socket([*reply("r1"), *reply("r2")])
        session = RealtimeSession(ws, volume_enabled=lambda: True)
        self.addAsyncCleanup(session.close)
        await session.start()
        payload = recall.recall_text("proje", "old data")
        events = [m async for m in session.turn(recall_payload=payload)]
        self.assertTrue(events[-1].server_content.turn_complete)
        _ = [m async for m in session.turn(text="new message")]
        self.assertEqual(ws.sent[1], recall.response_event(payload))
        self.assertEqual(ws.sent[2]["type"], "conversation.item.create")
        self.assertEqual(ws.sent[3], {"type": "response.create"})

    async def test_unexpected_tool_is_never_executed(self):
        call = {"type": "function_call", "name": "request_volume", "status": "completed",
                "call_id": "call_1", "arguments": '{"percent":50}'}
        ws = Socket([created("r1"), {"type": "response.done", "response": {
            "id": "r1", "status": "completed", "output": [call]}}])
        session = RealtimeSession(ws, volume_enabled=lambda: True)
        await session.start()
        with patch("providers.realtime_tools.tool_output") as dispatch:
            with self.assertRaises(RealtimeError):
                _ = [m async for m in session.turn(recall_payload=recall.recall_text("", "old"))]
            dispatch.assert_not_called()
        self.assertTrue(ws.closed)

    async def test_revoked_permission_before_generation_prevents_upload(self):
        allowed = True
        ws = Socket([])
        session = RealtimeSession(ws)
        await session.start()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        await engine.send_approved_recall(recall.recall_text("", "old"), lambda: allowed)
        allowed = False
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(len(ws.sent), 1)


class RecallHudTests(unittest.TestCase):
    def test_preview_requires_human_approval_and_session_still_matches(self):
        from tests._main_import import load_main
        main = load_main()
        engine = Mock()
        loop = Mock()
        loop.is_running.return_value = True
        obj = SimpleNamespace(_engine=engine, _loop=loop, _session_realtime=True,
                              _engine_mode=lambda: "realtime", ui=Mock())
        with patch("memory.config_manager.get_provider_config",
                   return_value={"cloud_consent": True}), patch(
                   "memory.continuity.realtime_history", return_value="historical data"), patch(
                   "core.confirm.request", return_value="[CONFIRMATION_PENDING]") as gate:
            main.FridayLive._request_realtime_recall(obj, "proje")
            engine.send_approved_recall.assert_not_called()
            payload = obj.ui.show_content.call_args.args[1]
            self.assertIn("historical data", payload)
            obj._engine = Mock()
            self.assertIn("NOT EXECUTED", gate.call_args.kwargs["run"]())
            engine.send_approved_recall.assert_not_called()
