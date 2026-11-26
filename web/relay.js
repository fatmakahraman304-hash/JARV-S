/* FRIDAY HTTPS projector control — encrypted relay, no new page or GitHub API.
 *
 * Android FRIDAY Alıcı subscribes to an opaque topic on ntfy.sh; this HTTPS
 * page publishes AES-256-GCM encrypted commands and receives encrypted replies.
 * The existing local pairing secret is held only in browser localStorage and
 * on the projector; it is never sent to the relay.
 */
(() => {
  'use strict';
  const ROOT = 'https://ntfy.sh/';
  const enc = new TextEncoder(), dec = new TextDecoder();
  const state = { secret: '', cmd: '', res: '', key: null, stream: null, ready: null,
    status: 'kapalı', pending: new Map() };

  const hex = bytes => [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  const hash = async text => new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(text)));
  const base64Url = b => btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const fromBase64Url = text => {
    const raw = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4));
    return Uint8Array.from(raw, c => c.charCodeAt(0));
  };

  async function seal(obj) {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ct = new Uint8Array(await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: nonce }, state.key, enc.encode(JSON.stringify(obj))));
    const packed = new Uint8Array(nonce.length + ct.length);
    packed.set(nonce); packed.set(ct, nonce.length);
    return base64Url(packed);
  }
  async function open(packed) {
    const bytes = fromBase64Url(packed);
    if (bytes.length < 29 || bytes.length > 6000) throw new Error('bad ciphertext');
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: bytes.subarray(0, 12) }, state.key, bytes.subarray(12));
    return JSON.parse(dec.decode(plain));
  }
  function reset() {
    if (state.stream) { state.stream.close(); state.stream = null; }
    for (const item of state.pending.values()) {
      clearTimeout(item.timer);
      item.resolve('Bağlantı değişti, komut iptal edildi.');
    }
    state.pending.clear();
    state.ready = null; state.secret = ''; state.status = 'kapalı'; state.key = null;
  }
  async function configure(url) {
    const u = new URL(url);
    const secret = u.pathname.replace(/^\//, '').replace(/\/$/, '');
    if (!/^[a-f0-9]{32,64}$/i.test(secret) || !crypto?.subtle || !window.EventSource)
      throw new Error('Bu cihazda şifreli HTTPS kontrolü desteklenmiyor.');
    if (secret === state.secret && state.stream) return state.ready;
    reset();
    state.secret = secret;
    const [cmd, res, keyBytes] = await Promise.all([
      hash('aether-v1-cmd:' + secret), hash('aether-v1-res:' + secret), hash('aether-v1-key:' + secret)
    ]);
    state.cmd = 'aether-' + hex(cmd).slice(0, 40);
    state.res = 'aether-' + hex(res).slice(0, 40);
    state.key = await crypto.subtle.importKey('raw', keyBytes, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
    state.status = 'bağlanıyor';
    let readyResolve, readyReject;
    state.ready = new Promise((resolve, reject) => {
      readyResolve = resolve; readyReject = reject;
    });
    // Capture replies sent during short Internet interruptions. IDs and
    // timestamps are checked after authenticated decryption.
    const stream = new EventSource(ROOT + state.res + '/sse?since=20s');
    state.stream = stream;
    let initialized = false;
    const startupTimeout = setTimeout(() => {
      if (!initialized) {
        initialized = true;
        state.status = 'bağlantı kurulamadı';
        stream.close();
        if (state.stream === stream) { state.stream = null; state.secret = ''; }
        readyReject(new Error('HTTPS köprüsü yanıt vermedi.'));
      }
    }, 9000);
    stream.onopen = () => {
      state.status = 'bağlı';
      if (!initialized) { initialized = true; clearTimeout(startupTimeout); readyResolve(); }
    };
    stream.onerror = () => { state.status = 'yeniden bağlanıyor'; };
    stream.onmessage = async e => {
      let event;
      try { event = JSON.parse(e.data); } catch { return; }
      if (event.event !== 'message' || !event.message) return;
      try {
        const message = await open(event.message);
        if (message.v !== 1 || typeof message.id !== 'string'
            || Math.abs(Date.now() - Number(message.ts)) > 120000) return;
        const item = state.pending.get(message.id);
        if (!item) return;
        state.pending.delete(message.id);
        clearTimeout(item.timer);
        item.resolve(String(message.reply || 'Komut tamamlandı.').slice(0, 400));
      } catch { /* Ignore unauthenticated or unrelated topic messages. */ }
    };
    return state.ready;
  }

  async function send(url, op, arg, options = {}) {
    if (!['key', 'app', 'search', 'url', 'type'].includes(op)) {
      return 'Bu işlem için yerel HTTPS komut köprüsü desteklenmiyor.';
    }
    if (!navigator.onLine) return 'İnternet yok. Wi-Fi kumandasını doğrudan açıp kullanabilirsin.';
    try {
      await configure(url);
      const id = hex(crypto.getRandomValues(new Uint8Array(16)));
      const where = ['youtube', 'chrome', 'google'].includes(options.where) ? options.where : 'youtube';
      const payload = await seal({ v: 1, id, ts: Date.now(), op, arg: String(arg || '').slice(0, 1000), where });
      const result = new Promise(resolve => {
        const timer = setTimeout(() => {
          state.pending.delete(id);
          resolve('Projeksiyon HTTPS komutuna yanıt vermedi. FRIDAY Alıcı içindeki HTTPS köprü durumunu kontrol et.');
        }, 16000);
        state.pending.set(id, { resolve, timer });
      });
      let response;
      try {
        response = await fetch(ROOT + state.cmd, {
          method: 'POST', mode: 'cors', credentials: 'omit', cache: 'no-store',
          referrerPolicy: 'no-referrer', headers: { 'Content-Type': 'text/plain' }, body: payload
        });
        if (!response.ok) throw new Error('HTTPS ileti servisi HTTP ' + response.status);
      } catch (e) {
        const item = state.pending.get(id);
        if (item) { clearTimeout(item.timer); state.pending.delete(id); item.resolve('HTTPS gönderimi başarısız: ' + (e.message || e)); }
      }
      return await result;
    } catch (e) {
      return 'HTTPS kumanda bağlantısı kurulamadı: ' + (e.message || e) + '. Yerel kumanda düğmesi çalışmaya devam eder.';
    }
  }

  window.FRIDAYRelay = { send, configure, get status() { return state.status; }, reset };
})();
