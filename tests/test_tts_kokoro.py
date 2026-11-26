import json
import unittest
from unittest.mock import patch

import httpx

from providers import registry
from providers.tts_kokoro import KokoroTTS, _endpoint


class KokoroTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, provider, handler, text="hello"):
        original = httpx.AsyncClient
        with patch("httpx.AsyncClient", side_effect=lambda **kw: original(
                transport=httpx.MockTransport(handler), **kw)):
            return [part async for part in provider.speak(text)]

    async def test_stream_pcm_without_credentials(self):
        def handler(request):
            self.assertEqual(str(request.url), "http://127.0.0.1:8880/v1/audio/speech")
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(json.loads(request.content), {
                "model": "kokoro", "input": "hello", "voice": "af_heart", "response_format": "pcm"})
            return httpx.Response(200, headers={"Content-Type": "audio/pcm"},
                                  content=b"\x01\x00" * 1300)
        chunks = await self.collect(KokoroTTS({"api_key": "never-send"}), handler)
        self.assertEqual([len(c) for c in chunks], [2400, 200])
        self.assertEqual(b"".join(chunks), b"\x01\x00" * 1300)

    async def test_invalid_content_type(self):
        def handler(request):
            return httpx.Response(200, json={"text": "not audio"})
        with self.assertRaisesRegex(RuntimeError, "yanıt biçimi"):
            await self.collect(KokoroTTS({}), handler)

    async def test_empty_and_odd_pcm(self):
        for data in (b"", b"\x01"):
            with self.subTest(data=data):
                def handler(request):
                    return httpx.Response(200, headers={"Content-Type": "audio/pcm"}, content=data)
                with self.assertRaisesRegex(RuntimeError, "boş veya eksik"):
                    await self.collect(KokoroTTS({}), handler)

    async def test_redirect_never_followed(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://example.com/"})
        with self.assertRaisesRegex(RuntimeError, "302"):
            await self.collect(KokoroTTS({}), handler)
        self.assertEqual(len(calls), 1)

    async def test_empty_text_does_not_request(self):
        def handler(request):
            self.fail("Unexpected request")
        self.assertEqual(await self.collect(KokoroTTS({}), handler, " "), [])

    def test_endpoint_and_registry(self):
        self.assertEqual(_endpoint("http://[::1]:8880"), "http://[::1]:8880/v1/audio/speech")
        for url in ("https://example.com/v1", "http://localhost:8880/v1",
                    "http://u:p@127.0.0.1:8880", "http://127.0.0.1:8880/v1?a=b"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _endpoint(url)
        self.assertIn("kokoro", {item["id"] for item in registry.discover("tts")})

    def test_probe_checks_response(self):
        original = httpx.Client
        def handler(request):
            self.assertEqual(json.loads(request.content)["input"], "Hello.")
            return httpx.Response(200, headers={"Content-Type": "audio/pcm"},
                                  content=b"\x00\x00" * 2400)
        with patch("httpx.Client", side_effect=lambda **kw: original(
                transport=httpx.MockTransport(handler), **kw)):
            ok, message = KokoroTTS({}).probe()
        self.assertTrue(ok)
        self.assertIn("çalma test edilmedi", message)


if __name__ == "__main__":
    unittest.main()
