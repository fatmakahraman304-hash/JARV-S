import base64
import io
import json
import unittest
import wave
from unittest.mock import patch

import httpx

from providers import registry
from providers.tts_gemini import GeminiTTS, MODELS, URL, _decode_audio


def response_audio(pcm=b"\x01\x00" * 1300, rate=24000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return {"steps": [{"type": "model_output", "content": [
        {"type": "audio", "data": base64.b64encode(stream.getvalue()).decode("ascii")}
    ]}]}


class GeminiTTSTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, provider, handler, text="Merhaba."):
        original = httpx.AsyncClient
        with patch("httpx.AsyncClient", side_effect=lambda **kw: original(
                transport=httpx.MockTransport(handler), **kw)):
            return [piece async for piece in provider.speak(text)]

    async def test_documented_request_and_pcm(self):
        def handler(request):
            self.assertEqual(str(request.url), URL)
            self.assertEqual(request.headers["x-goog-api-key"], "test-only")
            self.assertNotIn("test-only", str(request.url))
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], MODELS[0])
            self.assertEqual(payload["input"][0]["content"][0]["text"], "Merhaba.")
            self.assertEqual(payload["generation_config"]["speech_config"], [{"voice": "Kore"}])
            return httpx.Response(200, json=response_audio())
        result = await self.collect(GeminiTTS({"api_key": "test-only"}), handler)
        self.assertEqual([len(p) for p in result], [2400, 200])
        self.assertEqual(b"".join(result), b"\x01\x00" * 1300)

    async def test_error_body_never_exposed(self):
        def handler(request):
            return httpx.Response(403, text="sensitive-key-and-transcript")
        with self.assertRaisesRegex(RuntimeError, "^Gemini TTS HTTP 403$"):
            await self.collect(GeminiTTS({"api_key": "test-only"}), handler)

    async def test_redirect_not_followed(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://example.org/"})
        with self.assertRaisesRegex(RuntimeError, "302"):
            await self.collect(GeminiTTS({"api_key": "test-only"}), handler)
        self.assertEqual(calls, [URL])

    async def test_missing_key_and_empty_text(self):
        def handler(request):
            self.fail("Network request not expected")
        self.assertEqual(await self.collect(GeminiTTS({}), handler, " "), [])
        with self.assertRaisesRegex(RuntimeError, "anahtarı"):
            await self.collect(GeminiTTS({}), handler)

    def test_invalid_audio(self):
        for payload in ({}, response_audio(rate=16000), response_audio(pcm=b"")):
            with self.assertRaises(RuntimeError):
                _decode_audio(payload)
        with self.assertRaises(RuntimeError):
            _decode_audio({"steps": [{"type": "model_output", "content": [
                {"type": "audio", "data": "!!!"}
            ]}]})

    def test_configuration_and_discovery(self):
        self.assertIn("gemini_tts", {x["id"] for x in registry.discover("tts")})
        with self.assertRaises(ValueError):
            GeminiTTS({"model": "invalid"})._payload("hello")
        with self.assertRaises(ValueError):
            GeminiTTS({})._payload("x" * 4001)

    def test_probe_uses_fixed_phrase(self):
        original = httpx.Client
        def handler(request):
            self.assertEqual(json.loads(request.content)["input"][0]["content"][0]["text"], "Merhaba.")
            return httpx.Response(200, json=response_audio())
        with patch("httpx.Client", side_effect=lambda **kw: original(
                transport=httpx.MockTransport(handler), **kw)):
            ok, message = GeminiTTS({"api_key": "test-only"}).probe()
        self.assertTrue(ok)
        self.assertIn("hoparlör test edilmedi", message)


if __name__ == "__main__":
    unittest.main()
