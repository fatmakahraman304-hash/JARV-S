"""Controlled async providers test speech ordering and cancellation without devices."""
import asyncio
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from providers.engine_pipeline import PipelineEngine


class DelayedSTT:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []

    async def transcribe(self, pcm, sample_rate):
        self.calls.append(pcm)
        if len(self.calls) == 1:
            self.entered.set()
            await self.release.wait()
            return "ilk mesaj"
        return "ikinci mesaj"


class SpeechLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_from_another_thread_is_dispatched_to_the_engine_loop(self):
        loop = asyncio.get_running_loop()
        owner = threading.get_ident()
        cancelled = asyncio.Event()
        def cancel():
            self.assertEqual(threading.get_ident(), owner, "Task cancellation must run on its owning loop")
            cancelled.set()
        engine = PipelineEngine(None)
        engine._gen = SimpleNamespace(done=lambda: False, get_loop=lambda: loop, cancel=cancel)
        try:
            await asyncio.to_thread(engine.interrupt)
            await asyncio.wait_for(cancelled.wait(), 2)
        finally:
            engine._gen = None
            await engine.close()

    async def test_overlapping_flushes_preserve_utterance_order(self):
        stt = DelayedSTT()
        engine = PipelineEngine(None, stt=stt)
        engine._queue_generation = Mock()
        first = second = None
        try:
            await engine.send_realtime_input(audio=b"\x01\0" * 20)
            first = asyncio.create_task(engine.flush_microphone())
            await asyncio.wait_for(stt.entered.wait(), 2)
            await engine.send_realtime_input(audio=b"\x02\0" * 20)
            second = asyncio.create_task(engine.flush_microphone())
            await asyncio.sleep(0)
            self.assertEqual(len(stt.calls), 1, "STT must not run two utterances concurrently")
            stt.release.set()
            self.assertEqual(await first, "ilk mesaj")
            self.assertEqual(await second, "ikinci mesaj")
            self.assertEqual([item["content"] for item in engine._history], ["ilk mesaj", "ikinci mesaj"])
            self.assertEqual(engine._queue_generation.call_count, 2)
        finally:
            stt.release.set()
            await asyncio.gather(*(task for task in (first, second) if task), return_exceptions=True)
            await engine.close()

    async def test_close_discards_inflight_and_queued_recognition_results(self):
        stt = DelayedSTT()
        engine = PipelineEngine(None, stt=stt)
        engine._queue_generation = Mock()
        await engine.send_realtime_input(audio=b"\x01\0" * 20)
        first = asyncio.create_task(engine.flush_microphone())
        await asyncio.wait_for(stt.entered.wait(), 2)
        await engine.send_realtime_input(audio=b"\x02\0" * 20)
        second = asyncio.create_task(engine.flush_microphone())
        await asyncio.sleep(0)
        await engine.close()
        stt.release.set()
        results = await asyncio.gather(first, second)
        self.assertEqual(results, ["", ""])
        self.assertEqual(len(stt.calls), 1)
        self.assertEqual(engine._history, [])
        engine._queue_generation.assert_not_called()

    async def test_failed_recognition_releases_the_queue_for_the_next_utterance(self):
        class FailingFirstSTT(DelayedSTT):
            async def transcribe(self, pcm, sample_rate):
                text = await super().transcribe(pcm, sample_rate)
                if text == "ilk mesaj":
                    raise RuntimeError("synthetic recognition failure")
                return text
        stt = FailingFirstSTT()
        logs = []
        engine = PipelineEngine(None, stt=stt, log=logs.append)
        engine._queue_generation = Mock()
        first = second = None
        try:
            await engine.send_realtime_input(audio=b"\x01\0" * 20)
            first = asyncio.create_task(engine.flush_microphone())
            await asyncio.wait_for(stt.entered.wait(), 2)
            await engine.send_realtime_input(audio=b"\x02\0" * 20)
            second = asyncio.create_task(engine.flush_microphone())
            await asyncio.sleep(0)
            self.assertEqual(len(stt.calls), 1)
            stt.release.set()
            self.assertEqual(await first, "")
            self.assertEqual(await second, "ikinci mesaj")
            self.assertEqual([item["content"] for item in engine._history], ["ikinci mesaj"])
            self.assertTrue(any("speech recognition" in line for line in logs))
        finally:
            stt.release.set()
            await asyncio.gather(*(task for task in (first, second) if task), return_exceptions=True)
            await engine.close()

    async def test_interrupt_cancels_active_tts_stream_without_late_audio(self):
        entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class LLM:
            caps = {}
            async def chat(self, *args, **kwargs):
                yield {"text": "Merhaba."}
        class TTS:
            async def speak(self, *args, **kwargs):
                try:
                    entered.set()
                    yield b"\0\0" * 8
                    await release.wait()
                    yield b"\0\0" * 8
                finally:
                    finished.set()
        engine = PipelineEngine(LLM(), tts=TTS())
        try:
            await engine.send_client_content(turns={"parts": [{"text": "Merhaba"}]})
            await asyncio.wait_for(entered.wait(), 2)
            task = engine._gen
            engine.interrupt()
            await asyncio.gather(task, return_exceptions=True)
            self.assertTrue(finished.is_set())
            release.set()
            await asyncio.sleep(0)
            output = []
            while not engine._queue.empty():
                output.append(engine._queue.get_nowait())
            self.assertEqual(sum(bool(message.data) for message in output), 1)
            self.assertFalse(engine.caps["barge_in"])
        finally:
            release.set()
            await engine.close()
