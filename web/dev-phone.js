/* AETHER on the phone (iPhone 14 Pro Max first, any phone works).
 *
 *  1. Hold the mic to talk, let go to stop (a short tap still toggles).
 *  2. Swipe up on the core: conversation · swipe down: agenda · swipe a sheet down: close.
 *  3. Last typed commands as chips above the box; ↑/↓ in the box recalls them.
 *  4. Long-press the answer: copied.
 *  5. Text size (⚙ → A− / A+).
 *  6. Battery saver: the core draws slower (⚙, or by itself on low battery / reduced motion).
 *  7. The mic closes itself after 45 s of silence, so a forgotten mic doesn't drain the battery.
 *  8. Landscape layout: core on the left, answer and controls on the right.
 *  9. Tool chips in one swipeable row — more room for the core.
 * 10. Shake the phone while AETHER is talking: it stops.
 */
(() => {
  'use strict';
  const J = window.AETHER, K = window.AetherKit; if (!J || !K) return;
  const phone = J.is('phone'), handheld = J.is('phone', 'tablet');
  if (!handheld) return;
  const $ = J.$, S = J.S;

  J.css(`
    #mic { -webkit-touch-callout: none; user-select: none; -webkit-user-select: none; touch-action: manipulation; }
    #reply { -webkit-touch-callout: none; }
    .reply, .msg { font-size: calc(15px * var(--fs, 1)); } .reply .you { font-size: calc(12.5px * var(--fs, 1)); }
    #hist { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; padding: 0 2px; }
    #hist::-webkit-scrollbar { display: none; }
    #hist button { flex: 0 0 auto; max-width: 70vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 6px 10px; border-radius: 99px;
                   border: 1px solid var(--line); background: rgba(40,26,14,.55); color: var(--med); font-size: 12.5px; font-family: inherit; }
    body.k-phone .tools { flex-wrap: nowrap; overflow-x: auto; justify-content: flex-start; scroll-snap-type: x proximity; scrollbar-width: none;
                          padding-bottom: 2px; -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 14px, #000 calc(100% - 14px), transparent 100%); }
    body.k-phone .tools::-webkit-scrollbar { display: none; }
    body.k-phone .tools .chip { flex: 0 0 auto; scroll-snap-align: start; }
    @media (orientation: landscape) and (max-height: 520px) {
      body.k-phone .app { max-width: none; grid-template-columns: 42vw 1fr; grid-template-rows: auto 1fr auto; column-gap: 14px;
                          padding-left: max(14px, env(safe-area-inset-left)); padding-right: max(14px, env(safe-area-inset-right)); }
      body.k-phone .top { grid-column: 1 / span 2; }
      body.k-phone .main { grid-column: 1; grid-row: 2 / span 2; }
      body.k-phone .core { width: min(40vw, 62vh); }
      body.k-phone #wave { height: 24px; }
      body.k-phone .reply { max-height: 40vh; }
      body.k-phone .bottom { grid-column: 2; grid-row: 2 / span 2; align-content: end; }
      body.k-phone .bottom::before { content: ""; }
    }
  `);

  // 1 ── hold to talk ───────────────────────────────────────────────────────
  const mic = $('mic');
  let holdT = null, held = false, skipClick = false;
  mic.addEventListener('pointerdown', () => {
    askMotion();
    if (J.micOn) return;
    held = false;
    holdT = setTimeout(() => { held = true; skipClick = true; J.vibrate(20); J.startMic(); J.toast('Bırakınca dinlemeyi bitiririm'); }, 380);
  });
  const release = () => { clearTimeout(holdT); if (held) { held = false; setTimeout(() => J.stopMic(), 300); } };
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => mic.addEventListener(ev, release));
  mic.addEventListener('contextmenu', e => e.preventDefault());
  // the click that ends a hold must not toggle the mic back on
  mic.addEventListener('click', e => { if (skipClick) { skipClick = false; e.stopImmediatePropagation(); e.preventDefault(); } }, true);

  // 2 ── swipes ─────────────────────────────────────────────────────────────
  function swipeOn(el, fn) {
    let x0 = 0, y0 = 0, t0 = 0;
    el.addEventListener('touchstart', e => { const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); }, { passive: true });
    el.addEventListener('touchend', e => { const t = e.changedTouches[0]; const d = K.swipeDir(t.clientX - x0, t.clientY - y0, Date.now() - t0, 60); if (d) fn(d, e); }, { passive: true });
  }
  swipeOn(document.querySelector('.main'), d => {
    if (d === 'up') J.openSheet('s-chat');
    else if (d === 'down') $('t-agenda').click();
  });
  document.querySelectorAll('.sheet').forEach(sh => swipeOn(sh, d => { if (d === 'down' && sh.scrollTop <= 0) J.closeSheets(); }));

  // 3 ── command history ────────────────────────────────────────────────────
  const inp = $('inp');
  const hist = document.createElement('div'); hist.id = 'hist'; hist.hidden = true;
  $('ask').parentNode.insertBefore(hist, $('ask'));
  let hIdx = -1;
  $('ask').addEventListener('submit', () => { S.hist = K.histPush(S.hist, inp.value); J.save(); hIdx = -1; hist.hidden = true; setTimeout(() => { if (document.activeElement === inp) showHist(); }, 60); }, true);
  function showHist() {
    const L = (S.hist || []).slice(-6).reverse();
    hist.innerHTML = L.map((t, i) => `<button type="button" data-i="${i}">↺ ${J.esc(t)}</button>`).join('');
    hist.querySelectorAll('button').forEach(b => b.onpointerdown = e => { e.preventDefault(); J.ask(L[+b.dataset.i]); });
    hist.hidden = !L.length || !!inp.value;
  }
  inp.addEventListener('focus', showHist);
  inp.addEventListener('input', () => { hist.hidden = !!inp.value || !(S.hist || []).length; });
  inp.addEventListener('blur', () => setTimeout(() => { hist.hidden = true; }, 150));
  inp.addEventListener('keydown', e => {
    const L = S.hist || []; if (!L.length || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
    e.preventDefault();
    hIdx = e.key === 'ArrowUp' ? Math.min(L.length - 1, hIdx + 1) : Math.max(-1, hIdx - 1);
    inp.value = hIdx < 0 ? '' : L[L.length - 1 - hIdx];
  });

  // 4 ── long-press the answer to copy it ───────────────────────────────────
  let copyT = null;
  $('reply').addEventListener('pointerdown', () => { copyT = setTimeout(async () => {
    const t = $('reply-text').textContent.trim(); if (!t) return;
    try { await navigator.clipboard.writeText(t); J.vibrate(15); J.toast('Yanıt kopyalandı'); } catch { J.toast('Kopyalanamadı'); }
  }, 600); });
  ['pointerup', 'pointercancel', 'pointermove'].forEach(ev => $('reply').addEventListener(ev, () => clearTimeout(copyT)));

  // 5 ── text size ──────────────────────────────────────────────────────────
  const applyFs = () => document.documentElement.style.setProperty('--fs', String(S.fs || 1));
  applyFs();
  const fsRow = J.addSetting('<span style="flex:1;font-size:13px;color:var(--med)">Yazı boyutu</span><button class="btn" type="button" data-d="-1">A−</button><b id="fs-val" style="min-width:44px;text-align:center"></b><button class="btn" type="button" data-d="1">A+</button>');
  const paintFs = () => { $('fs-val').textContent = Math.round((S.fs || 1) * 100) + '%'; };
  fsRow.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { S.fs = K.clamp(Math.round(((S.fs || 1) + 0.1 * +b.dataset.d) * 10) / 10, 0.8, 1.6); J.save(); applyFs(); paintFs(); });
  paintFs();

  // 6 ── battery saver ──────────────────────────────────────────────────────
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  function applyFps() {
    const b = J.battery;
    const fps = K.coreFps({ reduced: reduced.matches, saver: !!S.saver, battery: b.battery ?? null, charging: !!b.charging, hidden: document.visibilityState !== 'visible' });
    J.core.paused = fps < 0; J.core.fps = fps > 0 ? fps : 0;
  }
  J.toggleSetting('saver', '🔋 Pil tasarrufu', applyFps);
  document.addEventListener('visibilitychange', applyFps);
  try { reduced.addEventListener('change', applyFps); } catch { /* old Safari */ }
  setInterval(applyFps, 15000);

  // 7 ── mic closes itself after 45 s of silence (phone only) ───────────────
  if (phone) {
    let lastVoice = Date.now();
    J.on('state', s => { if (s === 'listening' || s === 'speaking' || s === 'thinking') lastVoice = Date.now(); });
    setInterval(() => {
      if (!J.micOn || held) { lastVoice = Date.now(); return; }
      if (J.micLevel > 0.05 || J.speaking || J.state === 'thinking') { lastVoice = Date.now(); return; }
      if (Date.now() - lastVoice > 45000) { J.stopMic(); J.toast('45 sn ses gelmedi — pil için mikrofonu kapattım'); }
    }, 1000);
  }

  // 10 ── shake to stop AETHER talking ──────────────────────────────────────
  let motionAsked = false; const jolts = [];
  function askMotion() {
    if (motionAsked) return; motionAsked = true;
    try { if (window.DeviceMotionEvent && typeof DeviceMotionEvent.requestPermission === 'function') DeviceMotionEvent.requestPermission().catch(() => {}); } catch {}
  }
  window.addEventListener('devicemotion', e => {
    if (!J.speaking) return;
    const a = e.acceleration && e.acceleration.x != null ? e.acceleration : null;
    const g = e.accelerationIncludingGravity || {};
    const mag = a ? Math.hypot(a.x || 0, a.y || 0, a.z || 0) : Math.abs(Math.hypot(g.x || 0, g.y || 0, g.z || 0) - 9.81);
    const now = Date.now(); jolts.push({ t: now, a: mag }); while (jolts.length && now - jolts[0].t > 1500) jolts.shift();
    if (K.shaken(jolts, now)) { jolts.length = 0; J.hush(); J.vibrate(40); J.toast('Sustum 🤐'); }
  });
})();
