"""Exercise production audio queue methods without opening microphone/speaker."""
import asyncio
from types import SimpleNamespace
import unittest

from tests._main_import import load_main


class LiveAudioBounds(unittest.IsolatedAsyncioTestCase):
    def make(self, size=2):
        live = load_main().FridayLive
        fake = SimpleNamespace(out_queue=asyncio.Queue(maxsize=size),
                               audio_in_queue=asyncio.Queue(maxsize=size),
                               _awake=True, _interrupted=False, _playback_epoch=0)
        return live, fake

    async def test_upload_overload_keeps_recent_audio_and_counts_loss(self):
        live, fake = self.make()
        for number in range(10000):
            live._queue_mic_audio(fake, fake.out_queue, {"data": number})
        self.assertEqual(fake.out_queue.qsize(), 2)
        self.assertEqual(fake._mic_dropped_chunks, 9998)
        self.assertEqual([fake.out_queue.get_nowait()["data"] for _ in range(2)], [9998, 9999])

    async def test_previous_session_callback_cannot_write_into_replacement_queue(self):
        live, fake = self.make()
        old = fake.out_queue
        fake.out_queue = asyncio.Queue(maxsize=2)
        live._queue_mic_audio(fake, old, {"data": b"stale"})
        self.assertTrue(old.empty())
        self.assertTrue(fake.out_queue.empty())

    async def test_slow_playback_preserves_pcm_and_allows_other_tasks(self):
        live, fake = self.make()
        pcm = bytes(range(256)) * 200
        producer = asyncio.create_task(live._queue_playback_audio(fake, pcm))
        await asyncio.sleep(0)
        self.assertFalse(producer.done())
        self.assertEqual(fake.audio_in_queue.qsize(), 2)
        parts = []
        async def consume():
            while sum(map(len, parts)) < len(pcm):
                parts.append(await fake.audio_in_queue.get())
                await asyncio.sleep(0)
        try:
            await asyncio.wait_for(asyncio.gather(producer, consume()), 3)
            self.assertEqual(b"".join(parts), pcm)
            self.assertTrue(all(len(part) <= 2400 for part in parts))
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    async def test_interrupt_then_new_turn_does_not_resume_blocked_old_speech(self):
        live, fake = self.make(1)
        producer = asyncio.create_task(live._queue_playback_audio(fake, b"\x01\0" * 5000))
        await asyncio.sleep(0)
        fake.set_speaking = lambda value: None
        fake._visemes = SimpleNamespace(reset=lambda: None)
        fake._turn_done_event = None
        fake._engine = None
        fake.ui = SimpleNamespace(write_log=lambda text: None)
        live.interrupt(fake)
        fake._interrupted = False  # next turn may already have started
        await asyncio.wait_for(producer, 1)
        self.assertTrue(fake.audio_in_queue.empty())

    async def test_session_replacement_and_cancellation_release_backpressure(self):
        live, fake = self.make(1)
        producer = asyncio.create_task(live._queue_playback_audio(fake, b"a" * 10000))
        await asyncio.sleep(0)
        fake.audio_in_queue = asyncio.Queue(maxsize=1)
        await asyncio.wait_for(producer, 1)
        self.assertTrue(fake.audio_in_queue.empty())
        producer = asyncio.create_task(live._queue_playback_audio(fake, b"b" * 10000))
        await asyncio.sleep(0)
        producer.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await producer
