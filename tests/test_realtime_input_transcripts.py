import base64
import json
import unittest
from collections import deque

from providers.realtime_session import RealtimeSession
from providers.realtime_settings import validate_settings


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


def committed(item_id="input_1"):
    return {"type": "input_audio_buffer.committed", "item_id": item_id}


def transcript(text, item_id="input_1"):
    return {"type": "conversation.item.input_audio_transcription.completed",
            "item_id": item_id, "content_index": 0, "transcript": text}


def reply(rid="r1"):
    return [
        {"type": "response.created", "response": {"id": rid}},
        {"type": "response.output_audio.delta", "response_id": rid,
         "delta": base64.b64encode(b"\x01\x00").decode()},
        {"type": "response.output_audio_transcript.done", "response_id": rid, "transcript": "Merhaba"},
        {"type": "response.done", "response": {"id": rid, "status": "completed"}},
    ]


class InputTranscriptTests(unittest.IsolatedAsyncioTestCase):
    async def open(self, events, callback=None):
        ws = Socket(events)
        session = RealtimeSession(ws, input_transcript=callback)
        self.addAsyncCleanup(session.close)
        await session.start()
        return ws, session

    async def test_separate_consent_requires_microphone(self):
        cfg = {"api_key": "test-only", "cloud_consent": True}
        self.assertFalse(validate_settings(cfg)["input_transcription"])
        self.assertFalse(validate_settings(dict(cfg, input_transcription=True))["input_transcription"])
        self.assertTrue(validate_settings(dict(cfg, microphone=True, input_transcription=True))["input_transcription"])

    async def test_audio_commit_and_matching_transcript_after_response(self):
        records = []
        ws, session = await self.open([committed(), *reply(), transcript("old", "old_item"),
                                       transcript("Merhaba")], records.append)
        events = [m async for m in session.turn(pcm=b"\x01\x00" * 1600)]
        self.assertEqual(records, ["Merhaba"])
        self.assertEqual(ws.sent[0]["session"]["audio"]["input"]["transcription"],
                         {"model": "gpt-transcribe"})
        self.assertEqual([e["type"] for e in ws.sent],
                         ["session.update", "input_audio_buffer.append", "input_audio_buffer.commit", "response.create"])
        self.assertTrue(events[-1].server_content.turn_complete)
        self.assertFalse(any(m.server_content and m.server_content.input_transcription for m in events))

    async def test_early_transcript_and_duplicate_are_recorded_once(self):
        records = []
        _, session = await self.open([committed(), transcript("first"), transcript("duplicate"), *reply()],
                                     records.append)
        _ = [m async for m in session.turn(pcm=b"\x01\x00" * 1600)]
        self.assertEqual(records, ["first"])

    async def test_failed_transcription_does_not_fail_audio_response(self):
        records = []
        failure = {"type": "conversation.item.input_audio_transcription.failed",
                   "item_id": "input_1", "content_index": 0}
        _, session = await self.open([committed(), failure, *reply()], records.append)
        events = [m async for m in session.turn(pcm=b"\x01\x00" * 1600)]
        self.assertEqual(records, [])
        self.assertTrue(events[-1].server_content.turn_complete)

    async def test_default_voice_path_unchanged_and_text_not_transcribed(self):
        ws, session = await self.open(reply())
        _ = [m async for m in session.turn(pcm=b"\x01\x00" * 1600)]
        self.assertNotIn("transcription", ws.sent[0]["session"]["audio"]["input"])
        self.assertEqual(ws.sent[1]["type"], "conversation.item.create")
        records = []
        ws, session = await self.open([transcript("old"), *reply()], records.append)
        _ = [m async for m in session.turn(text="Merhaba")]
        self.assertEqual(records, [])
        self.assertEqual(ws.sent[1]["item"]["content"][0]["type"], "input_text")
