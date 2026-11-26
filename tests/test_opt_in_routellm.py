import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from core import gemini
from memory import config_manager as cfg
from providers import registry


class RouteLLMAccount(unittest.TestCase):
    def test_conversation_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            with patch.object(cfg, 'CONFIG_FILE', path):
                account = {'api_key': 'synthetic-abacus', 'allow_usage': '1'}
                cfg.save_provider_config('abacus_chat', account)
                instance = registry.build('abacus_chat', account)
                requests = []
                def respond(request):
                    requests.append(request)
                    return httpx.Response(200, json={'choices': [{'message': {'content': 'Merhaba'}}]})
                client = httpx.Client
                def transport(**kwargs):
                    return client(transport=httpx.MockTransport(respond), **kwargs)
                with patch.object(httpx, 'Client', side_effect=transport):
                    reply = gemini._provider_call('prov:abacus_chat', 'Selam', None, 3000)
                    self.assertEqual(reply.text, 'Merhaba')
                    self.assertEqual(str(requests[0].url), 'https://routellm.abacus.ai/v1/chat/completions')
                    self.assertEqual(json.loads(requests[0].content)['model'], 'route-llm')
                    self.assertEqual(requests[0].headers['authorization'], 'Bearer synthetic-abacus')
                    cfg._patch_config(local_only=True)
                    with self.assertRaisesRegex(ValueError, 'yerel'):
                        instance.complete([])
                    cfg._patch_config(local_only=False)
                    cfg.save_provider_config('abacus_chat', {'allow_usage': ''})
                    with self.assertRaisesRegex(ValueError, 'hesap ayarlarını'):
                        instance.complete([])
                    path.unlink()  # A backup still contains the former grant.
                    with self.assertRaisesRegex(ValueError, 'doğrulanamadı'):
                        instance.complete([])
                    self.assertEqual(len(requests), 1)

    def test_streamed_text_and_tool_share_one_request(self):
        import asyncio
        with tempfile.TemporaryDirectory() as directory, patch.object(
                cfg, 'CONFIG_FILE', Path(directory) / 'settings.json'):
            account = {'api_key': 'synthetic-stream', 'allow_usage': True}
            cfg.save_provider_config('abacus_chat', account)
            instance = registry.build('abacus_chat', account)
            received = []
            def respond(request):
                received.append(json.loads(request.content))
                deltas = [{'content': 'Saat'}, {'tool_calls': [{'index': 0, 'id': 'sample',
                          'function': {'name': 'clock', 'arguments': '{}'}}]}]
                frames = ['data: ' + json.dumps({'choices': [{'delta': delta}]}) for delta in deltas]
                return httpx.Response(200, text='\n\n'.join([*frames, 'data: [DONE]']))
            client = httpx.AsyncClient
            async def collect():
                return [part async for part in instance.chat([], tools=[{'type': 'function',
                        'function': {'name': 'clock', 'parameters': {'type': 'object'}}}])]
            with patch.object(httpx, 'AsyncClient', side_effect=lambda **kw:
                              client(transport=httpx.MockTransport(respond), **kw)):
                first, last = asyncio.run(collect())
            self.assertEqual(first, {'text': 'Saat'})
            self.assertEqual(last['tool_calls'][0].name, 'clock')
            self.assertEqual(len(received), 1)
            self.assertTrue(received[0]['stream'])
            self.assertEqual(received[0]['tools'][0]['function']['name'], 'clock')
