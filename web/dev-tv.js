/* MAYK on the TV (and every big screen: the projector uses this too).
 *
 *  1. The remote's arrows move between buttons (spatial navigation, like Android TV).
 *  2. Back key (Tizen, webOS, Android TV, Esc/Backspace) closes whatever is open.
 *  3. Colour keys / number keys: 🔴1 ajanda · 🟢2 cihazlar · 🟡3 konuşma · 🔵4 kumanda; play/pause = mic.
 *  4. Ambient screen after 5 min: clock, weather and next reminder that slowly
 *     move around so nothing burns into the panel.
 *  5. Overscan: ⚙ → screen edge margin, for TVs that crop the picture.
 *  6. A big, bright focus ring you can see from the sofa.
 *  7. A video sent to the TV ("bunu televizyonda aç") plays right in MAYK —
 *     TV browsers block pop-up windows.
 *  8. Quick commands you can pick with the remote: hava, ajanda, haberler, durum.
 *  9. Large live captions of what MAYK says.
 * 10. Refreshes itself at 04:00 when nobody is using it (TV browsers leak memory).
 */
(() => {
  'use strict';
  const J = window.JARVIS, K = window.JarvisKit; if (!J || !K) return;
  if (!J.is('tv', 'projector')) return;
  const $ = J.$, S = J.S;

  J.css(`
    body.big .app { padding: calc(2.2vw + var(--os, 0vh)) calc(2.6vw + var(--os, 0vh)); }
    body.big :focus { outline: none; }
    body.big :focus-visible, body.big .tvfocus { outline: .32vw solid var(--hot) !important; outline-offset: .25vw; box-shadow: 0 0 2.2vw rgba(255,180,80,.75) !important;
                                                  transform: scale(1.06); transition: transform .12s, box-shadow .12s; position: relative; z-index: 2; }
    .qbar { display: flex; gap: .7vw; justify-content: center; flex-wrap: wrap; margin-top: .3vw; }
    .qbar .chip { border-color: var(--line2); }
    #ambient { position: fixed; inset: 0; z-index: 30; background: #000; display: grid; place-items: center; cursor: none; }
    #ambient .box { text-align: center; transition: transform 3s ease-in-out; }
    #ambient .tm { font-size: 13vw; font-weight: 200; font-variant-numeric: tabular-nums; color: #d9cfc6; letter-spacing: -.3vw; line-height: 1; }
    #ambient .dt { font-size: 1.8vw; letter-spacing: .5vw; color: #8a7f76; text-transform: uppercase; margin-top: 1vw; }
    #ambient .nx { font-size: 1.6vw; color: #c98a3d; margin-top: 2.2vw; } #ambient .wx { font-size: 1.5vw; color: #8a7f76; margin-top: .8vw; }
    #tvplayer { position: fixed; inset: 0; z-index: 32; background: #000; }
    #tvplayer iframe { width: 100%; height: 100%; border: 0; }
    #tvplayer button { position: absolute; top: 2vw; right: 2vw; z-index: 2; }
    #caption { position: fixed; left: 50%; bottom: 7vh; transform: translateX(-50%); max-width: 70vw; z-index: 25; text-align: center; pointer-events: none;
               font-size: 2.3vw; line-height: 1.3; padding: .8vw 1.6vw; border-radius: 1vw; background: rgba(0,0,0,.72); color: #fff;
               text-shadow: 0 2px 6px #000; opacity: 0; transition: opacity .4s; }
    #caption.on { opacity: 1; }
  `);

  // 5 ── overscan ───────────────────────────────────────────────────────────
  const applyOs = () => document.documentElement.style.setProperty('--os', K.clamp(S.overscan, 0, 8) + 'vh');
  applyOs();
  const osRow = J.addSetting('<span style="flex:1;font-size:13px;color:var(--med)">Ekran kenar payı (TV kenarları kesiyorsa artır)</span><button class="btn" type="button" data-d="-1">−</button><b id="os-val" style="min-width:44px;text-align:center"></b><button class="btn" type="button" data-d="1">+</button>');
  const paintOs = () => { $('os-val').textContent = '%' + K.clamp(S.overscan, 0, 8); };
  osRow.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { S.overscan = K.clamp((+S.overscan || 0) + +b.dataset.d, 0, 8); J.save(); applyOs(); paintOs(); });
  paintOs();

  // 8 ── quick commands ─────────────────────────────────────────────────────
  const QUICK = [['🌤 Hava', 'Bugün hava nasıl?'], ['📅 Ajandam', 'Bugün ajandamda ne var? Hatırlatıcılarımı ve yapılacaklarımı söyle.'],
                 ['📰 Haberler', 'Bugünün en önemli üç haberini kısaca anlat.'], ['📊 Durum', 'Cihazlarımın durum raporunu ver.'], ['🎵 Müzik', 'Televizyonda rahatlatıcı bir müzik aç.']];
  const qbar = document.createElement('div'); qbar.className = 'qbar';
  qbar.innerHTML = QUICK.map(([l], i) => `<button class="chip" type="button" data-i="${i}">${l}</button>`).join('');
  document.querySelector('.tools').after(qbar);
  qbar.querySelectorAll('button').forEach(b => b.onclick = () => J.say(QUICK[+b.dataset.i][1]));

  // 7 ── videos play inside MAYK ──────────────────────────────────────────
  const player = document.createElement('div'); player.id = 'tvplayer'; player.hidden = true;
  player.innerHTML = '<button class="btn pri" type="button">✕ Kapat (Geri)</button><iframe allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>';
  document.body.appendChild(player);
  const closePlayer = () => { player.hidden = true; player.querySelector('iframe').src = 'about:blank'; $('mic').focus(); };
  player.querySelector('button').onclick = closePlayer;
  J.on('open', c => {
    const emb = K.youtubeEmbed(c.url); if (!emb) return false;
    standby(false); player.querySelector('iframe').src = emb; player.hidden = false; player.querySelector('button').focus();
    return true;
  });

  // 9 ── live captions ──────────────────────────────────────────────────────
  const cap = document.createElement('div'); cap.id = 'caption'; document.body.appendChild(cap);
  let capOff = null;
  setInterval(() => {
    if (!J.speaking || !player.hidden) return;
    const last = J.transcript.reverse().find(t => t.role === 'jarvis'); if (!last) return;
    const t = last.text.trim(); const tail = t.length > 150 ? '…' + t.slice(-150).replace(/^\S*\s/, '') : t;
    cap.textContent = tail; cap.classList.add('on'); clearTimeout(capOff); capOff = setTimeout(() => cap.classList.remove('on'), 4000);
  }, 300);
  J.toggleSetting('captions', '💬 Büyük altyazı', on => { cap.style.display = on ? '' : 'none'; }, true);

  // 4 ── ambient screen with burn-in protection ─────────────────────────────
  const amb = document.createElement('div'); amb.id = 'ambient'; amb.hidden = true;
  amb.innerHTML = '<div class="box"><div class="tm"></div><div class="dt"></div><div class="nx"></div><div class="wx"></div></div>';
  document.body.appendChild(amb);
  let weather = ''; J.on('weather', w => { weather = w; });
  let ambT = null, minute = 0;
  function paintAmb() {
    const d = new Date();
    amb.querySelector('.tm').textContent = d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    amb.querySelector('.dt').textContent = d.toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' });
    const nx = K.nextUp(J.pendingRem()); amb.querySelector('.nx').textContent = nx ? '⏰ ' + nx : '';
    amb.querySelector('.wx').textContent = weather;
    const m = Math.floor(Date.now() / 60000);
    if (m !== minute) { minute = m; const p = K.drift(m, Math.min(innerWidth, innerHeight) * 0.18); amb.querySelector('.box').style.transform = `translate(${p.x}px, ${p.y}px)`; }
  }
  function standby(on) {
    if (on === !amb.hidden) return;
    amb.hidden = !on; clearInterval(ambT); J.core.paused = on;
    if (on) { paintAmb(); ambT = setInterval(paintAmb, 5000); }
  }
  J.toggleSetting('ambient', '🌌 Bekleme ekranı (5 dk)', on => { if (!on) standby(false); }, true);
  setInterval(() => {
    const busy = J.micOn || J.speaking || J.state === 'thinking' || J.sheetOpen() || !player.hidden;
    if (busy) standby(false); else if (S.ambient && J.idleMs() > 300000) standby(true);
  }, 3000);
  amb.addEventListener('pointerdown', () => { J.touch(); standby(false); });

  // 1–3 ── the remote ───────────────────────────────────────────────────────
  function focusables() {
    const sheet = [...document.querySelectorAll('.sheet')].find(s => !s.hidden);
    const scope = !player.hidden ? player : sheet || document;
    return [...scope.querySelectorAll('button, input, select, [tabindex]:not([tabindex="-1"])')]
      .filter(el => !el.disabled && !el.closest('[hidden]') && (sheet || !el.closest('.sheet')) && el.getBoundingClientRect().width > 0);
  }
  function move(dir) {
    const list = focusables(); if (!list.length) return;
    const cur = document.activeElement;
    if (!list.includes(cur)) { (list.find(el => el.id === 'mic') || list[0]).focus(); return; }
    const box = el => { const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
    const boxes = list.map(box), i = K.nearest(box(cur), boxes, dir);
    if (i >= 0) { list[i].focus(); list[i].scrollIntoView({ block: 'nearest' }); }
  }
  function back() {
    if (!player.hidden) { closePlayer(); return true; }
    if (!amb.hidden) { standby(false); return true; }
    if (J.sheetOpen()) { J.closeSheets(); $('mic').focus(); return true; }
    if (J.typing()) { document.activeElement.blur(); return true; }
    return false;
  }
  document.addEventListener('keydown', e => {
    J.touch();
    if (!amb.hidden) { e.preventDefault(); standby(false); return; }       // any key wakes it, and does nothing else
    const act = K.tvKey(e.key, e.keyCode); if (!act) return;
    const typing = J.typing(), el = document.activeElement;
    if (act === 'back') {
      if (typing && (e.key === 'Backspace')) return;                       // deleting a letter
      if (back()) e.preventDefault();
      return;
    }
    if (['left', 'right', 'up', 'down'].includes(act)) {
      if (typing && el.tagName === 'INPUT' && (act === 'left' || act === 'right')) {
        const atEdge = act === 'left' ? el.selectionStart === 0 : el.selectionEnd === el.value.length;
        if (!atEdge) return;
      }
      if (typing && el.tagName === 'SELECT' && (act === 'up' || act === 'down')) return;
      e.preventDefault(); move(act); return;
    }
    if (act === 'ok' || typing) return;                                    // Enter clicks the focused button by itself
    if (act === 'mic') { if (e.key !== ' ' && e.key !== 'MediaPlayPause') { e.preventDefault(); $('mic').click(); } return; }  // app.js already does these two
    const go = { agenda: () => $('t-agenda').click(), devices: () => $('t-devs').click(), chat: () => J.openSheet('s-chat'), remote: () => $('t-remote').click() }[act];
    if (go) { e.preventDefault(); go(); setTimeout(() => move('down'), 50); }
  });

  // 10 ── nightly refresh ───────────────────────────────────────────────────
  function nightly() {
    setTimeout(function tryNow() {
      if (J.idleMs() > 600000 && !J.micOn && !J.speaking && player.hidden) location.reload();
      else setTimeout(tryNow, 30 * 60000);
    }, K.msUntil(4));
  }
  nightly();
  J.refreshHudWeather();
})();
