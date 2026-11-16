"""WhatsApp Business webhooks for Twilio messaging and inbound voice."""
import base64
import hashlib
import hmac
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree as xml

from memory.continuity import data_dir

MESSAGE = '/whatsapp/message'
VOICE = '/whatsapp/voice'
_NUMBER = re.compile(r'(?:whatsapp:)?(\+[1-9][0-9]{6,14})', re.ASCII | re.IGNORECASE)


def number(value):
    match = _NUMBER.fullmatch(value.strip())
    return match[1] if match else ''


def signature(url, fields, secret):
    data = url + ''.join(key + value for key in sorted(fields)
                         for value in sorted(set(fields[key])))
    return base64.b64encode(hmac.digest(secret.encode(), data.encode(), hashlib.sha1)).decode()


def words(value):
    value = value.lower().replace('ı', 'i')
    value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
    return set(re.findall(r'\w+', value))


class Assistant:
    def __init__(self, origin, secret, receiver, settings, database=None):
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment or not secret):
            raise ValueError('Dış adres yalnızca HTTPS alan adı olmalı. Twilio Auth Token gerekli.')
        self.origin = origin.rstrip('/')
        self.secret = secret
        self.receiver = number(receiver)
        if not self.receiver:
            raise ValueError('WhatsApp Business numarasını +90… biçiminde gir.')
        self.settings = settings
        self.database = database or data_dir() / 'whatsapp-webhooks.sqlite3'
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS replied (sid TEXT PRIMARY KEY, created INTEGER NOT NULL)')

    def claim_message(self, sid):
        now = int(time.time())
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DELETE FROM replied WHERE created < ?', (now - 7 * 86400,))
            return db.execute('INSERT OR IGNORE INTO replied VALUES (?, ?)', (sid, now)).rowcount == 1

    def dispatch(self, target, form, provided_signature):
        routes = {MESSAGE, VOICE} | {f'{VOICE}?turn={i}' for i in range(1, 6)}
        if target not in routes:
            return 404, b''
        expected = signature(self.origin + target, form, self.secret)
        if not hmac.compare_digest(expected.encode(), provided_signature.encode()):
            return 403, b''
        response = xml.Element('Response')
        get = lambda key: form.get(key, [''])[0]
        sender = number(get('From'))
        if (not sender or sender == self.receiver or number(get('To')) != self.receiver
                or (target == MESSAGE and not get('From').lower().startswith('whatsapp:'))):
            return 200, xml.tostring(response)
        settings = self.settings()
        if target == MESSAGE:
            sid = get('MessageSid')
            body = settings.get('message', '').strip()
            if (settings.get('messages_enabled') and body
                    and re.fullmatch(r'(?:SM|MM)[0-9a-fA-F]{32}', sid) and self.claim_message(sid)):
                xml.SubElement(response, 'Message').text = body[:1500]
        elif settings.get('voice_enabled') and re.fullmatch(r'CA[0-9a-fA-F]{32}', get('CallSid')):
            turn = int(target.rsplit('=', 1)[1]) if '?' in target else 0
            self.voice(response, turn, get('SpeechResult')[:1000], settings.get('faq', ''))
        else:
            xml.SubElement(response, 'Reject', reason='busy')
        return 200, xml.tostring(response, encoding='utf-8')

    def voice(self, response, turn, speech, faq):
        def say(parent, text):
            xml.SubElement(parent, 'Say', language='tr-TR', voice='Polly.Burcu-Neural').text = text

        terms = words(speech)
        if terms & {'gorusuruz', 'hoscakal'} or {'iyi', 'gunler'} <= terms:
            say(response, 'Görüşmek üzere.')
            xml.SubElement(response, 'Hangup')
            return
        if not turn:
            answer = (f'Merhaba, ben {assistant_name()}, otomatik sesli asistan. '
                      'Size nasıl yardımcı olabilirim?')
        else:
            match = []
            for line in faq.splitlines():
                question, separator, reply = line.partition('=')
                keywords = words(question)
                if separator and keywords and keywords <= terms and reply.strip():
                    match.append((len(keywords), reply.strip()))
            answer = (max(match)[1][:500] if match else
                      'Bu konuda doğrulanmış bir bilgim yok. WhatsApp üzerinden yazılı mesaj bırakabilirsiniz.')
        if turn >= 5:
            say(response, answer + ' Görüşmek üzere.')
        else:
            gather = xml.SubElement(response, 'Gather', input='speech', language='tr-TR',
                                    speechModel='googlev2_short', speechTimeout='2', timeout='5', method='POST',
                                    action=f'{self.origin}{VOICE}?turn={turn + 1}')
            say(gather, answer)
            say(response, 'Ses alamadım. Görüşmek üzere.')
        xml.SubElement(response, 'Hangup')


def server(assistant, port):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(10)
            super().setup()

        def log_request(self, code='-', size='-'):
            # A public caller controls the raw URL. Log only known identifiers.
            if self.path.split('?', 1)[0] in (MESSAGE, VOICE):
                self.log_message('WhatsApp webhook HTTP %s', code)

        def do_POST(self):
            payload = b''
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    status = 413
                elif self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                    status = 415
                else:
                    fields = parse_qs(self.rfile.read(size).decode(), keep_blank_values=True,
                                      max_num_fields=250, errors='strict')
                    status, payload = assistant.dispatch(self.path, fields,
                                                         self.headers.get('X-Twilio-Signature', ''))
            except (ValueError, UnicodeError):
                status = 400
            except sqlite3.Error:
                status = 503
            self.send_response(status)
            self.send_header('Content-Type', 'text/xml; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def assistant_name():
    """The name the user gave the assistant (Settings), for what callers hear."""
    try:
        from memory.config_manager import get_assistant_name
        return (get_assistant_name() or 'JARVIS').strip() or 'JARVIS'
    except Exception:
        return 'JARVIS'


def load_settings():
    from memory.config_manager import load_api_keys
    value = load_api_keys().get('whatsapp_assistant', {})
    return value if isinstance(value, dict) else {}


_listener = None


def start_listener():
    """Bind once per desktop process. Toggles and replies are read on each request."""
    import threading

    global _listener
    settings = load_settings()
    if not (settings.get('messages_enabled') or settings.get('voice_enabled')):
        return 'Otomatik yanıt ve arama kapalı.'
    connection = (settings.get('origin', ''), settings.get('secret', ''),
                  settings.get('receiver', ''), 8769)
    if _listener:
        if _listener[0] != connection:
            return 'Yeni bağlantı bilgilerini uygulamak için uygulamayı yeniden başlat.'
        return f'Yerel dinleyici açık ({connection[3]}). Twilio bağlantısı henüz doğrulanmadı.'
    def active_settings():
        current = load_settings()
        if (current.get('origin'), current.get('secret'), current.get('receiver')) != connection[:3]:
            return {}
        return current

    try:
        assistant = Assistant(*connection[:3], settings=active_settings)
    except sqlite3.Error as exc:
        raise OSError("WhatsApp tekrar denetimi veritabanı açılamadı.") from exc
    httpd = server(assistant, connection[3])
    thread = threading.Thread(target=httpd.serve_forever, name='whatsapp-assistant', daemon=True)
    try:
        thread.start()
    except RuntimeError:
        httpd.server_close()
        raise
    _listener = connection, httpd
    return f'Yerel dinleyici açıldı ({connection[3]}). Twilio bağlantısı henüz doğrulanmadı.'
