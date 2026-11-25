"""Real asyncio backpressure and shutdown, without model accounts or devices."""
import asyncio
import unittest

from providers.base import Msg, FunctionCall
from providers.engine_pipeline import PipelineEngine


class OutputBounds(unittest.IsolatedAsyncioTestCase):
    async def test_slow_reader_preserves_order_and_applies_backpressure(self):
        engine = PipelineEngine(None)
        self.assertGreater(engine._queue.maxsize, 0)
        messages = [Msg.said("merhaba"), Msg.audio(b"\x01\0" * 10),
                    Msg.calls([FunctionCall(id="one", name="test", args={})]),
                    Msg.turn_end()]
        expected = [messages[i % len(messages)] for i in range(10000)]
        maximum = 0
        async def produce():
            nonlocal maximum
            for message in expected:
                await engine._emit(message)
                maximum = max(maximum, engine._queue.qsize())
        producer = asyncio.create_task(produce())
        await asyncio.sleep(0)
        self.assertFalse(producer.done(), "producer must wait for a slow reader")
        self.assertEqual(engine._queue.qsize(), engine._queue.maxsize)
        received = []
        async def consume():
            async for message in engine.receive():
                received.append(message)
                if len(received) == len(expected):
                    break
                if len(received) % 31 == 0:
                    await asyncio.sleep(0)
        try:
            await asyncio.wait_for(asyncio.gather(producer, consume()), 10)
            self.assertEqual(received, expected)
            self.assertEqual(maximum, engine._queue.maxsize)
        finally:
            await engine.close()
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    async def test_full_queue_close_cancels_blocked_producers_and_repeated_receive_ends(self):
        engine = PipelineEngine(None)
        self.assertGreater(engine._queue.maxsize, 0)
        for _ in range(engine._queue.maxsize):
            await engine._emit(Msg.said("queued"))
        blocked = [asyncio.create_task(engine._emit(Msg.said("late"))) for _ in range(3)]
        await asyncio.sleep(0)
        await asyncio.wait_for(engine.close(), 1)
        results = await asyncio.gather(*blocked, return_exceptions=True)
        self.assertTrue(all(isinstance(result, asyncio.CancelledError) for result in results))
        self.assertFalse(engine._pending_puts)
        await engine._emit(Msg.said("after close"))
        await engine.close()
        for _ in range(2):
            async def drain():
                return [message async for message in engine.receive()]
            self.assertEqual(await asyncio.wait_for(drain(), 1), [])

    async def test_close_wakes_a_waiting_receiver(self):
        engine = PipelineEngine(None)
        receiver = asyncio.create_task(anext(engine.receive(), None))
        await asyncio.sleep(0)
        await engine.close()
        self.assertIsNone(await asyncio.wait_for(receiver, 1))

    async def test_cancelled_producer_leaves_no_pending_put_or_late_output(self):
        engine = PipelineEngine(None)
        self.assertGreater(engine._queue.maxsize, 0)
        for _ in range(engine._queue.maxsize):
            await engine._emit(Msg.turn_end())
        producer = asyncio.create_task(engine._emit(Msg.said("cancelled")))
        await asyncio.sleep(0)
        producer.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await producer
        self.assertFalse(engine._pending_puts)
        await engine.close()

    async def test_large_tts_chunk_is_split_without_losing_pcm(self):
        pcm = bytes(range(256)) * 50
        class Voice:
            async def speak(self, text):
                yield pcm
        engine = PipelineEngine(None, tts=Voice())
        try:
            await engine._speak("Merhaba")
            parts = []
            while not engine._queue.empty():
                parts.append(engine._queue.get_nowait().data)
            self.assertGreater(len(parts), 1)
            self.assertTrue(all(len(part) <= 2400 for part in parts))
            self.assertEqual(b"".join(parts), pcm)
        finally:
            await engine.close()
