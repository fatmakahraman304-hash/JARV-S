/* MAYK — the same assistant on every device.
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
  const assistantName = value => /^(?:mayk|m\.a\.y\.k\.?|jarvis|j\.a\.r\.v\.i\.s\.?)$/i.test(String(value || "").trim()) ? "MAYK" : value;
  S.name = assistantName(S.name);
  const save = () => localStorage.setItem('jarvis_web', JSON.stringify(S));
  if (!S.id) { S.id = 'w' + Math.random().toString(36).slice(2, 12); save(); }
  if (!S.voice) S.voice = 'Charon';
  // A setup link (…#s=<code>) carries the keys from one device to another —
  // and from Safari to the home-screen MAYK on an iPhone, which Apple keeps
  // in separate storage.
  function importSetup(text) {
    const m = String(text || '').match(/(?:[#&?]s=|^)([A-Za-z0-9_-]{20,})\s*$/);
    if (!m) return false;
    try {
      const b = m[1].replace(/-/g, '+').replace(/_/g, '/');
      const j = JSON.parse(decodeURIComponent(escape(atob(b + '==='.slice((b.length + 3) % 4)))));
      if (!j.g && !j.t) return false;
      if (j.g) S.key = j.g; if (j.t) S.tok = j.t; if (j.i) S.gist = j.i; if (j.n) S.name = assistantName(j.n);
      if (j.d && !S.devName) S.devName = j.d;
      save(); return true;
    } catch { return false; }
  }
  function setupLink() {
    const j = JSON.stringify({ g: S.key || '', t: S.tok || '', i: S.gist || '', n: S.name || '' });
    const b = btoa(unescape(encodeURIComponent(j))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return location.origin + location.pathname + '#s=' + b;
  }
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (/[#&]s=/.test(location.hash)) {
    const ok = importSetup(location.hash);
    setTimeout(() => toast(ok ? 'Kurulum tamam — MAYK bu cihazda hazır' : 'Kurulum bağlantısı okunamadı'), 600);
    history.replaceState(null, '', location.pathname);
  }

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
  const KIND_NAMES = { phone: 'Telefon', tablet: 'Tablet', tv: 'Televizyon', projector: 'Projeksiyon', watch: 'Akıllı saat', pc: 'Bilgisayar', receiver: 'Alıcı (projeksiyonu kontrol eder)' };
  const ICON = { phone: '📱', tablet: '📱', tv: '📺', projector: '📽️', watch: '⌚', pc: '💻', receiver: '📡' };
  const ALICI_APK = 'https://github.com/fatmakahraman304-hash/JARV-S/releases/download/alici/jarvis-alici.apk';
  let KIND = detectKind();
  function applyKind() {
    KIND = detectKind();
    document.body.classList.toggle('big', KIND === 'tv' || KIND === 'projector');
    document.body.classList.toggle('watch', KIND === 'watch');
    for (const k of Object.keys(KIND_NAMES)) document.body.classList.toggle('k-' + k, KIND === k);
    const displayName = (S.name || 'MAYK').toUpperCase();
    $('brand-name').textContent = displayName === 'MAYK' ? 'M.A.Y.K' : displayName;
    $('brand-sub').textContent = 'AI OS · ' + (S.devName || KIND_NAMES[KIND]);
  }
  applyKind();
  const devName = () => S.devName || KIND_NAMES[KIND];

  // ── little UI helpers ───────────────────────────────────────────────────
  // Device modules (web/dev-*.js) listen here: emit() calls every handler and
  // returns true when one of them says it took care of the event.
  const hooks = {};
  function emit(ev, ...a) { let took = false; for (const f of hooks[ev] || []) { try { if (f(...a) === true) took = true; } catch (e) { console.warn('hook', ev, e); } } return took; }
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
    emit('state', s);
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
    // Transcription arrives in pieces that carry their own spaces ("Merhaba", " efendim"):
    // keep them, or the words run together.
    text = String(text || ''); if (!text.trim()) return;
    const last = transcript[transcript.length - 1];
    if (last && last.role === role && last.open) { last.text += text; } else transcript.push({ role, text: text.trimStart(), open: true });
    renderLog();
  }
  function closeTurns() { transcript.forEach(t => { if (t.open) { t.open = false; queueRecent(t.role, t.text); } }); }
  function renderLog() {
    const L = transcript.slice(-60);
    $('log').innerHTML = L.map(t => `<div class="msg ${t.role === 'user' ? 'u' : t.role === 'sys' ? 's' : 'j'}">${esc(t.text)}</div>`).join('');
    $('side-log').innerHTML = L.filter(t => t.role !== 'sys').slice(-10).map(t => `<div><b>${t.role === 'user' ? 'Sen' : 'MAYK'}:</b> ${esc(t.text.slice(0, 160))}</div>`).join('');
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
      const g = await this.req('POST', '/gists', { description: 'MAYK — ortak hafıza (gizli, silme)', public: false,
        files: { 'memory.json': { content: '{}' }, 'recent.json': { content: '[]' }, 'README.md': { content: 'MAYK ortak hafıza. Silme.' } } });
      return g.id;
    },
  };
  const J = (s, d) => { try { const v = JSON.parse(s); return v ?? d; } catch { return d; } };
  let memory = J(localStorage.getItem('jarvis_mem'), {});
  let recent = J(localStorage.getItem('jarvis_recent'), []);
  let devices = [];
  let recentQueue = [];
  let pcProjects = J(localStorage.getItem('jarvis_projects'), []);
  // shared gallery (images.json; core/sync_hub.merge_gallery is the same rule)
  let gallery = [], galleryNew = [];
  function mergeGallery(a, b) {
    const by = new Map();
    for (const g of [...(a || []), ...(b || [])]) if (g && g.id && /^https:\/\//.test(g.url || '')) by.set(g.id, { ...(by.get(g.id) || {}), ...g });
    return [...by.values()].sort((x, y) => String(x.ts).localeCompare(String(y.ts))).slice(-40);
  }
  function projectsText() {
    const L = [];
    for (const pc of pcProjects) for (const p of (pc.projects || [])) {
      const step = p.stages ? ` — aşama ${p.stage}/${p.stages}${p.current ? ' (' + p.current + ')' : ''}` : '';
      L.push(`[${pc.computer}] #${p.id} ${p.title}: ${p.status}${step}${p.note ? ' — ' + p.note.slice(0, 160) : ''} (${(p.updated || '').replace('T', ' ')})`);
    }
    return L.join('\n');
  }
  function queueRecent(role, text) {
    if (role === 'sys') return;
    const t = { ts: new Date().toISOString(), device: devName(), role, text: text.slice(0, 600) };
    recentQueue.push(t); Archive.queue(t); Learn.turn(t);
  }

  // ── the archive: every conversation from every device, kept for good in a
  // second secret gist (one file a month), so "geçen hafta ne demiştim?"
  // can be answered. Not read on every sync — only when searching.
  // Desktop side: core/sync_hub.py (archive_*).
  const Archive = {
    pending: J(localStorage.getItem('jarvis_arch_q'), []), last: 0, busy: false,
    queue(t) { this.pending.push(t); this.save(); if (this.pending.length >= 16) this.flush(); },
    save() { try { localStorage.setItem('jarvis_arch_q', JSON.stringify(this.pending.slice(-400))); } catch {} },
    async id() {
      if (!Cloud.ok()) return '';
      const f = Cloud.cache || await Cloud.read();
      let id = J(f['archive.json'], {}).gist || '';
      if (!id) {
        const g = await Cloud.req('POST', '/gists', { description: 'MAYK — konuşma arşivi (gizli, silme)', public: false,
          files: { 'README.md': { content: 'MAYK konuşma arşivi: her ay bir dosya. Silme.' } } });
        id = g.id; await Cloud.write({ 'archive.json': JSON.stringify({ gist: id }) });
      }
      return id;
    },
    async files(id) {
      const g = await Cloud.req('GET', '/gists/' + id);
      const out = {};
      for (const [n, f] of Object.entries(g.files || {})) {
        if (!/^history-\d{4}-\d{2}\.json$/.test(n)) continue;
        out[n] = f.truncated && f.raw_url ? await (await fetch(f.raw_url, { cache: 'no-store' })).text() : (f.content || '');
      }
      return out;
    },
    async flush() {
      if (this.busy || !this.pending.length || !Cloud.ok() || !navigator.onLine) return;
      this.busy = true;
      try {
        const id = await this.id(), files = await this.files(id), batch = this.pending.slice(), writes = {};
        for (const t of batch) {
          const name = `history-${t.ts.slice(0, 7)}.json`;
          const list = writes[name] || J(files[name], []);
          if (!list.some(x => x.ts === t.ts && x.device === t.device && x.text === t.text)) list.push(t);
          writes[name] = list;
        }
        const body = { files: {} }; for (const [k, v] of Object.entries(writes)) body.files[k] = { content: JSON.stringify(v) };
        await Cloud.req('PATCH', '/gists/' + id, body);
        this.pending = this.pending.slice(batch.length); this.save(); this.last = Date.now();
      } catch (e) { console.warn('archive', e); } finally { this.busy = false; }
    },
    async search(query, days) {
      await this.flush();
      const id = await this.id(); if (!id) return 'Ortak hafıza kurulu değil; arşiv yok.';
      const files = await this.files(id);
      const since = days > 0 ? Date.now() - days * 864e5 : 0;
      const stem = w => w.length > 5 ? w.slice(0, Math.max(4, w.length - 3)) : w;
      const q = String(query || '').toLocaleLowerCase('tr').split(/[^\p{L}\p{N}]+/u).filter(w => w.length > 2).map(stem);
      const all = Object.keys(files).sort().flatMap(n => J(files[n], [])).filter(t => Date.parse(t.ts) >= since);
      const hits = [];
      all.forEach((t, i) => {
        const txt = String(t.text || '').toLocaleLowerCase('tr');
        const score = q.length ? q.filter(w => txt.includes(w)).length : 1;
        if (score) hits.push([score, i]);
      });
      hits.sort((a, b) => b[0] - a[0] || b[1] - a[1]);
      const pick = new Set();
      for (const [, i] of hits.slice(0, 8)) { pick.add(i - 1); pick.add(i); pick.add(i + 1); }   // with the line around it
      const lines = [...pick].filter(i => all[i]).sort((a, b) => a - b).map(i => { const t = all[i];
        return `${new Date(t.ts).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} [${t.device}] ${t.role === 'user' ? 'Kullanıcı' : 'MAYK'}: ${t.text}`; });
      return lines.length ? `Arşivden (${all.length} satır arandı):\n` + lines.join('\n').slice(0, 6000) : 'Arşivde bununla ilgili bir konuşma bulamadım.';
    },
  };
  setInterval(() => { if (Archive.pending.length && Date.now() - Archive.last > 180000) Archive.flush(); }, 30000);
  window.addEventListener('pagehide', () => Archive.save());

  // ── learning: every so often Gemini's free text model reads the latest
  // conversation and files lasting facts about the user into shared memory
  // ("annesinin adı Ayşe", "kahveyi şekersiz içer") — like MAYK knowing Tony.
  const Learn = {
    buf: [], timer: null,
    turn(t) { this.buf.push(t); clearTimeout(this.timer); this.timer = setTimeout(() => this.run(), 90000); if (this.buf.filter(x => x.role === 'user').length >= 10) this.run(); },
    async run() {
      clearTimeout(this.timer);
      const turns = this.buf.splice(0); if (!S.key || turns.filter(t => t.role === 'user').length < 2) return;
      const known = CATS.flatMap(c => Object.keys(memory[c] || {}).map(k => `${c}/${k}`)).join(', ').slice(0, 3000);
      const ask = 'Aşağıdaki konuşmadan kullanıcı hakkında KALICI ve işe yarar yeni bilgileri çıkar (kim olduğu, ailesi ve yakınları, tercihleri, alışkanlıkları, projeleri, istekleri, önemli tarihler). ' +
        'Geçici şeyleri (bugünkü ruh hali, tek seferlik istekler), sağlık, din, siyaset, para bilgilerini ve zaten bilinenleri ALMA. Emin değilsen alma. ' +
        `Kategoriler: ${CATS.join(', ')}. Bilinen anahtarlar: ${known || '(yok)'}\n` +
        'Sadece JSON dizi döndür: [{"category":"...","key":"kısa_anahtar","value":"kısa değer"}] ya da [].\n\nKONUŞMA:\n' +
        turns.map(t => `${t.role === 'user' ? 'Kullanıcı' : 'MAYK'}: ${t.text}`).join('\n').slice(-6000);
      for (const model of TEXT_MODELS) {
        try {
          const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, { method: 'POST',
            headers: { 'Content-Type': 'application/json', 'x-goog-api-key': S.key },
            body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: ask }] }], generationConfig: { responseMimeType: 'application/json' } }) });
          if (!r.ok) continue;
          const js = await r.json();
          const txt = (js.candidates?.[0]?.content?.parts || []).filter(p => p.text && !p.thought).map(p => p.text).join('');
          const facts = J(txt.replace(/^```(json)?|```$/g, '').trim(), []);
          let n = 0;
          for (const f of Array.isArray(facts) ? facts.slice(0, 6) : []) {
            const c = CATS.includes(f.category) ? f.category : 'notes', k = String(f.key || '').trim().slice(0, 60), v = String(f.value || '').trim().slice(0, 300);
            if (!k || !v || entry((memory[c] || {})[k] || '').value === v) continue;
            memory[c] = memory[c] || {}; memory[c][k] = { value: v, updated: nowIso() }; n++;
          }
          if (n) { localStorage.setItem('jarvis_mem', JSON.stringify(memory)); syncNow(); console.info('[öğrenme]', n, 'yeni bilgi'); }
          return;
        } catch {}
      }
    },
  };

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
      pcProjects = Object.entries(f).filter(([k]) => k.startsWith('projects-')).map(([, v]) => J(v, null)).filter(Boolean);
      try { localStorage.setItem('jarvis_projects', JSON.stringify(pcProjects)); } catch {}
      const myInbox = J(f[`inbox-${S.id}.json`], []);
      if (myInbox.length) { runInbox(myInbox); writes[`inbox-${S.id}.json`] = '[]'; }
      const cloudG = J(f['images.json'], []);
      gallery = mergeGallery(cloudG, galleryNew);
      if (galleryNew.length) { writes['images.json'] = JSON.stringify(gallery); galleryNew = []; }
      const cloudRem = J(f['reminders.json'], []);
      reminders = mergeReminders(reminders, cloudRem);
      const remSig = L => L.map(r => [r.id, +r.due, r.text, r.cancelled || ''].join('|')).join('\n');
      if (remSig(mergeReminders(cloudRem, [])) !== remSig(reminders)) writes['reminders.json'] = JSON.stringify(reminders);
      saveRem(); renderRem();
      if (beatDirty || !lastBeat || Date.now() - lastBeat > (isActive() ? 20000 : 60000)) {
        lastBeat = Date.now(); beatDirty = false;
        writes['device-' + S.id + '.json'] = JSON.stringify(myBeat());
      }
      if (Object.keys(writes).length) await Cloud.write(writes);
      localStorage.setItem('jarvis_mem', JSON.stringify(memory));
      localStorage.setItem('jarvis_recent', JSON.stringify(recent));
      renderDevices();
      updateOwner();
      batteryWatch();
      watchUpdateFile(f);
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
                          active: isActive(), claim: S.claim || '', ...battery });
  // This device's battery where the browser tells (Android Chrome; not iPhone).
  let battery = {};
  (async () => { try { const b = await navigator.getBattery?.(); if (!b) return;
    const upd = () => { battery = { battery: Math.round(b.level * 100), charging: !!b.charging }; };
    upd(); b.addEventListener('levelchange', upd); b.addEventListener('chargingchange', upd); } catch {} })();
  // Low battery anywhere: said once by the device that has the voice
  // (core/sync_hub.low_battery is the same rule).
  const batAlerted = new Set(J(sessionStorage.getItem('jarvis_bat'), []));
  function lowBattery(list) {
    const out = [];
    for (const d of list) {
      if (d.battery == null) continue;
      if (d.charging || d.battery > 30) { batAlerted.delete(d.id); continue; }
      if (d.battery <= 15 && online(d) && !batAlerted.has(d.id)) { batAlerted.add(d.id); out.push(d); }
    }
    try { sessionStorage.setItem('jarvis_bat', JSON.stringify([...batAlerted])); } catch {}
    return out;
  }
  function batteryWatch() {
    const me = { id: S.id, name: devName(), kind: KIND, seen: new Date().toISOString(), ...battery };
    const low = lowBattery([me, ...devices.filter(d => d.id !== S.id)]);
    if (!low.length || !amOwner()) return;
    const names = low.map(d => `${d.name} %${d.battery}`).join(', ');
    toast('🔋 Pil azaldı: ' + names); sys('🔋 Pil azaldı: ' + names);
    if (ws && ready) tellBrain(`Pili azalan cihaz: ${names}. Şarja takmasını öner.`);
  }
  function healthText(d) {
    const L = [];
    if (d.battery != null) L.push(`pil %${d.battery}${d.charging ? ' (şarjda)' : ''}`);
    if (d.cpu != null) L.push(`işlemci %${d.cpu}`);
    if (d.ram != null) L.push(`bellek %${d.ram}`);
    if (d.disk != null) L.push(`disk %${d.disk} dolu`);
    return L.join(', ');
  }
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
    const me = { id: S.id, name: devName() + ' (bu cihaz)', kind: KIND, seen: new Date().toISOString(), ...battery };
    const rows = [me, ...devices.filter(d => d.id !== S.id)];
    const html = rows.map(d => `<div class="dev"><div class="ic">${ICON[d.kind] || '💻'}</div><div class="tx"><div class="nm">${esc(d.name)}</div>
      <div class="sb">${d.kind === 'pc' ? 'Bilgisayar · komut alır' : (KIND_NAMES[d.kind] || 'Cihaz')}${online(d) ? '' : ' · görülmedi'}${healthText(d) ? ' · ' + esc(healthText(d)) : ''}${d.id === owner || (owner === null && d.id === S.id) ? ' · 🔊 sesli yanıt burada' : ''}</div></div>
      <span class="dot ${online(d) ? 'on' : ''}"></span></div>`).join('');
    $('devs').innerHTML = html + (Cloud.ok() ? '' : '<p>Ortak hafıza kurulmamış: cihazlar birbirini göremiyor. Ayarlar → GitHub anahtarı.</p>');
    $('side-devs').innerHTML = html;
    renderHud();
  }
  // Big screens (TV, projector): an Iron Man style board beside the core —
  // what is coming up, the to-do list, projects, and any device that needs care.
  let hudWeather = '';
  async function refreshHudWeather() {
    if (!hudOn() && !hooks.weather) return;
    try {
      const city = S.city || '';
      const { js, place } = await weatherData(city);
      const c = js.current || {}, d = js.daily || {};
      hudWeather = `${WICON(c.weather_code)} ${Math.round(c.temperature_2m)}°C ${WMO[c.weather_code] || ''} · ${Math.round(d.temperature_2m_min?.[0])}–${Math.round(d.temperature_2m_max?.[0])}°C${city ? ' · ' + place.split(',')[0] : ''}`;
      renderHud(); emit('weather', hudWeather);
    } catch { /* no location permission on a TV: set a city in settings */ }
  }
  const hudOn = () => document.body.classList.contains('big') || document.body.classList.contains('panels');
  function renderHud() {
    if (!hudOn()) return;
    try { renderHudNow(); } catch { /* called before the reminder code has loaded: next sync draws it */ }
  }
  function renderHudNow() {
    const block = (title, items, cls = '') => items.length ? `<div><h4>${title}</h4>${items.map(x => `<div class="it ${cls}">${esc(x)}</div>`).join('')}</div>` : '';
    const warn = [{ id: S.id, name: devName(), seen: new Date().toISOString(), ...battery }, ...devices.filter(d => d.id !== S.id)]
      .filter(d => online(d) && ((d.battery != null && d.battery <= 20 && !d.charging) || (d.disk != null && d.disk >= 90)))
      .map(d => d.battery != null && d.battery <= 20 ? `🔋 ${d.name} %${d.battery}` : `💾 ${d.name} disk %${d.disk}`);
    const rem = pendingRem().slice(0, 4).map(r => `⏰ ${remTime(r.due)} — ${r.text}`);
    const todos = Object.keys(memory.notes || {}).filter(k => k.startsWith('yapılacak: ')).slice(0, 5).map(k => '☐ ' + k.slice(11));
    const proj = [];
    for (const pc of pcProjects) for (const p of (pc.projects || [])) if (!/bitti|iptal|başarısız/.test(p.status)) proj.push(`⚙ ${p.title} — ${p.stages ? p.stage + '/' + p.stages : p.status}`);
    $('hud').innerHTML = (hudWeather ? `<div><h4>HAVA</h4><div class="it">${esc(hudWeather)}</div></div>` : '') + block('UYARI', warn, 'warn') + block('SIRADAKİLER', rem) + block('YAPILACAKLAR', todos) + block('PROJELER', proj.slice(0, 3));
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
  // Any device by name or kind ("telefon", "TV", "tablet", "saat", a name).
  const KIND_WORDS = { phone: /telefon|phone|cep/, tablet: /tablet|ipad/, tv: /tv|televizyon|tele/, projector: /projeksiyon|projekt/, watch: /saat|watch/, pc: /bilgisayar|laptop|pc|dizüstü|masaüstü/ };
  function findDevice(name, list = devices) {
    const n = String(name || '').toLocaleLowerCase('tr').trim();
    const others = list.filter(d => d.id !== S.id && d.kind !== 'receiver');   // the Alıcı takes only remote commands
    if (!n) return null;
    const byName = others.find(d => (d.name || '').toLocaleLowerCase('tr') === n) || others.find(d => (d.name || '').toLocaleLowerCase('tr').includes(n));
    if (byName) return byName;
    const kind = Object.keys(KIND_WORDS).find(k => KIND_WORDS[k].test(n));
    const ofKind = others.filter(d => d.kind === kind || (kind === 'tv' && d.kind === 'projector'));
    return ofKind.sort((a, b) => (online(b) - online(a)) || Date.parse(b.seen || 0) - Date.parse(a.seen || 0))[0] || null;
  }
  // Something sent to this device by another one (desktop: sync_hub.send_to_device).
  let inboxDone = J(localStorage.getItem('jarvis_inbox_done'), []);
  function runInbox(cmds) {
    let did = false;
    for (const c of Array.isArray(cmds) ? cmds : []) {
      if (!c || !c.id || inboxDone.includes(c.id)) continue;
      inboxDone.push(c.id); did = true;
      const from = c.from || 'Başka bir cihaz', title = String(c.title || '');
      try {
        if (c.kind === 'open' && /^https?:\/\//i.test(c.url || '') && emit('open', c)) {
          sys(`${from} gönderdi: ${title || c.url}`);
        } else if (c.kind === 'open' && /^https?:\/\//i.test(c.url || '')) {
          sys(`${from} bir bağlantı gönderdi: ${title || c.url}`);
          const w = window.open(c.url, '_blank');
          if (!w) askUser('Açılsın mı?', `${from}: ${title || c.url}`, () => window.open(c.url, '_blank'));
        } else if (c.kind === 'image' && (c.data || c.url)) {
          keepImage({ data: c.data || '', mime: c.mime || 'image/png', url: c.url || '', prompt: c.prompt || title, en: c.en || '', seed: c.seed || 0 });
          showImage(`${from} gönderdi${title ? ': ' + title : ''}`);
          if (c.see && c.data && ws && ready) {
            // the computer's screen, asked for by the user: let the brain look at it
            send({ realtimeInput: { video: { data: c.data, mimeType: c.mime || 'image/jpeg' } } });
            tellBrain(`${title} geldi ve ekranda; bu görüntüye bakarak ${c.question ? 'şu soruyu yanıtla: ' + c.question : 'bilgisayarda ne olduğunu kısaca anlat'}.`);
          }
        } else if (c.kind === 'code' || c.kind === 'text') {
          lastCode = { filename: String(c.filename || title || (c.kind === 'code' ? 'kod.txt' : 'not.txt')), code: String(c.text || ''), note: `${from} gönderdi` };
          showCode(); $('t-code').hidden = false;
        } else if (c.kind === 'report' && c.text) {
          // a background job on the computer finished while the user was here
          lastCode = { filename: (title || 'rapor').slice(0, 60) + '.txt', code: String(c.text), note: `${from} — ${title}` };
          showCode(); $('t-code').hidden = false; sys(`📋 ${title}`);
          if (amOwner()) { const note = `Bilgisayardaki arka plan görevi bitti: "${title}". Sonuç ekranda. Kullanıcıya başlığı ve ana sonucu bir iki cümleyle söyle:\n${String(c.text).slice(0, 1500)}`;
            if (ws && ready) tellBrain(note); else connect().then(() => tellBrain(note)).catch(() => toast('📋 ' + title)); }
        } else if (c.kind === 'ring') {
          ringHere(from);
        } else if (c.kind === 'guard') {
          if (c.on) startGuard().then(m => sys(`${from}: ${m}`)); else sys(`${from}: ${stopGuard()}`);
        } else if (c.kind === 'say' && c.text) {
          sys(`${from}: ${c.text}`);
          if (amOwner()) { if (ws && ready) tellBrain(`${from} şu mesajı iletti: "${c.text}".`); else toast(`${from}: ${c.text}`); }
        }
      } catch (e) { console.warn('inbox', e); }
    }
    if (did) localStorage.setItem('jarvis_inbox_done', JSON.stringify(inboxDone.slice(-200)));
    return did;
  }
  // ── "telefonumu bul": this device rings loudly until touched (or 30 s) ──
  let ringing = null;
  function ringHere(from) {
    if (ringing) return;
    ensureOut();
    const stop = () => { clearInterval(ringing); ringing = null; document.removeEventListener('pointerdown', stop, true); toast('Buldun 👍'); };
    let n = 0;
    ringing = setInterval(() => { beep(); if (navigator.vibrate) navigator.vibrate([400, 100, 400]); if (++n > 20) stop(); }, 1500);
    document.addEventListener('pointerdown', stop, true);
    toast(`📳 ${from || 'MAYK'} bu cihazı arıyor — durdurmak için dokun`);
    sys(`📳 ${from || 'MAYK'} bu cihazı arıyor.`);
  }

  // ── guard mode: this device's camera watches; on movement a photo goes to
  // every other device and the one with the voice says it ──────────────────
  let guard = null;
  async function startGuard() {
    if (guard) return 'Güvenlik modu zaten açık.';
    if (!navigator.mediaDevices?.getUserMedia) return 'Bu cihazda kamera yok.';
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false }); }
    catch { return 'Kameraya izin verilmedi.'; }
    const v = document.createElement('video'); v.muted = true; v.playsInline = true; v.srcObject = stream; await v.play().catch(() => {});
    const small = document.createElement('canvas'); small.width = 64; small.height = 48;
    const sctx = small.getContext('2d', { willReadFrequently: true });
    let prev = null, hits = 0, lastAlert = 0, warm = 4;
    guard = { stream, timer: setInterval(() => {
      if (!v.videoWidth) return;
      sctx.drawImage(v, 0, 0, 64, 48);
      const px = sctx.getImageData(0, 0, 64, 48).data, g = new Uint8Array(64 * 48);
      for (let i = 0; i < g.length; i++) g[i] = (px[i * 4] * 3 + px[i * 4 + 1] * 6 + px[i * 4 + 2]) / 10;
      if (prev) {
        let changed = 0; for (let i = 0; i < g.length; i++) if (Math.abs(g[i] - prev[i]) > 28) changed++;
        const moving = changed / g.length > 0.04;            // over 4 % of the picture changed
        hits = moving ? hits + 1 : 0;
        if (warm > 0) warm--;
        else if (hits >= 2 && Date.now() - lastAlert > 60000) { lastAlert = Date.now(); hits = 0; guardAlert(v); }
      }
      prev = g;
    }, 700) };
    document.body.classList.add('guard'); toast('🛡️ Güvenlik modu açık'); keepAwake();
    return 'Güvenlik modu açık: bu cihazın kamerası izliyor; hareket olursa fotoğrafı diğer cihazlara gönderip haber vereceğim. Cihazı sabit bir yere koy ve sayfayı açık bırak.';
  }
  function stopGuard() {
    if (!guard) return 'Güvenlik modu zaten kapalı.';
    clearInterval(guard.timer); guard.stream.getTracks().forEach(t => t.stop()); guard = null;
    document.body.classList.remove('guard'); toast('Güvenlik modu kapandı');
    return 'Güvenlik modu kapandı.';
  }
  async function guardAlert(v) {
    const c = document.createElement('canvas'), sc = Math.min(1, 800 / Math.max(v.videoWidth, v.videoHeight));
    c.width = Math.round(v.videoWidth * sc); c.height = Math.round(v.videoHeight * sc);
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    const data = c.toDataURL('image/jpeg', 0.75).split(',')[1];
    const when = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    const title = `🚨 ${devName()}: hareket algılandı (${when})`;
    sys(title);
    if (!Cloud.ok()) { beep(); toast(title); return; }
    try {
      await syncNow();
      const targets = devices.filter(d => d.id !== S.id && online(d));
      const f = await Cloud.read(), writes = {};
      for (const d of targets) {
        const name = `inbox-${d.id}.json`, box = J(f[name], []);
        const base = { from: devName(), ts: nowIso() };
        if (d.kind === 'pc') box.push({ ...base, id: S.id + '-g' + Date.now().toString(36), kind: 'image', data, mime: 'image/jpeg', title, text: title });
        else box.push({ ...base, id: S.id + '-g' + Date.now().toString(36), kind: 'image', data, mime: 'image/jpeg', title },
                      { ...base, id: S.id + '-s' + Date.now().toString(36), kind: 'say', text: `${devName()} kamerasında hareket algılandı, saat ${when}. Fotoğraf ekranda.` });
        writes[name] = JSON.stringify(box.slice(-10));
      }
      if (Object.keys(writes).length) await Cloud.write(writes);
    } catch (e) { console.warn('guard', e); }
  }
  async function sendToDevice(name, cmd) {
    if (!Cloud.ok()) return 'Ortak hafıza kurulu değil; başka cihaza ulaşamıyorum.';
    await syncNow();
    const d = findDevice(name);
    if (!d) return `"${name}" adında ya da türünde bir cihaz bulamadım. Açık cihazlar: ${devices.filter(x => x.id !== S.id).map(x => x.name).join(', ') || 'yok'}.`;
    if (d.kind === 'pc') {
      // Computers save pictures and code, open links (sync_hub._receive_item);
      // `text` is the same thing in words for older versions.
      const words = cmd.kind === 'open' ? `Bu bağlantıyı aç: ${cmd.url}` : cmd.kind === 'say' ? `Şunu söyle: ${cmd.text}` : `Bunu ekranda göster: ${cmd.text || cmd.url || cmd.title || ''}`;
      if (cmd.kind === 'say') return await sendToPc(d.name, words);
      return await sendToPc(d.name, words, { ...cmd, words });
    }
    const f = await Cloud.read();
    const box = J(f[`inbox-${d.id}.json`], []);
    box.push({ ...cmd, id: S.id + '-' + Date.now().toString(36), from: devName(), ts: nowIso() });
    let body = JSON.stringify(box.slice(-10));
    if (body.length > 4e6) return 'Gönderilecek şey çok büyük.';
    await Cloud.write({ [`inbox-${d.id}.json`]: body });
    return `${d.name} cihazına gönderildi${online(d) ? '' : ' (şu an kapalı görünüyor; açılınca görecek)'}.`;
  }
  async function sendToPc(name, text, item = null) {
    if (!Cloud.ok()) return 'Ortak hafıza kurulu değil; bilgisayara ulaşamıyorum.';
    await syncNow();
    const pc = findPc(name);
    if (!pc) return 'Bağlı bir bilgisayar yok. Bilgisayarda MAYK açıkken "MAYK\'ı her cihaza kur" demen gerekiyor.';
    if (!online(pc)) return `${pc.name} şu an kapalı ya da çevrimdışı görünüyor.`;
    const id = S.id + '-' + Date.now().toString(36);
    const f = await Cloud.read();
    const inbox = J(f[`inbox-${pc.id}.json`], []);
    inbox.push(item ? { ...item, text: item.kind === 'code' || item.kind === 'text' ? item.text : text, id, from: devName(), ts: nowIso() }
                    : { id, text, from: devName(), ts: nowIso() });
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
    { name: 'list_devices', description: 'MAYK\'ın çalıştığı cihazları ve hangisinin açık olduğunu listele.', parameters: { type: 'OBJECT', properties: {} } },
    { name: 'computer_command', description: 'Bilgisayardaki/laptoptaki MAYK\'a bir komut gönder ve yanıtını al: uygulama ya da dosya açmak, projede kod yazıp çalıştırmak, bilgisayarın ekranına bakmak, mesaj göndermek gibi yalnızca bilgisayarın yapabildiği her şey. Evdeki akıllı cihazlar da buradan (Home Assistant bilgisayara bağlı): "salonun ışığını kapat", "açık kalan ışıkları kapat", "klimayı 22 yap", "kapı kilitli mi" → command olarak aynen ilet. Bilgisayar kapalıysa bunu söyle.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING', description: 'bilgisayarın adı ya da "laptop"; boşsa açık olan' }, command: { type: 'STRING', description: 'bilgisayardaki MAYK\'a söylenecek komut, Türkçe' } }, required: ['command'] } },
    { name: 'computer_quick', description: 'Bilgisayarda anında: volume_up, volume_down, mute, play_pause, next, prev, lock.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING' }, action: { type: 'STRING' } }, required: ['action'] } },
    { name: 'show_code', description: 'Yazdığın kodu bu cihazın ekranında göster (kopyalanabilir, indirilebilir) ve ortak hafızaya kaydet. Kod yazman istenince bunu kullan; kodu sesli okuma.',
      parameters: { type: 'OBJECT', properties: { filename: { type: 'STRING' }, language: { type: 'STRING' }, code: { type: 'STRING' }, note: { type: 'STRING' } }, required: ['filename', 'code'] } },
    { name: 'open_link', description: 'Bu cihazda bir web sayfası, video ya da harita aç (TV ve projeksiyonda tam ekran).',
      parameters: { type: 'OBJECT', properties: { url: { type: 'STRING' }, title: { type: 'STRING' } }, required: ['url'] } },
    { name: 'camera', description: 'Bu cihazın kamerasını aç/kapat ki görebilesin. facing: back | front.',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' }, facing: { type: 'STRING' } }, required: ['on'] } },
    { name: 'make_image', description: 'Resim çiz (yeni) ya da son çizilen resmi / kullanıcının seçtiği resmi değiştir. Çizim, logo, illüstrasyon, fotoğraf gibi görsel istenince kullan. prompt İngilizce ve ayrıntılı olsun; resimde olması gereken yazıyı kullanıcının kelimeleriyle ekle.',
      parameters: { type: 'OBJECT', properties: { prompt: { type: 'STRING' }, mode: { type: 'STRING', description: 'new | edit' }, aspect_ratio: { type: 'STRING', description: '1:1 16:9 9:16 4:3 3:4' } }, required: ['prompt'] } },
    { name: 'open_app', description: 'Bu cihazda bir uygulamayı ya da hizmeti aç: whatsapp (mesaj taslağıyla), youtube, spotify, maps (yol tarifi/yer), phone (arama), sms, email, instagram, camera, web arama. query: ne aranacak / kime / mesaj.',
      parameters: { type: 'OBJECT', properties: { app: { type: 'STRING' }, query: { type: 'STRING' }, to: { type: 'STRING', description: 'telefon numarası ya da e-posta' } }, required: ['app'] } },
    { name: 'screen_share', description: 'Bu cihazın ekranını görmek için kullanıcıdan ekran paylaşımı iste (kullanıcı onaylamalı).',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' } }, required: ['on'] } },
    { name: 'reminder', description: 'Bu cihazda hatırlatıcı / zamanlayıcı: "10 dakika sonra hatırlat", "saat 18:30\'da ilacı söyle", "zamanlayıcı kur". action: set | list | cancel. Zamanı gelince cihaz çalar, bildirim gösterir ve sen söylersin.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING', description: 'set | list | cancel' }, text: { type: 'STRING', description: 'ne hatırlatılacak' },
        minutes: { type: 'NUMBER', description: 'kaç dakika sonra (saniye için 0.5 gibi)' }, at: { type: 'STRING', description: 'saat "HH:MM" ya da "YYYY-MM-DD HH:MM"' },
        id: { type: 'STRING', description: 'iptal için hatırlatıcı numarası ya da metni' },
        repeat: { type: 'STRING', description: '"daily" = her gün aynı saatte; boşsa bir kez' },
        protocol: { type: 'STRING', description: 'zamanı gelince söylemek yerine çalıştırılacak protokolün adı ("her sabah 8\'de günaydın protokolü")' } }, required: ['action'] } },
    { name: 'send_to_device', description: 'Başka bir cihaza bir şey gönder ya da orada aç: "bunu televizyonda aç", "resmi tablete gönder", "kodu bilgisayara at", "telefona yaz". what: open (bağlantı/video/harita) | image (son resim) | code (son kod) | text | say (o cihaz sesli söylesin). device: cihazın adı ya da türü (telefon, tablet, tv, projeksiyon, saat, bilgisayar).',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING' }, what: { type: 'STRING', description: 'open | image | code | text | say' },
        url: { type: 'STRING' }, text: { type: 'STRING' }, title: { type: 'STRING' } }, required: ['device', 'what'] } },
    { name: 'projects', description: 'Bilgisayarda MAYK\'ın yaptığı/yarım kalan projelerin (site, uygulama, kod) güncel durumu: "projem ne durumda", "site bitti mi". Devam ettirmek için computer_command ile "yarım kalan işe devam et" gönder.',
      parameters: { type: 'OBJECT', properties: {} } },
    { name: 'protocol', description: 'Protokoller (Iron Man tarzı): tek komutla sırayla birçok iş. "çalışma protokolü", "film moduna geç", "uyku protokolü", "günaydın", "protokollerim neler", "yeni protokol kaydet". action: run | list | save | delete. run bir adım listesi döner: o adımları sırayla araçlarınla yap.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, name: { type: 'STRING' }, steps: { type: 'ARRAY', items: { type: 'STRING' } } }, required: ['action'] } },
    { name: 'status_report', description: 'Iron Man tarzı durum raporu: bütün cihazlar (açık/kapalı, pil, işlemci, bellek, disk), sıradaki hatırlatıcılar, yapılacaklar, bilgisayardaki projeler. "durum raporu", "sistemler nasıl", "cihazlarım ne durumda", "laptopun şarjı kaç".',
      parameters: { type: 'OBJECT', properties: {} } },
    { name: 'guard', description: 'Güvenlik modu: bu cihazın (ya da device verilirse o cihazın) kamerası odayı izler; hareket olursa fotoğraf çekip bütün cihazlara gönderir ve sesli haber verir. "odayı izle", "güvenlik modunu aç/kapat", "tableti kamera yap".',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' }, device: { type: 'STRING', description: 'boşsa bu cihaz' } }, required: ['on'] } },
    { name: 'find_device', description: '"Telefonumu bul", "tablet nerede": o cihaz yüksek sesle çalar ve titrer (MAYK sayfası açıksa). device: cihazın adı ya da türü.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING' } }, required: ['device'] } },
    { name: 'gallery', description: 'Bütün cihazlarda çizilen resimlerin ortak galerisi: "galerimde ne var", "dünkü resmi göster", "laptopta çizdiğin logoyu aç", "ikinci resmi TV\'ye gönder". action: list | show | send. number: 1 = en yeni, ya da query: resimde ne vardı. send için device.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, number: { type: 'NUMBER' }, query: { type: 'STRING' }, device: { type: 'STRING' } }, required: ['action'] } },
    { name: 'place', description: 'Konum hafızası: "arabamı buraya park ettim", "bu yeri otel diye kaydet" (save: bu cihazın şu anki konumu), "arabam nerede", "otele yol tarifi" (find: haritada açar; device verilirse o cihazda açar), "kayıtlı yerlerim" (list), forget.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING', description: 'save | find | list | forget' }, name: { type: 'STRING', description: 'araba, otel, ev …' }, device: { type: 'STRING' } }, required: ['action'] } },
    { name: 'computer_screen', description: 'Bilgisayarın ekranını bu cihazda gör: "bilgisayarın ekranında ne var", "laptopta indirme bitti mi bak", "ekranını göster". Ekran görüntüsü gelir, ekranda açılır ve sen de bakıp anlatırsın. question: ekranda neye bakılacağı.',
      parameters: { type: 'OBJECT', properties: { device: { type: 'STRING' }, question: { type: 'STRING' } } } },
    { name: 'search_history', description: 'Bütün cihazlardaki geçmiş konuşmaların kalıcı arşivinde ara: "geçen hafta ne konuşmuştuk", "annemin doğum günü hakkında ne demiştim", "dün telefonda bahsettiğim film neydi". days: kaç gün geriye (boşsa hepsi).',
      parameters: { type: 'OBJECT', properties: { query: { type: 'STRING' }, days: { type: 'NUMBER' } }, required: ['query'] } },
    { name: 'background_task', description: 'Bilgisayarda uzun bir işi arka planda başlat: araştırma yapıp rapor yazmak, bir web sitesi/uygulama kodlamak, dosyaları düzenlemek. Kullanıcı başka işlerle uğraşırken sürer; bitince sonuç bu cihaza gelir ve sen söylersin. "araştır ve rapor hazırla", "bana bir site yap", "şu projeyi bitir".',
      parameters: { type: 'OBJECT', properties: { task: { type: 'STRING', description: 'yapılacak işin tam tarifi, Türkçe' }, kind: { type: 'STRING', description: 'research | code | other' } }, required: ['task'] } },
    { name: 'notifications', description: 'Sayfa kapalıyken de bildirim almak: kullanıcıya Ayarlar\'daki "🔔 Bildirimleri aç" tuşuna basmasını söyler (tarayıcı izni bir dokunuş ister).',
      parameters: { type: 'OBJECT', properties: {} } },
    { name: 'weather', description: 'Hava durumu (gerçek veri): şu an, bugün, yarın ve önümüzdeki günler; sıcaklık, gökyüzü, yağış ihtimali. city boşsa bu cihazın konumu. "hava nasıl", "yarın yağmur yağacak mı", "Lefkoşa\'da hafta sonu hava".',
      parameters: { type: 'OBJECT', properties: { city: { type: 'STRING' }, days: { type: 'NUMBER', description: '1-7, varsayılan 3' } } } },
    { name: 'currency', description: 'Döviz kuru ve çevirme (Avrupa Merkez Bankası günlük kurları): "dolar kaç TL", "250 euro kaç lira". base, targets (virgülle), amount.',
      parameters: { type: 'OBJECT', properties: { base: { type: 'STRING' }, targets: { type: 'STRING' }, amount: { type: 'NUMBER' } }, required: ['base'] } },
    { name: 'chess', description: 'Bu cihazda kullanıcıyla satranç oyna (ekrandaki tahta). action: open | new (color white/black, level kolay/orta/zor) | move (move: SAN "Nf3", koordinat "e2e4" ya da Türkçe "at f3") | undo | resign | status | hint (en iyi hamleyi göster) | teach (on: true/false — öğretme modu: her hamleyi değerlendir, daha iyisini ve nedenini öğret). Hamleleri Türkçe söyle (at, fil, kale, vezir, şah).',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, move: { type: 'STRING' }, color: { type: 'STRING' }, level: { type: 'STRING' }, on: { type: 'BOOLEAN' } }, required: ['action'] } },
    { name: 'coffee_fortune', description: 'Kahve falı (eğlence): fal ekranını açar; kullanıcı fincanın fotoğrafını çekince falı okur. "falıma bak", "kahve falı".',
      parameters: { type: 'OBJECT', properties: { question: { type: 'STRING', description: 'kullanıcının merak ettiği konu (aşk, iş …)' } } } },
    { name: 'projector', description: 'Projeksiyonu (HY320) ya da Android TV\'yi kontrol et — projeksiyondaki MAYK Alıcı uygulamasıyla (laptop kapalıyken de) ya da laptop üzerinden. op: app (arg: youtube, netflix …) | search (arg: aranacak; where: youtube|google) | type (arg: odaklı kutuya yazılacak, Türkçe olur) | key (arg: up, down, left, right, ok, back, home, volume_up, volume_down, mute, play_pause, next, previous, power) | url (arg) | look (ekranına bak; question) | wifi (arg: ağ adı, password) | jarvis (MAYK\'ı projeksiyonda aç) | apps. Kumanda ekranı için open: true.',
      parameters: { type: 'OBJECT', properties: { op: { type: 'STRING' }, arg: { type: 'STRING' }, where: { type: 'STRING' }, password: { type: 'STRING' }, question: { type: 'STRING' }, open: { type: 'BOOLEAN' } } } },
    { name: 'todo', description: 'Ortak yapılacaklar listesi (tüm cihazlar ve bilgisayar aynı listeyi görür): "listeye süt ekle", "yapılacaklarım ne", "faturayı ödedim, sil". action: add | list | done | clear_done | clear (tüm listeyi sil).',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, item: { type: 'STRING' } }, required: ['action'] } },
  ];
  const extraTools = {}, extraPrompt = [];
  let lastCode = null;
  async function runTool(name, a) {
    a = a || {};
    if (extraTools[name]) return await extraTools[name](a);
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
        // Turkish adds endings ("annemin", "annemle"): compare word stems.
        const stem = w => w.length > 5 ? w.slice(0, Math.max(4, w.length - 3)) : w;
        const q = String(a.query || '').toLocaleLowerCase('tr').split(/[^\p{L}\p{N}]+/u).filter(w => w.length > 1).map(stem);
        const hits = [];
        for (const c of CATS) for (const [k, v] of Object.entries(memory[c] || {})) {
          const s = (k + ' ' + entry(v).value).toLocaleLowerCase('tr');
          const score = q.filter(w => s.includes(w)).length;
          if (score) hits.push([score, `${c}/${k}: ${entry(v).value}`]);
        }
        hits.sort((x, y) => y[0] - x[0]);
        return hits.slice(0, 12).map(h => h[1]).join('\n') || 'Hafızada bununla ilgili bir şey yok.';
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
      case 'make_image': {
        // Drawing can take half a minute; the conversation goes on meanwhile and
        // MAYK says so when the picture is on screen.
        const edit = String(a.mode || 'new') === 'edit';
        if (imgBusy) return 'Önceki resmi hâlâ çiziyorum; o bitince bunu yaparım.';
        if (edit && !lastImage) return 'Değiştirilecek resim yok; önce yeni bir resim çizeyim mi?';
        makeImage(String(a.prompt || ''), edit, String(a.aspect_ratio || ''))
          .then(msg => { if (!/ekranda/.test(msg)) toast(msg); tellBrain(msg + (/ekranda/.test(msg) ? '' : ' Kullanıcıya nedenini kısaca söyle.')); })
          .catch(e => tellBrain('Resim üretilemedi: ' + (e.message || e)));
        return edit ? 'Resmi değiştirmeye başladım; arka planda sürüyor, bitince ekrana gelecek. Kullanıcıya kısaca "değiştiriyorum" de, "yapamam" deme.'
                    : 'Çizmeye başladım; arka planda sürüyor, 10-30 saniyede ekrana gelecek. Kullanıcıya kısaca "çiziyorum" de, "yapamam" deme.';
      }
      case 'reminder': return reminderTool(a);
      case 'todo': return todoTool(a);
      case 'projector': {
        if (a.open) { $('t-remote').click(); if (!a.op) return 'Kumanda ekranı açıldı.'; }
        const op = String(a.op || '').toLowerCase();
        if (!op) return 'Ne yapayım? (op gerekli)';
        await syncNow();
        const rx = receiver();
        if (rx && online(rx)) {
          const r = await sendToReceiver(rx, { op, arg: String(a.arg || ''), where: a.where || 'youtube', password: a.password || '', question: a.question || '', enter: true });
          if (op === 'look') { setTimeout(() => syncNow(), 2500); setTimeout(() => syncNow(), 6000); return r + ' Görüntü gelince ekranda açılacak; o zaman ne olduğunu anlat.'; }
          return r;
        }
        const pc = findPc('');
        if (pc && online(pc)) return await sendToPc('', `Projeksiyon/TV (android_device aracı): ${op} ${a.arg || ''} ${a.where || ''} ${a.question || ''}`.trim());
        return 'Projeksiyonu kontrol edecek bir şey açık değil: projeksiyona MAYK Alıcı uygulamasını kur (laptop kapalıyken de çalışır) ya da laptopu aç.';
      }
      case 'chess': return chessTool(a);
      case 'coffee_fortune': {
        openSheet('s-fal');
        if (falImages.length) { const t = await readFortune(String(a.question || '')); return t.length > 40 ? 'Fal hazır ve ekranda; bunu sıcak bir falcı gibi sesli oku: ' + t : t; }
        return 'Fal ekranı açıldı: kullanıcı "Fotoğraf çek" ile fincanın içini (ve tabağı) çeksin, sonra "Falıma bak"a bassın. Bunu ona söyle.';
      }
      case 'weather': return await weatherTool(a);
      case 'currency': return await currencyTool(a);
      case 'notifications': {
        if ('Notification' in window && Notification.permission === 'granted' && J(localStorage.getItem('jarvis_push_key'), '')) return 'Bildirimler bu cihazda zaten açık.';
        openSetup(); return 'Ayarlar açıldı: kullanıcı "🔔 Bildirimleri aç" tuşuna bassın (izin bir dokunuş ister). Bunu ona söyle.';
      }
      case 'background_task': {
        const kind = String(a.kind || 'other'), task = String(a.task || '').trim();
        if (!task) return 'Ne yapılacak?';
        const words = kind === 'code' ? `Arka planda kodlama işi başlat (dev_agent, aşamalı proje): ${task}`
                    : kind === 'research' ? `Arka planda araştırma görevi başlat ve rapor yaz (background task): ${task}`
                    : `Arka planda görev olarak başlat: ${task}`;
        const r = await sendToPc('', words);
        return r + ' (İş bilgisayarda arka planda sürüyor; bitince sonuç bu cihaza gelecek.)';
      }
      case 'search_history': return await Archive.search(String(a.query || ''), Number(a.days) || 0);
      case 'computer_screen': {
        const pc = findPc(a.device);
        if (!pc) return 'Bağlı bir bilgisayar yok.';
        const r = await sendToPc(pc.name, 'Ekranının görüntüsünü bana gönder.', { kind: 'screenshot', reply_to: S.id, question: String(a.question || '') });
        setTimeout(() => syncNow(), 2500); setTimeout(() => syncNow(), 6000);
        return r + ' Görüntü gelince ekranda açılacak ve sana göstereceğim; o zaman anlat.';
      }
      case 'place': return await placeTool(a);
      case 'gallery': {
        await syncNow();
        const newest = [...gallery].reverse();
        if (!newest.length) return 'Galeri boş. Bir resim çizeyim mi?';
        const act = String(a.action || 'list').toLowerCase();
        if (act === 'list') return 'Galeri (en yeni önce):\n' + newest.slice(0, 10).map((g, i) => `${i + 1}. ${g.prompt.slice(0, 70)} — ${g.from}, ${String(g.ts).slice(0, 16).replace('T', ' ')}`).join('\n');
        const q = String(a.query || '').toLocaleLowerCase('tr').trim();
        const g = q ? newest.find(x => x.prompt.toLocaleLowerCase('tr').includes(q)) : newest[Math.max(1, +a.number || 1) - 1];
        if (!g) return 'Galeride öyle bir resim bulamadım.';
        if (act === 'send') return await sendToDevice(a.device, { kind: 'image', url: g.url, mime: 'image/jpeg', prompt: g.prompt, en: g.en || '', seed: g.seed || 0, title: g.prompt.slice(0, 80) });
        keepImage({ data: '', mime: 'image/jpeg', url: g.url, prompt: g.prompt, en: g.en || '', seed: g.seed || 0 });
        showImage(`${g.from} çizmişti`);
        return `Ekranda: ${g.prompt.slice(0, 80)}.`;
      }
      case 'find_device': {
        const d = findDevice(a.device);
        if (!d) return `"${a.device}" adında bir cihaz bulamadım.`;
        if (d.kind === 'pc') return await sendToPc(d.name, 'quick:volume_up');
        return (await sendToDevice(d.name, { kind: 'ring' })) + ' Birkaç saniye içinde çalmaya başlar' + (online(d) ? '.' : '; ama şu an kapalı görünüyor, MAYK sayfası açık değilse çalamaz.');
      }
      case 'guard': {
        if (a.device && findDevice(a.device)) return await sendToDevice(a.device, { kind: 'guard', on: !!a.on });
        return a.on ? await startGuard() : stopGuard();
      }
      case 'status_report': return await statusReport();
      case 'protocol': return protocolTool(a);
      case 'projects': { await syncNow(); return projectsText() || 'Bilgisayarlarda kayıtlı bir proje yok (ya da bilgisayar henüz bağlanmadı).'; }
      case 'send_to_device': {
        const what = String(a.what || 'open').toLowerCase(), title = String(a.title || '');
        if (what === 'image') {
          if (!lastImage) return 'Gönderilecek resim yok.';
          return await sendToDevice(a.device, { kind: 'image', data: lastImage.url ? '' : lastImage.data, url: lastImage.url || '', mime: lastImage.mime,
                                                prompt: lastImage.prompt, en: lastImage.en || '', seed: lastImage.seed || 0, title });
        }
        if (what === 'code') {
          if (!lastCode && !a.text) return 'Gönderilecek kod yok.';
          return await sendToDevice(a.device, { kind: 'code', text: a.text || lastCode.code, filename: lastCode?.filename || title || 'kod.txt', title });
        }
        if (what === 'open') { const url = String(a.url || ''); if (!/^https?:\/\//i.test(url)) return 'Geçerli bir adres lazım.'; return await sendToDevice(a.device, { kind: 'open', url, title }); }
        if (!a.text) return 'Ne göndereyim?';
        return await sendToDevice(a.device, { kind: what === 'say' ? 'say' : 'text', text: String(a.text), title });
      }
      case 'open_app': return openApp(String(a.app || ''), String(a.query || ''), String(a.to || ''));
      case 'camera': return a.on ? await startVideo('camera', a.facing === 'front' ? 'user' : 'environment') : (stopVideo(), 'Kamera kapandı.');
      case 'screen_share':
        if (!a.on) { stopVideo(); return 'Ekran paylaşımı kapandı.'; }
        if (!navigator.mediaDevices?.getDisplayMedia) return 'Bu cihaz ekran paylaşamıyor (telefonlar desteklemiyor). Kamerayı açabilirim.';
        askUser('Ekranı göster', 'MAYK ekranını görmek istiyor.', () => startVideo('screen'));
        return 'Kullanıcıdan ekran paylaşımı onayı istendi.';
    }
    return 'Bilinmeyen araç.';
  }
  // ── pictures: Gemini's image models when the key has quota; otherwise
  // Gemini's free text model describes the picture and a free, keyless painter
  // (Pollinations / FLUX) draws it. Gemini image models have no free tier
  // ("429 … limit: 0"), so without this a free key could never draw.
  const IMAGE_MODELS = ['gemini-3.1-flash-image', 'gemini-3-pro-image', 'gemini-3-pro-image-preview', 'gemini-2.5-flash-image'];
  const TEXT_MODELS = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.5-flash-lite'];
  const NOQ_KEY = 'jarvis_img_noq', NOQ_REST = 6 * 3600e3;
  let lastImage = (() => { try { return JSON.parse(sessionStorage.getItem('jarvis_img') || 'null'); } catch { return null; } })();
  let imgBusy = false;
  const geminiResting = () => { try { return Number(localStorage.getItem(NOQ_KEY) || 0) > Date.now(); } catch { return false; } };
  const restGemini = (on) => { try { on ? localStorage.setItem(NOQ_KEY, String(Date.now() + NOQ_REST)) : localStorage.removeItem(NOQ_KEY); } catch {} };
  const noQuota = (e) => /limit: 0|free_tier|billing|^40[34]\b/i.test(e);
  function keepImage(img) {
    lastImage = img;
    try { sessionStorage.setItem('jarvis_img', JSON.stringify(lastImage)); }
    catch { try { sessionStorage.setItem('jarvis_img', JSON.stringify({ ...img, data: '' })); } catch {} }
  }
  async function geminiImage(prompt, edit, aspect) {
    const parts = edit && lastImage?.data
      ? [{ inlineData: { mimeType: lastImage.mime, data: lastImage.data } }, { text: 'Edit this image: ' + prompt + '\nKeep everything else the same unless asked.' }]
      : [{ text: prompt }];
    const gen = { responseModalities: ['TEXT', 'IMAGE'] };
    if (/^\d+:\d+$/.test(aspect)) gen.imageConfig = { aspectRatio: aspect };
    const errors = [];
    for (const model of IMAGE_MODELS) {
      let js;
      try {
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'x-goog-api-key': S.key },
          body: JSON.stringify({ contents: [{ role: 'user', parts }], generationConfig: gen }) });
        js = await r.json();
        if (!r.ok) { errors.push(`${r.status} ${js.error?.message || ''}`); if ([404, 403, 429, 500, 503].includes(r.status)) continue; break; }
      } catch (e) { errors.push(String(e.message || e)); continue; }
      let text = '';
      for (const c of js.candidates || []) for (const p of c.content?.parts || []) {
        const d = p.inlineData || p.inline_data;
        if (d?.data && !p.thought) return { img: { data: d.data, mime: d.mimeType || 'image/png', prompt }, text };
        if (p.text && !p.thought) text += p.text;
      }
      if (js.promptFeedback?.blockReason) return { blocked: true };
      errors.push(text || 'resim dönmedi');
    }
    return { errors };
  }
  async function describe(prompt, base) {
    const ask = base
      ? `You rewrite image-generation prompts. Prompt of the existing picture:\n${base}\n\nThe user wants this change (any language): ${prompt}\nWrite the full new prompt in English: keep everything the same (subject, composition, style, colours, lighting) except what the change asks. Answer with the prompt only, at most 90 words.`
      : `Turn this picture request (any language) into one vivid English prompt for an image generator: subject, setting, style, lighting, composition. Keep any text that must appear in the picture exactly as given, in quotes. Answer with the prompt only, at most 80 words.\n\nRequest: ${prompt}`;
    if (S.key) for (const model of TEXT_MODELS) {
      try {
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'x-goog-api-key': S.key },
          body: JSON.stringify({ contents: [{ role: 'user', parts: [{ text: ask }] }] }) });
        if (!r.ok) continue;
        const js = await r.json();
        const out = (js.candidates?.[0]?.content?.parts || []).filter(p => p.text && !p.thought).map(p => p.text).join('').trim()
          .replace(/^"|"$/g, '').replace(/^(new )?prompt\s*:\s*/i, '');
        if (out.length >= 10) return out.slice(0, 1500);
      } catch {}
    }
    return base ? `${base}. Change: ${prompt}` : prompt;
  }
  function imageSize(aspect) {
    const m = /^(\d+):(\d+)$/.exec(aspect || ''); if (!m) return [1024, 1024];
    const a = +m[1], b = +m[2]; if (!a || !b) return [1024, 1024];
    const [w, h] = a >= b ? [1024, 1024 * b / a] : [1024 * a / b, 1024];
    return [Math.max(64, Math.round(w / 64) * 64), Math.max(64, Math.round(h / 64) * 64)];
  }
  const blobToB64 = (blob) => new Promise((res, rej) => { const f = new FileReader(); f.onload = () => res(String(f.result).split(',')[1] || ''); f.onerror = rej; f.readAsDataURL(blob); });
  async function freeImage(en, aspect, seed) {
    const [w, h] = imageSize(aspect);
    const url = `https://image.pollinations.ai/prompt/${encodeURIComponent(en)}?width=${w}&height=${h}&seed=${seed}&model=flux&nologo=true&enhance=false&referrer=jarvis`;
    let err = '';
    for (let i = 0; i < 3; i++) {
      try {
        const r = await fetch(url);
        if (r.ok) {
          const blob = await r.blob();
          if (blob.type.startsWith('image/') && blob.size > 1000) return { data: await blobToB64(blob), mime: blob.type, url };
          err = 'resim dönmedi';
        } else err = String(r.status);
        if (r.status && ![429, 500, 502, 503, 504].includes(r.status)) break;
      } catch (e) {
        // Fetch blocked (CORS / network): the <img> tag can still show it.
        const ok = await new Promise(res => { const im = new Image(); im.onload = () => res(true); im.onerror = () => res(false); im.src = url; });
        if (ok) return { data: '', mime: 'image/jpeg', url };
        err = String(e.message || e);
      }
      await new Promise(r => setTimeout(r, err === '429' ? 16000 : 4000));
    }
    return { err };
  }
  async function makeImage(prompt, edit, aspect) {
    if (!prompt) return 'Ne çizeyim?';
    if (imgBusy) return 'Önceki resmi hâlâ çiziyorum.';
    if (edit && !lastImage) return 'Değiştirilecek resim yok; önce bir resim çizeyim mi?';
    imgBusy = true; toast(edit ? '🎨 Resim değiştiriliyor…' : '🎨 Çiziliyor…');
    try {
      let errors = [];
      if (S.key && !geminiResting() && !(edit && !lastImage.data)) {
        const g = await geminiImage(prompt, edit, aspect);
        if (g.blocked) return 'Bu resmi güvenlik kuralları yüzünden çizemiyorum.';
        if (g.img) {
          restGemini(false); keepImage({ ...g.img, prompt: edit ? `${lastImage.prompt} → ${prompt}` : prompt });
          showImage(g.text);
          return edit ? 'Resim değiştirildi ve ekranda.' : 'Resim çizildi ve ekranda.';
        }
        errors = g.errors || [];
        if (errors.length && errors.every(noQuota)) restGemini(true);
        console.warn('[resim] Gemini çizemedi, ücretsiz ressama geçiliyor:', errors.at(-1));
      }
      const base = edit ? (lastImage.en || lastImage.prompt || '') : '';
      const seed = edit && lastImage.seed ? lastImage.seed : Math.floor(Math.random() * 2e9) + 1;
      const en = await describe(prompt, base);
      const f = await freeImage(en, aspect, seed);
      if (f.err) return 'Resim üretilemedi (' + [...errors.slice(-1), 'ücretsiz ressam: ' + f.err].join('; ').slice(0, 200) + '). Biraz sonra tekrar deneyeyim mi?';
      keepImage({ data: f.data, mime: f.mime, url: f.url, en, seed, prompt: edit ? `${lastImage.prompt} → ${prompt}` : prompt });
      galleryNew.push({ id: S.id + '-' + Date.now().toString(36), prompt: lastImage.prompt.slice(0, 200), url: f.url, en, seed, from: devName(), ts: nowIso() });
      syncSoon();
      showImage('');
      return edit ? 'Resim değiştirildi ve ekranda.' : 'Resim çizildi ve ekranda.';
    } finally { imgBusy = false; }
  }
  function showImage(note) {
    if (!lastImage) return;
    $('img-view').src = lastImage.data ? `data:${lastImage.mime};base64,${lastImage.data}` : (lastImage.url || '');
    $('img-note').textContent = note || lastImage.prompt || '';
    openSheet('s-image');
    if (KIND === 'tv' || KIND === 'projector') { try { $('img-view').requestFullscreen?.(); } catch {} }
  }
  $('t-image').onclick = () => { if (lastImage) showImage(); else { $('inp').value = 'Bir resim çiz: '; $('inp').focus(); } };
  $('img-edit').addEventListener('submit', async (e) => {
    e.preventDefault();
    const t = $('img-edit-inp').value.trim(); if (!t) return;
    $('img-edit-inp').value = ''; claimHere();
    const msg = await makeImage(t, true, '');
    if (!/değiştirildi/.test(msg)) toast(msg);
  });
  function imageBlob() { if (!lastImage.data) return null; const b = atob(lastImage.data), u = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return new Blob([u], { type: lastImage.mime }); }
  $('img-dl').onclick = () => { if (!lastImage) return; if (!lastImage.data) { window.open(lastImage.url, '_blank'); return; } const a = document.createElement('a'); a.href = URL.createObjectURL(imageBlob());
    a.download = 'jarvis-' + Date.now() + (lastImage.mime.includes('jpeg') ? '.jpg' : '.png'); a.click(); };
  $('img-share').onclick = async () => {
    if (!lastImage) return;
    if (!lastImage.data) { try { await navigator.share({ url: lastImage.url, title: 'MAYK' }); } catch { window.open(lastImage.url, '_blank'); } return; }
    const file = new File([imageBlob()], 'jarvis.png', { type: lastImage.mime });
    try { if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: 'MAYK' }); else $('img-dl').click(); } catch {}
  };
  $('img-full').onclick = () => { try { $('img-view').requestFullscreen(); } catch {} };

  // ── apps on this device: links that open the installed app ──────────────
  function openApp(app, q, to) {
    const e = encodeURIComponent;
    const a = app.toLocaleLowerCase('tr');
    let url = '';
    if (/whats/.test(a)) url = to ? `https://wa.me/${to.replace(/[^\d]/g, '')}?text=${e(q)}` : `https://wa.me/?text=${e(q)}`;
    else if (/youtube|video/.test(a)) url = q ? `https://www.youtube.com/results?search_query=${e(q)}` : 'https://www.youtube.com/';
    else if (/spotify|müzik|music/.test(a)) url = q ? `https://open.spotify.com/search/${e(q)}` : 'https://open.spotify.com/';
    else if (/map|harita|yol/.test(a)) url = `https://www.google.com/maps/search/?api=1&query=${e(q || to)}`;
    else if (/phone|ara|tel/.test(a)) url = 'tel:' + (to || q).replace(/[^\d+]/g, '');
    else if (/sms|mesaj/.test(a)) url = `sms:${(to || '').replace(/[^\d+]/g, '')}?body=${e(q)}`;
    else if (/mail|e-posta|eposta/.test(a)) url = `mailto:${to}?body=${e(q)}`;
    else if (/insta/.test(a)) url = q ? `https://www.instagram.com/${e(q.replace(/^@/, ''))}/` : 'https://www.instagram.com/';
    else if (/camera|kamera/.test(a)) { startVideo('camera'); return 'Kamera açıldı.'; }
    else url = `https://www.google.com/search?q=${e(q || app)}`;
    const w = window.open(url, '_blank');
    if (!w) askUser('Uygulamayı aç', `${app} açılsın mı?`, () => window.open(url, '_blank'));
    return `${app} açılıyor.`;
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

  // Something finished in the background (a picture, a reminder): the brain
  // hears it as a note and tells the user in its own voice.
  function tellBrain(note) {
    if (ws && ready && amOwner()) send({ realtimeInput: { text: `(Sistem notu, kullanıcı söylemedi) ${note} Bunu kullanıcıya tek kısa cümleyle söyle.` } });
    else sys(note);
  }

  // ── protocols: one command, many steps (plugins/protocol.py has the same
  // names, steps and storage: preferences / "protokol: <ad>") ───────────────
  const PROTOCOLS = {"sabah": ["Günaydın de; bugünün tarihini ve Google aramasıyla bulunduğun yerin hava durumunu kısaca söyle", "Bugünün hatırlatıcılarını ve yapılacaklar listesini oku", "Yarım kalan proje varsa durumunu tek cümleyle söyle"], "çalışma": ["Bilgisayarda çalan müziği durdur ve sesi yüzde 20'ye indir", "Yapılacaklar listesini oku ve hangisiyle başlamak istediğini sor", "45 dakika sonrasına 'mola ver' hatırlatıcısı kur"], "film": ["Televizyonda YouTube'u aç (send_to_device, open); ne izlemek istediğini sor", "Bilgisayarda çalan müziği durdur", "Film bitince haber vermek için süre isterse hatırlatıcı kur"], "akşam": ["Bugün bütün cihazlarda neler konuştuğumuzu ve yapılanları arşivden kısaca özetle", "Biten yapılacakları sor, bitenleri listeden çıkar", "Yarının hatırlatıcılarını söyle ve eklenecek bir şey var mı sor"], "uyku": ["Yarının hatırlatıcılarını ve yapılacakları kısaca söyle", "Sabah için hatırlatıcı/alarm isteyip istemediğini sor, isterse kur", "İyi geceler de ve bilgisayarı kilitle"]};
  const PROTO_ALIASES = {"günaydın": "sabah", "sabah": "sabah", "çalış": "çalışma", "iş": "çalışma", "odak": "çalışma", "akşam": "akşam", "gün sonu": "akşam", "film": "film", "sinema": "film", "dizi": "film", "uyku": "uyku", "gece": "uyku", "yat": "uyku"};
  const PROTO = 'protokol: ';
  const protoNorm = n => String(n || '').toLocaleLowerCase('tr').replace('protokolü', '').replace('protokol', '').replace('moduna', '').replace('modu', '').trim().replace(/\s+/g, ' ').replace(/^[-: ]+|[-: ]+$/g, '');
  function savedProtocols() {
    const out = {};
    for (const [k, v] of Object.entries(memory.preferences || {})) if (k.startsWith(PROTO)) out[k.slice(PROTO.length)] = entry(v).value.split('|').map(x => x.trim()).filter(Boolean);
    return out;
  }
  function protocolTool(a) {
    const act = String(a.action || 'run').toLowerCase(), n = protoNorm(a.name), saved = savedProtocols();
    const names = [...new Set([...Object.keys(PROTOCOLS), ...Object.keys(saved)])];
    if (act === 'list') return `Protokoller: ${names.join(', ')}. Hangisini başlatayım?`;
    if (act === 'save') {
      const steps = (Array.isArray(a.steps) ? a.steps : String(a.steps || '').split(/\n|\|/)).map(x => String(x).trim()).filter(Boolean);
      if (!n || !steps.length) return 'Protokolün adı ve adımları lazım.';
      const text = steps.join(' | ');
      if (text.length > 370) return 'Bu protokol çok uzun; adımları kısalt (en fazla 370 harf).';
      memory.preferences = memory.preferences || {}; memory.preferences[PROTO + n] = { value: text, updated: nowIso() };
      localStorage.setItem('jarvis_mem', JSON.stringify(memory)); syncNow();
      return `'${n}' protokolü kaydedildi (${steps.length} adım); bütün cihazlar biliyor.`;
    }
    if (act === 'delete') {
      if (!(n in saved)) return 'Böyle kayıtlı bir protokol yok.';
      delete memory.preferences[PROTO + n]; memory._deleted = memory._deleted || {}; memory._deleted['preferences/' + PROTO + n] = nowIso();
      localStorage.setItem('jarvis_mem', JSON.stringify(memory));
      if (Cloud.ok()) Cloud.write({ 'memory.json': JSON.stringify(memory) }).catch(() => {});
      return `'${n}' protokolü silindi.`;
    }
    let key = '', steps = null;
    if (n && saved[n]) { key = n; steps = saved[n]; }
    if (!steps && n) { const k = Object.keys(saved).find(k => k.includes(n) || n.includes(k)); if (k) { key = k; steps = saved[k]; } }
    if (!steps && n) { const base = PROTO_ALIASES[n] || Object.entries(PROTO_ALIASES).find(([k]) => n.includes(k))?.[1]; if (base) { key = base; steps = saved[base] || PROTOCOLS[base]; } }
    if (!steps) return `'${a.name || ''}' diye bir protokol yok. Var olanlar: ${names.join(', ')}. İstersen adımlarını söyle, kaydedeyim.`;
    toast(`⚡ ${key.toLocaleUpperCase('tr')} PROTOKOLÜ`);
    return `${key.toLocaleUpperCase('tr')} PROTOKOLÜ BAŞLADI. Şimdi bu adımları sırayla, kendi araçlarınla yap (bilgisayarın yapacağı işler için computer_command, başka cihaz için send_to_device); yapamadığını atla ve sonunda ne yaptığını kısaca söyle:\n` +
      steps.map((x, i) => `${i + 1}. ${x}`).join('\n');
  }

  // ── places: "arabamı buraya park ettim" → shared memory notes / "konum: …" ──
  const PLACE = 'konum: ';
  function here() {
    return new Promise((res, rej) => {
      if (!navigator.geolocation) return rej(new Error('Bu cihaz konum vermiyor.'));
      navigator.geolocation.getCurrentPosition(p => res(p.coords), e => rej(new Error(e.code === 1 ? 'Konum izni verilmedi.' : 'Konum alınamadı.')),
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 });
    });
  }
  async function placeTool(a) {
    const act = String(a.action || 'find').toLowerCase();
    const name = String(a.name || 'araba').toLocaleLowerCase('tr').replace(/^(benim |bu )/, '').trim();
    memory.notes = memory.notes || {};
    const places = Object.entries(memory.notes).filter(([k]) => k.startsWith(PLACE));
    if (act === 'list') return places.length ? places.map(([k, v]) => `${k.slice(PLACE.length)} — ${entry(v).value.split('|')[1]?.trim() || ''}`).join('\n') : 'Kayıtlı yer yok.';
    if (act === 'save') {
      let c; try { c = await here(); } catch (e) { return e.message; }
      const when = new Date().toLocaleString('tr-TR', { weekday: 'short', hour: '2-digit', minute: '2-digit' });
      memory.notes[PLACE + name] = { value: `${c.latitude.toFixed(6)},${c.longitude.toFixed(6)} | ${when} | ±${Math.round(c.accuracy)} m`, updated: nowIso() };
      localStorage.setItem('jarvis_mem', JSON.stringify(memory)); syncNow();
      return `"${name}" konumu kaydedildi (±${Math.round(c.accuracy)} m). Bütün cihazlar biliyor.`;
    }
    const hit = places.find(([k]) => k.slice(PLACE.length) === name) || places.find(([k]) => k.includes(name));
    if (!hit) return `"${name}" diye kayıtlı bir yer yok.`;
    if (act === 'forget') {
      delete memory.notes[hit[0]]; memory._deleted = memory._deleted || {}; memory._deleted['notes/' + hit[0]] = nowIso();
      localStorage.setItem('jarvis_mem', JSON.stringify(memory)); if (Cloud.ok()) Cloud.write({ 'memory.json': JSON.stringify(memory) }).catch(() => {});
      return `"${hit[0].slice(PLACE.length)}" silindi.`;
    }
    const [coords, when] = entry(hit[1]).value.split('|').map(x => x.trim());
    const url = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(coords)}&travelmode=walking`;
    if (a.device && findDevice(a.device)) return await sendToDevice(a.device, { kind: 'open', url, title: hit[0].slice(PLACE.length) });
    const w = window.open(url, '_blank'); if (!w) askUser('Harita', `${hit[0].slice(PLACE.length)} haritada açılsın mı?`, () => window.open(url, '_blank'));
    return `"${hit[0].slice(PLACE.length)}" (${when} kaydedilmişti) haritada açılıyor, yol tarifiyle.`;
  }

  // ── live facts from free, keyless services (desktop: core/open_data.py) ──
  const WMO = { 0: 'açık', 1: 'çoğunlukla açık', 2: 'parçalı bulutlu', 3: 'kapalı', 45: 'sisli', 48: 'kırağılı sis', 51: 'hafif çisenti', 53: 'çisenti',
    55: 'yoğun çisenti', 61: 'hafif yağmurlu', 63: 'yağmurlu', 65: 'şiddetli yağmurlu', 71: 'hafif karlı', 73: 'karlı', 75: 'yoğun karlı',
    80: 'hafif sağanak', 81: 'sağanak', 82: 'şiddetli sağanak', 95: 'gök gürültülü fırtına', 96: 'dolulu fırtına', 99: 'şiddetli dolulu fırtına' };
  const WICON = c => c === 0 ? '☀️' : c <= 2 ? '⛅' : c === 3 ? '☁️' : c <= 48 ? '🌫️' : c <= 67 || (c >= 80 && c <= 82) ? '🌧️' : c <= 86 ? '❄️' : '⛈️';
  async function weatherData(city) {
    let lat, lon, place = city;
    if (city) {
      const g = await (await fetch('https://geocoding-api.open-meteo.com/v1/search?count=1&language=tr&name=' + encodeURIComponent(city))).json();
      const r = g.results?.[0]; if (!r) throw new Error(`'${city}' bulunamadı`);
      lat = r.latitude; lon = r.longitude; place = [r.name, r.country].filter(Boolean).join(', ');
    } else {
      const c = await here(); lat = c.latitude; lon = c.longitude; place = 'Bulunduğun yer';
    }
    const q = new URLSearchParams({ latitude: lat, longitude: lon, timezone: 'auto', forecast_days: 7,
      current: 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m',
      daily: 'temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max' });
    const js = await (await fetch('https://api.open-meteo.com/v1/forecast?' + q)).json();
    return { js, place };
  }
  async function weatherTool(a) {
    try {
      const { js, place } = await weatherData(String(a.city || '').trim());
      const c = js.current || {}, d = js.daily || {}, n = Math.max(1, Math.min(7, +a.days || 3));
      const days = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
      const L = [`${place}: şu an ${Math.round(c.temperature_2m)}°C, ${WMO[c.weather_code] || ''}, hissedilen ${Math.round(c.apparent_temperature)}°C, rüzgâr ${Math.round(c.wind_speed_10m)} km/s.`];
      for (let i = 0; i < n && i < (d.time || []).length; i++) L.push(`${i === 0 ? 'Bugün' : i === 1 ? 'Yarın' : days[new Date(d.time[i]).getDay()]}: ${Math.round(d.temperature_2m_min[i])}–${Math.round(d.temperature_2m_max[i])}°C, ${WMO[d.weather_code[i]] || ''}, yağış ihtimali %${d.precipitation_probability_max?.[i] ?? '?'}`);
      return L.join('\n');
    } catch (e) { return 'Hava durumu alınamadı: ' + (e.message || e); }
  }
  const CUR = { dolar: 'USD', usd: 'USD', euro: 'EUR', avro: 'EUR', eur: 'EUR', sterlin: 'GBP', pound: 'GBP', gbp: 'GBP', tl: 'TRY', lira: 'TRY', try: 'TRY', frank: 'CHF', yen: 'JPY', yuan: 'CNY' };
  const curCode = w => CUR[String(w || '').toLocaleLowerCase('tr').trim()] || String(w || '').toUpperCase().slice(0, 3);
  async function currencyTool(a) {
    try {
      const b = curCode(a.base || 'USD'), amt = +a.amount || 1;
      const tg = String(a.targets || 'TRY').split(/[,\s]+/).map(curCode).filter(t => t && t !== b);
      const js = await (await fetch(`https://api.frankfurter.dev/v1/latest?base=${b}&symbols=${(tg.length ? tg : ['TRY']).join(',')}&amount=${amt}`)).json();
      if (!js.rates) return 'Kur bulunamadı.';
      return Object.entries(js.rates).map(([k, v]) => `${amt} ${b} = ${v.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ${k}`).join('; ') + ` (Avrupa Merkez Bankası, ${js.date}).`;
    } catch (e) { return 'Kur alınamadı: ' + (e.message || e); }
  }

  // ── chess on every device (engine: web/chess.js, same as the desktop's) ──
  const CH = window.JarvisChess;
  // Built-in SVG pieces: no OS emoji fallback (iOS renders ♟ as a 3-D
  // black pawn even for the white side). Every piece uses the same viewBox.
  const PIECE_SHAPES = {
    p: '<circle cx="22.5" cy="12" r="5.4"/><path d="M19 17.5h7c0 5 4 9.5 5 15H14c1-5.5 5-10 5-15Z"/><path d="M13 32h19l2 5H11z"/><path d="M10 37h25v3H10z"/>',
    n: '<path d="M14 34c1-5 0-9-3-11l-4-3 5-6 6-2 1-7 5 5 5-1 5 11-3 14H14Z"/><path d="M10 20l6-1" fill="none" stroke="var(--piece-detail)" stroke-width="2"/><circle cx="21" cy="16" r="1.5" fill="var(--piece-detail)" stroke="none"/><path d="M12 34h22l2 5H10z"/>',
    b: '<circle cx="22.5" cy="6.5" r="2.3"/><path d="M22.5 9c5.2 4 9.2 9.8 8 15.8-.6 3.5-3.6 5.8-4.5 8.2h-7c-1-2.6-4.5-5.9-5-9.4-.8-5.4 3-11 8.5-14.6Z"/><path d="M28.7 14.2l-10.5 13" fill="none" stroke="var(--piece-detail)" stroke-width="2"/><path d="M14 33h17l2 5H12z"/><path d="M10 38h25v2H10z"/>',
    r: '<path d="M10 10h6v4h4v-4h5v4h4v-4h6v9H10z"/><path d="M13 19h19l-3 15H16z"/><path d="M11 34h23v5H11z"/><path d="M10 39h25v2H10z"/>',
    q: '<circle cx="10" cy="11" r="2.2"/><circle cx="18" cy="7.5" r="2.2"/><circle cx="27" cy="7.5" r="2.2"/><circle cx="35" cy="11" r="2.2"/><path d="M11 16l6 8 5.5-11 5.5 11 6-8-4 17H15z"/><path d="M14 33h17v3H14z"/><path d="M11 36h23v4H11z"/>',
    k: '<path d="M21 5h3v7h7v3h-7v5h-3v-5h-7v-3h7z"/><path d="M20 19c-6 0-8 4-8 8 0 3 3 6 5 8h11c2-2 5-5 5-8 0-4-2-8-8-8z"/><path d="M13 35h19v5H13z"/>',
  };
  const PIECE_NAMES = { p: 'Piyon', n: 'At', b: 'Fil', r: 'Kale', q: 'Vezir', k: 'Şah' };
  function pieceSvg(piece) {
    const color = piece === piece.toUpperCase() ? 'white' : 'black';
    return `<svg class="ch-piece ${color}" viewBox="0 0 45 45" aria-hidden="true" focusable="false"><g fill="var(--piece-fill)" stroke="var(--piece-stroke)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${PIECE_SHAPES[piece.toLowerCase()]}</g></svg>`;
  }
  const chess = (() => { const g = J(localStorage.getItem('jarvis_chess'), null);
    return { sans: g?.sans || [], userWhite: g?.userWhite ?? true, level: g?.level || 'orta', teach: !!g?.teach, sel: null, hint: null, coach: '' }; })();
  function chessBoard() { const b = new CH.Board(); for (const san of chess.sans) { const m = b.parse(san); if (!m) break; b.push(m); } return b; }
  const saveChess = () => localStorage.setItem('jarvis_chess', JSON.stringify({ sans: chess.sans, userWhite: chess.userWhite, level: chess.level, teach: chess.teach }));
  function chessState(b = chessBoard()) {
    const out = b.outcome(), pgn = chess.sans.map((m, i) => (i % 2 ? '' : (i / 2 + 1) + '. ') + m).join(' ');
    const userTurn = b.white === chess.userWhite;
    const status = out ? `Oyun bitti: ${out[0]} (${out[1]})` : (userTurn ? 'Sıra sende' : 'MAYK düşünüyor…') + (b.inCheck() ? ' — ŞAH!' : '');
    return { fen: b.fen(), moves: pgn || 'yok', status, user_color: chess.userWhite ? 'beyaz' : 'siyah', level: chess.level, teach: chess.teach };
  }
  function renderChess() {
    const b = chessBoard(), last = chess.sans.length ? (() => { const x = new CH.Board(); const L = chess.sans.slice(0, -1); for (const s of L) x.push(x.parse(s)); return x.parse(chess.sans[chess.sans.length - 1]); })() : null;
    const targets = chess.sel !== null ? b.legalMoves().filter(m => m[0] === chess.sel).map(m => m[1]) : [];
    let html = '';
    for (let r = 7; r >= 0; r--) for (let f = 0; f < 8; f++) {
      const rr = chess.userWhite ? r : 7 - r, ff = chess.userWhite ? f : 7 - f, s = rr * 8 + ff, p = b.sq[s];
      const cls = [((rr + ff) % 2) ? 'l' : 'd', p !== '.' ? (p === p.toUpperCase() ? 'w' : 'b') : '', chess.sel === s ? 'sel' : '',
        last && (last[0] === s || last[1] === s) ? 'last' : '', targets.includes(s) ? 'tgt' : '', chess.hint && (chess.hint[0] === s || chess.hint[1] === s) ? 'hint' : ''].join(' ');
      const label = p === '.' ? 'Boş kare' : (p === p.toUpperCase() ? 'Beyaz ' : 'Siyah ') + PIECE_NAMES[p.toLowerCase()];
      html += `<button type="button" class="ch-square ${cls}" data-s="${s}" aria-label="${label} ${CH.sqName(s)}" aria-pressed="${chess.sel === s}">${p !== '.' ? pieceSvg(p) : ''}</button>`;
    }
    $('ch-board').innerHTML = html;
    $('ch-status').textContent = chessState(b).status;
    $('ch-coach').hidden = !chess.coach; $('ch-coach').textContent = chess.coach;
    $('ch-teach').textContent = '🎓 Öğret: ' + (chess.teach ? 'açık' : 'kapalı');
    $('ch-level').value = chess.level; $('ch-color').value = chess.userWhite ? 'white' : 'black';
    $('ch-board').querySelectorAll('[data-s]').forEach(d => d.onclick = () => chessTap(+d.dataset.s));
  }
  // The coach: how good was the user's move compared with the best one?
  function coachMove(before, move) {
    const scores = CH.rootScores(before, 2), [bestScore, best] = scores[0];
    const mine = (scores.find(([, m]) => same3(m, move)) || [bestScore])[0];
    const loss = bestScore - mine;
    const verdict = same3(move, best) || loss < 35 ? 'çok iyi hamle' : loss < 90 ? 'fena değil' : loss < 250 ? 'hata' : 'büyük hata';
    return { yours: before.san(move), best: before.san(best), loss: Math.round(loss), verdict };
  }
  const same3 = (a, b) => a && b && a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
  function playUser(move, viaVoice = false) {
    const b = chessBoard();
    if (b.outcome()) return { ok: false, msg: 'Oyun bitti; yeni oyun başlat.' };
    if (b.white !== chess.userWhite) return { ok: false, msg: 'Sıra sende değil.' };
    const before = b.copy();
    const san = b.san(move); b.push(move); chess.sans.push(san); chess.sel = null; chess.hint = null; chess.coach = '';
    saveChess(); renderChess();                       // the user's piece moves at once
    const finish = () => {
      const coach = chess.teach ? coachMove(before, move) : null;
      chess.coach = coach ? (coach.verdict === 'çok iyi hamle' ? `✓ ${coach.yours}: çok iyi hamle.` : `${coach.yours}: ${coach.verdict}. Daha iyisi ${coach.best} idi.`) : '';
      let reply = '';
      if (!b.outcome()) { const [m] = CH.search(b, chess.level); if (m) { reply = b.san(m); b.push(m); chess.sans.push(reply); } }
      saveChess(); renderChess();
      const st = chessState(b);
      if (!viaVoice && amOwner() && ws && ready) {
        const teachNote = coach ? ` Öğretme modu açık: kullanıcının hamlesi "${coach.verdict}"${coach.best && coach.verdict !== 'çok iyi hamle' ? `, daha iyisi ${CH.spoken(coach.best)} idi (yaklaşık ${coach.loss} puan kayıp); nedenini bir iki cümleyle öğretici şekilde anlat` : ''}.` : '';
        tellBrain(`Satranç: kullanıcı ${CH.spoken(san)} oynadı, sen ${CH.spoken(reply) || '-'} oynadın. ${st.status}.${teachNote} Kısa konuş.`);
      }
      return { ok: true, san, reply, coach, st };
    };
    if (viaVoice) return finish();
    setTimeout(finish, 40);                          // let the screen draw before the engine thinks
    return { ok: true, san };
  }
  function chessTap(s) {
    const b = chessBoard();
    if (b.white !== chess.userWhite || b.outcome()) return;
    const mine = b.sq[s] !== '.' && (b.sq[s] === b.sq[s].toUpperCase()) === chess.userWhite;
    if (chess.sel === null || mine) { chess.sel = mine ? s : null; renderChess(); return; }
    const moves = b.legalMoves().filter(m => m[0] === chess.sel && m[1] === s);
    if (!moves.length) { chess.sel = null; renderChess(); return; }
    const m = moves.find(x => !x[2] || x[2] === 'q');
    playUser(m);
  }
  function chessHint() {
    const b = chessBoard();
    if (b.white !== chess.userWhite || b.outcome()) return 'Şu an ipucu yok.';
    const [m] = CH.search(b, 'zor'); if (!m) return 'Hamle yok.';
    chess.hint = m; renderChess();
    return `İpucu: ${CH.spoken(b.san(m))} (${b.san(m)}).`;
  }
  function chessNew(color, level) {
    chess.sans = []; chess.sel = null; chess.hint = null; chess.coach = '';
    if (color) chess.userWhite = !/^(b|s|black|siyah)/i.test(color);
    if (level && ['kolay', 'orta', 'zor'].includes(level)) chess.level = level;
    saveChess();
    let reply = '';
    if (!chess.userWhite) { const b = chessBoard(); const [m] = CH.search(b, chess.level); reply = b.san(m); chess.sans.push(reply); saveChess(); }
    renderChess(); return reply;
  }
  function chessTool(a) {
    const act = String(a.action || 'open').toLowerCase();
    if (act === 'open') { renderChess(); openSheet('s-chess'); return JSON.stringify(chessState()); }
    if (act === 'new') { const r = chessNew(a.color, a.level); openSheet('s-chess'); return JSON.stringify({ started: true, your_first_move: CH.spoken(r) || '-', ...chessState() }); }
    if (act === 'teach') { chess.teach = a.on !== false; saveChess(); renderChess(); openSheet('s-chess');
      return chess.teach ? 'Öğretme modu açık: her hamlesinden sonra iyi mi kötü mü olduğunu, daha iyisini ve nedenini anlat; açılış ilkelerini, taktikleri (çatal, şiş, açmaz) yeri geldikçe öğret.' : 'Öğretme modu kapandı.'; }
    if (act === 'hint') return chessHint();
    if (act === 'undo') { const b = chessBoard(); const n = b.white === chess.userWhite ? 2 : 1; chess.sans.splice(-n); chess.coach = ''; saveChess(); renderChess(); return 'Geri alındı. ' + JSON.stringify(chessState()); }
    if (act === 'resign') { chess.sans = []; saveChess(); renderChess(); return 'Kullanıcı pes etti; oyun sıfırlandı.'; }
    if (act === 'move') {
      const b = chessBoard(), m = b.parse(String(a.move || ''));
      if (!m) return JSON.stringify({ error: 'Bu hamle geçersiz ya da anlaşılmadı.', legal: b.legalMoves().slice(0, 40).map(x => b.san(x)).join(' '), ...chessState(b) });
      openSheet('s-chess');
      const r = playUser(m, true);
      if (!r.ok) return r.msg;
      return JSON.stringify({ user_move: CH.spoken(r.san), your_move: CH.spoken(r.reply) || '-', coach: r.coach || undefined, ...r.st });
    }
    return JSON.stringify(chessState());
  }
  $('t-chess').onclick = () => { renderChess(); openSheet('s-chess'); };
  $('ch-new').onclick = () => { chessNew($('ch-color').value, $('ch-level').value); };
  $('ch-level').onchange = () => { chess.level = $('ch-level').value; saveChess(); };
  $('ch-undo').onclick = () => toast(chessTool({ action: 'undo' }).split('.')[0] + '.');
  $('ch-hint').onclick = () => toast(chessHint());
  $('ch-teach').onclick = () => { chess.teach = !chess.teach; saveChess(); renderChess(); toast(chess.teach ? '🎓 Öğretme modu açık' : 'Öğretme modu kapandı'); };

  // ── projector / Android TV remote: the laptop drives it over ADB ────────
  // (core/adb_control.py); this page sends "adb:…" to the laptop's mailbox.
  // The MAYK Alıcı app on the projector (android-receiver/) works even when
  // the laptop is off; without it, the laptop drives the projector over ADB.
  const receiver = () => devices.filter(d => d.kind === 'receiver').sort((a, b) => online(b) - online(a) || Date.parse(b.seen || 0) - Date.parse(a.seen || 0))[0] || null;
  async function sendToReceiver(d, cmd) {
    const id = S.id + '-r' + Date.now().toString(36);
    const f = await Cloud.read();
    const box = J(f[`inbox-${d.id}.json`], []);
    box.push({ ...cmd, id, from: devName(), reply_to: S.id, ts: nowIso() });
    await Cloud.write({ [`inbox-${d.id}.json`]: JSON.stringify(box.slice(-10)) });
    for (let i = 0; i < 10; i++) {               // ~20 s
      await new Promise(r => setTimeout(r, 2000));
      try { const hit = J((await Cloud.read())[`outbox-${d.id}.json`], []).find(o => o.id === id); if (hit) return hit.reply; } catch {}
    }
    return `${d.controls || 'Projeksiyon'} komutu aldı ama yanıt vermedi (açık mı?).`;
  }
  async function remote(kind, arg, extra = {}) {
    if (!Cloud.ok()) return 'Ortak hafıza kurulu değil.';
    await syncNow();
    const rx = receiver();
    if (rx && online(rx)) return await sendToReceiver(rx, { op: kind, arg, ...extra });
    const pc = findPc('');
    if (pc && online(pc)) { const r = await sendToPc('', `adb:${kind}:${arg}`); return r.replace(/^[^:]+: /, ''); }
    return rx ? 'Projeksiyondaki MAYK Alıcı şu an çevrimdışı (projeksiyon kapalı ya da internete bağlı değil).'
              : 'Projeksiyonu kontrol edecek bir şey açık değil: projeksiyona MAYK Alıcı uygulamasını kur ya da laptopu aç.';
  }
  $('t-remote').onclick = () => { const pc = findPc(''); $('rm-note').textContent = pc ? `${pc.name} üzerinden kumanda (${online(pc) ? 'açık' : 'kapalı görünüyor'}). İlk kez: laptoptaki MAYK'a "projeksiyonu kur" de.` : 'Bağlı bilgisayar yok: kumanda laptoptaki MAYK üzerinden çalışır.'; openSheet('s-remote'); };
  document.querySelectorAll('#s-remote [data-k]').forEach(b => b.onclick = async () => { if (navigator.vibrate) navigator.vibrate(15); toast(await remote('key', b.dataset.k)); });
  document.querySelectorAll('#s-remote [data-app]').forEach(b => b.onclick = async () => toast(await remote('app', b.dataset.app)));
  $('rm-ask').addEventListener('submit', async (e) => { e.preventDefault(); const t = $('rm-inp').value.trim(); if (!t) return; $('rm-inp').value = ''; toast(await remote('search', t)); });
  $('rm-type').onclick = async () => { const t = $('rm-inp').value.trim(); if (!t) { toast('Önce yazacağını kutuya yaz.'); return; } $('rm-inp').value = ''; toast(await remote('type', t)); };
  $('rm-look').onclick = async () => { closeSheets(); claimHere(); try { await connect(); } catch {} toast(await remote('look', '', { question: '' })); setTimeout(() => syncNow(), 3000); };

  // ── coffee-cup reading (for fun): photos of the cup → Gemini looks ───────
  let falImages = [];
  $('fal-in').addEventListener('change', async (e) => {
    const files = [...(e.target.files || [])].slice(0, 3);
    falImages = [];
    for (const f of files) {
      const img = await createImageBitmap(f).catch(() => null); if (!img) continue;
      const c = document.createElement('canvas'), sc = Math.min(1, 1024 / Math.max(img.width, img.height));
      c.width = Math.round(img.width * sc); c.height = Math.round(img.height * sc); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      falImages.push(c.toDataURL('image/jpeg', 0.8).split(',')[1]);
    }
    $('fal-thumbs').innerHTML = falImages.map(d => `<img src="data:image/jpeg;base64,${d}" alt="">`).join('');
    $('fal-go').disabled = !falImages.length;
  });
  async function readFortune(question = '') {
    if (!falImages.length) return 'Önce fincanın fotoğrafını çekmen lazım: Fal ekranında "Fotoğraf çek".';
    if (!S.key) return 'Gemini anahtarı yok.';
    $('fal-out').textContent = '☕ Fincana bakıyorum…';
    const prompt = 'Sen sıcakkanlı, esprili ve deneyimli bir Türk kahve falcısısın. Fotoğraflardaki fincanın (ve varsa tabağın) telve şekillerine gerçekten bak: ' +
      'gördüğün şekilleri (kuş, yol, balık, kalp, dağ, harf, insan figürü …) ve fincanın neresinde olduklarını söyle ve geleneksel anlamlarıyla yorumla: aşk, kısmet, para, iş, yol, haber, sağlık değil ruh hâli. ' +
      'Akıcı, samimi bir dille 8-12 cümle yaz; sonunda bir dilek tut kısmı olsun. Korkutucu ya da kesin kehanet yok; olumsuz şeyleri yumuşak söyle. Son satıra "(Eğlence içindir.)" yaz.' +
      (question ? ` Kullanıcının sorusu: ${question}` : '') + ' Fotoğrafta fincan yoksa nazikçe söyle.';
    const parts = [...falImages.map(d => ({ inlineData: { mimeType: 'image/jpeg', data: d } })), { text: prompt }];
    for (const model of TEXT_MODELS) {
      try {
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, { method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-goog-api-key': S.key }, body: JSON.stringify({ contents: [{ role: 'user', parts }], generationConfig: { temperature: 0.9 } }) });
        if (!r.ok) continue;
        const js = await r.json();
        const txt = (js.candidates?.[0]?.content?.parts || []).filter(p => p.text && !p.thought).map(p => p.text).join('').trim();
        if (txt) { $('fal-out').textContent = txt; return txt; }
      } catch {}
    }
    $('fal-out').textContent = 'Fala bakılamadı; biraz sonra tekrar dene.'; return 'Fala bakılamadı.';
  }
  $('t-fal').onclick = () => openSheet('s-fal');
  $('fal-go').onclick = async () => { claimHere(); const txt = await readFortune();
    if (txt.length > 40 && amOwner()) { try { await connect(); } catch { return; } tellBrain(`Kullanıcının kahve falı hazır ve ekranda. Bunu sıcak, akıcı bir falcı gibi sesli oku (aynen ama doğal): ${txt}`); } };

  // ── shared to-do list: kept in shared memory (notes/"yapılacak: …"), so the
  // computer and every device see the same list ─────────────────────────────
  const TODO = 'yapılacak: ';
  function todoTool(a) {
    const act = String(a.action || 'list').toLowerCase(), item = String(a.item || '').trim();
    memory.notes = memory.notes || {};
    const items = Object.entries(memory.notes).filter(([k]) => k.startsWith(TODO));
    const persist = () => { localStorage.setItem('jarvis_mem', JSON.stringify(memory)); syncNow(); };
    const drop = (k) => { delete memory.notes[k]; memory._deleted = memory._deleted || {}; memory._deleted['notes/' + k] = nowIso(); };
    if (act === 'add') {
      if (!item) return 'Neyi ekleyeyim?';
      memory.notes[TODO + item.slice(0, 120)] = { value: 'açık', updated: nowIso() }; persist();
      return `Listeye eklendi: ${item}`;
    }
    if (act === 'done') {
      const q = item.toLocaleLowerCase('tr');
      const matches = items.filter(([k]) => q && k.slice(TODO.length).toLocaleLowerCase('tr').includes(q));
      const exact = matches.filter(([k]) => k.slice(TODO.length).toLocaleLowerCase('tr') === q);
      const candidates = exact.length ? exact : matches;
      if (candidates.length > 1) return 'Hangi maddeyi tamamladın? ' + candidates.map(([k]) => k.slice(TODO.length)).join(', ');
      const hit = candidates[0];
      if (!hit) return 'Listede böyle bir şey bulamadım.';
      drop(hit[0]); persist();
      if (Cloud.ok()) Cloud.write({ 'memory.json': JSON.stringify(memory) }).catch(() => {});
      return `Tamamlandı ve listeden çıktı: ${hit[0].slice(TODO.length)}`;
    }
    if (act === 'clear_done') return 'Tamamlanan maddeler zaten listeden çıkarılıyor. Açık görevlerin korunuyor.';
    if (act === 'clear') {
      const n = items.length; items.forEach(([k]) => drop(k)); persist();
      if (Cloud.ok()) Cloud.write({ 'memory.json': JSON.stringify(memory) }).catch(() => {});
      return `${n} madde silindi.`;
    }
    return items.length ? items.map(([k], i) => `${i + 1}. ${k.slice(TODO.length)}`).join('\n') : 'Yapılacaklar listesi boş.';
  }

  async function statusReport() {
    await syncNow();
    const me = { id: S.id, name: devName() + ' (bu cihaz)', kind: KIND, seen: new Date().toISOString(), ...battery };
    const devs = [me, ...devices.filter(d => d.id !== S.id)].map(d =>
      `- ${d.name} (${d.kind === 'pc' ? 'bilgisayar' : KIND_NAMES[d.kind] || d.kind}): ${online(d) ? 'açık' : 'kapalı'}${healthText(d) ? ', ' + healthText(d) : ''}`);
    const rem = pendingRem().slice(0, 4).map(r => `- ${remTime(r.due)}: ${r.text}`);
    const todos = Object.keys(memory.notes || {}).filter(k => k.startsWith('yapılacak: ')).map(k => '- ' + k.slice(11));
    const proj = projectsText();
    return `CİHAZLAR:\n${devs.join('\n')}\n\nSIRADAKİ HATIRLATICILAR:\n${rem.join('\n') || '- yok'}\n\nYAPILACAKLAR (${todos.length}):\n${todos.slice(0, 6).join('\n') || '- yok'}` +
      `\n\nPROJELER:\n${proj || '- yok'}\n\n(Kullanıcıya kısa, akıcı bir rapor olarak özetle; düşük pil ya da dolu disk varsa uyar.)`;
  }

  // ── reminders and timers, shared by every device ────────────────────────
  // Kept in reminders.json in the shared gist (desktop: core/sync_hub.py
  // merge_reminders), so one set on the phone is known to the computer and the
  // other way round. Every device marks it due on its own; only the device that
  // has the voice says it out loud.
  let reminders = J(localStorage.getItem('jarvis_rem'), []);
  let remFired = J(localStorage.getItem('jarvis_rem_fired'), []);
  const saveRem = () => { localStorage.setItem('jarvis_rem', JSON.stringify(reminders)); localStorage.setItem('jarvis_rem_fired', JSON.stringify(remFired.slice(-200))); };
  const REM_KEEP = 24 * 3600e3;
  function mergeReminders(a, b, now = Date.now()) {
    const by = new Map();
    for (const r of [...(a || []), ...(b || [])]) {
      if (!r || !r.id || !(+r.due)) continue;
      const old = by.get(r.id);
      by.set(r.id, old ? { ...old, ...r, cancelled: old.cancelled || r.cancelled || '' } : { ...r, cancelled: r.cancelled || '' });
    }
    // daily: the next day is added with an id that names the day, so every
    // device adds the same entry (core/sync_hub.merge_reminders does the same)
    const DAY = 86400000;
    for (const r of [...by.values()]) {
      if (r.repeat !== 'daily' || r.cancelled || +r.due > now) continue;
      const nxt = +r.due + DAY * Math.max(1, Math.floor((now - r.due) / DAY) + 1);
      const nid = `${String(r.id).split('@')[0]}@${nxt}`;
      if (!by.has(nid)) by.set(nid, { ...r, id: nid, due: nxt, cancelled: '' });
    }
    return [...by.values()].filter(r => +r.due > now - REM_KEEP).sort((x, y) => x.due - y.due);
  }
  const pendingRem = () => reminders.filter(r => !r.cancelled && !remFired.includes(r.id) && r.due > Date.now() - 60000);
  function parseWhen(a) {
    const min = Number(a.minutes);
    if (min > 0) return Date.now() + min * 60000;
    const at = String(a.at || '').trim();
    let m = /^(\d{4}-\d{2}-\d{2})[ T](\d{1,2})[:.](\d{2})$/.exec(at);
    if (m) { const t = new Date(`${m[1]}T${m[2].padStart(2, '0')}:${m[3]}:00`).getTime(); return isNaN(t) ? 0 : t; }
    m = /^(\d{1,2})[:.](\d{2})$/.exec(at);
    if (m) { const d = new Date(); d.setHours(+m[1], +m[2], 0, 0); if (d.getTime() <= Date.now()) d.setDate(d.getDate() + 1); return d.getTime(); }
    return 0;
  }
  const remTime = t => new Date(t).toLocaleString('tr-TR', { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  function reminderTool(a) {
    const act = String(a.action || 'set').toLowerCase();
    const open = pendingRem();
    if (act === 'list') return open.length ? open.map((r, i) => `${i + 1}. ${remTime(r.due)}${r.repeat ? ' (her gün)' : ''} — ${r.text}${r.from ? ` (${r.from})` : ''}`).join('\n') : 'Kurulu hatırlatıcı yok.';
    if (act === 'cancel') {
      const k = String(a.id || a.text || '').toLocaleLowerCase('tr').trim();
      const all = !k || k === 'hepsi' || k === 'all';
      const hit = open.filter((r, i) => all || String(i + 1) === k || r.text.toLocaleLowerCase('tr').includes(k));
      const bases = new Set(hit.map(r => String(r.id).split('@')[0]));     // a daily one: the whole series
      reminders.forEach(r => { if (bases.has(String(r.id).split('@')[0]) && !r.cancelled) r.cancelled = nowIso(); });
      saveRem(); renderRem(); if (hit.length) syncNow();
      return hit.length ? `${hit.length} hatırlatıcı iptal edildi (bütün cihazlarda).` : 'Böyle bir hatırlatıcı bulamadım.';
    }
    const due = parseWhen(a);
    if (!due) return 'Ne zaman? Dakika ya da saat söylemen lazım.';
    const protocol = String(a.protocol || '').trim(), repeat = /daily|her ?gün|günlük/i.test(String(a.repeat || '')) ? 'daily' : '';
    const text = String(a.text || (protocol ? `${protocol} protokolü` : 'Zamanlayıcı')).slice(0, 200);
    reminders.push({ id: S.id + '-' + Date.now().toString(36), text, due, from: devName(), cancelled: '', ...(repeat ? { repeat } : {}), ...(protocol ? { protocol } : {}), ...(a.op ? { op: String(a.op) } : {}) });
    reminders.sort((x, y) => x.due - y.due); saveRem(); renderRem(); syncNow();
    try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch {}
    if (repeat) { syncNow(); }
    return `Tamam: ${remTime(due)}${repeat ? ' ve her gün bu saatte' : ''} — ${protocol ? '"' + protocol + '" protokolü çalışacak' : text}.` + (Cloud.ok() ? ' Bütün cihazlar biliyor; o an hangisi açıksa o söyler.' : ' (Bu sayfa açık kaldıkça bu cihaz çalar.)');
  }
  function beep() {
    try { ensureOut(); const t0 = outCtx.currentTime;
      for (let i = 0; i < 3; i++) { const o = outCtx.createOscillator(), g = outCtx.createGain(); o.frequency.value = 880; o.connect(g); g.connect(outCtx.destination);
        g.gain.setValueAtTime(0.0001, t0 + i * 0.35); g.gain.exponentialRampToValueAtTime(0.3, t0 + i * 0.35 + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.35 + 0.25);
        o.start(t0 + i * 0.35); o.stop(t0 + i * 0.35 + 0.3); } } catch {}
  }
  function renderRem() {
    const b = $('t-rem'); if (!b) return;
    const open = pendingRem();
    b.hidden = !open.length; b.textContent = open.length ? `⏰ ${open.length}` : '⏰';
    b.title = open.map(r => `${remTime(r.due)} — ${r.text}`).join('\n');
    renderHud();
  }
  setInterval(() => {
    const now = Date.now(), due = reminders.filter(r => r.due <= now && !r.cancelled && !remFired.includes(r.id));
    if (!due.length) return;
    remFired.push(...due.map(r => r.id)); saveRem(); renderRem();
    for (const r of due) {
      if (now - r.due > 2 * 3600e3) continue;      // long past (this device was off): don't ring now
      if (emit('reminder', r)) continue;           // a device module did it (e.g. projector sleep timer)
      const late = now - r.due > 10 * 60000 ? ' (geç kaldı, sayfa kapalıydı)' : '';
      toast('⏰ ' + r.text + late);
      if (amOwner()) { beep(); if (navigator.vibrate) navigator.vibrate([300, 150, 300]); }
      try { if ('Notification' in window && Notification.permission === 'granted') new Notification('MAYK hatırlatıyor', { body: r.text, icon: 'icon-192.png' }); } catch {}
      sys('⏰ Hatırlatma: ' + r.text + late);
      if (amOwner()) {
        const note = r.protocol ? `Zamanlanmış protokol zamanı: "${r.protocol}". Şimdi protocol aracıyla çalıştır.` : `Hatırlatma zamanı: ${r.text}.`;
        if (ws && ready) tellBrain(note);
        else connect().then(() => tellBrain(note)).catch(() => {});
      }
    }
  }, 5000);

  // ── keep the screen awake while MAYK is listening or on a big screen ──
  let wakeLock = null;
  async function keepAwake() {
    const want = micOn || !!guard || KIND === 'tv' || KIND === 'projector';
    try {
      if (want && !wakeLock && document.visibilityState === 'visible' && navigator.wakeLock) {
        wakeLock = await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release', () => { wakeLock = null; });
      } else if (!want && wakeLock) { await wakeLock.release(); wakeLock = null; }
    } catch { wakeLock = null; }
  }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') keepAwake(); });

  // ── network: say so when it drops, pick up again when it is back ────────
  window.addEventListener('offline', () => { setState('offline'); toast('İnternet bağlantısı koptu'); });
  // typed while offline: sent, in order, as soon as the brain is reachable
  const offlineQueue = [];
  async function flushOffline() {
    if (!offlineQueue.length) return;
    try { await connect(); } catch { return; }
    const t = offlineQueue.splice(0).join('\n');
    setState('thinking'); send({ realtimeInput: { text: t } });
  }
  window.addEventListener('online', () => { toast('İnternet geri geldi'); if (wantLive || micOn || offlineQueue.length) connect().then(flushOffline).catch(() => {}); else setState('idle'); });

  // ── the brain: Gemini Live ───────────────────────────────────────────────
  let ws = null, ready = false, wantLive = false, variant = +(localStorage.getItem('jarvis_variant') || 0), connecting = null;
  // Gemini closes a live session every ~10 minutes and on network blips. With the
  // resumption handle the next session carries on the same conversation instead
  // of starting from nothing (the desktop does the same in main.py).
  const RESUME_MS = 2 * 3600e3;
  let resume = J(sessionStorage.getItem('jarvis_resume'), null);
  const resumeHandle = () => (resume && Date.now() - resume.t < RESUME_MS ? resume.h : '');
  function setResume(h) { resume = h ? { h, t: Date.now() } : null; try { h ? sessionStorage.setItem('jarvis_resume', JSON.stringify(resume)) : sessionStorage.removeItem('jarvis_resume'); } catch {} }
  function systemText() {
    const r = recent.slice(-16).map(t => `[${t.device}] ${t.role === 'user' ? 'Kullanıcı' : 'MAYK'}: ${t.text}`).join('\n');
    const pcs = devices.filter(d => d.kind === 'pc').map(d => `${d.name} (${online(d) ? 'açık' : 'kapalı'})`).join(', ') || 'yok';
    return `Adın ${S.name || 'MAYK'}. Kullanıcının kişisel asistanısın. Şu an "${devName()}" adlı ${KIND_NAMES[KIND].toLowerCase()} üzerinde çalışıyorsun; ` +
      `aynı sen bilgisayarda, laptopta, telefonda, tablette, TV'de ve saatte de varsın ve hepsi aynı hafızayı paylaşır. ` +
      `Türkçe (tr-TR) varsayılan komut ve yanıt dilindir. Türkçe sesli ve yazılı istekleri, günlük söyleyişleri ve ekleri anlayıp mevcut araçlara yönlendir. ` +
      `Örneğin 'uygulamayı aç', 'şunu araştır', 'dosyayı bul', 'hatırlatıcı kur', 'telefona gönder', 'projeksiyonu aç' ve 'testleri çalıştır' uygun aracı çağırmalıdır. ` +
      `Dahili araç adlarını ve parametre enum değerlerini değiştirme; işlem sonucunu, hata ve onayları Türkçe bildir. Kullanıcı açıkça başka bir dil seçerse onu kullan. ` +
      `Güncel bilgi için Google aramasını kullan. Kod istenince kodu show_code ile ekranda göster, sesli okuma. ` +
      `Yalnızca bir bilgisayarın yapabileceği işleri (uygulama/dosya açmak, projede çalışmak, bilgisayar ekranını görmek) computer_command ile bilgisayara gönder. ` +
      `Kullanıcı hakkında kalıcı bir şey öğrenince remember ile kaydet. ` +
      `RESİM ÇİZEBİLİRSİN: çizim, resim, görsel, logo istenince hemen make_image aracını çağır (resmi değiştirmek için mode='edit'); "resim yapamam" asla deme. ` +
      `Hava durumu için weather, döviz için currency kullan (gerçek veri). Bu cihazda uygulama açmak için open_app, hatırlatıcı ve zamanlayıcı için reminder, yapılacaklar listesi için todo, başka bir cihazda açmak/göstermek için send_to_device, "… protokolü / … modu" denince protocol, satranç için chess (öğret denirse teach), kahve falı için coffee_fortune, projeksiyon/TV kontrolü için projector kullan. `+
      `Kullanıcı bir şeyi sorduğunda önce search_memory ile ortak hafızaya bak; geçmiş bir konuşma sorulursa search_history ile arşive bak. ` +
      `"(Sistem notu" ile başlayan mesajlar kullanıcıdan değil, arka planda biten işlerden gelir. ` +
      `Düşüncelerini sesli söyleme; sadece kullanıcıya cevabı söyle. ` +
      `Önceki konuşmalar ve yarım işler aşağıda; "kaldığımız yerden devam" denirse oradan sür, bilgisayardaki yarım projeler için computer_command ile "yarım kalan işe devam et" gönder.\n\n` +
      `Bugün: ${new Date().toLocaleString('tr-TR', { dateStyle: 'full', timeStyle: 'short' })}.\nBilgisayarlar: ${pcs}.\n\n` +
      `BİLGİSAYARDAKİ PROJELER:\n${projectsText() || '(yok)'}\n\nORTAK HAFIZA:\n${memoryText()}\n\nSON KONUŞMALAR (tüm cihazlar):\n${r || '(yok)'}` + extraPrompt.map(f => { try { return '\n\n' + f(); } catch { return ''; } }).join('');
  }
  function setupMsg(v) {
    const model = LIVE_MODELS[v >= 2 ? 1 : 0];
    const voice = { voiceConfig: { prebuiltVoiceConfig: { voiceName: S.voice || 'Charon' } } };
    const setup = { model, systemInstruction: { parts: [{ text: systemText() }] },
                    tools: [{ functionDeclarations: TOOLS }, { googleSearch: {} }],
                    inputAudioTranscription: {}, outputAudioTranscription: {} };
    if (v % 2 === 0) { setup.generationConfig = { responseModalities: ['AUDIO'], speechConfig: voice }; setup.contextWindowCompression = { slidingWindow: {} };
                       setup.sessionResumption = resumeHandle() && v === variant ? { handle: resumeHandle() } : {}; }
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
        const usedHandle = v % 2 === 0 && v === variant && !!resumeHandle();
        sock.onclose = (e) => {
          if (!opened) {
            if (usedHandle) { setResume(''); attempt(); return; }     // stale handle: start fresh, same variant
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

  let outOpen = false, hadAudio = false, pendingText = '';
  async function onServer(m) {
    if (m.serverContent) {
      const sc = m.serverContent;
      if (sc.interrupted) { stopPlayback(); }
      if (sc.inputTranscription?.text) { lastInteract = Date.now(); addTurn('user', sc.inputTranscription.text); setState('thinking'); }
      if (sc.outputTranscription?.text) { if (!outOpen) { closeTurnsOf('user'); outOpen = true; } addTurn('jarvis', sc.outputTranscription.text); }
      for (const p of sc.modelTurn?.parts || []) {
        if (p.thought) continue;          // the model's own reasoning: never shown, never spoken
        if (p.inlineData?.data && /audio/.test(p.inlineData.mimeType || 'audio')) playPcm(p.inlineData.data);
        // With voice answers the words come from outputTranscription; model text parts
        // there are only notes to itself, so they are shown only in a text-only answer.
        else if (p.text && !sc.outputTranscription && !hadAudio) { pendingText += p.text; }
      }
      if (sc.modelTurn?.parts?.some(p => p.inlineData?.data && !p.thought)) hadAudio = true;
      if (sc.turnComplete) {
        if (pendingText && !hadAudio && !transcript.some(t => t.open && t.role === 'jarvis')) addTurn('jarvis', pendingText);
        pendingText = ''; hadAudio = false;
        outOpen = false; closeTurns(); syncSoon(); emit('turn'); if (!playing()) setState(micOn ? 'listening' : 'idle'); }
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
    if (m.sessionResumptionUpdate) {
      const u = m.sessionResumptionUpdate;
      if (u.newHandle && u.resumable !== false) setResume(u.newHandle);
    }
    if (m.goAway) { /* the server will close soon; onclose reconnects and resumes */ }
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
    micOn = true; $('mic').classList.add('live'); $('mic').textContent = '⏹'; beatDirty = true; keepAwake();
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
    keepAwake();
    if (state === 'listening') setState('idle');
  }
  $('mic').onclick = () => { if (micOn) { resumeMic = false; stopMic(); } else { claimHere(); startMic(); } };

  // ── text in ──────────────────────────────────────────────────────────────
  $('ask').addEventListener('submit', async (e) => {
    e.preventDefault();
    const t = $('inp').value.trim(); if (!t) return;
    $('inp').value = ''; ensureOut(); claimHere();
    closeTurns(); transcript.push({ role: 'user', text: t, open: false }); queueRecent('user', t); renderLog();
    if (!navigator.onLine) { offlineQueue.push(t); toast('İnternet yok; bağlantı gelince göndereceğim.'); return; }
    try { await connect(); } catch { offlineQueue.push(t); return; }
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
    // iPhone home-screen MAYK starting empty: say why and offer the paste
    $('f-ios').hidden = !(isIOS && standalone && !S.key);
    $('f-move').hidden = !(isIOS && !standalone && S.key);
    $('f-key').value = S.key || ''; $('f-tok').value = S.tok || ''; $('f-gist').value = S.gist || '';
    $('f-dev').value = S.devName || ''; $('f-city').value = S.city || ''; $('f-kind').value = S.kind || 'auto'; $('f-voice').value = S.voice || 'Charon';
    $('f-status').textContent = ''; openSheet('s-setup');
  }
  $('b-set').onclick = openSetup; $('b-menu').onclick = () => { renderDevices(); openSheet('s-devs'); syncNow(); };
  $('b-chat').onclick = () => openSheet('s-chat');
  $('f-close').onclick = closeSheets;
  async function pasteSetup() {
    let text = '';
    try { text = await navigator.clipboard.readText(); } catch {}
    if (!importSetup(text)) text = prompt('Kurulum bağlantısını buraya yapıştır:') || '';
    if (!importSetup(text)) { $('f-status').textContent = 'Bu bir MAYK kurulum bağlantısı değil.'; return; }
    $('f-status').textContent = 'Kurulum geldi, hafıza yükleniyor…';
    openSetup(); lastBeat = 0; await syncNow(); setState(S.key ? 'idle' : 'setup');
    $('f-status').textContent = 'Tamam — hafızan ve ayarların bu uygulamada.'; setTimeout(closeSheets, 1200);
  }
  $('f-paste').onclick = pasteSetup; $('f-paste2').onclick = pasteSetup;
  $('f-copy').onclick = async () => {
    try { await navigator.clipboard.writeText(setupLink()); $('f-status').textContent = 'Kopyalandı. Şimdi Paylaş ⬆︎ → "Ana Ekrana Ekle"; ana ekrandaki MAYK\'ı açınca "Yapıştır"a bas.'; }
    catch { prompt('Bu bağlantıyı kopyala:', setupLink()); }
  };
  $('f-save').onclick = async () => {
    S.key = $('f-key').value.trim(); S.tok = $('f-tok').value.trim(); S.gist = $('f-gist').value.trim();
    S.devName = $('f-dev').value.trim(); S.city = $('f-city').value.trim(); S.kind = $('f-kind').value; S.voice = $('f-voice').value; save(); applyKind();
    if (S.tok && !S.gist) {
      $('f-status').textContent = 'Ortak hafıza açılıyor…';
      try { S.gist = await Cloud.create(); save(); $('f-gist').value = S.gist; } catch (e) { $('f-status').textContent = 'GitHub: ' + e.message + ' (anahtarın gist izni var mı?)'; return; }
    }
    $('f-status').textContent = 'Kaydedildi.'; lastBeat = 0; await syncNow();
    if (ws) { try { ws.close(); } catch {} }
    setState(S.key ? 'idle' : 'setup'); setTimeout(closeSheets, 600);
  };
  $('f-link').onclick = async () => {
    const link = setupLink();
    try { if (navigator.share) await navigator.share({ title: 'MAYK kurulumu', url: link }); else { await navigator.clipboard.writeText(link); toast('Bağlantı kopyalandı — kendi cihazına gönder'); } }
    catch { try { await navigator.clipboard.writeText(link); toast('Bağlantı kopyalandı'); } catch { prompt('Bağlantı:', link); } }
  };

  // keyboard / TV remote: Enter or the OK key on the mic
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === ' ' || e.key === 'MediaPlayPause') { e.preventDefault(); $('mic').click(); }
  });

  // ── updates: this device, or every device at once ───────────────────────
  let loadedVer = null, latestVer = null;
  async function fetchVersion() {
    try { const r = await fetch('version.json?t=' + Date.now(), { cache: 'no-store' }); if (r.ok) return (await r.json()).version || ''; } catch {}
    return null;
  }
  async function checkVersion() {
    const v = await fetchVersion();
    if (v === null) return;
    if (loadedVer === null) loadedVer = v;
    latestVer = v;
    const fresh = loadedVer !== latestVer;
    $('t-update').classList.toggle('new', fresh);
    $('t-update').textContent = fresh ? '⬆ Yeni sürüm' : '⬆ Güncelle';
    $('upd-text').textContent = fresh ? `Yeni sürüm hazır (${latestVer.slice(0, 7)}). Bu cihaz ${loadedVer.slice(0, 7)} sürümünde.`
                                      : `Bu cihaz güncel (${(loadedVer || '?').slice(0, 7)}).`;
  }
  async function updateThis() {
    toast('Güncelleniyor…');
    try { if (window.caches) for (const k of await caches.keys()) await caches.delete(k); } catch {}
    try { if (navigator.serviceWorker) for (const r of await navigator.serviceWorker.getRegistrations()) await r.update(); } catch {}
    setTimeout(() => location.reload(), 400);
  }
  async function updateAll() {
    if (!Cloud.ok()) { toast('Ortak hafıza kurulu değil; sadece bu cihaz güncellenir'); return updateThis(); }
    try {
      S.updSeen = new Date().toISOString(); save();
      await Cloud.write({ 'update.json': JSON.stringify({ ts: nowIso(), by: devName() }) });
      toast('Bütün cihazlara güncelleme gönderildi');
    } catch { toast('Gönderilemedi'); return; }
    setTimeout(updateThis, 1200);
  }
  function watchUpdateFile(f) {             // called after every sync
    const u = J(f && f['update.json'], {});
    if (!u.ts) return;
    if (!S.updSeen) { S.updSeen = u.ts; save(); return; }  // first look: remember, don't act
    if (u.ts > S.updSeen) { S.updSeen = u.ts; save(); sys(`${u.by || 'Bir cihaz'} bütün cihazları güncelledi.`); updateThis(); }
  }
  $('t-update').onclick = () => { openSheet('s-update'); checkVersion(); };
  $('upd-this').onclick = updateThis;
  $('upd-all').onclick = updateAll;
  setInterval(checkVersion, 5 * 60000);
  renderRem(); keepAwake();
  refreshHudWeather(); setInterval(refreshHudWeather, 30 * 60000);
  // ── agenda: reminders, to-dos and saved places in one place, every device ──
  function renderAgenda() {
    const row = (txt, sub, btn, act) => `<div class="row2"><span>${esc(txt)}${sub ? `<br><small>${esc(sub)}</small>` : ''}</span>${btn ? `<button class="x" type="button" data-act="${esc(act)}">${btn}</button>` : ''}</div>`;
    const rem = pendingRem().map((r, i) => row(r.text, remTime(r.due) + (r.repeat ? ' · her gün' : '') + (r.from ? ' · ' + r.from : ''), 'İptal', 'rem:' + (i + 1)));
    const todos = Object.keys(memory.notes || {}).filter(k => k.startsWith('yapılacak: ')).map(k => row(k.slice(11), '', '✓', 'todo:' + k.slice(11)));
    const places = Object.entries(memory.notes || {}).filter(([k]) => k.startsWith('konum: ')).map(([k, v]) => row(k.slice(7), entry(v).value.split('|')[1]?.trim() || '', 'Harita', 'place:' + k.slice(7)));
    $('agenda-body').innerHTML = `<div class="ag"><h4>HATIRLATICILAR</h4>${rem.join('') || '<div class="row2"><small>Yok — "yarın 9\'da hatırlat" de.</small></div>'}` +
      `<h4>YAPILACAKLAR</h4>${todos.join('') || '<div class="row2"><small>Liste boş.</small></div>'}` + (places.length ? `<h4>KAYITLI YERLER</h4>${places.join('')}` : '') + '</div>';
    $('agenda-body').querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
      const [kind, ...rest] = b.dataset.act.split(':'), val = rest.join(':');
      if (kind === 'rem') toast(reminderTool({ action: 'cancel', id: val }));
      else if (kind === 'todo') toast(todoTool({ action: 'done', item: val }));
      else if (kind === 'place') toast(await placeTool({ action: 'find', name: val }));
      renderAgenda();
    });
  }
  $('t-agenda').onclick = async () => { renderAgenda(); openSheet('s-agenda'); await syncNow(); renderAgenda(); };
  $('agenda-add').addEventListener('submit', e => { e.preventDefault(); const t = $('agenda-inp').value.trim(); if (!t) return;
    $('agenda-inp').value = ''; toast(todoTool({ action: 'add', item: t })); renderAgenda(); });
  // ── notifications while this page is closed: the computer sends them
  // (core/webpush.py) with the keys in push.json; this device subscribes ──
  const b64uBytes = t => { const b = atob(String(t).replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((String(t).length + 3) % 4)); return Uint8Array.from(b, c => c.charCodeAt(0)); };
  async function enablePush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return /iPhone|iPad/.test(navigator.userAgent)
      ? 'iPhone\'da bildirim için önce Paylaş → "Ana Ekrana Ekle" ile MAYK\'ı ekle, sonra oradan açıp tekrar dene.' : 'Bu tarayıcı bildirim desteklemiyor.';
    if (!Cloud.ok()) return 'Önce ortak hafıza (GitHub anahtarı) kurulmalı.';
    const perm = await Notification.requestPermission();
    if (perm !== 'granted') return 'Bildirim izni verilmedi.';
    const f = await Cloud.read();
    const pub = J(f['push.json'], {}).publicKey;
    if (!pub) return 'Bildirim anahtarı henüz yok: bilgisayarda MAYK bir kez açılınca oluşur. Sonra tekrar dene.';
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (sub && J(localStorage.getItem('jarvis_push_key'), '') !== pub) { await sub.unsubscribe(); sub = null; }
    sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64uBytes(pub) });
    localStorage.setItem('jarvis_push_key', JSON.stringify(pub));
    await Cloud.write({ [`push-sub-${S.id}.json`]: JSON.stringify(sub.toJSON()) });
    return 'Bildirimler açık: sayfa kapalıyken de hatırlatıcılar, gönderilenler ve güvenlik uyarıları bildirim olarak gelecek (bilgisayardaki MAYK açıkken).';
  }
  $('f-alici').onclick = () => { window.open(ALICI_APK, '_blank'); $('f-status').textContent = 'İndirilen jarvis-alici.apk\'yı aç ve kur (bilinmeyen kaynaklara izin ver). Sonra "Alıcıyı bağla"ya bas.'; };
  $('f-alici-link').onclick = () => {
    const j = JSON.stringify({ g: '', t: S.tok || '', i: S.gist || '', n: S.name || '', d: devName() });
    const code = btoa(unescape(encodeURIComponent(j))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    if (!S.tok || !S.gist) { $('f-status').textContent = 'Önce ortak hafıza (GitHub anahtarı) kurulu olmalı.'; return; }
    const link = 'jarvisalici://setup?s=' + code;
    // Only Android devices with MAYK Alıcı installed can open this scheme.
    // iOS Safari/PWA otherwise displays an unhelpful "invalid address" error.
    if (/iPhone|iPad|iPod/i.test(navigator.userAgent)) {
      const note = 'Bu bağlantı iPhone\'da açılmaz. Projeksiyondaki MAYK Alıcı uygulamasının 2. adımına yapıştırmak için bağlantıyı güvenli biçimde projeksiyona aktar. Bağlantı özel GitHub anahtarını içerir; herkese açık paylaşma.';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => {
          $('f-status').textContent = 'Alıcı kurulum bağlantısı kopyalandı. ' + note;
        }).catch(() => {
          prompt(note + '\\nKurulum bağlantısı:', link);
        });
      } else {
        prompt(note + '\\nKurulum bağlantısı:', link);
      }
      return;
    }
    location.href = link;
  };
  $('f-push').onclick = async () => { $('f-status').textContent = 'Bildirimler açılıyor…'; try { $('f-status').textContent = await enablePush(); } catch (e) { $('f-status').textContent = 'Açılamadı: ' + (e.message || e); } };
  // ── the computer panel: buttons straight to the computer's MAYK ───────
  $('t-pc').onclick = () => {
    const pc = findPc(''); $('pc-note').textContent = pc ? `${pc.name} — ${online(pc) ? 'açık' : 'kapalı görünüyor'}${healthText(pc) ? ' · ' + healthText(pc) : ''}` : 'Bağlı bilgisayar yok: bilgisayarda "MAYK\'ı her cihaza kur" de.';
    openSheet('s-pc');
  };
  document.querySelectorAll('#s-pc [data-q]').forEach(b => b.onclick = async () => {
    b.disabled = true; toast('Gönderiliyor…');
    try { toast(await sendToPc('', 'quick:' + b.dataset.q)); } finally { b.disabled = false; }
  });
  $('pc-shot').onclick = async () => { closeSheets(); claimHere(); try { await connect(); } catch {} toast(await runTool('computer_screen', {})); };
  $('pc-status').onclick = async () => { closeSheets(); claimHere(); try { await connect(); } catch { return; } send({ realtimeInput: { text: 'Durum raporu ver.' } }); };
  $('pc-ask').addEventListener('submit', async (e) => {
    e.preventDefault(); const t = $('pc-inp').value.trim(); if (!t) return; $('pc-inp').value = '';
    toast('Bilgisayara gönderildi…'); const r = await sendToPc('', t); sys('💻 ' + r); toast(r.slice(0, 120));
  });
  // Shared from another app (Android "Paylaş → MAYK", manifest share_target):
  // MAYK asks what to do with it — open on the TV, send to the computer …
  (function sharedIn() {
    const q = new URLSearchParams(location.search);
    const parts = ['share_title', 'share_text', 'share_url'].map(k => (q.get(k) || '').trim()).filter(Boolean);
    if (!parts.length) return;
    history.replaceState(null, '', location.pathname);
    const shared = [...new Set(parts)].join(' — ').slice(0, 1500);
    closeTurns(); transcript.push({ role: 'user', text: '📎 ' + shared, open: false }); renderLog();
    claimHere();
    connect().then(() => { setState('thinking');
      send({ realtimeInput: { text: `(Sistem notu) Kullanıcı başka bir uygulamadan bunu MAYK'a paylaştı: ${shared}\n` +
        'Ne olduğunu tek cümleyle söyle ve ne yapmak istediğini sor: bir cihazda açmak (TV, bilgisayar…), özetlemek, kaydetmek, yapılacaklara eklemek gibi.' } }); })
      .catch(() => toast('Paylaşılan alındı; bağlanınca soracağım.'));
  })();
  $('t-rem').onclick = () => {
    const open = pendingRem(); if (!open.length) return;
    askUser('Hatırlatıcılar', open.map((r, i) => `${i + 1}. ${remTime(r.due)} — ${r.text}`).join('\n') + '\n\nHepsi iptal edilsin mi?',
      () => { toast(reminderTool({ action: 'cancel', id: 'hepsi' })); });
  };
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') checkVersion(); });
  checkVersion();

  // ── device modules: web/dev-*.js reach the app only through this object ──
  window.JARVIS = {
    get kind() { return KIND; }, S, save, $, esc, toast, sys, openSheet, closeSheets, askUser,
    on(ev, fn) { (hooks[ev] = hooks[ev] || []).push(fn); if (ev === 'weather' && hudWeather) fn(hudWeather); },
    tool(decl, fn) { if (!TOOLS.some(t => t.name === decl.name)) TOOLS.push(decl); extraTools[decl.name] = fn; },
    prompt(fn) { extraPrompt.push(fn); },
    ask(text) { $('inp').value = String(text); $('ask').requestSubmit(); },
    // the user said it: send to the brain without putting it in the input box
    async say(text) { claimHere(); closeTurns(); transcript.push({ role: 'user', text, open: false }); queueRecent('user', text); renderLog();
      try { await connect(); } catch { return false; } setState('thinking'); send({ realtimeInput: { text } }); return true; },
    async look(data, mime, question) { claimHere(); try { await connect(); } catch { return false; }
      send({ realtimeInput: { video: { data, mimeType: mime || 'image/jpeg' } } });
      tellBrain(`Kullanıcı ekrana bir resim bıraktı; ona bak ve ${question || 'ne gördüğünü kısaca söyle'}.`); setState('thinking'); return true; },
    get micOn() { return micOn; }, get micLevel() { return micLvl; }, get state() { return state; }, get speaking() { return playing(); },
    get lastInteract() { return lastInteract; }, touch() { lastInteract = Date.now(); },
    startMic() { if (!micOn) { claimHere(); return startMic(); } }, stopMic() { if (micOn) { resumeMic = false; stopMic(); } },
    hush() { stopPlayback(); if (state === 'speaking') setState(micOn ? 'listening' : 'idle'); },
    core, beep, ringHere, remote, sendToDevice, runTool, reminderTool, todoTool, pendingRem, remTime, online, findDevice, syncNow,
    get devices() { return devices.slice(); }, get memory() { return memory; }, get gallery() { return gallery.slice(); },
    get battery() { return { ...battery }; }, get weather() { return hudWeather; }, get owner() { return amOwner(); },
    get transcript() { return transcript.slice(); }, get receiver() { return receiver(); }, findPc, renderHud, refreshHudWeather,
  };

  // ── start ────────────────────────────────────────────────────────────────
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js' + new URL(document.currentScript.src).search).catch(() => {});
  window.addEventListener('online', () => setState(S.key ? 'idle' : 'setup'));
  window.addEventListener('offline', () => setState('offline'));
  setState(S.key ? 'idle' : 'setup');
  if (!S.key) setTimeout(openSetup, 400);
  renderDevices(); renderLog();
  if (Cloud.ok()) syncNow();
  if (KIND === 'tv' || KIND === 'projector') $('mic').focus();
})();
