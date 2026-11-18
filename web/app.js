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
  let pcProjects = J(localStorage.getItem('jarvis_projects'), []);
  function projectsText() {
    const L = [];
    for (const pc of pcProjects) for (const p of (pc.projects || [])) {
      const step = p.stages ? ` — aşama ${p.stage}/${p.stages}${p.current ? ' (' + p.current + ')' : ''}` : '';
      L.push(`[${pc.computer}] #${p.id} ${p.title}: ${p.status}${step}${p.note ? ' — ' + p.note.slice(0, 160) : ''} (${(p.updated || '').replace('T', ' ')})`);
    }
    return L.join('\n');
  }
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
      pcProjects = Object.entries(f).filter(([k]) => k.startsWith('projects-')).map(([, v]) => J(v, null)).filter(Boolean);
      try { localStorage.setItem('jarvis_projects', JSON.stringify(pcProjects)); } catch {}
      const myInbox = J(f[`inbox-${S.id}.json`], []);
      if (myInbox.length) { runInbox(myInbox); writes[`inbox-${S.id}.json`] = '[]'; }
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
  function renderHud() {
    if (!document.body.classList.contains('big')) return;
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
    $('hud').innerHTML = block('UYARI', warn, 'warn') + block('SIRADAKİLER', rem) + block('YAPILACAKLAR', todos) + block('PROJELER', proj.slice(0, 3));
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
    const others = list.filter(d => d.id !== S.id);
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
        if (c.kind === 'open' && /^https?:\/\//i.test(c.url || '')) {
          sys(`${from} bir bağlantı gönderdi: ${title || c.url}`);
          const w = window.open(c.url, '_blank');
          if (!w) askUser('Açılsın mı?', `${from}: ${title || c.url}`, () => window.open(c.url, '_blank'));
        } else if (c.kind === 'image' && (c.data || c.url)) {
          keepImage({ data: c.data || '', mime: c.mime || 'image/png', url: c.url || '', prompt: c.prompt || title, en: c.en || '', seed: c.seed || 0 });
          showImage(`${from} gönderdi${title ? ': ' + title : ''}`);
        } else if (c.kind === 'code' || c.kind === 'text') {
          lastCode = { filename: String(c.filename || title || (c.kind === 'code' ? 'kod.txt' : 'not.txt')), code: String(c.text || ''), note: `${from} gönderdi` };
          showCode(); $('t-code').hidden = false;
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
    if (!pc) return 'Bağlı bir bilgisayar yok. Bilgisayarda JARVIS açıkken "Jarvis\'i her cihaza kur" demen gerekiyor.';
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
    { name: 'projects', description: 'Bilgisayarda JARVIS\'in yaptığı/yarım kalan projelerin (site, uygulama, kod) güncel durumu: "projem ne durumda", "site bitti mi". Devam ettirmek için computer_command ile "yarım kalan işe devam et" gönder.',
      parameters: { type: 'OBJECT', properties: {} } },
    { name: 'protocol', description: 'Protokoller (Iron Man tarzı): tek komutla sırayla birçok iş. "çalışma protokolü", "film moduna geç", "uyku protokolü", "günaydın", "protokollerim neler", "yeni protokol kaydet". action: run | list | save | delete. run bir adım listesi döner: o adımları sırayla araçlarınla yap.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, name: { type: 'STRING' }, steps: { type: 'ARRAY', items: { type: 'STRING' } } }, required: ['action'] } },
    { name: 'status_report', description: 'Iron Man tarzı durum raporu: bütün cihazlar (açık/kapalı, pil, işlemci, bellek, disk), sıradaki hatırlatıcılar, yapılacaklar, bilgisayardaki projeler. "durum raporu", "sistemler nasıl", "cihazlarım ne durumda", "laptopun şarjı kaç".',
      parameters: { type: 'OBJECT', properties: {} } },
    { name: 'guard', description: 'Güvenlik modu: bu cihazın (ya da device verilirse o cihazın) kamerası odayı izler; hareket olursa fotoğraf çekip bütün cihazlara gönderir ve sesli haber verir. "odayı izle", "güvenlik modunu aç/kapat", "tableti kamera yap".',
      parameters: { type: 'OBJECT', properties: { on: { type: 'BOOLEAN' }, device: { type: 'STRING', description: 'boşsa bu cihaz' } }, required: ['on'] } },
    { name: 'todo', description: 'Ortak yapılacaklar listesi (tüm cihazlar ve bilgisayar aynı listeyi görür): "listeye süt ekle", "yapılacaklarım ne", "faturayı ödedim, sil". action: add | list | done | clear_done.',
      parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' }, item: { type: 'STRING' } }, required: ['action'] } },
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
        // JARVIS says so when the picture is on screen.
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
        askUser('Ekranı göster', 'JARVIS ekranını görmek istiyor.', () => startVideo('screen'));
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
    if (!lastImage.data) { try { await navigator.share({ url: lastImage.url, title: 'JARVIS' }); } catch { window.open(lastImage.url, '_blank'); } return; }
    const file = new File([imageBlob()], 'jarvis.png', { type: lastImage.mime });
    try { if (navigator.canShare?.({ files: [file] })) await navigator.share({ files: [file], title: 'JARVIS' }); else $('img-dl').click(); } catch {}
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
  const PROTOCOLS = {"sabah": ["Günaydın de; bugünün tarihini ve Google aramasıyla bulunduğun yerin hava durumunu kısaca söyle", "Bugünün hatırlatıcılarını ve yapılacaklar listesini oku", "Yarım kalan proje varsa durumunu tek cümleyle söyle"], "çalışma": ["Bilgisayarda çalan müziği durdur ve sesi yüzde 20'ye indir", "Yapılacaklar listesini oku ve hangisiyle başlamak istediğini sor", "45 dakika sonrasına 'mola ver' hatırlatıcısı kur"], "film": ["Televizyonda YouTube'u aç (send_to_device, open); ne izlemek istediğini sor", "Bilgisayarda çalan müziği durdur", "Film bitince haber vermek için süre isterse hatırlatıcı kur"], "uyku": ["Yarının hatırlatıcılarını ve yapılacakları kısaca söyle", "Sabah için hatırlatıcı/alarm isteyip istemediğini sor, isterse kur", "İyi geceler de ve bilgisayarı kilitle"]};
  const PROTO_ALIASES = {"günaydın": "sabah", "sabah": "sabah", "çalış": "çalışma", "iş": "çalışma", "odak": "çalışma", "film": "film", "sinema": "film", "dizi": "film", "uyku": "uyku", "gece": "uyku", "yat": "uyku"};
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
      const hit = items.find(([k]) => k.slice(TODO.length).toLocaleLowerCase('tr').includes(q));
      if (!q || !hit) return 'Listede böyle bir şey bulamadım.';
      drop(hit[0]); persist();
      if (Cloud.ok()) Cloud.write({ 'memory.json': JSON.stringify(memory) }).catch(() => {});
      return `Tamamlandı ve listeden çıktı: ${hit[0].slice(TODO.length)}`;
    }
    if (act === 'clear_done' || act === 'clear') {
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
      `\n\nPROJELER:\n${proj || '- yok'}\n\n(Kullanıcıya Iron Man'deki JARVIS gibi kısa, akıcı bir rapor olarak özetle; düşük pil ya da dolu disk varsa uyar.)`;
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
    reminders.push({ id: S.id + '-' + Date.now().toString(36), text, due, from: devName(), cancelled: '', ...(repeat ? { repeat } : {}), ...(protocol ? { protocol } : {}) });
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
      const late = now - r.due > 10 * 60000 ? ' (geç kaldı, sayfa kapalıydı)' : '';
      toast('⏰ ' + r.text + late);
      if (amOwner()) { beep(); if (navigator.vibrate) navigator.vibrate([300, 150, 300]); }
      try { if ('Notification' in window && Notification.permission === 'granted') new Notification('JARVIS hatırlatıyor', { body: r.text, icon: 'icon-192.png' }); } catch {}
      sys('⏰ Hatırlatma: ' + r.text + late);
      if (amOwner()) {
        const note = r.protocol ? `Zamanlanmış protokol zamanı: "${r.protocol}". Şimdi protocol aracıyla çalıştır.` : `Hatırlatma zamanı: ${r.text}.`;
        if (ws && ready) tellBrain(note);
        else connect().then(() => tellBrain(note)).catch(() => {});
      }
    }
  }, 5000);

  // ── keep the screen awake while JARVIS is listening or on a big screen ──
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
  window.addEventListener('online', () => { toast('İnternet geri geldi'); if (wantLive || micOn) connect().catch(() => {}); else setState('idle'); });

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
    const r = recent.slice(-16).map(t => `[${t.device}] ${t.role === 'user' ? 'Kullanıcı' : 'JARVIS'}: ${t.text}`).join('\n');
    const pcs = devices.filter(d => d.kind === 'pc').map(d => `${d.name} (${online(d) ? 'açık' : 'kapalı'})`).join(', ') || 'yok';
    return `Sen ${S.name || 'JARVIS'}sın: kullanıcının kişisel asistanı. Şu an "${devName()}" adlı ${KIND_NAMES[KIND].toLowerCase()} üzerinde çalışıyorsun; ` +
      `aynı sen bilgisayarda, laptopta, telefonda, tablette, TV'de ve saatte de varsın ve hepsi aynı hafızayı paylaşır. ` +
      `Kısa, doğal ve sıcak konuş; kullanıcının dilinde yanıt ver (çoğunlukla Türkçe). ` +
      `Güncel bilgi için Google aramasını kullan. Kod istenince kodu show_code ile ekranda göster, sesli okuma. ` +
      `Yalnızca bir bilgisayarın yapabileceği işleri (uygulama/dosya açmak, projede çalışmak, bilgisayar ekranını görmek) computer_command ile bilgisayara gönder. ` +
      `Kullanıcı hakkında kalıcı bir şey öğrenince remember ile kaydet. ` +
      `RESİM ÇİZEBİLİRSİN: çizim, resim, görsel, logo istenince hemen make_image aracını çağır (resmi değiştirmek için mode='edit'); "resim yapamam" asla deme. ` +
      `Bu cihazda uygulama açmak için open_app, hatırlatıcı ve zamanlayıcı için reminder, yapılacaklar listesi için todo, başka bir cihazda açmak/göstermek için send_to_device, "… protokolü / … modu" denince protocol kullan. `+
      `Kullanıcı bir şeyi sorduğunda önce search_memory ile ortak hafızaya bak. ` +
      `"(Sistem notu" ile başlayan mesajlar kullanıcıdan değil, arka planda biten işlerden gelir. ` +
      `Düşüncelerini sesli söyleme; sadece kullanıcıya cevabı söyle. ` +
      `Önceki konuşmalar ve yarım işler aşağıda; "kaldığımız yerden devam" denirse oradan sür, bilgisayardaki yarım projeler için computer_command ile "yarım kalan işe devam et" gönder.\n\n` +
      `Bugün: ${new Date().toLocaleString('tr-TR', { dateStyle: 'full', timeStyle: 'short' })}.\nBilgisayarlar: ${pcs}.\n\n` +
      `BİLGİSAYARDAKİ PROJELER:\n${projectsText() || '(yok)'}\n\nORTAK HAFIZA:\n${memoryText()}\n\nSON KONUŞMALAR (tüm cihazlar):\n${r || '(yok)'}`;
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
        outOpen = false; closeTurns(); syncSoon(); if (!playing()) setState(micOn ? 'listening' : 'idle'); }
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
  // Shared from another app (Android "Paylaş → JARVIS", manifest share_target):
  // JARVIS asks what to do with it — open on the TV, send to the computer …
  (function sharedIn() {
    const q = new URLSearchParams(location.search);
    const parts = ['share_title', 'share_text', 'share_url'].map(k => (q.get(k) || '').trim()).filter(Boolean);
    if (!parts.length) return;
    history.replaceState(null, '', location.pathname);
    const shared = [...new Set(parts)].join(' — ').slice(0, 1500);
    closeTurns(); transcript.push({ role: 'user', text: '📎 ' + shared, open: false }); renderLog();
    claimHere();
    connect().then(() => { setState('thinking');
      send({ realtimeInput: { text: `(Sistem notu) Kullanıcı başka bir uygulamadan bunu JARVIS'e paylaştı: ${shared}\n` +
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
