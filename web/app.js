/* JARVIS — the same assistant on every device.
 *
 * This page is the whole assistant for a phone, tablet, TV, projector or watch.
 * Its brain is Gemini Live, reached straight from the device, so it works when
 * the computer is off. What every device shares — long-term memory, the recent
 * conversation, who is online and the mailbox to the computers — lives in one
 * secret gist on the user's GitHub account (desktop side: core/sync_hub.py).
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const LIVE_MODELS = ['models/gemini-3.1-flash-live-preview', 'models/gemini-2.5-flash-native-audio-preview-12-2025'];
  const WS_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=';
  const GH = 'https://api.github.com';

  // ── settings ─────────────────────────────────────────────────────────────
  const S = (() => { try { return JSON.parse(localStorage.getItem('jarvis_web') || '{}'); } catch { return {}; } })();
  const save = () => localStorage.setItem('jarvis_web', JSON.stringify(S));
  if (!S.id) { S.id = 'w' + Math.random().toString(36).slice(2, 12); save(); }
  if (!S.voice) S.voice = 'Charon';
  (function importSetupLink() {
    const m = location.hash.match(/[#&]s=([A-Za-z0-9_-]+)/);
    if (!m) return;
    try {
      const b = m[1].replace(/-/g, '+').replace(/_/g, '/');
      const j = JSON.parse(decodeURIComponent(escape(atob(b + '==='.slice((b.length + 3) % 4)))));
      if (j.g) S.key = j.g; if (j.t) S.tok = j.t; if (j.i) S.gist = j.i; if (j.n) S.name = j.n;
      save(); setTimeout(() => toast('Kurulum tamam — JARVIS bu cihazda hazır'), 600);
    } catch { setTimeout(() => toast('Kurulum bağlantısı okunamadı'), 600); }
    history.replaceState(null, '', location.pathname);
  })();

  function detectKind() {
    if (S.kind && S.kind !== 'auto') return S.kind;
    const ua = navigator.userAgent;
    if (/SmartTV|SMART-TV|Tizen|Web0S|WebOS|HbbTV|BRAVIA|AFT[A-Z]|GoogleTV|Android TV|CrKey|Roku/i.test(ua)) return 'tv';
    const w = Math.min(screen.width, screen.height), h = Math.max(screen.width, screen.height);
    if (h <= 520 && w <= 520) return 'watch';
    const touch = navigator.maxTouchPoints > 0;
    if (touch && w >= 600) return 'tablet';
    if (touch) return 'phone';
    return 'pc';
  }
  const KIND_NAMES = { phone: 'Telefon', tablet: 'Tablet', tv: 'Televizyon', projector: 'Projeksiyon', watch: 'Akıllı saat', pc: 'Bilgisayar' };
  const ICON = { phone: '📱', tablet: '📱', tv: '📺', projector: '📽️', watch: '⌚', pc: '💻' };
  let KIND = detectKind();
  function applyKind() {
    KIND = detectKind();
    document.body.classList.toggle('big', KIND === 'tv' || KIND === 'projector');
    document.body.classList.toggle('watch', KIND === 'watch');
    $('brand-name').textContent = (S.name || 'JARVIS').toUpperCase();
    $('brand-sub').textContent = 'AI OS · ' + (S.devName || KIND_NAMES[KIND]);
  }
  applyKind();
  const devName = () => S.devName || KIND_NAMES[KIND];

  // ── little UI helpers ───────────────────────────────────────────────────
  let toastT;
  function toast(t) { const e = $('toast'); e.textContent = t; e.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => e.classList.remove('show'), 2800); }
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  function openSheet(id) { document.querySelectorAll('.sheet').forEach(s => s.hidden = s.id !== id); $('scrim').hidden = false; }
  function closeSheets() { document.querySelectorAll('.sheet').forEach(s => s.hidden = true); $('scrim').hidden = true; }
  $('scrim').onclick = closeSheets;
  document.querySelectorAll('[data-close]').forEach(b => b.onclick = closeSheets);

  const STATES = { idle: ['Hazır', 'Mikrofona dokun ya da yaz.'], listening: ['Dinliyor...', 'Konuş, seni duyuyorum.'],
                   thinking: ['Düşünüyor...', 'Komut bağlamı analiz ediliyor.'], speaking: ['Konuşuyor...', 'Yanıt aktarılıyor.'],
                   connecting: ['Bağlanıyor...', 'Beyne bağlanılıyor.'], offline: ['Bağlantı yok', 'İnternet bağlantını kontrol et.'],
                   setup: ['Kurulum gerekli', 'Ayarlardan Gemini anahtarını gir.'] };
  let state = 'idle';
  let micOn = false, micLvl = 0;
  const core = JarvisReactor($('core'), { small: KIND === 'watch' });
  function setState(s) {
    state = s; core.state = (s === 'listening' || s === 'connecting') ? 'idle' : (s === 'setup' ? 'sleeping' : s);
    $('st-title').textContent = STATES[s][0]; $('st-sub').textContent = STATES[s][1];
    if (s === 'idle' && typeof amOwner === 'function' && !amOwner()) {
      $('st-title').textContent = 'Sessiz'; $('st-sub').textContent = `Sesli yanıt: ${ownerName}. Konuşmak için mikrofona dokun.`;
    }
  }

  // waveform
  const wave = $('wave'), wc = wave.getContext('2d');
  let lvl = 0, lvlT = 0;
  (function wf(t) {
    lvl += (lvlT - lvl) * 0.2; lvlT *= 0.92;
    core.level = Math.min(1, lvl * 1.6);
    const W = wave.width, H = wave.height, n = 46, bw = W / n;
    wc.clearRect(0, 0, W, H);
    for (let i = 0; i < n; i++) {
      const x = i / (n - 1), env = Math.sin(Math.PI * x);
      const nz = 0.55 + 0.45 * Math.sin(t / 90 + i * 1.7) * Math.sin(t / 53 + i * 0.6);
      const amp = state === 'speaking' ? lvl * 1.6 : state === 'listening' ? micLvl * 2 : state === 'thinking' ? 0.08 : 0.01;
      const h = Math.max(2, H * 0.9 * env * Math.min(1, amp * nz + 0.03));
      wc.fillStyle = '#ffb648'; wc.globalAlpha = 0.9;
      wc.fillRect(i * bw + bw * 0.25, (H - h) / 2, bw * 0.5, h);
    }
    requestAnimationFrame(wf);
  })(0);

  // clock (big screens)
  setInterval(() => { const d = new Date();
    $('clock').textContent = d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    $('date').textContent = d.toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' }); }, 1000);

  // ── conversation log ────────────────────────────────────────────────────
  const transcript = [];               // {role, text}
  function addTurn(role, text) {
    text = String(text || '').trim(); if (!text) return;
    const last = transcript[transcript.length - 1];
    if (last && last.role === role && last.open) { last.text += text; } else transcript.push({ role, text, open: true });
    renderLog();
  }
  function closeTurns() { transcript.forEach(t => { if (t.open) { t.open = false; queueRecent(t.role, t.text); } }); }
  function renderLog() {
    const L = transcript.slice(-60);
    $('log').innerHTML = L.map(t => `<div class="msg ${t.role === 'user' ? 'u' : t.role === 'sys' ? 's' : 'j'}">${esc(t.text)}</div>`).join('');
    $('side-log').innerHTML = L.filter(t => t.role !== 'sys').slice(-10).map(t => `<div><b>${t.role === 'user' ? 'Sen' : 'Jarvis'}:</b> ${esc(t.text.slice(0, 160))}</div>`).join('');
    const lastJ = [...L].reverse().find(t => t.role === 'jarvis'), lastU = [...L].reverse().find(t => t.role === 'user');
    if (lastJ || lastU) {
      $('reply').hidden = false;
      $('reply-you').textContent = lastU ? '“' + lastU.text.slice(0, 120) + '”' : '';
      $('reply-text').textContent = lastJ ? lastJ.text : '';
      $('reply').scrollTop = $('reply').scrollHeight;
    }
  }
  const sys = t => { transcript.push({ role: 'sys', text: t }); renderLog(); };

  // ── shared memory: the gist ─────────────────────────────────────────────
  const Cloud = {
    ok() { return !!(S.tok && S.gist); },
    async req(method, path, body) {
      const r = await fetch(GH + path, { method, cache: 'no-store',
        headers: { 'Authorization': 'Bearer ' + S.tok, 'Accept': 'application/vnd.github+json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body: body ? JSON.stringify(body) : undefined });
      if (!r.ok) throw new Error('GitHub ' + r.status);
      return r.status === 204 ? null : r.json();
    },
    etag: '', cache: null,
    async read() {
      const r = await fetch(GH + '/gists/' + S.gist, { cache: 'no-store',
        headers: { 'Authorization': 'Bearer ' + S.tok, 'Accept': 'application/vnd.github+json', ...(this.etag && this.cache ? { 'If-None-Match': this.etag } : {}) } });
      if (r.status === 304 && this.cache) return this.cache;            // unchanged: free, not counted
      if (!r.ok) throw new Error('GitHub ' + r.status);
      this.etag = r.headers.get('ETag') || '';
      const g = await r.json();
      const out = {};
      for (const [name, f] of Object.entries(g.files || {})) {
        if (f.truncated && f.raw_url) { try { out[name] = await (await fetch(f.raw_url, { cache: 'no-store' })).text(); } catch {} }
        else out[name] = f.content || '';
      }
      this.cache = out;
      return out;
    },
    async write(files) {
      const body = { files: {} };
      for (const [k, v] of Object.entries(files)) body.files[k] = { content: typeof v === 'string' ? v : JSON.stringify(v) };
      this.etag = ''; this.cache = null;
      return this.req('PATCH', '/gists/' + S.gist, body);
    },
    async create() {
      const g = await this.req('POST', '/gists', { description: 'JARVIS — ortak hafıza (gizli, silme)', public: false,
        files: { 'memory.json': { content: '{}' }, 'recent.json': { content: '[]' }, 'README.md': { content: 'JARVIS ortak hafıza. Silme.' } } });
      return g.id;
    },
  };
  const J = (s, d) => { try { const v = JSON.parse(s); return v ?? d; } catch { return d; } };
  let memory = J(localStorage.getItem('jarvis_mem'), {});
  let recent = J(localStorage.getItem('jarvis_recent'), []);
  let devices = [];
  let recentQueue = [];
  function queueRecent(role, text) { if (role === 'sys') return; recentQueue.push({ ts: new Date().toISOString(), device: devName(), role, text: text.slice(0, 600) }); }

  async function syncNow(extra = {}) {
    if (!Cloud.ok()) return null;
    try {
      const f = await Cloud.read();
      memory = mergeMemory(J(f['memory.json'], {}), memory);
      recent = J(f['recent.json'], []);
      devices = Object.entries(f).filter(([k]) => k.startsWith('device-')).map(([, v]) => J(v, null)).filter(Boolean);
      const writes = { ...extra };
      const cloudMem = J(f['memory.json'], {});
      if (JSON.stringify(cloudMem) !== JSON.stringify(memory)) writes['memory.json'] = JSON.stringify(memory);
      if (recentQueue.length) { recent = recent.concat(recentQueue).slice(-40); recentQueue = []; writes['recent.json'] = JSON.stringify(recent); }
      if (beatDirty || !lastBeat || Date.now() - lastBeat > (isActive() ? 20000 : 60000)) {
        lastBeat = Date.now(); beatDirty = false;
        writes['device-' + S.id + '.json'] = JSON.stringify(myBeat());
      }
      if (Object.keys(writes).length) await Cloud.write(writes);
      localStorage.setItem('jarvis_mem', JSON.stringify(memory));
      localStorage.setItem('jarvis_recent', JSON.stringify(recent));
      renderDevices();
      updateOwner();
      return f;
    } catch (e) { console.warn('sync', e); updateOwner(); return null; }
  }
  let lastBeat = 0, beatDirty = false, syncing = false;
  async function syncLoop() {
    if (!syncing) { syncing = true; try { await syncNow(); } finally { syncing = false; } }
    setTimeout(syncLoop, document.visibilityState === 'visible' ? 8000 : 45000);
  }
  setTimeout(syncLoop, 1500);

  // ── one voice: which device answers out loud ────────────────────────────
  // Every device hears and understands; only one speaks. The phone first, then
  // the computer, then tablet, TV/projector, watch — unless the user just turned
  // to a device on purpose (tapped its mic, typed into it), which wins for five
  // minutes. Same rule as voice_owner() in core/sync_hub.py.
  const PRIORITY = { phone: 1, pc: 2, tablet: 3, tv: 4, projector: 4, watch: 5 };
  const ALIVE_MS = 60000, CLAIM_MS = 300000;
  let lastInteract = Date.now(), owner = null, ownerName = '', resumeMic = false;
  const isActive = () => document.visibilityState === 'visible' && (micOn || Date.now() - lastInteract < 10 * 60000);
  const myBeat = () => ({ id: S.id, name: devName(), kind: KIND, seen: new Date().toISOString(), commands: false,
                          active: isActive(), claim: S.claim || '' });
  function voiceOwner(list, now = Date.now()) {
    const live = list.filter(d => d.active && now - Date.parse(d.seen || 0) < ALIVE_MS);
    if (!live.length) return null;
    const claimed = live.filter(d => d.claim && now - Date.parse(d.claim) < CLAIM_MS);
    if (claimed.length) return claimed.sort((a, b) => Date.parse(b.claim) - Date.parse(a.claim) || String(b.id).localeCompare(String(a.id)))[0].id;
    return live.sort((a, b) => (PRIORITY[a.kind] || 9) - (PRIORITY[b.kind] || 9) || String(a.id).localeCompare(String(b.id)))[0].id;
  }
  const amOwner = () => owner === null || owner === S.id;
  function updateOwner() {
    const list = devices.filter(d => d.id !== S.id).concat([myBeat()]);
    const o = voiceOwner(list);
    const changed = o !== owner;
    owner = o; ownerName = (list.find(d => d.id === o) || {}).name || '';
    if (!changed) return;
    if (amOwner()) {
      document.body.classList.remove('quiet');
      if (resumeMic && !micOn) { resumeMic = false; startMic(); }
      if (state === 'idle') setState('idle');
    } else {
      document.body.classList.add('quiet');
      stopPlayback();
      if (micOn) { resumeMic = true; stopMic(); }
      sys(`Sesli yanıtı ${ownerName} veriyor; burada sessizim. Konuşmak için mikrofona dokun.`);
      if (state === 'idle' || state === 'listening') setState('idle');
    }
  }
  function claimHere() {
    lastInteract = Date.now(); S.claim = new Date().toISOString(); save();
    beatDirty = true; owner = S.id; document.body.classList.remove('quiet');
    syncNow();
  }
  document.addEventListener('visibilitychange', () => { beatDirty = true; if (Cloud.ok()) syncNow(); else updateOwner(); });
  ['pointerdown', 'keydown'].forEach(ev => document.addEventListener(ev, () => { lastInteract = Date.now(); }, { passive: true }));

  const CATS = ['identity', 'preferences', 'projects', 'relationships', 'wishes', 'notes'];
  function entry(v) { return v && typeof v === 'object' ? { value: String(v.value ?? ''), updated: String(v.updated ?? '') } : { value: String(v ?? ''), updated: '' }; }
  function mergeMemory(a, b) {           // newer `updated` wins; same rule as core/sync_hub.merge_memory
    const out = {};
    const tomb = { ...((a || {})._deleted || {}) };
    for (const [k, t] of Object.entries((b || {})._deleted || {})) if (!tomb[k] || t > tomb[k]) tomb[k] = t;
    for (const c of new Set([...CATS, ...Object.keys(a || {}), ...Object.keys(b || {})])) {
      if (c === '_deleted') continue;
      const ca = (a || {})[c] || {}, cb = (b || {})[c] || {};
      if (typeof ca !== 'object' || typeof cb !== 'object') { out[c] = ca; continue; }
      const m = {};
      for (const k of new Set([...Object.keys(ca), ...Object.keys(cb)])) {
        if (k in ca && k in cb) { const ea = entry(ca[k]), eb = entry(cb[k]); m[k] = eb.updated > ea.updated ? eb : ea; }
        else m[k] = entry(k in ca ? ca[k] : cb[k]);
      }
      for (const k of Object.keys(m)) if (tomb[c + '/' + k] && tomb[c + '/' + k] >= m[k].updated) delete m[k];
      out[c] = m;
    }
    if (Object.keys(tomb).length) out._deleted = tomb;
    return out;
  }
  const nowIso = () => new Date().toISOString().slice(0, 19) + 'Z';
  function memoryText() {
    const lines = [];
    for (const c of CATS) for (const [k, v] of Object.entries(memory[c] || {})) lines.push(`- ${c}/${k}: ${entry(v).value}`);
    return lines.slice(-80).join('\n') || '(henüz yok)';
  }

  // ── devices ──────────────────────────────────────────────────────────────
  const online = d => Date.now() - Date.parse(d.seen || 0) < 3 * 60 * 1000;
  function renderDevices() {
    const me = { id: S.id, name: devName() + ' (bu cihaz)', kind: KIND, seen: new Date().toISOString() };
    const rows = [me, ...devices.filter(d => d.id !== S.id)];
    const html = rows.map(d => `<div class="dev"><div class="ic">${ICON[d.kind] || '💻'}</div><div class="tx"><div class="nm">${esc(d.name)}</div>
      <div class="sb">${d.kind === 'pc' ? 'Bilgisayar · komut alır' : (KIND_NAMES[d.kind] || 'Cihaz')}${online(d) ? '' : ' · görülmedi'}${d.id === owner || (owner === null && d.id === S.id) ? ' · 🔊 sesli yanıt burada' : ''}</div></div>
      <span class="dot ${online(d) ? 'on' : ''}"></span></div>`).join('');
    $('devs').innerHTML = html + (Cloud.ok() ? '' : '<p>Ortak hafıza kurulmamış: cihazlar birbirini göremiyor. Ayarlar → GitHub anahtarı.</p>');
    $('side-devs').innerHTML = html;
  }
  $('t-devs').onclick = () => { renderDevices(); openSheet('s-devs'); syncNow(); };

  function findPc(name) {
    const pcs = devices.filter(d => d.kind === 'pc');
    if (!pcs.length) return null;
    const n = String(name || '').toLocaleLowerCase('tr');
    const hit = n && pcs.find(d => d.name.toLocaleLowerCase('tr').includes(n) || n.includes(d.name.toLocaleLowerCase('tr')));
    if (hit) return hit;
    if (/laptop|dizüstü/.test(n)) { const l = pcs.find(d => /laptop|book|dizüstü/i.test(d.name)); if (l) return l; }
    return pcs.filter(online).sort((a, b) => Date.parse(b.seen) - Date.parse(a.seen))[0] || pcs[0];
  }
  async function sendToPc(name, text) {
    if (!Cloud.ok()) return 'Ortak hafıza kurulu değil; bilgisayara ulaşamıyorum.';
    await syncNow();
    const pc = findPc(name);
    if (!pc) return 'Bağlı bir bilgisayar yok. Bilgisayarda JARVIS açıkken "Jarvis\'i her cihaza kur" demen gerekiyor.';
    if (!online(pc)) return `${pc.name} şu an kapalı ya da çevrimdışı görünüyor.`;
    const id = S.id + '-' + Date.now().toString(36);
    const f = await Cloud.read();
    const inbox = J(f[`inbox-${pc.id}.json`], []);
    inbox.push({ id, text, from: devName(), ts: nowIso() });
    await Cloud.write({ [`inbox-${pc.id}.json`]: JSON.stringify(inbox.slice(-20)) });
    for (let i = 0; i < 24; i++) {          // up to ~70 s
      await new Promise(r => setTimeout(r, 3000));
      try {
        const g = await Cloud.read();
        const hit = J(g[`outbox-${pc.id}.json`], []).find(o => o.id === id);
        if (hit) return `${pc.name}: ${hit.reply}`;
      } catch {}
    }
    return `${pc.name} komutu aldı ama henüz yanıt vermedi.`;
  }

  // ── tools the brain can use on every device ─────────────────────────────
  const TOOLS = [
    { name: 'remember', description: 'Kullanıcı hakkında kalıcı bir bilgiyi ortak hafızaya kaydet (tüm cihazlar ve bilgisayar paylaşır).',
      parameters: { type: 'OBJECT', properties: { category: { type: 'STRING', description: CATS.join(' | ') }, key: { type: 'STRING' }, value: { type: 'STRING' } }, required: ['key', 'value'] } },
    { name: 'forget', description: 'Ortak hafızadan bir bilgiyi sil.',
      parameters: { type: 'OBJECT', properties: { category: { type: 'STRING' }, key: { type: 'STRING' } }, required: ['key'] } },
    { name: 'search_memory', description: 'Ortak hafızada ara.', parameters: { type: 'OBJECT', properties: { query: { type: 'STRING' } }, required: ['query'] } },
    { name: 'list_devices', description: 'JARVIS\'in çalıştığı cihazları ve hangisinin açık olduğunu listele.', parameters: { type: 'OBJECT', properties: {} } },
    { name: 'computer_command', description: 'Bilgisayardaki/laptoptaki JARVIS\'e bir komut gönder ve yanıtını al: uygulama ya da dosya açmak, projede kod yazıp çalıştırmak, bilgisayarın ekranına bakmak, mesaj göndermek gibi yalnızca bilgisayarın yapabildiği her şey. Bilgisayar kapalıysa bunu söyle.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING', description: 'bilgisayarın adı ya da "laptop"; boşsa açık olan' }, command: { type: 'STRING', description: 'bilgisayardaki JARVIS\'e söylenecek komut, Türkçe' } }, required: ['command'] } },
    { name: 'computer_quick', description: 'Bilgisayarda anında: volume_up, volume_down, mute, play_pause, next, prev, lock.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING' }, action: { type: 'STRING' } }, required: ['action'] } },
    { name: 'show_code', description: 'Yazdığın kodu bu cihazın ekranında göster (kopyalanabilir, indirilebilir) ve ortak hafızaya kaydet. Kod yazman istenince bunu kullan; kodu sesli okuma.',
      parameters: { type: 'OBJECT', properties: { filename: { type: 'STRING' }, language: { type: 'STRING' }, code: { type: 'STRING' }, note: { type: 'STRING' } }, required: ['filename', 'code'] } },
    { name: 'open_link', description: 'Bu cihazda bir web sayfası, video ya da harita aç (TV ve projeksiyonda tam ekran).',
      parameters: { type: 'OBJECT', properties: { url: { type: 'STRING' }, title: { type: 'STRING' } }, required: ['url'] } },
    { name: 'camera', description: 'Bu cihazın kamerasını aç/kapat ki görebilesin. facing: back | front.',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' }, facing: { type: 'STRING' } }, required: ['on'] } },
    { name: 'screen_share', description: 'Bu cihazın ekranını görmek için kullanıcıdan ekran paylaşımı iste (kullanıcı onaylamalı).',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' } }, required: ['on'] } },
  ];
  let lastCode = null;
  async function runTool(name, a) {
    a = a || {};
    switch (name) {
      case 'remember': {
        const c = CATS.includes(a.category) ? a.category : 'notes';
        memory[c] = memory[c] || {}; memory[c][String(a.key)] = { value: String(a.value), updated: nowIso() };
        localStorage.setItem('jarvis_mem', JSON.stringify(memory)); syncNow();
        return `Kaydedildi: ${c}/${a.key}`;
      }
      case 'forget': {
        let done = false;
        for (const c of (a.category ? [a.category] : CATS)) if (memory[c] && a.key in memory[c]) {
          delete memory[c][a.key]; done = true;
          memory._deleted = memory._deleted || {}; memory._deleted[c + '/' + a.key] = nowIso();
        }
        localStorage.setItem('jarvis_mem', JSON.stringify(memory));
        if (done && Cloud.ok()) { try { await Cloud.write({ 'memory.json': JSON.stringify(memory) }); } catch {} }
        return done ? 'Silindi.' : 'Bulunamadı.';
      }
      case 'search_memory': {
        const q = String(a.query || '').toLocaleLowerCase('tr').split(/\s+/).filter(Boolean);
        const hits = [];
        for (const c of CATS) for (const [k, v] of Object.entries(memory[c] || {})) {
          const s = (k + ' ' + entry(v).value).toLocaleLowerCase('tr');
          if (q.some(w => s.includes(w))) hits.push(`${c}/${k}: ${entry(v).value}`);
        }
        return hits.slice(0, 12).join('\n') || 'Hafızada bununla ilgili bir şey yok.';
      }
      case 'list_devices': {
        await syncNow();
        const L = devices.map(d => `${d.name} (${d.kind === 'pc' ? 'bilgisayar' : KIND_NAMES[d.kind] || d.kind}) — ${online(d) ? 'açık' : 'kapalı'}`);
        return L.length ? L.join('\n') : 'Ortak hafızada kayıtlı başka cihaz yok.';
      }
      case 'computer_command': return await sendToPc(a.device, String(a.command || ''));
      case 'computer_quick': return await sendToPc(a.device, 'quick:' + String(a.action || ''));
      case 'show_code': {
        lastCode = { filename: String(a.filename || 'kod.txt'), code: String(a.code || ''), note: String(a.note || '') };
        showCode(); $('t-code').hidden = false;
        if (Cloud.ok()) Cloud.write({ ['code-' + lastCode.filename.replace(/[^\w.-]/g, '_')]: lastCode.code }).catch(() => {});
        return 'Kod ekranda gösterildi ve kaydedildi.';
      }
      case 'open_link': {
        const url = String(a.url || '');
        if (!/^https?:\/\//i.test(url)) return 'Geçerli bir adres değil.';
        const w = window.open(url, '_blank');
        if (!w) askUser('Bağlantı', `${a.title || url} açılsın mı?`, () => window.open(url, '_blank'));
        return 'Açıldı.';
      }
      case 'camera': return a.on ? await startVideo('camera', a.facing === 'front' ? 'user' : 'environment') : (stopVideo(), 'Kamera kapandı.');
      case 'screen_share':
        if (!a.on) { stopVideo(); return 'Ekran paylaşımı kapandı.'; }
        if (!navigator.mediaDevices?.getDisplayMedia) return 'Bu cihaz ekran paylaşamıyor (telefonlar desteklemiyor). Kamerayı açabilirim.';
        askUser('Ekranı göster', 'JARVIS ekranını görmek istiyor.', () => startVideo('screen'));
        return 'Kullanıcıdan ekran paylaşımı onayı istendi.';
    }
    return 'Bilinmeyen araç.';
  }
  function showCode() {
    if (!lastCode) return;
    $('code-name').textContent = lastCode.filename.toUpperCase();
    $('code-note').textContent = lastCode.note; $('code-body').textContent = lastCode.code; openSheet('s-code');
  }
  $('t-code').onclick = showCode;
  $('code-copy').onclick = async () => { try { await navigator.clipboard.writeText(lastCode.code); toast('Kopyalandı'); } catch { toast('Kopyalanamadı'); } };
  $('code-dl').onclick = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lastCode.code], { type: 'text/plain' }));
    a.download = lastCode.filename; a.click(); };
  let askFn = null;
  function askUser(title, text, fn) { $('ask-title').textContent = title.toUpperCase(); $('ask-text').textContent = text; askFn = fn; openSheet('s-ask'); }
  $('ask-yes').onclick = () => { closeSheets(); if (askFn) askFn(); askFn = null; };

  // ── the brain: Gemini Live ───────────────────────────────────────────────
  let ws = null, ready = false, wantLive = false, variant = +(localStorage.getItem('jarvis_variant') || 0), connecting = null;
  function systemText() {
    const r = recent.slice(-16).map(t => `[${t.device}] ${t.role === 'user' ? 'Kullanıcı' : 'JARVIS'}: ${t.text}`).join('\n');
    const pcs = devices.filter(d => d.kind === 'pc').map(d => `${d.name} (${online(d) ? 'açık' : 'kapalı'})`).join(', ') || 'yok';
    return `Sen ${S.name || 'JARVIS'}sın: kullanıcının kişisel asistanı. Şu an "${devName()}" adlı ${KIND_NAMES[KIND].toLowerCase()} üzerinde çalışıyorsun; ` +
      `aynı sen bilgisayarda, laptopta, telefonda, tablette, TV'de ve saatte de varsın ve hepsi aynı hafızayı paylaşır. ` +
      `Kısa, doğal ve sıcak konuş; kullanıcının dilinde yanıt ver (çoğunlukla Türkçe). ` +
      `Güncel bilgi için Google aramasını kullan. Kod istenince kodu show_code ile ekranda göster, sesli okuma. ` +
      `Yalnızca bir bilgisayarın yapabileceği işleri (uygulama/dosya açmak, projede çalışmak, bilgisayar ekranını görmek) computer_command ile bilgisayara gönder. ` +
      `Kullanıcı hakkında kalıcı bir şey öğrenince remember ile kaydet.\n\n` +
      `Bugün: ${new Date().toLocaleString('tr-TR', { dateStyle: 'full', timeStyle: 'short' })}.\nBilgisayarlar: ${pcs}.\n\n` +
      `ORTAK HAFIZA:\n${memoryText()}\n\nSON KONUŞMALAR (tüm cihazlar):\n${r || '(yok)'}`;
  }
  function setupMsg(v) {
    const model = LIVE_MODELS[v >= 2 ? 1 : 0];
    const voice = { voiceConfig: { prebuiltVoiceConfig: { voiceName: S.voice || 'Charon' } } };
    const setup = { model, systemInstruction: { parts: [{ text: systemText() }] },
                    tools: [{ functionDeclarations: TOOLS }, { googleSearch: {} }],
                    inputAudioTranscription: {}, outputAudioTranscription: {} };
    if (v % 2 === 0) { setup.generationConfig = { responseModalities: ['AUDIO'], speechConfig: voice }; setup.contextWindowCompression = { slidingWindow: {} }; }
    else { setup.responseModalities = ['AUDIO']; setup.speechConfig = voice; }
    return { setup };
  }
  function connect() {
    if (ready && ws && ws.readyState === 1) return Promise.resolve();
    if (connecting) return connecting;
    if (!S.key) { setState('setup'); openSetup(); return Promise.reject(new Error('anahtar yok')); }
    setState('connecting');
    connecting = new Promise((resolve, reject) => {
      let tries = 0;
      const attempt = () => {
        const v = (variant + tries) % 4;
        const sock = new WebSocket(WS_URL + encodeURIComponent(S.key));
        let opened = false;
        sock.binaryType = 'arraybuffer';
        sock.onopen = () => sock.send(JSON.stringify(setupMsg(v)));
        sock.onmessage = (e) => {
          const msg = typeof e.data === 'string' ? JSON.parse(e.data) : JSON.parse(new TextDecoder().decode(e.data));
          if (msg.setupComplete !== undefined) {
            opened = true; ws = sock; ready = true; connecting = null;
            if (v !== variant) { variant = v; localStorage.setItem('jarvis_variant', String(v)); }
            setState(micOn ? 'listening' : 'idle'); resolve(); return;
          }
          onServer(msg);
        };
        sock.onclose = (e) => {
          if (!opened) {
            tries++;
            if (/key|API_KEY|permission|unauth/i.test(e.reason || '') ) { connecting = null; setState('setup'); sys('Gemini anahtarı geçersiz: ' + e.reason); reject(new Error(e.reason)); return; }
            if (tries < 4) { console.warn('setup variant failed', v, e.code, e.reason); attempt(); return; }
            connecting = null; setState('offline'); sys('Beyne bağlanılamadı: ' + (e.reason || e.code)); reject(new Error(e.reason)); return;
          }
          if (sock !== ws) return;
          ready = false; ws = null; stopPlayback();
          if (wantLive) { setTimeout(() => connect().catch(() => {}), 800); } else setState('idle');
        };
        sock.onerror = () => {};
      };
      attempt();
    });
    return connecting;
  }
  function send(obj) { if (ws && ready && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

  let outOpen = false;
  async function onServer(m) {
    if (m.serverContent) {
      const sc = m.serverContent;
      if (sc.interrupted) { stopPlayback(); }
      if (sc.inputTranscription?.text) { lastInteract = Date.now(); addTurn('user', sc.inputTranscription.text); setState('thinking'); }
      if (sc.outputTranscription?.text) { if (!outOpen) { closeTurnsOf('user'); outOpen = true; } addTurn('jarvis', sc.outputTranscription.text); }
      for (const p of sc.modelTurn?.parts || []) {
        if (p.inlineData?.data && /audio/.test(p.inlineData.mimeType || 'audio')) playPcm(p.inlineData.data);
        else if (p.text && !sc.outputTranscription) { addTurn('jarvis', p.text); }
      }
      if (sc.turnComplete) { outOpen = false; closeTurns(); syncSoon(); if (!playing()) setState(micOn ? 'listening' : 'idle'); }
    }
    if (m.toolCall?.functionCalls) {
      setState('thinking');
      const responses = [];
      for (const fc of m.toolCall.functionCalls) {
        let result;
        try { result = await runTool(fc.name, fc.args); } catch (e) { result = { error: String(e.message || e) }; }
        responses.push({ id: fc.id, name: fc.name, response: { result } });
      }
      send({ toolResponse: { functionResponses: responses } });
    }
    if (m.goAway) { /* the server will close soon; onclose reconnects */ }
  }
  function closeTurnsOf(role) { transcript.forEach(t => { if (t.open && t.role === role) { t.open = false; queueRecent(t.role, t.text); } }); }
  let syncT; function syncSoon() { clearTimeout(syncT); syncT = setTimeout(() => syncNow(), 4000); }

  // ── voice out: 24 kHz PCM ────────────────────────────────────────────────
  let outCtx = null, nextAt = 0; const sources = new Set();
  function ensureOut() { if (!outCtx) { try { outCtx = new AudioContext({ sampleRate: 24000 }); } catch { outCtx = new AudioContext(); } } if (outCtx.state === 'suspended') outCtx.resume(); }
  const playing = () => sources.size > 0;
  function playPcm(b64) {
    if (!amOwner()) return;              // one voice: another device is speaking
    ensureOut();
    const bin = atob(b64), n = bin.length >> 1, f = new Float32Array(n);
    let sum = 0;
    for (let i = 0; i < n; i++) { let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8); if (v >= 32768) v -= 65536; f[i] = v / 32768; sum += f[i] * f[i]; }
    const buf = outCtx.createBuffer(1, n, 24000); buf.copyToChannel(f, 0);
    const src = outCtx.createBufferSource(); src.buffer = buf; src.connect(outCtx.destination);
    const t = Math.max(outCtx.currentTime + 0.03, nextAt); src.start(t); nextAt = t + buf.duration;
    const level = Math.min(1, Math.sqrt(sum / Math.max(1, n)) * 4);
    setTimeout(() => { lvlT = Math.max(lvlT, level); }, Math.max(0, (t - outCtx.currentTime) * 1000));
    sources.add(src); setState('speaking');
    src.onended = () => { sources.delete(src); if (!sources.size) setState(micOn ? 'listening' : 'idle'); };
  }
  function stopPlayback() { for (const s of sources) { try { s.stop(); } catch {} } sources.clear(); nextAt = 0; }

  // ── voice in: 16 kHz PCM ─────────────────────────────────────────────────
  let micCtx = null, micStream = null, micNode = null;
  function b64(u8) { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); }
  async function startMic() {
    if (!navigator.mediaDevices?.getUserMedia) { toast('Bu cihaz mikrofona izin vermiyor; yazarak konuş.'); return; }
    ensureOut();
    try { micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } }); }
    catch (e) { toast('Mikrofon izni verilmedi'); return; }
    wantLive = true;
    try { await connect(); } catch { stopMic(); return; }
    micCtx = new AudioContext();
    const rate = micCtx.sampleRate, ratio = rate / 16000;
    const src = micCtx.createMediaStreamSource(micStream);
    let acc = [], accLen = 0, carry = 0;
    const handle = (f32) => {
      let e = 0; for (let i = 0; i < f32.length; i++) e += f32[i] * f32[i];
      micLvl = micLvl * 0.7 + Math.sqrt(e / f32.length) * 0.3 * 3;
      const outLen = Math.floor((f32.length - carry) / ratio);
      const o = new Int16Array(Math.max(0, outLen));
      for (let i = 0; i < outLen; i++) { const p = carry + i * ratio, j = Math.floor(p); const v = f32[j] + (f32[Math.min(j + 1, f32.length - 1)] - f32[j]) * (p - j);
        o[i] = Math.max(-32768, Math.min(32767, v * 32767)); }
      carry = carry + outLen * ratio - f32.length; if (carry < 0) carry = 0;
      acc.push(o); accLen += o.length;
      if (accLen >= 640) {
        const all = new Int16Array(accLen); let off = 0; for (const c of acc) { all.set(c, off); off += c.length; }
        acc = []; accLen = 0;
        send({ realtimeInput: { audio: { data: b64(new Uint8Array(all.buffer)), mimeType: 'audio/pcm;rate=16000' } } });
      }
    };
    try {
      const code = `class P extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('jp',P)`;
      const url = URL.createObjectURL(new Blob([code], { type: 'application/javascript' }));
      await micCtx.audioWorklet.addModule(url); URL.revokeObjectURL(url);
      micNode = new AudioWorkletNode(micCtx, 'jp'); micNode.port.onmessage = e => handle(e.data); src.connect(micNode);
    } catch {
      micNode = micCtx.createScriptProcessor(4096, 1, 1); micNode.onaudioprocess = e => handle(e.inputBuffer.getChannelData(0));
      src.connect(micNode); micNode.connect(micCtx.destination);
    }
    micOn = true; $('mic').classList.add('live'); $('mic').textContent = '⏹'; beatDirty = true;
    if (!playing()) setState('listening');
    if (KIND === 'watch' && navigator.vibrate) navigator.vibrate(30);
  }
  function stopMic() {
    micOn = false; micLvl = 0;
    try { micNode && micNode.disconnect(); } catch {} micNode = null;
    try { micCtx && micCtx.close(); } catch {} micCtx = null;
    if (micStream) micStream.getTracks().forEach(t => t.stop()); micStream = null;
    $('mic').classList.remove('live'); $('mic').textContent = '🎙️';
    send({ realtimeInput: { audioStreamEnd: true } });
    if (state === 'listening') setState('idle');
  }
  $('mic').onclick = () => { if (micOn) { resumeMic = false; stopMic(); } else { claimHere(); startMic(); } };

  // ── text in ──────────────────────────────────────────────────────────────
  $('ask').addEventListener('submit', async (e) => {
    e.preventDefault();
    const t = $('inp').value.trim(); if (!t) return;
    $('inp').value = ''; ensureOut(); claimHere();
    closeTurns(); transcript.push({ role: 'user', text: t, open: false }); queueRecent('user', t); renderLog();
    try { await connect(); } catch { return; }
    setState('thinking');
    send({ realtimeInput: { text: t } });
  });

  // ── eyes: camera and screen, ~1 frame a second ───────────────────────────
  let vStream = null, vTimer = null, vKind = '';
  async function startVideo(kind, facing = 'environment') {
    stopVideo();
    try {
      vStream = kind === 'screen' ? await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 2 }, audio: false })
                                  : await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing }, width: { ideal: 1280 } }, audio: false });
    } catch { toast(kind === 'screen' ? 'Ekran paylaşılamadı' : 'Kamera açılamadı'); return 'Açılamadı.'; }
    vKind = kind;
    const v = $('preview'); v.srcObject = vStream; v.hidden = false;
    $('t-cam').classList.toggle('on', kind === 'camera'); $('t-screen').classList.toggle('on', kind === 'screen');
    vStream.getVideoTracks()[0].onended = stopVideo;
    try { await connect(); } catch {}
    const c = document.createElement('canvas');
    vTimer = setInterval(() => {
      if (!v.videoWidth) return;
      const sc = Math.min(1, 1024 / Math.max(v.videoWidth, v.videoHeight));
      c.width = Math.round(v.videoWidth * sc); c.height = Math.round(v.videoHeight * sc);
      c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
      const data = c.toDataURL('image/jpeg', 0.7).split(',')[1];
      send({ realtimeInput: { video: { data, mimeType: 'image/jpeg' } } });
    }, 1000);
    return kind === 'screen' ? 'Ekranı görüyorum.' : 'Kamera açık, görüyorum.';
  }
  function stopVideo() {
    clearInterval(vTimer); vTimer = null;
    if (vStream) vStream.getTracks().forEach(t => t.stop()); vStream = null;
    $('preview').hidden = true; $('t-cam').classList.remove('on'); $('t-screen').classList.remove('on'); vKind = '';
  }
  $('t-cam').onclick = () => vKind === 'camera' ? stopVideo() : startVideo('camera');
  $('t-screen').onclick = () => {
    if (vKind === 'screen') return stopVideo();
    if (!navigator.mediaDevices?.getDisplayMedia) { toast('Bu cihaz ekran paylaşamıyor; kamerayı kullan'); return; }
    startVideo('screen');
  };

  // ── settings ─────────────────────────────────────────────────────────────
  function openSetup() {
    $('f-key').value = S.key || ''; $('f-tok').value = S.tok || ''; $('f-gist').value = S.gist || '';
    $('f-dev').value = S.devName || ''; $('f-kind').value = S.kind || 'auto'; $('f-voice').value = S.voice || 'Charon';
    $('f-status').textContent = ''; openSheet('s-setup');
  }
  $('b-set').onclick = openSetup; $('b-menu').onclick = () => { renderDevices(); openSheet('s-devs'); syncNow(); };
  $('b-chat').onclick = () => openSheet('s-chat');
  $('f-close').onclick = closeSheets;
  $('f-save').onclick = async () => {
    S.key = $('f-key').value.trim(); S.tok = $('f-tok').value.trim(); S.gist = $('f-gist').value.trim();
    S.devName = $('f-dev').value.trim(); S.kind = $('f-kind').value; S.voice = $('f-voice').value; save(); applyKind();
    if (S.tok && !S.gist) {
      $('f-status').textContent = 'Ortak hafıza açılıyor…';
      try { S.gist = await Cloud.create(); save(); $('f-gist').value = S.gist; } catch (e) { $('f-status').textContent = 'GitHub: ' + e.message + ' (anahtarın gist izni var mı?)'; return; }
    }
    $('f-status').textContent = 'Kaydedildi.'; lastBeat = 0; await syncNow();
    if (ws) { try { ws.close(); } catch {} }
    setState(S.key ? 'idle' : 'setup'); setTimeout(closeSheets, 600);
  };
  $('f-link').onclick = async () => {
    const j = JSON.stringify({ g: S.key || '', t: S.tok || '', i: S.gist || '', n: S.name || '' });
    const b = btoa(unescape(encodeURIComponent(j))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const link = location.origin + location.pathname + '#s=' + b;
    try { if (navigator.share) await navigator.share({ title: 'JARVIS kurulumu', url: link }); else { await navigator.clipboard.writeText(link); toast('Bağlantı kopyalandı — kendi cihazına gönder'); } }
    catch { try { await navigator.clipboard.writeText(link); toast('Bağlantı kopyalandı'); } catch { prompt('Bağlantı:', link); } }
  };

  // keyboard / TV remote: Enter or the OK key on the mic
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === ' ' || e.key === 'MediaPlayPause') { e.preventDefault(); $('mic').click(); }
  });

  // ── start ────────────────────────────────────────────────────────────────
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
  window.addEventListener('online', () => setState(S.key ? 'idle' : 'setup'));
  window.addEventListener('offline', () => setState('offline'));
  setState(S.key ? 'idle' : 'setup');
  if (!S.key) setTimeout(openSetup, 400);
  renderDevices(); renderLog();
  if (Cloud.ok()) syncNow();
  if (KIND === 'tv' || KIND === 'projector') $('mic').focus();
})();
