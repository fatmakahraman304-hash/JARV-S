import asyncio
import base64
import json
import unittest
from collections import deque
from contextlib import aclosing

from providers import realtime_transport as rt
from providers import realtime_session as rs


class Socket:
    def __init__(self, events):
        self.events = deque(events)
        self.sent = []
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if self.events:
            return json.dumps(self.events.popleft())
        await asyncio.Future()

    async def close(self):
        self.closed = True


def reply(rid, text):
    return [
        {"type": "response.created", "response": {"id": rid}},
        {"type": "response.output_audio.delta", "response_id": rid,
         "delta": base64.b64encode(b"\x01\x00" * 1300).decode()},
        {"type": "response.output_audio_transcript.delta", "response_id": rid, "delta": text[:2]},
        {"type": "response.output_audio_transcript.delta", "response_id": rid, "delta": text[2:]},
        {"type": "response.output_audio_transcript.done", "response_id": rid, "transcript": text},
        {"type": "response.done", "response": {"id": rid, "status": "completed"}},
    ]


class RealtimeSessionTests(unittest.IsolatedAsyncioTestCase):
    async def make(self, *events):
        ws = Socket([{"type": "session.created"}, {"type": "session.updated"}, *events])
        session = rs.RealtimeSession(ws)
        await session.start()
        self.addAsyncCleanup(session.close)
        return ws, session

    async def test_two_turns_share_session_and_emit_friday_events(self):
        ws, session = await self.make(*reply("r1", "Merhaba."), *reply("r2", "Devam."))
        for text in ("Merhaba.", "Devam."):
            events = [m async for m in session.turn(text=text)]
            self.assertEqual([len(m.data) for m in events if m.data], [2400, 200])
            transcripts = [m.server_content.output_transcription.text for m in events
                           if m.server_content and m.server_content.output_transcription]
            self.assertEqual(transcripts, [text])
            self.assertTrue(events[-1].server_content.turn_complete)
        self.assertEqual([e["type"] for e in ws.sent], ["session.update",
            "conversation.item.create", "response.create", "conversation.item.create", "response.create"])
        self.assertFalse(ws.closed)

    async def test_early_exit_invalidates_session(self):
        ws, session = await self.make(*reply("r1", "Merhaba"))
        async with aclosing(session.turn(text="Hi")) as stream:
            self.assertTrue((await anext(stream)).data)
        self.assertTrue(ws.closed)
        with self.assertRaises(rt.RealtimeError):
            await anext(session.turn(text="Again"))

    async def test_concurrent_turn_is_rejected(self):
        ws, session = await self.make(*reply("r1", "Hi"))
        async with aclosing(session.turn(text="Hi")) as first:
            await anext(first)
            with self.assertRaisesRegex(rt.RealtimeError, "hâlâ"):
                await anext(session.turn(text="Other"))
            self.assertFalse(ws.closed)
            await self.consume(first)

    async def consume(self, stream):
        return [m async for m in stream]

    async def test_wrong_response_id_closes_session(self):
        events = reply("r1", "Hi")
        events[1]["response_id"] = "wrong"
        ws, session = await self.make(*events)
        with self.assertRaises(rt.RealtimeError):
            await self.consume(session.turn(text="Hi"))
        self.assertTrue(ws.closed)

    async def test_cancellation_closes_socket(self):
        ws, session = await self.make({"type": "response.created", "response": {"id": "r1"}})
        task = asyncio.create_task(self.consume(session.turn(text="Hi")))
        for _ in range(20):
            if len(ws.sent) == 3:
                break
            await asyncio.sleep(0)
        self.assertEqual(len(ws.sent), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(ws.closed)

    async def test_turn_limit_does_not_send_more(self):
        events = [event for i in range(rs.MAX_TURNS) for event in reply(str(i), "Hi")]
        ws, session = await self.make(*events)
        for _ in range(rs.MAX_TURNS):
            await self.consume(session.turn(text="Hi"))
        before = len(ws.sent)
        with self.assertRaisesRegex(rt.RealtimeError, "tur sınırı"):
            await anext(session.turn(text="Hi"))
        self.assertEqual(len(ws.sent), before)


if __name__ == "__main__":
    unittest.main()
