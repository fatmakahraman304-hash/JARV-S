"""Model read-ahead is bounded, ordered, and tied to the generation lifetime."""
import asyncio
import unittest

from providers.engine_pipeline import PipelineEngine, _prefetched_chat


class ReadAheadTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_ahead_is_bounded_and_ordered(self):
        seen = []
        async def source():
            for i in range(100):
                seen.append(i)
                yield i
        async with _prefetched_chat(source()) as events:
            await asyncio.sleep(0)
            self.assertGreater(len(seen), 1)
            self.assertLessEqual(len(seen), 17)
            self.assertEqual([value async for value in events], list(range(100)))

    async def test_early_exit_closes_blocked_reader(self):
        closed = asyncio.Event()
        async def source():
            try:
                for i in range(100):
                    yield i
            finally:
                closed.set()
        async with _prefetched_chat(source()) as events:
            self.assertEqual(await anext(events), 0)
            await asyncio.sleep(0)
        self.assertTrue(closed.is_set())

    async def test_provider_failure_preserves_prior_events(self):
        async def source():
            yield "first"
            raise ValueError("provider failed")
        with self.assertRaisesRegex(ValueError, "provider failed"):
            async with _prefetched_chat(source()) as events:
                self.assertEqual(await anext(events), "first")
                await anext(events)

    async def test_model_can_continue_during_first_sentence_synthesis(self):
        voice_entered = asyncio.Event()
        second_read = asyncio.Event()
        release_voice = asyncio.Event()

        class LLM:
            caps = {}
            async def chat(self, *args, **kwargs):
                yield {"text": "Merhaba. "}
                await voice_entered.wait()
                second_read.set()
                yield {"text": "Nasılsın? "}

        class Voice:
            async def speak(self, text):
                if "Merhaba" in text:
                    voice_entered.set()
                    await release_voice.wait()
                yield b"\x01\x00"

        engine = PipelineEngine(LLM(), tts=Voice())
        try:
            await engine.send_client_content(turns={"parts": [{"text": "Selam"}]})
            await asyncio.wait_for(second_read.wait(), 2)
            release_voice.set()
            await asyncio.wait_for(engine._gen, 2)
            messages = []
            while not engine._queue.empty():
                messages.append(engine._queue.get_nowait())
            transcripts = [m.server_content.output_transcription.text for m in messages
                           if m.server_content and m.server_content.output_transcription]
            self.assertEqual(transcripts, ["Merhaba.", "Nasılsın?"])
        finally:
            release_voice.set()
            await engine.close()

    async def test_cancel_closes_model_and_voice(self):
        entered = asyncio.Event()
        reader_closed = asyncio.Event()
        voice_closed = asyncio.Event()
        wait = asyncio.Event()

        class LLM:
            caps = {}
            async def chat(self, *args, **kwargs):
                try:
                    yield {"text": "Merhaba. "}
                    await wait.wait()
                finally:
                    reader_closed.set()

        class Voice:
            async def speak(self, text):
                try:
                    entered.set()
                    await wait.wait()
                    yield b"\x00\x00"
                finally:
                    voice_closed.set()

        engine = PipelineEngine(LLM(), tts=Voice())
        try:
            await engine.send_client_content(turns={"parts": [{"text": "Selam"}]})
            await asyncio.wait_for(entered.wait(), 2)
            task = engine._gen
            engine.interrupt()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)
            self.assertTrue(reader_closed.is_set())
            self.assertTrue(voice_closed.is_set())
        finally:
            wait.set()
            await engine.close()


if __name__ == "__main__":
    unittest.main()
