import base64
import json
import unittest
from collections import deque

from providers import realtime_transport as rt


class FakeSocket:
    def __init__(self, events):
        self.events = deque(events)
        self.sent = []

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        return json.dumps(self.events.popleft())


def delta(data):
    return {"type": "response.output_audio.delta", "delta": base64.b64encode(data).decode("ascii")}


def socket(*events):
    return FakeSocket([{"type": "session.created"}, {"type": "session.updated"}, *events])


class RealtimeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_to_ordered_pcm(self):
        pcm = b"\x01\x00" * 1300
        ws = socket(delta(pcm), delta(b"\x02\x00"),
                    {"type": "response.done", "response": {"status": "completed"}})
        parts = [part async for part in rt.exchange(ws, text="Merhaba")]
        self.assertEqual(list(map(len, parts)), [2400, 200, 2])
        self.assertEqual(b"".join(parts), pcm + b"\x02\x00")
        self.assertEqual([e["type"] for e in ws.sent],
                         ["session.update", "conversation.item.create", "response.create"])
        self.assertEqual(ws.sent[0]["session"]["audio"]["input"]["turn_detection"], None)
        self.assertEqual(ws.sent[0]["session"]["tools"], [])
        self.assertEqual(ws.sent[1]["item"]["content"][0]["text"], "Merhaba")

    def test_resamples_microphone_pcm(self):
        event = rt.input_event(pcm=b"\x00\x00" * 16000)
        data = base64.b64decode(event["item"]["content"][0]["audio"])
        self.assertEqual(len(data), 48000)

    def test_invalid_inputs(self):
        for kwargs in ({}, {"text": ""}, {"text": "a", "pcm": b"aa"},
                       {"pcm": b"a"}, {"pcm": b"\0" * (960000 + 2)}):
            with self.subTest(kwargs=kwargs.keys()), self.assertRaises(ValueError):
                rt.input_event(**kwargs)
        with self.assertRaises(ValueError):
            rt.session_event("unknown")

    async def test_server_error_does_not_expose_body(self):
        ws = socket({"type": "error", "error": {"message": "secret and transcript"}})
        with self.assertRaisesRegex(rt.RealtimeError, "^Realtime sunucusu isteği reddetti.$"):
            async for _ in rt.exchange(ws, text="hello"):
                pass

    async def test_no_audio_and_failed_response(self):
        for status in ("completed", "failed"):
            ws = socket({"type": "response.done", "response": {"status": status}})
            with self.assertRaises(rt.RealtimeError):
                async for _ in rt.exchange(ws, text="hello"):
                    pass

    async def test_invalid_pcm(self):
        for event in (delta(b"\x00"), {"type": "response.output_audio.delta", "delta": "!!!"}):
            ws = socket(event)
            with self.assertRaises(rt.RealtimeError):
                async for _ in rt.exchange(ws, text="hello"):
                    pass


if __name__ == "__main__":
    unittest.main()
