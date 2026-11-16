import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as xml

from core.whatsapp_assistant import Assistant, MESSAGE, VOICE, server, signature


class BusinessAssistantTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.settings = {'messages_enabled': True, 'voice_enabled': True,
                         'message': 'Merhaba & hoş geldiniz', 'faq': 'çalışma saatleri = Saat 9 ile 18 arası.'}
        self.bot = Assistant('https://example.org', 'sample-secret', '+905551111111',
                             lambda: self.settings, Path(temp.name) / 'data.sqlite3')
        self.form = {'From': ['whatsapp:+905552222222'], 'To': ['whatsapp:+905551111111'],
                     'MessageSid': ['SM' + '1'*32], 'CallSid': ['CA' + '1'*32]}

    def event(self, path):
        auth = signature(self.bot.origin + path, self.form, self.bot.secret)
        status, body = self.bot.dispatch(path, self.form, auth)
        self.assertEqual(status, 200)
        return xml.fromstring(body)

    def test_message_over_http_and_retry_is_suppressed(self):
        with server(self.bot, 0) as listener:
            thread = threading.Thread(target=listener.serve_forever, daemon=True)
            thread.start()
            try:
                auth = signature(self.bot.origin + MESSAGE, self.form, self.bot.secret)
                request = Request(f'http://127.0.0.1:{listener.server_port}{MESSAGE}',
                                  data=urlencode(self.form, doseq=True).encode(),
                                  headers={'X-Twilio-Signature': auth})
                with urlopen(request, timeout=4) as response:
                    self.assertEqual(xml.fromstring(response.read()).findtext('Message'), self.settings['message'])
                with urlopen(request, timeout=4) as response:
                    self.assertIsNone(xml.fromstring(response.read()).find('Message'))
            finally:
                listener.shutdown()
                thread.join()

    def test_signature_and_sender_scope(self):
        self.assertEqual(self.bot.dispatch(MESSAGE, self.form, 'wrong')[0], 403)
        self.form['To'] = ['whatsapp:+905553333333']
        self.assertIsNone(self.event(MESSAGE).find('Message'))

    def test_voice_greets_then_answers_and_honors_switch(self):
        gather = self.event(VOICE).find('Gather')
        self.assertIn('otomatik sesli asistan', gather.findtext('Say'))
        self.assertEqual(gather.attrib['action'], self.bot.origin + VOICE + '?turn=1')
        self.form['SpeechResult'] = ['Çalışma saatleri nedir?']
        self.assertIn('Saat 9', self.event(VOICE + '?turn=1').findtext('./Gather/Say'))
        self.settings['voice_enabled'] = False
        self.assertIsNotNone(self.event(VOICE).find('Reject'))
