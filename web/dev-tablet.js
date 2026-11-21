/* MAYK on the tablet.
 *
 *  1. Landscape dashboard: clock, weather and agenda on the left, devices and the
 *     live conversation on the right, the core in the middle.
 *  2. Keyboard shortcuts (iPad keyboard, also on a computer's browser):
 *     ⌘/Ctrl+K or / → type · Esc → close · Alt+A ajanda · Alt+D cihazlar · Alt+C konuşma · Alt+R kumanda.
 *  3. Standby / photo frame: idle 3 min → big clock, next reminder, weather and the
 *     shared gallery as a slideshow. A touch brings MAYK back.
 *  4. Drop or paste a picture: MAYK looks at it.
 *  5. Full-screen button (wall-mounted tablet).
 *  6. Night dim: 22:00–07:00 the idle screen dims to a warm glow.
 *  7. Quick timers in the agenda: +1 / +5 / +10 / +15 min (every device).
 *  8. Bigger chess board in landscape.
 *  9. Panels open as centred cards instead of full-width sheets.
 * 10. Home-screen shortcuts (long-press the icon on Android: Konuş, Ajanda,
 *     Konuşma, Kumanda) — the page opens straight there (every device).
 */
(() => {
  'use strict';
  const J = window.JARVIS, K = window.JarvisKit; if (!J || !K) return;
  const $ = J.$, S = J.S;
  const tablet = J.is('tablet');

  // 10 ── ?a=… from a home-screen shortcut (every device) ───────────────────
  (function shortcut() {
    const q = new URLSearchParams(location.search), a = q.get('a'); if (!a) return;
    history.replaceState(null, '', location.pathname);
    setTimeout(() => {
      if (a === 'mic') J.startMic();
      else if (a === 'agenda') $('t-agenda').click();
      else if (a === 'chat') J.openSheet('s-chat');
      else if (a === 'remote') $('t-remote').click();
      else if (a === 'chess') $('t-chess').click();
    }, 500);
  })();

  // 7 ── quick timers in the agenda (every device but the watch) ────────────
  if (!J.is('watch')) {
    const row = document.createElement('div'); row.className = 'row'; row.id = 'quick-timers';
    row.innerHTML = '<span style="align-self:center;color:var(--dim);font-size:12px;letter-spacing:2px">ZAMANLAYICI</span>' +
      [1, 5, 10, 15].map(m => `<button class="btn" type="button" data-m="${m}">+${m} dk</button>`).join('');
    $('agenda-add').after(row);
    row.querySelectorAll('[data-m]').forEach(b => b.onclick = () => { J.toast(J.reminderTool({ action: 'set', minutes: +b.dataset.m, text: `${b.dataset.m} dakikalık zamanlayıcı` })); $('t-agenda').click(); });
  }

  // 2 ── keyboard shortcuts (tablet and computer browsers) ──────────────────
  if (J.is('tablet', 'pc')) {
    document.addEventListener('keydown', e => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); J.closeSheets(); $('inp').focus(); return; }
      if (e.key === 'Escape') { if (J.sheetOpen()) { e.preventDefault(); J.closeSheets(); } else if (J.typing()) document.activeElement.blur(); return; }
      if (e.key === '/' && !J.typing()) { e.preventDefault(); $('inp').focus(); return; }
      if (e.altKey && !mod) {
        const act = { a: () => $('t-agenda').click(), d: () => $('t-devs').click(), c: () => J.openSheet('s-chat'), r: () => $('t-remote').click() }[e.code.replace('Key', '').toLowerCase()];
        if (act) { e.preventDefault(); act(); }
      }
    });
  }

  // 4 ── drop or paste a picture: MAYK looks at it (every device with a page) ──
  async function lookAtFile(file) {
    if (!file || !/^image\//.test(file.type)) return false;
    const img = new Image(); const url = URL.createObjectURL(file);
    try {
      await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = url; });
      const sc = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement('canvas'); c.width = Math.round(img.naturalWidth * sc); c.height = Math.round(img.naturalHeight * sc);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      J.toast('Resme bakıyorum…');
      const q = $('inp').value.trim(); if (q) $('inp').value = '';
      if (!(await J.look(c.toDataURL('image/jpeg', 0.8).split(',')[1], 'image/jpeg', q ? 'şu soruyu yanıtla: ' + q : ''))) J.toast('Beyne bağlanamadım');
    } catch { J.toast('Resim okunamadı'); } finally { URL.revokeObjectURL(url); }
    return true;
  }
  document.addEventListener('dragover', e => { if ([...(e.dataTransfer?.items || [])].some(i => i.kind === 'file')) { e.preventDefault(); document.body.classList.add('dropping'); } });
  document.addEventListener('dragleave', e => { if (!e.relatedTarget) document.body.classList.remove('dropping'); });
  document.addEventListener('drop', e => { document.body.classList.remove('dropping'); const f = e.dataTransfer?.files?.[0]; if (f && /^image\//.test(f.type)) { e.preventDefault(); lookAtFile(f); } });
  document.addEventListener('paste', e => { const it = [...(e.clipboardData?.items || [])].find(i => /^image\//.test(i.type)); if (it) { e.preventDefault(); lookAtFile(it.getAsFile()); } });

  if (!tablet) return;

  J.css(`
    @media (orientation: landscape) and (min-width: 900px) {
      body.panels .app { max-width: none; grid-template-columns: 250px 1fr 290px; grid-template-rows: auto 1fr auto; column-gap: 22px; padding-left: 24px; padding-right: 24px; }
      body.panels .top { grid-column: 1 / span 3; }
      body.panels .left { display: block; grid-column: 1; grid-row: 2 / span 2; overflow: auto; }
      body.panels .main { grid-column: 2; }
      body.panels .bottom { grid-column: 2; }
      body.panels .side { display: flex; grid-column: 3; grid-row: 2 / span 2; flex-direction: column; gap: 14px; min-height: 0; }
      body.panels .clock { font-size: 54px; } body.panels .date { font-size: 14px; letter-spacing: 3px; }
      body.panels .hud { margin-top: 20px; gap: 14px; } body.panels .hud h4 { font-size: 11px; letter-spacing: 3px; margin-bottom: 4px; }
      body.panels .hud div.it { font-size: 14px; }
      body.panels .card { border-radius: 14px; padding: 14px; } body.panels .card h3 { font-size: 11px; letter-spacing: 3px; } body.panels .card .rule { height: 2px; margin: 8px 0 10px; }
      body.panels #side-log div { font-size: 13.5px; margin: 5px 0; }
      body.panels .core { width: min(52vh, 34vw); }
      #s-chess .board { width: min(68vh, 560px); }
    }
    body.k-tablet .sheet { left: 50%; right: auto; bottom: auto; top: 50%; transform: translate(-50%, -50%); width: min(640px, 92vw); max-height: 84vh;
                           border: 1px solid var(--line2); border-radius: 20px; padding-bottom: 18px; }
    body.k-tablet #s-chess { width: min(760px, 94vw); }
    body.dropping .app { outline: 3px dashed var(--acc); outline-offset: -10px; }
    #standby { position: fixed; inset: 0; z-index: 30; background: #000; display: grid; place-items: center; overflow: hidden; cursor: none; }
    #standby .ph { position: absolute; inset: 0; background-size: cover; background-position: center; opacity: 0; transition: opacity 2s; filter: brightness(.55); }
    #standby .ph.on { opacity: 1; }
    #standby .tx { position: relative; text-align: center; text-shadow: 0 2px 18px #000; }
    #standby .tm { font-size: min(22vw, 30vh); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -2px; }
    #standby .dt { font-size: min(3.4vw, 4vh); color: var(--med); letter-spacing: .3em; text-transform: uppercase; margin-top: 1vh; }
    #standby .nx { font-size: min(2.8vw, 3.4vh); color: var(--acc); margin-top: 3vh; } #standby .wx { font-size: min(2.6vw, 3.2vh); color: var(--med); margin-top: 1vh; }
    #nightdim { position: fixed; inset: 0; z-index: 35; pointer-events: none; background: rgba(20,6,0,.62); mix-blend-mode: multiply; opacity: 0; transition: opacity 4s; }
    #nightdim.on { opacity: 1; }
    #b-full { display: none; } body.k-tablet #b-full { display: grid; }
  `);

  // 1 ── landscape dashboard ────────────────────────────────────────────────
  const wide = matchMedia('(orientation: landscape) and (min-width: 900px)');
  function panels() {
    document.body.classList.toggle('panels', wide.matches);
    if (wide.matches) { J.refreshHudWeather(); J.renderHud(); }
  }
  try { wide.addEventListener('change', panels); } catch { wide.addListener(panels); }
  panels();

  // 5 ── full screen ────────────────────────────────────────────────────────
  const el = document.documentElement;
  const canFull = !!(el.requestFullscreen || el.webkitRequestFullscreen);
  if (canFull) {
    const b = document.createElement('button'); b.className = 'ib'; b.id = 'b-full'; b.type = 'button'; b.setAttribute('aria-label', 'Tam ekran'); b.textContent = '⛶';
    $('b-chat').before(b);
    b.onclick = () => {
      const on = document.fullscreenElement || document.webkitFullscreenElement;
      try { on ? (document.exitFullscreen || document.webkitExitFullscreen).call(document) : (el.requestFullscreen || el.webkitRequestFullscreen).call(el); } catch { J.toast('Tam ekran açılamadı'); }
    };
  }

  // 3 ── standby / photo frame ──────────────────────────────────────────────
  const sb = document.createElement('div'); sb.id = 'standby'; sb.hidden = true;
  sb.innerHTML = '<div class="ph"></div><div class="ph"></div><div class="tx"><div class="tm"></div><div class="dt"></div><div class="nx"></div><div class="wx"></div></div>';
  document.body.appendChild(sb);
  const ph = sb.querySelectorAll('.ph'); let phI = 0, phN = 0;
  let weather = ''; J.on('weather', w => { weather = w; });
  function paintStandby() {
    const d = new Date();
    sb.querySelector('.tm').textContent = d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
    sb.querySelector('.dt').textContent = d.toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' });
    sb.querySelector('.nx').textContent = K.nextUp(J.pendingRem()) ? '⏰ ' + K.nextUp(J.pendingRem()) : '';
    sb.querySelector('.wx').textContent = weather;
  }
  function nextPhoto() {
    const g = J.gallery.filter(x => /^https:\/\//.test(x.url || '')); if (!g.length) return;
    const cur = ph[phI % 2], nxt = ph[(phI + 1) % 2]; phI++;
    nxt.style.backgroundImage = `url("${g[phN++ % g.length].url.replace(/"/g, '%22')}")`;
    nxt.classList.add('on'); cur.classList.remove('on');
  }
  let sbT = null;
  function standby(on) {
    if (on === !sb.hidden) return;
    sb.hidden = !on; clearInterval(sbT);
    if (on) { J.refreshHudWeather(); paintStandby(); nextPhoto(); let n = 0; sbT = setInterval(() => { paintStandby(); if (++n % 12 === 0) nextPhoto(); }, 1000); }
  }
  sb.addEventListener('pointerdown', e => { e.preventDefault(); J.touch(); standby(false); });
  J.toggleSetting('standby', '🖼 Bekleme ekranı (3 dk)', on => { if (!on) standby(false); }, true);

  // 6 ── night dim ──────────────────────────────────────────────────────────
  const dim = document.createElement('div'); dim.id = 'nightdim'; document.body.appendChild(dim);
  J.toggleSetting('nightDim', '🌙 Gece karartma (22–07)', on => { if (!on) dim.classList.remove('on'); }, true);

  setInterval(() => {
    const busy = J.micOn || J.speaking || J.state === 'thinking' || J.sheetOpen();
    const idle = busy ? 0 : J.idleMs();
    if (S.standby && idle > 180000) standby(true);
    if (busy) standby(false);
    dim.classList.toggle('on', !!S.nightDim && K.isNight(new Date().getHours()) && idle > 60000);
  }, 2000);
})();
