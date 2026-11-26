import asyncio
import unittest
from types import SimpleNamespace
from contextlib import aclosing

from providers.base import Msg
from providers import engine_realtime as er


class Session:
    def __init__(self):
        self.requests = []
        self.closed = False
        self.entered = asyncio.Event()
        self.block = None

    async def turn(self, **request):
        self.requests.append(request)
        self.entered.set()
        yield Msg.audio(b"\x01\x00")
        if self.block is not None:
            await self.block.wait()
        yield Msg.said("Merhaba.")
        yield Msg.turn_end()

    async def close(self):
        self.closed = True


class RealtimeEngineTests(unittest.IsolatedAsyncioTestCase):
    async def make(self):
        session = Session()
        logs = []
        engine = er.RealtimeEngine(session, logs.append)
        self.addAsyncCleanup(engine.close)
        return session, engine, logs

    async def test_text_turn_emits_ordered_events(self):
        session, engine, _ = await self.make()
        await engine.send_client_content(turns={"parts": [{"text": "Selam"}]})
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [{"text": "Selam"}])
        async with aclosing(engine.receive()) as stream:
            self.assertEqual((await anext(stream)).data, b"\x01\x00")
            self.assertEqual((await anext(stream)).server_content.output_transcription.text, "Merhaba.")
            self.assertTrue((await anext(stream)).server_content.turn_complete)
        self.assertFalse(engine.caps["tools"])
        self.assertFalse(engine.caps["vision"])
        self.assertTrue(engine.caps["audio_out"])

    async def test_microphone_only_sends_at_explicit_flush(self):
        session, engine, _ = await self.make()
        await engine.send_realtime_input(audio=SimpleNamespace(data=b"\x01\x00"))
        await engine.send_realtime_input(audio=b"\x02\x00")
        self.assertEqual(session.requests, [])
        self.assertEqual(await engine.flush_microphone(), "")
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(session.requests, [{"pcm": b"\x01\x00\x02\x00"}])

    async def test_oversize_discards_whole_capture(self):
        session, engine, logs = await self.make()
        await engine.send_realtime_input(audio=b"\0" * er.MAX_MIC_BYTES)
        await engine.send_realtime_input(audio=b"\0\0")
        await engine.flush_microphone()
        self.assertEqual(session.requests, [])
        self.assertIsNone(engine._gen)
        self.assertTrue(logs)
        self.assertEqual(len(engine._mic), 0)

    async def test_busy_and_unsupported_inputs_never_transmit(self):
        session, engine, logs = await self.make()
        session.block = asyncio.Event()
        await engine.send_client_content(turns={"parts": [{"text": "First"}]})
        await asyncio.wait_for(session.entered.wait(), 2)
        await engine.send_client_content(turns={"parts": [{"text": "Second"}]})
        await engine.send_client_content(turns={"parts": [{"inline_data": {"data": "image"}}]})
        await engine.send_tool_response(function_responses=[object()])
        self.assertEqual(session.requests, [{"text": "First"}])
        self.assertGreaterEqual(len(logs), 3)
        session.block.set()
        await asyncio.wait_for(engine._gen, 2)

    async def test_interrupt_discards_queued_audio_and_disables_session(self):
        session, engine, logs = await self.make()
        session.block = asyncio.Event()
        await engine.send_client_content(turns={"parts": [{"text": "First"}]})
        await asyncio.wait_for(session.entered.wait(), 2)
        task = engine._gen
        await asyncio.to_thread(engine.interrupt)
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.wait_for(engine._closing, 2)
        self.assertTrue(session.closed)
        events = []
        while not engine._queue.empty():
            events.append(engine._queue.get_nowait())
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].server_content.turn_complete)
        await engine.send_client_content(turns={"parts": [{"text": "Again"}]})
        self.assertEqual(session.requests, [{"text": "First"}])

    async def test_close_wakes_receiver(self):
        session, engine, _ = await self.make()
        receiver = asyncio.create_task(anext(engine.receive(), None))
        await asyncio.sleep(0)
        await engine.close()
        self.assertIsNone(await asyncio.wait_for(receiver, 2))
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
