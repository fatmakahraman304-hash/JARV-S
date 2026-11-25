"""Synthetic PCM through the real pipeline entry point; no microphone/network."""
import math
from types import SimpleNamespace
import unittest
import numpy as np

from providers import audio
from providers.engine_pipeline import PipelineEngine, _VAD_MAX_TURN_S


class RecordingSTT:
    def __init__(self, fail=False):
        self.calls = []
        self.payloads = []
        self.fail = fail

    async def transcribe(self, pcm, sample_rate):
        self.calls.append((len(pcm), sample_rate))
        self.payloads.append(pcm)
        if self.fail:
            raise RuntimeError("synthetic STT failure")
        return ""


class PipelineAudioBounds(unittest.IsolatedAsyncioTestCase):
    async def ramp(self, engine):
        await engine.send_realtime_input(audio=bytes(2048))
        for index in range(485):
            amplitude = .01 * math.exp(math.log(90) * index / 484)
            pcm = np.full(1024, round(amplitude * 32767), dtype="<i2").tobytes()
            await engine.send_realtime_input(
                audio=SimpleNamespace(data=pcm, mime_type="audio/pcm;rate=16000"))

    async def test_continuous_voice_flushes_at_limit_without_waiting_for_silence(self):
        stt = RecordingSTT()
        engine = PipelineEngine(None, stt=stt)
        engine.auto_turn = True
        try:
            await self.ramp(engine)  # More than 30 seconds of PCM, processed without real-time sleep.
            maximum = int(audio.MIC_RATE * audio.SAMPLE_WIDTH * _VAD_MAX_TURN_S)
            self.assertEqual(len(stt.calls), 1)
            self.assertLessEqual(stt.calls[0][0], maximum + 2048)  # at most one input-frame overshoot
            self.assertEqual(stt.calls[0][1], audio.MIC_RATE)
            self.assertLess(engine._mic_bytes, maximum)
            self.assertEqual(engine._mic_bytes, sum(map(len, engine._mic)))
        finally:
            await engine.close()

    async def test_oversized_silent_frame_keeps_only_preroll_without_transcribing(self):
        stt = RecordingSTT()
        engine = PipelineEngine(None, stt=stt)
        engine.auto_turn = True
        try:
            await engine.send_realtime_input(audio=bytes(audio.MIC_RATE * audio.SAMPLE_WIDTH * 2))
            self.assertLessEqual(engine._mic_bytes, int(audio.MIC_RATE * .3) * audio.SAMPLE_WIDTH)
            self.assertEqual(stt.calls, [])
            self.assertEqual(engine._mic_bytes, sum(map(len, engine._mic)))
        finally:
            await engine.close()

    async def test_manual_input_waits_for_explicit_flush_and_close_clears_audio(self):
        stt = RecordingSTT()
        engine = PipelineEngine(None, stt=stt)
        pcm = np.full(320, 10000, dtype="<i2").tobytes()
        await engine.send_realtime_input(audio=pcm)
        self.assertEqual(stt.calls, [])
        await engine.flush_microphone()
        self.assertEqual(stt.calls, [(len(pcm), audio.MIC_RATE)])
        await engine.send_realtime_input(audio=pcm)
        await engine.close()
        self.assertEqual(engine._mic_bytes, 0)
        self.assertEqual(engine._mic, [])
        await engine.send_realtime_input(audio=pcm)
        self.assertEqual(engine._mic, [])

    async def test_stt_failure_at_limit_does_not_leave_old_audio_buffered(self):
        stt = RecordingSTT(fail=True)
        logs = []
        engine = PipelineEngine(None, stt=stt, log=logs.append)
        engine.auto_turn = True
        try:
            await self.ramp(engine)
            self.assertEqual(len(stt.calls), 1)
            self.assertTrue(any("speech recognition" in entry for entry in logs))
            self.assertLess(engine._mic_bytes, int(audio.MIC_RATE * audio.SAMPLE_WIDTH * _VAD_MAX_TURN_S))
        finally:
            await engine.close()

    async def test_partial_pcm_samples_do_not_corrupt_the_next_frame(self):
        stt = RecordingSTT()
        engine = PipelineEngine(None, stt=stt)
        try:
            await engine.send_realtime_input(audio=b"\xff")
            self.assertEqual(engine._mic_bytes, 0)
            await engine.send_realtime_input(audio=b"\x10\x00\xff")
            await engine.send_realtime_input(audio=b"\x20\x00")
            await engine.flush_microphone()
            self.assertEqual(stt.payloads, [b"\x10\x00\x20\x00"])
        finally:
            await engine.close()
