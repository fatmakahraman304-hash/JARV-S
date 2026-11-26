import asyncio
import unittest

from providers.realtime_local_turns import LocalTurns, FRAME_BYTES, START_FRAMES, END_FRAMES, MAX_FRAMES
from providers.engine_realtime import RealtimeEngine
from providers.base import Msg

SILENCE = b"\0" * FRAME_BYTES
VOICE = b"\x00\x10" * (FRAME_BYTES // 2)


class LocalTurnTests(unittest.TestCase):
    def test_silence_and_short_noise_do_not_trigger(self):
        vad = LocalTurns()
        self.assertEqual(list(vad.feed(SILENCE * 80)), [])
        self.assertEqual(list(vad.feed(VOICE * (START_FRAMES - 1) + SILENCE * 80)), [])

    def test_fragmented_frames_and_trailing_silence(self):
        vad = LocalTurns()
        utterance = VOICE * START_FRAMES + SILENCE * END_FRAMES
        results = []
        for start in range(0, len(utterance), 218):
            results.extend(vad.feed(utterance[start:start + 218]))
        self.assertEqual(results, [utterance])

    def test_reset_discards_previous_audio(self):
        vad = LocalTurns()
        list(vad.feed(VOICE * START_FRAMES))
        vad.reset()
        self.assertEqual(list(vad.feed(SILENCE * END_FRAMES)), [])

    def test_overlong_turn_is_discarded_not_split(self):
        vad = LocalTurns()
        self.assertEqual(list(vad.feed(VOICE * (MAX_FRAMES + 20))), [])
        self.assertEqual(list(vad.feed(SILENCE * END_FRAMES)), [])
        self.assertEqual(len(list(vad.feed(VOICE * START_FRAMES + SILENCE * END_FRAMES))), 1)


class Session:
    def __init__(self):
        self.requests = []
    async def turn(self, **request):
        self.requests.append(request)
        yield Msg.turn_end()
    async def close(self):
        pass


class HandsFreeTests(unittest.IsolatedAsyncioTestCase):
    async def test_opt_in_submits_only_completed_utterance(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        self.assertFalse(engine.auto_turn)
        engine.auto_turn = True
        await engine.send_realtime_input(audio=SILENCE * 80)
        self.assertIsNone(engine._gen)
        await engine.send_realtime_input(audio=VOICE * START_FRAMES)
        self.assertIsNone(engine._gen)
        await engine.send_realtime_input(audio=SILENCE * END_FRAMES)
        await asyncio.wait_for(engine._gen, 2)
        self.assertEqual(len(session.requests), 1)
        self.assertTrue(session.requests[0]["pcm"].endswith(SILENCE * END_FRAMES))

    async def test_discard_capture_prevents_submission(self):
        session = Session()
        engine = RealtimeEngine(session)
        self.addAsyncCleanup(engine.close)
        engine.auto_turn = True
        await engine.send_realtime_input(audio=VOICE * START_FRAMES)
        engine.discard_capture()
        await engine.send_realtime_input(audio=SILENCE * END_FRAMES)
        self.assertIsNone(engine._gen)
        self.assertEqual(session.requests, [])
